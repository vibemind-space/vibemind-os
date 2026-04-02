"""
Unit Tests für die Feature-basierten Slicing-Funktionen in slicer.py.

Diese Tests sind unabhängig von anderen Komponenten ausführbar:
    pytest tests/engine/test_slicer_features.py -v
"""
import pytest
from dataclasses import dataclass

# Test imports
from src.engine.slicer import (
    Domain,
    FrontendFeature,
    BackendFeature,
    FeatureGroupConfig,
    DomainChunk,
    FeatureChunk,
    TaskSlice,
    SliceManifest,
    Slicer,
)


class TestEnums:
    """Tests für die Enum-Definitionen."""

    
    def test_domain_enum_values(self):
        """Domain enum hat alle erwarteten Werte."""
        assert Domain.FRONTEND.value == "frontend"
        assert Domain.BACKEND.value == "backend"
        assert Domain.DATABASE.value == "database"
        assert Domain.API.value == "api"
        assert Domain.AUTHENTICATION.value == "auth"
    
    def test_frontend_feature_enum_values(self):
        """FrontendFeature enum hat alle ARCH-38 Kategorien."""
        expected = {"components", "pages", "hooks", "services", "state", "styles", "utils", "layout"}
        actual = {f.value for f in FrontendFeature}
        assert actual == expected
    
    def test_backend_feature_enum_values(self):
        """BackendFeature enum hat alle ARCH-39 Kategorien."""
        expected = {"routes", "models", "services", "database", "auth", "middleware", "utils", "config"}
        actual = {f.value for f in BackendFeature}
        assert actual == expected


class TestFeatureGroupConfig:
    """Tests für die FeatureGroupConfig Dataclass."""

    
    def test_default_values(self):
        """Standardwerte sind gesetzt."""
        config = FeatureGroupConfig()
        
        # ARCH-40: Größere Batch-Sizes
        assert config.frontend_batch_size == 50
        assert config.backend_batch_size == 30
        assert config.db_batch_size == 20
        
        # ARCH-41: Multi-Worker
        assert config.frontend_workers == 3
        assert config.backend_workers == 2
        assert config.db_workers == 1
    
    def test_custom_values(self):
        """Custom Werte können gesetzt werden."""
        config = FeatureGroupConfig(
            frontend_batch_size=100,
            backend_workers=5,
        )
        assert config.frontend_batch_size == 100
        assert config.backend_workers == 5
    
    def test_feature_sizes_dict(self):
        """Feature-spezifische Batch-Sizes werden korrekt geladen."""
        config = FeatureGroupConfig()
        
        assert FrontendFeature.COMPONENTS in config.frontend_feature_sizes
        assert config.frontend_feature_sizes[FrontendFeature.COMPONENTS] == 20
        
        assert BackendFeature.ROUTES in config.backend_feature_sizes
        assert config.backend_feature_sizes[BackendFeature.ROUTES] == 15


class TestTaskSlice:
    """Tests für die TaskSlice Dataclass."""

    
    def test_basic_creation(self):
        """TaskSlice kann erstellt werden."""
        ts = TaskSlice(
            slice_id="fe-components-001",
            depth=0,
            agent_type="frontend",
            requirements=["REQ-001", "REQ-002"],
            feature="components",
        )
        
        assert ts.slice_id == "fe-components-001"
        assert ts.agent_type == "frontend"
        assert ts.feature == "components"
        assert len(ts.requirements) == 2
    
    def test_to_dict(self):
        """to_dict() gibt korrektes Dictionary zurück."""
        ts = TaskSlice(
            slice_id="test-001",
            depth=1,
            agent_type="backend",
        )
        d = ts.to_dict()
        
        assert d["slice_id"] == "test-001"
        assert d["depth"] == 1
        assert d["agent_type"] == "backend"
        assert "requirements" in d


