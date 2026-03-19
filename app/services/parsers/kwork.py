"""Парсер заказов/вакансий с Kwork.ru через window.stateData."""

import asyncio
import logging
import re
import json
import aiohttp
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class KworkParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://kwork.ru"
        self.pages = [
            "/projects?c=41",  # Разработка сайтов
            "/projects?c=42",  # Мобильные приложения
            "/projects?c=79",  # Программирование
            "/projects?c=155",  # Базы данных/ML
        ]
        self.state_data_re = re.compile(
            r"window\.stateData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL
        )

    async def parse(self, job_service: JobService) -> int:
        total_new = 0
        for cat_url in self.pages:
            url = self.base_url + cat_url
            jobs = await self._scrape_page(url)
            for job_data in jobs:
                job_data["category"] = detect_category(
                    job_data["title"], job_data["description"]
                )
                job = await job_service.add_job(**job_data)
                if job:
                    total_new += 1
            await asyncio.sleep(4)  # Kwork строгий к ботам
        return total_new

    async def _scrape_page(self, url: str) -> list:
        jobs_found = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
        }

        try:
            proxy = self._get_proxy()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as resp:
                    if resp.status in (403, 429):
                        logger.error(
                            f"❌ Kwork BAN IP: HTTP {resp.status} for {url} (Proxy: {proxy})"
                        )
                        return []
                    if resp.status != 200:
                        logger.warning(f"Kwork: HTTP {resp.status} for {url}")
                        return []
                    html = await resp.text()

            match = self.state_data_re.search(html) or re.search(
                r"window\.stateData\s*=\s*(\{.+?\})\s*;", html, re.DOTALL
            )
            if not match:
                return []

            raw_json = match.group(1)
            try:
                state_data = json.loads(raw_json)
            except json.JSONDecodeError:
                state_data = json.loads(raw_json.replace("'", '"'))

            projects = []
            for key_path in [
                lambda d: d.get("wants", []),
                lambda d: d.get("wantsData", {}).get("data", []),
                lambda d: d.get("projects", []),
                lambda d: d.get("data", {}).get("wants", []),
            ]:
                try:
                    result = key_path(state_data)
                    if result and isinstance(result, list):
                        projects = result
                        break
                except Exception:
                    continue

            if not projects:
                projects = self._find_projects_recursive(state_data)

            for item in projects[:20]:
                if not isinstance(item, dict):
                    continue
                title = (
                    item.get("name") or item.get("title") or item.get("want_name") or ""
                )
                if not title or len(title) < 5:
                    continue

                link = item.get("url") or item.get("link") or ""
                want_id = item.get("id") or item.get("want_id")
                if not link and want_id:
                    link = f"{self.base_url}/projects/{want_id}"
                elif link and not link.startswith("http"):
                    link = self.base_url + link

                price = (
                    item.get("priceLimit")
                    or item.get("price")
                    or item.get("possiblePriceLimit")
                    or ""
                )
                price_str = f"💰 до {price} ₽" if price else ""
                desc = item.get("description") or item.get("desc") or ""

                jobs_found.append(
                    {
                        "title": title[:255],
                        "description": f"{price_str}\n{desc}".strip()[:2000],
                        "link": link,
                        "source": "kwork.ru",
                    }
                )
        except Exception as e:
            logger.error(f"Kwork error: {e}")
        return jobs_found

    def _find_projects_recursive(self, data, depth=0) -> list:
        if depth > 5:
            return []
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict) and any(
                k in first for k in ("name", "title", "want_name", "priceLimit")
            ):
                return data
        if isinstance(data, dict):
            for key, value in data.items():
                res = self._find_projects_recursive(value, depth + 1)
                if res:
                    return res
        return []


# Регистрация парсера
registry.register(KworkParser())
