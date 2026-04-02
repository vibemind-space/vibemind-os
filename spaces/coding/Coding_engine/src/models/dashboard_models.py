"""
Pydantic models for dashboard API responses.
Defines request/response models for real-time dashboard endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class TimelineEntry(BaseModel):
    """Single timeline entry for connection events."""

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime = Field(..., description="Event timestamp")
    event_type: str = Field(..., description="Type of event (e.g., CONNECTION_ESTABLISHED)")
    affected_resource: str = Field(..., description="Resource affected by event (e.g., 'Process: chrome (PID: 1234) Port: 8080')")
    message: Optional[str] = Field(None, description="Human-readable event message")
    severity: str = Field("info", description="Event severity: info, warning, error, success")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional event details")


class TimelineResponse(BaseModel):
    """Response for timeline endpoint."""

    model_config = ConfigDict(from_attributes=True)

    events: List[TimelineEntry] = Field(..., description="List of timeline events")
    total_count: int = Field(..., description="Total number of events in database")
    returned_count: int = Field(..., description="Number of events returned in this response")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(100, description="Number of events per page")
    has_more: bool = Field(False, description="Whether more events are available")


class ProcessMetrics(BaseModel):
    """Real-time process metrics."""

    model_config = ConfigDict(from_attributes=True)

    active_processes: int = Field(..., description="Number of active processes")
    total_threads: int = Field(0, description="Total number of threads across all processes")
    cpu_usage_percent: float = Field(0.0, description="System CPU usage percentage")
    memory_usage_percent: float = Field(0.0, description="System memory usage percentage")
    memory_usage_mb: float = Field(0.0, description="System memory usage in MB")


class ConnectionMetrics(BaseModel):
    """Real-time connection metrics."""

    model_config = ConfigDict(from_attributes=True)

    active_connections: int = Field(0, description="Number of active connections")
    listening_ports: int = Field(0, description="Number of listening ports")
    established_connections: int = Field(0, description="Number of ESTABLISHED connections")
    time_wait_connections: int = Field(0, description="Number of TIME_WAIT connections")
    tcp_connections: int = Field(0, description="Number of TCP connections")
    udp_connections: int = Field(0, description="Number of UDP connections")


class DashboardMetrics(BaseModel):
    """Comprehensive dashboard metrics."""

    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metrics collection timestamp")
    process_metrics: ProcessMetrics = Field(..., description="Process-level metrics")
    connection_metrics: ConnectionMetrics = Field(..., description="Connection-level metrics")
    recent_events_count: int = Field(0, description="Number of events in last minute")
    error_rate_percent: float = Field(0.0, description="Error rate in last minute (0-100)")


class DashboardOverview(BaseModel):
    """Complete dashboard overview with timeline and metrics."""

    model_config = ConfigDict(from_attributes=True)

    metrics: DashboardMetrics = Field(..., description="Current system metrics")
    timeline: TimelineResponse = Field(..., description="Recent connection events timeline")
    load_time_ms: float = Field(..., description="Time taken to load dashboard data (milliseconds)")


class ProcessInfo(BaseModel):
    """Detailed process information."""

    model_config = ConfigDict(from_attributes=True)

    pid: int = Field(..., description="Process ID")
    name: str = Field(..., description="Process name")
    status: str = Field(..., description="Process status (running, sleeping, etc.)")
    cpu_percent: float = Field(0.0, description="CPU usage percentage")
    memory_percent: float = Field(0.0, description="Memory usage percentage")
    memory_mb: float = Field(0.0, description="Memory usage in MB")
    num_threads: int = Field(1, description="Number of threads")
    created_time: datetime = Field(..., description="Process creation time")
    ports: List[int] = Field(default_factory=list, description="Ports used by process")


class ProcessListResponse(BaseModel):
    """Response for process list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    processes: List[ProcessInfo] = Field(..., description="List of active processes")
    total_count: int = Field(..., description="Total number of processes")
    load_time_ms: float = Field(..., description="Time taken to load process data (milliseconds)")


class WebSocketMessage(BaseModel):
    """WebSocket message structure for real-time updates."""

    model_config = ConfigDict(from_attributes=True)

    type: str = Field(..., description="Message type (event, metrics, error)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    data: Dict[str, Any] = Field(..., description="Message payload")


class EventFilter(BaseModel):
    """Filter parameters for timeline queries."""

    model_config = ConfigDict(from_attributes=True)

    event_types: Optional[List[str]] = Field(None, description="Filter by event types")
    severity: Optional[List[str]] = Field(None, description="Filter by severity levels")
    process_id: Optional[int] = Field(None, description="Filter by process ID")
    port: Optional[int] = Field(None, description="Filter by port number")
    since: Optional[datetime] = Field(None, description="Events since timestamp")
    until: Optional[datetime] = Field(None, description="Events until timestamp")
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of events to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class PerformanceMetrics(BaseModel):
    """Performance metrics for dashboard requirements."""

    model_config = ConfigDict(from_attributes=True)

    request_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Request initiation time")
    response_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response completion time")
    load_time_ms: float = Field(..., description="Total load time in milliseconds")
    backend_time_ms: float = Field(..., description="Backend processing time in milliseconds")
    database_time_ms: float = Field(0.0, description="Database query time in milliseconds")
    active_processes_count: int = Field(..., description="Number of active processes at time of request")
    meets_sla: bool = Field(True, description="Whether response met SLA requirements (< 2000ms)")


class RealtimeUpdate(BaseModel):
    """Real-time update message for WebSocket."""

    model_config = ConfigDict(from_attributes=True)

    update_type: str = Field(..., description="Type of update: event, metrics, process_change")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Update timestamp")
    latency_ms: float = Field(0.0, description="Latency from event to UI update (milliseconds)")
    data: Dict[str, Any] = Field(..., description="Update payload")


class HealthStatus(BaseModel):
    """Dashboard health status."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field("healthy", description="Overall status: healthy, degraded, unhealthy")
    websocket_connected: bool = Field(False, description="WebSocket connection status")
    active_connections: int = Field(0, description="Number of active WebSocket connections")
    last_event_timestamp: Optional[datetime] = Field(None, description="Timestamp of last event")
    event_processing_lag_ms: float = Field(0.0, description="Event processing lag in milliseconds")
    metrics_update_interval_ms: float = Field(1000.0, description="Metrics update interval in milliseconds")
