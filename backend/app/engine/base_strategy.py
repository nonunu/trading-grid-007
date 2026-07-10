"""
网格交易基础策略类 (统一版本, 1:N)
券商无关 - 通过 BrokerClient 接口下单/撤单
"""

import logging
import threading
import pandas as pd
from datetime import datetime

from app.constants import (
    SUBMITTED, FILLED_ALL, FILLED_PART,
    CANCELLED_ALL, CANCELLED_PART, FAILED,
    SUCCESS, TERMINAL, SUBMITTED_SET, TradeSide,
)
from app.brokers.base import BrokerClient
from app.engine.grid import DatabaseGrid

logger = logging.getLogger(__name__)


class BaseGridStrategy:
    """
    网格交易基础策略类

    子类设置以下类属性定义具体策略:
    - strategy_type: 'MULTI' or 'SHORT'
    - parent_cell_type: 父单元格类型 ('BUY' or 'SELL')
    - child_cell_type: 子单元格类型 ('SELL' or 'BUY')
    - trade_side_primary: 主交易方向 ('BUY' or 'SELL')
    - trade_side_secondary: 次交易方向 ('SELL' or 'BUY')
    - primary_sort_asc: 主交易排序方向
    - secondary_sort_asc: 次交易排序方向
    """

    strategy_type = None
    parent_cell_type = None
    child_cell_type = None
    trade_side_primary = None
    trade_side_secondary = None
    primary_sort_asc = True
    secondary_sort_asc = True

    def __init__(self, code: str, grid: DatabaseGrid,
                 broker: BrokerClient,
                 stock_config: dict = None,
                 stock_lock=None):
        self.code = code
        self.grid = grid
        self.broker = broker
        self.stock_config = stock_config or {}
        self._lock = stock_lock or threading.RLock()

    # ==================== 查询未完成订单 ====================

    def query_local_unfinished_records(self):
        """查询本地未完成的单元格"""
        return self.grid.data[
            (~self.grid.data['order_status'].isnull()) &
            (~self.grid.data['order_status'].isin(TERMINAL))
        ]

    # ==================== 撤单逻辑 ====================

    def cancel_order(self, cur_price, place_order_scope):
        """撤销超出范围的订单"""
        condition = (
            (self.grid.data['order_status'].isin(SUBMITTED_SET)) &
            (~self.grid.data['order_id'].isnull())
        )
        records = self.grid.query_records(condition)

        primary_orders = records[
            (records['cell_type'] == self.parent_cell_type) &
            (self._primary_price_out_of_scope(records, cur_price, place_order_scope))
        ]
        secondary_orders = records[
            (records['cell_type'] == self.child_cell_type) &
            (self._secondary_price_out_of_scope(records, cur_price, place_order_scope))
        ]

        self._cancel_orders_batch(primary_orders, self.parent_cell_type)
        self._cancel_orders_batch(secondary_orders, self.child_cell_type)

    def _primary_price_out_of_scope(self, records, cur_price, place_order_scope):
        raise NotImplementedError

    def _secondary_price_out_of_scope(self, records, cur_price, place_order_scope):
        raise NotImplementedError

    def _cancel_orders_batch(self, orders, cell_type):
        """批量撤销订单"""
        if len(orders) == 0:
            return
        for row in orders.to_dict('records'):
            order_id = row['order_id']
            cell_id = row['id']

            # 再次确认当前状态仍为 SUBMITTED（防止并发回调已更新状态）
            current = self.grid.get_one_record(self.grid.data['id'] == cell_id)
            if current is None:
                continue
            current_status = current.get('order_status')
            if current_status not in SUBMITTED_SET:
                # 状态已变（可能订单回调已处理），跳过撤单
                continue

            try:
                success = self.broker.cancel_order(str(order_id))
                if success:
                    logger.info(f"{self.code} 撤单 {cell_type} price={row['price']}")
                else:
                    # 券商说撤单失败（已撤/已成交），清除本地状态
                    condition = self.grid.data['id'] == cell_id
                    self.grid.clear_record_order_info(condition)
                    logger.debug(f"{self.code} 撤单 {cell_type} price={row['price']} "
                                 f"券商返回失败，已重置本地状态")
            except Exception as e:
                logger.warning(f"{self.code} 撤单异常 price={row['price']}: {e}")

    # ==================== 核心策略逻辑 ====================

    def run_strategy(self, cur_price):
        """运行网格策略 (内部加锁保护)"""
        with self._lock:
            return self._run_strategy_impl(cur_price)

    def _run_strategy_impl(self, cur_price):
        """策略实际执行逻辑，返回 (买单下单数, 卖单下单数) 用于外部日志合并"""
        if not self.broker.is_trading_time():
            return None  # 非交易时间

        place_order_scope = self.stock_config.get('place_order_scope', 0.1)
        buy_placed = 0
        sell_placed = 0

        # ===== 主交易 (父单元格) =====
        primary_condition = (
            (self.grid.data['cell_type'] == self.parent_cell_type) &
            (self.grid.data['parent_cell_id'].isna()) &
            (self.grid.data['order_id'].isnull())
        )
        primary_records = self.grid.query_records(primary_condition)

        if len(primary_records) == 0 and len(self.grid.data) > 0:
            # 诊断: 为什么没有可下单的父单元格
            all_parents = self.grid.data[
                (self.grid.data['cell_type'] == self.parent_cell_type) &
                (self.grid.data['parent_cell_id'].isna())
            ]
            has_order = all_parents[all_parents['order_id'].notna()]
            if len(all_parents) > 0 and len(has_order) < len(all_parents):
                # 有未下单的父单元格但不满足条件，才打印诊断
                logger.debug(
                    f"{self.code} {self.strategy_type} 主交易无候选: "
                    f"grid总行数={len(self.grid.data)}, "
                    f"{self.parent_cell_type}父单元格={len(all_parents)}, "
                    f"已有订单={len(has_order)}"
                )

        # 先过滤 scope 范围内，再排序取前 N 个
        if len(primary_records) > 0:
            in_scope = primary_records[
                (primary_records['price'] - cur_price).abs() <= place_order_scope
            ].sort_values('price', ascending=self.primary_sort_asc
            ).head(self._get_primary_count())

            for row in in_scope.to_dict('records'):
                self._place_order(row, is_primary=True)
                if self.trade_side_primary == TradeSide.BUY:
                    buy_placed += 1
                else:
                    sell_placed += 1

        # ===== 次交易 (子单元格) =====
        parent_success = self.grid.data[
            (self.grid.data['cell_type'] == self.parent_cell_type) &
            (self.grid.data['parent_cell_id'].isna()) &
            (self.grid.data['order_status'].isin(SUCCESS))
        ]
        success_parent_ids = set(parent_success['id'].tolist())
        parent_dealt_map = dict(
            zip(parent_success['id'], parent_success['dealt_qty'].fillna(0))
        )

        secondary_condition = (
            (self.grid.data['cell_type'] == self.child_cell_type) &
            (self.grid.data['order_id'].isnull())
        )
        secondary_candidates = self.grid.query_records(secondary_condition)
        all_child_count = len(secondary_candidates)

        if len(secondary_candidates) > 0:
            # 过滤: 父单元格必须在 SUCCESS 状态
            secondary_candidates = secondary_candidates[
                secondary_candidates['parent_cell_id'].isin(success_parent_ids)
            ]
            parent_matched_count = len(secondary_candidates)

            valid_rows = []
            for row in secondary_candidates.to_dict('records'):
                parent_id = row['parent_cell_id']
                parent_dealt_qty = parent_dealt_map.get(parent_id, 0)
                if row['qty'] <= parent_dealt_qty:
                    valid_rows.append(row)

            valid_df = pd.DataFrame(valid_rows)
            skipped_scope = 0
            if len(valid_df) > 0:
                # 先过滤 scope 范围内，再排序取前 N 个
                in_scope_df = valid_df[
                    (valid_df['price'] - cur_price).abs() <= place_order_scope
                ].sort_values('price', ascending=self.secondary_sort_asc
                ).head(self._get_secondary_count())

                for row in in_scope_df.to_dict('records'):
                    self._place_order(row, is_primary=False)
                    if self.trade_side_secondary == TradeSide.BUY:
                        buy_placed += 1
                    else:
                        sell_placed += 1

                skipped_scope = len(valid_df) - len(in_scope_df)

            # 诊断: 如果有子单元格但没有下单，输出原因
            if (buy_placed + sell_placed) == 0 and all_child_count > 0:
                logger.debug(
                    f"{self.code} {self.strategy_type} 子单元格未下单诊断: "
                    f"待下子单元格={all_child_count}, "
                    f"父成交匹配={parent_matched_count}, "
                    f"qty有效={len(valid_rows)}, "
                    f"scope内={len(valid_df) - skipped_scope if len(valid_df) > 0 else 0}, "
                    f"scope外跳过={skipped_scope}"
                )

        # 撤单
        self.cancel_order(cur_price, place_order_scope)
        return (buy_placed, sell_placed)

    def _get_primary_count(self):
        raise NotImplementedError

    def _get_secondary_count(self):
        raise NotImplementedError

    # ==================== 下单逻辑 ====================

    def _place_order(self, row, is_primary: bool):
        """下单 (统一通过 broker 接口)"""
        price = row['price']
        qty = int(row['qty'])

        # 次交易时数量不超过父单元格实际成交量
        if not is_primary:
            parent_id = row.get('parent_cell_id')
            if parent_id and not pd.isna(parent_id):
                parent = self.grid.db.load_cell_by_id(int(parent_id))
                if parent:
                    parent_dealt_qty = int(parent.get('dealt_qty', 0) or 0)
                    qty = min(qty, parent_dealt_qty)

        if qty <= 0:
            logger.warning(f"place_order skip: qty=0, cell_id={row['id']}")
            return

        side = self.trade_side_primary if is_primary else self.trade_side_secondary
        remark = self.strategy_type

        order_id = self.broker.place_order(
            stock_code=self.code,
            side=side,
            price=price,
            qty=qty,
            remark=remark,
        )

        if order_id:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cell_id = row['id']
            condition = self.grid.data['id'] == cell_id
            self.grid.update_records(
                condition,
                ['order_id', 'order_status', 'create_time'],
                [order_id, SUBMITTED, now]
            )
        else:
            logger.error(f"{self.code} 下单失败: {side} price={price} qty={qty}")

    # ==================== 订单状态处理 ====================

    def process_order_status(self, order_info: dict) -> str:
        """
        处理订单状态更新 (由引擎的订单回调调用)

        Args:
            order_info: {order_id, order_status, dealt_avg_price, dealt_qty, ...}

        Returns:
            处理日志
        """
        order_id = order_info.get('order_id')
        if not order_id:
            return "no order_id"

        # 在本策略的 grid 中查找该订单
        condition = self.grid.data['order_id'] == str(order_id)
        record = self.grid.get_one_record(condition)
        if record is None:
            return "not found"

        cell_id = record['id']
        cell_type = record['cell_type']
        price = record.get('price', 0)
        status = order_info['order_status']
        is_child = not pd.isna(record.get('parent_cell_id', None))

        if status in SUBMITTED_SET:
            return self._on_order_submitted(order_info, cell_id, cell_type, price)
        elif status == FILLED_PART:
            return self._on_order_filled_part(order_info, cell_id, cell_type, price)
        elif status == FILLED_ALL:
            if is_child:
                return self._on_secondary_filled_all(order_info, cell_id)
            else:
                return self._on_order_success(order_info, cell_id, cell_type, price)
        elif status == CANCELLED_PART:
            if is_child:
                return self._on_secondary_cancelled_part(order_info, cell_id)
            else:
                return self._on_order_success(order_info, cell_id, cell_type, price)
        elif status in {CANCELLED_ALL, FAILED}:
            return self._on_order_failed(cell_id, cell_type, price)
        else:
            return f"unknown status: {status}"

    def _on_order_submitted(self, order, cell_id, cell_type, price):
        condition = self.grid.data['id'] == cell_id
        record = self.grid.get_one_record(condition)
        if record is None:
            return "record not found"
        if order.get('order_status') == record.get('order_status'):
            return "status no change"
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.grid.update_records(
            condition,
            ['order_status', 'updated_time'],
            [order['order_status'], now]
        )
        return f"{cell_type} price={price}: {record.get('order_status')}->{order['order_status']}"

    def _on_order_filled_part(self, order, cell_id, cell_type, price):
        condition = self.grid.data['id'] == cell_id
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.grid.update_records(
            condition,
            ['order_status', 'dealt_avg_price', 'dealt_qty', 'updated_time'],
            [order['order_status'], order.get('dealt_avg_price'),
             order.get('dealt_qty'), now]
        )
        return f"{cell_type} price={price}: FILLED_PART qty={order.get('dealt_qty')}"

    def _on_order_success(self, order, cell_id, cell_type, price):
        condition = self.grid.data['id'] == cell_id
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.grid.update_records(
            condition,
            ['order_status', 'dealt_avg_price', 'dealt_qty', 'updated_time'],
            [order['order_status'], order.get('dealt_avg_price'),
             order.get('dealt_qty'), now]
        )
        return f"{cell_type} price={price}: SUCCESS -> trigger run_strategy"

    def _on_order_failed(self, cell_id, cell_type, price):
        condition = self.grid.data['id'] == cell_id
        self.grid.clear_record_order_info(condition)
        return f"{cell_type} price={price}: FAILED -> reset"

    def _on_secondary_filled_all(self, order, cell_id):
        """子单元格全部成交"""
        condition = self.grid.data['id'] == cell_id
        record = self.grid.get_one_record(condition)
        if record is None:
            return "record not found"

        record_dict = record.to_dict() if hasattr(record, 'to_dict') else dict(record)
        record_dict['order_status'] = order['order_status']
        record_dict['dealt_avg_price'] = order.get('dealt_avg_price')
        record_dict['dealt_qty'] = order.get('dealt_qty')
        record_dict['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            self.grid.save_filled_orders(record_dict)
        except Exception as e:
            logger.error(f"保存 filled_order 失败(cell_id={cell_id}): {e}")

        self.grid.clear_record_order_info(condition)

        # 检查兄弟单元格是否都完成
        parent_id = record_dict.get('parent_cell_id')
        if parent_id and not pd.isna(parent_id):
            siblings = self.grid.get_child_cells(int(parent_id))
            unfinished = siblings[
                (~siblings['order_status'].isnull()) &
                (~siblings['order_status'].isin([FILLED_ALL]))
            ]
            if len(unfinished) == 0:
                parent_cond = self.grid.data['id'] == int(parent_id)
                self.grid.clear_record_order_info(parent_cond)

        return f"{record_dict.get('cell_type', '')} price={record_dict.get('price', 0)}: 成交完成, 已保存记录"

    def _on_secondary_cancelled_part(self, order, cell_id):
        """子单元格部分成交后撤单"""
        condition = self.grid.data['id'] == cell_id
        record = self.grid.get_one_record(condition)
        if record is None:
            return "record not found"

        record_dict = record.to_dict() if hasattr(record, 'to_dict') else dict(record)
        record_dict['order_status'] = order['order_status']
        record_dict['dealt_avg_price'] = order.get('dealt_avg_price')
        record_dict['dealt_qty'] = order.get('dealt_qty')
        record_dict['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            self.grid.save_filled_orders(record_dict)
        except Exception as e:
            logger.error(f"保存 filled_order 失败(cell_id={cell_id}): {e}")

        self.grid.clear_record_order_info(condition)
        return f"secondary CANCELLED_PART, saved record"

    # ==================== 初始化订单核对 ====================

    def init_grid_orders(self, order_dict: dict) -> str:
        """
        初始化时核对本地 grid 与券商订单状态

        Args:
            order_dict: {order_id: order_info} 从券商查询得到
        """
        unfinished = self.query_local_unfinished_records()
        log = f"{self.strategy_type} unfinished={len(unfinished)}"

        if len(unfinished) == 0 or not order_dict:
            return log

        for _, row in unfinished.iterrows():
            order_id = row.get('order_id')
            if not order_id or str(order_id) not in order_dict:
                continue

            broker_order = order_dict[str(order_id)]
            broker_status = broker_order.get('order_status')
            local_status = row.get('order_status')

            if broker_status != local_status:
                result = self.process_order_status(broker_order)
                log = f"{log} | {order_id}:{result}"

        return log
