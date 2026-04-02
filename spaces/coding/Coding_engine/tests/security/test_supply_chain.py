"""
Tests for Supply Chain Security.

Tests:
- SBOM generation (npm, pip, cargo, go)
- Vulnerability scanning
- License compliance checking
- Git signature verification
- Container image signing
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.security.supply_chain import (
    SBOMGenerator, VulnerabilityScanner, SupplyChainSecurity,
    SBOM, Dependency, CVE, LicenseRisk, SeverityLevel,
    LicenseComplianceResult, SignatureVerificationResult,
)


class TestDependency:
    """Tests for Dependency dataclass."""

    def test_dependency_creation(self):
        """Test basic dependency creation."""
        dep = Dependency(
            name="lodash",
            version="4.17.21",
            package_manager="npm",
            license="MIT",
        )

        assert dep.name == "lodash"
        assert dep.version == "4.17.21"
        assert dep.package_manager == "npm"

    def test_dependency_to_spdx_package(self):
        """Test conversion to SPDX package format."""
        dep = Dependency(
            name="react",
            version="18.2.0",
            package_manager="npm",
            license="MIT",
            purl="pkg:npm/react@18.2.0",
            checksums={"sha512": "abc123"},
        )

        spdx = dep.to_spdx_package()

        assert "SPDXRef-Package-react" in spdx["SPDXID"]
        assert spdx["name"] == "react"
        assert spdx["versionInfo"] == "18.2.0"
        assert spdx["licenseConcluded"] == "MIT"
        assert len(spdx["checksums"]) == 1

    def test_dependency_with_no_license(self):
        """Test dependency without license."""
        dep = Dependency(
            name="unknown-pkg",
            version="1.0.0",
            package_manager="npm",
        )

        spdx = dep.to_spdx_package()

        assert spdx["licenseConcluded"] == "NOASSERTION"


class TestSBOM:
    """Tests for SBOM dataclass."""

    def test_sbom_creation(self, sample_sbom: SBOM):
        """Test SBOM creation."""
        assert sample_sbom.document_name == "Test-SBOM"
        assert len(sample_sbom.packages) == 3

    def test_sbom_to_spdx_json(self, sample_sbom: SBOM):
        """Test SPDX JSON export."""
        spdx = sample_sbom.to_spdx_json()

        assert spdx["spdxVersion"] == "SPDX-2.3"
        assert spdx["dataLicense"] == "CC0-1.0"
        assert "SPDXID" in spdx
        assert len(spdx["packages"]) == 3
        assert len(spdx["relationships"]) > 0

    def test_sbom_to_cyclonedx_json(self, sample_sbom: SBOM):
        """Test CycloneDX JSON export."""
        cyclonedx = sample_sbom.to_cyclonedx_json()

        assert cyclonedx["bomFormat"] == "CycloneDX"
        assert cyclonedx["specVersion"] == "1.4"
        assert len(cyclonedx["components"]) == 3


class TestSBOMGenerator:
    """Tests for SBOM generation."""

    @pytest.mark.asyncio
    async def test_generate_sbom_from_package_json(self, temp_project_dir: Path):
        """Test SBOM generation from package.json."""
        generator = SBOMGenerator(temp_project_dir)
        sbom = await generator.generate()

        assert sbom is not None
        assert len(sbom.packages) > 0

        # Check for expected packages
        package_names = [p.name for p in sbom.packages]
        assert "react" in package_names

    @pytest.mark.asyncio
    async def test_generate_sbom_from_requirements_txt(self, temp_project_dir: Path):
        """Test SBOM generation from requirements.txt."""
        generator = SBOMGenerator(temp_project_dir)
        sbom = await generator.generate()

        package_names = [p.name for p in sbom.packages]
        pip_packages = [p for p in sbom.packages if p.package_manager == "pip"]

        assert len(pip_packages) > 0
        assert "fastapi" in package_names

    @pytest.mark.asyncio
    async def test_parse_package_lock_v2(self, tmp_path: Path):
        """Test parsing package-lock.json v2 format."""
        package_lock = {
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "test-project"},
                "node_modules/lodash": {
                    "version": "4.17.21",
                    "license": "MIT",
                    "integrity": "sha512-abc123",
                },
            },
        }
        (tmp_path / "package-lock.json").write_text(json.dumps(package_lock))

        generator = SBOMGenerator(tmp_path)
        deps = await generator._parse_package_lock(tmp_path / "package-lock.json")

        assert len(deps) == 1
        assert deps[0].name == "lodash"
        assert deps[0].version == "4.17.21"

    @pytest.mark.asyncio
    async def test_parse_requirements_txt(self, tmp_path: Path):
        """Test parsing requirements.txt."""
        requirements = """
