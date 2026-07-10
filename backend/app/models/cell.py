"""
网格单元格 Pydantic 模型
"""

from typing import Optional
from pydantic import BaseModel, Field


class CellCreate(BaseModel):
    """创建单元格"""
    stock_code: str
    strategy_type: str = Field(..., description="MULTI or SHORT")
    cell_type: str = Field(..., description="BUY or SELL")
    price: float = Field(..., gt=0)
    qty: int = Field(..., gt=0)
    parent_cell_id: Optional[int] = None
    dealt_qty: float = Field(0, ge=0)
    dealt_avg_price: Optional[float] = None


class CellUpdate(BaseModel):
    """更新单元格"""
    price: Optional[float] = Field(None, gt=0)
    qty: Optional[int] = Field(None, gt=0)


class CellResponse(BaseModel):
    """单元格响应"""
    id: int
    stock_code: str
    strategy_type: str
    cell_type: str
    parent_cell_id: Optional[int] = None
    price: float
    qty: int
    allocated_qty: Optional[float] = 0
    order_id: Optional[str] = None
    order_status: Optional[str] = None
    dealt_avg_price: Optional[float] = None
    dealt_qty: Optional[float] = 0
    create_time: Optional[str] = None
    updated_time: Optional[str] = None
