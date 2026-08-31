"""EventRoutingHead — maps text embeddings to event_type via learned centroids.

Routes to ~120 event_types (e.g. "bubble.list", "idea.create"). Cosine similarity
between an input embedding and learned per-event centroids; centroids are
refined by Hebbian reward and supervised training.

Embedding source: by default, sentence-transformers (SBERT MiniLM, 384-dim).
The Brain's SeedEncoder + RadialNetwork pipeline was tested first but its
hashed-bag-of-words signal was too weak to separate 123 event types — see
`docs/event_classifier_separability.md` if you need the receipts.

The EventRoutingHead is embedder-agnostic: pass `embed_dim=384` for SBERT
or `embed_dim=256` to feed it Ring 3 activations from the existing pipeline.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from core.space_routing_head import EVENT_SPACE_MAP

logger = logging.getLogger('brain.event_routing_head')


def _is_learner() -> bool:
    """Phase D: only the learner (or a mono brain) may mutate/persist
    centroids. Inference replicas must stay read-only or routing diverges.
    Fail-safe: if config can't import, default to True (= legacy mono
    behaviour, nothing changes for a single brain)."""
    try:
        from core import config as _cfg
        return _cfg.is_learner()
    except Exception:
        return True

# Conversation events — not tied to any space but still real classification
# targets from the LLM. SpaceRoutingHead ignores these; EventRoutingHead needs
# them as valid classes, otherwise every "hi" fails with 'event not in list'.
CONVERSATION_EVENTS: List[str] = [
    "conversation.greeting",
    "conversation.farewell",
    "conversation.unknown",
    "conversation.listening",
    "conversation.help",
    "evaluation.correct",
    "evaluation.incorrect",
]

# Stable, sorted list of all event_types we know about. Sorting keeps the
# centroid index assignment deterministic across restarts.
EVENT_NAMES: List[str] = sorted(set(EVENT_SPACE_MAP.keys()) | set(CONVERSATION_EVENTS))


# Curated seed phrases per event_type for warm-start.
# These give the EventRoutingHead enough variety per class that it can route
# real user inputs reasonably even before any shadow-mode training has run.
# Add bilingual variants (DE/EN) for the events the user actually triggers.
EVENT_SEED_PHRASES: Dict[str, List[str]] = {
    # ── Bubbles ────────────────────────────────────────────────────────
    "bubble.list": [
        "list bubbles", "show bubbles", "show all bubbles", "what bubbles do i have",
        "zeige bubbles", "zeige alle bubbles", "liste bubbles", "welche bubbles habe ich",
        "alle bubbles anzeigen", "bubbles auflisten",
    ],
    "bubble.create": [
        "create bubble", "new bubble", "make a new bubble",
        "erstelle bubble", "neue bubble", "bubble erstellen",
    ],
    "bubble.delete": [
        "delete bubble", "delete this bubble", "remove bubble",
        "delete the bubble called X", "delete bubble 5",
        "lösche die bubble", "lösche bubble", "lösche diese bubble",
        "bubble löschen", "entferne bubble", "die bubble löschen",
        "lösch die bubble weg", "kill that bubble",
    ],
    "bubble.exit": [
        "exit bubble", "leave bubble", "close bubble", "go back from bubble",
        "verlasse bubble", "bubble verlassen", "raus aus der bubble",
        "zurück aus bubble", "leave the current bubble",
    ],
    "bubble.promote": [
        "promote bubble to project", "upgrade bubble", "convert bubble to project",
        "bubble zum projekt machen", "bubble befoerdern",
    ],
    "bubble.find": [
        "find bubble", "search for bubble", "where is bubble",
        "finde bubble", "suche bubble",
    ],
    "bubble.stats": [
        "bubble stats", "bubble statistics", "show bubble metrics",
        "bubble statistik", "bubble übersicht",
    ],
    "bubble.enter": [
        "enter bubble", "open bubble", "go into bubble",
        "öffne bubble", "betrete bubble", "in bubble wechseln",
    ],
    "bubble.current": [
        "current bubble", "what bubble am i in", "which bubble",
        "aktuelle bubble", "wo bin ich", "welche bubble bin ich",
    ],

    # ── Ideas ──────────────────────────────────────────────────────────
    "idea.list": [
        "list ideas", "show ideas", "show all ideas", "what ideas do i have",
        "zeige ideen", "liste ideen", "welche ideen habe ich",
    ],
    "idea.create": [
        "create idea", "new idea", "i have an idea", "add an idea",
        "create idea about API design", "new idea: build a chat app",
        "erstelle idee", "neue idee", "ich habe eine idee", "ideen hinzufügen",
        "erstelle eine neue idee", "ich habe gerade eine idee",
    ],
    "idea.delete": [
        "delete idea", "remove idea",
        "lösche idee", "idee löschen",
    ],
    "idea.find": [
        "find idea", "search idea",
        "finde idee", "suche idee",
    ],
    "idea.update": [
        "update idea", "edit idea", "change idea",
        "ändere idee", "idee bearbeiten", "idee ändern",
    ],
    "idea.summarize": [
        "summarize idea", "summarize this", "give me a summary",
        "fasse zusammen", "zusammenfassung",
    ],
    "idea.expand": [
        "expand on this idea", "elaborate", "tell me more",
        "erweitere die idee", "erkläre mehr",
    ],
    "idea.connect": [
        "connect ideas", "link ideas",
        "verbinde ideen", "ideen verknüpfen",
    ],

    # ── Conversation ───────────────────────────────────────────────────
    # Many variants needed because in multilingual SBERT short greetings
    # cluster close to "send a message" — extra seed mass keeps them apart.
    "conversation.greeting": [
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening", "good night",
        "hi there", "hello there", "hey there", "howdy", "yo", "sup",
        "hallo", "hi", "hey", "hallöchen", "servus", "moin", "moin moin",
        "guten tag", "guten morgen", "guten abend", "schönen tag",
        "ciao", "hola", "salut", "bonjour",
    ],
    "conversation.farewell": [
        "bye", "goodbye", "see you", "see you later", "cya", "take care",
        "tschüss", "tschüss bis später", "bis dann", "bis morgen",
        "auf wiedersehen", "machs gut", "ciao",
    ],
    "conversation.help": [
        "help", "what can you do", "how do I use this", "how does this work",
        "hilfe", "was kannst du", "wie funktioniert das", "was geht",
    ],
    "evaluation.correct": [
        "perfekt", "genau das", "ja genau", "richtig so", "stimmt", "super",
        "perfect", "exactly", "yes that's right", "correct", "nice",
    ],
    "evaluation.incorrect": [
        "nein das war falsch", "falsch verstanden", "nicht das", "das war falsch",
        "no that's wrong", "wrong", "not what I wanted", "misunderstood",
    ],

    # ── Web / Research ─────────────────────────────────────────────────
    "web.search": [
        "search the web", "google this", "look it up online", "search for",
        "suche im web", "google das", "im internet suchen",
    ],
    "web.fetch": [
        "fetch this url", "open this link", "get this page",
        "lade diese url", "hole die seite",
    ],
    "research.web": [
        "research this", "do some research",
        "recherchiere das", "mach eine recherche",
    ],
    "research.summarize": [
        "summarize this research", "summarize the article",
        "fasse den artikel zusammen",
    ],

    # ── Desktop ────────────────────────────────────────────────────────
    "desktop.screenshot": [
        "take a screenshot", "screenshot please", "capture the screen",
        "mach einen screenshot", "bildschirmfoto", "screen aufnehmen",
    ],
    "desktop.open_app": [
        "open application", "launch app", "start program",
        "öffne anwendung", "starte programm", "app öffnen",
    ],
    "desktop.click": [
        "click here", "click that button", "click the button",
        "klick hier", "klicke auf",
    ],
    "desktop.type": [
        "type this", "type the text",
        "tippe das", "schreibe",
    ],
    "desktop.task.create": [
        "create a task", "create a new task", "add a todo", "new task",
        "remind me to buy milk", "add task: review PR",
        "erstelle eine aufgabe", "erstelle eine neue aufgabe", "neue aufgabe anlegen",
        "neue aufgabe", "todo hinzufügen", "aufgabe erstellen",
    ],
    "desktop.task.list": [
        "list tasks", "list my tasks", "show my tasks", "show todos", "show all tasks",
        "what are my tasks",
        "zeige aufgaben", "liste aufgaben", "todos anzeigen", "welche aufgaben habe ich",
    ],

    # ── Code ───────────────────────────────────────────────────────────
    "code.generate": [
        "generate code", "write code", "build me a function",
        "generiere code", "schreibe code", "erstelle eine funktion",
    ],
    "code.modify": [
        "modify code", "change the code", "refactor",
        "ändere code", "code ändern", "code refactorn",
    ],
    "code.list": [
        "list projects", "show my projects",
        "zeige projekte", "liste projekte",
    ],
    "code.status": [
        "code status", "build status", "deployment status",
        "build-status", "deployment-status",
    ],

    # ── Schedule ───────────────────────────────────────────────────────
    "schedule.create": [
        "schedule a meeting", "schedule a meeting tomorrow", "create a reminder",
        "set an alarm for 8am", "remind me at 5pm",
        "termin erstellen", "termin am freitag eintragen", "erinnerung setzen",
        "wecker auf 8 uhr stellen", "neuer termin",
    ],
    "schedule.list": [
        "list schedule", "list my appointments", "show my calendar",
        "what's on my agenda", "what meetings do i have today",
        "zeige termine", "liste termine", "kalender anzeigen", "was steht an",
        "welche termine habe ich",
    ],

    # ── Messaging ──────────────────────────────────────────────────────
    "messaging.send": [
        "send a message to john", "send a chat to anna",
        "message marcel about the meeting", "tell sarah we're running late",
        "schreibe john eine nachricht", "sage marcel bescheid",
        "schick anna eine nachricht", "informiere das team",
    ],
    "messaging.whatsapp": [
        "send a whatsapp message to john", "whatsapp marcel about the meeting",
        "schicke marcel eine whatsapp nachricht", "über whatsapp an anna senden",
    ],

    # ── MiroFish (the rule-bug victim) ─────────────────────────────────
    "mirofish.evaluate": [
        "evaluate bubble", "rate this bubble", "is this bubble ready",
        "bewerte bubble", "ist die bubble bereit", "bubble evaluation",
    ],

    # ── OpenClaw (browser + messaging + research) ─────────────────────
    "openclaw.browse": [
        "open website", "go to website", "browse to", "navigate to url",
        "oeffne webseite", "geh auf die seite", "zeig mir die website",
    ],
    "openclaw.scrape": [
        "scrape website", "read the page", "extract data from website",
        "lies die seite aus", "daten von der website holen",
    ],
    "openclaw.research": [
        "research this topic", "do web research", "find information about",
        "recherchiere das thema", "finde infos ueber", "web recherche",
    ],
    "openclaw.message.send": [
        "send whatsapp message", "send telegram message", "schick eine nachricht",
        "whatsapp an", "telegram an", "slack nachricht senden",
    ],
    "openclaw.message.read": [
        "read my messages", "check whatsapp", "read telegram",
        "lies meine nachrichten", "zeig whatsapp", "neue nachrichten",
    ],
    "openclaw.linkedin.search": [
        "search linkedin", "find people on linkedin", "linkedin suche",
        "finde leute auf linkedin", "linkedin jobs suchen",
    ],
    "openclaw.enrich": [
        "enrich this idea with research", "add web research to idea",
        "reichere die idee an", "recherchiere mehr zu dieser idee",
    ],
    "openclaw.pitch": [
        "create a pitch", "write a pitch deck", "pitch erstellen",
        "mach einen pitch fuer die bubble", "investor pitch schreiben",
    ],
    "openclaw.compare": [
        "compare prices", "compare services", "which is better",
        "vergleiche preise", "was ist besser", "vergleich",
    ],
    "openclaw.monitor": [
        "monitor website", "watch this url", "alert me if down",
        "ueberwache die seite", "benachrichtige mich wenn offline",
    ],

    # ── n8n ────────────────────────────────────────────────────────────
    "n8n.list": [
        "list workflows", "show workflows", "list n8n",
        "zeige workflows", "n8n workflows",
    ],
    "n8n.execute": [
        "run workflow", "execute workflow", "trigger n8n",
        "starte workflow", "workflow ausführen",
    ],
}


class EventRoutingHead(nn.Module):
    """Routing head: cosine similarity between Ring 3 output and event-type centroids.

    Centroids start near zero, get seeded from event-name embeddings, and are
    refined by reward-modulated Hebbian learning + supervised training from
    the LLM-classifier ground truth (shadow mode).
    """

    def __init__(self, embed_dim: int = 384, events: Optional[List[str]] = None):
        """Initialize the head.

        Args:
            embed_dim: dimensionality of the input embeddings. 384 for SBERT
                MiniLM (default), 256 for the Brain's Ring 3 if you want to
                feed in radial activations instead.
            events: optional override of the event-name list. Defaults to
                the sorted EVENT_SPACE_MAP keys.
        """
        super().__init__()
        self.event_names = list(events or EVENT_NAMES)
        self.embed_dim = embed_dim
        self.centroids = nn.Parameter(torch.randn(len(self.event_names), embed_dim) * 0.1)
        self._pending_routes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._total_routes = 0
        self._total_rewards = 0
        self._train_count_since_save = 0
        # Per-user sparse deltas over the shared base centroids.
        #   user_deltas[user_id][event_idx] = tensor of shape (embed_dim,)
        # A given user only has entries for events they've actually trained on.
        # At inference, effective_centroid[i] = base[i] + user_delta[user_id][i]
        # (zero if absent). This gives personalization without duplicating the
        # full centroid matrix per user.
        self.user_deltas: Dict[str, Dict[int, torch.Tensor]] = {}

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _effective_centroids(self, user_id: Optional[str]) -> torch.Tensor:
        """Return centroids with per-user deltas folded in.

        Returns the shared base if no user_id is given or the user has no
        deltas yet. Otherwise returns a cloned matrix with the user's
        sparse deltas added to the relevant rows.
        """
        if user_id is None or user_id not in self.user_deltas:
            return self.centroids
        deltas = self.user_deltas.get(user_id) or {}
        if not deltas:
            return self.centroids
        # Clone to avoid mutating the nn.Parameter
        effective = self.centroids.data.clone()
        for event_idx, delta in deltas.items():
            if 0 <= event_idx < effective.shape[0]:
                effective[event_idx] = effective[event_idx] + delta
        return effective

    def forward(self, embedding: torch.Tensor, user_id: Optional[str] = None) -> torch.Tensor:
        """Cosine similarity between an input embedding and all event centroids.

        Args:
            embedding: (1, embed_dim) or (embed_dim,) tensor from SBERT (or Ring 3)
            user_id: optional user identifier. When provided, per-user deltas
                are folded into the centroids before similarity. Unknown users
                fall back to the shared base.
        Returns:
            (num_events,) tensor of cosine similarities in [-1, 1]
        """
        q = F.normalize(embedding.flatten().unsqueeze(0), dim=-1)
        c = F.normalize(self._effective_centroids(user_id), dim=-1)
        sims = (q @ c.T).squeeze(0)
        return sims

    def route(self, embedding: torch.Tensor, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Full classification decision with ID tracking for reward feedback."""
        with torch.no_grad():
            sims = self.forward(embedding, user_id=user_id)

        best_idx = sims.argmax().item()
        confidence = float(sims[best_idx].item())

        # Top-3 alternatives for diagnostics
        topk = sims.topk(min(3, len(self.event_names))).indices.tolist()
        alternatives = [self.event_names[i] for i in topk if i != best_idx]

        routing_id = f"ec_{uuid.uuid4().hex[:8]}"

        with self._lock:
            self._pending_routes[routing_id] = {
                'event_type': self.event_names[best_idx],
                'embedding': embedding.detach().clone(),
                'timestamp': time.time(),
                'user_id': user_id,
            }
            self._total_routes += 1

        return {
            'event_type': self.event_names[best_idx],
            'alternatives': alternatives,
            'confidence': round(confidence, 4),
            'routing_id': routing_id,
        }

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def reward(self, routing_id: str, success: bool, lr: float = 0.01) -> bool:
        """Update centroid based on tool execution outcome.

        Args:
            routing_id: ID returned from route()
            success: Whether the tool execution succeeded
            lr: Learning rate for the centroid update
        Returns:
            True if reward was applied, False if routing_id is unknown/expired
            OR this is an inference replica (read-only — see Phase D).
        """
        if not _is_learner():
            # Inference replica: never mutate centroids. The reward should be
            # forwarded to the learner by the caller (Phase D2). Returning
            # False keeps the existing "not applied" contract intact.
            return False
        with self._lock:
            rec = self._pending_routes.pop(routing_id, None)
        if rec is None:
            return False

        try:
            event_idx = self.event_names.index(rec['event_type'])
        except ValueError:
            return False

        reward_val = 0.5 if success else -0.3
        with torch.no_grad():
            emb = F.normalize(rec['embedding'].flatten().unsqueeze(0), dim=-1).squeeze(0)
            # Update the shared base (small contribution from each user)
            self.centroids.data[event_idx] += lr * reward_val * emb
            # Also update the per-user delta if this was a user-attributed route
            user_id = rec.get('user_id')
            if user_id is not None:
                user_deltas = self.user_deltas.setdefault(user_id, {})
                delta = user_deltas.get(event_idx)
                if delta is None:
                    delta = torch.zeros(self.embed_dim)
                    user_deltas[event_idx] = delta
                delta += (lr * 2.0) * reward_val * emb  # user delta learns 2x faster

        self._total_rewards += 1
        logger.info(
            f"Event reward: {rec['event_type']} {'OK' if success else 'FAIL'} "
            f"(routing_id={routing_id}, reward={reward_val})"
        )
        return True

    def train_supervised(self, embedding: torch.Tensor,
                         correct_event: str, lr: float = 0.05,
                         user_id: Optional[str] = None) -> bool:
        """Supervised centroid update from ground truth (shadow observer or bootstrap).

        Stronger than reward — directly attracts the correct centroid and
        slightly repels the others to increase separation. When `user_id` is
        given, also updates that user's sparse delta with a larger learning
        rate, so personalization kicks in faster than the shared base.
        """
        if not _is_learner():
            return False  # inference replica: read-only (Phase D)
        if correct_event not in self.event_names:
            return False
        correct_idx = self.event_names.index(correct_event)
        with torch.no_grad():
            emb = F.normalize(embedding.flatten().unsqueeze(0), dim=-1).squeeze(0)
            # Attract correct base centroid
            self.centroids.data[correct_idx] += lr * emb
            # Repel other centroids slightly
            self.centroids.data -= (lr * 0.2 / len(self.event_names)) * emb
            # Undo the repel on the correct one (it got the full attract above)
            self.centroids.data[correct_idx] += (lr * 0.2 / len(self.event_names)) * emb
            # Per-user delta gets a larger learning rate for faster personalization
            if user_id is not None:
                user_deltas = self.user_deltas.setdefault(user_id, {})
                delta = user_deltas.get(correct_idx)
                if delta is None:
                    delta = torch.zeros(self.embed_dim)
                    user_deltas[correct_idx] = delta
                delta += (lr * 3.0) * emb  # 3x lr for user delta
        self._total_rewards += 1
        self._train_count_since_save += 1
        return True

    # ------------------------------------------------------------------
    # Bootstrap / Seeding
    # ------------------------------------------------------------------

    def seed(self, embed_fn, lr: float = 0.20) -> int:
        """Initialize each centroid as the L2-normalized mean of its seed phrases.

        For each event_type we average the embeddings of:
          1. The event-name string itself ("bubble.list")
          2. Any curated example phrases from EVENT_SEED_PHRASES

        This is the standard cosine-mean classifier — much more stable than
        the additive Hebbian rule for cold-start, and gives every class a
        clean prototype regardless of how many phrases it has. After seeding,
        the centroids continue to be refined by `train_supervised` (online
        from shadow mode) and `reward` (from tool execution outcomes).

        Args:
            embed_fn: callable(text: str) -> torch.Tensor of shape (1, embed_dim)
                or (embed_dim,). Inject SBERT here.
            lr: kept for API compatibility but unused (mean replaces centroid).
        Returns:
            Number of (event, phrase) pairs averaged
        """
        if embed_fn is None:
            return 0

        count = 0
        for idx, event_name in enumerate(self.event_names):
            phrases = [event_name] + EVENT_SEED_PHRASES.get(event_name, [])
            phrase_embs = []
            for phrase in phrases:
                try:
                    emb = embed_fn(phrase)
                    if not isinstance(emb, torch.Tensor):
                        emb = torch.tensor(emb, dtype=torch.float32)
                    emb = emb.flatten()
                    emb = F.normalize(emb.unsqueeze(0), dim=-1).squeeze(0)
                    phrase_embs.append(emb)
                    count += 1
                except Exception as e:
                    logger.debug(f"Seed failed for {event_name!r} / {phrase!r}: {e}")

            if phrase_embs:
                # L2-normalized mean = the cosine-mean prototype
                stacked = torch.stack(phrase_embs)
                mean_emb = stacked.mean(dim=0)
                mean_emb = F.normalize(mean_emb.unsqueeze(0), dim=-1).squeeze(0)
                with torch.no_grad():
                    self.centroids.data[idx] = mean_emb

        # Reset training counter after bulk seeding so we don't immediately
        # trigger an auto-save from the seed step alone.
        self._train_count_since_save = 0
        logger.info(
            f"EventRoutingHead seeded {count} phrase embeddings averaged "
            f"into {len(self.event_names)} class centroids"
        )
        return count

    # Legacy alias kept for any callers that still pass an agent_loop.
    # Internally tries to use the SeedEncoder+RadialNetwork pipeline as a
    # fallback embedder. Returns 0 if the agent_loop has no seed_encoder.
    def seed_from_event_names(self, agent_loop) -> int:
        if agent_loop is None:
            return 0
        encoder = getattr(agent_loop, 'seed_encoder', None)
        radial = getattr(agent_loop, 'radial_network', None)
        if encoder is None or radial is None:
            return 0

        def _legacy_embed(text: str) -> torch.Tensor:
            seed_np = encoder.encode_from_description(text)
            seed_tensor = torch.tensor(seed_np, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                result = radial.forward(seed_tensor)
            return result['ring_activations'][2]

        return self.seed(_legacy_embed, lr=0.10)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Persist centroids, event_names, and per-user deltas to disk.

        Phase D: only the learner persists. An inference replica writing
        its (unchanged) centroids would race the learner on a shared volume.
        """
        if not _is_learner():
            return
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # Serialize user_deltas as a plain dict-of-dict-of-tensors.
        # torch.save handles nested tensors inside Python dicts cleanly.
        user_deltas_serial = {
            uid: {int(k): v.clone() for k, v in deltas.items()}
            for uid, deltas in self.user_deltas.items()
        }
        torch.save({
            'centroids': self.centroids.data,
            'event_names': self.event_names,
            'total_routes': self._total_routes,
            'total_rewards': self._total_rewards,
            'user_deltas': user_deltas_serial,
            'version': 2,
        }, path)
        self._train_count_since_save = 0
        logger.info(
            f"EventRoutingHead saved to {path} "
            f"({len(self.user_deltas)} personalized users)"
        )

    def load(self, path: str) -> bool:
        """Load centroids (and per-user deltas if present) from disk.

        Returns True on success. If the saved event_names disagree with the
        current ones (e.g. new events were added), the load is rejected to
        avoid silently misaligned centroids.
        """
        try:
            ckpt = torch.load(path, map_location='cpu', weights_only=False)
        except Exception as e:
            logger.warning(f"EventRoutingHead load failed ({path}): {e}")
            return False

        saved_names = ckpt.get('event_names', [])
        if saved_names != self.event_names:
            logger.warning(
                f"EventRoutingHead checkpoint event_names differ "
                f"(saved={len(saved_names)}, current={len(self.event_names)}). "
                f"Refusing to load — re-seed instead."
            )
            return False

        with torch.no_grad():
            self.centroids.data = ckpt['centroids'].clone()
        self._total_routes = int(ckpt.get('total_routes', 0))
        self._total_rewards = int(ckpt.get('total_rewards', 0))
        self._train_count_since_save = 0

        # Load user deltas if this checkpoint has them (v2+)
        saved_deltas = ckpt.get('user_deltas', {}) or {}
        self.user_deltas = {
            uid: {int(k): v.clone() for k, v in deltas.items()}
            for uid, deltas in saved_deltas.items()
        }

        logger.info(
            f"EventRoutingHead loaded from {path} "
            f"({len(self.event_names)} events, {self._total_routes} prior routes, "
            f"{len(self.user_deltas)} personalized users)"
        )
        return True

    def should_autosave(self, every_n: int = 100) -> bool:
        """Whether enough training has accumulated to warrant an autosave."""
        return self._train_count_since_save >= every_n

    def maybe_reload(self, path: str) -> bool:
        """Phase D3: reload centroids from disk IF the file changed since the
        last load. Used by inference replicas to pick up the learner's
        periodic save() on a shared volume — without restarting.

        Returns True if a reload actually happened. mtime-cached so a no-op
        poll is just one os.stat (cheap enough for a ~30s tick). load()
        itself stays the single source of truth for the parse/validation.
        """
        import os
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return False  # file not there yet — nothing to reload
        last = getattr(self, "_ckpt_mtime", None)
        if last is not None and mtime <= last:
            return False  # unchanged since last (re)load
        ok = self.load(path)
        if ok:
            self._ckpt_mtime = mtime
            logger.info(f"EventRoutingHead reloaded from {path} (mtime changed)")
        return ok

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def cleanup_stale(self, max_age: float = 300.0) -> int:
        """Remove pending routes older than max_age seconds."""
        cutoff = time.time() - max_age
        with self._lock:
            stale = [k for k, v in self._pending_routes.items() if v['timestamp'] < cutoff]
            for k in stale:
                del self._pending_routes[k]
        return len(stale)

    def get_stats(self) -> Dict[str, Any]:
        """Stats for the diagnostics endpoint."""
        with self._lock:
            pending = len(self._pending_routes)
        centroid_norms = self.centroids.data.norm(dim=1).tolist()
        # Only include the top-N centroids by norm in the response to keep it small
        ranked = sorted(
            zip(self.event_names, centroid_norms), key=lambda kv: kv[1], reverse=True
        )
        top_events = {name: round(norm, 4) for name, norm in ranked[:20]}
        # Per-user stats
        users_info = {
            uid: {"personalized_events": len(deltas)}
            for uid, deltas in self.user_deltas.items()
        }
        return {
            'total_events': len(self.event_names),
            'total_routes': self._total_routes,
            'total_rewards': self._total_rewards,
            'pending_routes': pending,
            'train_since_save': self._train_count_since_save,
            'top_centroids': top_events,
            'personalized_users': len(self.user_deltas),
            'users': users_info,
        }
