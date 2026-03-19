from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union, Optional
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str = "sqlite+aiosqlite:///jobs.db"
    REDIS_URL: str = ""
    CHANNELS_TO_PARSE: Union[List[str], str] = []
    PARSE_INTERVAL_SECONDS: int = 900
    ADMIN_ID: Optional[int] = None
    # Опциональные (оставлены для обратной совместимости)
    API_ID: Optional[int] = None
    API_HASH: Optional[str] = None

    # Proxy Settings
    USE_PROXIES: bool = False
    PROXY_LIST: Union[List[str], str] = []  # Список в формате http://user:pass@ip:port

    # AI
    GEMINI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ELEVENLABS_API_KEY: Optional[str] = None
    AI_MODEL: str = "google/gemini-2.0-flash-001"  # Актуальный ID модели на OpenRouter

    # Web Dashboard Auth
    DASHBOARD_USER: str = "admin"
    DASHBOARD_PASS: str = "admin"

    # Social/Subscription Logic
    REQUIRED_CHANNEL_ID: Optional[Union[int, str]] = None  # Например: -100123456789
    REQUIRED_CHANNEL_LINK: str = "https://t.me/arbot_channel"

    # YooMoney Monetization
    YOOMONEY_TOKEN: Optional[str] = None
    YOOMONEY_WALLET: Optional[str] = None

    @field_validator("CHANNELS_TO_PARSE", mode="before")
    @classmethod
    def parse_channels(cls, v):
        if isinstance(v, str):
            return [str(item).strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("PROXY_LIST", mode="before")
    @classmethod
    def parse_proxies(cls, v):
        if isinstance(v, str):
            return [str(item).strip() for item in v.split(",") if item.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

settings = Settings()
