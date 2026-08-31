"""
Tests for Distributed Checkpoint Manager

Coverage:
- SemanticVersion parsing, comparison, increment
- CheckpointDiff structure and serialization
- S3StorageAdapter (with mocking)
- HTTPStorageAdapter (with mocking)
- DistributedCheckpointManager operations
"""

import pytest
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.distributed_checkpoint import (
    SemanticVersion,
    StorageBackend,
    CheckpointDiff,
    MergedCheckpoint,
    StorageAdapter,
    S3StorageAdapter,
    HTTPStorageAdapter,
    DistributedCheckpointManager
)
from core.oscillator_checkpoint import OscillatorCheckpoint


# =============================================================================
# SEMANTIC VERSION TESTS
# =============================================================================

class TestSemanticVersion:
    """Test suite for SemanticVersion."""

    def test_parse_basic(self):
        """Test parsing basic version string."""
        v = SemanticVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert v.prerelease is None

    def test_parse_with_prerelease(self):
        """Test parsing version with prerelease."""
        v = SemanticVersion.parse("2.0.0-beta.1")
        assert v.major == 2
        assert v.minor == 0
        assert v.patch == 0
        assert v.prerelease == "beta.1"

    def test_parse_partial(self):
        """Test parsing partial version strings."""
        v1 = SemanticVersion.parse("1")
        assert v1.major == 1
        assert v1.minor == 0
        assert v1.patch == 0

        v2 = SemanticVersion.parse("1.5")
        assert v2.major == 1
        assert v2.minor == 5
        assert v2.patch == 0

    def test_str_representation(self):
        """Test string representation."""
        v = SemanticVersion(1, 2, 3)
        assert str(v) == "1.2.3"

        v_pre = SemanticVersion(2, 0, 0, "alpha")
        assert str(v_pre) == "2.0.0-alpha"

    def test_comparison_basic(self):
        """Test version comparison."""
        v1 = SemanticVersion.parse("1.0.0")
        v2 = SemanticVersion.parse("2.0.0")
        v3 = SemanticVersion.parse("1.1.0")
        v4 = SemanticVersion.parse("1.0.1")

        assert v1 < v2
        assert v1 < v3
        assert v1 < v4
        assert v3 < v2
        assert v4 < v3

    def test_comparison_prerelease(self):
        """Prerelease versions should be less than release versions."""
        v_release = SemanticVersion.parse("1.0.0")
        v_beta = SemanticVersion.parse("1.0.0-beta")
        v_alpha = SemanticVersion.parse("1.0.0-alpha")

        assert v_alpha < v_release
        assert v_beta < v_release
        assert v_alpha < v_beta  # alphabetically

    def test_increment_major(self):
        """Test major version increment."""
        v = SemanticVersion(1, 2, 3)
        v_new = v.increment_major()
        assert v_new.major == 2
        assert v_new.minor == 0
        assert v_new.patch == 0

    def test_increment_minor(self):
        """Test minor version increment."""
        v = SemanticVersion(1, 2, 3)
        v_new = v.increment_minor()
        assert v_new.major == 1
        assert v_new.minor == 3
        assert v_new.patch == 0

    def test_increment_patch(self):
        """Test patch version increment."""
        v = SemanticVersion(1, 2, 3)
        v_new = v.increment_patch()
        assert v_new.major == 1
        assert v_new.minor == 2
        assert v_new.patch == 4


# =============================================================================
# CHECKPOINT DIFF TESTS
# =============================================================================

class TestCheckpointDiff:
    """Test suite for CheckpointDiff."""

    def test_creation(self):
        """Test creating a CheckpointDiff."""
        diff = CheckpointDiff(
            source_name="checkpoint_a",
            target_name="checkpoint_b",
            source_version="1.0.0",
            target_version="1.1.0"
        )
        assert diff.source_name == "checkpoint_a"
        assert diff.target_name == "checkpoint_b"
        assert diff.total_changes == 0

    def test_with_changes(self):
        """Test CheckpointDiff with actual changes."""
        diff = CheckpointDiff(
            source_name="a",
            target_name="b",
            source_version="1.0.0",
            target_version="1.1.0",
            oscillator_diff={'A': {'amplitude': 0.15}},
            tokens_added={'new_token': 'ACTION'},
            tokens_removed=['old_token'],
            tokens_changed={'changed_token': ('ACTION', 'REFLECT')}
        )
        diff.total_changes = 4
        diff.change_magnitude = 0.35

        assert len(diff.tokens_added) == 1
        assert len(diff.tokens_removed) == 1
        assert len(diff.tokens_changed) == 1

    def test_to_dict(self):
        """Test serialization to dict."""
        diff = CheckpointDiff(
            source_name="a",
            target_name="b",
            source_version="1.0.0",
            target_version="1.1.0"
        )
        diff.total_changes = 5
        diff.change_magnitude = 0.5

        d = diff.to_dict()
        assert d['source']['name'] == "a"
        assert d['target']['name'] == "b"
        assert d['total_changes'] == 5
        assert d['change_magnitude'] == 0.5


