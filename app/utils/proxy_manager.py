import random
import logging
from typing import List, Optional
from ..config import settings

logger = logging.getLogger(__name__)


class ProxyManager:
    """
    Управляет списком прокси для парсеров.
    """

    def __init__(self):
        self.proxies: List[str] = (
            settings.PROXY_LIST if isinstance(settings.PROXY_LIST, list) else []
        )
        self.use_proxies = settings.USE_PROXIES

        if self.use_proxies and not self.proxies:
            logger.warning("⚠️ USE_PROXIES is True, but PROXY_LIST is empty!")

    def get_proxy(self) -> Optional[str]:
        """Возвращает случайный прокси из списка или None."""
        if not self.use_proxies or not self.proxies:
            return None
        return random.choice(self.proxies)

    def mark_failed(self, proxy: str):
        """Здесь можно реализовать логику временного исключения плохих прокси."""
        logger.warning(f"Proxy failed: {proxy}")


# Глобальный экземпляр
proxy_manager = ProxyManager()
