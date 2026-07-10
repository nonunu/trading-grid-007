"""
自救管理 API
- 查询可转换单元格
- 转仓 MULTI→SHORT
- 还原 SHORT→MULTI
- 查询转换记录
"""

import json
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.api.deps import get_db, get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rescue", tags=["rescue"])


class TransferRequest(BaseModel):
    """转仓请求"""
    cell_id: int
    short_price: float
    qty: int


class RestoreRequest(BaseModel):
    """还原请求"""
    rescue_record_id: int


@router.get("/available")
async def list_available_cells(stock_code: str = Query(...)):
    """获取可转换的 MULTI BUY 已成交单元格"""
    db = get_db()
    conn = db._get_connection()

    # 查询 MULTI 策略下已成交的 BUY 父单元格 (排除 TRANSFERRED)
    cursor = conn.execute("""
        SELECT * FROM grid_cells
        WHERE stock_code = ? AND strategy_type = 'MULTI'
          AND cell_type = 'BUY'
          AND parent_cell_id IS NULL
          AND order_status = 'FILLED_ALL'
        ORDER BY price
    """, (stock_code,))
    cells = [dict(row) for row in cursor.fetchall()]

    # 排除已经在活跃 rescue_records 中的
    cursor2 = conn.execute("""
        SELECT multi_parent_cell_id FROM rescue_records
        WHERE stock_code = ? AND status = 'ACTIVE'
    """, (stock_code,))
    transferred_ids = {row['multi_parent_cell_id'] for row in cursor2.fetchall()}

    result = []
    for cell in cells:
        if cell['id'] in transferred_ids:
            continue
        # 查询子单元格数量
        cursor3 = conn.execute(
            "SELECT COUNT(*) as cnt FROM grid_cells WHERE parent_cell_id = ?",
            (cell['id'],)
        )
        child_count = cursor3.fetchone()['cnt']

        result.append({
            'cell_id': cell['id'],
            'price': cell['price'],
            'dealt_avg_price': cell.get('dealt_avg_price') or 0,
            'dealt_qty': cell.get('dealt_qty') or 0,
            'child_count': child_count,
            'status': '可转仓',
        })

    return result


@router.get("/records")
async def list_rescue_records(
    stock_code: Optional[str] = Query(None),
    include_restored: bool = Query(False),
):
    """获取自救转换记录"""
    db = get_db()
    conn = db._get_connection()

    if stock_code and not include_restored:
        cursor = conn.execute(
            "SELECT * FROM rescue_records WHERE stock_code = ? AND status = 'ACTIVE' "
            "ORDER BY created_at DESC", (stock_code,)
        )
    elif stock_code:
        cursor = conn.execute(
            "SELECT * FROM rescue_records WHERE stock_code = ? "
            "ORDER BY created_at DESC", (stock_code,)
        )
    elif not include_restored:
        cursor = conn.execute(
            "SELECT * FROM rescue_records WHERE status = 'ACTIVE' "
            "ORDER BY created_at DESC"
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM rescue_records ORDER BY created_at DESC"
        )

    return [dict(row) for row in cursor.fetchall()]


