from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import config
from app.database.models import Base

# Setup the database engine
# Note: For SQLite, we enforce check_same_thread=False
is_sqlite = config.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

if is_sqlite:
    async_engine = create_async_engine(
        config.DATABASE_URL,
        echo=False,
        connect_args=connect_args
    )
else:
    async_engine = create_async_engine(
        config.DATABASE_URL,
        echo=False,
        pool_size=100,
        max_overflow=50,
        pool_recycle=1800,
        connect_args=connect_args
    )

# Async session factory
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """Initializes the database, creating tables if they do not exist."""
    from sqlalchemy import text
    async with async_engine.begin() as conn:
        # Drop the old cache tables if they exist to force database schema / constraints update
        cascade_suffix = "" if is_sqlite else " CASCADE"
        try:
            await conn.execute(text(f"DROP TABLE IF EXISTS search_cache{cascade_suffix};"))
            await conn.execute(text(f"DROP TABLE IF EXISTS episode_cache{cascade_suffix};"))
            await conn.execute(text(f"DROP TABLE IF EXISTS download_cache{cascade_suffix};"))
        except Exception as e:
            print(f"Warning while dropping cache tables: {e}")
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables initialized successfully.")
