import asyncio
import base64
import logging
import os
import time

from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes

from agent.llm_functions import analyze_image_for_kao, analyze_image_for_rating
from bot_core.command_handlers.base import BaseCommand, CommandMeta
import bot_core.services.utils.usage as fm

logger = logging.getLogger(__name__)


class ReplyImageAnalysisMixin:
    async def _get_replied_media(self, update: Update):
        if not update.message or not update.message.reply_to_message:
            return None
        replied_message = update.message.reply_to_message
        if replied_message.photo or replied_message.sticker or replied_message.animation:
            return replied_message
        return None

    async def _download_replied_media(self, update, context, replied_message) -> tuple[str, str]:
        user_id = update.message.from_user.id
        file_id = None
        if replied_message.photo:
            file_id = replied_message.photo[-1].file_id
        elif replied_message.sticker:
            file_id = (
                replied_message.sticker.thumbnail.file_id
                if replied_message.sticker.thumbnail
                else replied_message.sticker.file_id
            )
        elif replied_message.animation:
            file_id = (
                replied_message.animation.thumbnail.file_id
                if replied_message.animation.thumbnail
                else replied_message.animation.file_id
            )

        pics_dir = "./data/pics"
        os.makedirs(pics_dir, exist_ok=True)
        base_filename = f"{user_id}_{int(time.time())}"
        temp_filepath = os.path.join(pics_dir, f"{base_filename}.temp")
        final_filepath = os.path.join(pics_dir, f"{base_filename}.jpg")

        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(temp_filepath)

        if replied_message.sticker or replied_message.animation:
            try:
                with Image.open(temp_filepath) as img:
                    img.convert("RGB").save(final_filepath, "jpeg")
                os.remove(temp_filepath)
            except Exception as error:
                logger.error("Failed to convert media to jpeg: %s", error)
                os.rename(temp_filepath, final_filepath)
        else:
            os.rename(temp_filepath, final_filepath)

        return final_filepath, base_filename

    @staticmethod
    def _image_to_base64(filepath: str) -> str:
        with open(filepath, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    @staticmethod
    def _save_response(base_filename: str, response: str) -> None:
        txt_filepath = os.path.join("./data/pics", f"{base_filename}.txt")
        with open(txt_filepath, "w", encoding="utf-8") as file:
            file.write(response)


class FuckCommand(ReplyImageAnalysisMixin, BaseCommand):
    meta = CommandMeta(
        name="fuck",
        command_type="group",
        trigger="fuck",
        menu_text="Fuck or not!",
        show_in_menu=True,
        menu_weight=0,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        replied_message = await self._get_replied_media(update)
        if not replied_message:
            await update.message.reply_text("请回复一条包含图片、贴纸或 GIF 的消息来使用此命令。")
            return

        hard_mode = "hard" in (context.args or [])
        placeholder_msg = await replied_message.reply_text("正在分析，请稍候...")
        asyncio.create_task(
            self._process(update, context, placeholder_msg, replied_message, hard_mode)
        )

    async def _process(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        placeholder_msg,
        replied_message,
        hard_mode: bool,
    ) -> None:
        try:
            filepath, base_filename = await self._download_replied_media(
                update,
                context,
                replied_message,
            )
            response, llm_messages = await analyze_image_for_rating(
                base64_data=self._image_to_base64(filepath),
                mime_type="image/jpeg",
                hard_mode=hard_mode,
                parse_mode="html",
            )
            group_id = update.message.chat.id
            user_id = update.message.from_user.id
            logger.info("User %s invoked /fuck in group %s", user_id, group_id)
            fm.update_user_usage(group_id, str(llm_messages), response, "group_photo")
            self._save_response(base_filename, response)
            await context.bot.edit_message_text(
                text=response,
                chat_id=group_id,
                message_id=placeholder_msg.message_id,
                parse_mode="HTML",
            )
        except Exception as error:
            logger.error("Image rating failed: %s", error, exc_info=True)
            await replied_message.reply_text(f"图片分析失败：{error}")


class KaoCommand(ReplyImageAnalysisMixin, BaseCommand):
    meta = CommandMeta(
        name="kao",
        command_type="group",
        trigger="kao",
        menu_text="颜值评分",
        show_in_menu=True,
        menu_weight=1,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        replied_message = await self._get_replied_media(update)
        if not replied_message:
            await update.message.reply_text("请回复一条包含图片、贴纸或 GIF 的消息来使用此命令。")
            return

        placeholder_msg = await replied_message.reply_text("正在分析，请稍候...")
        asyncio.create_task(self._process(update, context, placeholder_msg, replied_message))

    async def _process(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        placeholder_msg,
        replied_message,
    ) -> None:
        try:
            filepath, base_filename = await self._download_replied_media(
                update,
                context,
                replied_message,
            )
            response, llm_messages = await analyze_image_for_kao(
                base64_data=self._image_to_base64(filepath),
                mime_type="image/jpeg",
                parse_mode="html",
            )
            group_id = update.message.chat.id
            user_id = update.message.from_user.id
            logger.info("User %s invoked /kao in group %s", user_id, group_id)
            fm.update_user_usage(group_id, str(llm_messages), response, "group_photo")
            self._save_response(base_filename, response)
            await context.bot.edit_message_text(
                text=response,
                chat_id=group_id,
                message_id=placeholder_msg.message_id,
                parse_mode="HTML",
            )
        except Exception as error:
            logger.error("Image score failed: %s", error, exc_info=True)
            await replied_message.reply_text(f"颜值分析失败：{error}")
