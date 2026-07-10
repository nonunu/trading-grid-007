from app.api.configs import router as configs_router
from app.api.cells import router as cells_router
from app.api.engine import router as engine_router
from app.api.dashboard import router as dashboard_router
from app.api.ws import router as ws_router

__all__ = [
    'configs_router',
    'cells_router',
    'engine_router',
    'dashboard_router',
    'ws_router',
]
