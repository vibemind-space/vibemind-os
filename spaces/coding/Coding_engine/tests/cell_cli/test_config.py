"""
Tests for Cell CLI configuration management.

Tests:
- Config file loading/saving
- Credentials storage
- Tenant configuration
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCLIConfig:
    """Tests for CLI configuration."""

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_load_config_default(self, config_dir: Path):
        """Test loading default config when none exists."""
        try:
            from cell_cli.config import Config

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                config = Config.load()

            assert config is not None
            assert config.api_url == "https://api.codingengine.io"
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_load_config_from_file(self, config_dir: Path):
        """Test loading config from file."""
        config_data = {
            "api_url": "https://custom-api.example.com",
            "default_tenant": "my-org",
        }
        (config_dir / "config.json").write_text(json.dumps(config_data))

        try:
            from cell_cli.config import Config

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                config = Config.load()

            assert config.api_url == "https://custom-api.example.com"
            assert config.default_tenant == "my-org"
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_save_config(self, config_dir: Path):
        """Test saving config to file."""
        try:
            from cell_cli.config import Config

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                config = Config(
                    api_url="https://test.example.com",
                    default_tenant="test-org",
                )
                config.save()

            config_file = config_dir / "config.json"
            assert config_file.exists()

            saved_data = json.loads(config_file.read_text())
            assert saved_data["api_url"] == "https://test.example.com"
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")


class TestCredentialsStorage:
    """Tests for credentials storage."""

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_store_credentials(self, config_dir: Path):
        """Test storing credentials."""
        try:
            from cell_cli.config import CredentialsManager

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                manager = CredentialsManager(config_dir)
                manager.store(
                    access_token="token-123",
                    refresh_token="refresh-456",
                    expires_in=3600,
                )

            creds_file = config_dir / "credentials.json"
            assert creds_file.exists()
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_load_credentials(self, config_dir: Path):
        """Test loading credentials."""
        creds_data = {
            "access_token": "token-123",
            "refresh_token": "refresh-456",
            "expires_at": "2099-01-01T00:00:00",
        }
        (config_dir / "credentials.json").write_text(json.dumps(creds_data))

        try:
            from cell_cli.config import CredentialsManager

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                manager = CredentialsManager(config_dir)
                creds = manager.load()

            assert creds is not None
            assert creds.access_token == "token-123"
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_credentials_expired(self, config_dir: Path):
        """Test checking expired credentials."""
        creds_data = {
            "access_token": "token-123",
            "refresh_token": "refresh-456",
            "expires_at": "2020-01-01T00:00:00",  # In the past
        }
        (config_dir / "credentials.json").write_text(json.dumps(creds_data))

        try:
            from cell_cli.config import CredentialsManager

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                manager = CredentialsManager(config_dir)
                creds = manager.load()

            assert creds.is_expired is True
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_clear_credentials(self, config_dir: Path):
        """Test clearing credentials."""
        creds_file = config_dir / "credentials.json"
        creds_file.write_text('{"access_token": "test"}')

        try:
            from cell_cli.config import CredentialsManager

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                manager = CredentialsManager(config_dir)
                manager.clear()

            assert not creds_file.exists()
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")


class TestTenantConfiguration:
    """Tests for multi-tenant configuration."""

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_get_current_tenant(self, config_dir: Path):
        """Test getting current tenant."""
        config_data = {"default_tenant": "my-org"}
        (config_dir / "config.json").write_text(json.dumps(config_data))

        try:
            from cell_cli.config import Config

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                config = Config.load()

            assert config.default_tenant == "my-org"
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_switch_tenant(self, config_dir: Path):
        """Test switching tenants."""
        try:
            from cell_cli.config import Config

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                config = Config()
                config.switch_tenant("new-org")
                config.save()

            assert config.default_tenant == "new-org"
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_list_tenants(self, config_dir: Path):
        """Test listing available tenants."""
        config_data = {
            "tenants": ["org1", "org2", "org3"],
            "default_tenant": "org1",
        }
        (config_dir / "config.json").write_text(json.dumps(config_data))

        try:
            from cell_cli.config import Config

            with patch.dict(os.environ, {"CELL_CLI_CONFIG": str(config_dir)}):
                config = Config.load()

            assert len(config.tenants) == 3
            assert "org1" in config.tenants
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")
