"""
网格交易数据管理类 (统一版本, 1:N)
基于 SQLite 的网格数据管理，支持 1:N 买卖比模型
券商无关 - 通过 BrokerClient 接口交互
"""

import pandas as pd
import numpy as np
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DatabaseGrid:
    """
    基于 SQLite 的网格数据管理类 (1:N 版本)

    数据模型：
    - 每个单元格是一行，有 cell_type ('BUY'/'SELL') 和 parent_cell_id
    - 做多(MULTI): 买入单元格是父，卖出单元格是子
    - 做空(SHORT): 卖出单元格是父，买入单元格是子
    """

    def __init__(self, db, stock_code: str, strategy_type: str):
        self.db = db
        self.stock_code = stock_code
        self.strategy_type = strategy_type
        self.data = self.db.load_cells(stock_code, strategy_type)
        self.is_modified = False

    # ==================== 核心查询方法 ====================

    def query_records(self, condition):
        """查询记录"""
        return self.data[condition]

    def get_one_record(self, condition):
        """获取单条记录"""
        filtered = self.data[condition]
        if len(filtered) > 0:
            return filtered.iloc[0]
        return None

    # ==================== 更新方法 ====================

    def update_records(self, condition, cols, cols_val):
        """更新记录 - 先更新内存 DataFrame，再持久化"""
        self.is_modified = True
        updated_rows = self.data[condition]
        self.data.loc[condition, cols] = cols_val

        if len(updated_rows) > 0:
            self._persist_updates(cols, cols_val, updated_rows)

    def _persist_updates(self, cols: list, cols_val: list,
                         updated_rows: pd.DataFrame):
        """将更新持久化到数据库"""
        try:
            for _, row in updated_rows.iterrows():
                cell_id = row['id']
                fields_to_update = {}
                for col, val in zip(cols, cols_val):
                    if col == 'id':
                        continue
                    if isinstance(val, float) and pd.isna(val):
                        val = None
                    fields_to_update[col] = val
                if fields_to_update:
                    self.db.update_cell_fields(cell_id, fields_to_update)
        except Exception as e:
            logger.error(f"Failed to persist updates: {e}")
            raise

    def update_cell(self, cell_id: int, fields: Dict[str, Any]):
        """直接通过 cell_id 更新单元格"""
        self.is_modified = True
        condition = self.data['id'] == cell_id
        for col, val in fields.items():
            self.data.loc[condition, col] = val
        self.db.update_cell_fields(cell_id, fields)

    # ==================== 清空订单信息 ====================

    def clear_record_order_info(self, condition):
        """清空单元格的订单信息"""
        cols = ['order_status', 'order_id', 'dealt_avg_price',
                'dealt_qty', 'create_time', 'updated_time']
        cols_val = [None, None, np.nan, 0, None, None]
        self.update_records(condition, cols, cols_val)

    # ==================== 成交记录 ====================

    def save_filled_orders(self, row):
        """保存成交记录到数据库"""
        try:
            cell_id = row.get('id')
            cell_price = row.get('price', 0)
            record_dict = {}
            cell_type = row.get('cell_type', 'BUY')

            if cell_type == 'SELL':
                parent_cell_id = row.get('parent_cell_id')
                parent = self.db.load_cell_by_id(parent_cell_id) if parent_cell_id else None
                if parent:
                    record_dict['buy_order_id'] = parent.get('order_id')
                    record_dict['buy_dealt_avg_price'] = parent.get('dealt_avg_price')
                    record_dict['buy_dealt_qty'] = parent.get('dealt_qty')
                    record_dict['buy_create_time'] = parent.get('create_time')
                    record_dict['buy_updated_time'] = parent.get('updated_time')
                record_dict['sell_order_id'] = row.get('order_id')
                record_dict['sell_dealt_avg_price'] = row.get('dealt_avg_price')
                record_dict['sell_dealt_qty'] = row.get('dealt_qty')
                record_dict['sell_create_time'] = row.get('create_time')
                record_dict['sell_updated_time'] = row.get('updated_time')
            else:
                parent_cell_id = row.get('parent_cell_id')
                parent = self.db.load_cell_by_id(parent_cell_id) if parent_cell_id else None
                record_dict['buy_order_id'] = row.get('order_id')
                record_dict['buy_dealt_avg_price'] = row.get('dealt_avg_price')
                record_dict['buy_dealt_qty'] = row.get('dealt_qty')
                record_dict['buy_create_time'] = row.get('create_time')
                record_dict['buy_updated_time'] = row.get('updated_time')
                if parent:
                    record_dict['sell_order_id'] = parent.get('order_id')
                    record_dict['sell_dealt_avg_price'] = parent.get('dealt_avg_price')
                    record_dict['sell_dealt_qty'] = parent.get('dealt_qty')
                    record_dict['sell_create_time'] = parent.get('create_time')
                    record_dict['sell_updated_time'] = parent.get('updated_time')

            self.db.save_filled_order(
                self.stock_code, self.strategy_type,
                cell_id, cell_price, record_dict
            )
        except Exception as e:
            logger.error(f"Failed to save filled order: {e}")
            raise

    # ==================== 父子关系查询 ====================

    def get_parent_cells(self) -> pd.DataFrame:
        """获取所有父单元格"""
        return self.data[self.data['parent_cell_id'].isna()]

    def get_child_cells(self, parent_cell_id: int) -> pd.DataFrame:
        """获取某父单元格的所有子单元格"""
        return self.data[self.data['parent_cell_id'] == parent_cell_id]

    def get_buy_cells(self) -> pd.DataFrame:
        return self.data[self.data['cell_type'] == 'BUY']

    def get_sell_cells(self) -> pd.DataFrame:
        return self.data[self.data['cell_type'] == 'SELL']

    def get_parent_buy_cells(self) -> pd.DataFrame:
        return self.data[
            (self.data['cell_type'] == 'BUY') &
            (self.data['parent_cell_id'].isna())
        ]

    def get_parent_sell_cells(self) -> pd.DataFrame:
        return self.data[
            (self.data['cell_type'] == 'SELL') &
            (self.data['parent_cell_id'].isna())
        ]

    # ==================== 数据同步 ====================

    def reload_from_db(self):
        """从数据库重新加载数据"""
        self.data = self.db.load_cells(self.stock_code, self.strategy_type)
        logger.debug(f"Reloaded: {self.stock_code} {self.strategy_type} "
                    f"({len(self.data)} rows)")
