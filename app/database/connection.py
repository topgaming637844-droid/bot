from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import config
from app.database.models import Base

# Setup the database engine
# Note: For SQLite, check_same_thread=False. For PostgreSQL (asyncpg), prepared_statement_cache_size=0 prevents prepared statement clashes.

# Auto-fix: Railway injects DATABASE_URL as 'postgresql://' but we need 'postgresql+asyncpg://'
_raw_url = config.DATABASE_URL
if _raw_url.startswith("postgresql://") or _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _raw_url = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)

is_sqlite = _raw_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {"prepared_statement_cache_size": 0}

if is_sqlite:
    async_engine = create_async_engine(
        _raw_url,
        echo=False,
        connect_args=connect_args
    )
else:
    async_engine = create_async_engine(
        _raw_url,
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

        async def add_column_if_missing(table_name: str, column_name: str, column_type: str):
            try:
                if is_sqlite:
                    res = await conn.execute(text(f"PRAGMA table_info({table_name});"))
                    existing_cols = [row[1] for row in res.fetchall()]
                    if column_name not in existing_cols:
                        await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_type};"))
            except Exception as ex:
                print(f"Info on column migration {table_name}.{column_name}: {ex}")

        # Column migrations
        await add_column_if_missing("custom_buttons", "response_text", "TEXT")
        await add_column_if_missing("telegram_file_cache", "file_size", "DOUBLE PRECISION" if not is_sqlite else "REAL")
        await add_column_if_missing("users", "first_name", "VARCHAR(255)")
        await add_column_if_missing("users", "last_name", "VARCHAR(255)")
        await add_column_if_missing("users", "is_blocked", "BOOLEAN DEFAULT FALSE")

    print("Database tables initialized successfully.")
