import logging

from plugins.trading.commands import (
    BeggingCommand,
    BillCommand,
    CancelCommand,
    CloseCommand,
    LoanCommand,
    LongCommand,
    PnlCommand,
    PositionCommand,
    RankCommand,
    RepayCommand,
    ShortCommand,
    StopLossCommand,
    TakeProfitCommand,
    TestLiquidationCommand,
)
from bot_core.plugin_system import PluginMeta
from bot_core.services.trading.monitor_service import monitor_service
from plugins._helpers import register_commands

logger = logging.getLogger(__name__)

plugin = PluginMeta(id="trading", name="Trading")


def _monitor_enabled(settings) -> bool:
    plugin_config = settings.get("plugins.items.trading", {})
    if isinstance(plugin_config, dict):
        lifecycle_config = plugin_config.get("lifecycle", {})
        if isinstance(lifecycle_config, dict):
            monitor_config = lifecycle_config.get("monitor", {})
            if isinstance(monitor_config, dict) and "enabled" in monitor_config:
                return bool(monitor_config["enabled"])

        monitor_config = plugin_config.get("monitor", {})
        if isinstance(monitor_config, dict) and "enabled" in monitor_config:
            return bool(monitor_config["enabled"])

    return bool(settings.features.start_monitor)


async def startup(app, settings) -> None:
    if _monitor_enabled(settings):
        await monitor_service.start_monitoring()
        logger.info("Trading monitor started")


async def shutdown(app, settings) -> None:
    if _monitor_enabled(settings):
        await monitor_service.stop_monitoring()
        logger.info("Trading monitor stopped")


def register(registrar):
    register_commands(
        registrar,
        [
            LongCommand,
            ShortCommand,
            PositionCommand,
            PnlCommand,
            BeggingCommand,
            CloseCommand,
            RankCommand,
            TestLiquidationCommand,
            LoanCommand,
            RepayCommand,
            BillCommand,
            TakeProfitCommand,
            StopLossCommand,
            CancelCommand,
        ],
    )
    registrar.register_lifecycle(startup=startup, shutdown=shutdown)
