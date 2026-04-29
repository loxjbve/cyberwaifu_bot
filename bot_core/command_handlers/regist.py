from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from bot_core.plugin_system import (
    BotCommandData,
    PluginManager,
    get_default_plugin_manager,
    set_default_plugin_manager,
)
from utils.config_utils import get_settings

logger = logging.getLogger(__name__)


class CommandHandlers:
    """
    Compatibility facade for older imports.

    Runtime command discovery now belongs to PluginManager and plugins/*/regist.py.
    """

    @classmethod
    def initialize(cls, manager: PluginManager | None = None) -> None:
        if manager is not None:
            set_default_plugin_manager(manager)
            return

        if get_default_plugin_manager() is not None:
            return

        from bot_core.builtins import register_builtin_capabilities

        settings = get_settings(force_reload=False)
        plugin_manager = PluginManager(
            root_path=Path(settings.project_root) / "plugins",
            settings=settings,
        )
        register_builtin_capabilities(plugin_manager)
        plugin_manager.load()
        set_default_plugin_manager(plugin_manager)

    @classmethod
    def get_command_handler(cls, command: str, chat_type: str) -> Callable | None:
        manager = get_default_plugin_manager()
        if not manager:
            logger.error("Plugin manager is not initialized")
            return None
        return manager.get_command_handler(command, chat_type)

    @staticmethod
    def get_command_definitions(
        module_names: list[str] | None = None,
    ) -> dict[str, list[BotCommandData]]:
        manager = get_default_plugin_manager()
        if not manager:
            logger.error("Plugin manager is not initialized")
            return {"private": [], "group": []}
        return manager.get_command_definitions()
