import asyncio
from sqlalchemy import text
from app.database import engine

async def fix_schema():
    async with engine.begin() as conn:
        print("Проверка схемы таблицы users...")
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='notify_mode';
        """))
        column_exists = result.scalar()
        
        if not column_exists:
            print("Добавляем колонку notify_mode в таблицу users...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN notify_mode VARCHAR(20) DEFAULT 'instant';"))
            print("Колонка успешно добавлена!")
        else:
            print("Колонка notify_mode уже существует в БД.")

if __name__ == "__main__":
    asyncio.run(fix_schema())

