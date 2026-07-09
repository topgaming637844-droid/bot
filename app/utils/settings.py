from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import SystemSettings
from app.database.connection import AsyncSessionLocal
from app.utils.logging_config import logger

async def get_setting(key: str, default: str = None, session: AsyncSession = None) -> str:
    """Retrieves a setting value from SystemSettings table."""
    if session:
        try:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                return entry.value
            return default
        except Exception:
            logger.exception(f"Error fetching system setting for key '{key}'")
            return default

    try:
        async with AsyncSessionLocal() as session_local:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session_local.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                return entry.value
            return default
    except Exception:
        logger.exception(f"Error fetching system setting for key '{key}'")
        return default

async def set_setting(key: str, value: str, session: AsyncSession = None):
    """Saves or updates a setting value in SystemSettings table."""
    if session:
        try:
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
        return

    try:
        async with AsyncSessionLocal() as session_local:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session_local.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                entry.value = value
            else:
                entry = SystemSettings(key=key, value=value)
                session_local.add(entry)
            await session_local.commit()
    except Exception:
        logger.exception(f"Error saving system setting for key '{key}'")

async def delete_setting(key: str, session: AsyncSession = None):
    """Deletes a setting from SystemSettings table."""
    if session:
        try:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                await session.delete(entry)
                await session.commit()
        except Exception:
            logger.exception(f"Error deleting system setting for key '{key}'")
        return

    try:
        async with AsyncSessionLocal() as session_local:
            stmt = select(SystemSettings).where(SystemSettings.key == key)
            res = await session_local.execute(stmt)
            entry = res.scalar_one_or_none()
            if entry:
                await session_local.delete(entry)
                await session_local.commit()
    except Exception:
        logger.exception(f"Error deleting system setting for key '{key}'")
