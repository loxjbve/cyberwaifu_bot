from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.command_handlers.base import BaseCommand, CommandMeta
from bot_core.data_repository.gateways import GroupGateway, UserGateway
from bot_core.services.soul_agent import SoulSkillRepository


class _ModeCommandMixin:
    target_mode: str

    async def _switch_private_mode(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not update.message or not update.message.from_user:
            return

        user_gateway = UserGateway()
        user = user_gateway.get_or_create(
            user_id=update.message.from_user.id,
            first_name=update.message.from_user.first_name or "",
            last_name=update.message.from_user.last_name or "",
            user_name=update.message.from_user.username or "",
        )

        if self.target_mode == "v2" and not SoulSkillRepository().has_skill(user.character):
            await update.message.reply_text(
                f"无法切换到 V2：缺少 data/souls/{user.character}/SKILL.md。"
            )
            return

        user_gateway.update_chat_mode(user.id, self.target_mode)
        await update.message.reply_text(f"已切换到 {self.target_mode.upper()} 对话模式。")

    async def _switch_group_mode(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not update.message or not update.message.chat:
            return

        group_gateway = GroupGateway()
        config = group_gateway.get_runtime_config(update.message.chat.id)
        character = config.char

        if self.target_mode == "v2" and (not character or not SoulSkillRepository().has_skill(character)):
            await update.message.reply_text(
                f"无法切换到 V2：缺少 data/souls/{character or '<未配置角色>'}/SKILL.md。"
            )
            return

        group_gateway.update_chat_mode(update.message.chat.id, self.target_mode)
        await update.message.reply_text(f"本群已切换到 {self.target_mode.upper()} 对话模式。")


class PrivateV1Command(_ModeCommandMixin, BaseCommand):
    target_mode = "v1"
    meta = CommandMeta(
        name="v1",
        command_type="private",
        trigger="v1",
        menu_text="切换到 V1 对话模式",
        show_in_menu=True,
        menu_weight=20,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._switch_private_mode(update, context)


class PrivateV2Command(_ModeCommandMixin, BaseCommand):
    target_mode = "v2"
    meta = CommandMeta(
        name="v2",
        command_type="private",
        trigger="v2",
        menu_text="切换到 V2 Soul Agent 模式",
        show_in_menu=True,
        menu_weight=21,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._switch_private_mode(update, context)


class GroupV1Command(_ModeCommandMixin, BaseCommand):
    target_mode = "v1"
    meta = CommandMeta(
        name="v1",
        command_type="group",
        group_admin_required=True,
        trigger="v1",
        menu_text="切换到 V1 对话模式",
        show_in_menu=True,
        menu_weight=20,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._switch_group_mode(update, context)


class GroupV2Command(_ModeCommandMixin, BaseCommand):
    target_mode = "v2"
    meta = CommandMeta(
        name="v2",
        command_type="group",
        group_admin_required=True,
        trigger="v2",
        menu_text="切换到 V2 Soul Agent 模式",
        show_in_menu=True,
        menu_weight=21,
    )

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._switch_group_mode(update, context)
