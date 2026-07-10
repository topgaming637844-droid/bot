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
if is_sqlite:
    connect_args = {"check_same_thread": False}
    async_engine = create_async_engine(
        _raw_url,
        echo=False,
        connect_args=connect_args
    )
else:
    connect_args = {
        "prepared_statement_cache_size": 0,
        "timeout": 10.0,
        "command_timeout": 15.0
    }
    async_engine = create_async_engine(
        _raw_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_timeout=10.0,
        pool_recycle=1200,
        pool_pre_ping=True,
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

        # Fix PostgreSQL sequences to match actual max IDs (prevents duplicate key errors after data import)
        if not is_sqlite:
            try:
                for tbl in ["episode_cache", "download_cache", "telegram_file_cache",
                            "search_cache", "persistent_task_queue", "users", "custom_buttons"]:
                    await conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {tbl}), 0) + 1, false)"
                    ))
            except Exception as ex:
                print(f"Info on sequence reset: {ex}")

    print("Database tables initialized successfully.")