class TestSlicerDomainDetection:
    """Tests für die Domain-Erkennung im Slicer."""

    
    @pytest.fixture
    def slicer(self):
        return Slicer()
    
    def test_detect_frontend_from_ui_keywords(self, slicer):
        """Frontend wird durch UI-Keywords erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-001", name="Create a button component for the dashboard")
        domain = slicer._detect_domain(node)
        assert domain == Domain.FRONTEND
    
    def test_detect_backend_from_api_keywords(self, slicer):
        """Backend wird durch API-Keywords erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-002", name="Create REST API endpoint for user service")
        domain = slicer._detect_domain(node)
        assert domain == Domain.BACKEND
    
    def test_detect_database_from_sql_keywords(self, slicer):
        """Database wird durch SQL-Keywords erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-003", name="Create PostgreSQL table schema for users")
        domain = slicer._detect_domain(node)
        assert domain == Domain.DATABASE


class TestSlicerFeatureDetection:
    """Tests für die Feature-Erkennung im Slicer."""

    
    @pytest.fixture
    def slicer(self):
        return Slicer()
    
    def test_detect_frontend_components(self, slicer):
        """Frontend components werden erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-001", name="Create Button input component with modal dialog")
        feature = slicer._detect_frontend_feature(node)
        assert feature == FrontendFeature.COMPONENTS
    
    def test_detect_frontend_hooks(self, slicer):
        """Frontend hooks werden erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-002", name="Create custom useAuth hook with useState")
        feature = slicer._detect_frontend_feature(node)
        assert feature == FrontendFeature.HOOKS
    
    def test_detect_frontend_pages(self, slicer):
        """Frontend pages werden erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-003", name="Create dashboard page with settings view")
        feature = slicer._detect_frontend_feature(node)
        assert feature == FrontendFeature.PAGES
    
    def test_detect_backend_routes(self, slicer):
        """Backend routes werden erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-004", name="Create REST endpoint for GET users")
        feature = slicer._detect_backend_feature(node)
        assert feature == BackendFeature.ROUTES
    
    def test_detect_backend_models(self, slicer):
        """Backend models werden erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-005", name="Create Pydantic model schema for User entity")
        feature = slicer._detect_backend_feature(node)
        assert feature == BackendFeature.MODELS
    
    def test_detect_backend_auth(self, slicer):
        """Backend auth wird erkannt."""
        @dataclass
        class MockNode:
            id: str
            name: str
        
        node = MockNode(id="REQ-006", name="Implement JWT token authentication with login")
        feature = slicer._detect_backend_feature(node)
        assert feature == BackendFeature.AUTH


class TestSlicerFeaturePriority:
    """Tests für die Feature-Prioritäten."""

    
    @pytest.fixture
    def slicer(self):
        return Slicer()
    
    def test_frontend_priorities(self, slicer):
        """Frontend-Features haben korrekte Prioritäten."""
        # Layout sollte höchste Priorität haben (niedrigster Wert)
        layout_prio = slicer._get_feature_priority(FrontendFeature.LAYOUT)
        components_prio = slicer._get_feature_priority(FrontendFeature.COMPONENTS)
        utils_prio = slicer._get_feature_priority(FrontendFeature.UTILS)
        
        assert layout_prio < components_prio  # Layout vor Components
        assert components_prio < utils_prio    # Components vor Utils
    
    def test_backend_priorities(self, slicer):
        """Backend-Features haben korrekte Prioritäten."""
        # Config/Models sollten höhere Priorität haben (niedrigerer Wert)
        config_prio = slicer._get_feature_priority(BackendFeature.CONFIG)
        models_prio = slicer._get_feature_priority(BackendFeature.MODELS)
        routes_prio = slicer._get_feature_priority(BackendFeature.ROUTES)
        
        assert config_prio < models_prio  # Config vor Models
        assert models_prio < routes_prio   # Models vor Routes


class TestSlicerDomainBatchSize:
    """Tests für Domain-spezifische Batch-Sizes."""

    
    @pytest.fixture
    def slicer(self):
        return Slicer(feature_config=FeatureGroupConfig())
    
    def test_database_batch_size(self, slicer):
        """Database hat korrekte Batch-Size."""
        batch_size = slicer._get_domain_batch_size(Domain.DATABASE)
        assert batch_size == slicer.feature_config.db_batch_size
    
    def test_testing_batch_size(self, slicer):
        """Testing hat korrekte Batch-Size."""
        batch_size = slicer._get_domain_batch_size(Domain.TESTING)
        assert batch_size == slicer.feature_config.testing_batch_size


class TestSliceManifest:
    """Tests für SliceManifest."""

    
    def test_to_dict(self):
        """to_dict() gibt vollständiges Dictionary zurück."""
        manifest = SliceManifest(
            job_id=123,
            total_requirements=50,
            total_slices=10,
            max_depth=2,
            slices=[
                TaskSlice(slice_id="s1", depth=0, agent_type="frontend"),
                TaskSlice(slice_id="s2", depth=1, agent_type="backend"),
            ],
        )
        
        d = manifest.to_dict()
        assert d["job_id"] == 123
        assert d["total_requirements"] == 50
        assert d["total_slices"] == 10
        assert len(d["slices"]) == 2
    
    def test_to_json(self):
        """to_json() gibt valides JSON zurück."""
        import json
        
        manifest = SliceManifest(
            job_id=1,
            total_requirements=5,
            total_slices=2,
            max_depth=1,
        )
        
        json_str = manifest.to_json()
        parsed = json.loads(json_str)
        assert parsed["job_id"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
