"""
最小化测试策略

直接copy Qlib官方的Order创建方式
"""

from qlib.strategy.base import BaseStrategy
from qlib.backtest import Order
from qlib.backtest.decision import OrderDir, TradeDecisionWO
import pandas as pd
from loguru import logger


class MinimalTestStrategy(BaseStrategy):
    """最小化测试策略 - 每天买一只固定股票"""
    
    def generate_trade_decision(self, execute_result=None):
        """
        每天都买000001.SZ（平安银行）
        """
        # 获取当前日期
        trade_step = self.trade_calendar.get_trade_step()
        current_date = self.trade_calendar.get_step_time(trade_step)
        if isinstance(current_date, tuple):
            current_date = current_date[0]
        date_str = pd.Timestamp(current_date).strftime('%Y-%m-%d')
        
        logger.info(f"日期: {date_str}")
        
        # ✅ 正确方式：从self.trade_position获取持仓
        current_positions = {}
        if hasattr(self, 'trade_position') and self.trade_position is not None:
            current_positions = dict(self.trade_position.position)
            logger.info(f"当前持仓（from trade_position）: {current_positions}")
        else:
            logger.warning("trade_position未初始化！")
        
        orders = []
        
        # 如果还没持仓，就买入
        if "000001.SZ" not in current_positions or current_positions.get("000001.SZ", 0) == 0:
            # 使用官方方式：通过trade_exchange获取价格
            if hasattr(self, 'trade_exchange') and self.trade_exchange is not None:
                try:
                    start_time = pd.Timestamp(date_str)
                    end_time = start_time + pd.Timedelta(days=1)
                    
                    # 检查是否可交易
                    if self.trade_exchange.is_stock_tradable(
                        stock_id="000001.SZ",
                        start_time=start_time,
                        end_time=end_time,
                        direction=OrderDir.BUY
                    ):
                        # 获取价格
                        price = self.trade_exchange.get_deal_price(
                            stock_id="000001.SZ",
                            start_time=start_time,
                            end_time=end_time,
                            direction=OrderDir.BUY
                        )
                        
                        if price > 0:
                            # 买3万元的股票
                            shares = 30000 / price
                            shares = int(shares / 100) * 100  # 取整到100股
                            
                            if shares >= 100:
                                order = Order(
                                    stock_id="000001.SZ",
                                    amount=shares,
                                    direction=Order.BUY,
                                    start_time=start_time,
                                    end_time=end_time
                                )
                                orders.append(order)
                                logger.info(f"✅ 买入: 000001.SZ, 价格={price:.2f}, 股数={shares}")
                            else:
                                logger.warning(f"股数不足100: {shares}")
                        else:
                            logger.warning(f"价格无效: {price}")
                    else:
                        logger.warning("股票不可交易")
                        
                except Exception as e:
                    logger.error(f"获取交易信息失败: {e}")
            else:
                logger.warning("trade_exchange未初始化！")
        
        logger.info(f"生成订单数: {len(orders)}")
        
        return TradeDecisionWO(orders, self)
