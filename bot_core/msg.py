import asyncio
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from utils import LLM_utils as llm
from telegram.error import BadRequest, TelegramError
from bot_core import public
import telegram


# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
# 获取全局 logger
logger = logging.getLogger(__name__)
# 单独设置 httpx 的日志级别为 WARNING，屏蔽 INFO 级别日志
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)
httpx_logger.propagate = True


async def msg_group_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理群组消息。

    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    await public.group_info_update_or_create(update, context)
    info = public.update_info_get(update)
    # 添加消息到群消息记录
    public.group_dialog_add(info)
    # 检查是否需要回复
    needs_reply = public.group_msg_needs_reply(update, context)
    if not needs_reply:
        return
    else:
        conversation = public.Conversation(info)
        conversation.set_trigger(needs_reply)
        conversation.save_to_db('user')
        conversation.check_conv_id('group')
        placeholder_message = await update.message.reply_text("思考中...")
        conversation.set_send_msg_id(placeholder_message.message_id)
    if needs_reply == 'random' or needs_reply == 'keyword':
        asyncio.create_task(_generate_message_once_background(conversation, placeholder_message))
        return
    if needs_reply == 'reply' or needs_reply == '@':
        asyncio.create_task(_generate_group_message_background(conversation, placeholder_message))
        return


