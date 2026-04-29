import asyncio
import logging
from typing import Optional, AsyncGenerator, Dict, Any, Union
from enum import Enum
import html
import re
import telegram
from telegram import Update, Message
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from utils.logging_utils import setup_logging
from bot_core.services.trading.position_service import position_service

setup_logging()
logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4000


class ParseMode(Enum):
    """消息解析模式枚举"""
    HTML = "HTML"
    MARKDOWN = "MarkdownV2"
    NONE = None


class MessageErrorHandler:
    """统一的消息错误处理器"""
    
    @staticmethod
    async def handle_send_error(
        error: Exception,
        chat_id: int,
        text: str,
        bot: telegram.Bot,
        placeholder: Optional[Message] = None,
        fallback_parse_mode: Optional[str] = None
    ) -> Optional[Message]:
        """处理消息发送错误，包含回退逻辑"""
        if isinstance(error, BadRequest):
            error_msg = str(error)
            logger.warning(f"消息解析失败: {error}，尝试回退模式")
            
            # 检查是否是HTML解析错误
            if "Can't parse entities" in error_msg or "unsupported start tag" in error_msg:
                # 对于HTML解析错误，尝试清理文本并使用无解析模式
                cleaned_text = MessageErrorHandler._clean_problematic_text(text)
                try:
                    if placeholder:
                        result = await placeholder.edit_text(text=cleaned_text, parse_mode=None)
                        return result if not isinstance(result, bool) else placeholder
                    else:
                        return await bot.send_message(chat_id=chat_id, text=cleaned_text, parse_mode=None)
                except Exception as fallback_error:
                    logger.error(f"清理文本后仍然失败: {fallback_error}")
                    # 最后的回退：发送简化的错误消息
                    return await MessageErrorHandler._send_error_message(chat_id, bot, placeholder, "消息包含无法解析的内容")
            
            # 其他BadRequest错误的处理
            if fallback_parse_mode is not None:
                try:
                    if placeholder:
                        result = await placeholder.edit_text(text=text, parse_mode=fallback_parse_mode)
                        return result if not isinstance(result, bool) else placeholder
                    else:
                        return await bot.send_message(chat_id=chat_id, text=text, parse_mode=fallback_parse_mode)
                except Exception as fallback_error:
                    logger.error(f"回退模式也失败: {fallback_error}")
                    return await MessageErrorHandler._send_error_message(chat_id, bot, placeholder, "消息发送失败")
            else:
                return await MessageErrorHandler._send_error_message(chat_id, bot, placeholder, "消息格式错误")
        
        elif isinstance(error, TelegramError):
            if "Message is not modified" in str(error):
                logger.debug("消息未修改，跳过")
                return placeholder
            else:
                logger.error(f"Telegram错误: {error}")
                return await MessageErrorHandler._send_error_message(chat_id, bot, placeholder, f"Telegram错误: {error}")
        
        else:
            logger.error(f"未知错误: {error}", exc_info=True)
            return await MessageErrorHandler._send_error_message(chat_id, bot, placeholder, "发送消息时发生未知错误")
    
    @staticmethod
    def _clean_problematic_text(text: str) -> str:
        """清理可能导致Telegram解析错误的文本"""
        # 转义HTML特殊字符
        cleaned_text = html.escape(text)
        
        # 移除或替换可能导致解析错误的特殊字符
        # 移除不可见的Unicode字符和控制字符
        cleaned_text = re.sub(r'[\u200b-\u200f\u2028-\u202f\u205f-\u206f\ufeff]', '', cleaned_text)
        
        # 替换可能导致问题的特殊标点符号
        problematic_chars = {
            '｡': '。',  # 全角句号替换为中文句号
            '｢': '「',  # 全角左引号
            '｣': '」',  # 全角右引号
            '､': '、',  # 全角顿号
            '･': '·',   # 全角中点
        }
        
        for old_char, new_char in problematic_chars.items():
            cleaned_text = cleaned_text.replace(old_char, new_char)
        
        # 移除可能导致HTML解析错误的特殊符号组合
        cleaned_text = re.sub(r'[<>](?![a-zA-Z/])', '', cleaned_text)  # 移除不是HTML标签的尖括号
        
        return cleaned_text
    
    @staticmethod
    async def _send_error_message(
        chat_id: int, 
        bot: telegram.Bot, 
        placeholder: Optional[Message], 
        error_text: str
    ) -> Optional[Message]:
        """发送错误消息"""
        try:
            if placeholder:
                result = await placeholder.edit_text(error_text)
                return result if not isinstance(result, bool) else placeholder
            else:
                return await bot.send_message(chat_id=chat_id, text=error_text)
        except Exception as e:
            logger.error(f"发送错误消息也失败: {e}")
            return None


