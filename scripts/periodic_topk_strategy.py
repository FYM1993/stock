#!/usr/bin/env python3
"""
周期调仓策略
============

继承 Qlib 的 TopkDropoutStrategy，增加 hold_days 参数：
只有每隔 N 个交易日才执行调仓，其余时间持仓不动。

配置方式（config.yaml）:

  strategy:
    class: "PeriodicTopkStrategy"
    module_path: "periodic_topk_strategy"
    kwargs:
      signal: "<PRED>"
      topk: 30
      n_drop: 5
      hold_days: 5       # ← 每5个交易日调仓一次
"""

import copy
import numpy as np
import pandas as pd

from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
from qlib.backtest.position import Position
from qlib.backtest.decision import Order, OrderDir, TradeDecisionWO


class PeriodicTopkStrategy(TopkDropoutStrategy):
    """
    定期调仓的 TopK 策略
    
    继承 TopkDropoutStrategy，增加 hold_days 参数。
    只有每 hold_days 个交易日才执行调仓，其余交易日返回空决策（持仓不动）。
    """

    def __init__(self, *, hold_days=5, **kwargs):
        """
        Parameters
        ----------
        hold_days : int
            调仓间隔（交易日）。例如 hold_days=5 表示每5个交易日调仓一次。
            首个交易日（trade_step=0）一定会调仓。
        其他参数同 TopkDropoutStrategy:
            topk, n_drop, method_sell, method_buy, hold_thresh,
            only_tradable, forbid_all_trade_at_limit
        """
        super().__init__(**kwargs)
        self.hold_days = hold_days

    def generate_trade_decision(self, execute_result=None):
        """
        重写调仓逻辑：只在调仓日执行，其他日期返回空决策。
        """
        trade_step = self.trade_calendar.get_trade_step()

        # 判断今天是否是调仓日
        # trade_step=0 是第一个交易日，必定调仓
        # 之后每 hold_days 个交易日调仓一次
        if trade_step % self.hold_days != 0:
            # 非调仓日，不做任何操作，持有现有仓位
            return TradeDecisionWO([], self)

        # 调仓日，执行父类的原始逻辑
        return super().generate_trade_decision(execute_result)
