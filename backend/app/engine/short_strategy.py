"""
做空策略 (统一版本)
父单元格 = SELL, 子单元格 = BUY
"""

from app.constants import TradeSide
from app.engine.base_strategy import BaseGridStrategy


class ShortStrategy(BaseGridStrategy):
    """
    做空网格策略

    - 主方向: 卖出 (价格从高到低找最近的)
    - 次方向: 买入 (价格从低到高找最近的)
    """

    strategy_type = 'SHORT'
    parent_cell_type = 'SELL'
    child_cell_type = 'BUY'
    trade_side_primary = TradeSide.SELL
    trade_side_secondary = TradeSide.BUY
    primary_sort_asc = False   # 卖出: 价格高优先
    secondary_sort_asc = True  # 买入: 价格低优先

    def _get_primary_count(self):
        return self.stock_config.get('sell_cell_count', 3)

    def _get_secondary_count(self):
        return self.stock_config.get('buy_cell_count', 3)

    def _primary_price_out_of_scope(self, records, cur_price, scope):
        """卖出订单偏离: 当前价远低于卖出价 → 撤单"""
        return (records['price'] - cur_price) > scope

    def _secondary_price_out_of_scope(self, records, cur_price, scope):
        """买入订单偏离: 当前价远高于买入价 → 撤单"""
        return (cur_price - records['price']) > scope
