from aiogram import Router
from .profile import router as profile_router
from .favorites import router as favorites_router
from .tracker import router as tracker_router
from .achievements import router as achievements_router
from .referral import router as referral_router

router = Router()

router.include_routers(
    profile_router,
    favorites_router,
    tracker_router,
    achievements_router,
    referral_router,
)
