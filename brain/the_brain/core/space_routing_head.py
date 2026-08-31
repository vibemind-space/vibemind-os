"""SpaceRoutingHead — maps Ring 3 activations to space routing decisions via learned centroids."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from .space_contract import load_space_contract

logger = logging.getLogger('brain.space_routing_head')


def _is_learner() -> bool:
    """Phase D: only the learner / a mono brain may mutate or persist
    space centroids. Inference replicas stay read-only. Fail-safe → True
    (legacy mono behaviour unchanged for a single brain)."""
    try:
        from core import config as _cfg
        return _cfg.is_learner()
    except Exception:
        return True


_SPACE_CONTRACT = load_space_contract()
SPACE_NAMES = list(_SPACE_CONTRACT.space_ids)

# Complete event_type → space mapping (from EventRouter.STREAM_MAPPING)
_LEGACY_EVENT_SPACE_MAP = {
    # Coding
    "code.generate": "coding", "code.modify": "coding", "code.status": "coding",
    "code.show": "coding", "code.preview.start": "coding", "code.preview.stop": "coding",
    "code.list": "coding", "code.cancel": "coding",
    # Desktop
    "desktop.open_app": "desktop", "desktop.click": "desktop", "desktop.type": "desktop",
    "desktop.press_key": "desktop", "desktop.screenshot": "desktop", "desktop.scroll": "desktop",
    "desktop.task": "desktop", "desktop.task.create": "desktop", "desktop.task.update": "desktop",
    "desktop.task.list": "desktop", "desktop.moire.scan": "desktop", "desktop.moire.find": "desktop",
    "messaging.whatsapp": "desktop", "messaging.telegram": "desktop", "messaging.send": "desktop",
    "web.search": "desktop", "web.fetch": "desktop",
    "openclaw.status": "desktop", "openclaw.notifications": "desktop",
    "openclaw.prompt": "desktop",
    # OpenClaw browser + messaging events
    "openclaw.browse": "desktop", "openclaw.scrape": "desktop",
    "openclaw.screenshot.web": "desktop", "openclaw.fill_form": "desktop",
    "openclaw.research": "research", "openclaw.compare": "research",
    "openclaw.message.send": "desktop", "openclaw.message.read": "desktop",
    "openclaw.linkedin.search": "desktop",
    "openclaw.enrich": "ideas", "openclaw.pitch": "ideas",
    "openclaw.monitor": "desktop", "openclaw.cron": "schedule",
    # Bubbles
    "bubble.list": "bubbles", "bubble.create": "bubbles", "bubble.enter": "bubbles",
    "bubble.exit": "bubbles", "bubble.back": "bubbles", "bubble.delete": "bubbles",
    "bubble.delete_all_except": "bubbles", "bubble.update": "bubbles", "bubble.find": "bubbles",
    "bubble.stats": "bubbles", "bubble.score": "bubbles", "bubble.evaluate": "bubbles",
    "bubble.promote": "bubbles", "bubble.current": "bubbles",
    # Ideas
    "idea.list": "ideas", "idea.create": "ideas", "idea.update": "ideas",
    "idea.delete": "ideas", "idea.find": "ideas", "idea.connect": "ideas",
    "idea.auto_link": "ideas", "idea.add_image": "ideas", "idea.current_space": "ideas",
    "idea.format_table": "ideas", "idea.summarize": "ideas", "idea.whitepaper": "ideas",
    "idea.expand": "ideas", "idea.explain": "ideas", "idea.analyze_links": "ideas",
    "idea.format_note": "ideas", "idea.format_action_list": "ideas",
    "idea.format_pros_cons": "ideas", "idea.format_hierarchy": "ideas",
    "idea.format_specs": "ideas", "idea.convert_format": "ideas",
    "idea.explore.start": "ideas", "idea.explore.stop": "ideas",
    "idea.generate_doc": "ideas", "idea.to_project": "ideas",
    # Research
    "research.web": "research", "research.scrape": "research",
    "research.summarize": "research", "research.to_idea": "research",
    # Roarboot (Knowledge Graph)
    "roarboot.search": "roarboot", "roarboot.query": "roarboot",
    "roarboot.email_draft": "roarboot", "roarboot.meeting_brief": "roarboot",
    "roarboot.deck": "roarboot", "roarboot.status": "roarboot",
    "roarboot.docker.start": "roarboot", "roarboot.docker.stop": "roarboot",
    # Minibook
    "minibook.discuss": "minibook", "minibook.collaborate": "minibook",
    "minibook.status": "minibook", "minibook.list_projects": "minibook",
    # Schedule
    "schedule.create": "schedule", "schedule.list": "schedule",
    "schedule.cancel": "schedule", "schedule.modify": "schedule",
    "schedule.status": "schedule", "schedule.snooze": "schedule",
    # N8n
    "n8n.generate": "n8n", "n8n.list": "n8n", "n8n.status": "n8n",
    "n8n.activate": "n8n", "n8n.deactivate": "n8n", "n8n.delete": "n8n",
    "n8n.execute": "n8n", "n8n.describe": "n8n",
    # AgentFarm
    "agentfarm.create_team": "agentfarm", "agentfarm.run": "agentfarm",
    "agentfarm.status": "agentfarm", "agentfarm.list_teams": "agentfarm",
    "agentfarm.stop": "agentfarm", "agentfarm.results": "agentfarm",
    "agentfarm.list_templates": "agentfarm", "agentfarm.collaborate": "agentfarm",
    # Video
    "video.status": "video", "video.team_status": "video", "video.team_run": "video",
    "video.vision": "video", "video.demo_analyze": "video", "video.demo_build": "video",
    "video.lipsync": "video", "video.voice_clone": "video", "video.voice_tts": "video",
    # Flowzen
    "rose.recommend": "flowzen", "rose.accept": "flowzen", "rose.status": "flowzen",
    # MiroFish
    "mirofish.simulate": "mirofish", "mirofish.predict": "mirofish",
    "mirofish.graph.build": "mirofish", "mirofish.graph.search": "mirofish",
    "mirofish.status": "mirofish", "mirofish.evaluate": "mirofish",
    "mirofish.interview": "mirofish",
}

# Registry-owned runtime mapping.  The legacy literal above remains inert as
# migration documentation and cannot influence routing decisions.
EVENT_SPACE_MAP = dict(_SPACE_CONTRACT.event_space_map)


class SpaceRoutingHead(nn.Module):
    """Lightweight routing head: cosine similarity between Ring 3 output and space centroids.

    Centroids are trained by reward-modulated Hebbian learning when agents succeed/fail.
    """

    def __init__(self, ring3_dim: int = 256, spaces: Optional[List[str]] = None):
        super().__init__()
        self.space_names = list(spaces or SPACE_NAMES)
        self.centroids = nn.Parameter(torch.randn(len(self.space_names), ring3_dim) * 0.1)
        self._pending_routes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._total_routes = 0
        self._total_rewards = 0
        self._train_count_since_save = 0

    def forward(self, ring3_activation: torch.Tensor) -> torch.Tensor:
        """Cosine similarity between Ring 3 output and all space centroids.

        Args:
            ring3_activation: (1, 256) or (256,) tensor from Ring 3
        Returns:
            (num_spaces,) tensor of cosine similarities
        """
        q = F.normalize(ring3_activation.flatten().unsqueeze(0), dim=-1)
        c = F.normalize(self.centroids, dim=-1)
        sims = (q @ c.T).squeeze(0)
        return sims

    def route(self, ring3_activation: torch.Tensor) -> Dict[str, Any]:
        """Full routing decision with ID tracking for reward feedback."""
        with torch.no_grad():
            sims = self.forward(ring3_activation)

        best_idx = sims.argmax().item()
        confidence = float(sims[best_idx].item())

        # Top-2 for secondary spaces
        top2 = sims.topk(min(2, len(self.space_names))).indices.tolist()
        secondary = [self.space_names[i] for i in top2 if i != best_idx]

        routing_id = f"rt_{uuid.uuid4().hex[:8]}"

        with self._lock:
            self._pending_routes[routing_id] = {
                'space': self.space_names[best_idx],
                'embedding': ring3_activation.detach().clone(),
                'timestamp': time.time(),
            }
            self._total_routes += 1

        return {
            'primary_space': self.space_names[best_idx],
            'secondary_spaces': secondary,
            'confidence': round(confidence, 4),
            'routing_id': routing_id,
        }

    def reward(self, routing_id: str, success: bool, lr: float = 0.01) -> bool:
        """Update centroid based on agent outcome.

        Args:
            routing_id: ID from route() call
            success: Whether the agent succeeded
            lr: Learning rate for centroid update
        Returns:
            True if reward was applied, False if routing_id not found OR
            this is an inference replica (read-only — Phase D).
        """
        if not _is_learner():
            return False  # inference replica: never mutate centroids
        with self._lock:
            rec = self._pending_routes.pop(routing_id, None)
        if rec is None:
            return False

        space_idx = self.space_names.index(rec['space'])
        reward_val = 0.5 if success else -0.3

        with torch.no_grad():
            emb = F.normalize(rec['embedding'].flatten().unsqueeze(0), dim=-1)
            self.centroids.data[space_idx] += lr * reward_val * emb.squeeze(0)

        self._total_rewards += 1
        self._train_count_since_save += 1
        logger.info(f"Routing reward: {rec['space']} {'SUCCESS' if success else 'FAIL'} "
                     f"(routing_id={routing_id}, reward={reward_val})")
        return True

    def train_supervised(self, ring3_activation: torch.Tensor,
                         correct_space: str, lr: float = 0.05) -> bool:
        """Supervised centroid update from shadow observer ground truth.

        Stronger than reward — directly moves centroid toward correct embedding.
        Also slightly repels other centroids to increase separation.

        Returns True if training was applied.
        """
        if not _is_learner():
            return False  # inference replica: read-only (Phase D)
        if correct_space not in self.space_names:
            return False
        correct_idx = self.space_names.index(correct_space)
        with torch.no_grad():
            emb = F.normalize(ring3_activation.flatten().unsqueeze(0), dim=-1).squeeze(0)
            # Attract correct centroid
            self.centroids.data[correct_idx] += lr * emb
            # Repel other centroids slightly
            for i in range(len(self.space_names)):
                if i != correct_idx:
                    self.centroids.data[i] -= (lr * 0.2) * emb
        self._total_rewards += 1
        self._train_count_since_save += 1
        return True

    # ------------------------------------------------------------------
    # Persistence (mirrors EventRoutingHead.save/load)
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist centroids and space_names to disk.

        Phase D: only the learner persists (avoids inference replicas
        racing the learner on a shared checkpoint volume).
        """
        if not _is_learner():
            return
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        torch.save({
            'centroids': self.centroids.data,
            'space_names': self.space_names,
            'total_routes': self._total_routes,
            'total_rewards': self._total_rewards,
            'version': 1,
        }, path)
        self._train_count_since_save = 0
        logger.info(f"SpaceRoutingHead saved to {path}")

    def load(self, path: str) -> bool:
        """Load centroids from disk. Returns True on success.

        Rejects the load if the saved space_names differ from the current
        list (e.g. new spaces were added since the checkpoint was written),
        so we never silently feed misaligned centroids.
        """
        try:
            ckpt = torch.load(path, map_location='cpu', weights_only=False)
        except Exception as e:
            logger.warning(f"SpaceRoutingHead load failed ({path}): {e}")
            return False

        saved_names = ckpt.get('space_names', [])
        if saved_names != self.space_names:
            logger.warning(
                f"SpaceRoutingHead checkpoint space_names differ "
                f"(saved={len(saved_names)}, current={len(self.space_names)}). "
                f"Refusing to load — re-seed instead."
            )
            return False

        with torch.no_grad():
            self.centroids.data = ckpt['centroids'].clone()
        self._total_routes = int(ckpt.get('total_routes', 0))
        self._total_rewards = int(ckpt.get('total_rewards', 0))
        self._train_count_since_save = 0
        logger.info(
            f"SpaceRoutingHead loaded from {path} "
            f"({len(self.space_names)} spaces, {self._total_routes} prior routes)"
        )
        return True

    def should_autosave(self, every_n: int = 100) -> bool:
        """Whether enough training has accumulated to warrant an autosave."""
        return self._train_count_since_save >= every_n

    def maybe_reload(self, path: str) -> bool:
        """Phase D3: reload centroids from disk if the file changed (mtime).
        Inference replicas poll this to pick up the learner's save() on a
        shared volume without restarting. Returns True if reloaded."""
        import os
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return False
        last = getattr(self, "_ckpt_mtime", None)
        if last is not None and mtime <= last:
            return False
        ok = self.load(path)
        if ok:
            self._ckpt_mtime = mtime
            logger.info(f"SpaceRoutingHead reloaded from {path} (mtime changed)")
        return ok

    def cleanup_stale(self, max_age: float = 300.0) -> int:
        """Remove pending routes older than max_age seconds. Returns count removed."""
        cutoff = time.time() - max_age
        with self._lock:
            stale = [k for k, v in self._pending_routes.items() if v['timestamp'] < cutoff]
            for k in stale:
                del self._pending_routes[k]
        return len(stale)

    def seed_from_event_map(self, agent_loop) -> int:
        """Pre-train centroids from EVENT_SPACE_MAP on startup.

        Encodes each event_type string through the RadialNetwork and
        uses the Ring 3 output to initialize the correct space centroid.
        This gives the brain a head-start instead of random centroids.

        Args:
            agent_loop: AgentLoop with seed_encoder + radial_network
        Returns:
            Number of events seeded
        """
        import torch as _torch
        if agent_loop is None:
            return 0
        encoder = getattr(agent_loop, 'seed_encoder', None)
        radial = getattr(agent_loop, 'radial_network', None)
        if encoder is None or radial is None:
            return 0

        count = 0
        for event_type, space in EVENT_SPACE_MAP.items():
            if space not in self.space_names:
                continue
            try:
                seed_np = encoder.encode_from_description(event_type)
                seed_tensor = _torch.tensor(seed_np, dtype=_torch.float32).unsqueeze(0)
                with _torch.no_grad():
                    result = radial.forward(seed_tensor)
                ring3 = result['ring_activations'][2]
                self.train_supervised(ring3, space, lr=0.02)
                count += 1
            except Exception:
                continue

        logger.info(f"SpaceRoutingHead seeded from {count} event_type mappings")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Stats for diagnostics endpoint."""
        with self._lock:
            pending = len(self._pending_routes)
        centroid_norms = self.centroids.data.norm(dim=1).tolist()
        return {
            'total_routes': self._total_routes,
            'total_rewards': self._total_rewards,
            'pending_routes': pending,
            'spaces': {name: round(norm, 4) for name, norm in zip(self.space_names, centroid_norms)},
        }
