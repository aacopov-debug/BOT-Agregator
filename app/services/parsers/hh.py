"""Парсер вакансий с hh.ru через публичный API."""

import asyncio
import logging
import aiohttp
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class HHParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.api_url = "https://api.hh.ru/vacancies"
        self.request_delay = 1.0
        self.queries = [
            "Python разработчик",
            "Frontend разработчик",
            "Backend разработчик",
            "DevOps инженер",
            "QA тестировщик",
            "Java разработчик",
            "Go разработчик",
            "Data Scientist",
            "Mobile разработчик",
            "React разработчик",
        ]

    async def parse(self, job_service: JobService) -> int:
        total_new = 0
        for query in self.queries:
            jobs = await self._fetch_vacancies(query, per_page=10)
            for job_data in jobs:
                job_data["category"] = detect_category(
                    job_data["title"], job_data["description"]
                )
                job = await job_service.add_job(**job_data)
                if job:
                    total_new += 1
            await asyncio.sleep(self.request_delay)
        return total_new

    async def _fetch_vacancies(self, query: str, per_page: int = 20) -> list:
        params = {
            "text": query,
            "per_page": per_page,
            "order_by": "publication_time",
            "area": 113,  # Россия
        }
        headers = {"User-Agent": "TelegramJobBot/1.0"}

        for attempt in range(3):
            try:
                proxy = self._get_proxy()
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.api_url,
                        params=params,
                        headers=headers,
                        proxy=proxy,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        if resp.status == 429:
                            wait = 5 * (attempt + 1)
                            logger.warning(
                                f"hh.ru rate limit, ждём {wait}с... (Proxy: {proxy})"
                            )
                            await asyncio.sleep(wait)
                            continue
                        if resp.status != 200:
                            logger.warning(
                                f"hh.ru API: HTTP {resp.status} (Proxy: {proxy})"
                            )
                            return []
                        data = await resp.json()
                break
            except Exception as e:
                logger.error(f"hh.ru fetch error: {e}")
                return []
        else:
            return []

        jobs = []
        for item in data.get("items", []):
            salary_text = ""
            if item.get("salary"):
                s = item["salary"]
                currency = s.get("currency", "")
                if s.get("from") and s.get("to"):
                    salary_text = f"💰 {s['from']}–{s['to']} {currency}"
                elif s.get("from"):
                    salary_text = f"💰 от {s['from']} {currency}"
                elif s.get("to"):
                    salary_text = f"💰 до {s['to']} {currency}"

            employer = item.get("employer", {}).get("name", "")
            area = item.get("area", {}).get("name", "")
            experience = item.get("experience", {}).get("name", "")
            schedule = item.get("schedule", {}).get("name", "")

            description = (
                f"Компания: {employer}\n"
                f"Город: {area}\n"
                f"Опыт: {experience}\n"
                f"График: {schedule}\n"
                f"{salary_text}"
            ).strip()

            jobs.append(
                {
                    "title": item.get("name", "Без названия")[:255],
                    "description": description[:2000],
                    "link": item.get("alternate_url", ""),
                    "source": "hh.ru",
                }
            )
        return jobs


# Регистрация парсера
registry.register(HHParser())
