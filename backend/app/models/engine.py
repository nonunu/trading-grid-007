"""
引擎状态 Pydantic 模型
"""

from typing import List
from pydantic import BaseModel


class EngineStatus(BaseModel):
    """引擎状态"""
    running: bool
    strategies_count: int
    stocks: List[str]


class EngineAction(BaseModel):
    """引擎操作响应"""
    success: bool
    message: str = ""
