"""Парсер заказов с FL.ru через веб-скрапинг."""

import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class FLParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.fl.ru"
        self.categories = [
            "/projects/?kind=1&category=5",  # Программирование
            "/projects/?kind=1&category=3",  # Веб-разработка
            "/projects/?kind=1&category=15",  # Мобильная разработка
            "/projects/?kind=1&category=10",  # Дизайн
            "/projects/?kind=1&category=19",  # Тестирование
            "/projects/?kind=1&category=23",  # Администрирование
        ]

    async def parse(self, job_service: JobService) -> int:
        total_new = 0
        for cat_url in self.categories:
            url = self.base_url + cat_url
            jobs = await self._scrape_page(url)
            for job_data in jobs:
                job_data["category"] = detect_category(
                    job_data["title"], job_data["description"]
                )
                job = await job_service.add_job(**job_data)
                if job:
                    total_new += 1
            await asyncio.sleep(3)
        return total_new

    async def _scrape_page(self, url: str) -> list:
        jobs_found = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }

        try:
            proxy = self._get_proxy()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status in (403, 429):
                        logger.error(
                            f"❌ FL.ru BAN IP: HTTP {resp.status} for {url} (Proxy: {proxy})"
                        )
                        return []
                    if resp.status != 200:
                        logger.warning(f"FL.ru: HTTP {resp.status} for {url}")
                        return []
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            cards = (
                soup.find_all("div", class_="b-post")
                or soup.find_all("div", class_="b-post__grid")
                or soup.find_all("article")
            )

            for card in cards[:15]:
                title_tag = (
                    card.find("a", class_="b-post__link")
                    or card.find("h2")
                    or card.find("a", href=True)
                )
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)[:255]
                if not title or len(title) < 5:
                    continue

                href = title_tag.get("href", "")
                link = (
                    self.base_url + href
                    if href.startswith("/")
                    else (href if href.startswith("http") else "")
                )

                price_tag = (
                    card.find("div", class_="b-post__price")
                    or card.find("span", class_="b-post__bold")
                    or card.find("div", class_="text-6")
                )
                price = price_tag.get_text(strip=True) if price_tag else ""

                desc_tag = (
                    card.find("div", class_="b-post__txt")
                    or card.find("div", class_="b-post__body")
                    or card.find("p")
                )
                desc_text = desc_tag.get_text(strip=True)[:500] if desc_tag else ""

                tags = card.find_all("a", class_="b-post__tag")
                skills = ", ".join([t.get_text(strip=True) for t in tags[:5]])

                description = f"{price}\n{desc_text}"
                if skills:
                    description += f"\nНавыки: {skills}"

                jobs_found.append(
                    {
                        "title": title,
                        "description": description.strip()[:2000],
                        "link": link,
                        "source": "fl.ru",
                    }
                )
        except Exception as e:
            logger.error(f"FL.ru error: {e}")

        return jobs_found


# Регистрация парсера
registry.register(FLParser())
