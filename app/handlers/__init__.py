# Импорт роутеров из поддиректорий
from .admin import router as admin_router
from .admin.parser_stats import router as parser_stats_router
from .discovery import router as discovery_router
from .cabinet import router as cabinet_router
from .ai import router as ai_router
from .system import router as system_router


def register_handlers(dp):
    """Регистрирует все роутеры в диспетчере."""
    dp.include_router(admin_router)
    dp.include_router(parser_stats_router)
    dp.include_router(discovery_router)
    dp.include_router(cabinet_router)
    dp.include_router(ai_router)
    dp.include_router(system_router)
