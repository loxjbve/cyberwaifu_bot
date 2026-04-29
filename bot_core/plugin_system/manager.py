from __future__ import annotations

import importlib.util
import inspect
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

from bot_core.plugin_system.types import (
    AgentToolSpec,
    BaseCallback,
    BaseCommand,
    BotCommandData,
    CallbackMeta,
    MessageInterceptorCallable,
    MessageInterceptorMeta,
    PluginMeta,
    PromptProvider,
)
from utils.config_utils import AppSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandRegistration:
    plugin_id: str
    instance: BaseCommand
    meta: Any
    handler: Callable


@dataclass(frozen=True)
class CallbackRegistration:
    plugin_id: str
    instance: BaseCallback
    meta: Any
    handler: Callable


@dataclass(frozen=True)
class MessageInterceptorRegistration:
    plugin_id: str
    meta: MessageInterceptorMeta
    handler: MessageInterceptorCallable


@dataclass(frozen=True)
class LifecycleRegistration:
    plugin_id: str
    startup: Callable | None = None
    shutdown: Callable | None = None


@dataclass(frozen=True)
class PromptSectionRegistration:
    plugin_id: str
    name: str
    provider: PromptProvider


class PluginRegistrationError(RuntimeError):
    pass


class PluginRegistrar:
    def __init__(self, manager: "PluginManager", plugin_meta: PluginMeta) -> None:
        self._manager = manager
        self.plugin_meta = plugin_meta

    def register_command(self, command_cls: type[BaseCommand]) -> None:
        self._manager._register_command(self.plugin_meta.id, command_cls)

    def register_callback(self, callback_cls: type[BaseCallback]) -> None:
        self._manager._register_callback(self.plugin_meta.id, callback_cls)

    def register_message_interceptor(
        self,
        meta: MessageInterceptorMeta,
        handler: MessageInterceptorCallable,
    ) -> None:
        self._manager._register_message_interceptor(self.plugin_meta.id, meta, handler)

    def register_lifecycle(
        self,
        *,
        startup: Callable | None = None,
        shutdown: Callable | None = None,
    ) -> None:
        self._manager._register_lifecycle(self.plugin_meta.id, startup, shutdown)

    def register_agent_tool(self, tool_spec: AgentToolSpec) -> None:
        self._manager._register_agent_tool(self.plugin_meta.id, tool_spec)

    def register_prompt_section(self, name: str, provider: PromptProvider) -> None:
        self._manager._register_prompt_section(self.plugin_meta.id, name, provider)


