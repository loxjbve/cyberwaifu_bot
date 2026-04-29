import datetime
import logging

from telegram import Update
from telegram.ext import ContextTypes

import bot_core.services.utils.tg_parse as public
from bot_core.command_handlers.base import BaseCommand, CommandMeta
from bot_core.services.messages import send_message
from utils.config_utils import get_admin_ids

logger = logging.getLogger(__name__)


class FeedbackCommand(BaseCommand):
    meta = CommandMeta(
        name="feedback",
        command_type="private",
        trigger="feedback",
        menu_text="发送反馈",
        show_in_menu=True,
        menu_weight=0,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        args = context.args if hasattr(context, "args") else []
        if not args:
            await update.message.reply_text(
                "请提供反馈内容。\n\n格式：`/feedback <反馈内容>`",
                parse_mode="Markdown",
            )
            return

        feedback_content = " ".join(args).strip()
        if not feedback_content:
            await update.message.reply_text("反馈内容不能为空。")
            return

        info = public.update_info_get(update)
        if not info:
            await update.message.reply_text("无法获取您的用户信息，反馈失败。")
            return

        user_info = (
            f"用户ID: {info.get('user_id')}\n"
            f"用户名: {info.get('user_name', '未知')}\n"
            f"昵称: {info.get('first_name', '')} {info.get('last_name', '')}"
        )
        admin_message = (
            f"用户反馈\n\n"
            f"用户信息\n{user_info}\n\n"
            f"反馈内容\n{feedback_content}\n\n"
            f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        success_count = 0
        failed_count = 0
        for admin_id in get_admin_ids():
            try:
                await send_message(context, admin_id, admin_message)
                success_count += 1
            except Exception as error:
                failed_count += 1
                logger.warning("Failed to send feedback to admin %s: %s", admin_id, error)

        if success_count > 0:
            await update.message.reply_text(
                f"反馈已发送给管理员。\n\n发送状态：成功 {success_count} 个，失败 {failed_count} 个。"
            )
            logger.info(
                "User %s (%s) sent feedback: %s",
                info.get("user_id"),
                info.get("user_name", "unknown"),
                feedback_content,
            )
        else:
            await update.message.reply_text("反馈发送失败，请稍后重试或联系管理员。")
