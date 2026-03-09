"""Async database connection (asyncpg + SQLAlchemy 2)."""

import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from syllabus.db.models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://localhost/syllabus",
)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=os.environ.get("SQL_ECHO", "").lower() == "true")
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_db() -> None:
    """Create tables (for dev); in production use Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """Async context manager for DB session."""
    async with async_session_factory() as session:
        yield session
