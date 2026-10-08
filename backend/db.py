"""SQLAlchemy async engine and session factory."""
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base

_engine = None
_async_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        database_url = os.environ["DATABASE_URL"]
        # asyncpg requires postgresql+asyncpg:// scheme
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        _engine = create_async_engine(database_url, echo=False)
    return _engine


def _get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def init_db() -> None:
    """Create all tables if they don't exist. Called from the FastAPI lifespan."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migration: add pipeline_started_at column if it doesn't exist
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                "pipeline_started_at TIMESTAMPTZ NULL"
            )
        )
        # Idempotent migration: add context_data column if it doesn't exist
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                "context_data JSONB NULL"
            )
        )
        # Idempotent migration: add channels column to skill_packs if it doesn't exist
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE skill_packs ADD COLUMN IF NOT EXISTS "
                "channels TEXT[] NULL"
            )
        )
        # Idempotent migration: add recording_url column to sessions if it doesn't exist
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                "recording_url TEXT NULL"
            )
        )
        # Idempotent migration: add recall_recording_url column to sessions if it doesn't exist
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                "recall_recording_url TEXT NULL"
            )
        )
        # Idempotent migration: add full_transcript column to sessions if it doesn't exist
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                "full_transcript TEXT NULL"
            )
        )


async def get_db():
    """FastAPI dependency that yields an AsyncSession."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        yield session