class ChatIdResolver:
    """Chat ID 解析器，统一处理各种获取chat_id的逻辑"""
    
    @staticmethod
    def resolve_chat_id(
        update: Optional[Update] = None,
        placeholder: Optional[Message] = None,
        explicit_chat_id: Optional[int] = None
    ) -> Optional[int]:
        """按优先级解析chat_id"""
        # 1. 显式提供的chat_id
        if explicit_chat_id:
            return explicit_chat_id
        
        # 2. 从placeholder消息获取
        if placeholder:
            return placeholder.chat_id
        
        # 3. 从update获取
        if update:
            # 3.1 普通消息
            if update.message:
                return update.message.chat_id
            
            # 3.2 回调查询
            if update.callback_query and update.callback_query.message:
                return getattr(update.callback_query.message, 'chat_id', None)
            
            # 3.3 有效聊天
            if update.effective_chat:
                return update.effective_chat.id
        
        return None

class MessageFactory:
    """
    一个用于发送和编辑Telegram消息的工厂类，封装了通用逻辑。
    - 自动处理长消息分割。
    - 统一处理Markdown/HTML解析错误和回退。
    - 简化消息发送和编辑的接口。
    """

    def __init__(self, update: Optional[Update] = None, context: Optional[ContextTypes.DEFAULT_TYPE] = None):
        self.update = update 
        self.context = context
        if not self.update and not self.context:
            raise ValueError("必须提供 Update 或 ContextTypes.DEFAULT_TYPE 对象")
        if self.context:
            self.bot = self.context.bot
        elif self.update:
            self.bot = self.update.get_bot()
        self.chat_id_resolver = ChatIdResolver()
        self.error_handler = MessageErrorHandler()
    
    @staticmethod
    def format_extra_content(summary: Optional[str] = None, comment: Optional[str] = None) -> str:
        """格式化额外内容（摘要和评论）"""
        content_parts = []
        
        if summary and summary != "暂无":
            content_parts.append(f"<b>摘要:</b>\n{html.escape(summary)}")
        
        if comment and comment != "暂无":
            content_parts.append(f"<b>评论:</b>\n{html.escape(comment)}")
        
        return "\n\n".join(content_parts)

        

    async def _send_or_edit_internal(
        self,
        text: str,
        chat_id: Optional[int] = None,
        placeholder: Optional[Message] = None,
        parse_mode: str = "HTML",
        photo: Optional[bytes] = None
    ) -> Optional[Message]:
        """
        内部核心方法，处理所有消息的发送和编辑。
        """
        # 使用ChatIdResolver获取chat_id
        resolved_chat_id = self.chat_id_resolver.resolve_chat_id(
            update=self.update,
            placeholder=placeholder,
            explicit_chat_id=chat_id
        )
        
        if not resolved_chat_id:
            logger.error(f"无法确定 chat_id。Update: {self.update}, Placeholder: {placeholder}")
            return None

        logger.debug(f"确定的 chat_id: {resolved_chat_id}")

        # 1. 分割消息
        text_parts = self._split_text(text)

        # 2. 发送或编辑
        sent_message = None
        current_placeholder = placeholder
        
        for i, part in enumerate(text_parts):
            is_first_part = (i == 0)
            target_message = current_placeholder if is_first_part and current_placeholder else None
            
            try:
                # 尝试使用指定解析模式发送
                sent_message = await self._try_send_part(
                    chat_id=resolved_chat_id,
                    text_part=part,
                    placeholder=target_message,
                    parse_mode=parse_mode,
                    photo=photo if is_first_part else None # 只有第一部分带图片
                )
            except Exception as e:
                # 使用统一错误处理器，为HTML解析失败提供回退模式
                fallback_mode = None if parse_mode != "HTML" else None  # 如果是HTML模式失败，回退到无解析模式
                sent_message = await self.error_handler.handle_send_error(
                    error=e,
                    chat_id=resolved_chat_id,
                    text=part,
                    bot=self.bot,
                    placeholder=target_message,
                    fallback_parse_mode=fallback_mode
                )
                
                if not sent_message:
                    logger.error(f"消息部分 {i+1} 发送完全失败")
                    continue

            # 更新 placeholder 以便下一部分回复
            if sent_message and not current_placeholder:
                current_placeholder = sent_message

        return current_placeholder or sent_message


    async def _try_send_part(
        self,
        chat_id: int,
        text_part: str,
        placeholder: Optional[Message],
        parse_mode: Optional[str],
        photo: Optional[bytes]
    ) -> Message:
        """尝试发送或编辑单个消息部分。"""
        try:
            if placeholder:
                # 如果有图片，不能编辑，只能发送新消息
                if photo:
                    await placeholder.delete() # 删除占位符
                    return await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=text_part, parse_mode=parse_mode)

                # 编辑消息并统一处理返回值
                result = await placeholder.edit_text(text=text_part, parse_mode=parse_mode)
                return self._normalize_message_result(result, placeholder)

            if photo:
                return await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=text_part, parse_mode=parse_mode)

            # 如果是回复，使用 reply_text
            if self.update and self.update.message:
                return await self.update.message.reply_text(text=text_part, parse_mode=parse_mode)
            # 否则直接发送
            return await self.bot.send_message(chat_id=chat_id, text=text_part, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"发送消息部分失败: {e}", exc_info=True)
            raise
    
    def _normalize_message_result(self, result: Union[Message, bool], fallback_message: Message) -> Message:
        """统一处理消息操作的返回值"""
        if isinstance(result, bool):
            # 消息未修改或编辑成功但未返回新消息对象，返回原消息对象
            logger.debug("消息操作返回布尔值，使用fallback消息对象")
            return fallback_message
        return result


    def _split_text(self, text: str) -> list[str]:
        """将长文本分割成多个部分。"""
        if len(text) <= TELEGRAM_MESSAGE_LIMIT:
            return [text]
        
        parts = []
        current_lines = []
        current_length = 0
        
        for line in text.split('\n'):
            line_length = len(line) + 1  # +1 for newline character
            
            # 如果单行就超长，强制截断
            if len(line) > TELEGRAM_MESSAGE_LIMIT:
                # 先保存当前积累的内容
                if current_lines:
                    parts.append('\n'.join(current_lines).strip())
                    current_lines = []
                    current_length = 0
                
                # 分割超长行
                while len(line) > TELEGRAM_MESSAGE_LIMIT:
                    parts.append(line[:TELEGRAM_MESSAGE_LIMIT])
                    line = line[TELEGRAM_MESSAGE_LIMIT:]
                
                # 剩余部分作为新的开始
                if line:
                    current_lines = [line]
                    current_length = len(line)
                continue
            
            # 检查是否会超出限制
            if current_length + line_length > TELEGRAM_MESSAGE_LIMIT:
                if current_lines:
                    parts.append('\n'.join(current_lines).strip())
                current_lines = [line]
                current_length = len(line)
            else:
                current_lines.append(line)
                current_length += line_length
        
        # 添加最后一部分
        if current_lines:
            final_part = '\n'.join(current_lines).strip()
            if final_part:
                parts.append(final_part)
            
        return parts

    async def send(self, text: str, chat_id: Optional[int] = None, parse_mode: str = "HTML", photo: Optional[bytes] = None) -> Optional[Message]:
        """发送一条新消息。"""
        return await self._send_or_edit_internal(text=text, chat_id=chat_id, parse_mode=parse_mode, photo=photo)

    async def edit(self, placeholder: Message, text: str, parse_mode: str = "HTML", summary: Optional[str] = None, comment: Optional[str] = None) -> Optional[Message]:
        """编辑一条已存在的消息。"""
        #logger.debug(f"MessageFactory.edit 收到参数: text={repr(text[:100])}, summary={repr(summary)}, comment={repr(comment)}")

        # 使用统一的格式化方法
        extra_content = self.format_extra_content(summary, comment)
        
        if extra_content:
            # 使用 expandable 属性来创建可折叠的引用块
            text = f'{text}\n\n<blockquote expandable>{extra_content}</blockquote>'

        logger.debug(f"MessageFactory.edit 最终发送文本: {repr(text[:200])}")
        return await self._send_or_edit_internal(text=text, placeholder=placeholder, parse_mode=parse_mode)


