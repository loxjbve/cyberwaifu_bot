import datetime
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.command_handlers.base import BaseCommand, CommandMeta
from bot_core.data_repository import SignRepository

logger = logging.getLogger(__name__)


class SignCommand(BaseCommand):
    meta = CommandMeta(
        name="sign",
        command_type="private",
        trigger="sign",
        menu_text="签到获取额度",
        show_in_menu=True,
        menu_weight=1,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.from_user:
            return

        user_id = update.message.from_user.id
        sign_info_result = SignRepository.user_sign_info_get(user_id)
        sign_info = (
            sign_info_result["data"]
            if sign_info_result["success"]
            else {"last_sign": 0, "frequency": 0}
        )

        if sign_info.get("last_sign") == 0:
            SignRepository.user_sign_info_create(user_id)
            sign_info_result = SignRepository.user_sign_info_get(user_id)
            sign_info = sign_info_result["data"] if sign_info_result["success"] else {"frequency": 0}
            await update.message.reply_text(
                f"签到成功！临时额度+50。\n你的临时额度为 {sign_info.get('frequency')} 条（上限100）。"
            )
            return

        current_time = datetime.datetime.now()
        last_sign_str = sign_info.get("last_sign")
        if not last_sign_str:
            await update.message.reply_text("签到时间数据异常，请联系管理员。")
            return

        try:
            last_sign_time = datetime.datetime.strptime(
                str(last_sign_str),
                "%Y-%m-%d %H:%M:%S.%f",
            )
        except ValueError:
            try:
                last_sign_time = datetime.datetime.strptime(
                    str(last_sign_str),
                    "%Y-%m-%d %H:%M:%S",
                )
            except ValueError as error:
                logger.error("Unable to parse sign time %s: %s", last_sign_str, error)
                await update.message.reply_text("签到时间数据异常，请联系管理员。")
                return

        total_seconds = (current_time - last_sign_time).total_seconds()
        if total_seconds < 28800:
            remaining_hours = (28800 - total_seconds) // 3600
            await update.message.reply_text(
                f"您 8 小时内已经签到过，请在 {int(remaining_hours)} 小时后再试。"
            )
            return

        SignRepository.user_sign(user_id)
        sign_info_result = SignRepository.user_sign_info_get(user_id)
        sign_info = sign_info_result["data"] if sign_info_result["success"] else {"frequency": 0}
        await update.message.reply_text(
            f"签到成功！临时额度+50。\n你的临时额度为 {sign_info.get('frequency')} 条（上限100）。"
        )
