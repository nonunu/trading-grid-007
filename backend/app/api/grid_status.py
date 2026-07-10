"""
网格状态 API (策略信息页面)
计算每只股票的满仓数量、当前仓位、做多/做空网格指标
"""

from typing import Optional, List
from fastapi import APIRouter

from app.api.deps import get_db, get_engine

router = APIRouter(prefix="/api/grid_status", tags=["grid_status"])


@router.get("")
async def get_grid_status():
    """获取所有股票的网格状态卡片数据"""
    db = get_db()
    engine = get_engine()

    configs = db.load_all_configs(active_only=True)
    result = []

    for config in configs:
        stock_code = config['stock_code']
        last_price = config.get('last_price')

        # 从引擎获取实时价格（如果引擎运行中）
        if engine and engine.is_running():
            engine_config = engine._stock_grids.get(stock_code, {})
            if engine_config.get('last_price'):
                last_price = engine_config['last_price']

        multi_full, multi_position = _calc_grid_metrics(db, stock_code, 'MULTI', last_price)
        short_full, short_position = _calc_grid_metrics(db, stock_code, 'SHORT', last_price)

        all_full = multi_full + short_full
        all_position = multi_position + short_position
        all_pct = round(all_position / all_full * 100, 1) if all_full > 0 else 0.0

        multi_pct = round(multi_position / multi_full * 100, 1) if multi_full > 0 else 0.0
        short_pct = round(short_position / short_full * 100, 1) if short_full > 0 else 0.0

        result.append({
            'stock_code': stock_code,
            'last_price': last_price,
            'all_full_qty': all_full,
            'all_position_qty': all_position,
            'all_position_pct': all_pct,
            'multi_full_qty': multi_full,
            'multi_position_qty': multi_position,
            'multi_position_pct': multi_pct,
            'short_full_qty': short_full,
            'short_position_qty': short_position,
            'short_position_pct': short_pct,
            'holding_qty': _query_holding_qty(stock_code),
        })

    return result


def _calc_grid_metrics(db, stock_code: str, strategy_type: str, last_price: Optional[float]):
    """
    计算网格指标

    满仓数量 = BUY 单元格 qty 总和 (排除 TRANSFERRED)
    当前仓位 = BUY 单元格中 price > last_price 的 qty 总和
    """
    conn = db._get_connection()
    try:
        cursor = conn.execute("""
            SELECT COALESCE(SUM(qty), 0) as total_qty
            FROM grid_cells
            WHERE stock_code = ? AND strategy_type = ?
              AND cell_type = 'BUY'
              AND (order_status IS NULL OR order_status != 'TRANSFERRED')
        """, (stock_code, strategy_type))
        total_qty = int(cursor.fetchone()['total_qty'])

        if last_price and last_price > 0:
            cursor = conn.execute("""
                SELECT COALESCE(SUM(qty), 0) as total_position
                FROM grid_cells
                WHERE stock_code = ? AND strategy_type = ?
                  AND cell_type = 'BUY'
                  AND price > ?
                  AND (order_status IS NULL OR order_status != 'TRANSFERRED')
            """, (stock_code, strategy_type, last_price))
            total_position = int(cursor.fetchone()['total_position'])
        else:
            total_position = 0

        return total_qty, total_position
    except Exception:
        return 0, 0


def _query_holding_qty(stock_code: str) -> Optional[int]:
    """
    从券商查询实际持仓数量
    如果券商未连接则返回 None
    """
    try:
        from app.brokers.factory import get_broker
        broker = get_broker(stock_code)
        if not broker.is_connected:
            return None

        # FUTU broker
        if hasattr(broker, '_trade_ctx') and broker._trade_ctx:
            import futu as ft
            from app.config import TRADING_ENV
            trd_env = ft.TrdEnv.REAL if TRADING_ENV == 'REAL' else ft.TrdEnv.SIMULATE
            ret, data = broker._trade_ctx.position_list_query(
                code=stock_code, trd_env=trd_env
            )
            if ret == ft.RET_OK and len(data) > 0:
                return int(data.iloc[0]['qty'])
            return 0

        # QMT broker
        if hasattr(broker, '_trader') and broker._trader:
            positions = broker._trader.query_stock_positions(broker._account)
            if positions:
                for pos in positions:
                    if pos.stock_code == stock_code:
                        return int(pos.volume)
            return 0

    except Exception:
        pass
    return None
