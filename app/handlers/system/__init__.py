from aiogram import Router

from .start import router as start_router
from .settings import router as settings_router
from .hubs import router as hubs_router
from .payments import router as payments_router
from .feedback import router as feedback_router
from .reminders import router as reminders_router
from .inline import router as inline_router
from .utils import router as utils_router
from .extra import router as extra_router
from .analytics import router as analytics_router
from .blacklist import router as blacklist_router
from .channel import router as channel_router

router = Router()

router.include_router(start_router)
router.include_router(settings_router)
router.include_router(hubs_router)
router.include_router(payments_router)
router.include_router(feedback_router)
router.include_router(reminders_router)
router.include_router(inline_router)
router.include_router(utils_router)
router.include_router(extra_router)
router.include_router(analytics_router)
router.include_router(blacklist_router)
router.include_router(channel_router)
