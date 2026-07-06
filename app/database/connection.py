from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import config
from app.database.models import Base

# Setup the database engine
# Note: For SQLite, check_same_thread=False. For PostgreSQL (asyncpg), prepared_statement_cache_size=0 prevents prepared statement clashes.
is_sqlite = config.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {"prepared_statement_cache_size": 0}

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
        try:
            if not is_sqlite:
                await conn.execute(text("ALTER TABLE telegram_file_cache ADD COLUMN IF NOT EXISTS file_size DOUBLE PRECISION;"))
        except Exception as e:
            print(f"Info on column migration for telegram_file_cache.file_size: {e}")

        # Column migration for custom_buttons table
        try:
            if is_sqlite:
                await conn.execute(text("ALTER TABLE custom_buttons ADD COLUMN response_text TEXT;"))
            else:
                await conn.execute(text("ALTER TABLE custom_buttons ADD COLUMN IF NOT EXISTS response_text TEXT;"))
        except Exception as e:
            print(f"Info on column migration for custom_buttons.response_text: {e}")

        # Column migrations for users table
        for col_name, col_type in [("first_name", "VARCHAR(255)"), ("last_name", "VARCHAR(255)"), ("is_blocked", "BOOLEAN DEFAULT FALSE")]:
            try:
                if is_sqlite:
                    await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
            except Exception:
                pass
    print("Database tables initialized successfully.")
