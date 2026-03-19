from aiogram import Router
from .admin import router as admin_router
from .broadcast import router as broadcast_router
from .hr_panel import router as hr_panel_router

router = Router()

router.include_routers(admin_router, broadcast_router, hr_panel_router)
