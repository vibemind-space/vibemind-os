"""
Client Registry Service for TRAE Backend

Manages desktop client registration, tracking, and lifecycle.
Replaces Supabase Edge Function client management with local PostgreSQL.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.database import get_db, db
from app.models.db_models import ActiveDesktopClient

logger = logging.getLogger(__name__)


class ClientRegistry:
    """
    Desktop client registry service.

    Tracks connected desktop clients, their capabilities, and streaming status.
    Provides methods for registration, updates, and cleanup of stale clients.
    """

    async def register_client(
        self,
        session: AsyncSession,
        client_id: str,
        client_info: Dict[str, Any]
    ) -> ActiveDesktopClient:
        """
        Register or update a desktop client.

        Args:
            session: Database session
            client_id: Unique client identifier
            client_info: Client information including monitors, capabilities, etc.

        Returns:
            The registered/updated client record
        """
        now = datetime.utcnow()

        # Prepare client data
        client_data = {
            "client_id": client_id,
            "name": client_info.get("name", client_id),
            "monitors": client_info.get("monitors", []),
            "capabilities": client_info.get("capabilities", {}),
            "user_id": client_info.get("user_id"),
            "hostname": client_info.get("hostname"),
            "is_streaming": False,
            "last_ping": now,
            "connected_at": now,
            "updated_at": now
        }

        # Upsert - insert or update on conflict
        stmt = insert(ActiveDesktopClient).values(**client_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["client_id"],
            set_={
                "name": stmt.excluded.name,
                "monitors": stmt.excluded.monitors,
                "capabilities": stmt.excluded.capabilities,
                "user_id": stmt.excluded.user_id,
                "hostname": stmt.excluded.hostname,
                "last_ping": stmt.excluded.last_ping,
                "updated_at": stmt.excluded.updated_at
            }
        )

        await session.execute(stmt)
        await session.commit()

        # Fetch and return the client
        result = await session.execute(
            select(ActiveDesktopClient).where(ActiveDesktopClient.client_id == client_id)
        )
        client = result.scalar_one()

        logger.info(f"Registered client: {client_id} ({client_info.get('hostname', 'unknown')})")
        return client

    async def unregister_client(self, session: AsyncSession, client_id: str) -> bool:
        """
        Remove a client from the registry.

        Args:
            session: Database session
            client_id: Client to remove

        Returns:
            True if client was removed, False if not found
        """
        result = await session.execute(
            delete(ActiveDesktopClient).where(ActiveDesktopClient.client_id == client_id)
        )
        await session.commit()

        removed = result.rowcount > 0
        if removed:
            logger.info(f"Unregistered client: {client_id}")
        return removed

    async def update_ping(self, session: AsyncSession, client_id: str) -> bool:
        """
        Update the last ping timestamp for a client.

        Args:
            session: Database session
            client_id: Client to update

        Returns:
            True if client was updated, False if not found
        """
        result = await session.execute(
            update(ActiveDesktopClient)
            .where(ActiveDesktopClient.client_id == client_id)
            .values(last_ping=datetime.utcnow(), updated_at=datetime.utcnow())
        )
        await session.commit()

        return result.rowcount > 0

    async def set_streaming_status(
        self,
        session: AsyncSession,
        client_id: str,
        is_streaming: bool
    ) -> bool:
        """
        Update the streaming status for a client.

        Args:
            session: Database session
            client_id: Client to update
            is_streaming: New streaming status

        Returns:
            True if client was updated, False if not found
        """
        result = await session.execute(
            update(ActiveDesktopClient)
            .where(ActiveDesktopClient.client_id == client_id)
            .values(is_streaming=is_streaming, updated_at=datetime.utcnow())
        )
        await session.commit()

        if result.rowcount > 0:
            logger.info(f"Client {client_id} streaming: {is_streaming}")
            return True
        return False

    async def get_client(
        self,
        session: AsyncSession,
        client_id: str
    ) -> Optional[ActiveDesktopClient]:
        """
        Get a specific client by ID.

        Args:
            session: Database session
            client_id: Client to retrieve

        Returns:
            Client record or None if not found
        """
        result = await session.execute(
            select(ActiveDesktopClient).where(ActiveDesktopClient.client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def get_active_clients(
        self,
        session: AsyncSession,
        max_age_minutes: int = 2
    ) -> List[ActiveDesktopClient]:
        """
        Get all active clients (pinged within max_age_minutes).

        Args:
            session: Database session
            max_age_minutes: Maximum age of last ping in minutes

        Returns:
            List of active client records
        """
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        result = await session.execute(
            select(ActiveDesktopClient)
            .where(ActiveDesktopClient.last_ping >= cutoff)
            .order_by(ActiveDesktopClient.connected_at.desc())
        )

        return list(result.scalars().all())

    async def get_streaming_clients(
        self,
        session: AsyncSession
    ) -> List[ActiveDesktopClient]:
        """
        Get all currently streaming clients.

        Args:
            session: Database session

        Returns:
            List of streaming client records
        """
        result = await session.execute(
            select(ActiveDesktopClient)
            .where(ActiveDesktopClient.is_streaming == True)
            .order_by(ActiveDesktopClient.connected_at.desc())
        )

        return list(result.scalars().all())

    async def cleanup_stale_clients(
        self,
        session: AsyncSession,
        max_age_minutes: int = 2
    ) -> int:
        """
        Remove clients that haven't pinged within max_age_minutes.

        Args:
            session: Database session
            max_age_minutes: Maximum age of last ping in minutes

        Returns:
            Number of clients removed
        """
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        result = await session.execute(
            delete(ActiveDesktopClient).where(ActiveDesktopClient.last_ping < cutoff)
        )
        await session.commit()

        if result.rowcount > 0:
            logger.info(f"Cleaned up {result.rowcount} stale clients")

        return result.rowcount

    async def get_clients_summary(self, session: AsyncSession) -> Dict[str, Any]:
        """
        Get a summary of connected clients.

        Args:
            session: Database session

        Returns:
            Summary dictionary with counts and client list
        """
        active = await self.get_active_clients(session)
        streaming = [c for c in active if c.is_streaming]

        return {
            "total_active": len(active),
            "total_streaming": len(streaming),
            "clients": [c.to_dict() for c in active]
        }


# Global singleton instance
client_registry = ClientRegistry()


async def get_client_registry() -> ClientRegistry:
    """Get the global client registry instance"""
    return client_registry
