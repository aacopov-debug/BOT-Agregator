from aiogram import Router
from .jobs import router as jobs_router
from .search import router as search_router
from .city_compare import router as city_compare_router
from .market import router as market_router

router = Router()

router.include_routers(jobs_router, search_router, city_compare_router, market_router)
