import random
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from ..config import settings

logger = logging.getLogger(__name__)


class ProxyManager:
    """
    Управляет списком прокси для парсеров.
    Реализует временное исключение (blacklisting) заблокированных прокси.
    """

    def __init__(self):
        self.proxies: List[str] = (
            settings.PROXY_LIST if isinstance(settings.PROXY_LIST, list) else []
        )
        self.use_proxies = settings.USE_PROXIES
        self._bad_proxies: Dict[str, datetime] = {}  # proxy -> expire_at

        if self.use_proxies and not self.proxies:
            logger.warning("⚠️ USE_PROXIES is True, but PROXY_LIST is empty!")

    def get_proxy(self) -> Optional[str]:
        """Возвращает случайный прокси из списка доступных."""
        if not self.use_proxies or not self.proxies:
            return None

        # Очистка старых "плохих" прокси
        now = datetime.now()
        self._bad_proxies = {
            p: exp for p, exp in self._bad_proxies.items() if exp > now
        }

        # Фильтрация
        available = [p for p in self.proxies if p not in self._bad_proxies]
        
        if not available:
            # Если все прокси заблокированы — пробуем любой, вдруг какой-то ожил
            logger.warning("⚠️ All proxies are in blacklist! Using random one.")
            return random.choice(self.proxies)

        return random.choice(available)

    def mark_failed(self, proxy: str, duration_minutes: int = 30):
        """Временно исключает прокси из ротации."""
        if not proxy:
            return
        expire_at = datetime.now() + timedelta(minutes=duration_minutes)
        self._bad_proxies[proxy] = expire_at
        logger.warning(f"🚫 Proxy {proxy} blacklisted for {duration_minutes}m")


# Глобальный экземпляр
proxy_manager = ProxyManager()
