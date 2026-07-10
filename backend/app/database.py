"""
网格交易数据库访问层 (统一版本)
支持 A股/港股/美股, 多线程安全, 1:N 买卖比模型
"""

import sqlite3
import threading
import logging
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime
from os import path

logger = logging.getLogger(__name__)

# 统一的时间格式
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# SQL 字段白名单 - 防止 SQL 注入
ALLOWED_CELL_FIELDS = {
    'order_id', 'order_status', 'dealt_avg_price', 'dealt_qty',
    'create_time', 'updated_time', 'price', 'qty', 'allocated_qty',
    'parent_cell_id', 'cell_type', 'strategy_type', 'stock_code',
    'updated_at',
}

ALLOWED_CONFIG_FIELDS = {
    'direction', 'buy_cell_count', 'sell_cell_count',
    'order_query_period', 'place_order_scope', 'last_price',
    'is_active', 'updated_at', 'market', 'min_lot_size',
}


def _validate_field(field: str, allowed: set):
    """验证字段名是否在白名单内"""
    if field not in allowed:
        raise ValueError(f"非法字段名: {field!r}，允许的字段: {allowed}")


def format_datetime(dt_value) -> Optional[str]:
    """
    将各种格式的时间值统一转换为标准格式: YYYY-MM-DD HH:MM:SS
    """
    if dt_value is None or (isinstance(dt_value, float) and pd.isna(dt_value)):
        return None

    if isinstance(dt_value, str):
        dt_value = dt_value.strip()
        if not dt_value:
            return None
        formats_to_try = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y%m%d%H%M%S",
            "%Y%m%d",
        ]
        for fmt in formats_to_try:
            try:
                dt_obj = datetime.strptime(dt_value, fmt)
                return dt_obj.strftime(TIME_FORMAT)
            except ValueError:
                continue
        logger.warning(f"无法解析时间格式: {dt_value}，保持原样")
        return dt_value

    if isinstance(dt_value, datetime):
        return dt_value.strftime(TIME_FORMAT)

    try:
        return format_datetime(str(dt_value))
    except (ValueError, TypeError, OverflowError):
        logger.warning(f"未知时间类型: {type(dt_value)}, 值: {dt_value}")
        return None


