from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from agent.llm_functions import analyze_image_for_rating
import bot_core.services.utils.usage as fm
from bot_core.data_repository.gateways import UserGateway
from bot_core.services import messages
from utils import file_utils, text_utils
from utils.logging_utils import setup_logging

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

setup_logging()
logger = logging.getLogger(__name__)


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