# --- 向后兼容的函数（已废弃，建议使用MessageFactory） ---

import warnings

def _deprecated_warning(func_name: str, replacement: str):
    """发出废弃警告"""
    warnings.warn(
        f"{func_name} 已废弃，请使用 {replacement}",
        DeprecationWarning,
        stacklevel=3
    )

async def update_message(text: str, placeholder: Message) -> Optional[Message]:
    """
    兼容旧版：更新一条消息。
    @deprecated: 请使用 MessageFactory(update=update).edit(placeholder, text)
    """
    _deprecated_warning("update_message", "MessageFactory.edit")

    try:
        result = await placeholder.edit_text(text, parse_mode="markdown")
        # 统一返回值处理
        return result if not isinstance(result, bool) else placeholder
    except Exception as e:
        # 使用统一错误处理
        return await MessageErrorHandler.handle_send_error(
            error=e,
            chat_id=placeholder.chat_id,
            text=text,
            bot=placeholder.get_bot(),
            placeholder=placeholder,
            fallback_parse_mode=None
        )


async def finalize_message(sent_message: Message, text: str, parse: str = "html", summary: Optional[str] = None, comment: Optional[str] = None) -> Optional[Message]:
    """
    兼容旧版：最终确定一条消息。
    @deprecated: 请使用 MessageFactory.edit 方法
    """
    _deprecated_warning("finalize_message", "MessageFactory.edit")

    # 使用统一的格式化方法
    extra_content = MessageFactory.format_extra_content(summary, comment)

    if extra_content:
        text = f'{text}\n\n<blockquote expandable>{extra_content}</blockquote>'

    try:
        result = await sent_message.edit_text(text, parse_mode=parse)
        return result if not isinstance(result, bool) else sent_message
    except Exception as e:
        return await MessageErrorHandler.handle_send_error(
            error=e,
            chat_id=sent_message.chat_id,
            text=text,
            bot=sent_message.get_bot(),
            placeholder=sent_message,
            fallback_parse_mode=None
        )


