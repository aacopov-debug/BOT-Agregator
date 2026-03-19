import logging
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Optional, Any
from ..job_service import JobService

logger = logging.getLogger(__name__)


class ParserError(Exception):
    """Базовое исключение для ошибок парсера."""
    pass

class ParserBlockError(ParserError):
    """Исключение при блокировке IP (403, 429)."""
    pass

class BaseParser(ABC):
    """
    Абстрактный базовый класс для всех парсеров вакансий.
    """

    def __init__(self):
        self.name = self.__class__.__name__

    def _get_proxy(self) -> Optional[str]:
        """Вспомогательный метод для получения прокси из менеджера."""
        from ...utils.proxy_manager import proxy_manager

        return proxy_manager.get_proxy()

    async def _request_with_retry(
        self, method: str, url: str, retries: int = 3, return_type: str = "json", **kwargs
    ) -> Optional[Any]:
        """
        Выполняет HTTP-запрос с механизмом повторов при сетевых ошибках.
        Использует экспоненциальную задержку.
        """
        for i in range(retries):
            proxy = self._get_proxy()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method, url, proxy=proxy, timeout=20, **kwargs
                    ) as resp:
                        if resp.status in (403, 429):
                            raise ParserBlockError(
                                f"BLOCK: HTTP {resp.status} (Proxy: {proxy})"
                            )
                        if resp.status != 200:
                            raise ParserError(
                                f"ERROR: HTTP {resp.status} (Proxy: {proxy})"
                            )
                        
                        if return_type == "json":
                            return await resp.json()
                        return await resp.text()
            except ParserBlockError as e:
                # При блокировке помечаем прокси как плохой и пробуем следующий ретрай (с другим прокси)
                from ...utils.proxy_manager import proxy_manager

                if proxy:
                    proxy_manager.mark_failed(proxy)
                
                if i < retries - 1:
                    logger.warning(
                        f"🚫 {self.name} blocked on {proxy}. Retrying with another proxy... ({i + 1}/{retries})"
                    )
                    await asyncio.sleep(1)
                    continue
                else:
                    raise e
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                wait_time = (i + 1) * 2
                if i < retries - 1:
                    logger.warning(
                        f"⚠️ {self.name} network error: {e}. Retrying... ({i + 1}/{retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise ParserError(
                        f"NETWORK_FAILED after {retries} retries: {e} (Proxy: {proxy})"
                    )
            except Exception as e:
                if not isinstance(e, ParserError):
                    raise ParserError(f"Unexpected error: {e}")
                raise e
        return None

    async def _get_html(self, url: str, **kwargs) -> Optional[str]:
        """Удобная обертка для получения HTML."""
        return await self._request_with_retry("GET", url, return_type="text", **kwargs)

    @abstractmethod
    async def parse(self, job_service: JobService) -> int:
        """
        Основной метод парсинга.
        Должен вернуть количество новых добавленных вакансий.
        """
        pass

    def get_name(self) -> str:
        return self.name


class ParserRegistry:
    """
    Реестр всех доступных парсеров.
    """

    _parsers: List[BaseParser] = []

    @classmethod
    def register(cls, parser: BaseParser):
        cls._parsers.append(parser)
        logger.info(f"✅ Parser registered: {parser.get_name()}")

    @classmethod
    def get_all_parsers(cls) -> List[BaseParser]:
        return cls._parsers


# Глобальный экземпляр реестра
registry = ParserRegistry()
