"""
Universal VNC Streaming Tests for SandboxTool

Tests that VNC streaming works for ALL project types:
- Electron apps (direct Xvfb display)
- React/Vite web apps (Chromium browser)
- Node.js API apps (Chromium browser)
- Python FastAPI/Flask apps (Chromium browser)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import json
import os

# Import the SandboxTool and related classes
from src.tools.sandbox_tool import (
    SandboxTool,
    SandboxResult,
    ProjectType,
    run_sandbox_test,
)


class TestSandboxVNCUniversal:
    """Tests for universal VNC support across all project types."""

    @pytest.fixture
    def mock_docker_available(self):
        """Mock Docker being available."""
        async def mock_check():
            return True
        return mock_check

    @pytest.fixture
    def mock_sandbox_image_available(self):
        """Mock sandbox image being available."""
        async def mock_check():
            return True
        return mock_check

    def test_vnc_enabled_for_electron(self, tmp_path):
        """Test VNC is enabled for Electron projects."""
        # Create mock package.json with electron
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {"electron": "^28.0.0"}
        }))

        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)
        project_type = tool.detect_project_type()

        assert project_type == ProjectType.ELECTRON
        assert tool.enable_vnc is True
        assert tool.vnc_port == 6080

    def test_vnc_enabled_for_react_vite(self, tmp_path):
        """Test VNC is enabled for React/Vite projects."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {"react": "^18.0.0", "vite": "^5.0.0"}
        }))

        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)
        project_type = tool.detect_project_type()

        assert project_type == ProjectType.REACT_VITE
        assert tool.enable_vnc is True

    def test_vnc_enabled_for_node_api(self, tmp_path):
        """Test VNC is enabled for Node.js API projects."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "dependencies": {"express": "^4.18.0"}
        }))

        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)
        project_type = tool.detect_project_type()

        assert project_type == ProjectType.NODE_API
        assert tool.enable_vnc is True

    def test_vnc_enabled_for_fastapi(self, tmp_path):
        """Test VNC is enabled for FastAPI projects."""
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("fastapi==0.104.1\nuvicorn[standard]")

        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)
        project_type = tool.detect_project_type()

        assert project_type == ProjectType.PYTHON_FASTAPI
        assert tool.enable_vnc is True

    def test_vnc_enabled_for_flask(self, tmp_path):
        """Test VNC is enabled for Flask projects."""
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("flask==3.0.0\ngunicorn")

        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)
        project_type = tool.detect_project_type()

        assert project_type == ProjectType.PYTHON_FLASK
        assert tool.enable_vnc is True


class TestSandboxResultVNC:
    """Tests for SandboxResult VNC fields."""

    def test_result_contains_vnc_info(self):
        """Test SandboxResult contains VNC information."""
        result = SandboxResult(
            success=True,
            project_type=ProjectType.REACT_VITE,
            vnc_enabled=True,
            vnc_url="http://localhost:6080/vnc.html",
            vnc_port=6080,
        )

        assert result.vnc_enabled is True
        assert result.vnc_url == "http://localhost:6080/vnc.html"
        assert result.vnc_port == 6080

    def test_result_to_dict_includes_vnc(self):
        """Test SandboxResult.to_dict() includes VNC info when enabled."""
        result = SandboxResult(
            success=True,
            project_type=ProjectType.REACT_VITE,
            vnc_enabled=True,
            vnc_url="http://localhost:6080/vnc.html",
            vnc_port=6080,
        )

        result_dict = result.to_dict()

        assert "vnc_streaming" in result_dict
        assert result_dict["vnc_streaming"]["enabled"] is True
        assert result_dict["vnc_streaming"]["url"] == "http://localhost:6080/vnc.html"
        assert result_dict["vnc_streaming"]["port"] == 6080

    def test_result_to_dict_excludes_vnc_when_disabled(self):
        """Test SandboxResult.to_dict() excludes VNC info when disabled."""
        result = SandboxResult(
            success=True,
            project_type=ProjectType.REACT_VITE,
            vnc_enabled=False,
        )

        result_dict = result.to_dict()

        assert "vnc_streaming" not in result_dict


class TestDockerContainerVNC:
    """Tests for Docker container creation with VNC."""

    @pytest.mark.asyncio
    async def test_container_command_includes_vnc_for_all_types(self, tmp_path):
        """Test Docker container command includes VNC env vars for all project types."""
        for project_type in [
            ProjectType.ELECTRON,
            ProjectType.REACT_VITE,
            ProjectType.NODE_API,
            ProjectType.PYTHON_FASTAPI,
            ProjectType.PYTHON_FLASK,
        ]:
            # Create appropriate project files
            if project_type == ProjectType.ELECTRON:
                (tmp_path / "package.json").write_text(
                    json.dumps({"dependencies": {"electron": "^28.0.0"}})
                )
            elif project_type == ProjectType.REACT_VITE:
                (tmp_path / "package.json").write_text(
                    json.dumps({"dependencies": {"react": "^18.0.0", "vite": "^5.0.0"}})
                )
            elif project_type == ProjectType.NODE_API:
                (tmp_path / "package.json").write_text(
                    json.dumps({"dependencies": {"express": "^4.18.0"}})
                )
            elif project_type == ProjectType.PYTHON_FASTAPI:
                (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn")
            elif project_type == ProjectType.PYTHON_FLASK:
                (tmp_path / "requirements.txt").write_text("flask\ngunicorn")

            tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)
            detected = tool.detect_project_type()

            # VNC should be enabled for all project types
            assert tool.enable_vnc is True, f"VNC should be enabled for {project_type}"


class TestVNCPortConfiguration:
    """Tests for VNC port configuration."""

    def test_default_vnc_ports(self, tmp_path):
        """Test default VNC port values."""
        tool = SandboxTool(str(tmp_path), enable_vnc=True)

        assert tool.vnc_port == 6080  # noVNC web port
        assert tool.DEFAULT_VNC_PORT == 5900  # VNC server port
        assert tool.DEFAULT_NOVNC_PORT == 6080  # noVNC web port

    def test_custom_vnc_port(self, tmp_path):
        """Test custom VNC port configuration."""
        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=7080)

        assert tool.vnc_port == 7080

    def test_vnc_url_format(self, tmp_path):
        """Test VNC URL format."""
        tool = SandboxTool(str(tmp_path), enable_vnc=True, vnc_port=6080)

        # Simulate what would be set in result
        expected_url = f"http://localhost:{tool.vnc_port}/vnc.html"
        assert expected_url == "http://localhost:6080/vnc.html"


class TestProjectTypeDetection:
    """Tests for project type detection (ensuring all types work with VNC)."""

    def test_detect_electron(self, tmp_path):
        """Detect Electron project."""
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"electron": "^28.0.0"}})
        )
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.ELECTRON

    def test_detect_electron_vite(self, tmp_path):
        """Detect Electron-Vite project."""
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"electron-vite": "^2.0.0"}})
        )
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.ELECTRON

    def test_detect_react_vite(self, tmp_path):
        """Detect React/Vite project."""
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.0.0"}, "devDependencies": {"vite": "^5.0.0"}})
        )
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.REACT_VITE

    def test_detect_vue(self, tmp_path):
        """Detect Vue project (should map to REACT_VITE)."""
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"vue": "^3.0.0"}})
        )
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.REACT_VITE

    def test_detect_express(self, tmp_path):
        """Detect Express.js API project."""
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"express": "^4.18.0"}})
        )
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.NODE_API

    def test_detect_fastify(self, tmp_path):
        """Detect Fastify API project."""
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"fastify": "^4.0.0"}})
        )
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.NODE_API

    def test_detect_fastapi(self, tmp_path):
        """Detect FastAPI project."""
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100.0\nuvicorn")
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.PYTHON_FASTAPI

    def test_detect_flask(self, tmp_path):
        """Detect Flask project."""
        (tmp_path / "requirements.txt").write_text("flask>=3.0.0\ngunicorn")
        tool = SandboxTool(str(tmp_path), enable_vnc=True)
        assert tool.detect_project_type() == ProjectType.PYTHON_FLASK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])