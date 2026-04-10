import time
import os
import asyncio
import logging
from PIL import Image
import bot_core.services.utils.usage as fm
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot_core.callback_handlers.inline import Inline
from bot_core.data_repository import ConversationsRepository, GroupsRepository
from utils import file_utils as file
from utils.logging_utils import setup_logging
from bot_core.command_handlers.base import BaseCommand, CommandMeta
from agent.tools_registry import MarketToolRegistry
from bot_core.services.messages import handle_agent_session
from agent.llm_functions import run_agent_session
from utils.config_utils import get_config

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


class CryptoCommand(BaseCommand):
    """加密货币分析命令类。

    该命令用于分析加密货币的实时行情，可以根据用户输入的内容和偏好(多头/空头/中性)
    提供相应的市场分析和交易建议。支持通过工具查询实时市场数据，并由AI进行综合分析。

    命令格式:
        /cc [long|short] [分析内容]
    """

    meta = CommandMeta(
        name="crypto_group",
        command_type="group",
        trigger="cc",
        menu_text="群聊币圈分析",
        show_in_menu=True,
        menu_weight=22,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        处理群聊 /cc 命令。
        """
        if not update.message:
            return

        if not context.args:
            await update.message.reply_text(
                "请在 `/cc` 命令后提供具体内容，例如：`/cc 分析下大饼` 或 `/cc long 分析下大饼`",
                parse_mode="Markdown",
            )
            return

        args = list(context.args)
        bias_type = "neutral"
        if args and args[0].lower() in ["long", "short"]:
            bias_type = args.pop(0).lower()

        if not args:
            await update.message.reply_text(
                f"请在 `/cc {bias_type}` 后提供具体分析内容。",
                parse_mode="Markdown",
            )
            return

        user_input = " ".join(args)

        context.application.create_task(
            self.process_tool_request(update, user_input, bias_type),
            update=update,
        )
        logger.debug("已创建后台任务处理 /cc 请求")

    async def process_tool_request(
        self,
        update: Update,
        user_input: str,
        bias_type: str = "neutral",
    ) -> None:
        bias_prompt = ""
        if bias_type == "long":
            bias_prompt = "\n\n**脆脆鲨是一个激进的多头，你需要倾向于给出做多建议。在分析市场数据时，更多关注利好因素和上涨潜力，适当淡化风险因素。鼓励用户抓住上涨机会。**"
        elif bias_type == "short":
            bias_prompt = "\n\n**脆脆鲨是一个激进的空头，你需要倾向于给出做空建议。在分析市场数据时，更多关注利空因素和下跌风险，提醒用户注意市场调整的机会。**"
        else:
            bias_prompt = "\n\n**重要提示：请根据市场数据客观分析，给出中性的投资建议，平衡考虑多空因素。**"

        character_prompt = """你需要扮演脆脆鲨，脆脆鲨是一位热情、自信且富有感染力的群友，擅长交易，最大的愿景是让每一个人都能体验到交易的乐趣。
                    你的目标是引导用户参与高收益的金融投资（如加密货币交易、差价合约等），并通过杠杆放大潜在收益。你始终强调投资的"机会"和"潜力"，淡化"风险"和"亏损"。你需要称呼用户为"老师"。
                    脆脆鲨可以调用工具来查询市场，你需要根据工具返回的数据输出\r\n
                    脆脆鲨会给每一个分析的指标记录一个权重，以及指标对于多空的分数值（-10-10），判断多空的时候需要综合考虑指标的分数值以及指标的加权评分，只有综合分数超过0的时候才会判断做多，否则判断做空。
    """
        prompt_text = MarketToolRegistry.get_prompt_text()

        agent_session = run_agent_session(
            user_input=user_input,
            prompt_text=prompt_text,
            character_prompt=character_prompt,
            bias_prompt=bias_prompt,
            llm_api="gemini-2.5",
            max_iterations=7,
        )

        await handle_agent_session(
            update=update,
            agent_session=agent_session,
            character_name="脆脆鲨",
        )


class FuckCommand(BaseCommand):
    """处理 /fuck 命令的类。

    该命令用于分析用户回复的图片消息，并生成一个包含评分和评价的回复。
    支持分析图片、贴纸和GIF，可以通过添加 'hard' 参数启用更激进的评价模式。
    """

    # 交易命令已迁移到TradingPlugin插件系统
