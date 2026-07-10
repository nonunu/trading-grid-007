"""
股票配置 Pydantic 模型
"""

from typing import Optional
from pydantic import BaseModel, Field


class StockConfigCreate(BaseModel):
    """创建股票配置"""
    stock_code: str = Field(..., description="股票代码 (如 HK.08017, 600519.SH)")
    market: Optional[str] = Field(None, description="市场 (自动从代码推断)")
    direction: str = Field('ALL', description="策略方向: ALL/MULTI/SHORT")
    buy_cell_count: int = Field(3, ge=1, le=10)
    sell_cell_count: int = Field(3, ge=1, le=10)
    order_query_period: int = Field(4, ge=1)
    place_order_scope: float = Field(0.1, gt=0)
    min_lot_size: Optional[int] = Field(None, description="最小交易单位")


class StockConfigUpdate(BaseModel):
    """更新股票配置"""
    direction: Optional[str] = None
    buy_cell_count: Optional[int] = Field(None, ge=1, le=10)
    sell_cell_count: Optional[int] = Field(None, ge=1, le=10)
    order_query_period: Optional[int] = Field(None, ge=1)
    place_order_scope: Optional[float] = Field(None, gt=0)
    min_lot_size: Optional[int] = None
    is_active: Optional[int] = Field(None, ge=0, le=1)


class StockConfigResponse(BaseModel):
    """股票配置响应"""
    stock_code: str
    market: str
    direction: str
    buy_cell_count: int
    sell_cell_count: int
    order_query_period: int
    place_order_scope: float
    last_price: Optional[float] = None
    min_lot_size: int
    is_active: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