async def send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_content: str, parse: str = "markdown", photo=None) -> Optional[Message]:
    """
    兼容旧版：发送一条消息。
    @deprecated: 请使用 MessageFactory(context=context).send(text, chat_id)
    """
    _deprecated_warning("send_message", "MessageFactory.send")

    factory = MessageFactory(context=context)
    return await factory.send(text=message_content, chat_id=chat_id, parse_mode=parse, photo=photo)


# --- 重构后的 Agent 会话处理器 ---

async def handle_agent_session(
    update: Update,
    agent_session: AsyncGenerator[Dict[str, Any], None],
    character_name: str = "cyberwaifu"
) -> None:
    """
    处理 Agent 会话的异步生成器，并向用户发送格式化的消息。
    使用 MessageFactory 来管理消息的创建和更新。
    """
    if not update.message:
        return

    factory = MessageFactory(update=update)
    current_placeholder: Optional[Message] = None

    try:
        async for state in agent_session:
            status = state.get("status")
            
            if status == "initializing":
                logger.debug(state.get("message"))
                continue

            elif status == "thinking":
                iteration = state.get("iteration", "?")
                current_placeholder = await update.message.reply_text(f"🔄 第 {iteration} 轮分析中...")

            elif status == "tool_call":
                iteration = state.get("iteration", "?")
                llm_text = state.get("llm_text", "")
                tool_results = state.get("tool_results", [])
                
                if not llm_text and not tool_results:
                    continue

                # 使用列表收集消息部分，最后join
                message_parts = [f"<b>🤖 第 {iteration} 轮分析结果</b>"]
                
                if llm_text:
                    message_parts.append(f"<b>{character_name}:</b> {html.escape(llm_text.strip())}")
                
                if tool_results:
                    tool_results_html = []
                    for res in tool_results:
                        tool_name = res.get('tool_name', '未知工具')
                        tool_result = str(res.get('result', ''))
                        trimmed_result = (tool_result[:2000] + "...") if len(tool_result) > 2000 else tool_result
                        tool_html = f"<b>🔧 {tool_name} 执行结果:</b>\n<blockquote expandable>{html.escape(trimmed_result)}</blockquote>"
                        tool_results_html.append(tool_html)
                    message_parts.extend(tool_results_html)
                
                iteration_message_text = "\n\n".join(message_parts)

                if current_placeholder:
                    await factory.edit(current_placeholder, iteration_message_text)
                else:
                    current_placeholder = await factory.send(iteration_message_text)
                current_placeholder = None # 重置占位符

            elif status == "final_response":
                final_content = state.get("content", "处理完成，但未生成最终回复。")
                final_message = f"<b>🤖 {character_name} 最终回复:</b>\n\n{html.escape(final_content)}"
                if current_placeholder:
                    await factory.edit(current_placeholder, final_message)
                else:
                    await factory.send(final_message)
                current_placeholder = None
                logger.info(f"最终回复: {final_content}")

            elif status == "max_iterations_reached":
                max_iter_msg = f"<b>⚠️ {character_name}提醒</b>\n\n老师，分析轮次已达上限，如需继续分析请重新发起请求哦！"
                if current_placeholder:
                    await factory.edit(current_placeholder, max_iter_msg)
                else:
                    await factory.send(max_iter_msg)
                current_placeholder = None

            elif status == "error":
                error_message = state.get("message", "未知错误")
                error_text = f"处理请求时发生错误: <code>{html.escape(error_message)}</code>"
                if current_placeholder:
                    await factory.edit(current_placeholder, error_text)
                else:
                    await factory.send(error_text)
                current_placeholder = None

    except Exception as e:
        logger.error(f"处理 Agent 会话消息时发生意外错误: {e}", exc_info=True)
        error_message = f"处理请求时发生意外错误: <code>{html.escape(str(e))}</code>"
        if current_placeholder:
            await factory.edit(current_placeholder, error_message)
        else:
            # 尝试回复原始消息
            if update.message:
                await factory.send(error_message)


