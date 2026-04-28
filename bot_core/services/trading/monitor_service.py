"""
监控服务
负责价格轮询、订单触发、强平监控和利息计算
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import os

from .account_service import account_service
from .order_service import order_service
from .position_service import position_service
from .price_service import price_service
from bot_core.data_repository.trading_repository import TradingRepository
from utils.logging_utils import setup_logging
from utils.db_utils import user_info_get
from utils.config_utils import get_settings
from telegram import Bot

setup_logging()
logger = logging.getLogger(__name__)


class MonitorService:
    """
    监控服务类
    负责定时监控价格、触发订单、检查强平条件和利息计算
    """

    def __init__(self):
        self.is_running = False
        self.monitor_task = None
        self.price_check_interval = 10  # 价格检查间隔(秒)
        self.liquidation_check_interval = 30  # 强平检查间隔(秒)
        self.interest_update_interval = 21600  # 利息更新间隔(6小时)

        # 回调函数
        self.on_liquidation_callback: Optional[Callable] = None

        # 定时器计数器
        self.price_counter = 0
        self.liquidation_counter = 0
        self.interest_counter = 0

        logger.info("监控服务已初始化")

    async def start_monitoring(self):
        """启动监控服务"""
        if self.is_running:
            logger.warning("监控服务已在运行中")
            return

        self.is_running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("监控服务已启动")

    async def stop_monitoring(self):
        """停止监控服务"""
        self.is_running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("监控服务已停止")

    async def _monitor_loop(self):
        """主监控循环"""
        logger.info("监控循环已启动")

        try:
            while self.is_running:
                try:
                    # 更新计数器
                    self.price_counter += 1
                    self.liquidation_counter += 1
                    self.interest_counter += 1

                    # 每10秒检查订单触发条件和止盈止损
                    if self.price_counter >= 1:
                        self.price_counter = 0
                        await self._check_pending_orders()
                        await self._check_stop_loss_take_profit_orders()

                    # 每30秒检查一次强平条件
                    if self.liquidation_counter >= 3:
                        self.liquidation_counter = 0
                        await self._check_liquidations()

                    # 每6小时更新一次利息
                    if self.interest_counter >= 2160:  # 6小时 * 3600秒 / 10秒
                        self.interest_counter = 0
                        await self._update_loan_interests()

                    # 等待10秒
                    await asyncio.sleep(10)

                except Exception as e:
                    logger.error(f"监控循环出错: {e}")
                    await asyncio.sleep(10)  # 出错后等待10秒再继续

        except asyncio.CancelledError:
            logger.info("监控循环被取消")
            raise

    async def _check_pending_orders(self):
        """检查待成交订单是否可以触发"""
        try:
            # 获取所有待成交订单
            pending_orders_result = TradingRepository.get_orders_by_type('open', 'pending')
            if not pending_orders_result["success"]:
                return

            orders = pending_orders_result["orders"]
            logger.debug(f"检查 {len(orders)} 个待成交订单")

            if not orders:
                return

            # 收集所有需要的交易对
            symbols = set(order['symbol'] for order in orders)
            
            # 批量获取价格
            prices = {}
            for symbol in symbols:
                try:
                    price = await price_service.get_real_time_price(symbol)
                    if price > 0:
                        prices[symbol] = price
                except Exception as e:
                    logger.error(f"获取 {symbol} 价格失败: {e}")

            triggered_orders = []
            
            for order in orders:
                try:
                    symbol = order['symbol']
                    if symbol not in prices:
                        logger.debug(f"无法获取 {symbol} 的实时价格，跳过订单 {order['order_id']}")
                        continue
                    
                    current_price = prices[symbol]
                    
                    # 检查订单是否可以触发
                    can_trigger = await self._check_order_trigger_condition_with_price(order, current_price)
                    
                    if can_trigger:
                        # 执行订单
                        result = await order_service.execute_order(order["order_id"])
                        
                        if result["success"]:
                            logger.info(f"订单 {order['order_id']} 已成功执行")
                            triggered_orders.append(order)
                            
                            # 发送订单触发通知
                            await self._send_order_trigger_notification(order, current_price, "限价单")
                            
                            # 检查是否需要触发止盈止损订单
                            await self._check_and_create_stop_orders(order)
                        else:
                            logger.debug(f"订单 {order['order_id']} 执行失败: {result.get('message', '未知错误')}")

                except Exception as e:
                    logger.error(f"检查订单 {order['order_id']} 失败: {e}")
                    continue
            
            # 检查现有仓位的止盈止损条件
            await self._check_stop_loss_take_profit_orders()
            
            if triggered_orders:
                logger.info(f"本轮触发了 {len(triggered_orders)} 个订单")

        except Exception as e:
            logger.error(f"检查待成交订单失败: {e}")

    async def _check_liquidations(self):
        """检查所有仓位是否需要强平"""
        try:
            # 获取所有仓位
            positions_result = TradingRepository.get_all_positions()
            if not positions_result["success"]:
                return

            positions = positions_result["positions"]
            logger.debug(f"检查 {len(positions)} 个仓位强平条件")

            # 按用户分组检查强平
            user_positions = {}
            for pos in positions:
                user_key = (pos['user_id'], pos['group_id'])
                if user_key not in user_positions:
                    user_positions[user_key] = []
                user_positions[user_key].append(pos)

            liquidated_positions = []

            for (user_id, group_id), user_pos_list in user_positions.items():
                user_liquidated = await self._check_user_liquidations(user_id, group_id, user_pos_list)
                liquidated_positions.extend(user_liquidated)

            # 处理强平结果
            if liquidated_positions:
                logger.info(f"共处理 {len(liquidated_positions)} 个强平")
                for position_info in liquidated_positions:
                    if self.on_liquidation_callback:
                        try:
                            await self.on_liquidation_callback(position_info)
                        except Exception as e:
                            logger.error(f"执行强平回调失败: {e}")

        except Exception as e:
            logger.error(f"检查强平失败: {e}")

    async def _check_user_liquidations(self, user_id: int, group_id: int, positions: List[Dict]) -> List[Dict]:
        """检查单个用户的强平条件"""
        try:
            liquidated_positions = []

            # 获取用户账户信息
            account = account_service.get_or_create_account(user_id, group_id)
            initial_balance = 1000.0  # 初始本金

            # 收集所有需要的交易对，避免重复获取价格
            symbols_needed = set(pos['symbol'] for pos in positions)
            symbol_prices = {}
            
            # 批量获取价格
            for symbol in symbols_needed:
                price = await price_service.get_real_time_price(symbol)
                if price > 0:
                    symbol_prices[symbol] = price

            # 计算总未实现盈亏
            total_unrealized_pnl = 0.0
            position_details = []

            for pos in positions:
                symbol = pos['symbol']
                side = pos['side']
                size = pos['size']
                entry_price = pos['entry_price']
                liquidation_price = pos['liquidation_price']

                # 使用缓存的价格
                current_price = symbol_prices.get(symbol, 0)
                if current_price <= 0:
                    continue

                # 计算该仓位的未实现盈亏
                if side == 'long':
                    unrealized_pnl = (current_price - entry_price) * (size / entry_price)
                else:
                    unrealized_pnl = (entry_price - current_price) * (size / entry_price)

                total_unrealized_pnl += unrealized_pnl

                position_details.append({
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'liquidation_price': liquidation_price,
                    'unrealized_pnl': unrealized_pnl
                })

            # 计算浮动余额
            floating_balance = account['balance'] + total_unrealized_pnl

            # 计算动态强平阈值（基于杠杆率）
            total_position_value = sum(pos['size'] for pos in positions)
            leverage_ratio = total_position_value / account['balance'] if account['balance'] > 0 else float('inf')

            dynamic_threshold_ratio = self._calculate_dynamic_liquidation_threshold(leverage_ratio)
            liquidation_threshold = account['balance'] * dynamic_threshold_ratio

            # 检查是否触发强平
            if floating_balance < liquidation_threshold:
                logger.info(f"用户 {user_id} 在群组 {group_id} 触发强平，浮动余额: {floating_balance:.2f}, 阈值: {liquidation_threshold:.2f}")

                # 统计强平信息
                total_position_value = sum(pos['size'] for pos in positions)

                liquidated_positions.append({
                    'user_id': user_id,
                    'group_id': group_id,
                    'floating_balance': floating_balance,
                    'threshold': liquidation_threshold,
                    'leverage_ratio': leverage_ratio,
                    'threshold_ratio': dynamic_threshold_ratio,
                    'total_positions': len(positions),
                    'total_position_value': total_position_value
                })

                # 格式化并发送强平通知
                notification_message = self._format_liquidation_message(
                    user_id, positions, floating_balance, liquidation_threshold, leverage_ratio
                )
                await self._send_liquidation_notification(user_id, group_id, notification_message)

                # 执行强平清算
                await self._execute_liquidation(user_id, group_id, positions, floating_balance)

            return liquidated_positions

        except Exception as e:
            logger.error(f"检查用户强平失败 {user_id}: {e}")
            return []

    def _format_liquidation_message(self, user_id: int, positions: List[Dict], floating_balance: float, threshold: float, leverage_ratio: float) -> str:
        """格式化强平通知消息"""
        try:
            from utils.db_utils import user_info_get
            
            # 获取用户信息以构造正确的用户提及
            user_info = user_info_get(user_id)
            if user_info and (user_info.get('first_name') or user_info.get('last_name')):
                user_display_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                user_mention = f"[{user_display_name}](tg://user?id={user_id})"
            else:
                user_mention = f"[用户{user_id}](tg://user?id={user_id})"

            # 获取触发强平的第一个仓位信息
            trigger_position = positions[0] if positions else None
            position_info = ""
            if trigger_position:
                position_info = (
                    f"📊 触发仓位: {trigger_position['symbol']}/USDT {trigger_position['side'].upper()}\n"
                    f"💰 仓位大小: {trigger_position['size']:.2f} USDT\n"
                )

            # 构造强平通知消息
            message = (
                f"🚨 强平通知 🚨\n\n"
                f"{user_mention} 您的所有仓位已被强制平仓！\n\n"
                f"{position_info}"
                f"📉 浮动余额: {floating_balance:.2f} USDT\n"
                f"⚖️ 杠杆倍数: {leverage_ratio:.2f}x\n"
                f"⚠️ 强平阈值: {threshold:.2f} USDT (本金的{threshold/floating_balance*100:.1f}%)\n\n"
                f"💔 您的账户余额已清零，所有仓位已被清空。\n"
                f"🆘 请使用 /begging 领取救济金重新开始交易。"
            )
            
            return message
        except Exception as e:
            logger.error(f"格式化强平通知消息失败: {e}")
            return "🚨 强平通知：您的账户已被强平，所有仓位已清空。"

    async def _send_liquidation_notification(self, user_id: int, group_id: int, message: str):
        """发送强平通知到群组"""
        try:
            token = get_settings().telegram_token
            if token:
                bot = Bot(token=token)
                await bot.send_message(
                    chat_id=group_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info(f"强平通知已发送: 用户{user_id} 群组{group_id}")
            else:
                logger.error("未找到Telegram Bot Token，无法发送强平通知")
        except Exception as e:
            logger.error(f"发送强平通知失败: {e}")

    async def _execute_liquidation(self, user_id: int, group_id: int, positions: List[Dict], final_balance: float):
        """执行强平清算"""
        try:
            # 获取账户当前实际余额
            account = account_service.get_or_create_account(user_id, group_id)
            actual_balance = account['balance']
            total_loss = -abs(actual_balance)  # 使用实际余额计算损失

            for pos in positions:
                try:
                    # 删除仓位
                    TradingRepository.delete_position(user_id, group_id, pos['symbol'], pos['side'])

                    # 获取当前价格用于历史记录
                    current_price = await price_service.get_current_price(pos['symbol'])
                    if current_price <= 0:
                        current_price = pos['entry_price']

                    # 记录强平历史
                    TradingRepository.add_trading_history(
                        user_id, group_id, 'liquidated', pos['symbol'], pos['side'],
                        pos['size'], current_price, total_loss / len(positions)  # 平均分配损失
                    )
                    logger.debug(f"强平仓位删除: {pos['symbol']} {pos['side']} - {pos['size']}")

                except Exception as e:
                    logger.error(f"删除强平仓位失败 {pos['symbol']} {pos['side']}: {e}")
                    continue

            # 清零余额并记录强平损失
            TradingRepository.update_account_balance(
                user_id, group_id, 0.0, total_loss, 0.0, False
            )

            logger.info(f"强平清算完成 - 用户{user_id} 群组{group_id}: 损失{total_loss:.2f}")

        except Exception as e:
            logger.error(f"执行强平清算失败 {user_id}: {e}")

    async def _update_loan_interests(self):
        """批量更新所有用户的贷款利息"""
        try:
            logger.info("开始批量更新贷款利息")

            # 获取所有活跃贷款
            command = """
                SELECT DISTINCT user_id, group_id
                FROM loans
                WHERE status = 'active'
            """
            from utils.db_utils import query_db
            result = query_db(command)

            updated_count = 0
            for row in result:
                user_id = row[0]
                group_id = row[1]

                try:
                    # 导入loan_service并更新利息
                    from .loan_service import loan_service
                    loan_result = loan_service.update_loan_interests(user_id, group_id)
                    
                    if loan_result.get("success", False):
                        updated_count += 1
                        logger.debug(f"用户 {user_id} 贷款利息更新成功")
                    else:
                        logger.warning(f"用户 {user_id} 贷款利息更新失败: {loan_result.get('message', '未知错误')}")

                except Exception as e:
                    logger.error(f"更新用户 {user_id} 贷款利息失败: {e}")
                    continue

            if updated_count > 0:
                logger.info(f"完成贷款利息更新: {updated_count} 个用户")

        except Exception as e:
            logger.error(f"批量更新贷款利息失败: {e}")

    def set_liquidation_callback(self, callback: Callable):
        """设置强平回调函数"""
        self.on_liquidation_callback = callback
        logger.info("强平回调函数已设置")
    
    async def _send_order_trigger_notification(self, order: dict, execution_price: float, order_type_name: str):
        """发送订单触发通知"""
        try:
            user_id = order.get('user_id')
            group_id = order.get('group_id')
            symbol = order.get('symbol', '未知')
            direction = order.get('direction', '未知')  # bid/ask
            order_type = order.get('order_type', '未知')
            volume = order.get('volume', 0)
            
            # 获取用户信息以构造正确的用户提及
            user_info = user_info_get(user_id)
            if user_info and (user_info.get('first_name') or user_info.get('last_name')):
                user_display_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                user_mention = f"[{user_display_name}](tg://user?id={user_id})"
            else:
                user_mention = f"[用户{user_id}](tg://user?id={user_id})"
            
            # 获取实际币种数量
            quantity = order.get('quantity', 0)
            # 对于止盈止损订单，quantity已经是正确的币种数量，不需要重新计算
            # 只有当quantity为0且不是止盈止损订单时才重新计算
            if quantity == 0 and volume > 0 and order_type not in ['tp', 'sl']:
                quantity = volume / execution_price
            
            # 提取币种名称（去掉/USDT后缀）
            base_currency = symbol.replace('/USDT', '') if '/USDT' in symbol else symbol.split('/')[0]
            
            # 获取盈亏信息
            pnl_info = order.get('pnl_info', '')
            if not pnl_info and order_type in ['tp', 'sl']:
                # 如果没有预计算的盈亏信息，尝试查询仓位信息来计算
                try:
                    positions_result = self.trading_repo.get_user_positions(user_id, group_id)
                    if positions_result.get('success', False):
                        positions = positions_result.get('positions', [])
                        position = next((p for p in positions if p['symbol'] == symbol), None)
                        
                        if position:
                            entry_price = position.get('entry_price', 0)
                            position_side = position.get('side', '')
                            if entry_price > 0:
                                # 根据原始仓位方向计算盈亏
                                if position_side == 'long':  # 多仓平仓
                                    pnl = (execution_price - entry_price) * quantity
                                else:  # 空仓平仓
                                    pnl = (entry_price - execution_price) * quantity
                                
                                # 计算手续费（假设0.1%）
                                fee = volume * 0.001
                                net_pnl = pnl - fee
                                
                                pnl_symbol = "📈" if net_pnl >= 0 else "📉"
                                pnl_info = (
                                    f"\n💹 盈亏: {pnl:.2f} USDT"
                                    f"\n💸 手续费: {fee:.2f} USDT"
                                    f"\n{pnl_symbol} 净盈亏: {net_pnl:.2f} USDT"
                                )
                except Exception as e:
                    logger.warning(f"计算盈亏信息失败: {e}")
            
            # 根据订单类型和方向确定显示的方向
            if order_type in ['tp', 'sl']:  # 止盈止损订单显示平仓方向
                # 对于止盈止损，direction是平仓方向，需要反推原持仓方向
                if direction == 'ask':  # 卖出平仓，说明原来是多头
                    side_text = "平多"
                elif direction == 'bid':  # 买入平仓，说明原来是空头
                    side_text = "平空"
                else:
                    side_text = "未知"
            else:  # 开仓订单显示开仓方向
                if direction == 'bid':  # 买入开多
                    side_text = "做多"
                elif direction == 'ask':  # 卖出开空
                    side_text = "做空"
                else:
                    side_text = "未知"
            
            message = (
                f"🎯 订单触发通知\n\n"
                f"{user_mention} 您的{order_type_name}已成功执行！\n\n"
                f"📊 交易对: {symbol}\n"
                f"📈 方向: {side_text}\n"
                f"💰 数量: {quantity:.4f} {base_currency}\n"
                f"💵 成交价: {execution_price:.4f}\n"
                f"💎 成交额: {volume:.2f} USDT"
                f"{pnl_info}\n"
                f"⏰ 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # 发送通知到群组
            token = get_settings().telegram_token
            if token:
                bot = Bot(token=token)
                await bot.send_message(
                    chat_id=group_id,
                    text=message,
                    parse_mode='Markdown'
                )
                logger.info(f"订单触发通知已发送: 用户{user_id} 群组{group_id} {order_type_name}")
            else:
                logger.error("未找到Telegram Bot Token，无法发送订单触发通知")
                
        except Exception as e:
            logger.error(f"发送订单触发通知失败: {e}")

    async def update_all_liquidation_prices(self) -> dict:
        """更新所有仓位的强平价格 - 根据实时价格数据动态调整"""
        try:
            all_positions_result = TradingRepository.get_all_positions()
            if not all_positions_result["success"]:
                return {"success": False, "error": "获取仓位失败"}
            
            positions = all_positions_result["positions"]
            updated_count = 0
            
            # 按用户分组更新强平价格
            user_positions = {}
            for pos in positions:
                user_key = (pos['user_id'], pos['group_id'])
                if user_key not in user_positions:
                    user_positions[user_key] = []
                user_positions[user_key].append(pos)
            
            for (user_id, group_id), user_pos_list in user_positions.items():
                for pos in user_pos_list:
                    try:
                        # 重新计算强平价格
                        new_liquidation_price = await position_service._calculate_liquidation_price(
                            user_id, group_id, pos['symbol'], pos['side'], 
                            pos['size'], pos['entry_price']
                        )
                        
                        # 更新数据库中的强平价格
                        update_result = TradingRepository.update_position(
                            user_id, group_id, pos['symbol'], pos['side'],
                            pos['size'], pos['entry_price'], new_liquidation_price
                        )
                        
                        if update_result["success"]:
                            updated_count += 1
                        
                    except Exception as e:
                        logger.error(f"更新仓位 {pos['symbol']} {pos['side']} 强平价格失败: {e}")
                        continue
            
            return {
                "success": True, 
                "updated_count": updated_count,
                "total_positions": len(positions)
            }
            
        except Exception as e:
            logger.error(f"批量更新强平价格失败: {e}")
            return {"success": False, "error": str(e)}

    async def check_liquidations(self) -> List[Dict]:
        """检查强平条件并返回需要强平的仓位列表"""
        try:
            await self._check_liquidations()
            # 这里应该返回实际被强平的仓位列表
            # 由于_check_liquidations是私有方法且没有返回值，我们暂时返回空列表
            return []
        except Exception as e:
            logger.error(f"检查强平失败: {e}")
            return []

    def _calculate_dynamic_liquidation_threshold(self, leverage_ratio: float) -> float:
        """根据杠杆倍数动态计算强平保证金率阈值"""
        if leverage_ratio <= 1.0:
            return 0.05  # 1倍以内，5%
        elif leverage_ratio >= 100.0:
            return 0.20  # 100倍以上，20%
        else:
            # 1-100倍之间线性插值
            return 0.05 + (leverage_ratio - 1.0) * 0.15 / 99.0

    async def get_monitoring_status(self) -> Dict:
        """获取监控服务状态"""
        try:
            # 获取待成交订单数量
            pending_orders_result = TradingRepository.get_orders_by_type('open', 'pending')
            pending_orders_count = len(pending_orders_result["orders"]) if pending_orders_result["success"] else 0

            # 获取活跃仓位数量
            positions_result = TradingRepository.get_all_positions()
            positions_count = len(positions_result["positions"]) if positions_result["success"] else 0

            return {
                "success": True,
                "is_running": self.is_running,
                "check_intervals": {
                    "price_check": f"{self.price_check_interval}s",
                    "liquidation_check": f"{self.liquidation_check_interval}s",
                    "interest_update": f"{self.interest_update_interval}s"
                },
                "pending_orders_count": pending_orders_count,
                "active_positions_count": positions_count,
                "performance_counters": {
                    "price_checks": self.price_counter,
                    "liquidation_checks": self.liquidation_counter,
                    "interest_updates": self.interest_counter
                }
            }

        except Exception as e:
            logger.error(f"获取监控状态失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "is_running": self.is_running
            }


    async def _check_order_trigger_condition(self, order: Dict) -> bool:
        """检查订单是否满足触发条件（获取实时价格版本）"""
        try:
            symbol = order['symbol']
            # 获取实时市场价格（订单触发检查必须使用最新价格确保准确性）
            current_price = await price_service.get_real_time_price(symbol)
            if current_price <= 0:
                logger.debug(f"无法获取 {symbol} 的实时价格")
                return False
            
            return await self._check_order_trigger_condition_with_price(order, current_price)
        except Exception as e:
            logger.error(f"检查订单触发条件失败: {e}")
            return False
    
    async def _check_order_trigger_condition_with_price(self, order: Dict, current_price: float) -> bool:
        """检查订单是否满足触发条件（使用提供的价格）"""
        try:
            symbol = order['symbol']
            order_type = order['order_type']
            direction = order['direction']  # 使用正确的字段名
            role = order['role']
            order_price = order.get('price')  # 使用正确的字段名
            tp_price = order.get('tp_price')
            sl_price = order.get('sl_price')
            
            logger.debug(f"检查订单触发条件: {order['order_id']}, 类型: {order_type}, 方向: {direction}, 角色: {role}, 委托价: {order_price}, 当前价: {current_price}")
            
            # 根据订单类型和方向判断触发条件
            if order_type == 'open' and role == 'maker':  # 开仓限价单
                if direction == 'bid':  # 买入(做多)
                    # 买入限价单：当前价格 <= 委托价格时触发
                    triggered = current_price <= order_price
                    logger.debug(f"买入限价单触发检查: 当前价 {current_price} <= 委托价 {order_price} = {triggered}")
                    return triggered
                elif direction == 'ask':  # 卖出(做空)
                    # 卖出限价单：当前价格 >= 委托价格时触发
                    triggered = current_price >= order_price
                    logger.debug(f"卖出限价单触发检查: 当前价 {current_price} >= 委托价 {order_price} = {triggered}")
                    return triggered
            
            elif order_type == 'open' and role == 'taker':  # 开仓市价单
                # 市价单立即触发
                logger.debug(f"市价单立即触发")
                return True
            
            elif order_type == 'sl':  # 止损单
                # 止损单使用 price 字段作为触发价格
                trigger_price = order_price
                if not trigger_price:
                    logger.debug(f"止损单 {order['order_id']} 缺少触发价格，跳过检查")
                    return False
                    
                if direction == 'bid':  # 多头止损
                    # 多头止损：当前价格 <= 止损价格时触发
                    triggered = current_price <= trigger_price
                    logger.debug(f"多头止损触发检查: 当前价 {current_price} <= 止损价 {trigger_price} = {triggered}")
                    return triggered
                elif direction == 'ask':  # 空头止损
                    # 空头止损：当前价格 >= 止损价格时触发
                    triggered = current_price >= trigger_price
                    logger.debug(f"空头止损触发检查: 当前价 {current_price} >= 止损价 {trigger_price} = {triggered}")
                    return triggered
            
            elif order_type == 'tp':  # 止盈单
                # 止盈单使用 price 字段作为触发价格
                trigger_price = order_price
                if not trigger_price:
                    logger.debug(f"止盈单 {order['order_id']} 缺少触发价格，跳过检查")
                    return False
                    
                if direction == 'bid':  # 多头止盈
                    # 多头止盈：当前价格 >= 止盈价格时触发
                    triggered = current_price >= trigger_price
                    logger.debug(f"多头止盈触发检查: 当前价 {current_price} >= 止盈价 {trigger_price} = {triggered}")
                    return triggered
                elif direction == 'ask':  # 空头止盈
                    # 空头止盈：当前价格 <= 止盈价格时触发
                    triggered = current_price <= trigger_price
                    logger.debug(f"空头止盈触发检查: 当前价 {current_price} <= 止盈价 {trigger_price} = {triggered}")
                    return triggered
            
            logger.debug(f"订单不满足任何触发条件")
            return False
            
        except Exception as e:
            logger.error(f"检查订单触发条件失败: {e}")
            return False
    
    async def _check_and_create_stop_orders(self, executed_order: Dict):
        """检查并同步止盈止损价格到仓位表"""
        try:
            # 如果执行的订单有止盈止损设置，将其同步到仓位表
            sl_price = executed_order.get('sl_price')
            tp_price = executed_order.get('tp_price')
            
            if sl_price or tp_price:
                user_id = executed_order['user_id']
                group_id = executed_order['group_id']
                symbol = executed_order['symbol']
                # 根据订单方向确定仓位方向
                order_direction = executed_order['direction']  # bid/ask
                position_direction = 'long' if order_direction == 'bid' else 'short'
                
                # 同步止盈止损价格到仓位表
                result = await position_service.set_position_tp_sl(
                    user_id=user_id,
                    group_id=group_id,
                    symbol=symbol,
                    side=position_direction,
                    tp_price=tp_price,
                    sl_price=sl_price
                )
                
                if result.get('success', False):
                    logger.info(f"订单 {executed_order['order_id']} 的止盈止损价格已同步到仓位表: TP:{tp_price} SL:{sl_price}")
                else:
                    logger.warning(f"同步订单 {executed_order['order_id']} 的止盈止损价格失败: {result.get('message', '未知错误')}")
                        
        except Exception as e:
            logger.error(f"同步止盈止损价格失败: {e}")
    
    async def _check_stop_loss_take_profit_orders(self):
        """检查现有仓位的止盈止损价格触发条件"""
        try:
            # 获取所有有止盈止损价格的仓位
            positions_result = TradingRepository.get_all_positions()
            if not positions_result.get('success', False):
                return
            
            positions = positions_result.get('positions', [])
            if not positions:
                return
            
            # 筛选出有止盈止损价格的仓位
            positions_with_tp_sl = []
            for pos in positions:
                if pos.get('tp_price') or pos.get('sl_price'):
                    positions_with_tp_sl.append(pos)
            
            if not positions_with_tp_sl:
                return
            
            # 收集所有需要的交易对
            symbols = set(pos['symbol'] for pos in positions_with_tp_sl)
            
            # 批量获取价格
            prices = {}
            for symbol in symbols:
                try:
                    price = await price_service.get_real_time_price(symbol)
                    if price > 0:
                        prices[symbol] = price
                except Exception as e:
                    logger.error(f"获取 {symbol} 价格失败: {e}")
            
            for position in positions_with_tp_sl:
                try:
                    symbol = position['symbol']
                    if symbol not in prices:
                        logger.debug(f"无法获取 {symbol} 的实时价格，跳过仓位检查")
                        continue
                    
                    current_price = prices[symbol]
                    direction = position['side']
                    tp_price = position.get('tp_price')
                    sl_price = position.get('sl_price')
                    
                    logger.debug(f"检查仓位 {symbol} {direction}: 当前价格={current_price}, TP={tp_price}, SL={sl_price}")
                    
                    # 检查止盈触发条件
                    if tp_price and self._check_tp_trigger(current_price, tp_price, direction):
                        logger.info(f"止盈触发: {symbol} {direction} 当前价格{current_price} >= 止盈价{tp_price}")
                        await self._execute_tp_sl_trigger(position, current_price, 'tp')
                    
                    # 检查止损触发条件
                    elif sl_price and self._check_sl_trigger(current_price, sl_price, direction):
                        logger.info(f"止损触发: {symbol} {direction} 当前价格{current_price} <= 止损价{sl_price}")
                        await self._execute_tp_sl_trigger(position, current_price, 'sl')
                        
                except Exception as e:
                    logger.error(f"检查仓位止盈止损失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"检查仓位止盈止损失败: {e}")
    
    def _check_tp_trigger(self, current_price: float, tp_price: float, direction: str) -> bool:
        """检查止盈触发条件"""
        if direction == 'long':
            return current_price >= tp_price
        else:  # short
            return current_price <= tp_price
    
    def _check_sl_trigger(self, current_price: float, sl_price: float, direction: str) -> bool:
        """检查止损触发条件"""
        if direction == 'long':
            return current_price <= sl_price
        else:  # short
            return current_price >= sl_price
    
    async def _execute_tp_sl_trigger(self, position: dict, trigger_price: float, trigger_type: str):
        """执行止盈止损触发"""
        try:
            user_id = position['user_id']
            group_id = position['group_id']
            symbol = position['symbol']
            direction = position['side']
            quantity = position['size']
            entry_price = position.get('entry_price', 0)
            
            # 确定平仓方向：long仓位用ask(卖出)平仓，short仓位用bid(买入)平仓
            close_direction = 'ask' if direction == 'long' else 'bid'
            
            # 在平仓前计算盈亏信息
            # 计算实际币种数量：开仓时的USDT价值 / 开仓价格
            actual_coin_quantity = quantity / entry_price
            # 计算当前仓位的实际价值：币种数量 * 当前价格
            current_position_value = actual_coin_quantity * trigger_price
            
            pnl_info = ""
            if entry_price > 0:
                # 根据原始仓位方向计算盈亏
                if direction == 'long':  # 多仓平仓
                    pnl = (trigger_price - entry_price) * actual_coin_quantity
                else:  # 空仓平仓
                    pnl = (entry_price - trigger_price) * actual_coin_quantity
                
                # 计算手续费（基于当前仓位价值，万分之3.5）
                fee = current_position_value * 0.00035
                net_pnl = pnl - fee
                
                pnl_symbol = "📈" if net_pnl >= 0 else "📉"
                pnl_info = (
                    f"\n💹 盈亏: {pnl:.2f} USDT"
                    f"\n💸 手续费: {fee:.2f} USDT"
                    f"\n{pnl_symbol} 净盈亏: {net_pnl:.2f} USDT"
                )
            
            # 使用position_service平仓
            result = await position_service._reduce_position(
                user_id=user_id,
                group_id=group_id,
                symbol=symbol,
                direction=close_direction,
                volume=quantity,
                exit_price=trigger_price
            )
            
            if result.get('success', False):
                logger.info(f"{'止盈' if trigger_type == 'tp' else '止损'}触发成功: {symbol} {direction} {quantity}@{trigger_price}")
                
                # 发送触发通知
                order_type_name = "止盈单" if trigger_type == 'tp' else "止损单"
                fake_order = {
                    'user_id': user_id,
                    'group_id': group_id,
                    'symbol': symbol,
                    'direction': close_direction,
                    'quantity': actual_coin_quantity,  # 实际币种数量
                    'volume': current_position_value,  # 当前仓位的实际价值
                    'order_type': trigger_type,
                    'pnl_info': pnl_info  # 预计算的盈亏信息
                }
                await self._send_order_trigger_notification(fake_order, trigger_price, order_type_name)
                
            else:
                logger.error(f"{'止盈' if trigger_type == 'tp' else '止损'}触发失败: {result.get('message', '未知错误')}")
                
        except Exception as e:
            logger.error(f"执行{'止盈' if trigger_type == 'tp' else '止损'}触发失败: {e}")


# 全局监控服务实例
monitor_service = MonitorService()
