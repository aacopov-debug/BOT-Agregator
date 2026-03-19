
import asyncio
from sqlalchemy import select
from app.database import engine, SessionLocal
from app.models.stats import ParserStats

async def check_stats():
    async with SessionLocal() as session:
        result = await session.execute(select(ParserStats))
        stats = result.scalars().all()
        print(f"{'Parser':<20} | {'Status':<10} | {'Found':<5} | {'Error'}")
        print("-" * 60)
        for s in stats:
            print(f"{s.parser_name:<20} | {s.status:<10} | {s.vacancies_found:<5} | {s.last_error}")

if __name__ == "__main__":
    asyncio.run(check_stats())
