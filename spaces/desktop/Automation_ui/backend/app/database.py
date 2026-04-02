"""
Database Configuration for TRAE Backend

SQLAlchemy async engine and session management for PostgreSQL.
Supports both sync (for migrations) and async (for FastAPI) operations.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all ORM models"""
    pass


class DatabaseManager:
    """Manages database connections and sessions"""

    def __init__(self):
        self._sync_engine = None
        self._async_engine = None
        self._async_session_factory = None
        self._sync_session_factory = None
        self._initialized = False

    def init(
        self,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        echo: bool = False
    ):
        """Initialize database engines and session factories"""
        if self._initialized:
            logger.warning("Database already initialized, skipping")
            return

        is_sqlite = database_url.startswith("sqlite")

        if is_sqlite:
            # SQLite: single-threaded, no pool config, use StaticPool
            self._sync_engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=echo,
            )
            # Async SQLite via aiosqlite
            async_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
            self._async_engine = create_async_engine(
                async_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=echo,
            )
        else:
            # PostgreSQL: full pool support
            self._sync_engine = create_engine(
                database_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                echo=echo
            )
            async_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://"
            ).replace(
                "postgres://", "postgresql+asyncpg://"
            )
            self._async_engine = create_async_engine(
                async_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                echo=echo
            )

        # Session factories
        self._sync_session_factory = sessionmaker(
            bind=self._sync_engine,
            autocommit=False,
            autoflush=False
        )

        self._async_session_factory = async_sessionmaker(
            bind=self._async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False
        )

        self._initialized = True
        logger.info("Database initialized successfully")

    @property
    def sync_engine(self):
        """Get sync engine (for migrations)"""
        if not self._sync_engine:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._sync_engine

    @property
    def async_engine(self):
        """Get async engine"""
        if not self._async_engine:
            raise RuntimeError("Database not initialized. Call init() first.")
        return self._async_engine

    async def create_tables(self):
        """Create all tables (for development/testing)"""
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")

    async def drop_tables(self):
        """Drop all tables (for testing)"""
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Database tables dropped")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for async database sessions"""
        if not self._async_session_factory:
            raise RuntimeError("Database not initialized. Call init() first.")

        session = self._async_session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Dependency for FastAPI route injection"""
        async with self.session() as session:
            yield session

    async def close(self):
        """Close database connections"""
        if self._async_engine:
            await self._async_engine.dispose()
            logger.info("Async database engine closed")
        if self._sync_engine:
            self._sync_engine.dispose()
            logger.info("Sync database engine closed")
        self._initialized = False


# Global database manager instance
db = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions"""
    async for session in db.get_session():
        yield session


def init_db(
    database_url: str,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    echo: bool = False
):
    """Initialize the global database manager"""
    db.init(
        database_url=database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        echo=echo
    )


async def close_db():
    """Close the global database manager"""
    await db.close()
