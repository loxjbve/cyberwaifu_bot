from __future__ import annotations

import logging

from bot_core.callback_handlers.callback import (
    CharPageCallback,
    DelCharCallback,
    DelConversationCallback,
    DialogBackCallback,
    DialogDeleteCallback,
    DialogLoadCallback,
    DialogShowCallback,
    GroupCharCallback,
    GroupKeywordAddCallback,
    GroupKeywordCancelCallback,
    GroupKeywordDeleteCallback,
    GroupKeywordSelectCallback,
    GroupKeywordSubmitDeleteCallback,
    SetApiCallback,
    SetCharCallback,
    SetConversationCallback,
    SetGroupApiCallback,
    SetPresetCallback,
    SettingsCallback,
)
from bot_core.command_handlers.group import (
    ApiCommand as GroupApiCommand,
    DisableTopicCommand,
    EnableTopicCommand,
    KeywordCommand,
    RateCommand,
    RemakeCommand,
    SwitchCommand,
)
from bot_core.command_handlers.mode import (
    GroupV1Command,
    GroupV2Command,
    PrivateV1Command,
    PrivateV2Command,
)
from bot_core.command_handlers.private import (
    ApiCommand as PrivateApiCommand,
    CharCommand,
    DeleteCommand,
    DelcharCommand,
    DialogCommand,
    DoneCommand,
    HelpCommand,
    LoadCommand,
    MeCommand,
    NewcharCommand,
    NewCommand,
    NickCommand,
    PresetCommand,
    RegenCommand,
    SaveCommand,
    SettingCommand,
    StartCommand,
    StreamCommand,
    UndoCommand,
)
from bot_core.message_handlers import features
from bot_core.plugin_system import MessageInterceptorMeta, PluginMeta, PluginRegistrar

logger = logging.getLogger(__name__)

CORE_META = PluginMeta(id="core", name="Core Builtins")


async def private_newchar_interceptor(update, context) -> bool:
    if not update.message or not update.message.from_user:
        return False

    user_id = update.message.from_user.id
    newchar_state = context.bot_data.get("newchar_state", {}).get(user_id)
    if not newchar_state:
        return False

    logger.info("Processing new character flow for user %s", user_id)
    await features.private_newchar(update, newchar_state, user_id)
    return True


async def group_keyword_add_interceptor(update, context) -> bool:
    if not context.user_data or not update.message or not update.message.from_user:
        return False

    user_id = update.message.from_user.id
    keyword_action = context.user_data.get("keyword_action")
    is_adding = False
    if isinstance(keyword_action, dict):
        is_adding = keyword_action.get(user_id) == "add"
    elif isinstance(keyword_action, str):
        is_adding = keyword_action == "add"

    if not is_adding:
        return False

    logger.info(
        "Processing keyword add flow for user %s in group %s",
        user_id,
        update.message.chat.id,
    )
    await features.group_keyword_add(update, context)
    return True


def register_builtin_capabilities(manager) -> None:
    registrar = PluginRegistrar(manager, CORE_META)

    for command_cls in [
        StartCommand,
        HelpCommand,
        MeCommand,
        StreamCommand,
        UndoCommand,
        NewCommand,
        SaveCommand,
        RegenCommand,
        LoadCommand,
        DeleteCommand,
        DialogCommand,
        SettingCommand,
        CharCommand,
        DelcharCommand,
        NewcharCommand,
        NickCommand,
        DoneCommand,
        PrivateApiCommand,
        PresetCommand,
        PrivateV1Command,
        PrivateV2Command,
        RemakeCommand,
        SwitchCommand,
        RateCommand,
        KeywordCommand,
        DisableTopicCommand,
        EnableTopicCommand,
        GroupApiCommand,
        GroupV1Command,
        GroupV2Command,
    ]:
        registrar.register_command(command_cls)

    for callback_cls in [
        SetCharCallback,
        DelCharCallback,
        CharPageCallback,
        SetConversationCallback,
        DelConversationCallback,
        DialogShowCallback,
        DialogLoadCallback,
        DialogDeleteCallback,
        DialogBackCallback,
        SettingsCallback,
        GroupCharCallback,
        GroupKeywordCancelCallback,
        GroupKeywordAddCallback,
        GroupKeywordDeleteCallback,
        GroupKeywordSelectCallback,
        GroupKeywordSubmitDeleteCallback,
        SetApiCallback,
        SetGroupApiCallback,
        SetPresetCallback,
    ]:
        registrar.register_callback(callback_cls)

    registrar.register_message_interceptor(
        MessageInterceptorMeta(
            name="private_newchar_flow",
            chat_type="private",
            priority=10,
        ),
        private_newchar_interceptor,
    )
    registrar.register_message_interceptor(
        MessageInterceptorMeta(
            name="group_keyword_add_flow",
            chat_type="group",
            priority=10,
        ),
        group_keyword_add_interceptor,
    )