# =============================================================================
# S3 STORAGE ADAPTER TESTS
# =============================================================================

class TestS3StorageAdapter:
    """Test suite for S3StorageAdapter."""

    def test_init_without_boto3(self):
        """Test initialization when boto3 is not available."""
        with patch.dict('sys.modules', {'boto3': None}):
            # Force reimport by removing cached module
            if 'core.distributed_checkpoint' in sys.modules:
                del sys.modules['core.distributed_checkpoint']

            # Create adapter - should gracefully handle missing boto3
            adapter = S3StorageAdapter(bucket="test-bucket")
            assert adapter._s3_available == False

    @patch('boto3.client')
    def test_init_with_boto3(self, mock_boto_client):
        """Test initialization with boto3 available."""
        adapter = S3StorageAdapter(
            bucket="test-bucket",
            prefix="checkpoints",
            endpoint_url="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin"
        )

        if adapter._s3_available:
            assert adapter.bucket == "test-bucket"
            assert adapter.prefix == "checkpoints"
            mock_boto_client.assert_called()

    def test_full_key_with_prefix(self):
        """Test full key generation with prefix."""
        adapter = S3StorageAdapter(bucket="test", prefix="checkpoints")
        if not adapter._s3_available:
            adapter._s3_available = True  # Force for testing

        # Just test the method
        key = adapter._full_key("model_v1.json")
        assert key == "checkpoints/model_v1.json"

    def test_full_key_without_prefix(self):
        """Test full key generation without prefix."""
        adapter = S3StorageAdapter(bucket="test", prefix="")
        if not adapter._s3_available:
            adapter._s3_available = True

        key = adapter._full_key("model_v1.json")
        assert key == "model_v1.json"

    @patch('boto3.client')
    def test_upload_success(self, mock_boto_client):
        """Test successful upload."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        adapter = S3StorageAdapter(bucket="test-bucket")
        if adapter._s3_available:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test content")
                temp_path = f.name

            try:
                result = adapter.upload(temp_path, "test.json")
                assert result == True
                mock_client.upload_file.assert_called_once()
            finally:
                os.unlink(temp_path)

    @patch('boto3.client')
    def test_download_success(self, mock_boto_client):
        """Test successful download."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        adapter = S3StorageAdapter(bucket="test-bucket")
        if adapter._s3_available:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = os.path.join(tmpdir, "downloaded.json")
                result = adapter.download("test.json", local_path)
                assert result == True
                mock_client.download_file.assert_called_once()

    @patch('boto3.client')
    def test_exists_true(self, mock_boto_client):
        """Test exists returns True when object exists."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        adapter = S3StorageAdapter(bucket="test-bucket")
        if adapter._s3_available:
            result = adapter.exists("test.json")
            assert result == True
            mock_client.head_object.assert_called_once()

    @patch('boto3.client')
    def test_exists_false(self, mock_boto_client):
        """Test exists returns False when object doesn't exist."""
        mock_client = MagicMock()
        mock_client.head_object.side_effect = Exception("Not found")
        mock_boto_client.return_value = mock_client

        adapter = S3StorageAdapter(bucket="test-bucket")
        if adapter._s3_available:
            result = adapter.exists("nonexistent.json")
            assert result == False

    def test_operations_when_unavailable(self):
        """Test all operations return False/empty when S3 unavailable."""
        adapter = S3StorageAdapter(bucket="test")
        adapter._s3_available = False
        adapter.client = None

        assert adapter.upload("local", "remote") == False
        assert adapter.download("remote", "local") == False
        assert adapter.list() == []
        assert adapter.delete("path") == False
        assert adapter.exists("path") == False


# =============================================================================
# HTTP STORAGE ADAPTER TESTS
# =============================================================================

