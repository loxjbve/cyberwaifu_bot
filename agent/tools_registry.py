from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from bot_core.plugin_system import PluginManager
from plugins.admin_tools.tools import DatabaseSuperToolRegistry
from plugins.market_tools.tools import MarketToolRegistry
from utils.logging_utils import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


ALL_TOOLS: Dict[str, Callable] = {}

for tool_name in MarketToolRegistry.TOOLS:
    tool_func = MarketToolRegistry.get_tool(tool_name)
    if tool_func:
        if tool_name in ALL_TOOLS:
            logger.warning(
                "Tool name conflict: %s already exists and will be overwritten by MarketToolRegistry",
                tool_name,
            )
        ALL_TOOLS[tool_name] = tool_func

for tool_name in DatabaseSuperToolRegistry.TOOLS:
    tool_func = DatabaseSuperToolRegistry.get_tool(tool_name)
    if tool_func:
        if tool_name in ALL_TOOLS:
            logger.warning(
                "Tool name conflict: %s already exists and will be overwritten by DatabaseSuperToolRegistry",
                tool_name,
            )
        ALL_TOOLS[tool_name] = tool_func

logger.info("Unified tool pool initialized with tools: %s", list(ALL_TOOLS.keys()))


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    tool_type: str
    parameters: Dict[str, Any]
    output_format: str
    example: Dict[str, Any]
    return_value: str
    executor: Callable


class ToolExecutor:
    def __init__(self, specs: Dict[str, ToolSpec]) -> None:
        self._specs = specs

    def get_spec(self, tool_name: str) -> Optional[ToolSpec]:
        return self._specs.get(tool_name)

    def list_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def get_callable(self, tool_name: str) -> Optional[Callable]:
        spec = self.get_spec(tool_name)
        return spec.executor if spec else None


def _build_specs(
    registry_tools: Dict[str, Dict[str, Any]],
    resolver: Callable[[str], Optional[Callable]],
) -> Dict[str, ToolSpec]:
    specs: Dict[str, ToolSpec] = {}
    for tool_name, tool_info in registry_tools.items():
        executor = resolver(tool_name)
        if not executor:
            continue
        specs[tool_name] = ToolSpec(
            name=tool_name,
            description=tool_info["description"],
            tool_type=tool_info["type"],
            parameters=tool_info.get("parameters", {}),
            output_format=tool_info.get("output_format", ""),
            example=tool_info.get("example", {}),
            return_value=tool_info.get("return_value", ""),
            executor=executor,
        )
    return specs


ALL_TOOL_SPECS: Dict[str, ToolSpec] = {}
ALL_TOOL_SPECS.update(_build_specs(MarketToolRegistry.TOOLS, MarketToolRegistry.get_tool))
ALL_TOOL_SPECS.update(
    _build_specs(DatabaseSuperToolRegistry.TOOLS, DatabaseSuperToolRegistry.get_tool)
)


class DynamicToolExecutor:
    def __init__(self, fallback_specs: Dict[str, ToolSpec]) -> None:
        self._fallback = ToolExecutor(fallback_specs)
        self._plugin_manager: PluginManager | None = None

    def set_plugin_manager(self, plugin_manager: PluginManager | None) -> None:
        self._plugin_manager = plugin_manager

    def get_spec(self, tool_name: str):
        if self._plugin_manager:
            plugin_spec = self._plugin_manager.get_tool_spec(tool_name)
            if plugin_spec:
                return plugin_spec
        return self._fallback.get_spec(tool_name)

    def list_specs(self) -> list:
        if self._plugin_manager:
            return self._plugin_manager.get_tool_specs()
        return self._fallback.list_specs()

    def get_callable(self, tool_name: str) -> Optional[Callable]:
        if self._plugin_manager:
            plugin_callable = self._plugin_manager.get_tool_callable(tool_name)
            if plugin_callable:
                return plugin_callable
        return self._fallback.get_callable(tool_name)


tool_executor = DynamicToolExecutor(ALL_TOOL_SPECS)


def set_plugin_manager(plugin_manager: PluginManager | None) -> None:
    tool_executor.set_plugin_manager(plugin_manager)


def get_tool_spec(tool_name: str) -> Optional[ToolSpec]:
    return tool_executor.get_spec(tool_name)


def get_tool_specs() -> list[ToolSpec]:
    return tool_executor.list_specs()
