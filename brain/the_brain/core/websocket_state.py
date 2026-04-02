"""
WebSocket Live-State Streaming (PHASE 7: P7.98)

Real-time brain state streaming using Server-Sent Events (SSE).
Falls back to polling if SSE is not supported.

Features:
1. SSE-based live state streaming
2. Configurable update intervals per channel
3. Multiple channels: brain_state, cognitive_loop, emotional, neuromodulation
4. Client connection tracking
5. Automatic cleanup of stale connections
"""

import time
import json
import logging
import threading
from typing import Dict, Any, Optional, List, Generator
from dataclasses import dataclass, field
from datetime import datetime
from queue import Queue, Empty

logger = logging.getLogger('brain.websocket_state')


@dataclass
class SSEClient:
    """Represents a connected SSE client."""
    client_id: str
    channels: List[str]
    queue: Queue = field(default_factory=lambda: Queue(maxsize=50))
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def push(self, event: str, data: Dict) -> bool:
        """Push an event to this client. Returns False if queue is full."""
        try:
            self.queue.put_nowait({'event': event, 'data': data})
            self.last_activity = time.time()
            return True
        except:
            return False


class LiveStateStreamer:
    """
    Manages real-time brain state streaming to connected clients.
    """

    # Available channels
    CHANNELS = ['brain_state', 'cognitive_loop', 'emotional', 'neuromodulation',
                'consciousness', 'memory', 'goals', 'frequency', 'events']

    def __init__(self, update_interval: float = 1.0, stale_timeout: float = 300.0):
        self._clients: Dict[str, SSEClient] = {}
        self._lock = threading.Lock()
        self._update_interval = update_interval
        self._stale_timeout = stale_timeout
        self._running = False
        self._broadcast_thread: Optional[threading.Thread] = None
        self._brain_ref = None
        self._total_broadcasts = 0
        self._total_clients_served = 0

    def set_brain(self, brain) -> None:
        """Set the brain reference for state polling."""
        self._brain_ref = brain

    def register_client(self, client_id: str, channels: Optional[List[str]] = None) -> SSEClient:
        """Register a new SSE client."""
        if channels is None:
            channels = ['brain_state']

        # Validate channels
        channels = [c for c in channels if c in self.CHANNELS]
        if not channels:
            channels = ['brain_state']

        client = SSEClient(client_id=client_id, channels=channels)
        with self._lock:
            self._clients[client_id] = client
            self._total_clients_served += 1

        logger.info(f"SSE client registered: {client_id} channels={channels}")
        return client

    def unregister_client(self, client_id: str) -> None:
        """Unregister an SSE client."""
        with self._lock:
            self._clients.pop(client_id, None)
        logger.info(f"SSE client unregistered: {client_id}")

    def get_client_stream(self, client: SSEClient) -> Generator[str, None, None]:
        """Generate SSE event stream for a client."""
        try:
            while True:
                try:
                    msg = client.queue.get(timeout=30)
                    event_name = msg.get('event', 'message')
                    data = json.dumps(msg.get('data', {}))
                    yield f"event: {event_name}\ndata: {data}\n\n"
                except Empty:
                    # Send keepalive
                    yield f": keepalive {datetime.now().isoformat()}\n\n"
        except GeneratorExit:
            self.unregister_client(client.client_id)

    def broadcast(self, channel: str, data: Dict[str, Any]) -> int:
        """Broadcast data to all clients subscribed to a channel."""
        dispatched = 0
        with self._lock:
            clients = list(self._clients.values())

        for client in clients:
            if channel in client.channels:
                if client.push(channel, data):
                    dispatched += 1

        self._total_broadcasts += 1
        return dispatched

    def _collect_brain_state(self) -> Dict[str, Any]:
        """Collect current brain state for broadcasting."""
        if self._brain_ref is None:
            return {}

        state = {}
        brain = self._brain_ref

        try:
            # Brain state
            if hasattr(brain, 'get_statistics'):
                stats = brain.get_statistics()
                state['brain_state'] = {
                    'total_predictions': stats.get('total_predictions', 0),
                    'total_feedback': stats.get('total_feedback', 0),
                    'timestamp': datetime.now().isoformat()
                }
        except Exception:
            pass

        try:
            # Cognitive loop
            if hasattr(brain, 'cognitive_loop') and brain.cognitive_loop:
                loop_state = brain.cognitive_loop.get_loop_state()
                state['cognitive_loop'] = loop_state
        except Exception:
            pass

        try:
            # Emotional state
            if hasattr(brain, 'cognitive_loop') and brain.cognitive_loop:
                cl = brain.cognitive_loop
                if hasattr(cl, '_emotional_system') and cl._emotional_system:
                    es = cl._emotional_system
                    if hasattr(es, 'state'):
                        state['emotional'] = {
                            'valence': float(es.state.valence),
                            'arousal': float(es.state.arousal),
                        }
        except Exception:
            pass

        try:
            # Neuromodulation
            planner = getattr(brain, 'planner', brain)
            if hasattr(planner, 'neuromodulation') and planner.neuromodulation:
                nm = planner.neuromodulation
                if hasattr(nm, 'levels') and hasattr(nm.levels, 'to_dict'):
                    state['neuromodulation'] = nm.levels.to_dict()
        except Exception:
            pass

        try:
            # Consciousness
            planner = getattr(brain, 'planner', brain)
            if hasattr(planner, 'consciousness') and planner.consciousness:
                cs = planner.consciousness
                if hasattr(cs, 'current_state') and hasattr(cs.current_state, 'to_dict'):
                    state['consciousness'] = cs.current_state.to_dict()
        except Exception:
            pass

        return state

    def _broadcast_loop(self):
        """Background thread that periodically broadcasts state."""
        while self._running:
            try:
                with self._lock:
                    client_count = len(self._clients)

                if client_count > 0:
                    state = self._collect_brain_state()
                    for channel, data in state.items():
                        self.broadcast(channel, data)

                # Cleanup stale clients
                self._cleanup_stale()

            except Exception as e:
                logger.error(f"Broadcast loop error: {e}")

            time.sleep(self._update_interval)

    def _cleanup_stale(self):
        """Remove stale clients that haven't had activity."""
        now = time.time()
        stale = []
        with self._lock:
            for cid, client in self._clients.items():
                if now - client.last_activity > self._stale_timeout:
                    stale.append(cid)
            for cid in stale:
                del self._clients[cid]

        if stale:
            logger.info(f"Cleaned up {len(stale)} stale SSE clients")

    def start(self):
        """Start the broadcast loop."""
        if self._running:
            return
        self._running = True
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcast_thread.start()
        logger.info("LiveStateStreamer started")

    def stop(self):
        """Stop the broadcast loop."""
        self._running = False
        if self._broadcast_thread:
            self._broadcast_thread.join(timeout=5)
        logger.info("LiveStateStreamer stopped")

    def get_statistics(self) -> Dict[str, Any]:
        """Get streamer statistics."""
        with self._lock:
            client_count = len(self._clients)
            client_info = [
                {
                    'client_id': c.client_id,
                    'channels': c.channels,
                    'connected_seconds': round(time.time() - c.connected_at, 1),
                    'queue_size': c.queue.qsize(),
                }
                for c in self._clients.values()
            ]

        return {
            'active_clients': client_count,
            'total_clients_served': self._total_clients_served,
            'total_broadcasts': self._total_broadcasts,
            'update_interval': self._update_interval,
            'running': self._running,
            'clients': client_info,
            'available_channels': self.CHANNELS,
        }


# Module-level singleton
_streamer: Optional[LiveStateStreamer] = None
_streamer_lock = threading.Lock()


def get_live_streamer(update_interval: float = 1.0) -> LiveStateStreamer:
    """Get or create the global live state streamer."""
    global _streamer
    if _streamer is None:
        with _streamer_lock:
            if _streamer is None:
                _streamer = LiveStateStreamer(update_interval=update_interval)
    return _streamer
