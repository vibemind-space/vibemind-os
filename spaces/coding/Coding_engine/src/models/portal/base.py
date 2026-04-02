"""
Database base configuration and utilities.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy import Column, DateTime, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, declared_attr


class TimestampMixin:
    """Mixin for automatic timestamp management."""

    @declared_attr
    def created_at(cls):
        return Column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            nullable=False,
        )

    @declared_attr
    def updated_at(cls):
        return Column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        )


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


# Database configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/cell_colony"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("SQL_DEBUG", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.

    Usage:
        async with get_db_context() as db:
            result = await db.execute(query)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    """Drop all database tables (use with caution!)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Row-Level Security helpers for PostgreSQL
RLS_POLICIES = """
-- Enable RLS on tenant-scoped tables
ALTER TABLE cells ENABLE ROW LEVEL SECURITY;
ALTER TABLE cell_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cell_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_members ENABLE ROW LEVEL SECURITY;

-- Policy for cells: users can only see cells in their tenant
CREATE POLICY tenant_isolation_cells ON cells
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Policy for cell_versions: same as cells
CREATE POLICY tenant_isolation_versions ON cell_versions
    USING (cell_id IN (SELECT id FROM cells WHERE tenant_id = current_setting('app.current_tenant_id')::uuid));

-- Policy for tenant_members: users can only see their own tenant members
CREATE POLICY tenant_isolation_members ON tenant_members
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Public cells can be seen by anyone
CREATE POLICY public_cells ON cells
    FOR SELECT
    USING (visibility = 'public');
"""


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    """
    Set the current tenant context for RLS policies.

    Args:
        session: Database session
        tenant_id: UUID of the tenant
    """
    await session.execute(
        f"SET app.current_tenant_id = '{tenant_id}'"
    )