@router.post("/transfer")
async def transfer_to_short(req: TransferRequest):
    """转仓: MULTI BUY → SHORT SELL"""
    db = get_db()
    conn = db._get_connection()

    # 1. 验证源单元格
    parent = db.load_cell_by_id(req.cell_id)
    if not parent:
        raise HTTPException(status_code=404, detail=f"单元格不存在: {req.cell_id}")
    if parent.get('order_status') != 'FILLED_ALL':
        raise HTTPException(status_code=400, detail="只能转换已成交的单元格")

    stock_code = parent['stock_code']
    dealt_qty = parent.get('dealt_qty') or 0
    if req.qty > dealt_qty:
        raise HTTPException(status_code=400, detail=f"转仓数量({req.qty})不能超过成交量({int(dealt_qty)})")

    # 2. 快照
    snapshot_parent = json.dumps(dict(parent), default=str)
    children_df = db.get_children(req.cell_id)
    child_ids = []
    children_snapshots = []
    if not children_df.empty:
        for _, child in children_df.iterrows():
            child_ids.append(int(child['id']))
            children_snapshots.append(child.to_dict())
    snapshot_children = json.dumps(children_snapshots, default=str) if children_snapshots else None

    # 3. 创建 SHORT SELL 父单元格
    short_cell_id = db.insert_cell(
        stock_code=stock_code,
        strategy_type='SHORT',
        cell_type='SELL',
        price=req.short_price,
        qty=req.qty,
        parent_cell_id=None,
    )

    # 4. 标记 MULTI 父单元格为 TRANSFERRED
    db.update_cell_fields(req.cell_id, {'order_status': 'TRANSFERRED'})

    # 5. 标记子单元格为 TRANSFERRED
    for cid in child_ids:
        child = db.load_cell_by_id(cid)
        if child and child.get('order_status') not in ('FILLED_ALL', 'CANCELLED_PART'):
            db.update_cell_fields(cid, {'order_status': 'TRANSFERRED'})

    # 6. 保存自救记录
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("""
        INSERT INTO rescue_records (
            stock_code, multi_parent_cell_id, multi_child_cell_ids,
            short_parent_cell_id, short_price, qty, buy_dealt_avg_price,
            snapshot_parent, snapshot_children, created_at, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
    """, (
        stock_code, req.cell_id, json.dumps(child_ids),
        short_cell_id, req.short_price, req.qty,
        parent.get('dealt_avg_price'),
        snapshot_parent, snapshot_children, now
    ))
    conn.commit()

    # 7. 通知引擎刷新
    engine = get_engine()
    if engine:
        engine.reload_data(stock_code)

    logger.info(f"转仓完成: {stock_code} MULTI({req.cell_id}) -> SHORT({short_cell_id})")
    return {"success": True, "message": f"转仓完成，SHORT 单元格 ID={short_cell_id}"}


@router.post("/restore")
async def restore_to_multi(req: RestoreRequest):
    """还原: SHORT → MULTI"""
    db = get_db()
    conn = db._get_connection()

    # 1. 查找自救记录
    cursor = conn.execute(
        "SELECT * FROM rescue_records WHERE id = ?", (req.rescue_record_id,)
    )
    record = cursor.fetchone()
    if not record:
        raise HTTPException(status_code=404, detail="自救记录不存在")
    record = dict(record)

    if record.get('status') != 'ACTIVE':
        raise HTTPException(status_code=400, detail="该记录已还原")

    stock_code = record['stock_code']
    multi_parent_id = record['multi_parent_cell_id']
    short_parent_id = record['short_parent_cell_id']
    child_ids = json.loads(record.get('multi_child_cell_ids') or '[]')

    # 2. 从快照还原 MULTI 父单元格
    snapshot = json.loads(record.get('snapshot_parent') or '{}')
    if snapshot:
        restore_fields = {}
        if 'order_status' in snapshot:
            restore_fields['order_status'] = snapshot['order_status']
        if 'dealt_avg_price' in snapshot:
            restore_fields['dealt_avg_price'] = snapshot['dealt_avg_price']
        if 'dealt_qty' in snapshot:
            restore_fields['dealt_qty'] = snapshot['dealt_qty']
        if restore_fields:
            db.update_cell_fields(multi_parent_id, restore_fields)

    # 3. 还原子单元格
    children_snapshot = json.loads(record.get('snapshot_children') or '[]')
    for cs in children_snapshot:
        cid = cs.get('id')
        if cid:
            restore_fields = {}
            if cs.get('order_status') and cs['order_status'] != 'TRANSFERRED':
                restore_fields['order_status'] = cs['order_status']
            else:
                restore_fields['order_status'] = None
            if restore_fields:
                db.update_cell_fields(cid, restore_fields)

    # 4. 删除 SHORT 父单元格及其子单元格
    short_children = db.get_children(short_parent_id)
    if not short_children.empty:
        db.delete_cells_by_parent(short_parent_id)
    db.delete_cell(short_parent_id)

    # 5. 标记自救记录为已还原
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "UPDATE rescue_records SET status = 'RESTORED', restored_at = ? WHERE id = ?",
        (now, req.rescue_record_id)
    )
    conn.commit()

    # 6. 通知引擎刷新
    engine = get_engine()
    if engine:
        engine.reload_data(stock_code)

    logger.info(f"还原完成: {stock_code} SHORT({short_parent_id}) -> MULTI({multi_parent_id})")
    return {"success": True, "message": "还原完成"}
