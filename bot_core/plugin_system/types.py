from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from telegram import Update
from telegram.ext import ContextTypes

from bot_core.services.utils.decorators import Decorators


class CommandMeta:
    def __init__(
        self,
        name: str,
        command_type: str,
        group_admin_required: bool = False,
        bot_admin_required: bool = False,
        trigger: str = "",
        menu_text: str = "",
        show_in_menu: bool = True,
        menu_weight: int = 0,
        enabled: bool = True,
    ):
        self.name = name
        self.command_type = command_type
        self.group_admin_required = group_admin_required
        self.bot_admin_required = bot_admin_required
        self.trigger = trigger
        self.menu_text = menu_text
        self.show_in_menu = show_in_menu
        self.menu_weight = menu_weight
        self.enabled = enabled


class BaseCommand(ABC):
    meta: CommandMeta

    def __init__(self):
        if not hasattr(self, "meta"):
            raise NotImplementedError("Command must define meta attribute")
        self.handler = self._build_handler()

    def _build_handler(self) -> Callable:
        func = self.handle
        if self.meta.bot_admin_required:
            func = Decorators.user_admin_required(func)
        if self.meta.command_type == "group" and self.meta.group_admin_required:
            func = Decorators.group_admin_required(func)
        func = Decorators.handle_command_errors(func)
        func = Decorators.ensure_user_info_updated(func)
        if self.meta.command_type == "group":
            func = Decorators.ensure_group_info_updated(func)
        return func

    @abstractmethod
    async def handle(self, update, context: ContextTypes.DEFAULT_TYPE):
        pass


class CallbackMeta:
    def __init__(
        self,
        name: str,
        callback_type: str,
        group_admin_required: bool = False,
        trigger: str = "",
        enabled: bool = True,
    ):
        self.name = name
        self.callback_type = callback_type
        self.group_admin_required = group_admin_required
        self.trigger = trigger
        self.enabled = enabled


class BaseCallback(ABC):
    meta: CallbackMeta

    def __init__(self):
        if not hasattr(self, "meta"):
            raise NotImplementedError("Callback must define meta attribute")
        self.handle_callback = self._build_handler()

    def _build_handler(self) -> Callable:
        func = self.handle_callback
        if self.meta.group_admin_required:
            func = Decorators.group_admin_required(func)
        return func

    @abstractmethod
    async def handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        data: str,
    ) -> None:
        pass


@dataclass(frozen=True)
class PluginMeta:
    id: str
    name: str
    version: str = "0.1.0"
    enabled: bool = True


@dataclass(frozen=True)
class MessageInterceptorMeta:
    name: str
    chat_type: str
    priority: int = 100
    enabled: bool = True


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    tool_type: str
    parameters: dict[str, Any]
    output_format: str
    example: dict[str, Any]
    return_value: str
    executor: Callable


@dataclass(frozen=True)
class BotCommandData:
    command: str
    description: str

    def __repr__(self) -> str:
        return (
            f"BotCommand(command='{self.command}', "
            f"description='{self.description}')"
        )


CommandHandlerCallable = Callable[[Any, Any], Awaitable[None]]
CallbackHandlerCallable = Callable[[Update, ContextTypes.DEFAULT_TYPE, str], Awaitable[None]]
MessageInterceptorCallable = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[bool]]
LifecycleCallable = Callable[..., Awaitable[None]]
PromptProvider = Callable[[], str] | str
OptionalAwaitable = Optional[Awaitable[None]]
