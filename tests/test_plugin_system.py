from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.tools_handler import parse_and_invoke_tool
from agent.tools_registry import set_plugin_manager as set_tool_plugin_manager
from bot_core.builtins import register_builtin_capabilities
from bot_core.plugin_system import (
    AgentToolSpec,
    BaseCallback,
    CallbackHandler,
    CallbackMeta,
    MessageInterceptorMeta,
    PluginManager,
    PluginMeta,
    PluginRegistrar,
    PluginRegistrationError,
)


class FakeSettings:
    def __init__(self, config):
        self.config = config

    def get(self, key=None, default=None):
        if key is None:
            return self.config
        value = self.config
        for part in key.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def _write_plugin(root, name, body):
    plugin_dir = root / name
    plugin_dir.mkdir()
    (plugin_dir / "regist.py").write_text(body, encoding="utf-8")


def test_plugin_manager_loads_commands_and_applies_config(tmp_path):
    _write_plugin(
        tmp_path,
        "alpha",
        """
from bot_core.plugin_system import BaseCommand, CommandMeta, PluginMeta

plugin = PluginMeta(id="alpha", name="Alpha")

class PingCommand(BaseCommand):
    meta = CommandMeta(name="ping", command_type="private", trigger="ping", menu_text="Ping")

    async def handle(self, update, context):
        pass

def register(registrar):
    registrar.register_command(PingCommand)
""",
    )

    disabled_settings = FakeSettings(
        {
            "plugins": {
                "items": {
                    "alpha": {
                        "commands": {
                            "ping": {"enabled": False},
                        },
                    },
                },
            },
        }
    )
    disabled_manager = PluginManager(root_path=tmp_path, settings=disabled_settings)
    disabled_manager.load()
    assert disabled_manager.get_command_handler("ping", "private") is None

    enabled_manager = PluginManager(root_path=tmp_path, settings=FakeSettings({}))
    enabled_manager.load()
    assert enabled_manager.get_command_handler("ping", "private") is not None
    assert enabled_manager.get_command_definitions()["private"][0].command == "ping"


def test_plugin_manager_rejects_duplicate_commands(tmp_path):
    plugin_body = """
from bot_core.plugin_system import BaseCommand, CommandMeta, PluginMeta

plugin = PluginMeta(id="{plugin_id}", name="{plugin_id}")

class PingCommand(BaseCommand):
    meta = CommandMeta(name="ping", command_type="private", trigger="ping")

    async def handle(self, update, context):
        pass

def register(registrar):
    registrar.register_command(PingCommand)
"""
    _write_plugin(tmp_path, "alpha", plugin_body.format(plugin_id="alpha"))
    _write_plugin(tmp_path, "beta", plugin_body.format(plugin_id="beta"))

    manager = PluginManager(root_path=tmp_path)
    with pytest.raises(PluginRegistrationError, match="Duplicate command"):
        manager.load()


def test_plugin_manager_rejects_plugin_directory_without_regist(tmp_path):
    (tmp_path / "missing_entrypoint").mkdir()

    manager = PluginManager(root_path=tmp_path)

    with pytest.raises(PluginRegistrationError, match="missing regist.py"):
        manager.load()


def test_callback_dispatcher_uses_longest_prefix_first():
    calls = []
    manager = PluginManager(root_path="unused")
    registrar = PluginRegistrar(manager, PluginMeta(id="test", name="Test"))

    class ShortCallback(BaseCallback):
        meta = CallbackMeta(name="short", callback_type="private", trigger="a")

        async def handle_callback(self, update, context, data):
            calls.append(("short", data))

    class LongCallback(BaseCallback):
        meta = CallbackMeta(name="long", callback_type="private", trigger="ab_")

        async def handle_callback(self, update, context, data):
            calls.append(("long", data))

    registrar.register_callback(ShortCallback)
    registrar.register_callback(LongCallback)

    class Query:
        data = "ab_value"
        from_user = SimpleNamespace(id=1)
        message = SimpleNamespace(reply_text=lambda text: None)

        async def answer(self):
            pass

    update = SimpleNamespace(callback_query=Query())
    context = SimpleNamespace(bot_data={"plugin_manager": manager})

    asyncio.run(CallbackHandler(manager).handle_callback_query(update, context))

    assert calls == [("long", "value")]


def test_message_interceptors_respect_priority_and_consumption():
    calls = []
    manager = PluginManager(root_path="unused")
    registrar = PluginRegistrar(manager, PluginMeta(id="test", name="Test"))

    async def first(update, context):
        calls.append("first")
        return False

    async def second(update, context):
        calls.append("second")
        return True

    async def third(update, context):
        calls.append("third")
        return True

    registrar.register_message_interceptor(
        MessageInterceptorMeta(name="third", chat_type="private", priority=30),
        third,
    )
    registrar.register_message_interceptor(
        MessageInterceptorMeta(name="first", chat_type="private", priority=10),
        first,
    )
    registrar.register_message_interceptor(
        MessageInterceptorMeta(name="second", chat_type="private", priority=20),
        second,
    )
    manager._message_interceptors.sort(key=lambda item: item.meta.priority)

    consumed = asyncio.run(
        manager.run_message_interceptors(
            SimpleNamespace(),
            SimpleNamespace(),
            "private",
        )
    )

    assert consumed is True
    assert calls == ["first", "second"]


def test_lifecycle_hooks_run_startup_and_shutdown():
    calls = []
    manager = PluginManager(root_path="unused")
    registrar = PluginRegistrar(manager, PluginMeta(id="test", name="Test"))

    async def startup(app, settings):
        calls.append(("startup", app.name, settings.name))

    async def shutdown(app, settings):
        calls.append(("shutdown", app.name, settings.name))

    registrar.register_lifecycle(startup=startup, shutdown=shutdown)

    app = SimpleNamespace(name="app")
    settings = SimpleNamespace(name="settings")
    asyncio.run(manager.run_startup(app, settings))
    asyncio.run(manager.run_shutdown(app, settings))

    assert calls == [("startup", "app", "settings"), ("shutdown", "app", "settings")]


def test_agent_tools_can_be_registered_by_plugin_manager():
    manager = PluginManager(root_path="unused")
    registrar = PluginRegistrar(manager, PluginMeta(id="tools", name="Tools"))

    async def echo_tool(value: str):
        return {"display": f"display:{value}", "llm_feedback": f"feedback:{value}"}

    registrar.register_agent_tool(
        AgentToolSpec(
            name="echo_tool",
            description="Echo a value",
            tool_type="query",
            parameters={"value": {"type": "string"}},
            output_format="text",
            example={"tool_name": "echo_tool", "parameters": {"value": "x"}},
            return_value="echoed text",
            executor=echo_tool,
        )
    )

    set_tool_plugin_manager(manager)
    try:
        _, display_results, llm_feedback, had_tool_calls = asyncio.run(
            parse_and_invoke_tool(
                '{"tool_name":"echo_tool","parameters":{"value":"hello","ignored":"x"}}'
            )
        )
    finally:
        set_tool_plugin_manager(None)

    assert had_tool_calls is True
    assert display_results[0]["result"] == "display:hello"
    assert llm_feedback[0]["result"] == "feedback:hello"


def test_builtin_capabilities_are_not_plugins():
    manager = PluginManager(root_path="unused")
    register_builtin_capabilities(manager)

    assert "core" not in manager.plugins
    assert manager.get_command_handler("help", "private") is not None
    assert manager.get_command_handler("kw", "group") is not None
    assert any(
        registration.meta.trigger == "settings_"
        for registration in manager.iter_callbacks()
    )
