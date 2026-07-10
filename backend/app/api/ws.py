"""
WebSocket 实时推送
向前端推送行情价格更新和引擎状态
"""

import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_engine, get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# 活跃的 WebSocket 连接
_connections: Set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 连接端点"""
    await ws.accept()
    _connections.add(ws)
    logger.info(f"WebSocket 连接建立, 当前连接数: {len(_connections)}")

    try:
        while True:
            # 每 2 秒推送一次状态
            data = _build_push_data()
            await ws.send_text(json.dumps(data, ensure_ascii=False))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket 异常: {e}")
    finally:
        _connections.discard(ws)
        logger.info(f"WebSocket 断开, 剩余连接: {len(_connections)}")


def _build_push_data() -> dict:
    """构建推送数据"""
    engine = get_engine()
    if not engine:
        return {"type": "status", "running": False, "stocks": []}

    status = engine.get_status()

    # 获取各股票最新价格
    stocks_data = []
    for code in status.get('stocks', []):
        config = engine._stock_grids.get(code, {})
        stocks_data.append({
            "stock_code": code,
            "last_price": config.get('last_price'),
            "market": config.get('market', ''),
        })

    return {
        "type": "status",
        "running": status['running'],
        "strategies_count": status['strategies_count'],
        "stocks": stocks_data,
    }


async def broadcast_message(message: dict):
    """向所有连接广播消息"""
    if not _connections:
        return
    text = json.dumps(message, ensure_ascii=False)
    dead = set()
    for ws in _connections:
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    _connections -= dead
