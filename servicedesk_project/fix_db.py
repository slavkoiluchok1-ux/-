import asyncio

from app.database import engine
from app.migrations import migrate_schema


async def fix_database():
    print("Підключення до бази даних та оновлення схеми...")
    async with engine.begin() as conn:
        await migrate_schema(conn)
    print("OK: database schema updated")

if __name__ == "__main__":
    asyncio.run(fix_database())