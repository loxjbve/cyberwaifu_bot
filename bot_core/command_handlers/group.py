import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot_core.callback_handlers.inline import Inline
from bot_core.command_handlers.base import BaseCommand, CommandMeta
from bot_core.data_repository import ConversationsRepository, GroupsRepository
from utils import file_utils as file
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
class RemakeCommand(BaseCommand):
    meta = CommandMeta(
        name="remake",
        command_type="group",
        trigger="remake",
        menu_text="重开对话 (群组)",
        show_in_menu=True,
        menu_weight=17,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        result = ConversationsRepository.conversation_group_delete(
            update.message.chat.id, update.message.from_user.id
        )
        if result["success"]:
            logger.info(f"处理 /remake 命令，用户ID: {update.effective_user.id}")
            await update.message.reply_text("您已重开对话！")


class SwitchCommand(BaseCommand):
    meta = CommandMeta(
        name="switch",
        command_type="group",
        trigger="switch",
        menu_text="切换角色 (群组)",
        show_in_menu=True,
        menu_weight=18,
        group_admin_required=True,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        markup = Inline.print_char_list(
            "load", "group", update.message.chat.id)
        if markup == "没有可操作的角色。":
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个角色：", reply_markup=markup)


class RateCommand(BaseCommand):
    meta = CommandMeta(
        name="rate",
        command_type="group",
        trigger="rate",
        menu_text="设置回复频率 (群组)",
        show_in_menu=True,
        menu_weight=19,
        group_admin_required=True,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args if hasattr(context, "args") else []
        if len(args) < 1:
            await update.message.reply_text("请输入一个0-1的小数")
            return
        rate_value = float(args[0])
        if not 0 <= rate_value <= 1:
            await update.message.reply_text("请输入一个0-1的小数")
            return
        result = GroupsRepository.group_info_update(update.message.chat.id, "rate", rate_value)
        if result["success"]:
            await update.message.reply_text(f"已设置触发频率: {rate_value}")


class KeywordCommand(BaseCommand):
    meta = CommandMeta(
        name="keyword",
        command_type="group",
        trigger="kw",
        menu_text="设置关键词",
        show_in_menu=True,
        menu_weight=0,
        group_admin_required=True,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keywords_result = GroupsRepository.group_keyword_get(update.message.chat.id)
        keywords = keywords_result["data"] if keywords_result["success"] else []
        if not keywords:
            keywords_text = "当前群组没有设置关键词。"
        else:
            keywords_text = "当前群组的关键词列表：\r\n" + ", ".join(
                [f"`{escape_markdown(kw, version=1)}`" for kw in keywords]
            )
        keyboard = [
            [
                InlineKeyboardButton(
                    "添加关键词", callback_data=f"group_kw_add_{update.message.chat.id}"
                ),
                InlineKeyboardButton(
                    "删除关键词", callback_data=f"group_kw_del_{update.message.chat.id}"
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            keywords_text, reply_markup=reply_markup, parse_mode="Markdown"
        )


class DisableTopicCommand(BaseCommand):
    meta = CommandMeta(
        name="disable_topic",
        command_type="group",
        trigger="d",
        menu_text="禁用当前话题",
        show_in_menu=True,
        menu_weight=20,
        group_admin_required=True,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理禁用话题命令"""
        try:
            message = update.message
            group_id = message.chat.id

            if (
                not hasattr(message, "message_thread_id")
                or not message.message_thread_id
            ):
                await message.reply_text("请在话题中执行此命令以禁用当前话题。")
                return

            topic_id = str(message.message_thread_id)

            disabled_topics_result = GroupsRepository.group_disabled_topics_get(group_id)
            disabled_topics = disabled_topics_result["data"] if disabled_topics_result["success"] else []
            if topic_id not in disabled_topics:
                disabled_topics.append(topic_id)
                result = GroupsRepository.group_disabled_topics_set(group_id, disabled_topics)
                if result["success"]:
                    await message.reply_text(
                        f"已禁用当前话题 (ID: `{topic_id}`)。Bot将不会在此话题中发言。",
                        parse_mode="Markdown",
                    )
                else:
                    await message.reply_text("禁用话题失败，请稍后重试。")
            else:
                await message.reply_text(
                    f"当前话题 (ID: `{topic_id}`) 已被禁用。", parse_mode="Markdown"
                )

        except Exception as e:
            logger.error("处理禁用话题命令失败: %s", str(e))
            await update.message.reply_text("处理禁用话题命令时发生错误，请稍后重试。")


class EnableTopicCommand(BaseCommand):
    meta = CommandMeta(
        name="enable_topic",
        command_type="group",
        trigger="e",
        menu_text="启用当前话题",
        show_in_menu=True,
        menu_weight=20,
        group_admin_required=True,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理启用话题命令"""
        try:
            message = update.message
            group_id = message.chat.id

            if (
                not hasattr(message, "message_thread_id")
                or not message.message_thread_id
            ):
                await message.reply_text("请在话题中执行此命令以启用当前话题。")
                return

            topic_id = str(message.message_thread_id)

            disabled_topics_result = GroupsRepository.group_disabled_topics_get(group_id)
            disabled_topics = disabled_topics_result["data"] if disabled_topics_result["success"] else []
            if topic_id in disabled_topics:
                disabled_topics.remove(topic_id)
                result = GroupsRepository.group_disabled_topics_set(group_id, disabled_topics)
                if result["success"]:
                    await message.reply_text(
                        f"已启用当前话题 (ID: `{topic_id}`)。Bot将在此话题中发言。",
                        parse_mode="Markdown",
                    )
                else:
                    await message.reply_text("启用话题失败，请稍后重试。")
            else:
                await message.reply_text(
                    f"当前话题 (ID: `{topic_id}`) 未被禁用。", parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"处理启用话题命令失败: {str(e)}")
            await update.message.reply_text("处理启用话题命令时发生错误，请稍后重试。")


class ApiCommand(BaseCommand):
    meta = CommandMeta(
        name="api",
        command_type="group",
        trigger="api",
        menu_text="选择API (群组)",
        show_in_menu=True,
        menu_weight=21,
        group_admin_required=True,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle the /api command to show available APIs for group (only group=0 APIs).
        Args:
            update: The Telegram Update object containing the user input.
            context: The Telegram ContextTypes object for bot interaction.
        """
        # 获取群组信息
        group_id = update.message.chat.id

        # 创建群组专用的 API 列表（只显示 group=0 的 API）
        markup = self._get_group_api_list(group_id)

        if isinstance(markup, str):
            await update.message.reply_text(markup)
        else:
            await update.message.reply_text("请选择一个API：", reply_markup=markup)

        # 删除命令消息
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"删除命令消息失败: {e}")

    def _get_group_api_list(self, group_id):
        """
        获取群组可用的 API 列表（只返回 group=0 的 API）

        Args:
            group_id: 群组ID
        """
        try:
            api_list = file.load_config()["api"]
            if not api_list:
                return "没有可用的API。"

            # 过滤API列表，只保留group=0的API
            filtered_api_list = [
                api for api in api_list if api.get("group", 0) == 0]

            if not filtered_api_list:
                return "没有适用于群组的API。"

            keyboard = [
                [
                    InlineKeyboardButton(
                        api["name"],
                        callback_data=f"set_group_api_{api['name']}_{group_id}",
                    )
                ]
                for api in filtered_api_list
            ]
            return InlineKeyboardMarkup(keyboard)
        except Exception as e:
            logger.error("获取群组API列表失败: %s", str(e))
            return "获取API列表失败，请稍后重试。"

