
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models.stats import ParserStats

async def check_stats():
    async with async_session() as session:
        stmt = select(ParserStats).order_by(ParserStats.updated_at.desc())
        result = await session.execute(stmt)
        stats = result.scalars().all()
        
        print(f"{'Parser':<20} | {'Status':<7} | {'Found':<5} | {'Today':<5} | {'Last Error':<20} | {'Updated At'}")
        print("-" * 90)
        for s in stats:
            error_snippet = (s.last_error[:17] + "...") if s.last_error else "None"
            print(f"{s.parser_name:<20} | {s.status:<7} | {s.vacancies_found:<5} | {s.total_today:<5} | {error_snippet:<20} | {s.updated_at}")

if __name__ == "__main__":
    asyncio.run(check_stats())
