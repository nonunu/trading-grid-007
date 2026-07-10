"""
API 依赖注入
提供 db 和 engine 的全局访问
"""

from typing import Optional

from app.database import GridDatabase
from app.engine.trading_engine import TradingEngine

# 全局实例 (在 main.py lifespan 中初始化)
_db: Optional[GridDatabase] = None
_engine: Optional[TradingEngine] = None


def set_db(db: GridDatabase):
    global _db
    _db = db


def get_db() -> GridDatabase:
    if _db is None:
        raise RuntimeError("数据库未初始化")
    return _db


def set_engine(engine: TradingEngine):
    global _engine
    _engine = engine


def get_engine() -> Optional[TradingEngine]:
    return _engine
