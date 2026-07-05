import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal
from app.database.models import User
from sqlalchemy import select

async def test():
    async with AsyncSessionLocal() as db_session:
        stmt = select(User).where(User.user_id == 8820710465)
        res = await db_session.execute(stmt)
        user = res.scalar_one_or_none()
        if user:
            print(f"User found: ID={user.user_id}, Name={user.first_name} {user.last_name}, Username={user.username}, IsBlocked={user.is_blocked}, CreatedAt={user.created_at}")
        else:
            print("User NOT found in database!")

if __name__ == "__main__":
    asyncio.run(test())
