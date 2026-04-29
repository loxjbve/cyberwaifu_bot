from __future__ import annotations

from typing import Iterable

from bot_core.plugin_system import AgentToolSpec, PluginRegistrar


def register_commands(registrar: PluginRegistrar, command_classes: Iterable[type]) -> None:
    for command_cls in command_classes:
        registrar.register_command(command_cls)


def register_callbacks(registrar: PluginRegistrar, callback_classes: Iterable[type]) -> None:
    for callback_cls in callback_classes:
        registrar.register_callback(callback_cls)


def register_tool_registry(registrar: PluginRegistrar, registry) -> None:
    for tool_name, tool_info in registry.TOOLS.items():
        executor = registry.get_tool(tool_name)
        if not executor:
            continue
        registrar.register_agent_tool(
            AgentToolSpec(
                name=tool_name,
                description=tool_info["description"],
                tool_type=tool_info["type"],
                parameters=tool_info.get("parameters", {}),
                output_format=tool_info.get("output_format", ""),
                example=tool_info.get("example", {}),
                return_value=tool_info.get("return_value", ""),
                executor=executor,
            )
        )