class TestHTTPStorageAdapter:
    """Test suite for HTTPStorageAdapter."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        adapter = HTTPStorageAdapter(
            base_url="https://api.example.com/storage",
            api_key="secret-key"
        )
        assert adapter.base_url == "https://api.example.com/storage"
        assert 'Authorization' in adapter.headers
        assert adapter.headers['Authorization'] == 'Bearer secret-key'

    def test_init_with_custom_headers(self):
        """Test initialization with custom headers."""
        adapter = HTTPStorageAdapter(
            base_url="https://api.example.com",
            headers={'X-Custom': 'value'}
        )
        assert adapter.headers['X-Custom'] == 'value'

    @patch('requests.put')
    def test_upload_success(self, mock_put):
        """Test successful HTTP upload."""
        mock_put.return_value = MagicMock(status_code=201)

        adapter = HTTPStorageAdapter(base_url="https://api.example.com")
        if adapter._http_available:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test content")
                temp_path = f.name

            try:
                result = adapter.upload(temp_path, "test.json")
                assert result == True
            finally:
                os.unlink(temp_path)

    @patch('requests.get')
    def test_download_success(self, mock_get):
        """Test successful HTTP download."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"test": "data"}'
        mock_get.return_value = mock_response

        adapter = HTTPStorageAdapter(base_url="https://api.example.com")
        if adapter._http_available:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = os.path.join(tmpdir, "downloaded.json")
                result = adapter.download("test.json", local_path)
                assert result == True
                with open(local_path, 'rb') as f:
                    assert f.read() == b'{"test": "data"}'

    @patch('requests.get')
    def test_list_files(self, mock_get):
        """Test listing files."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'files': ['a.json', 'b.json']}
        mock_get.return_value = mock_response

        adapter = HTTPStorageAdapter(base_url="https://api.example.com")
        if adapter._http_available:
            files = adapter.list("checkpoints/")
            assert files == ['a.json', 'b.json']

    @patch('requests.delete')
    def test_delete_success(self, mock_delete):
        """Test successful delete."""
        mock_delete.return_value = MagicMock(status_code=204)

        adapter = HTTPStorageAdapter(base_url="https://api.example.com")
        if adapter._http_available:
            result = adapter.delete("test.json")
            assert result == True

    @patch('requests.head')
    def test_exists_true(self, mock_head):
        """Test exists returns True."""
        mock_head.return_value = MagicMock(status_code=200)

        adapter = HTTPStorageAdapter(base_url="https://api.example.com")
        if adapter._http_available:
            result = adapter.exists("test.json")
            assert result == True

    def test_operations_when_unavailable(self):
        """Test operations when requests not available."""
        adapter = HTTPStorageAdapter(base_url="https://api.example.com")
        adapter._http_available = False

        assert adapter.upload("local", "remote") == False
        assert adapter.download("remote", "local") == False
        assert adapter.list() == []
        assert adapter.delete("path") == False
        assert adapter.exists("path") == False


# =============================================================================
# DISTRIBUTED CHECKPOINT MANAGER TESTS
# =============================================================================

class TestDistributedCheckpointManager:
    """Test suite for DistributedCheckpointManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def manager(self, temp_dir):
        """Create a manager instance for testing."""
        return DistributedCheckpointManager(
            local_dir=temp_dir,
            max_versions=5,
            sync_on_save=False
        )

    def test_initialization(self, manager, temp_dir):
        """Test manager initialization."""
        assert manager.local_dir == Path(temp_dir)
        assert manager.max_versions == 5
        assert manager.sync_on_save == False
        assert len(manager.remote_adapters) == 0

    def test_add_remove_remote(self, manager):
        """Test adding and removing remote adapters."""
        mock_adapter = Mock(spec=StorageAdapter)

        manager.add_remote("s3", mock_adapter)
        assert "s3" in manager.remote_adapters

        result = manager.remove_remote("s3")
        assert result == True
        assert "s3" not in manager.remote_adapters

        # Remove non-existent
        result = manager.remove_remote("nonexistent")
        assert result == False

    def test_list_versions_empty(self, manager):
        """Test listing versions when none exist."""
        versions = manager.list_versions("nonexistent")
        assert versions == []

    def test_get_latest_version_empty(self, manager):
        """Test getting latest version when none exist."""
        version = manager.get_latest_version("nonexistent")
        assert version is None

    def test_version_index_persistence(self, temp_dir):
        """Test version index is saved and loaded."""
        # Create manager and add version
        manager1 = DistributedCheckpointManager(
            local_dir=temp_dir,
            sync_on_save=False
        )
        manager1.version_index["test"] = [SemanticVersion(1, 0, 0)]
        manager1._save_version_index()
        manager1.shutdown()

        # Create new manager and check index loaded
        manager2 = DistributedCheckpointManager(
            local_dir=temp_dir,
            sync_on_save=False
        )
        assert "test" in manager2.version_index
        assert len(manager2.version_index["test"]) == 1
        manager2.shutdown()

    def test_get_statistics(self, manager):
        """Test getting manager statistics."""
        stats = manager.get_statistics()
        assert 'local_dir' in stats
        assert 'remote_adapters' in stats
        assert 'max_versions' in stats
        assert 'checkpoint_count' in stats
        assert stats['checkpoint_count'] == 0

    def test_cleanup_old_versions(self, manager):
        """Test old version cleanup."""
        # Add more versions than max
        manager.version_index["test"] = [
            SemanticVersion(1, 0, i) for i in range(10)
        ]
        manager._cleanup_old_versions("test")

        assert len(manager.version_index["test"]) == manager.max_versions

    def test_get_checkpoint_path(self, manager):
        """Test checkpoint path generation."""
        version = SemanticVersion(1, 2, 3)
        path = manager._get_checkpoint_path("model", version)
        assert path.name == "model_v1.2.3.json"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestDistributedCheckpointIntegration:
    """Integration tests requiring more setup."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        shutil.rmtree(tmpdir)

    def test_diff_checkpoints_basic(self, temp_dir):
        """Test diffing two checkpoints."""
        manager = DistributedCheckpointManager(
            local_dir=temp_dir,
            sync_on_save=False
        )

        # Create two mock checkpoint files
        cp1_data = {
            'name': 'test_v1.0.0',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'oscillator_state': {
                'A': {'amplitude': 0.5, 'phase': 0.0},
                'B': {'amplitude': 0.3, 'phase': 0.1},
                'C': {'amplitude': 0.2, 'phase': 0.2}
            },
            'token_mappings': {'token1': 'ACTION', 'token2': 'REFLECT'},
            'synchrony_vector': [],
            'dominant_channel': 'advance',
            'frequency_history': [],
            'statistics': {}
        }

        cp2_data = {
            'name': 'test_v1.1.0',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'oscillator_state': {
                'A': {'amplitude': 0.6, 'phase': 0.0},  # Changed
                'B': {'amplitude': 0.3, 'phase': 0.1},
                'C': {'amplitude': 0.1, 'phase': 0.3}   # Changed
            },
            'token_mappings': {
                'token1': 'ACTION',
                'token2': 'ACTION',  # Changed
                'token3': 'REFLECT'  # Added
            },
            'synchrony_vector': [],
            'dominant_channel': 'advance',
            'frequency_history': [],
            'statistics': {}
        }

        # Write checkpoint files
        with open(os.path.join(temp_dir, 'test_v1.0.0.json'), 'w') as f:
            json.dump(cp1_data, f)
        with open(os.path.join(temp_dir, 'test_v1.1.0.json'), 'w') as f:
            json.dump(cp2_data, f)

        # Update version index
        manager.version_index['test'] = [
            SemanticVersion(1, 0, 0),
            SemanticVersion(1, 1, 0)
        ]

        # Compute diff
        diff = manager.diff_checkpoints('test', 'test', '1.0.0', '1.1.0')

        assert diff is not None
        assert diff.source_version == '1.0.0'
        assert diff.target_version == '1.1.0'
        assert len(diff.tokens_added) == 1  # token3
        assert 'token3' in diff.tokens_added
        assert len(diff.tokens_changed) == 1  # token2

        manager.shutdown()


# =============================================================================
# MOCK ROUTER FOR SAVE TESTS
# =============================================================================

class MockRouter:
    """Mock router for testing save operations."""

    def __init__(self):
        self.token_adapter = Mock()
        self.token_adapter.get_token_mappings.return_value = {
            'test': 'ACTION',
            'data': 'REFLECT'
        }
        self.token_adapter.get_frequency_history.return_value = []
        self.oscillator = Mock()
        self.oscillator.get_state.return_value = {
            'A': {'amplitude': 0.5, 'phase': 0.0},
            'B': {'amplitude': 0.3, 'phase': 0.1},
            'C': {'amplitude': 0.2, 'phase': 0.2}
        }
        self.oscillator.get_synchrony_vector.return_value = [0.8, 0.6, 0.4]
        self.oscillator.get_dominant_channel.return_value = 'advance'


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_semantic_version_equality(self):
        """Test version equality."""
        v1 = SemanticVersion(1, 2, 3)
        v2 = SemanticVersion(1, 2, 3)
        # Note: equality check via less-than comparison
        assert not (v1 < v2)
        assert not (v2 < v1)

    def test_empty_diff(self):
        """Test diff with identical checkpoints."""
        diff = CheckpointDiff(
            source_name="a",
            target_name="a",
            source_version="1.0.0",
            target_version="1.0.0"
        )
        assert diff.total_changes == 0
        assert diff.change_magnitude == 0.0

    def test_storage_adapter_base_class(self):
        """Test base StorageAdapter raises NotImplementedError."""
        adapter = StorageAdapter()

        with pytest.raises(NotImplementedError):
            adapter.upload("local", "remote")

        with pytest.raises(NotImplementedError):
            adapter.download("remote", "local")

        with pytest.raises(NotImplementedError):
            adapter.list()

        with pytest.raises(NotImplementedError):
            adapter.delete("path")

        with pytest.raises(NotImplementedError):
            adapter.exists("path")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
