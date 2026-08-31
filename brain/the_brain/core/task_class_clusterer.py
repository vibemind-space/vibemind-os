"""Phase 1 — TaskClassClusterer: Intent -> stabile task_class_id.

Injection-first: embedder/client sind injizierbar (Tests laufen ohne Modell
und ohne Qdrant). Live: core.qdrant_kg.Embedder.get()-Singleton (jetzt ein
HTTP-Client zum embedding-service, siehe docs/superpowers/specs/2026-07-13-
brain-embedder-external-api-design.md) + Qdrant-Collection "brain-task-classes".
Wirft nie — Fallback "" (kein Clustering ist besser als ein Crash im
Executor-finally).

ACHTUNG (2026-07-13, embedder-Migration): "brain-task-classes" ist NICHT im
COLLECTIONS-Dict in qdrant_kg.py registriert — ensure_collections()'s
Alias-Logik und scripts/migrate_embeddings_v3072.py sehen diese Collection
NICHT. _QdrantStoreAdapter._ensure_collection() liest SEMANTIC_DIM live, legt
also auf einer frischen Umgebung korrekt 3072-dim an. Nur falls diese
Collection irgendwo bereits im ALTEN 1024-dim existiert (TASK_CLASS_CLUSTERING
war zum Zeitpunkt der Migration überall aus, per Default) UND der Flag später
aktiviert wird: erst manuell prüfen/migrieren, sonst schlägt der erste upsert()
mit einem Dimension-Mismatch fehl. Gleiche Kategorie Sonderfall wie
EventRoutingHead (siehe project memory project_eventroutinghead_stays_local),
nur hier: schlicht vergessene fünfte Collection statt bewusster Ausnahme.

Grenzen (bewusst akzeptiert)
---------------------------
Das hier ist GREEDY nearest-neighbour-Zuordnung, kein echtes inkrementelles
Clustering. Drei reale Limitierungen:

- DRIFT: der Klassen-Vektor wird nie aktualisiert — der ZUERST gesehene Intent
  definiert die Klasse dauerhaft (kein Zentroid-Update).
- ORDER-DEPENDENCE: dieselbe Intent-Menge kann je nach Ankunftsreihenfolge
  unterschiedliche Klassen ergeben.
- NO-MERGE: zwei Klassen, die sich später als ähnlich erweisen, werden nie
  zusammengeführt.

Für den aktuellen Zweck (Episoden für Pattern-Mining grob gruppieren) ist das
akzeptabel. Bekannter Upgrade-Pfad, falls die Klassen zu grob/zerfasert werden:
Moving-Average-Zentroid pro Klasse + periodisches Re-Clustering.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "brain-task-classes"
# Cosine-Schwelle auf den Embedder.get()-Vektoren (embedding-service seit der
# 2026-07-13-Migration, davor Qwen lokal). 0.85 = "klar dieselbe Task-Art";
# darunter fangen unterschiedliche Arten an zu verschmelzen. Für Ops ohne
# Code-Änderung nachjustierbar (Stil wie TASK_CLASS_CLUSTERING).
DEFAULT_THRESHOLD = float(os.environ.get("TASK_CLASS_THRESHOLD", "0.85"))


class _QdrantStoreAdapter:
    """Private adapter: exposes the injected `client` contract
    (search(vector, limit)->[{"id","score"}], upsert(point_id, vector))
    on top of the real qdrant_client.QdrantClient. Lazily creates the
    collection on first use. Any Qdrant-side error propagates so the
    caller's try/except can fall back to "" — no swallowing here.
    """

    def __init__(self, collection: str) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm
        from core.qdrant_kg import QDRANT_URL, SEMANTIC_DIM, _point_id

        self._qm = qm
        self._collection = collection
        self._client = QdrantClient(url=QDRANT_URL, timeout=30)
        self._dim = SEMANTIC_DIM
        self._point_id = _point_id
        self._ensured = False

    def _ensure_collection(self) -> None:
        if self._ensured:
            return
        qm = self._qm
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qm.VectorParams(
                    size=self._dim, distance=qm.Distance.COSINE,
                ),
            )
        self._ensured = True

    def search(self, vector: List[float], limit: int = 1) -> List[Dict[str, Any]]:
        """Qdrant point ids must be int/UUID, so the external `tc_<hex>` id is
        stored in payload["task_class_id"] and surfaced here — the injected
        contract only ever deals with the external id, never the raw UUID."""
        self._ensure_collection()
        hits = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=limit,
            with_payload=True,
        ).points
        out = []
        for h in hits:
            ext_id = (h.payload or {}).get("task_class_id") or str(h.id)
            out.append({"id": ext_id, "score": float(h.score)})
        return out

    def upsert(self, point_id: str, vector: List[float]) -> None:
        self._ensure_collection()
        qm = self._qm
        self._client.upsert(
            collection_name=self._collection,
            points=[qm.PointStruct(
                id=self._point_id(point_id),
                vector=vector,
                payload={"task_class_id": point_id},
            )],
            wait=True,
        )


class TaskClassClusterer:
    def __init__(self, embedder: Any = None, client: Any = None,
                 collection: str = DEFAULT_COLLECTION,
                 threshold: float = DEFAULT_THRESHOLD) -> None:
        self._embedder = embedder
        self._client = client
        self._collection = collection
        self._threshold = threshold

    def _get_embedder(self):
        if self._embedder is None:
            from core.qdrant_kg import Embedder  # lazy — nie beim Import laden
            self._embedder = Embedder.get()
        return self._embedder

    def _get_client(self):
        if self._client is None:
            self._client = _QdrantStoreAdapter(self._collection)
        return self._client

    def cluster_id(self, user_text: str) -> str:
        """Stabile Klassen-ID für semantisch ähnliche Intents; "" bei Fehler."""
        text = (user_text or "").strip()
        if not text:
            return ""
        try:
            vec = list(self._get_embedder().encode(text))
            hits = self._get_client().search(vector=vec, limit=1)
            if hits and float(hits[0].get("score", 0.0)) >= self._threshold:
                return str(hits[0]["id"])
            new_id = f"tc_{uuid.uuid4().hex[:12]}"
            self._get_client().upsert(point_id=new_id, vector=vec)
            return new_id
        except Exception as e:  # noqa: BLE001 — Clustering darf nie blocken
            logger.debug(f"[task-class] cluster_id failed: {e}")
            return ""
