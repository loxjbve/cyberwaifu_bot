# Standard library imports
import asyncio
import logging
import os
from typing import TYPE_CHECKING

# Third-party imports
from telegram import Update
from telegram.ext import ContextTypes

# Local application imports
from agent.llm_functions import analyze_image_for_rating
import bot_core.services.utils.usage as fm
from bot_core.services import messages
from bot_core.data_repository.gateways import UserGateway
from utils import db_utils as db
from utils.config_utils import get_config
from utils.logging_utils import setup_logging
from utils import text_utils
from utils import file_utils

# Conditional imports for type checking
if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Load configuration
fuck_api = get_config(
    "fuck_or_not_api", "gemini-2.5"
)  # 从配置文件读取API，默认使用gemini-2


async def private_newchar(update: "Update", newchar_state: dict, user_id: int):
    """处理用于创建新角色的文本输入。

    此函数处理角色创建工作流程中的传入文本消息。

    Args:
        update: Telegram更新对象。
        newchar_state: 用于存储新角色创建过程状态的字典，
                     包括 'char_name' 和 'desc_chunks'。
        user_id: Telegram用户的唯一标识符。
    """
    if not update.message or not update.message.text:
        return

    # 在此状态下忽略命令
    if update.message.text.startswith('/'):
        return
        
    newchar_state.setdefault("desc_chunks", []).append(update.message.text)
    await update.message.reply_text(
        "文本已接收，可继续发送，发送 /done 完成。"
    )


async def _cleanup_keyword_messages(
    context: "ContextTypes.DEFAULT_TYPE",
    chat_id: int,
    user_message_id: int,
    bot_message_id: int,
    original_message_id: int | None,
):
    """删除用户和机器人的消息并移除内联键盘。"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e:
        logger.warning(f"Failed to delete user reply message: {e}")

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=bot_message_id)
    except Exception as e:
        logger.warning(f"Failed to delete prompt message: {e}")

    if original_message_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=original_message_id, reply_markup=None
            )
        except Exception as e:
            logger.warning(f"Failed to remove inline keyboard: {e}")


async def group_keyword_add(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """处理为群组添加新关键词的过程。

    当用户回复特定的机器人消息以添加关键字时，将触发此功能。
    它会验证上下文，解析新关键字，更新数据库并清理交互消息。

    Args:
        update: Telegram更新对象。
        context: 上下文对象，用于访问user_data和机器人实例。
    """
    if (
        not context.user_data
        or not update.message
        or context.user_data.get("keyword_action") != "add"
        or not update.message.reply_to_message
        or not update.message.reply_to_message.from_user
    ):
        return

    if update.message.reply_to_message.from_user.id != context.bot.id:
        await update.message.reply_text("请回复 Bot 的消息来添加关键词。")
        return

    group_id = context.user_data.get("group_id")
    if not group_id:
        logger.warning("group_keyword_add called without group_id in user_data.")
        return

    input_text = (update.message.text or "").strip()
    new_keywords = [kw.strip() for kw in input_text.split() if kw.strip()]

    if not new_keywords:
        await update.message.reply_text("未提供有效的关键词。")
        return

    current_keywords = db.group_keyword_get(group_id)
    updated_keywords = list(set(current_keywords + new_keywords))
    db.group_keyword_set(group_id, updated_keywords)

    await _cleanup_keyword_messages(
        context,
        chat_id=update.message.chat.id,
        user_message_id=update.message.message_id,
        bot_message_id=update.message.reply_to_message.message_id,
        original_message_id=context.user_data.get("original_message_id"),
    )

    await update.message.reply_text(f"已成功添加关键词：{', '.join(new_keywords)}")
    context.user_data.clear()






class ImageAnalyzer:
    """
    封装了与图像分析相关的所有逻辑。
    """

    def __init__(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
        if not update.message or not update.message.from_user:
            raise ValueError("Update或Message对象无效。")
        self.update = update
        self.context = context
        self.user_id = update.message.from_user.id
        user_gateway = UserGateway()
        self.user = user_gateway.get_by_id(self.user_id)
        if not self.user:
            raise ValueError(f"用户 {self.user_id} 不存在。")
        self.chat_id = update.message.chat.id
        self.placeholder_msg = None

    async def analyze(self):
        """执行完整的图像分析工作流程。"""
        if not self.update.message:
            logger.warning("ImageAnalyzer.analyze called with no message.")
            return
        
        if not self.user:
            logger.error(f"ImageAnalyzer.analyze called with no user object for user_id: {self.user_id}")
            return

        if self.user.remain_frequency <= 0 and self.user.temporary_frequency <= 0:
            await messages.send_message(
                self.context, self.user.id, "你的额度已用尽，联系 @xi_cuicui"
            )
            return

        self.placeholder_msg = await self.update.message.reply_text(
            "正在分析，请稍候...", reply_to_message_id=self.update.message.message_id
        )
        
        filepath = None
        try:
            filepath = await file_utils.download_and_convert_image(self.update, self.context, self.user_id)
            
            file_id = self.update.message.photo[-1].file_id if self.update.message.photo else \
                      (self.update.message.sticker.thumbnail.file_id if self.update.message.sticker and self.update.message.sticker.thumbnail else
                       (self.update.message.sticker.file_id if self.update.message.sticker else
                        (self.update.message.animation.thumbnail.file_id if self.update.message.animation and self.update.message.animation.thumbnail else
                         (self.update.message.animation.file_id if self.update.message.animation else None))))

            if not file_id:
                raise ValueError("未能识别到图片、贴纸或GIF。")

            image_data = await text_utils.convert_file_id_to_base64(file_id, self.context)
            if not image_data:
                raise ValueError("无法将file_id转换为Base64")

            formatted_response, llm_messages = await analyze_image_for_rating(
                base64_data=image_data["data"],
                mime_type=image_data["mime_type"],
                hard_mode=False,
                parse_mode="markdown",
            )

            if not formatted_response:
                raise ValueError("从 analyze_image_for_rating 函数收到了空的响应。")

            fm.update_user_usage(self.user, llm_messages, formatted_response, "private_photo")

            txt_filename = f"{os.path.basename(filepath).split('.')[0]}.txt"
            txt_filepath = os.path.join("data/pics", txt_filename)
            with open(txt_filepath, "w", encoding="utf-8") as f:
                f.write(formatted_response)

            await self.placeholder_msg.delete()

            with open(filepath, "rb") as photo_file:
                await messages.send_message(
                    context=self.context,
                    chat_id=self.chat_id,
                    message_content=formatted_response,
                    parse="markdown",
                    photo=photo_file,
                )

        except Exception as e:
            logger.error(f"图像分析失败: {e}", exc_info=True)
            if self.placeholder_msg:
                try:
                    await self.placeholder_msg.delete()
                except Exception:
                    pass
            await self.context.bot.send_message(self.chat_id, f"图片分析失败：{str(e)}")


async def f_or_not(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """
    通过实例化和运行ImageAnalyzer来处理用户图像分析请求。
    """
    try:
        analyzer = ImageAnalyzer(update, context)
        asyncio.create_task(analyzer.analyze())
    except ValueError as e:
        logger.warning(f"无法初始化ImageAnalyzer: {e}")


