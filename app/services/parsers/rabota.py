"""Парсер вакансий с Rabota.ru."""

import asyncio
import logging
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class RabotaParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.rabota.ru"
        self.api_url = (
            "https://www.rabota.ru/api-web/v5/vacancies/search_with_similar.json"
        )
        self.queries = ["Python", "разработчик", "IT", "Backend", "Frontend"]

    async def parse(self, job_service: JobService) -> int:
        total_new = 0
        for query in self.queries:
            jobs = await self._fetch_api(query)
            for job_data in jobs:
                job_data["category"] = detect_category(
                    job_data["title"], job_data["description"]
                )
                job = await job_service.add_job(**job_data)
                if job:
                    total_new += 1
            await asyncio.sleep(2)
        return total_new

    async def _fetch_api(self, query: str, limit: int = 20) -> list:
        headers = {
            "Content-Type": "application/json",
            "Application-Id": "13",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        }
        payload = {
            "request": {
                "query": query,
                "limit": limit,
                "offset": 0,
                "sort": {"field": "relevance", "direction": "desc"},
                "fields": [
                    "vacancies.id",
                    "vacancies.title",
                    "vacancies.salary",
                    "vacancies.description",
                    "vacancies.company",
                ],
            },
            "application_id": 13,
        }

        jobs_found = []
        data = await self._request_with_retry(
            "POST", self.api_url, headers=headers, json=payload
        )

        if not data or not isinstance(data, dict):
            return []

        response = data.get("response")
        if not isinstance(response, dict):
            response = {}

        vacancies = response.get("vacancies")
        if not isinstance(vacancies, list):
            vacancies = []

        for v in vacancies:
            if not isinstance(v, dict):
                continue

            salary_data = v.get("salary")
            if not isinstance(salary_data, dict):
                salary_data = {}

            s_from, s_to, curr = (
                salary_data.get("from"),
                salary_data.get("to"),
                salary_data.get("currency", "руб."),
            )
            salary = (
                f"от {s_from} до {s_to} {curr}"
                if s_from and s_to
                else (
                    f"от {s_from} {curr}"
                    if s_from
                    else (f"до {s_to} {curr}" if s_to else "З/П не указана")
                )
            )

            comp_data = v.get("company")
            if not isinstance(comp_data, dict):
                comp_data = {}
            company = comp_data.get("name", "Компания не указана")

            short_desc = v.get("description", "") or ""
            short_desc = short_desc.replace("<p>", "").replace("</p>", " ").strip()
            job_id = v.get("id")
            jobs_found.append(
                {
                    "title": v.get("title", "Без названия")[:255],
                    "description": f"🏢 {company}\n💰 {salary}\n\n📝 {short_desc}"[
                        :2000
                    ],
                    "link": f"{self.base_url}/vacancy/{job_id}" if job_id else "",
                    "source": "rabota.ru",
                }
            )
        return jobs_found


# Регистрация парсера
registry.register(RabotaParser())
