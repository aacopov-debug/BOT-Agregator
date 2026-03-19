"""Парсер вакансий и заданий с Work-Zilla.com."""

import logging
import aiohttp
from bs4 import BeautifulSoup
from .base import BaseParser, registry
from ..job_service import JobService
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)


class WorkZillaParser(BaseParser):
    def __init__(self):
        super().__init__()
        self.base_url = "https://work-zilla.com"
        # API для разовых заданий
        self.api_url = "https://work-zilla.com/api/server-side-tasks/v1/list"
        # Страница для долгосрочных вакансий
        self.vacancies_url = "https://work-zilla.com/vacancies"

    async def parse(self, job_service: JobService) -> int:
        total_new = 0

        # 1. Парсим разовые задания через API
        tasks = await self._fetch_api_tasks()
        for task_data in tasks:
            task_data["category"] = detect_category(
                task_data["title"], task_data["description"]
            )
            # На Work-Zilla много не-IT задач, фильтруем
            if task_data["category"] != "other":
                job = await job_service.add_job(**task_data)
                if job:
                    total_new += 1

        # 2. Парсим долгосрочные вакансии через HTML
        vacancies = await self._fetch_html_vacancies()
        for vac_data in vacancies:
            vac_data["category"] = detect_category(
                vac_data["title"], vac_data["description"]
            )
            if vac_data["category"] != "other":
                job = await job_service.add_job(**vac_data)
                if job:
                    total_new += 1

        return total_new

    async def _fetch_api_tasks(self) -> list:
        params = {"skipCount": 0, "takeCount": 50}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        tasks_found = []

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
                    if resp.status in (403, 429):
                        logger.error(
                            f"❌ Work-Zilla BAN IP (API): HTTP {resp.status} (Proxy: {proxy})"
                        )
                        return []
                    if resp.status != 200:
                        logger.warning(f"Work-Zilla API: HTTP {resp.status}")
                        return []
                    data = await resp.json()

            if not isinstance(data, dict):
                logger.warning(f"Work-Zilla API: Expected dict, got {type(data)}")
                return []

            task_list = data.get("data", {}).get("Data", [])
            if not isinstance(task_list, list):
                # Пробуем другой путь, если структура изменилась
                task_list = data.get("tasks", []) or data.get("items", [])

            logger.debug(f"Work-Zilla API: Found {len(task_list)} items")

            for item in task_list:
                title = item.get("Subject", "")
                price = item.get("Price", 0)
                desc = item.get("Description", "")
                task_id = item.get("Id")

                if not title or not task_id:
                    continue

                tasks_found.append(
                    {
                        "title": title[:255],
                        "description": f"💰 Бюджет: {price} ₽\n\n{desc}"[:2000],
                        "link": f"{self.base_url}/tasks/{task_id}",
                        "source": "work-zilla.com",
                    }
                )
        except Exception as e:
            logger.error(f"Work-Zilla API error: {e}")

        return tasks_found

    async def _fetch_html_vacancies(self) -> list:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        vacs_found = []

        try:
            proxy = self._get_proxy()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.vacancies_url,
                    headers=headers,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status in (403, 429):
                        logger.error(
                            f"❌ Work-Zilla BAN IP (HTML): HTTP {resp.status} (Proxy: {proxy})"
                        )
                        return []
                    if resp.status != 200:
                        logger.warning(f"Work-Zilla HTML: HTTP {resp.status}")
                        return []
                    html = await resp.text()

            soup = BeautifulSoup(html, "html.parser")
            # Более гибкий поиск карточек: ссылки, содержащие /vacancies/
            cards = soup.find_all("a", href=lambda h: h and "/vacancies/" in h)
            logger.debug(f"Work-Zilla HTML: Found {len(cards)} cards")

            for card in cards:
                # Внутренняя структура может меняться, ищем по порядку div-ы
                divs = card.find_all("div", recursive=False)
                # Если div-ы вложены глубже (например, в один общий div), ищем их там
                if not divs and card.div:
                    divs = card.div.find_all("div", recursive=False)

                title = ""
                salary = ""
                description = ""

                if len(divs) >= 1:
                    title = divs[0].get_text(strip=True)
                if len(divs) >= 2:
                    salary = divs[1].get_text(strip=True)
                if len(divs) >= 3:
                    description = divs[2].get_text(strip=True)

                # Запасной вариант по классам, если div-ы не сработали
                if not title:
                    title_el = card.select_one(".vacancy-title")
                    title = title_el.get_text(strip=True) if title_el else ""

                link = card.get("href", "")
                if not title or len(title) < 5 or not link:
                    continue

                if link and not link.startswith("http"):
                    link = self.base_url + link

                vacs_found.append(
                    {
                        "title": title[:255],
                        "description": f"💰 Зарплата: {salary}\n\n{description}"[:2000],
                        "link": link,
                        "source": "work-zilla.com",
                    }
                )
        except Exception as e:
            logger.error(f"Work-Zilla HTML error: {e}")

        return vacs_found


# Регистрация парсера
registry.register(WorkZillaParser())