class PluginManager:
    def __init__(
        self,
        *,
        root_path: str | Path,
        settings: AppSettings | None = None,
    ) -> None:
        self.root_path = Path(root_path)
        self.settings = settings
        self.plugins: dict[str, PluginMeta] = {}
        self._commands: dict[str, dict[str, CommandRegistration]] = {
            "private": {},
            "group": {},
        }
        self._callbacks: dict[str, CallbackRegistration] = {}
        self._message_interceptors: list[MessageInterceptorRegistration] = []
        self._lifecycles: list[LifecycleRegistration] = []
        self._agent_tools: dict[str, AgentToolSpec] = {}
        self._prompt_sections: dict[str, PromptSectionRegistration] = {}
        self._loaded = False

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "PluginManager":
        return cls(root_path=Path(settings.project_root) / "plugins", settings=settings)

    def load(self) -> None:
        if self._loaded:
            logger.info("Plugin manager already loaded; skipping")
            return

        if not self._plugins_globally_enabled():
            logger.info("Plugins are disabled by configuration")
            self._loaded = True
            return

        if not self.root_path.exists():
            logger.warning("Plugin directory does not exist: %s", self.root_path)
            self._loaded = True
            return

        for plugin_dir in sorted(self.root_path.iterdir(), key=lambda path: path.name):
            if not plugin_dir.is_dir() or plugin_dir.name == "__pycache__":
                continue
            if not plugin_dir.name.isidentifier():
                logger.warning("Skipping plugin with invalid directory name: %s", plugin_dir)
                continue

            regist_path = plugin_dir / "regist.py"
            if not regist_path.exists():
                raise PluginRegistrationError(
                    f"Plugin directory {plugin_dir.name} is missing regist.py"
                )

            module = self._load_module(plugin_dir.name, regist_path)
            plugin_meta = getattr(module, "plugin", None)
            register = getattr(module, "register", None)
            if not isinstance(plugin_meta, PluginMeta):
                raise PluginRegistrationError(
                    f"Plugin {plugin_dir.name} must define plugin = PluginMeta(...)"
                )
            if not callable(register):
                raise PluginRegistrationError(
                    f"Plugin {plugin_meta.id} must define register(registrar)"
                )
            if plugin_meta.id in self.plugins:
                raise PluginRegistrationError(f"Duplicate plugin id: {plugin_meta.id}")
            if not self._plugin_enabled(plugin_meta):
                logger.info("Plugin %s is disabled", plugin_meta.id)
                continue

            registrar = PluginRegistrar(self, plugin_meta)
            register(registrar)
            self.plugins[plugin_meta.id] = plugin_meta
            logger.info("Loaded plugin %s (%s)", plugin_meta.id, plugin_meta.name)

        self._message_interceptors.sort(
            key=lambda item: (item.meta.priority, item.plugin_id, item.meta.name)
        )
        self._loaded = True

    def _load_module(self, plugin_dir_name: str, regist_path: Path) -> ModuleType:
        module_name = f"plugins.{plugin_dir_name}.regist"
        spec = importlib.util.spec_from_file_location(module_name, regist_path)
        if spec is None or spec.loader is None:
            raise PluginRegistrationError(f"Unable to load plugin module: {regist_path}")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            raise PluginRegistrationError(
                f"Failed to import plugin {plugin_dir_name}: {error}"
            ) from error
        return module

    def _plugins_globally_enabled(self) -> bool:
        config = self._plugins_config()
        return bool(config.get("enabled", True))

    def _plugins_config(self) -> dict[str, Any]:
        if not self.settings:
            return {}
        value = self.settings.get("plugins", {})
        return value if isinstance(value, dict) else {}

    def _plugin_config(self, plugin_id: str) -> dict[str, Any]:
        config = self._plugins_config().get("items", {}).get(plugin_id, {})
        return config if isinstance(config, dict) else {}

    def _plugin_enabled(self, plugin_meta: PluginMeta) -> bool:
        plugin_config = self._plugin_config(plugin_meta.id)
        return bool(plugin_config.get("enabled", plugin_meta.enabled))

    def _item_enabled(
        self,
        plugin_id: str,
        section: str,
        item_name: str,
        trigger: str,
        default: bool,
    ) -> bool:
        plugin_config = self._plugin_config(plugin_id)
        section_config = plugin_config.get(section, {})
        if not isinstance(section_config, dict):
            return default

        for key in (trigger, item_name):
            item_config = section_config.get(key)
            if isinstance(item_config, dict) and "enabled" in item_config:
                return bool(item_config["enabled"])
        return default

    def _register_command(self, plugin_id: str, command_cls: type[BaseCommand]) -> None:
        if not self._valid_command_class(command_cls):
            raise PluginRegistrationError(
                f"Plugin {plugin_id} registered invalid command: {command_cls}"
            )

        instance = command_cls()
        meta = instance.meta
        trigger = meta.trigger
        if not trigger:
            raise PluginRegistrationError(
                f"Command {meta.name} in plugin {plugin_id} has empty trigger"
            )
        if not self._item_enabled(
            plugin_id, "commands", meta.name, trigger, bool(meta.enabled)
        ):
            logger.info("Command /%s from plugin %s is disabled", trigger, plugin_id)
            return

        command_type = self._normalize_command_type(meta.command_type)
        if command_type not in self._commands:
            raise PluginRegistrationError(
                f"Unknown command type {meta.command_type!r} for /{trigger}"
            )
        if trigger in self._commands[command_type]:
            previous = self._commands[command_type][trigger]
            raise PluginRegistrationError(
                f"Duplicate command /{trigger} for {command_type}: "
                f"{previous.plugin_id} and {plugin_id}"
            )

        self._commands[command_type][trigger] = CommandRegistration(
            plugin_id=plugin_id,
            instance=instance,
            meta=meta,
            handler=instance.handler,
        )

    def _register_callback(self, plugin_id: str, callback_cls: type[BaseCallback]) -> None:
        if not self._valid_callback_class(callback_cls):
            raise PluginRegistrationError(
                f"Plugin {plugin_id} registered invalid callback: {callback_cls}"
            )

        instance = callback_cls()
        meta = instance.meta
        trigger = meta.trigger
        if not trigger:
            raise PluginRegistrationError(
                f"Callback {meta.name} in plugin {plugin_id} has empty trigger"
            )
        if not self._item_enabled(
            plugin_id, "callbacks", meta.name, trigger, bool(meta.enabled)
        ):
            logger.info("Callback %s from plugin %s is disabled", trigger, plugin_id)
            return
        if trigger in self._callbacks:
            previous = self._callbacks[trigger]
            raise PluginRegistrationError(
                f"Duplicate callback prefix {trigger}: {previous.plugin_id} and {plugin_id}"
            )

        self._callbacks[trigger] = CallbackRegistration(
            plugin_id=plugin_id,
            instance=instance,
            meta=meta,
            handler=instance.handle_callback,
        )

    def _register_message_interceptor(
        self,
        plugin_id: str,
        meta: MessageInterceptorMeta,
        handler: MessageInterceptorCallable,
    ) -> None:
        if not callable(handler):
            raise PluginRegistrationError(
                f"Message interceptor {meta.name} in plugin {plugin_id} is not callable"
            )
        if meta.chat_type not in {"private", "group", "both"}:
            raise PluginRegistrationError(
                f"Unknown interceptor chat_type {meta.chat_type!r} for {meta.name}"
            )
        if not self._item_enabled(
            plugin_id,
            "message_interceptors",
            meta.name,
            meta.name,
            bool(meta.enabled),
        ):
            logger.info(
                "Message interceptor %s from plugin %s is disabled",
                meta.name,
                plugin_id,
            )
            return

        self._message_interceptors.append(
            MessageInterceptorRegistration(plugin_id=plugin_id, meta=meta, handler=handler)
        )

    def _register_lifecycle(
        self,
        plugin_id: str,
        startup: Callable | None,
        shutdown: Callable | None,
    ) -> None:
        if startup is None and shutdown is None:
            raise PluginRegistrationError(
                f"Plugin {plugin_id} registered empty lifecycle hooks"
            )
        self._lifecycles.append(
            LifecycleRegistration(plugin_id=plugin_id, startup=startup, shutdown=shutdown)
        )

    def _register_agent_tool(self, plugin_id: str, tool_spec: AgentToolSpec) -> None:
        if not self._item_enabled(
            plugin_id,
            "agent_tools",
            tool_spec.name,
            tool_spec.name,
            True,
        ):
            logger.info("Agent tool %s from plugin %s is disabled", tool_spec.name, plugin_id)
            return
        if tool_spec.name in self._agent_tools:
            raise PluginRegistrationError(
                f"Duplicate agent tool {tool_spec.name}: plugin {plugin_id}"
            )
        self._agent_tools[tool_spec.name] = tool_spec

    def _register_prompt_section(
        self,
        plugin_id: str,
        name: str,
        provider: PromptProvider,
    ) -> None:
        if name in self._prompt_sections:
            raise PluginRegistrationError(f"Duplicate prompt section: {name}")
        self._prompt_sections[name] = PromptSectionRegistration(
            plugin_id=plugin_id,
            name=name,
            provider=provider,
        )

    @staticmethod
    def _valid_command_class(obj: object) -> bool:
        return (
            inspect.isclass(obj)
            and issubclass(obj, BaseCommand)
            and obj != BaseCommand
            and not inspect.isabstract(obj)
            and hasattr(obj, "meta")
        )

    @staticmethod
    def _valid_callback_class(obj: object) -> bool:
        return (
            inspect.isclass(obj)
            and issubclass(obj, BaseCallback)
            and obj != BaseCallback
            and not inspect.isabstract(obj)
            and hasattr(obj, "meta")
        )

    @staticmethod
    def _normalize_command_type(command_type: str) -> str:
        if command_type == "admin":
            return "private"
        return command_type

    def get_command_handler(self, command: str, chat_type: str) -> Callable | None:
        registration = self._commands.get(chat_type, {}).get(command)
        return registration.handler if registration else None

    def get_command_definitions(self) -> dict[str, list[BotCommandData]]:
        result: dict[str, list[BotCommandData]] = {"private": [], "group": []}
        for chat_type, registrations in self._commands.items():
            visible = [
                registration
                for registration in registrations.values()
                if registration.meta.show_in_menu
            ]
            visible.sort(key=lambda registration: registration.meta.menu_weight)
            result[chat_type] = [
                BotCommandData(registration.meta.trigger, registration.meta.menu_text)
                for registration in visible
            ]
        return result

    def iter_callbacks(self) -> Iterable[CallbackRegistration]:
        return sorted(
            self._callbacks.values(),
            key=lambda registration: len(registration.meta.trigger),
            reverse=True,
        )

    async def run_message_interceptors(
        self,
        update: Any,
        context: Any,
        chat_type: str,
    ) -> bool:
        for interceptor in self._message_interceptors:
            if interceptor.meta.chat_type not in {chat_type, "both"}:
                continue
            consumed = await interceptor.handler(update, context)
            if consumed:
                logger.debug(
                    "Message consumed by interceptor %s from plugin %s",
                    interceptor.meta.name,
                    interceptor.plugin_id,
                )
                return True
        return False

    async def run_startup(self, app: Any, settings: AppSettings) -> None:
        for lifecycle in self._lifecycles:
            if lifecycle.startup:
                await self._invoke_lifecycle(lifecycle.startup, app, settings)

    async def run_shutdown(self, app: Any, settings: AppSettings) -> None:
        for lifecycle in reversed(self._lifecycles):
            if lifecycle.shutdown:
                await self._invoke_lifecycle(lifecycle.shutdown, app, settings)

    @staticmethod
    async def _invoke_lifecycle(
        hook: Callable,
        app: Any,
        settings: AppSettings,
    ) -> None:
        parameters = inspect.signature(hook).parameters
        if len(parameters) == 0:
            result = hook()
        elif len(parameters) == 1:
            result = hook(app)
        else:
            result = hook(app, settings)
        if inspect.isawaitable(result):
            await result

    def get_tool_spec(self, tool_name: str) -> AgentToolSpec | None:
        return self._agent_tools.get(tool_name)

    def get_tool_specs(self) -> list[AgentToolSpec]:
        return list(self._agent_tools.values())

    def get_tool_callable(self, tool_name: str) -> Callable | None:
        tool_spec = self.get_tool_spec(tool_name)
        return tool_spec.executor if tool_spec else None

    def get_prompt_section(self, name: str) -> str | None:
        registration = self._prompt_sections.get(name)
        if not registration:
            return None
        provider = registration.provider
        return provider() if callable(provider) else provider

    def get_prompt_sections(self) -> dict[str, str]:
        rendered: dict[str, str] = {}
        for name in self._prompt_sections:
            section = self.get_prompt_section(name)
            if section is not None:
                rendered[name] = section
        return rendered


_default_plugin_manager: PluginManager | None = None


def set_default_plugin_manager(manager: PluginManager | None) -> None:
    global _default_plugin_manager
    _default_plugin_manager = manager


def get_default_plugin_manager() -> PluginManager | None:
    return _default_plugin_manager


def resolve_plugin_manager(context: Any | None = None) -> PluginManager | None:
    bot_data = getattr(context, "bot_data", None) if context is not None else None
    if isinstance(bot_data, dict):
        manager = bot_data.get("plugin_manager")
        if manager is not None:
            return manager
    return get_default_plugin_manager()
