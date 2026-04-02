"""
Process monitoring service for tracking system processes and resources.
Provides real-time monitoring of processes, ports, and connections.
"""

import psutil
from typing import List, Dict, Optional, Set
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class ProcessInfo:
    """Information about a running process."""

    def __init__(
        self,
        pid: int,
        name: str,
        status: str,
        cpu_percent: float = 0.0,
        memory_percent: float = 0.0,
        memory_mb: float = 0.0,
        num_threads: int = 1,
        ports: List[int] = None,
        created_time: Optional[datetime] = None
    ):
        self.pid = pid
        self.name = name
        self.status = status
        self.cpu_percent = cpu_percent
        self.memory_percent = memory_percent
        self.memory_mb = memory_mb
        self.num_threads = num_threads
        self.ports = ports or []
        self.created_time = created_time


class ProcessMonitorService:
    """Service for monitoring system processes and resources."""

    def __init__(self):
        """Initialize process monitor service."""
        self._cached_processes: Dict[int, ProcessInfo] = {}
        self._last_update: Optional[datetime] = None
        logger.info("process_monitor_service_initialized")

    def get_all_processes(self) -> List[ProcessInfo]:
        """
        Get information about all running processes.

        Returns:
            List of ProcessInfo objects
        """
        processes = []
        for proc in psutil.process_iter([
            'pid', 'name', 'status', 'cpu_percent', 'memory_percent',
            'memory_info', 'num_threads', 'create_time', 'connections'
        ]):
            try:
                info = proc.info
                connections = info.get('connections', [])
                ports = list(set(c.laddr.port for c in connections if c.laddr))

                proc_info = ProcessInfo(
                    pid=info['pid'],
                    name=info['name'],
                    status=info['status'],
                    cpu_percent=info.get('cpu_percent', 0.0) or 0.0,
                    memory_percent=info.get('memory_percent', 0.0) or 0.0,
                    memory_mb=(info.get('memory_info').rss / (1024 * 1024)) if info.get('memory_info') else 0.0,
                    num_threads=info.get('num_threads', 1),
                    created_time=datetime.fromtimestamp(info['create_time']) if info.get('create_time') else None,
                    ports=ports
                )
                processes.append(proc_info)
                self._cached_processes[info['pid']] = proc_info
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        self._last_update = datetime.utcnow()
        return processes

    def get_process_by_pid(self, pid: int) -> Optional[ProcessInfo]:
        """
        Get information about a specific process by PID.

        Args:
            pid: Process ID

        Returns:
            ProcessInfo or None if process not found
        """
        try:
            proc = psutil.Process(pid)
            connections = proc.connections()
            ports = list(set(c.laddr.port for c in connections if c.laddr))

            return ProcessInfo(
                pid=proc.pid,
                name=proc.name(),
                status=proc.status(),
                cpu_percent=proc.cpu_percent(interval=0.1),
                memory_percent=proc.memory_percent(),
                memory_mb=proc.memory_info().rss / (1024 * 1024),
                num_threads=proc.num_threads(),
                created_time=datetime.fromtimestamp(proc.create_time()),
                ports=ports
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None

    def get_processes_by_port(self, port: int) -> List[ProcessInfo]:
        """
        Get all processes listening on or connected to a specific port.

        Args:
            port: Port number

        Returns:
            List of ProcessInfo objects
        """
        matching_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                connections = proc.connections()
                if any(c.laddr.port == port for c in connections if c.laddr):
                    proc_info = self.get_process_by_pid(proc.pid)
                    if proc_info:
                        matching_processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return matching_processes

    def get_system_stats(self) -> Dict[str, any]:
        """
        Get overall system resource statistics.

        Returns:
            Dictionary with CPU, memory, disk, and network stats
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net_io = psutil.net_io_counters()

        return {
            "cpu": {
                "percent": cpu_percent,
                "count": psutil.cpu_count(logical=True),
                "count_physical": psutil.cpu_count(logical=False)
            },
            "memory": {
                "total_mb": memory.total / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
                "used_mb": memory.used / (1024 * 1024),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": disk.total / (1024 * 1024 * 1024),
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
                "percent": disk.percent
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        }

    def get_listening_ports(self) -> Set[int]:
        """
        Get all ports currently being listened on.

        Returns:
            Set of port numbers
        """
        ports = set()
        for conn in psutil.net_connections():
            if conn.status == 'LISTEN' and conn.laddr:
                ports.add(conn.laddr.port)
        return ports

    def get_process_count(self) -> int:
        """
        Get total number of running processes.

        Returns:
            Process count
        """
        return len(list(psutil.process_iter()))

    def get_thread_count(self) -> int:
        """
        Get total number of threads across all processes.

        Returns:
            Thread count
        """
        total_threads = 0
        for proc in psutil.process_iter(['num_threads']):
            try:
                total_threads += proc.info.get('num_threads', 1)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total_threads

    def kill_process(self, pid: int, force: bool = False) -> bool:
        """
        Terminate a process by PID.

        Args:
            pid: Process ID to terminate
            force: If True, use SIGKILL instead of SIGTERM

        Returns:
            True if process was terminated, False otherwise
        """
        try:
            proc = psutil.Process(pid)
            if force:
                proc.kill()
            else:
                proc.terminate()
            logger.info("process_terminated", pid=pid, force=force)
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning("failed_to_terminate_process", pid=pid, error=str(e))
            return False