class MessageDeletionService:
    """消息删除服务，提供统一的自动删除功能"""

    @staticmethod
    async def schedule_auto_delete(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_id: int,
        delay_seconds: int = 120,
        user_message_id: Optional[int] = None
    ) -> None:
        """
        安排消息自动删除

        Args:
            context: Telegram context
            chat_id: 聊天ID
            message_id: 要删除的bot回复消息ID
            delay_seconds: 删除延迟时间（秒）
            user_message_id: 用户指令消息ID（可选，如果提供则也会尝试删除）
        """
        try:
            await asyncio.sleep(delay_seconds)

            # 删除bot回复消息
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"已删除bot回复消息: {message_id}")

            # 如果提供了用户消息ID，尝试删除用户指令消息
            if user_message_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
                    logger.debug(f"已删除用户指令消息: {user_message_id}")
                except Exception as user_delete_error:
                    logger.warning(f"删除用户指令消息失败: {user_delete_error}")

        except Exception as e:
            logger.warning(f"自动删除消息失败: {e}")

    @staticmethod
    async def send_and_schedule_delete(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        parse_mode: str = "HTML",
        delay_seconds: int = 120,
        delete_user_message: bool = True
    ) -> Optional[Message]:
        """
        发送消息并安排自动删除

        Args:
            update: Telegram update
            context: Telegram context
            text: 消息文本
            parse_mode: 解析模式
            delay_seconds: 删除延迟时间（秒）
            delete_user_message: 是否同时删除用户指令消息

        Returns:
            发送的消息对象
        """
        # 发送回复消息
        sent_message = await update.message.reply_text(text, parse_mode=parse_mode)

        if sent_message:
            # 获取用户指令消息ID
            user_message_id = None
            if delete_user_message and update.message:
                user_message_id = update.message.message_id

            # 安排自动删除
            context.application.create_task(
                MessageDeletionService.schedule_auto_delete(
                    context=context,
                    chat_id=update.effective_chat.id,
                    message_id=sent_message.message_id,
                    delay_seconds=delay_seconds,
                    user_message_id=user_message_id
                )
            )

        return sent_message

    @staticmethod
    async def send_photo_and_schedule_delete(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        photo: bytes,
        caption: str = "",
        parse_mode: str = "HTML",
        delay_seconds: int = 120,
        delete_user_message: bool = True
    ) -> Optional[Message]:
        """
        发送图片消息并安排自动删除

        Args:
            update: Telegram update
            context: Telegram context
            photo: 图片bytes数据
            caption: 图片描述
            parse_mode: 解析模式
            delay_seconds: 删除延迟时间（秒）
            delete_user_message: 是否同时删除用户指令消息

        Returns:
            发送的消息对象
        """
        # 发送图片消息
        sent_message = await update.message.reply_photo(
            photo=photo,
            caption=caption,
            parse_mode=parse_mode
        )

        if sent_message:
            # 获取用户指令消息ID
            user_message_id = None
            if delete_user_message and update.message:
                user_message_id = update.message.message_id

            # 安排自动删除
            context.application.create_task(
                MessageDeletionService.schedule_auto_delete(
                    context=context,
                    chat_id=update.effective_chat.id,
                    message_id=sent_message.message_id,
                    delay_seconds=delay_seconds,
                    user_message_id=user_message_id
                )
            )

        return sent_message