class GridDatabase:
    """网格交易数据库管理类（统一版本，支持1:N买卖比）"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._schema_initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                timeout=30,
                isolation_level=None
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.execute("PRAGMA cache_size=-64000")

        if not self._schema_initialized:
            with self._init_lock:
                if not self._schema_initialized:
                    self._init_schema(self._local.conn)
                    self._schema_initialized = True

        return self._local.conn

    def _init_schema(self, conn: sqlite3.Connection):
        """从 schema.sql 初始化表结构，并自动迁移旧表"""
        # 先执行迁移（为旧表添加缺失列），再执行 schema.sql（创建索引等）
        self._migrate_schema(conn)

        schema_path = path.join(
            path.dirname(path.abspath(__file__)), 'schema.sql'
        )
        if path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                conn.executescript(f.read())
            logger.debug("Schema initialized from schema.sql")
        else:
            logger.warning("schema.sql not found at %s", schema_path)

    def _migrate_schema(self, conn: sqlite3.Connection):
        """检测并添加旧数据库缺失的列"""
        migrations = [
            # (表名, 列名, 列定义)
            ('grid_configs', 'market', "TEXT NOT NULL DEFAULT 'HK'"),
            ('grid_configs', 'min_lot_size', "INTEGER DEFAULT 1"),
            ('rescue_records', 'status', "TEXT DEFAULT 'ACTIVE'"),
            ('rescue_records', 'source_strategy', "TEXT"),
            ('rescue_records', 'target_strategy', "TEXT"),
            ('rescue_records', 'source_cell_id', "INTEGER"),
            ('rescue_records', 'target_cell_id', "INTEGER"),
            ('rescue_records', 'transfer_qty', "REAL"),
            ('rescue_records', 'transfer_price', "REAL"),
            ('rescue_records', 'snapshot_order_id', "TEXT"),
            ('rescue_records', 'snapshot_order_status', "TEXT"),
            ('rescue_records', 'snapshot_dealt_avg_price', "REAL"),
            ('rescue_records', 'snapshot_dealt_qty', "REAL"),
            ('grid_cells', 'updated_at', "TEXT"),
        ]

        for table, column, definition in migrations:
            try:
                # 检查列是否已存在
                cursor = conn.execute(f"PRAGMA table_info({table})")
                existing_columns = {row[1] for row in cursor.fetchall()}
                if column not in existing_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    logger.info(f"迁移: {table} 添加列 {column}")
            except Exception as e:
                # 表可能不存在，忽略
                logger.debug(f"迁移跳过 {table}.{column}: {e}")

    # ==================== 配置管理方法 ====================

    def insert_config(self, stock_code: str, market: str = 'HK',
                     direction: str = 'ALL',
                     buy_cell_count: int = 3, sell_cell_count: int = 3,
                     order_query_period: int = 4, place_order_scope: float = 0.1,
                     last_price: Optional[float] = None,
                     min_lot_size: int = 1, is_active: int = 1):
        """插入或更新股票配置"""
        conn = self._get_connection()
        try:
            now = format_datetime(datetime.now())
            conn.execute("""
                INSERT INTO grid_configs (
                    stock_code, market, direction, buy_cell_count, sell_cell_count,
                    order_query_period, place_order_scope, last_price,
                    min_lot_size, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_code) DO UPDATE SET
                    market = excluded.market,
                    direction = excluded.direction,
                    buy_cell_count = excluded.buy_cell_count,
                    sell_cell_count = excluded.sell_cell_count,
                    order_query_period = excluded.order_query_period,
                    place_order_scope = excluded.place_order_scope,
                    last_price = excluded.last_price,
                    min_lot_size = excluded.min_lot_size,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
            """, (
                stock_code, market, direction, buy_cell_count, sell_cell_count,
                order_query_period, place_order_scope, last_price,
                min_lot_size, is_active, now, now
            ))
            conn.commit()
            logger.info(f"Config saved for {stock_code} (market={market})")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save config for {stock_code}: {e}")
            raise

    def load_config(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """加载单个股票配置"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM grid_configs WHERE stock_code = ?",
            (stock_code,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def load_all_configs(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """加载所有股票配置"""
        conn = self._get_connection()
        if active_only:
            cursor = conn.execute(
                "SELECT * FROM grid_configs WHERE is_active = 1 ORDER BY stock_code"
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM grid_configs ORDER BY stock_code"
            )
        return [dict(row) for row in cursor.fetchall()]

    def load_configs_by_market(self, markets: set) -> List[Dict[str, Any]]:
        """按市场加载活跃配置"""
        conn = self._get_connection()
        placeholders = ','.join('?' * len(markets))
        cursor = conn.execute(
            f"SELECT * FROM grid_configs WHERE market IN ({placeholders}) "
            f"AND is_active = 1 ORDER BY stock_code",
            list(markets)
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_config(self, stock_code: str, **kwargs):
        """更新股票配置的部分字段"""
        if not kwargs:
            return
        conn = self._get_connection()
        try:
            set_clauses = []
            values = []
            for key, value in kwargs.items():
                _validate_field(key, ALLOWED_CONFIG_FIELDS)
                set_clauses.append(f"{key} = ?")
                values.append(value)

            now = format_datetime(datetime.now())
            set_clauses.append("updated_at = ?")
            values.append(now)
            values.append(stock_code)

            sql = f"UPDATE grid_configs SET {', '.join(set_clauses)} WHERE stock_code = ?"
            conn.execute(sql, values)
            conn.commit()
            logger.info(f"Config updated for {stock_code}: {list(kwargs.keys())}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update config for {stock_code}: {e}")
            raise

    def delete_config(self, stock_code: str):
        """删除股票配置及其关联的网格单元格"""
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM grid_configs WHERE stock_code = ?", (stock_code,))
            conn.execute("DELETE FROM grid_cells WHERE stock_code = ?", (stock_code,))
            conn.commit()
            logger.info(f"Config and cells deleted for {stock_code}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete config for {stock_code}: {e}")
            raise

    # ==================== 网格单元格管理方法 (1:N) ====================

    def insert_cell(self, stock_code: str, strategy_type: str,
                    cell_type: str, price: float, qty: int,
                    parent_cell_id: Optional[int] = None,
                    allocated_qty: float = 0,
                    dealt_qty: float = 0,
                    dealt_avg_price: Optional[float] = None) -> int:
        """插入单元格，返回新创建的ID"""
        conn = self._get_connection()
        try:
            order_status = 'FILLED_ALL' if dealt_qty > 0 else None
            now = format_datetime(datetime.now())
            cursor = conn.execute("""
                INSERT INTO grid_cells (
                    stock_code, strategy_type, cell_type, parent_cell_id,
                    price, qty, allocated_qty, dealt_qty,
                    dealt_avg_price, order_status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stock_code, strategy_type, cell_type, parent_cell_id,
                price, qty, allocated_qty, dealt_qty,
                dealt_avg_price, order_status, now
            ))
            conn.commit()
            cell_id = cursor.lastrowid
            logger.info(
                f"Cell created: id={cell_id} {stock_code} {strategy_type} "
                f"{cell_type} price={price} qty={qty} parent={parent_cell_id}"
            )
            return cell_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to insert cell: {e}")
            raise

    def delete_cell(self, cell_id: int):
        """删除单个单元格"""
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM grid_cells WHERE id = ?", (cell_id,))
            conn.commit()
            logger.info(f"Cell deleted: id={cell_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete cell: {e}")
            raise

    def delete_cells_by_parent(self, parent_cell_id: int):
        """删除某父单元格的所有子单元格"""
        conn = self._get_connection()
        try:
            conn.execute(
                "DELETE FROM grid_cells WHERE parent_cell_id = ?",
                (parent_cell_id,)
            )
            conn.commit()
            logger.info(f"Children deleted for parent id={parent_cell_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete children: {e}")
            raise

    def load_cells(self, stock_code: str, strategy_type: str,
                   cell_type: Optional[str] = None) -> pd.DataFrame:
        """加载单元格数据"""
        conn = self._get_connection()
        if cell_type:
            query = """
                SELECT * FROM grid_cells
                WHERE stock_code = ? AND strategy_type = ? AND cell_type = ?
                ORDER BY price
            """
            params = (stock_code, strategy_type, cell_type)
        else:
            query = """
                SELECT * FROM grid_cells
                WHERE stock_code = ? AND strategy_type = ?
                ORDER BY cell_type, price
            """
            params = (stock_code, strategy_type)

        df = pd.read_sql_query(query, conn, params=params)
        if not df.empty:
            numeric_cols = ['price', 'qty', 'dealt_avg_price', 'dealt_qty', 'allocated_qty']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def load_all_cells(self) -> List[Dict[str, Any]]:
        """加载所有单元格（用于前端策略页面）"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM grid_cells ORDER BY stock_code, strategy_type, cell_type, price"
        )
        return [dict(row) for row in cursor.fetchall()]

    def load_cell_by_id(self, cell_id: int) -> Optional[Dict[str, Any]]:
        """通过ID加载单个单元格"""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM grid_cells WHERE id = ?", (cell_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_children(self, parent_cell_id: int) -> pd.DataFrame:
        """获取某父单元格的所有子单元格"""
        conn = self._get_connection()
        df = pd.read_sql_query("""
            SELECT * FROM grid_cells
            WHERE parent_cell_id = ?
            ORDER BY price
        """, conn, params=(parent_cell_id,))
        if not df.empty:
            numeric_cols = ['price', 'qty', 'dealt_avg_price', 'dealt_qty']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def update_cell_field(self, cell_id: int, field: str, value: Any):
        """更新单元格的单个字段"""
        _validate_field(field, ALLOWED_CELL_FIELDS)
        conn = self._get_connection()
        try:
            if field in ['create_time', 'updated_time']:
                value = format_datetime(value)
            now = format_datetime(datetime.now())
            conn.execute(
                f"UPDATE grid_cells SET {field} = ?, updated_at = ? WHERE id = ?",
                (value, now, cell_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update cell field: {e}")
            raise

    def update_cell_fields(self, cell_id: int, fields: Dict[str, Any]):
        """批量更新单元格的多个字段"""
        if not fields:
            return
        for field in fields.keys():
            _validate_field(field, ALLOWED_CELL_FIELDS)

        conn = self._get_connection()
        try:
            set_clauses = [f"{field} = ?" for field in fields.keys()]
            formatted_values = []
            for field, value in fields.items():
                if field in ['create_time', 'updated_time']:
                    formatted_values.append(format_datetime(value))
                else:
                    formatted_values.append(value)

            now = format_datetime(datetime.now())
            set_clauses.append("updated_at = ?")
            formatted_values.append(now)
            formatted_values.append(cell_id)

            sql = f"UPDATE grid_cells SET {', '.join(set_clauses)} WHERE id = ?"
            conn.execute(sql, formatted_values)
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update cell fields: {e}")
            raise

    def clear_cell_order_info(self, cell_id: int):
        """清空单元格的订单信息（重置为初始状态）"""
        self.update_cell_fields(cell_id, {
            'order_id': None,
            'order_status': None,
            'dealt_avg_price': None,
            'dealt_qty': 0,
            'create_time': None,
            'updated_time': None,
        })

    def get_children_total_qty(self, parent_cell_id: int) -> float:
        """获取子单元格的总配置数量"""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT COALESCE(SUM(qty), 0) as total
            FROM grid_cells WHERE parent_cell_id = ?
        """, (parent_cell_id,))
        return cursor.fetchone()['total']

    def validate_allocation(self, parent_cell_id: int) -> bool:
        """验证子单元格总数量不超过父单元格实际成交量"""
        parent = self.load_cell_by_id(parent_cell_id)
        if not parent:
            return False
        parent_dealt_qty = parent.get('dealt_qty', 0) or 0
        children_total = self.get_children_total_qty(parent_cell_id)
        return children_total <= parent_dealt_qty

    def query_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """通过订单ID查询单元格"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM grid_cells WHERE order_id = ?", (order_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    # ==================== 成交记录 ====================

    def save_filled_order(self, stock_code: str, strategy_type: str,
                          cell_id: int, cell_price: float,
                          record_dict: Dict[str, Any]):
        """保存成交记录"""
        conn = self._get_connection()
        try:
            buy_avg = record_dict.get('buy_dealt_avg_price')
            buy_qty = record_dict.get('buy_dealt_qty')
            sell_avg = record_dict.get('sell_dealt_avg_price')
            sell_qty = record_dict.get('sell_dealt_qty')

            buy_amount = (buy_avg * buy_qty) if buy_avg and buy_qty else None
            sell_amount = (sell_avg * sell_qty) if sell_avg and sell_qty else None
            profit_diff = (sell_amount - buy_amount) if buy_amount and sell_amount else None
            completed_at = format_datetime(datetime.now())

            conn.execute("""
                INSERT INTO filled_orders (
                    stock_code, strategy_type, cell_id, cell_price,
                    buy_order_id, buy_dealt_avg_price, buy_dealt_qty,
                    buy_create_time, buy_updated_time,
                    sell_order_id, sell_dealt_avg_price, sell_dealt_qty,
                    sell_create_time, sell_updated_time,
                    buy_amount, sell_amount, profit_diff, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stock_code, strategy_type, cell_id, cell_price,
                record_dict.get('buy_order_id'),
                buy_avg, buy_qty,
                format_datetime(record_dict.get('buy_create_time')),
                format_datetime(record_dict.get('buy_updated_time')),
                record_dict.get('sell_order_id'),
                sell_avg, sell_qty,
                format_datetime(record_dict.get('sell_create_time')),
                format_datetime(record_dict.get('sell_updated_time')),
                buy_amount, sell_amount, profit_diff, completed_at
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save filled order: {e}")
            raise

    def load_filled_orders(self, stock_code: Optional[str] = None,
                           limit: int = 100) -> List[Dict[str, Any]]:
        """加载成交记录"""
        conn = self._get_connection()
        if stock_code:
            cursor = conn.execute(
                "SELECT * FROM filled_orders WHERE stock_code = ? "
                "ORDER BY completed_at DESC LIMIT ?",
                (stock_code, limit)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM filled_orders ORDER BY completed_at DESC LIMIT ?",
                (limit,)
            )
        return [dict(row) for row in cursor.fetchall()]

    # ==================== 自救记录 ====================

    def save_rescue_record(self, stock_code: str, source_strategy: str,
                           target_strategy: str, source_cell_id: int,
                           target_cell_id: Optional[int],
                           transfer_qty: float, transfer_price: float,
                           snapshot: Dict[str, Any] = None):
        """保存自救转换记录"""
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO rescue_records (
                    stock_code, source_strategy, target_strategy,
                    source_cell_id, target_cell_id,
                    transfer_qty, transfer_price,
                    snapshot_order_id, snapshot_order_status,
                    snapshot_dealt_avg_price, snapshot_dealt_qty
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stock_code, source_strategy, target_strategy,
                source_cell_id, target_cell_id,
                transfer_qty, transfer_price,
                snapshot.get('order_id') if snapshot else None,
                snapshot.get('order_status') if snapshot else None,
                snapshot.get('dealt_avg_price') if snapshot else None,
                snapshot.get('dealt_qty') if snapshot else None,
            ))
            conn.commit()
            logger.info(f"Rescue record saved: {stock_code} {source_strategy}->{target_strategy}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save rescue record: {e}")
            raise

    def load_rescue_records(self, stock_code: Optional[str] = None,
                            status: str = 'ACTIVE') -> List[Dict[str, Any]]:
        """加载自救记录"""
        conn = self._get_connection()
        if stock_code:
            cursor = conn.execute(
                "SELECT * FROM rescue_records WHERE stock_code = ? AND status = ? "
                "ORDER BY created_at DESC",
                (stock_code, status)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM rescue_records WHERE status = ? "
                "ORDER BY created_at DESC",
                (status,)
            )
        return [dict(row) for row in cursor.fetchall()]
