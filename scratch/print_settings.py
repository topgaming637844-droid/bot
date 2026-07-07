import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import SystemSettings

async def main():
    await init_db()
    async with AsyncSessionLocal() as session:
        stmt = select(SystemSettings)
        res = await session.execute(stmt)
        entries = res.scalars().all()
        print("--- SYSTEM SETTINGS ---")
        for entry in entries:
            print(f"Key: {entry.key} | Value: {entry.value}")
        print("-----------------------")

if __name__ == "__main__":
    asyncio.run(main())
