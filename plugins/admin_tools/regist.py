from plugins.admin_tools.commands import (
    AddFrequencyCommand,
    CheckpointCommand,
    DatabaseCommand,
    ExportCommand,
    ForwardCommand,
    MessageCommand,
    RebootCommand,
    RestartCommand,
    SetTierCommand,
)
from plugins.admin_tools.tools import DatabaseSuperToolRegistry
from bot_core.plugin_system import PluginMeta
from plugins._helpers import register_commands, register_tool_registry

plugin = PluginMeta(id="admin_tools", name="Admin Tools")


def register(registrar):
    register_commands(
        registrar,
        [
            AddFrequencyCommand,
            SetTierCommand,
            DatabaseCommand,
            ExportCommand,
            ForwardCommand,
            MessageCommand,
            CheckpointCommand,
            RebootCommand,
            RestartCommand,
        ],
    )
    register_tool_registry(registrar, DatabaseSuperToolRegistry)
    registrar.register_prompt_section("database_tools", DatabaseSuperToolRegistry.get_prompt_text)