# Comment
fastapi>=0.100.0
pydantic==2.0.0
-r other-requirements.txt
uvicorn
"""
        (tmp_path / "requirements.txt").write_text(requirements)

        generator = SBOMGenerator(tmp_path)
        deps = await generator._parse_requirements_txt(tmp_path / "requirements.txt")

        assert len(deps) >= 3
        names = [d.name for d in deps]
        assert "fastapi" in names
        assert "pydantic" in names
        assert "uvicorn" in names

    def test_save_sbom_spdx(self, sample_sbom: SBOM, tmp_path: Path):
        """Test saving SBOM in SPDX format."""
        generator = SBOMGenerator(tmp_path)
        output_path = tmp_path / "sbom.spdx.json"

        generator.save_sbom(sample_sbom, output_path, format="spdx-json")

        assert output_path.exists()
        content = json.loads(output_path.read_text())
        assert content["spdxVersion"] == "SPDX-2.3"

    def test_save_sbom_cyclonedx(self, sample_sbom: SBOM, tmp_path: Path):
        """Test saving SBOM in CycloneDX format."""
        generator = SBOMGenerator(tmp_path)
        output_path = tmp_path / "sbom.cdx.json"

        generator.save_sbom(sample_sbom, output_path, format="cyclonedx-json")

        assert output_path.exists()
        content = json.loads(output_path.read_text())
        assert content["bomFormat"] == "CycloneDX"


class TestVulnerabilityScanner:
    """Tests for vulnerability scanning."""

    @pytest.mark.asyncio
    async def test_scan_sbom(self, sample_sbom: SBOM):
        """Test scanning SBOM for vulnerabilities."""
        scanner = VulnerabilityScanner()
        cves = await scanner.scan_sbom(sample_sbom)

        # Our sample packages are safe, should have no CVEs
        # (in real implementation, would query OSV)
        assert isinstance(cves, list)

    @pytest.mark.asyncio
    async def test_scan_vulnerable_package(self):
        """Test scanning a known vulnerable package."""
        scanner = VulnerabilityScanner()

        # Create a vulnerable dependency
        vulnerable_dep = Dependency(
            name="lodash",
            version="4.17.20",  # Known vulnerable version
            package_manager="npm",
        )

        cves = await scanner.scan_package(vulnerable_dep)

        # Should find CVE-2021-23337
        assert len(cves) >= 1
        assert any("CVE-2021-23337" in cve.id for cve in cves)

    @pytest.mark.asyncio
    async def test_cve_caching(self):
        """Test that vulnerability results are cached."""
        scanner = VulnerabilityScanner()

        dep = Dependency(
            name="test-pkg",
            version="1.0.0",
            package_manager="npm",
        )

        # First call
        await scanner.scan_package(dep)

        # Second call should use cache
        assert f"npm:test-pkg:1.0.0" in scanner._cache


class TestCVE:
    """Tests for CVE dataclass."""

    def test_cve_creation(self, sample_cve: CVE):
        """Test CVE creation."""
        assert sample_cve.id == "CVE-2021-12345"
        assert sample_cve.severity == SeverityLevel.HIGH

    def test_cve_to_dict(self, sample_cve: CVE):
        """Test CVE serialization."""
        data = sample_cve.to_dict()

        assert data["id"] == "CVE-2021-12345"
        assert data["severity"] == "high"
        assert data["score"] == 7.5


class TestLicenseCompliance:
    """Tests for license compliance checking."""

    @pytest.mark.asyncio
    async def test_check_license_compliance_passing(
        self,
        sample_sbom: SBOM,
        temp_project_dir: Path,
    ):
        """Test license compliance check with permissive licenses."""
        security = SupplyChainSecurity(temp_project_dir)
        result = await security.check_license_compliance(sample_sbom)

        # All our sample packages are MIT licensed
        assert result.compliant is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_check_license_compliance_violation(
        self,
        temp_project_dir: Path,
    ):
        """Test license compliance check with forbidden license."""
        sbom = SBOM(
            document_name="test",
            document_namespace="test",
            creation_time=datetime.now(timezone.utc),
            packages=[
                Dependency(
                    name="gpl-package",
                    version="1.0.0",
                    package_manager="npm",
                    license="GPL-3.0",
                    license_risk=LicenseRisk.STRONG_COPYLEFT,
                ),
            ],
        )

        security = SupplyChainSecurity(temp_project_dir)
        result = await security.check_license_compliance(sbom)

        assert result.compliant is False
        assert len(result.violations) == 1
        assert result.violations[0]["license"] == "GPL-3.0"

    @pytest.mark.asyncio
    async def test_check_license_compliance_warning(
        self,
        temp_project_dir: Path,
    ):
        """Test license compliance check with review-required license."""
        sbom = SBOM(
            document_name="test",
            document_namespace="test",
            creation_time=datetime.now(timezone.utc),
            packages=[
                Dependency(
                    name="lgpl-package",
                    version="1.0.0",
                    package_manager="npm",
                    license="LGPL-3.0",
                ),
            ],
        )

        security = SupplyChainSecurity(temp_project_dir)
        result = await security.check_license_compliance(sbom)

        assert result.compliant is True  # Not a violation
        assert len(result.warnings) >= 1


class TestGitSignatureVerification:
    """Tests for git signature verification."""

    @pytest.mark.asyncio
    async def test_verify_git_signatures_success(self, temp_project_dir: Path):
        """Test successful git signature verification."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "G|User Name|KEYID"
            mock_thread.return_value = mock_result

            security = SupplyChainSecurity(temp_project_dir)
            result = await security.verify_git_signatures()

            assert result.verified is True
            assert result.signer == "User Name"

    @pytest.mark.asyncio
    async def test_verify_git_signatures_no_signature(self, temp_project_dir: Path):
        """Test git verification with no signature."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "N||"
            mock_thread.return_value = mock_result

            security = SupplyChainSecurity(temp_project_dir)
            result = await security.verify_git_signatures()

            assert result.verified is False

    @pytest.mark.asyncio
    async def test_verify_git_signatures_git_not_found(self, temp_project_dir: Path):
        """Test git verification when git is not available."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = FileNotFoundError()

            security = SupplyChainSecurity(temp_project_dir)
            result = await security.verify_git_signatures()

            assert result.verified is False
            assert "Git not found" in result.error


