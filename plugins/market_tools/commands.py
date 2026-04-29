import logging

from telegram import Update
from telegram.ext import ContextTypes

from agent.llm_functions import run_agent_session
from plugins.market_tools.tools import MarketToolRegistry
from bot_core.command_handlers.base import BaseCommand, CommandMeta
from bot_core.services.messages import handle_agent_session

logger = logging.getLogger(__name__)


class CryptoAnalysisMixin:
    command_label = "c"

    async def _handle_crypto(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        if not context.args:
            await update.message.reply_text(
                f"请在 `/{self.command_label}` 后提供分析内容，例如："
                f"`/{self.command_label} 分析一下 BTC` 或 `/{self.command_label} long 分析一下 BTC`",
                parse_mode="Markdown",
            )
            return

        args = list(context.args)
        bias_type = "neutral"
        if args and args[0].lower() in ["long", "short"]:
            bias_type = args.pop(0).lower()

        if not args:
            await update.message.reply_text(
                f"请在 `/{self.command_label} {bias_type}` 后提供分析内容。",
                parse_mode="Markdown",
            )
            return

        user_input = " ".join(args)
        context.application.create_task(
            self.process_tool_request(update, user_input, bias_type),
            update=update,
        )
        logger.debug("Created background crypto analysis task for /%s", self.command_label)

    async def process_tool_request(
        self,
        update: Update,
        user_input: str,
        bias_type: str = "neutral",
    ) -> None:
        if bias_type == "long":
            bias_prompt = (
                "\n\n你偏向多头视角：重点关注利好因素和上涨潜力，"
                "但仍需提示关键风险。"
            )
        elif bias_type == "short":
            bias_prompt = (
                "\n\n你偏向空头视角：重点关注利空因素和下跌风险，"
                "但仍需提示反弹风险。"
            )
        else:
            bias_prompt = "\n\n请基于市场数据客观分析，平衡多空因素。"

        character_prompt = (
            "你需要扮演脆脆鲨，一位热情、自信且熟悉加密货币交易的群友。"
            "你会调用工具查询市场数据，并根据工具返回的数据输出分析。"
            "称呼用户为老师。判断多空时需要综合指标权重和评分。"
        )
        agent_session = run_agent_session(
            user_input=user_input,
            prompt_text=MarketToolRegistry.get_prompt_text(),
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


class PrivateCryptoCommand(CryptoAnalysisMixin, BaseCommand):
    command_label = "c"
    meta = CommandMeta(
        name="crypto",
        command_type="private",
        trigger="c",
        menu_text="分析加密货币实时行情",
        show_in_menu=True,
        menu_weight=99,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_crypto(update, context)


class GroupCryptoCommand(CryptoAnalysisMixin, BaseCommand):
    command_label = "cc"
    meta = CommandMeta(
        name="crypto_group",
        command_type="group",
        trigger="cc",
        menu_text="群聊币圈分析",
        show_in_menu=True,
        menu_weight=22,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_crypto(update, context)
