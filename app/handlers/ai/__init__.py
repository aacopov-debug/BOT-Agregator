from aiogram import Router
from .resume import router as resume_router
from .cover_letter import router as cover_letter_router
from .interview import router as interview_router
from .job_chat import router as job_chat_router
from .recommend import router as recommend_router
from .voice import router as voice_router

router = Router()

router.include_routers(
    resume_router,
    cover_letter_router,
    interview_router,
    job_chat_router,
    recommend_router,
    voice_router,
)
