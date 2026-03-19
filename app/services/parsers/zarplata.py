"""Парсер Zarplata.ru (zarplata.ru)."""

import asyncio
import logging
import re
import json
from typing import List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import aiohttp
from .base import BaseParser, registry
from ..job_service import JobService

logger = logging.getLogger(__name__)


class ZarplataParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.zarplata.ru"
        self.categories = {
            "python": "python",
            "frontend": "frontend",
            "backend": "backend",
            "devops": "devops",
            "qa": "qa",
            "data science": "data",
            "design": "дизайн",
        }
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        }

    async def parse(self, job_service: JobService) -> int:
        new_jobs_count = 0
        parsed_ids = set()

        for cat_name, query in self.categories.items():
            url = f"{self.base_url}/vacancy?q={query}&geo_id=0"
            html = await self._get_html(url, headers=self.headers)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            job_cards = soup.find_all(
                "a", href=re.compile(r"/vacancy/[0-9a-f-]{36}|/vacancy/\d+")
            )

            if not job_cards:
                script_tag = soup.find("script", id="__NEXT_DATA__")
                if script_tag:
                    try:
                        data = json.loads(script_tag.string)
                        vacancies = self._find_vacancies_in_json(data)
                        for vac in vacancies:
                            vac_id = str(vac.get("id", ""))
                            if vac_id in parsed_ids:
                                continue
                            parsed_ids.add(vac_id)
                            title = vac.get("header", "")
                            if vac.get("salary"):
                                title += f" {vac['salary']}"
                            desc_clean = (
                                BeautifulSoup(
                                    vac.get("description", ""), "html.parser"
                                )
                                .get_text(separator=" ")
                                .strip()
                            )
                            job = await job_service.add_job(
                                title=title[:255],
                                description=desc_clean[:5000],
                                link=f"{self.base_url}/vacancy/{vac_id}",
                                source="zarplata.ru",
                                category=self._detect_category_local(title),
                            )
                            if job:
                                new_jobs_count += 1
                        continue
                    except Exception:
                        pass

            for card in job_cards:
                href = card.get("href", "")
                if not href.startswith("/vacancy/"):
                    continue
                vac_id = href.split("/")[-1].split("?")[0]
                if vac_id in parsed_ids:
                    continue
                parsed_ids.add(vac_id)

                title_elem = card.find(
                    ["h2", "h3", "span"], class_=re.compile(r"title|name|header")
                )
                title = (
                    title_elem.get_text(strip=True)
                    if title_elem
                    else card.get_text(strip=True)
                )
                if not title or len(title) < 5:
                    continue

                salary_elem = card.find(string=re.compile(r"₽|руб"))
                if salary_elem:
                    title += f" {salary_elem.strip()}"
                desc_elem = card.find(["div", "p"], class_=re.compile(r"desc|text"))
                desc = (
                    desc_elem.get_text(separator=" ", strip=True)
                    if desc_elem
                    else "См. подробности по ссылке"
                )

                job = await job_service.add_job(
                    title=title[:255],
                    description=desc[:5000],
                    link=urljoin(self.base_url, href),
                    source="zarplata.ru",
                    category=self._detect_category_local(title),
                )
                if job:
                    new_jobs_count += 1
            await asyncio.sleep(2)
        return new_jobs_count

    def _find_vacancies_in_json(self, obj: Any) -> List[Dict]:
        vacancies = []
        if isinstance(obj, dict):
            if "vacancies" in obj and isinstance(obj["vacancies"], list):
                vacancies.extend(obj["vacancies"])
            elif (
                "list" in obj
                and isinstance(obj["list"], list)
                and len(obj["list"]) > 0
                and isinstance(obj["list"][0], dict)
                and "id" in obj["list"][0]
            ):
                vacancies.extend(obj["list"])
            else:
                for v in obj.values():
                    vacancies.extend(self._find_vacancies_in_json(v))
        elif isinstance(obj, list):
            for item in obj:
                vacancies.extend(self._find_vacancies_in_json(item))
        return vacancies

    def _detect_category_local(self, title: str) -> str:
        tl = title.lower()
        if "python" in tl:
            return "backend"
        if "frontend" in tl or "react" in tl:
            return "frontend"
        if "devops" in tl:
            return "devops"
        if "qa" in tl or "тестиров" in tl:
            return "qa"
        if "дизайн" in tl:
            return "design"
        return "other"


# Регистрация парсера
registry.register(ZarplataParser())
