"""
交易引擎控制 API
启动/停止/状态查询
"""

from fastapi import APIRouter, HTTPException

from app.models.engine import EngineStatus, EngineAction
from app.api.deps import get_engine

router = APIRouter(prefix="/api/engine", tags=["engine"])


@router.get("/status", response_model=EngineStatus)
async def engine_status():
    """获取引擎状态"""
    engine = get_engine()
    if not engine:
        return EngineStatus(running=False, strategies_count=0, stocks=[])
    status = engine.get_status()
    return EngineStatus(**status)


@router.post("/start", response_model=EngineAction)
async def engine_start():
    """启动交易引擎"""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="引擎未初始化")

    if engine.is_running():
        return EngineAction(success=False, message="引擎已在运行")

    success = engine.start()
    if success:
        return EngineAction(success=True, message="引擎启动成功")
    else:
        return EngineAction(success=False, message="引擎启动失败，请查看日志")


@router.post("/stop", response_model=EngineAction)
async def engine_stop():
    """停止交易引擎"""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="引擎未初始化")

    if not engine.is_running():
        return EngineAction(success=False, message="引擎未在运行")

    success = engine.stop()
    if success:
        return EngineAction(success=True, message="引擎已停止")
    else:
        return EngineAction(success=False, message="停止失败")


@router.post("/reload")
async def engine_reload(stock_code: str = None):
    """通知引擎重新加载数据"""
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="引擎未初始化")

    engine.reload_data(stock_code)
    return {"message": "数据已重新加载"}