class TestContainerImageSigning:
    """Tests for container image signing."""

    @pytest.mark.asyncio
    async def test_sign_container_image(self, temp_project_dir: Path):
        """Test container image signing."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_thread.return_value = mock_result

            security = SupplyChainSecurity(temp_project_dir)
            result = await security.sign_container_image("myimage:latest")

            assert result == "myimage:latest"

    @pytest.mark.asyncio
    async def test_sign_container_image_cosign_not_found(
        self,
        temp_project_dir: Path,
    ):
        """Test image signing when cosign not available."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = FileNotFoundError()

            security = SupplyChainSecurity(temp_project_dir)
            result = await security.sign_container_image("myimage:latest")

            # Should return image without signing when cosign not available
            assert result == "myimage:latest"

    @pytest.mark.asyncio
    async def test_verify_image_signature(self, temp_project_dir: Path):
        """Test container image signature verification."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_thread.return_value = mock_result

            security = SupplyChainSecurity(temp_project_dir)
            result = await security.verify_image_signature("myimage:latest")

            assert result.verified is True


class TestFullSecurityAudit:
    """Tests for full security audit."""

    @pytest.mark.asyncio
    async def test_full_security_audit(self, temp_project_dir: Path):
        """Test comprehensive security audit."""
        with patch.object(
            SupplyChainSecurity,
            "verify_git_signatures",
            new_callable=AsyncMock,
        ) as mock_git:
            mock_git.return_value = SignatureVerificationResult(verified=True)

            security = SupplyChainSecurity(temp_project_dir)
            report = await security.full_security_audit()

            assert "timestamp" in report
            assert "sbom" in report
            assert "vulnerabilities" in report
            assert "license_compliance" in report
            assert "git_signatures" in report
            assert "risk_score" in report
            assert "risk_level" in report

    @pytest.mark.asyncio
    async def test_risk_score_calculation(self, temp_project_dir: Path):
        """Test risk score calculation."""
        security = SupplyChainSecurity(temp_project_dir)

        # Create some vulnerabilities
        vulnerabilities = [
            CVE(
                id="CVE-1",
                severity=SeverityLevel.CRITICAL,
                score=9.8,
                package_name="pkg1",
                vulnerable_versions="<1.0",
                fixed_version="1.0",
                summary="Critical vuln",
            ),
            CVE(
                id="CVE-2",
                severity=SeverityLevel.HIGH,
                score=7.5,
                package_name="pkg2",
                vulnerable_versions="<2.0",
                fixed_version="2.0",
                summary="High vuln",
            ),
        ]

        # Create license result with violations
        license_result = LicenseComplianceResult(
            compliant=False,
            violations=[{"package": "gpl-pkg", "license": "GPL-3.0"}],
        )

        score = security._calculate_risk_score(vulnerabilities, license_result)

        # CRITICAL (25) + HIGH (15) + violation (20) = 60
        assert score == 60

    def test_risk_level_from_score(self, temp_project_dir: Path):
        """Test risk level classification."""
        security = SupplyChainSecurity(temp_project_dir)

        assert security._risk_level_from_score(0) == "NONE"
        assert security._risk_level_from_score(10) == "LOW"
        assert security._risk_level_from_score(30) == "MEDIUM"
        assert security._risk_level_from_score(60) == "HIGH"
        assert security._risk_level_from_score(80) == "CRITICAL"


class TestLicenseRisk:
    """Tests for LicenseRisk enum."""

    def test_license_risk_values(self):
        """Test all LicenseRisk values exist."""
        assert LicenseRisk.PERMISSIVE.value == "permissive"
        assert LicenseRisk.WEAK_COPYLEFT.value == "weak_copyleft"
        assert LicenseRisk.STRONG_COPYLEFT.value == "strong_copyleft"
        assert LicenseRisk.PROPRIETARY.value == "proprietary"
        assert LicenseRisk.UNKNOWN.value == "unknown"


class TestSeverityLevel:
    """Tests for SeverityLevel enum."""

    def test_severity_level_values(self):
        """Test all SeverityLevel values exist."""
        assert SeverityLevel.CRITICAL.value == "critical"
        assert SeverityLevel.HIGH.value == "high"
        assert SeverityLevel.MEDIUM.value == "medium"
        assert SeverityLevel.LOW.value == "low"
        assert SeverityLevel.UNKNOWN.value == "unknown"
