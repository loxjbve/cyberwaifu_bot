from __future__ import annotations

import logging
from typing import Optional

from telegram import Bot

from bot_core.services.trading.monitor_service import monitor_service

logger = logging.getLogger(__name__)


class TradingMonitor:
    def __init__(self, bot: Optional[Bot] = None) -> None:
        if bot is not None:
            logger.warning(
                "bot_core.services.trading_monitor.TradingMonitor is deprecated; "
                "use bot_core.services.trading.monitor_service.monitor_service instead."
            )
        self.bot = bot

    async def start_monitoring(self):
        return await monitor_service.start_monitoring()

    async def stop_monitoring(self):
        return await monitor_service.stop_monitoring()


_trading_monitor: Optional[TradingMonitor] = None


def get_trading_monitor(bot: Optional[Bot] = None) -> TradingMonitor:
    global _trading_monitor
    if _trading_monitor is None:
        _trading_monitor = TradingMonitor(bot)
    return _trading_monitor


trading_monitor = get_trading_monitor()
