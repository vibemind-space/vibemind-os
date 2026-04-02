"""
Command Queue Service for TRAE Backend

Manages automation command queuing for desktop clients.
Replaces Supabase Edge Function command queue with local PostgreSQL.
Supports idempotency keys to prevent duplicate command execution.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import DesktopCommand

logger = logging.getLogger(__name__)


class CommandQueue:
    """
    Command queue service for desktop automation.

    Provides methods for enqueueing, processing, and managing automation
    commands destined for desktop clients.
    """

    async def enqueue_command(
        self,
        session: AsyncSession,
        client_id: str,
        command_type: str,
        command_data: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> DesktopCommand:
        """
        Add a command to the queue for a desktop client.

        Args:
            session: Database session
            client_id: Target desktop client ID
            command_type: Type of command (e.g., 'mouse_click', 'type_text')
            command_data: Command parameters
            idempotency_key: Optional key to prevent duplicate execution

        Returns:
            The created command record
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = f"{client_id}_{command_type}_{uuid.uuid4().hex[:8]}"

        # Check for existing command with same idempotency key
        existing = await session.execute(
            select(DesktopCommand).where(DesktopCommand.idempotency_key == idempotency_key)
        )
        existing_cmd = existing.scalar_one_or_none()

        if existing_cmd:
            logger.debug(f"Command with idempotency key {idempotency_key} already exists")
            return existing_cmd

        # Create new command
        command = DesktopCommand(
            desktop_client_id=client_id,
            command_type=command_type,
            command_data=command_data,
            status="pending",
            idempotency_key=idempotency_key
        )

        session.add(command)
        await session.commit()
        await session.refresh(command)

        logger.info(f"Enqueued command {command.id} for client {client_id}: {command_type}")
        return command

    async def get_pending_commands(
        self,
        session: AsyncSession,
        client_id: str,
        limit: int = 10
    ) -> List[DesktopCommand]:
        """
        Get pending commands for a client.

        Args:
            session: Database session
            client_id: Desktop client ID
            limit: Maximum number of commands to retrieve

        Returns:
            List of pending command records
        """
        result = await session.execute(
            select(DesktopCommand)
            .where(DesktopCommand.desktop_client_id == client_id)
            .where(DesktopCommand.status == "pending")
            .order_by(DesktopCommand.created_at.asc())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def mark_completed(
        self,
        session: AsyncSession,
        command_id: uuid.UUID,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Mark a command as completed.

        Args:
            session: Database session
            command_id: Command ID to mark
            result: Optional result data

        Returns:
            True if command was updated, False if not found
        """
        update_data = {
            "status": "completed",
            "processed_at": datetime.utcnow()
        }

        if result:
            update_data["command_data"] = {
                **(await self._get_command_data(session, command_id) or {}),
                "result": result
            }

        db_result = await session.execute(
            update(DesktopCommand)
            .where(DesktopCommand.id == command_id)
            .values(**update_data)
        )
        await session.commit()

        if db_result.rowcount > 0:
            logger.info(f"Command {command_id} marked as completed")
            return True
        return False

    async def mark_failed(
        self,
        session: AsyncSession,
        command_id: uuid.UUID,
        error: str
    ) -> bool:
        """
        Mark a command as failed.

        Args:
            session: Database session
            command_id: Command ID to mark
            error: Error message

        Returns:
            True if command was updated, False if not found
        """
        result = await session.execute(
            update(DesktopCommand)
            .where(DesktopCommand.id == command_id)
            .values(
                status="failed",
                processed_at=datetime.utcnow(),
                error_message=error
            )
        )
        await session.commit()

        if result.rowcount > 0:
            logger.warning(f"Command {command_id} marked as failed: {error}")
            return True
        return False

    async def get_command(
        self,
        session: AsyncSession,
        command_id: uuid.UUID
    ) -> Optional[DesktopCommand]:
        """
        Get a specific command by ID.

        Args:
            session: Database session
            command_id: Command ID to retrieve

        Returns:
            Command record or None if not found
        """
        result = await session.execute(
            select(DesktopCommand).where(DesktopCommand.id == command_id)
        )
        return result.scalar_one_or_none()

    async def _get_command_data(
        self,
        session: AsyncSession,
        command_id: uuid.UUID
    ) -> Optional[Dict[str, Any]]:
        """Get command data for a specific command"""
        command = await self.get_command(session, command_id)
        return command.command_data if command else None

    async def get_client_command_history(
        self,
        session: AsyncSession,
        client_id: str,
        limit: int = 50,
        status_filter: Optional[str] = None
    ) -> List[DesktopCommand]:
        """
        Get command history for a client.

        Args:
            session: Database session
            client_id: Desktop client ID
            limit: Maximum number of commands to retrieve
            status_filter: Optional status filter ('pending', 'completed', 'failed')

        Returns:
            List of command records
        """
        query = (
            select(DesktopCommand)
            .where(DesktopCommand.desktop_client_id == client_id)
            .order_by(DesktopCommand.created_at.desc())
            .limit(limit)
        )

        if status_filter:
            query = query.where(DesktopCommand.status == status_filter)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def cleanup_old_commands(
        self,
        session: AsyncSession,
        max_age_minutes: int = 30,
        completed_only: bool = True
    ) -> int:
        """
        Remove old commands from the queue.

        Args:
            session: Database session
            max_age_minutes: Maximum age of commands to keep
            completed_only: If True, only remove completed/failed commands

        Returns:
            Number of commands removed
        """
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

        query = delete(DesktopCommand).where(DesktopCommand.created_at < cutoff)

        if completed_only:
            query = query.where(DesktopCommand.status.in_(["completed", "failed"]))

        result = await session.execute(query)
        await session.commit()

        if result.rowcount > 0:
            logger.info(f"Cleaned up {result.rowcount} old commands")

        return result.rowcount

    async def cancel_pending_commands(
        self,
        session: AsyncSession,
        client_id: str
    ) -> int:
        """
        Cancel all pending commands for a client.

        Args:
            session: Database session
            client_id: Desktop client ID

        Returns:
            Number of commands cancelled
        """
        result = await session.execute(
            update(DesktopCommand)
            .where(DesktopCommand.desktop_client_id == client_id)
            .where(DesktopCommand.status == "pending")
            .values(
                status="failed",
                processed_at=datetime.utcnow(),
                error_message="Cancelled by system"
            )
        )
        await session.commit()

        if result.rowcount > 0:
            logger.info(f"Cancelled {result.rowcount} pending commands for client {client_id}")

        return result.rowcount

    async def get_queue_stats(
        self,
        session: AsyncSession,
        client_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get queue statistics.

        Args:
            session: Database session
            client_id: Optional client ID to filter by

        Returns:
            Dictionary with queue statistics
        """
        base_query = select(DesktopCommand)
        if client_id:
            base_query = base_query.where(DesktopCommand.desktop_client_id == client_id)

        # Get counts by status
        pending = await session.execute(
            base_query.where(DesktopCommand.status == "pending")
        )
        completed = await session.execute(
            base_query.where(DesktopCommand.status == "completed")
        )
        failed = await session.execute(
            base_query.where(DesktopCommand.status == "failed")
        )

        return {
            "pending": len(list(pending.scalars().all())),
            "completed": len(list(completed.scalars().all())),
            "failed": len(list(failed.scalars().all())),
            "client_id": client_id
        }


# Global singleton instance
command_queue = CommandQueue()


async def get_command_queue() -> CommandQueue:
    """Get the global command queue instance"""
    return command_queue
