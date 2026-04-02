"""
Dashboard service for real-time metrics aggregation and timeline management.
Handles connection events timeline, process monitoring, and performance metrics.
"""

import time
import psutil
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.connection_event import ConnectionEvent
from src.models.dashboard_models import (
    TimelineEntry,
    TimelineResponse,
    ProcessMetrics,
    ConnectionMetrics,
    DashboardMetrics,
    DashboardOverview,
    ProcessInfo,
    ProcessListResponse,
    EventFilter,
    PerformanceMetrics,
)
from src.services.process_service import ProcessMonitorService


class DashboardService:
    """Service for dashboard data aggregation and real-time metrics."""

    def __init__(self, db_session: AsyncSession):
        """
        Initialize dashboard service.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self.process_monitor = ProcessMonitorService()

    async def get_timeline(
        self,
        limit: int = 100,
        offset: int = 0,
        event_filter: Optional[EventFilter] = None
    ) -> TimelineResponse:
        """
        Get connection events timeline.

        Args:
            limit: Maximum number of events to return (max 1000)
            offset: Offset for pagination
            event_filter: Optional filter parameters

        Returns:
            TimelineResponse with events and pagination info
        """
        # Build query
        query = select(ConnectionEvent).order_by(desc(ConnectionEvent.timestamp))

        # Apply filters
        if event_filter:
            filters = []

            if event_filter.event_types:
                filters.append(ConnectionEvent.event_type.in_(event_filter.event_types))

            if event_filter.severity:
                filters.append(ConnectionEvent.severity.in_(event_filter.severity))

            if event_filter.process_id is not None:
                filters.append(ConnectionEvent.process_id == event_filter.process_id)

            if event_filter.port is not None:
                filters.append(ConnectionEvent.port == event_filter.port)

            if event_filter.since:
                filters.append(ConnectionEvent.timestamp >= event_filter.since)

            if event_filter.until:
                filters.append(ConnectionEvent.timestamp <= event_filter.until)

            if filters:
                query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(ConnectionEvent)
        if event_filter and filters:
            count_query = count_query.where(and_(*filters))

        total_count_result = await self.db.execute(count_query)
        total_count = total_count_result.scalar() or 0

        # Apply pagination
        query = query.limit(limit).offset(offset)

        # Execute query
        result = await self.db.execute(query)
        events = result.scalars().all()

        # Convert to timeline entries
        timeline_entries = [
            TimelineEntry(**event.to_timeline_entry())
            for event in events
        ]

        return TimelineResponse(
            events=timeline_entries,
            total_count=total_count,
            returned_count=len(timeline_entries),
            page=(offset // limit) + 1,
            page_size=limit,
            has_more=(offset + len(timeline_entries)) < total_count
        )

    async def get_process_metrics(self) -> ProcessMetrics:
        """
        Get real-time process metrics.

        Returns:
            ProcessMetrics with current system stats
        """
        # Get system stats
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        # Get process count and threads
        processes = list(psutil.process_iter(['num_threads']))
        active_processes = len(processes)
        total_threads = sum(p.info.get('num_threads', 1) for p in processes)

        return ProcessMetrics(
            active_processes=active_processes,
            total_threads=total_threads,
            cpu_usage_percent=cpu_percent,
            memory_usage_percent=memory.percent,
            memory_usage_mb=memory.used / (1024 * 1024)
        )

    async def get_connection_metrics(self) -> ConnectionMetrics:
        """
        Get real-time connection metrics.

        Returns:
            ConnectionMetrics with current connection stats
        """
        connections = psutil.net_connections()

        # Count by type
        listening = sum(1 for c in connections if c.status == 'LISTEN')
        established = sum(1 for c in connections if c.status == 'ESTABLISHED')
        time_wait = sum(1 for c in connections if c.status == 'TIME_WAIT')
        tcp = sum(1 for c in connections if c.type == 1)  # SOCK_STREAM = TCP
        udp = sum(1 for c in connections if c.type == 2)  # SOCK_DGRAM = UDP

        return ConnectionMetrics(
            active_connections=len(connections),
            listening_ports=listening,
            established_connections=established,
            time_wait_connections=time_wait,
            tcp_connections=tcp,
            udp_connections=udp
        )

    async def get_recent_events_count(self, minutes: int = 1) -> int:
        """
        Get count of events in last N minutes.

        Args:
            minutes: Number of minutes to look back

        Returns:
            Event count
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)
        query = select(func.count()).select_from(ConnectionEvent).where(
            ConnectionEvent.timestamp >= since
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_error_rate(self, minutes: int = 1) -> float:
        """
        Get error rate percentage in last N minutes.

        Args:
            minutes: Number of minutes to look back

        Returns:
            Error rate as percentage (0-100)
        """
        since = datetime.utcnow() - timedelta(minutes=minutes)

        # Total events
        total_query = select(func.count()).select_from(ConnectionEvent).where(
            ConnectionEvent.timestamp >= since
        )
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        if total == 0:
            return 0.0

        # Error events
        error_query = select(func.count()).select_from(ConnectionEvent).where(
            and_(
                ConnectionEvent.timestamp >= since,
                ConnectionEvent.severity == 'error'
            )
        )
        error_result = await self.db.execute(error_query)
        errors = error_result.scalar() or 0

        return (errors / total) * 100.0

    async def get_dashboard_metrics(self) -> DashboardMetrics:
        """
        Get comprehensive dashboard metrics.

        Returns:
            DashboardMetrics with all current stats
        """
        # Gather metrics in parallel
        process_metrics = await self.get_process_metrics()
        connection_metrics = await self.get_connection_metrics()
        recent_events = await self.get_recent_events_count(minutes=1)
        error_rate = await self.get_error_rate(minutes=1)

        return DashboardMetrics(
            timestamp=datetime.utcnow(),
            process_metrics=process_metrics,
            connection_metrics=connection_metrics,
            recent_events_count=recent_events,
            error_rate_percent=error_rate
        )

    async def get_dashboard_overview(
        self,
        timeline_limit: int = 100,
        timeline_filter: Optional[EventFilter] = None
    ) -> Tuple[DashboardOverview, PerformanceMetrics]:
        """
        Get complete dashboard overview with timeline and metrics.
        Measures performance against SLA requirements.

        Args:
            timeline_limit: Number of timeline events to return
            timeline_filter: Optional timeline filters

        Returns:
            Tuple of (DashboardOverview, PerformanceMetrics)
        """
        start_time = time.perf_counter()
        request_timestamp = datetime.utcnow()

        # Gather data
        db_start = time.perf_counter()
        metrics = await self.get_dashboard_metrics()
        timeline = await self.get_timeline(limit=timeline_limit, event_filter=timeline_filter)
        db_end = time.perf_counter()

        end_time = time.perf_counter()
        response_timestamp = datetime.utcnow()

        # Calculate timings
        load_time_ms = (end_time - start_time) * 1000
        backend_time_ms = load_time_ms
        database_time_ms = (db_end - db_start) * 1000

        # Create overview
        overview = DashboardOverview(
            metrics=metrics,
            timeline=timeline,
            load_time_ms=load_time_ms
        )

        # Performance metrics
        performance = PerformanceMetrics(
            request_timestamp=request_timestamp,
            response_timestamp=response_timestamp,
            load_time_ms=load_time_ms,
            backend_time_ms=backend_time_ms,
            database_time_ms=database_time_ms,
            active_processes_count=metrics.process_metrics.active_processes,
            meets_sla=load_time_ms < 2000  # REQ-ea7004-016: < 2 seconds
        )

        return overview, performance

    async def get_process_list(
        self,
        sort_by: str = "cpu",
        limit: int = 100
    ) -> ProcessListResponse:
        """
        Get list of active processes with details.

        Args:
            sort_by: Sort field (cpu, memory, name, pid)
            limit: Maximum number of processes to return

        Returns:
            ProcessListResponse with process details
        """
        start_time = time.perf_counter()

        # Get all processes
        processes = []
        for proc in psutil.process_iter([
            'pid', 'name', 'status', 'cpu_percent', 'memory_percent',
            'memory_info', 'num_threads', 'create_time', 'connections'
        ]):
            try:
                info = proc.info
                connections = info.get('connections', [])
                ports = list(set(c.laddr.port for c in connections if c.laddr))

                processes.append(ProcessInfo(
                    pid=info['pid'],
                    name=info['name'],
                    status=info['status'],
                    cpu_percent=info.get('cpu_percent', 0.0) or 0.0,
                    memory_percent=info.get('memory_percent', 0.0) or 0.0,
                    memory_mb=(info.get('memory_info').rss / (1024 * 1024)) if info.get('memory_info') else 0.0,
                    num_threads=info.get('num_threads', 1),
                    created_time=datetime.fromtimestamp(info['create_time']),
                    ports=ports
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Sort processes
        if sort_by == "cpu":
            processes.sort(key=lambda p: p.cpu_percent, reverse=True)
        elif sort_by == "memory":
            processes.sort(key=lambda p: p.memory_percent, reverse=True)
        elif sort_by == "name":
            processes.sort(key=lambda p: p.name.lower())
        elif sort_by == "pid":
            processes.sort(key=lambda p: p.pid)

        # Limit results
        limited_processes = processes[:limit]

        end_time = time.perf_counter()
        load_time_ms = (end_time - start_time) * 1000

        return ProcessListResponse(
            processes=limited_processes,
            total_count=len(processes),
            load_time_ms=load_time_ms
        )

    async def record_event(self, event: ConnectionEvent) -> ConnectionEvent:
        """
        Record a connection event to the database.

        Args:
            event: ConnectionEvent to record

        Returns:
            Saved ConnectionEvent with ID
        """
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def record_event_from_dict(self, event_dict: dict) -> ConnectionEvent:
        """
        Record a connection event from EventBus event dictionary.

        Args:
            event_dict: Event dictionary from EventBus

        Returns:
            Saved ConnectionEvent
        """
        event = ConnectionEvent.from_event_bus(event_dict)
        return await self.record_event(event)

    async def cleanup_old_events(self, days: int = 7) -> int:
        """
        Clean up events older than specified days.

        Args:
            days: Number of days to retain

        Returns:
            Number of events deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        delete_query = select(ConnectionEvent).where(
            ConnectionEvent.timestamp < cutoff
        )

        result = await self.db.execute(delete_query)
        events_to_delete = result.scalars().all()
        count = len(events_to_delete)

        for event in events_to_delete:
            await self.db.delete(event)

        await self.db.commit()
        return count
