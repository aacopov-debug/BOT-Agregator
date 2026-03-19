"""Парсер вакансий с Habr Career через веб-скрапинг."""

import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class HabrParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://career.habr.com"
        self.queries = [
            "/vacancies?type=all&sort=date&s[]=2",  # Разработка
            "/vacancies?type=all&sort=date&s[]=3",  # Тестирование
            "/vacancies?type=all&sort=date&s[]=82",  # DevOps
            "/vacancies?type=all&sort=date&s[]=4",  # Дизайн
            "/vacancies?type=all&sort=date&s[]=6",  # Аналитика
        ]

    async def parse(self, job_service: JobService) -> int:
        total_new = 0
        for query in self.queries:
            url = self.base_url + query
            jobs = await self._scrape_page(url)
            for job_data in jobs:
                job_data["category"] = detect_category(
                    job_data["title"], job_data["description"]
                )
                job = await job_service.add_job(**job_data)
                if job:
                    total_new += 1
            await asyncio.sleep(2)
        return total_new

    async def _scrape_page(self, url: str) -> list:
        jobs_found = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
                            f"❌ Habr BAN IP: HTTP {resp.status} for {url} (Proxy: {proxy})"
                        )
                        return []
                    if resp.status != 200:
                        logger.warning(
                            f"Habr Career Career: HTTP {resp.status} for {url}"
                        )
                        return []
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            cards = soup.find_all("div", class_="vacancy-card")

            for card in cards[:15]:
                title_tag = card.find("a", class_="vacancy-card__title-link")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)[:255]
                link = self.base_url + title_tag.get("href", "")

                company_tag = card.find("a", class_="vacancy-card__company-title")
                company = company_tag.get_text(strip=True) if company_tag else ""

                salary_tag = card.find("div", class_="vacancy-card__salary")
                salary = salary_tag.get_text(strip=True) if salary_tag else ""

                meta_tag = card.find("div", class_="vacancy-card__meta")
                meta = (
                    meta_tag.get_text(separator=" · ", strip=True) if meta_tag else ""
                )

                skills_tags = card.find_all("a", class_="vacancy-card__skill-tag")
                skills = ", ".join([s.get_text(strip=True) for s in skills_tags[:5]])

                description = f"Компания: {company}\n{salary}\n{meta}\nНавыки: {skills}"

                jobs_found.append(
                    {
                        "title": title,
                        "description": description[:2000],
                        "link": link,
                        "source": "habr.career",
                    }
                )
        except Exception as e:
            logger.error(f"Habr Career error: {e}")

        return jobs_found


# Регистрация парсера
registry.register(HabrParser())
