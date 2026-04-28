import argparse
import logging
import threading
from typing import Optional, Sequence

from telegram import BotCommand as TelegramBotCommand
from telegram import BotCommandScopeAllGroupChats, BotCommandScopeDefault, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

import bot_core.message_handlers.group as group_handler
import bot_core.message_handlers.private as private_handler
from bot_core.callback_handlers.callback import create_callback_handler
from bot_core.command_handlers.regist import CommandHandlers
from bot_core.services.trading.monitor_service import monitor_service
from bot_core.services.utils.error import BotError, error_handler
from utils.config_utils import AppSettings, load_settings, validate_settings
from utils.db_utils import close_all_connections
from utils.logging_utils import setup_logging
from web.factory import create_app

setup_logging()
logger = logging.getLogger(__name__)


def setup_handlers(app: Application) -> None:
    message_handlers = [
        MessageHandler(
            (filters.TEXT | filters.Document.ALL | filters.PHOTO | filters.Sticker.ALL)
            & filters.ChatType.PRIVATE,
            private_handler.private_msg_handler,
        ),
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL)
            & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
            group_handler.group_msg_handler,
        ),
    ]

    callback_handler = create_callback_handler(["bot_core.callback_handlers"])
    app.add_handler(CallbackQueryHandler(callback_handler.handle_callback_query))
    for handler in message_handlers:
        app.add_handler(handler)


async def setup_command_menu(app_instance: Application) -> None:
    try:
        command_menus = CommandHandlers.get_command_definitions(
            ["private", "group", "admin", "trading"]
        )
        private_commands = [
            TelegramBotCommand(cmd.command, cmd.description)
            for cmd in command_menus["private"]
        ]
        group_commands = [
            TelegramBotCommand(cmd.command, cmd.description)
            for cmd in command_menus["group"]
        ]

        await app_instance.bot.set_my_commands(private_commands, scope=BotCommandScopeDefault())  # type: ignore[arg-type]
        await app_instance.bot.set_my_commands(
            group_commands,
            scope=BotCommandScopeAllGroupChats(),
        )  # type: ignore[arg-type]
    except Exception as error:
        logger.error("Failed to setup command menu: %s", error, exc_info=True)
        raise BotError(f"设置命令菜单失败: {error}")


async def _post_init(app_instance: Application, settings: AppSettings) -> None:
    await setup_command_menu(app_instance)
    if settings.features.start_monitor:
        await monitor_service.start_monitoring()
        logger.info("Trading monitor started")


async def _post_shutdown(_: Application, settings: AppSettings) -> None:
    if settings.features.start_monitor:
        await monitor_service.stop_monitoring()
        logger.info("Trading monitor stopped")
    close_all_connections()


def register_lifecycle(app: Application, settings: AppSettings) -> None:
    async def post_init(app_instance: Application) -> None:
        await _post_init(app_instance, settings)

    async def post_shutdown(app_instance: Application) -> None:
        await _post_shutdown(app_instance, settings)

    app.post_init = post_init
    app.post_shutdown = post_shutdown


def build_bot_app(settings: AppSettings) -> Application:
    validate_settings(settings, require_bot_token=True)
    CommandHandlers.initialize()

    app = Application.builder().token(settings.telegram_token).build()
    setup_handlers(app)
    app.add_error_handler(error_handler)
    register_lifecycle(app, settings)
    return app


def _run_web_app(settings: AppSettings) -> None:
    app = create_app(settings)
    logger.info("Starting web admin at http://%s:%s", settings.web.host, settings.web.port)
    app.run(
        debug=settings.web.debug,
        host=settings.web.host,
        port=settings.web.port,
        use_reloader=False,
    )


def start_web(settings: AppSettings) -> threading.Thread:
    web_thread = threading.Thread(target=_run_web_app, args=(settings,), daemon=True)
    web_thread.start()
    logger.info("Web admin started in background thread")
    return web_thread


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CyberWaifu bot runtime")
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=["all", "bot", "web"],
        help="Runtime mode",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    settings = load_settings(force_reload=True)

    try:
        validate_settings(settings, require_bot_token=args.mode in {"all", "bot"})

        if args.mode == "web":
            _run_web_app(settings)
            return

        if args.mode == "all" and settings.features.start_web:
            start_web(settings)

        app = build_bot_app(settings)
        logger.info("Bot initialized, starting polling in %s mode", args.mode)
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as error:
        logger.error("Runtime failed: %s", error, exc_info=True)
        raise BotError(f"运行失败: {error}")


if __name__ == "__main__":
    main()
