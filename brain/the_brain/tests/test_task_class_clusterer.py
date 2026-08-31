"""Phase 1 — Task-Klassen-Clustering, injection-first (kein Modell-Load)."""
from core.task_class_clusterer import TaskClassClusterer


class _StubEmbedder:
    """Deterministische 3D-'Embeddings': bekannte Texte -> feste Vektoren."""
    VECS = {
        "review my docker image": [1.0, 0.0, 0.0],
        "check das docker image": [0.98, 0.199, 0.0],   # cos ~0.98 zum ersten
        "erstelle eine bubble":   [0.0, 1.0, 0.0],       # orthogonal
    }
    def encode(self, text):
        return self.VECS[text]


class _StubStore:
    """In-Memory-Ersatz für die Qdrant-Collection."""
    def __init__(self):
        self.points = []  # [(id, vector)]
    def search(self, vector, limit=1):
        import math
        def cos(a, b):
            num = sum(x * y for x, y in zip(a, b))
            den = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b))
            return num / den if den else 0.0
        scored = sorted(((cos(vector, v), pid) for pid, v in self.points), reverse=True)
        return [{"id": pid, "score": s} for s, pid in scored[:limit]]
    def upsert(self, point_id, vector):
        self.points.append((point_id, vector))


def _clusterer():
    return TaskClassClusterer(embedder=_StubEmbedder(), client=_StubStore())


def test_similar_intents_share_a_class():
    c = _clusterer()
    a = c.cluster_id("review my docker image")
    b = c.cluster_id("check das docker image")
    assert a.startswith("tc_") and a == b


def test_dissimilar_intent_gets_new_class():
    c = _clusterer()
    a = c.cluster_id("review my docker image")
    b = c.cluster_id("erstelle eine bubble")
    assert a != b and b.startswith("tc_")


def test_empty_text_returns_empty():
    assert _clusterer().cluster_id("   ") == ""


def test_never_raises_on_broken_embedder():
    class _Broken:
        def encode(self, text):
            raise RuntimeError("model down")
    c = TaskClassClusterer(embedder=_Broken(), client=_StubStore())
    assert c.cluster_id("whatever") == ""


class _FixedScoreStore(_StubStore):
    """Store, dessen search() einen exakt kontrollierten Score liefert —
    so laesst sich die >=-Grenze pinnen, ohne mit Float-Cosinus zu kaempfen."""
    def __init__(self, score):
        super().__init__()
        self._score = score
    def search(self, vector, limit=1):
        if not self.points:
            return []
        return [{"id": self.points[0][0], "score": self._score}]


def test_score_exactly_at_threshold_matches_existing_class():
    store = _FixedScoreStore(0.85)  # == threshold -> >= -> MATCH
    c = TaskClassClusterer(embedder=_StubEmbedder(), client=store, threshold=0.85)
    a = c.cluster_id("review my docker image")
    b = c.cluster_id("erstelle eine bubble")
    assert a.startswith("tc_") and b == a
    assert len(store.points) == 1  # keine neue Klasse angelegt


def test_score_just_below_threshold_creates_new_class():
    store = _FixedScoreStore(0.849)  # < threshold -> NEUE Klasse
    c = TaskClassClusterer(embedder=_StubEmbedder(), client=store, threshold=0.85)
    a = c.cluster_id("review my docker image")
    b = c.cluster_id("erstelle eine bubble")
    assert b.startswith("tc_") and b != a
    assert len(store.points) == 2


def test_adapter_threads_task_class_into_metadata(tmp_path):
    from core.dual_graph import DualGraph
    from core.multihop_kotlin_adapter import record_plan

    class _Plan:
        plan_id, intent, trace_id = "plan_tc", "tc test", "tr_tc"

    dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=10_000)
    executed = {"s1": {"ok": True, "contract_pass": True, "reward": 1.0,
                       "capability": "x", "target": "direct:a:b"}}
    record_plan(dg, _Plan(), executed, task_class_id="tc_abc123")
    ev = dg.kotlingraph.events[-1]
    assert ev.metadata["task_class_id"] == "tc_abc123"


def test_adapter_omits_task_class_when_empty(tmp_path):
    from core.dual_graph import DualGraph
    from core.multihop_kotlin_adapter import record_plan

    class _Plan:
        plan_id, intent, trace_id = "plan_no_tc", "no tc", "tr_no_tc"

    dg = DualGraph(save_dir=str(tmp_path), auto_mine_interval=10_000)
    executed = {"s1": {"ok": True, "contract_pass": True, "reward": 1.0,
                       "capability": "x", "target": "direct:a:b"}}
    record_plan(dg, _Plan(), executed)
    ev = dg.kotlingraph.events[-1]
    assert "task_class_id" not in ev.metadata
