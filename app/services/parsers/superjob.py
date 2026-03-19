"""Парсер вакансий с SuperJob.ru через API."""

import asyncio
import logging
import aiohttp
from bs4 import BeautifulSoup
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class SuperJobParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.superjob.ru"
        self.categories = [
            "/vakansii?keywords=it",
            "/vakansii?keywords=python",
            "/vakansii?keywords=frontend",
            "/vakansii?keywords=qa",
            "/vakansii?keywords=devops",
            "/vakansii?keywords=design",
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
                            f"❌ SuperJob BAN IP: HTTP {resp.status} for {url} (Proxy: {proxy})"
                        )
                        return []
                    if resp.status != 200:
                        logger.warning(f"SuperJob: HTTP {resp.status} for {url}")
                        return []
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            cards = (
                soup.find_all("div", class_="f-test-search-result-item")
                or soup.find_all("div", attrs={"data-marker": True})
                or soup.find_all("a", class_="icMQ_")
            )

            for card in cards[:15]:
                title_tag = card.find("a") or card.find("span", class_="")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)[:255]
                if not title or len(title) < 5:
                    continue

                href = title_tag.get("href", "") if title_tag.name == "a" else ""
                if href.startswith("/"):
                    href = self.base_url + href

                salary_tag = card.find("span", class_="f-test-text-company-item-salary")
                salary = salary_tag.get_text(strip=True) if salary_tag else ""

                company_tag = card.find(
                    "span", class_="f-test-text-company-item-company-name"
                )
                company = company_tag.get_text(strip=True) if company_tag else ""

                desc_parts = [salary, company]
                desc_tag = card.find(
                    "div", class_="f-test-text-company-item-description"
                )
                if desc_tag:
                    desc_parts.append(desc_tag.get_text(strip=True)[:400])

                jobs_found.append(
                    {
                        "title": title,
                        "description": "\n".join([p for p in desc_parts if p])[:2000],
                        "link": href,
                        "source": "superjob.ru",
                    }
                )
        except Exception as e:
            logger.error(f"SuperJob error: {e}")

        return jobs_found


# Регистрация парсера
registry.register(SuperJobParser())
