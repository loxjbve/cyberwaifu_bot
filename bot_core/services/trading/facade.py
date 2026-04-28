from __future__ import annotations

from bot_core.data_repository.trading_repository import TradingRepository
from bot_core.services.trading.account_service import account_service
from bot_core.services.trading.analysis_service import analysis_service
from bot_core.services.trading.loan_service import loan_service
from bot_core.services.trading.order_service import order_service
from bot_core.services.trading.position_service import position_service
from bot_core.services.trading.price_service import price_service


class TradingFacade:
    async def create_market_order(self, *args, **kwargs):
        return await order_service.create_market_order(*args, **kwargs)

    async def create_limit_order(self, *args, **kwargs):
        return await order_service.create_limit_order(*args, **kwargs)

    def update_order_tp_sl(self, *args, **kwargs):
        return TradingRepository.update_order_tp_sl(*args, **kwargs)

    async def set_position_tp_sl(self, *args, **kwargs):
        return await position_service.set_position_tp_sl(*args, **kwargs)

    def get_or_create_account(self, *args, **kwargs):
        return account_service.get_or_create_account(*args, **kwargs)

    async def get_positions(self, *args, **kwargs):
        return await position_service.get_positions(*args, **kwargs)

    def get_positions_snapshot(self, *args, **kwargs):
        return TradingRepository.get_positions(*args, **kwargs)

    def get_orders(self, *args, **kwargs):
        return order_service.get_orders(*args, **kwargs)

    def cancel_order(self, *args, **kwargs):
        return order_service.cancel_order(*args, **kwargs)

    async def get_current_price(self, *args, **kwargs):
        return await price_service.get_current_price(*args, **kwargs)

    def calculate_dynamic_liquidation_threshold(self, *args, **kwargs):
        return position_service._calculate_dynamic_liquidation_threshold(*args, **kwargs)

    def _calculate_dynamic_liquidation_threshold(self, *args, **kwargs):
        return self.calculate_dynamic_liquidation_threshold(*args, **kwargs)

    async def get_pnl_report(self, *args, **kwargs):
        return await analysis_service.get_pnl_report(*args, **kwargs)

    def generate_pnl_chart(self, *args, **kwargs):
        return analysis_service.generate_pnl_chart(*args, **kwargs)

    async def close_all_positions(self, *args, **kwargs):
        return await position_service.close_all_positions(*args, **kwargs)

    async def reduce_position(self, *args, **kwargs):
        return await position_service._reduce_position(*args, **kwargs)

    async def _reduce_position(self, *args, **kwargs):
        return await self.reduce_position(*args, **kwargs)

    async def get_global_ranking_data(self, *args, **kwargs):
        return await analysis_service.get_global_ranking_data(*args, **kwargs)

    async def get_global_deadbeat_ranking_data(self, *args, **kwargs):
        return await analysis_service.get_global_deadbeat_ranking_data(*args, **kwargs)

    async def get_ranking_data(self, *args, **kwargs):
        return await analysis_service.get_ranking_data(*args, **kwargs)

    async def get_deadbeat_ranking_data(self, *args, **kwargs):
        return await analysis_service.get_deadbeat_ranking_data(*args, **kwargs)

    def begging(self, *args, **kwargs):
        return loan_service.begging(*args, **kwargs)

    def apply_loan(self, *args, **kwargs):
        return loan_service.apply_loan(*args, **kwargs)

    def repay_loan(self, *args, **kwargs):
        return loan_service.repay_loan(*args, **kwargs)

    def get_loan_bill(self, *args, **kwargs):
        return loan_service.get_loan_bill(*args, **kwargs)


trading_facade = TradingFacade()
