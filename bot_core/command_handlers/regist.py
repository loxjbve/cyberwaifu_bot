import importlib
import inspect

from bot_core.command_handlers.base import BaseCommand
from bot_core.command_handlers.base import BotCommandData
from utils.logging_utils import setup_logging
import logging
setup_logging()
logger = logging.getLogger(__name__)
from telegram.ext import CommandHandler
from typing import Callable

class CommandHandlers:
    """
    命令处理器管理类，负责动态加载和管理Telegram Bot的命令处理器。
    """
    _command_maps: dict[str, dict[str, Callable]] | None = None

    @staticmethod
    def _is_valid_command_class(obj: object) -> bool:
        return (
            inspect.isclass(obj)
            and issubclass(obj, BaseCommand)
            and obj != BaseCommand
            and not inspect.isabstract(obj)
            and hasattr(obj, "meta")
        )

    @classmethod
    def initialize(cls):
        """
        扫描所有命令模块并按聊天类型构建命令映射表。
        这个方法应该在机器人启动时被明确调用一次。
        """
        if cls._command_maps is not None:
            logger.info("命令映射表已初始化，跳过。")
            return

        logger.info("正在初始化命令映射表...")
        cls._command_maps = {"private": {}, "group": {}}
        module_names = ["private", "group", "admin", "trading"]
        for module_name in module_names:
            try:
                module = importlib.import_module(f"bot_core.command_handlers.{module_name}")
            except ImportError as e:
                logger.error(f"导入模块 {module_name} 失败: {e}", exc_info=True)
                continue

            for name, obj in inspect.getmembers(module):
                if cls._is_valid_command_class(obj):
                    try:
                        instance = obj()
                        if instance.meta.enabled:
                            command_type = instance.meta.command_type
                            if command_type == "admin":
                                command_type = "private"  # 管理员命令视为私聊命令
                            
                            if command_type in cls._command_maps:
                                cls._command_maps[command_type][instance.meta.trigger] = instance.handler
                                logger.debug(f"已加载命令: /{instance.meta.trigger} 到 {command_type} 映射")
                    except Exception as e:
                        logger.error(f"为 {name} 创建命令处理器失败: {e}", exc_info=True)

    @classmethod
    def get_command_handler(cls, command: str, chat_type: str) -> Callable | None:
        """
        根据命令触发词和聊天类型获取对应的处理器。
        假定 initialize() 已经在启动时被调用。

        Args:
            command (str): 命令触发词 (不带 /).
            chat_type (str): 聊天类型 ('private' 或 'group').

        Returns:
            Callable | None: 对应的命令处理器或 None。
        """
        if cls._command_maps is None:
            logger.error("命令映射表尚未初始化！请在机器人启动时调用 CommandHandlers.initialize()")
            return None
        
        if chat_type in cls._command_maps:
            return cls._command_maps[chat_type].get(command)
        
        return None

    @staticmethod
    def get_command_definitions(
            module_names: list[str],
    ) -> dict[str, list[BotCommandData]]:  # 类型提示BotCommandData
        """
        动态扫描指定模块，提取所有BaseCommand的子类，并根据其meta属性，生成命令字典。
        Args:
            module_names (list): 模块名称列表.
        Returns:
            dict: 包含命令信息的字典，格式为 {'private': [BotCommand, ...], 'group': [BotCommand, ...]}
        """
        command_definitions: dict[str, list[BotCommandData]] = {
            "private": [],
            "group": [],
        }  # 类型提示BotCommandData
        command_weights: dict[str, dict[str, int]] = {
            "private": {},
            "group": {},
        }
        for module_name in module_names:
            try:
                module = importlib.import_module(
                    f"bot_core.command_handlers.{module_name}"
                )  # 动态导入模块
            except ImportError as e:
                logger.error(
                    f"Error importing module {module_name}: {e}", exc_info=True
                )  # 打印导入错误，方便调试
                continue

            for name, obj in inspect.getmembers(module):  # 扫描模块中的所有成员
                if CommandHandlers._is_valid_command_class(obj):
                    try:
                        instance = obj()  # 创建命令类实例
                        if (
                                instance.meta.enabled and instance.meta.show_in_menu
                        ):  # 确保已激活和显示在菜单中

                            command_type = instance.meta.command_type
                            if command_type == "admin":
                                command_type = "private"  # 将admin命令归类到private
                            if command_type in command_definitions:
                                command_definitions[command_type].append(
                                    BotCommandData(
                                        instance.meta.trigger,
                                        instance.meta.menu_text,
                                    )
                                )
                                command_weights[command_type][instance.meta.trigger] = (
                                    instance.meta.menu_weight
                                )
                            else:
                                print(
                                    f"Unknown command type: {command_type} for command {instance.meta.trigger}"
                                )
                    except Exception as e:
                        logger.error(
                            f"Error processing command {name}: {e}", exc_info=True
                        )  # 打印创建实例或CommandHandler错误，方便调试
                        continue
        # 排序命令列表
        for command_type in command_definitions:
            command_definitions[command_type] = sorted(
                command_definitions[command_type],
                key=lambda cmd: command_weights[command_type].get(cmd.command, 0),
            )
        return command_definitions
