from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot_core.command_handlers.base import BaseCommand, CommandMeta


class DirectorCommand(BaseCommand):
    meta = CommandMeta(
        name="director",
        command_type="private",
        trigger="director",
        menu_text="导演模式",
        show_in_menu=True,
        menu_weight=0,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        keyboard = [
            [
                InlineKeyboardButton("推进", callback_data="director_nav_propel_menu"),
                InlineKeyboardButton("控制", callback_data="director_nav_control_menu"),
                InlineKeyboardButton("镜头", callback_data="director_nav_camera_menu"),
            ],
            [
                InlineKeyboardButton("重新生成", callback_data="director_act_regen"),
                InlineKeyboardButton("撤回", callback_data="director_act_undo"),
            ],
        ]
        await update.message.reply_text(
            "请选择导演模式操作：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        await update.message.delete()
