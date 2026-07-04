from sqlalchemy import select
from app.database.models import SystemSettings
from app.database.connection import AsyncSessionLocal
from app.utils.logging_config import logger

async def get_setting(key: str, default: str = None) -> str:
    """Retrieves a setting value from SystemSettings table."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                return entry.value
            return default
    except Exception:
        logger.exception(f"Error fetching system setting for key '{key}'")
        return default

async def set_setting(key: str, value: str):
    """Saves or updates a setting value in SystemSettings table."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                entry.value = value
            else:
                entry = SystemSettings(key=key, value=value)
                session.add(entry)
            await session.commit()
    except Exception:
        logger.exception(f"Error saving system setting for key '{key}'")

async def delete_setting(key: str):
    """Deletes a setting from SystemSettings table."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                await session.delete(entry)
                await session.commit()
    except Exception:
        logger.exception(f"Error deleting system setting for key '{key}'")
