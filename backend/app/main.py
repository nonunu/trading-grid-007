"""
FastAPI 应用入口
统一网格交易系统 API
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DB_PATH
from app.database import GridDatabase
from app.engine.trading_engine import TradingEngine
from app.api.deps import set_db, set_engine

logger = logging.getLogger(__name__)


# 过滤高频轮询接口的访问日志，避免刷屏
class _QuietHealthFilter(logging.Filter):
    """正常 200 响应的 API 请求不输出访问日志，只有非 200 响应才输出"""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # 所有正常的 200 请求都不打印
        if '200 OK' in msg:
            return False
        return True


logging.getLogger("uvicorn.access").addFilter(_QuietHealthFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("正在初始化交易系统...")

    db = GridDatabase(DB_PATH)
    set_db(db)
    logger.info(f"数据库已初始化: {DB_PATH}")

    engine = TradingEngine(db)
    set_engine(engine)
    logger.info("交易引擎已创建 (等待手动启动)")

    yield

    # 关闭时清理
    logger.info("正在关闭交易系统...")
    if engine.is_running():
        engine.stop()
    engine.disconnect()
    logger.info("交易系统已关闭")


app = FastAPI(
    title="Trading Grid Unified API",
    description="统一网格交易系统 - A股(miniQMT) + 港美股(FUTU OpenD)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
from app.api.configs import router as configs_router
from app.api.cells import router as cells_router
from app.api.engine import router as engine_router
from app.api.dashboard import router as dashboard_router
from app.api.grid_status import router as grid_status_router
from app.api.rescue import router as rescue_router
from app.api.ws import router as ws_router

app.include_router(configs_router)
app.include_router(cells_router)
app.include_router(engine_router)
app.include_router(dashboard_router)
app.include_router(grid_status_router)
app.include_router(rescue_router)
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "trading-grid-unified"}
