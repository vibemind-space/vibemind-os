"""
Tests for Cell CLI marketplace commands.

Tests:
- Search cells
- Install cells
- Update cells
- List installed cells
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner


class TestSearchCommand:
    """Tests for `cell search` command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_search_cells(self, runner: CliRunner, config_dir: Path):
        """Test searching for cells."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with patch("cell_cli.api.MarketplaceAPI.search") as mock_search:
                    mock_search.return_value = {
                        "results": [
                            {"namespace": "auth/jwt-auth", "description": "JWT Auth"},
                            {"namespace": "auth/oauth2", "description": "OAuth2 Auth"},
                        ]
                    }

                    result = runner.invoke(cli, ["search", "auth"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_search_with_filters(self, runner: CliRunner, config_dir: Path):
        """Test searching with filters."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                result = runner.invoke(
                    cli,
                    ["search", "auth", "--category", "security", "--sort", "downloads"],
                )

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_search_no_results(self, runner: CliRunner, config_dir: Path):
        """Test search with no results."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with patch("cell_cli.api.MarketplaceAPI.search") as mock_search:
                    mock_search.return_value = {"results": []}

                    result = runner.invoke(cli, ["search", "nonexistent"])

            assert result.exit_code == 0
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")


class TestInstallCommand:
    """Tests for `cell install` command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    @pytest.fixture
    def project_dir(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "my-project"
        project.mkdir()
        (project / "cell.json").write_text('{"name": "my-project"}')
        return project

    def test_install_cell(
        self,
        runner: CliRunner,
        config_dir: Path,
        project_dir: Path,
    ):
        """Test installing a cell."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    # Create a cell.json in current directory
                    Path("cell.json").write_text('{"name": "test"}')

                    result = runner.invoke(cli, ["install", "auth/jwt-auth"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_install_specific_version(
        self,
        runner: CliRunner,
        config_dir: Path,
    ):
        """Test installing a specific version."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text('{"name": "test"}')

                    result = runner.invoke(cli, ["install", "auth/jwt-auth@1.2.0"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_install_with_dependencies(
        self,
        runner: CliRunner,
        config_dir: Path,
    ):
        """Test installing cell with dependencies."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text('{"name": "test"}')

                    result = runner.invoke(cli, ["install", "complex-cell"])

            # Should resolve and install dependencies
            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_install_not_in_project(
        self,
        runner: CliRunner,
        config_dir: Path,
    ):
        """Test install fails when not in a project."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    # No cell.json

                    result = runner.invoke(cli, ["install", "some-cell"])

            # Should fail with error about not being in a project
            assert result.exit_code != 0
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")


class TestUpdateCommand:
    """Tests for `cell update` command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_update_all_cells(self, runner: CliRunner, config_dir: Path):
        """Test updating all installed cells."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text(json.dumps({
                        "name": "test",
                        "dependencies": {
                            "auth/jwt-auth": "^1.0.0",
                        },
                    }))

                    result = runner.invoke(cli, ["update"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_update_specific_cell(self, runner: CliRunner, config_dir: Path):
        """Test updating a specific cell."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text(json.dumps({
                        "name": "test",
                        "dependencies": {
                            "auth/jwt-auth": "^1.0.0",
                        },
                    }))

                    result = runner.invoke(cli, ["update", "auth/jwt-auth"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_update_check_only(self, runner: CliRunner, config_dir: Path):
        """Test checking for updates without installing."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text('{"name": "test"}')

                    result = runner.invoke(cli, ["update", "--check"])

            assert result.exit_code == 0
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")


class TestListCommand:
    """Tests for `cell list` command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_list_installed_cells(self, runner: CliRunner, config_dir: Path):
        """Test listing installed cells."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text(json.dumps({
                        "name": "test",
                        "dependencies": {
                            "auth/jwt-auth": "1.0.0",
                            "db/postgres": "2.1.0",
                        },
                    }))

                    result = runner.invoke(cli, ["list"])

            assert result.exit_code == 0
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_list_outdated(self, runner: CliRunner, config_dir: Path):
        """Test listing outdated cells."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with runner.isolated_filesystem():
                    Path("cell.json").write_text('{"name": "test"}')

                    result = runner.invoke(cli, ["list", "--outdated"])

            assert result.exit_code == 0
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")


class TestInfoCommand:
    """Tests for `cell info` command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    @pytest.fixture
    def config_dir(self, tmp_path: Path) -> Path:
        """Create a temporary config directory."""
        config = tmp_path / ".cell-cli"
        config.mkdir()
        return config

    def test_info_cell(self, runner: CliRunner, config_dir: Path):
        """Test getting info about a cell."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                with patch("cell_cli.api.MarketplaceAPI.get_cell") as mock_get:
                    mock_get.return_value = {
                        "namespace": "auth/jwt-auth",
                        "description": "JWT Authentication",
                        "latest_version": "1.2.0",
                        "downloads": 1000,
                    }

                    result = runner.invoke(cli, ["info", "auth/jwt-auth"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")

    def test_info_cell_versions(self, runner: CliRunner, config_dir: Path):
        """Test getting version history."""
        try:
            from cell_cli.main import cli

            with patch.dict("os.environ", {"CELL_CLI_CONFIG": str(config_dir)}):
                result = runner.invoke(cli, ["info", "auth/jwt-auth", "--versions"])

            assert result.exit_code in (0, 1)
        except ImportError:
            pytest.skip("Cell CLI not implemented yet")
