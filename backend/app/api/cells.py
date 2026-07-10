"""
网格单元格管理 API
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.models.cell import CellCreate, CellUpdate, CellResponse
from app.api.deps import get_db, get_engine

router = APIRouter(prefix="/api/cells", tags=["cells"])


@router.get("", response_model=List[CellResponse])
async def list_cells(
    stock_code: Optional[str] = Query(None),
    strategy_type: Optional[str] = Query(None),
):
    """获取网格单元格列表"""
    import math
    db = get_db()
    if stock_code and strategy_type:
        df = db.load_cells(stock_code, strategy_type)
        records = df.to_dict('records')
    else:
        records = db.load_all_cells()

    # 清洗 NaN/float('nan') 为 None，避免 Pydantic 验证失败
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r[k] = None
    return records


@router.get("/{cell_id}", response_model=CellResponse)
async def get_cell(cell_id: int):
    """获取单个单元格"""
    db = get_db()
    cell = db.load_cell_by_id(cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail=f"单元格不存在: {cell_id}")
    return cell


@router.post("", response_model=CellResponse)
async def create_cell(data: CellCreate):
    """创建单元格"""
    db = get_db()

    # 验证股票配置存在
    config = db.load_config(data.stock_code)
    if not config:
        raise HTTPException(
            status_code=400,
            detail=f"股票配置不存在: {data.stock_code}，请先添加配置"
        )

    # 验证父单元格存在 (如果指定了)
    if data.parent_cell_id:
        parent = db.load_cell_by_id(data.parent_cell_id)
        if not parent:
            raise HTTPException(
                status_code=400,
                detail=f"父单元格不存在: {data.parent_cell_id}"
            )

    cell_id = db.insert_cell(
        stock_code=data.stock_code,
        strategy_type=data.strategy_type,
        cell_type=data.cell_type,
        price=data.price,
        qty=data.qty,
        parent_cell_id=data.parent_cell_id,
        dealt_qty=data.dealt_qty,
        dealt_avg_price=data.dealt_avg_price,
    )

    # 通知引擎刷新
    engine = get_engine()
    if engine:
        engine.reload_data(data.stock_code)

    return db.load_cell_by_id(cell_id)


@router.put("/{cell_id}", response_model=CellResponse)
async def update_cell(cell_id: int, data: CellUpdate):
    """更新单元格 (仅允许修改 price/qty)"""
    db = get_db()
    cell = db.load_cell_by_id(cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail=f"单元格不存在: {cell_id}")

    # 已下单的不允许修改
    if cell.get('order_id'):
        raise HTTPException(
            status_code=400,
            detail="已下单的单元格不允许修改，请先撤单"
        )

    update_fields = data.model_dump(exclude_unset=True)
    if update_fields:
        db.update_cell_fields(cell_id, update_fields)

    # 通知引擎刷新
    engine = get_engine()
    if engine:
        engine.reload_data(cell.get('stock_code'))

    return db.load_cell_by_id(cell_id)


@router.delete("/{cell_id}")
async def delete_cell(cell_id: int):
    """删除单元格"""
    db = get_db()
    cell = db.load_cell_by_id(cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail=f"单元格不存在: {cell_id}")

    # 已下单的不允许删除
    if cell.get('order_id'):
        raise HTTPException(
            status_code=400,
            detail="已下单的单元格不允许删除，请先撤单"
        )

    # 如果是父单元格，同时删除子单元格
    children = db.get_children(cell_id)
    if not children.empty:
        # 检查子单元格是否有正在执行的订单
        active_children = children[children['order_id'].notna()]
        if not active_children.empty:
            raise HTTPException(
                status_code=400,
                detail="子单元格有未完成订单，无法删除"
            )
        db.delete_cells_by_parent(cell_id)

    db.delete_cell(cell_id)

    # 通知引擎刷新
    engine = get_engine()
    if engine:
        engine.reload_data(cell.get('stock_code'))

    return {"message": f"已删除单元格 id={cell_id}"}


@router.post("/{cell_id}/clear")
async def clear_cell_order(cell_id: int):
    """清空单元格订单信息 (重置)"""
    db = get_db()
    cell = db.load_cell_by_id(cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail=f"单元格不存在: {cell_id}")

    db.clear_cell_order_info(cell_id)

    engine = get_engine()
    if engine:
        engine.reload_data(cell.get('stock_code'))

    return db.load_cell_by_id(cell_id)


# ==================== 批量保存修改 ====================

from pydantic import BaseModel
from typing import Dict


class BatchUpdateItem(BaseModel):
    price: Optional[float] = None
    qty: Optional[int] = None
    allocated_qty: Optional[float] = None


class BatchUpdateRequest(BaseModel):
    updates: Dict[int, BatchUpdateItem]  # {cell_id: {field: value}}


@router.post("/batch_update")
async def batch_update_cells(req: BatchUpdateRequest):
    """批量保存修改 (价格、数量、分配量)"""
    db = get_db()
    updated_count = 0
    stock_code = None

    for cell_id, fields in req.updates.items():
        cell = db.load_cell_by_id(cell_id)
        if not cell:
            continue

        # 已有未完成订单的不允许修改价格和数量
        if cell.get('order_id') and cell.get('order_status') not in (
            None, 'FILLED_ALL', 'CANCELLED_PART', 'TRANSFERRED'
        ):
            continue

        update_fields = {}
        if fields.price is not None:
            update_fields['price'] = fields.price
        if fields.qty is not None:
            update_fields['qty'] = fields.qty
        if fields.allocated_qty is not None:
            update_fields['allocated_qty'] = fields.allocated_qty

        if update_fields:
            db.update_cell_fields(cell_id, update_fields)
            updated_count += 1
            stock_code = cell['stock_code']

    # 通知引擎刷新
    if stock_code:
        engine = get_engine()
        if engine:
            engine.reload_data(stock_code)

    return {"success": True, "updated_count": updated_count}


# ==================== 拆分父单元格 ====================

class SplitRequest(BaseModel):
    cell_id: int
    splits: list  # [{price: float, qty: int}, ...]


@router.post("/split")
async def split_parent_cell(req: SplitRequest):
    """
    拆分父单元格: 将一个已成交的父单元格拆分为多个新的父单元格
    原父单元格保留，新父单元格继承成交信息
    """
    db = get_db()

    parent = db.load_cell_by_id(req.cell_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"单元格不存在: {req.cell_id}")

    if parent.get('order_status') not in ('FILLED_ALL', 'CANCELLED_PART'):
        raise HTTPException(status_code=400, detail="只能拆分已成交的父单元格")

    if parent.get('parent_cell_id'):
        raise HTTPException(status_code=400, detail="不能拆分子单元格")

    dealt_qty = parent.get('dealt_qty') or 0
    dealt_avg_price = parent.get('dealt_avg_price') or parent['price']

    # 验证拆分总量不超过原始成交量
    total_split_qty = sum(s.get('qty', 0) for s in req.splits)
    if total_split_qty > dealt_qty:
        raise HTTPException(
            status_code=400,
            detail=f"拆分总量({total_split_qty})超过成交量({int(dealt_qty)})"
        )

    stock_code = parent['stock_code']
    strategy_type = parent['strategy_type']
    cell_type = parent['cell_type']

    new_cell_ids = []
    for split in req.splits:
        new_id = db.insert_cell(
            stock_code=stock_code,
            strategy_type=strategy_type,
            cell_type=cell_type,
            price=split['price'],
            qty=split['qty'],
            parent_cell_id=None,
            dealt_qty=split['qty'],
            dealt_avg_price=dealt_avg_price,
        )
        new_cell_ids.append(new_id)

    # 原父单元格减去已拆分的数量
    remaining_qty = int(dealt_qty - total_split_qty)
    if remaining_qty <= 0:
        # 全部拆完，标记原父单元格
        db.update_cell_fields(req.cell_id, {
            'qty': 0,
            'dealt_qty': 0,
            'order_status': 'TRANSFERRED',
        })
    else:
        db.update_cell_fields(req.cell_id, {
            'qty': remaining_qty,
            'dealt_qty': remaining_qty,
        })

    # 通知引擎刷新
    engine = get_engine()
    if engine:
        engine.reload_data(stock_code)

    return {
        "success": True,
        "new_cell_ids": new_cell_ids,
        "message": f"拆分完成，生成 {len(new_cell_ids)} 个新单元格"
    }