async def msg_private_handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理私聊文本消息。
    Args:
        update (Update): Telegram 更新对象。
        context (ContextTypes.DEFAULT_TYPE): 上下文对象。
    """
    # Keep existing logic, decorators are for commands
    try:
        info = public.update_info_get(update)
        conversation = public.Conversation(info)
        # 检查聊天是否存在
        conversation.check_conv_id('private')

        #logger.info(f"处理私聊消息，用户: {info['user_name']}\r\n{info['message_text']}")
        if info['remain'] > 0:
            conversation.save_to_db('user')
            result = await private_chat_handle(conversation, update)
            if result is not None:
                try:
                    await update.message.reply_text(result, parse_mode="markdown")
                except telegram.error.BadRequest as e:
                    logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
                    await update.message.reply_text(result, parse_mode=None)
        else:
            await update.message.reply_text("您的额度已用尽，请联系 @xi_cuicui")

    except Exception as e:
        logger.error(f"处理私聊消息时出错: {str(e)}", exc_info=True)
        await update.message.reply_text(f"处理消息时发生错误{str(e)}，请稍后重试。")


async def private_chat_handle(conversation, update) -> Optional[str]:
    """处理私聊消息的核心逻辑，根据用户配置选择流式或非流式回复。

    Args:
        conversation: 当前会话对象。
        update: Telegram 更新对象。

    Returns:
        Optional[str]: 如果是非流式回复且立即返回结果，则为回复文本，否则为None。
    """
    info = public.update_info_get(update)

    if info['stream'] == 'yes':
        asyncio.create_task(_streaming_response(update, conversation))
        return None
    else:
        placeholder_message = await update.message.reply_text("思考中...")  # 发送占位符
        conversation.set_send_msg_id(placeholder_message.message_id)
        asyncio.create_task(_non_streaming_response(conversation, placeholder_message))
        return None


async def newchar_handle(update, newchar_state, user_id):
    """处理创建新角色时的文件和文本输入。

    Args:
        update: Telegram 更新对象。
        newchar_state (dict): 存储新角色创建状态的字典。
        user_id (int): 用户ID。
    """
    if update.message.document:
        file = update.message.document
        if file.mime_type in ['application/json', 'text/plain'] or file.file_name.endswith(('.json', '.txt')):
            file_obj = await file.get_file()
            import os
            save_dir = os.path.join(os.path.dirname(__file__), 'characters')
            os.makedirs(save_dir, exist_ok=True)
            char_name = newchar_state['char_name']
            target_ext = os.path.splitext(file.file_name)[1] if os.path.splitext(file.file_name)[1] else '.txt'
            save_path = os.path.join(save_dir, f"{char_name}_{user_id}{target_ext}")
            await file_obj.download_to_drive(save_path)
            newchar_state['file_saved'] = save_path
            await update.message.reply_text(f"文件已保存为 {save_path}，如需补充文本可继续发送，发送 /done 完成。")
        else:
            await update.message.reply_text("仅支持json或txt文件。")
        return
    # 文本输入
    if update.message.text:
        newchar_state['desc_chunks'].append(update.message.text)
        await update.message.reply_text("文本已接收，可继续发送文本或文件，发送 /done 完成。")
        return


async def _generate_message_once_background(conversation, placeholder_message):
    """后台任务：为一次性群聊生成回复（例如由关键词或随机触发）。

    Args:
        conversation: 当前会话对象。
        placeholder_message: 占位符消息对象。
    """
    try:
        response = await llm.get_response_no_stream(conversation.prompt, 0, 'once', conversation.api)
        conversation.set_response_text(response)
        conversation.save_to_db('assistant')
        await _finalize_message(placeholder_message, conversation.cleared_response_text)
    except Exception as e:
        logger.error(f"一次性群聊回复后台处理失败: {str(e)}", exc_info=True)
        try:
            await placeholder_message.edit_text(f"处理消息时出错，请稍后再试。\r\n{str(e)}")
        except Exception as edit_e:
            logger.error(f"编辑群聊错误消息失败: {edit_e}")


async def _generate_group_message_background(conversation, placeholder_message):
    """后台任务：为持续性群聊生成回复（例如回复机器人或@机器人）。

    Args:
        conversation: 当前会话对象。
        placeholder_message: 占位符消息对象。
    """
    try:
        response = await llm.get_response_no_stream(conversation.prompt, conversation.id, 'group', conversation.api)
        conversation.set_response_text(response)
        conversation.save_to_db('assistant')
        await _finalize_message(placeholder_message, conversation.cleared_response_text)  # cleared_response 确保是字符串
    except Exception as e:
        logger.error(f"群聊非流式回复后台处理失败: {str(e)}", exc_info=True)
        try:
            await placeholder_message.edit_text("处理消息时出错，请稍后再试。")
        except Exception as edit_e:
            logger.error(f"编辑群聊错误消息失败: {edit_e}")


async def _streaming_response(update, conversation) -> None:
    """处理流式传输回复逻辑，生成并逐步更新响应内容。

    Args:
        update: Telegram 更新对象。
        conversation: 当前会话对象。
    """

    #logger.info(f"使用流式传输生成私聊回复, user_id: {conversation.info['user_id']}")
    sent_message = None  # 初始化 sent_message
    try:
        # 初始化响应消息
        sent_message = await update.message.reply_text("...", parse_mode="markdown")
        msg_id = sent_message.message_id
        conversation.set_send_msg_id(msg_id)
        # 获取流式响应并处理
        full_response = await _process_streaming_response_background(conversation, sent_message)
        conversation.set_response_text(full_response)
        await _finalize_message(sent_message, conversation.cleared_response_text)
        conversation.save_to_db('assistant')
    except Exception as e:
        logger.error(f"处理流式响应时出错: {e}", exc_info=True)
        if sent_message:
            try:
                await sent_message.edit_text("处理消息时出错，请稍后再试。")
            except Exception as edit_e:
                logger.error(f"编辑流式错误消息失败: {edit_e}")


async def _non_streaming_response(conversation, placeholder_message: telegram.Message) -> None:
    """
    处理非流式传输回复逻辑 (后台任务)。

    Args:
        conversation:conv对象。
        placeholder_message (telegram.Message): 占位符消息对象。
    """

    try:

        full_response = await llm.get_response_no_stream(conversation.prompt, conversation.id, 'private',conversation.api)
        conversation.set_response_text(full_response)
        await _finalize_message(placeholder_message, conversation.cleared_response_text)
        conversation.save_to_db('assistant')

    except Exception as e:
        logger.error(f"{conversation.info['user_name']}后台处理非流式回复失败, 错误: {e}", exc_info=True)
        try:
            await placeholder_message.edit_text("处理消息时出错，请稍后再试。")
        except Exception as edit_e:
            logger.error(f"编辑错误消息失败: {edit_e}")


async def _process_streaming_response_background(conversation, sent_message) -> str:
    """
    处理流式传输响应，定期更新消息内容。
    """
    response_chunks = []
    last_update_time = asyncio.get_event_loop().time()
    last_updated_content = "..."
    # Correctly iterate over the async generator
    async for chunk in llm.get_response_stream(conversation.prompt, conversation.id, 'private', conversation.api):
        response_chunks.append(chunk)
        full_response = "".join(response_chunks)
        current_time = asyncio.get_event_loop().time()
        # 每 8 秒或内容显著变化时更新消息
        if current_time - last_update_time >= 8 and full_response != last_updated_content:
            await _update_message(sent_message, full_response, last_updated_content)
            last_updated_content = full_response
            last_update_time = current_time
        # 短暂让出事件循环控制权，避免长时间占用
        await asyncio.sleep(0.01)
    return "".join(response_chunks)


async def _update_message(sent_message, full_response: str, last_updated_content: str) -> None:
    """
    更新消息内容，避免频繁更新导致 Telegram API 过载。
    Args:
        sent_message: 已发送的消息对象。
        full_response (str): 当前完整的响应内容。
        last_updated_content (str): 上次更新的内容。
    """
    try:
        # Telegram 单条消息最大长度限制4096字符，保险起见用4000
        MAX_LEN = 4000
        if len(full_response) > MAX_LEN:
            full_response = full_response[-MAX_LEN:]
        await sent_message.edit_text(full_response, parse_mode="markdown")
    except BadRequest as e:
        logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
        try:
            await sent_message.edit_text(full_response, parse_mode=None)
        except Exception as e2:
            logger.error(f"再次尝试发送消息失败: {e2}")
    except TelegramError as e:
        if "Message is not modified" in str(e):
            logger.debug(f"消息内容未变化，跳过更新: {str(e)}")
        else:
            logger.error(f"更新消息时出错: {str(e)}")


async def _finalize_message(sent_message, cleared_response: str) -> None:
    """
    最终更新消息内容，确保显示最终的处理后的响应。
    Args:
        sent_message: 已发送的消息对象。
        cleared_response (str): 处理后的最终响应内容。
    """
    try:
        # Telegram 单条消息最大长度限制4096字符，保险起见用4000
        MAX_LEN = 4000
        if len(cleared_response) <= MAX_LEN:
            await sent_message.edit_text(cleared_response, parse_mode="markdown")
        else:
            # 超长时分两段发送，先发前半段，再发后半段
            await sent_message.edit_text(cleared_response[:MAX_LEN], parse_mode="markdown")
            await sent_message.reply_text(cleared_response[MAX_LEN:], parse_mode="markdown")
    except BadRequest as e:
        logger.warning(f"Markdown 解析错误: {str(e)}, 禁用 Markdown 重试")
        try:
            if len(cleared_response) <= MAX_LEN:
                await sent_message.edit_text(cleared_response, parse_mode=None)
            else:
                await sent_message.edit_text(cleared_response[:MAX_LEN], parse_mode=None)
                await sent_message.reply_text(cleared_response[MAX_LEN:], parse_mode=None)
        except Exception as e2:
            logger.error(f"再次尝试发送消息失败: {e2}")
    except TelegramError as e:
        if "Message is not modified" in str(e):
            logger.debug(f"最终更新时消息内容未变化，跳过更新: {str(e)}")
        else:
            logger.error(f"最终更新消息时出错: {str(e)}")
