"""
Dashboard 数据 API
提供汇总统计、按日/周/月聚合收益趋势
"""

from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Query

from app.api.deps import get_db, get_engine

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_summary(
    stock_code: Optional[str] = Query(None, description="股票代码筛选，空=全部"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """获取 Dashboard 汇总数据（支持筛选）"""
    db = get_db()
    engine = get_engine()

    configs = db.load_all_configs()
    active_count = sum(1 for c in configs if c.get('is_active'))

    engine_status = engine.get_status() if engine else {
        'running': False, 'strategies_count': 0, 'stocks': []
    }

    # 获取成交记录（带筛选）
    filled_orders = _load_filtered_orders(db, stock_code, start_date, end_date)
    total_profit = sum((r.get('profit_diff') or 0) for r in filled_orders)
    total_trades = len(filled_orders)

    return {
        "engine_running": engine_status['running'],
        "strategies_count": engine_status['strategies_count'],
        "total_stocks": len(configs),
        "active_stocks": active_count,
        "total_trades": total_trades,
        "total_profit": round(total_profit, 2),
        "stocks": [
            {
                "stock_code": c['stock_code'],
                "market": c.get('market', ''),
                "direction": c['direction'],
                "last_price": c.get('last_price'),
                "is_active": c['is_active'],
            }
            for c in configs
        ],
    }


@router.get("/profit_trend")
async def get_profit_trend(
    stock_code: Optional[str] = Query(None, description="股票代码筛选，空=全部"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """
    获取收益趋势数据（按日/周/月聚合）
    返回 daily, weekly, monthly 三组数据
    """
    db = get_db()
    filled_orders = _load_filtered_orders(db, stock_code, start_date, end_date)

    # 按日聚合
    daily = defaultdict(lambda: {'profit': 0.0, 'count': 0})
    # 按周聚合
    weekly = defaultdict(lambda: {'profit': 0.0, 'count': 0})
    # 按月聚合
    monthly = defaultdict(lambda: {'profit': 0.0, 'count': 0})

    for r in filled_orders:
        completed_at = r.get('completed_at') or ''
        profit = r.get('profit_diff') or 0

        # 解析日期
        dt = _parse_date(completed_at)
        if dt is None:
            continue

        # 日
        day_key = dt.strftime('%Y-%m-%d')
        daily[day_key]['profit'] += profit
        daily[day_key]['count'] += 1

        # 周 (ISO 周数)
        iso_year, iso_week, _ = dt.isocalendar()
        week_key = f"{iso_year}-{iso_week:02d}"
        weekly[week_key]['profit'] += profit
        weekly[week_key]['count'] += 1

        # 月
        month_key = dt.strftime('%Y-%m')
        monthly[month_key]['profit'] += profit
        monthly[month_key]['count'] += 1

    return {
        "daily": _format_trend(daily),
        "weekly": _format_trend(weekly),
        "monthly": _format_trend(monthly),
    }


@router.get("/filled_orders")
async def get_filled_orders(
    stock_code: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    """获取成交记录"""
    db = get_db()
    records = _load_filtered_orders(db, stock_code, start_date, end_date, limit)
    return records


@router.get("/profit_summary")
async def get_profit_summary():
    """按股票汇总利润"""
    db = get_db()
    filled_orders = db.load_filled_orders(limit=5000)

    summary = {}
    for r in filled_orders:
        code = r['stock_code']
        if code not in summary:
            summary[code] = {
                'stock_code': code,
                'trade_count': 0,
                'total_profit': 0.0,
            }
        summary[code]['trade_count'] += 1
        summary[code]['total_profit'] += (r.get('profit_diff') or 0)

    result = list(summary.values())
    for item in result:
        item['total_profit'] = round(item['total_profit'], 2)

    return sorted(result, key=lambda x: x['total_profit'], reverse=True)


# ==================== 内部辅助函数 ====================

def _load_filtered_orders(db, stock_code=None, start_date=None, end_date=None, limit=5000):
    """加载并按条件筛选成交记录"""
    records = db.load_filled_orders(stock_code=stock_code, limit=limit)

    if start_date or end_date:
        filtered = []
        for r in records:
            completed_at = r.get('completed_at') or ''
            dt = _parse_date(completed_at)
            if dt is None:
                continue
            if start_date and dt.strftime('%Y-%m-%d') < start_date:
                continue
            if end_date and dt.strftime('%Y-%m-%d') > end_date:
                continue
            filtered.append(r)
        return filtered

    return records


def _parse_date(date_str: str):
    """解析日期字符串"""
    if not date_str:
        return None
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _format_trend(data: dict) -> list:
    """将聚合字典转为排序后的列表"""
    result = []
    for key in sorted(data.keys()):
        result.append({
            'period': key,
            'profit': round(data[key]['profit'], 2),
            'count': data[key]['count'],
        })
    return result