class RealTimePositionService:
    """实时仓位更新服务，提供定时更新仓位信息的功"""

    @staticmethod
    async def start_realtime_update(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        group_id: int,
        initial_message: Message
    ) -> None:
        """
        启动实时仓位更新

        Args:
            update: Telegram update对象
            context: Telegram context对象
            user_id: 用户ID
            group_id: 群组ID
            initial_message: 初始消息对象，用于后续编辑
        """
        try:
            # 创建消息工厂
            factory = MessageFactory(update=update, context=context)

            # 总更新时长120秒，每10秒更新一次
            total_duration = 120
            update_interval = 10
            updates_count = total_duration // update_interval

            # 循环更新消息
            for i in range(updates_count):
                try:
                    # 计算剩余时间
                    remaining_seconds = total_duration - (i + 1) * update_interval

                    # 获取最新的仓位信息 - 需要导入group模块来使用_get_enhanced_position_info方法
                    from plugins.trading.commands import PositionCommand
                    position_cmd = PositionCommand()
                    position_data = await position_cmd._get_enhanced_position_info(user_id, group_id)

                    # 构建实时更新消息
                    position_message = RealTimePositionService._build_realtime_message(
                        position_data,
                        remaining_seconds
                    )

                    # 编辑消息
                    await factory.edit(initial_message, position_message)

                    # 如果不是最后一次更新，等待下一次更新
                    if i < updates_count - 1:
                        await asyncio.sleep(update_interval)

                except Exception as update_error:
                    logger.error(f"更新仓位消息失败: {update_error}")
                    continue

            # 120秒后删除消息
            await RealTimePositionService._cleanup_message(
                context, group_id, initial_message.message_id
            )

        except Exception as e:
            logger.error(f"实时更新过程失败: {e}")
            # 发生错误时也清理消息
            try:
                await RealTimePositionService._cleanup_message(
                    context, group_id, initial_message.message_id
                )
            except Exception as cleanup_error:
                logger.error(f"清理消息失败: {cleanup_error}")

    @staticmethod
    def _build_realtime_message(position_data: str, remaining_seconds: int) -> str:
        """
        构建实时更新消息

        Args:
            position_data: 仓位数据字符串
            remaining_seconds: 剩余时间（秒）

        Returns:
            格式化的消息字符串
        """
        # 添加实时更新状态头
        status_header = f"🔄 实时更新中... (剩余: {remaining_seconds}秒)\n\n"

        # 返回组合后的消息
        return status_header + position_data

    @staticmethod
    async def _cleanup_message(
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_id: int
    ) -> None:
        """
        清理（删除）消息

        Args:
            context: Telegram context对象
            chat_id: 聊天ID
            message_id: 要删除的消息ID
        """
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"已删除实时更新消息: {message_id}")
        except Exception as e:
            logger.warning(f"删除实时更新消息失败: {e}")


