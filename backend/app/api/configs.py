"""
股票配置 CRUD API
"""

from typing import List
from fastapi import APIRouter, HTTPException

from app.models.config import StockConfigCreate, StockConfigUpdate, StockConfigResponse
from app.constants import Market, A_SHARE_MIN_LOT_SIZE
from app.api.deps import get_db

router = APIRouter(prefix="/api/configs", tags=["configs"])


@router.get("", response_model=List[StockConfigResponse])
async def list_configs():
    """获取所有股票配置"""
    db = get_db()
    configs = db.load_all_configs()
    return configs


@router.get("/{stock_code}", response_model=StockConfigResponse)
async def get_config(stock_code: str):
    """获取单个股票配置"""
    db = get_db()
    config = db.load_config(stock_code)
    if not config:
        raise HTTPException(status_code=404, detail=f"配置不存在: {stock_code}")
    return config


@router.post("", response_model=StockConfigResponse)
async def create_config(data: StockConfigCreate):
    """创建股票配置"""
    db = get_db()

    # 自动推断市场
    try:
        market = data.market or Market.from_stock_code(data.stock_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 自动设置 A 股最小交易单位
    min_lot_size = data.min_lot_size
    if min_lot_size is None:
        min_lot_size = A_SHARE_MIN_LOT_SIZE if Market.is_a_share(data.stock_code) else 1

    db.insert_config(
        stock_code=data.stock_code,
        market=market,
        direction=data.direction,
        buy_cell_count=data.buy_cell_count,
        sell_cell_count=data.sell_cell_count,
        order_query_period=data.order_query_period,
        place_order_scope=data.place_order_scope,
        min_lot_size=min_lot_size,
    )

    config = db.load_config(data.stock_code)
    return config


@router.put("/{stock_code}", response_model=StockConfigResponse)
async def update_config(stock_code: str, data: StockConfigUpdate):
    """更新股票配置"""
    db = get_db()
    config = db.load_config(stock_code)
    if not config:
        raise HTTPException(status_code=404, detail=f"配置不存在: {stock_code}")

    update_fields = data.model_dump(exclude_unset=True)
    if update_fields:
        db.update_config(stock_code, **update_fields)

    return db.load_config(stock_code)


@router.delete("/{stock_code}")
async def delete_config(stock_code: str):
    """删除股票配置及关联网格"""
    db = get_db()
    config = db.load_config(stock_code)
    if not config:
        raise HTTPException(status_code=404, detail=f"配置不存在: {stock_code}")

    db.delete_config(stock_code)
    return {"message": f"已删除: {stock_code}"}
