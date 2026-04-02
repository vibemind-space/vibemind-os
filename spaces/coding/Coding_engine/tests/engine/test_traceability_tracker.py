import pytest
from pathlib import Path
from src.engine.spec_parser import SpecParser
from src.engine.traceability_tracker import TraceabilityTracker


class TestTraceabilityTracker:
    def test_register_from_spec(self):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        entries = tracker.get_all_entries()
        assert len(entries) > 0
        assert all(e.status == "SKELETON" for e in entries)

    def test_update_status(self):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        entries = tracker.get_all_entries()
        if entries:
            tracker.update_status(entries[0].requirement_id, entries[0].service, "IMPLEMENTED")
            updated = tracker.get_entries(entries[0].service)
            assert any(e.status == "IMPLEMENTED" for e in updated)

    def test_generate_report(self):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        report = tracker.generate_report()
        assert "total_requirements" in report
        assert report["total_requirements"] > 0

    def test_save_json(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        output = tmp_path / "trace.json"
        tracker.save_json(output)
        assert output.exists()
        import json
        data = json.loads(output.read_text())
        assert "report" in data
        assert "entries" in data

    def test_save_markdown(self, tmp_path):
        spec = SpecParser(Path("Data/all_services/whatsapp-messaging-service_20260211_025459")).parse()
        tracker = TraceabilityTracker()
        tracker.register_from_spec(spec)
        output = tmp_path / "TRACE.md"
        tracker.save_markdown(output)
        assert output.exists()
        content = output.read_text()
        assert "Traceability Matrix" in content
