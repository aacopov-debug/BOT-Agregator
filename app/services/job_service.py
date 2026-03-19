import re
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from ..models.job import Job
from ..models.favorite import Favorite
from ..utils.hash import generate_job_hash
from typing import Optional, List

log = logging.getLogger(__name__)


def _sanitize_query(query: str) -> str:
    """Очищает пользовательский ввод для SQL LIKE."""
    query = query.strip()[:100]
    query = re.sub(r"[%_\\]", "", query)
    return query


class JobService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_job(
        self,
        title: str,
        description: str,
        link: str,
        source: str,
        category: Optional[str] = None,
    ) -> Optional[Job]:
        """Добавляет вакансию, если её нет (проверка по хешу)."""
        if not link or len(link) < 5:
            # Не добавляем вакансии без ссылок
            return None

        job_hash = generate_job_hash(title, description)

        stmt = select(Job).where(Job.job_hash == job_hash)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none():
            return None

        # Улучшенная дедупликация: совпадение title и source за последние 3 дня
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        stmt_dedup = (
            select(Job.id)
            .where(Job.title == title, Job.source == source, Job.created_at >= cutoff)
            .limit(1)
        )
        if (await self.session.execute(stmt_dedup)).scalar_one_or_none():
            return None

        new_job = Job(
            title=title,
            description=description,
            link=link,
            source=source,
            category=category or "other",
            job_hash=job_hash,
        )
        self.session.add(new_job)
        try:
            await self.session.commit()
            await self.session.refresh(new_job)
        except Exception as e:
            await self.session.rollback()
            log.warning(f"Failed to save job (likely duplicate): {title} - {e}")
            return None

        return new_job

    async def get_latest_jobs(self, limit: int = 10) -> List[Job]:
        stmt = (
            select(Job)
            .order_by(Job.is_promoted.desc().nulls_last(), Job.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_jobs(self) -> int:
        stmt = select(func.count(Job.id))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_jobs_page(self, page: int = 0, per_page: int = 5) -> List[Job]:
        stmt = (
            select(Job)
            .order_by(Job.is_promoted.desc().nulls_last(), Job.created_at.desc())
            .offset(page * per_page)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_job_by_id(self, job_id: int) -> Optional[Job]:
        stmt = select(Job).where(Job.id == job_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def promote_job(self, job_id: int) -> bool:
        """Помечает вакансию как продвигаемую."""
        job = await self.get_job_by_id(job_id)
        if job:
            job.is_promoted = True
            await self.session.commit()
            return True
        return False

    async def search_jobs(self, query: str, limit: int = 20) -> List[Job]:
        """Поиск с FTS5 (Full-Text Search) или fallback на LIKE."""
        clean_q = query.strip()
        if not clean_q:
            return []

        # Парсинг зарплаты (например: >100000 или > 150000)
        min_salary = None
        salary_match = re.search(r">\s*(\d+)", clean_q)
        if salary_match:
            min_salary = int(salary_match.group(1))
            clean_q = re.sub(r">\s*\d+", "", clean_q).strip()

        if not clean_q and min_salary is None:
            return []

        # Поиск через ILIKE
        import time

        t0 = time.time()
        res = await self._search_like(clean_q, min_salary, limit)
        duration = time.time() - t0
        log.info(f"🔎 PostgreSQL Search for '{clean_q}' took {duration:.4f}s")
        return res

    async def _search_like(self, query: str, min_salary, limit: int) -> List[Job]:
        """Медленный fallback-поиск через LIKE (SQL)."""
        from sqlalchemy import or_, and_, not_

        stmt = select(Job)
        tokens = query.split() if query else []
        has_logical = any(t in ("AND", "OR", "NOT") for t in tokens)

        if query:
            if not has_logical:
                conds = []
                for token in tokens:
                    cl = _sanitize_query(token)
                    if cl:
                        conds.append(
                            or_(
                                Job.title.ilike(f"%{cl}%"),
                                Job.description.ilike(f"%{cl}%"),
                            )
                        )
                if conds:
                    stmt = stmt.where(and_(*conds))
            else:
                words_and = []
                words_not = []
                words_or = []
                current_op = "AND"
                for token in tokens:
                    if token in ("AND", "OR", "NOT"):
                        current_op = token
                        continue
                    cl = _sanitize_query(token)
                    if not cl:
                        continue
                    cond = or_(
                        Job.title.ilike(f"%{cl}%"), Job.description.ilike(f"%{cl}%")
                    )
                    if current_op == "AND":
                        words_and.append(cond)
                    elif current_op == "OR":
                        words_or.append(cond)
                    elif current_op == "NOT":
                        words_not.append(not_(cond))
                        current_op = "AND"
                final_conds = []
                if words_and:
                    final_conds.append(and_(*words_and))
                if words_not:
                    final_conds.append(and_(*words_not))
                if words_or and final_conds:
                    stmt = stmt.where(or_(and_(*final_conds), *words_or))
                elif words_or:
                    stmt = stmt.where(or_(*words_or))
                elif final_conds:
                    stmt = stmt.where(and_(*final_conds))

        # Фильтр по зарплате
        if min_salary is not None:
            stmt = stmt.where(Job.description.ilike(f"%{min_salary}%"))

        stmt = stmt.order_by(
            Job.is_promoted.desc().nulls_last(), Job.created_at.desc()
        ).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_jobs_by_category(self, category: str, limit: int = 10) -> List[Job]:
        stmt = (
            select(Job)
            .where(Job.category == category)
            .order_by(Job.is_promoted.desc().nulls_last(), Job.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_source(self) -> dict:
        stmt = select(Job.source, func.count(Job.id)).group_by(Job.source)
        result = await self.session.execute(stmt)
        return dict(result.all())

    async def count_by_category(self) -> dict:
        stmt = select(Job.category, func.count(Job.id)).group_by(Job.category)
        result = await self.session.execute(stmt)
        return dict(result.all())

    # === Избранное ===

    async def add_favorite(self, telegram_id: int, job_id: int) -> bool:
        existing = await self.session.execute(
            select(Favorite).where(
                Favorite.user_telegram_id == telegram_id, Favorite.job_id == job_id
            )
        )
        if existing.scalar_one_or_none():
            return False
        fav = Favorite(user_telegram_id=telegram_id, job_id=job_id)
        self.session.add(fav)
        await self.session.commit()
        return True

    async def remove_favorite(self, telegram_id: int, job_id: int) -> bool:
        result = await self.session.execute(
            select(Favorite).where(
                Favorite.user_telegram_id == telegram_id, Favorite.job_id == job_id
            )
        )
        fav = result.scalar_one_or_none()
        if not fav:
            return False
        await self.session.delete(fav)
        await self.session.commit()
        return True

    async def clear_all_favorites(self, telegram_id: int) -> int:
        """Batch-удаление всех избранных (один SQL запрос)."""
        stmt = delete(Favorite).where(Favorite.user_telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def count_favorites(self, telegram_id: int) -> int:
        stmt = select(func.count(Favorite.id)).where(
            Favorite.user_telegram_id == telegram_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_favorites(self, telegram_id: int) -> List[Job]:
        stmt = (
            select(Job)
            .join(Favorite, Favorite.job_id == Job.id)
            .where(Favorite.user_telegram_id == telegram_id)
            .order_by(Favorite.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
