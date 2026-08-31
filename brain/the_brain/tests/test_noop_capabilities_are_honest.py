"""Phase 1 — Attrappen sind ehrlich: eine Cap, die nichts tut, darf keinen
Erfolg melden.

bubble_noop_op gab "ok (no-op ...)" zurück, damit Pläne nicht scheitern.
Für bubble_promote / bubble_delete_all / bubble_generate_embeddings ist das
eine LÜGE: der Nutzer glaubt, es sei passiert; das Tagebuch lernt "diese
Capability funktioniert". bubble_exit ist der einzige legitime No-op
(zustandslose Navigation).
"""
import yaml
from pathlib import Path

CAPS = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "data" / "capabilities.yaml")
    .read_text(encoding="utf-8")
)
BY_NAME = {c["capability"]: c for c in CAPS}

LYING_STUBS = ("bubble_delete_all", "bubble_generate_embeddings")


class TestLyingStubsAreDisabled:
    def test_they_have_no_execution_target(self):
        """Ohne Target kann der Planner sie nicht dispatchen und der
        GapSentinel meldet die Lücke — statt Erfolg vorzutäuschen."""
        for name in LYING_STUBS:
            cap = BY_NAME[name]
            assert not cap.get("execution_target"), (
                f"{name} zeigt noch auf {cap.get('execution_target')} — "
                f"es täuscht weiterhin Erfolg vor"
            )

    def test_they_say_why_in_the_description(self):
        for name in LYING_STUBS:
            desc = (BY_NAME[name].get("description") or "").lower()
            assert "not implemented" in desc or "nicht implementiert" in desc, (
                f"{name}: die Beschreibung muss sagen, dass es nicht geht"
            )

    def test_bubble_exit_keeps_its_noop(self):
        """bubble_exit ist der EINZIGE legitime No-op: zustandslose
        Navigation, es gibt nichts zu schreiben."""
        assert BY_NAME["bubble_exit"]["execution_target"] == "supabase:bubble.noop"


class TestNoopOpNoLongerServesWriters:
    def test_docstring_names_only_bubble_exit(self):
        src = (Path(__file__).resolve().parents[1] / "core" /
               "supabase_ideas_ops.py").read_text(encoding="utf-8")
        i = src.index("async def bubble_noop_op")
        doc = src[i:i + 500]
        for name in ("bubble_delete_all", "bubble_generate_embeddings"):
            assert name not in doc, (
                f"bubble_noop_op bedient laut Docstring noch {name}"
            )
