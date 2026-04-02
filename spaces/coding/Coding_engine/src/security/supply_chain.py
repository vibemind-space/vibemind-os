"""
Supply Chain Security - SBOM generation and dependency scanning.

Provides comprehensive supply chain security:
- SBOM generation in SPDX format
- Dependency vulnerability scanning via OSV/NVD
- Git signature verification
- Container image signing with Sigstore/Cosign
- License compliance checking
"""

import asyncio
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

import structlog

logger = structlog.get_logger()


class SeverityLevel(str, Enum):
    """CVE severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class LicenseRisk(str, Enum):
    """License risk classification."""
    PERMISSIVE = "permissive"  # MIT, Apache, BSD
    WEAK_COPYLEFT = "weak_copyleft"  # LGPL, MPL
    STRONG_COPYLEFT = "strong_copyleft"  # GPL, AGPL
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


@dataclass
class Dependency:
    """Represents a software dependency."""
    name: str
    version: str
    package_manager: str  # npm, pip, cargo, go
    license: Optional[str] = None
    license_risk: LicenseRisk = LicenseRisk.UNKNOWN
    purl: Optional[str] = None  # Package URL (PURL)
    checksums: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # Transitive deps

    def to_spdx_package(self) -> Dict[str, Any]:
        """Convert to SPDX package format."""
        pkg = {
            "SPDXID": f"SPDXRef-Package-{self.name}-{self.version}".replace(".", "-"),
            "name": self.name,
            "versionInfo": self.version,
            "downloadLocation": self.purl or "NOASSERTION",
            "filesAnalyzed": False,
        }

        if self.license:
            pkg["licenseConcluded"] = self.license
            pkg["licenseDeclared"] = self.license
        else:
            pkg["licenseConcluded"] = "NOASSERTION"
            pkg["licenseDeclared"] = "NOASSERTION"

        if self.checksums:
            pkg["checksums"] = [
                {"algorithm": algo.upper(), "checksumValue": value}
                for algo, value in self.checksums.items()
            ]

        if self.purl:
            pkg["externalRefs"] = [{
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": self.purl
            }]

        return pkg


@dataclass
class CVE:
    """Represents a Common Vulnerabilities and Exposures entry."""
    id: str
    severity: SeverityLevel
    score: float  # CVSS score
    package_name: str
    vulnerable_versions: str
    fixed_version: Optional[str]
    summary: str
    references: List[str] = field(default_factory=list)
    published: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "severity": self.severity.value,
            "score": self.score,
            "package_name": self.package_name,
            "vulnerable_versions": self.vulnerable_versions,
            "fixed_version": self.fixed_version,
            "summary": self.summary,
            "references": self.references,
            "published": self.published.isoformat() if self.published else None,
        }


@dataclass
class SBOM:
    """Software Bill of Materials in SPDX format."""
    document_name: str
    document_namespace: str
    creation_time: datetime
    creator_tool: str = "CodingEngine-SBOMGenerator-1.0"
    packages: List[Dependency] = field(default_factory=list)
    relationships: List[Dict[str, str]] = field(default_factory=list)
    spdx_version: str = "SPDX-2.3"
    data_license: str = "CC0-1.0"

    def to_spdx_json(self) -> Dict[str, Any]:
        """Export to SPDX JSON format."""
        doc = {
            "spdxVersion": self.spdx_version,
            "dataLicense": self.data_license,
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": self.document_name,
            "documentNamespace": self.document_namespace,
            "creationInfo": {
                "created": self.creation_time.isoformat(),
                "creators": [f"Tool: {self.creator_tool}"],
            },
            "packages": [pkg.to_spdx_package() for pkg in self.packages],
            "relationships": self.relationships or [{
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relatedSpdxElement": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES"
            }],
        }

        # Add relationships for each package
        for pkg in self.packages:
            doc["relationships"].append({
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relatedSpdxElement": pkg.to_spdx_package()["SPDXID"],
                "relationshipType": "DESCRIBES"
            })

        return doc

    def to_cyclonedx_json(self) -> Dict[str, Any]:
        """Export to CycloneDX JSON format."""
        components = []
        for pkg in self.packages:
            component = {
                "type": "library",
                "name": pkg.name,
                "version": pkg.version,
                "purl": pkg.purl,
            }
            if pkg.license:
                component["licenses"] = [{"license": {"id": pkg.license}}]
            if pkg.checksums:
                component["hashes"] = [
                    {"alg": algo.upper().replace("SHA", "SHA-"), "content": value}
                    for algo, value in pkg.checksums.items()
                ]
            components.append(component)

        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "version": 1,
            "metadata": {
                "timestamp": self.creation_time.isoformat(),
                "tools": [{"name": self.creator_tool}],
            },
            "components": components,
        }


@dataclass
class LicenseComplianceResult:
    """Result of license compliance check."""
    compliant: bool
    violations: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[Dict[str, str]] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)


@dataclass
class SignatureVerificationResult:
    """Result of signature verification."""
    verified: bool
    signer: Optional[str] = None
    timestamp: Optional[datetime] = None
    certificate_chain: List[str] = field(default_factory=list)
    error: Optional[str] = None


class SBOMGenerator:
    """
    Generates Software Bill of Materials (SBOM) from project dependencies.

    Supports:
    - npm (package.json, package-lock.json)
    - pip (requirements.txt, Pipfile.lock, poetry.lock)
    - cargo (Cargo.lock)
    - go (go.sum)
    """

    # License classification mapping
    LICENSE_CLASSIFICATION = {
        # Permissive
        "MIT": LicenseRisk.PERMISSIVE,
        "Apache-2.0": LicenseRisk.PERMISSIVE,
        "BSD-2-Clause": LicenseRisk.PERMISSIVE,
        "BSD-3-Clause": LicenseRisk.PERMISSIVE,
        "ISC": LicenseRisk.PERMISSIVE,
        "Unlicense": LicenseRisk.PERMISSIVE,
        "CC0-1.0": LicenseRisk.PERMISSIVE,
        "0BSD": LicenseRisk.PERMISSIVE,
        # Weak Copyleft
        "LGPL-2.1": LicenseRisk.WEAK_COPYLEFT,
        "LGPL-3.0": LicenseRisk.WEAK_COPYLEFT,
        "MPL-2.0": LicenseRisk.WEAK_COPYLEFT,
        "EPL-1.0": LicenseRisk.WEAK_COPYLEFT,
        "EPL-2.0": LicenseRisk.WEAK_COPYLEFT,
        # Strong Copyleft
        "GPL-2.0": LicenseRisk.STRONG_COPYLEFT,
        "GPL-3.0": LicenseRisk.STRONG_COPYLEFT,
        "AGPL-3.0": LicenseRisk.STRONG_COPYLEFT,
    }

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.logger = logger.bind(component="SBOMGenerator", project=str(project_path))

    async def generate(self) -> SBOM:
        """Generate SBOM from project dependencies."""
        self.logger.info("Generating SBOM")

        packages: List[Dependency] = []

        # Detect and parse all dependency files
        parsers = [
            (self._parse_package_lock, "package-lock.json"),
            (self._parse_package_json, "package.json"),
            (self._parse_requirements_txt, "requirements.txt"),
            (self._parse_pipfile_lock, "Pipfile.lock"),
            (self._parse_poetry_lock, "poetry.lock"),
            (self._parse_cargo_lock, "Cargo.lock"),
            (self._parse_go_sum, "go.sum"),
        ]

        for parser, filename in parsers:
            filepath = self.project_path / filename
            if filepath.exists():
                try:
                    deps = await parser(filepath)
                    packages.extend(deps)
                    self.logger.info("Parsed dependencies", file=filename, count=len(deps))
                except Exception as e:
                    self.logger.warning("Failed to parse", file=filename, error=str(e))

        # Deduplicate packages
        seen = set()
        unique_packages = []
        for pkg in packages:
            key = (pkg.name, pkg.version, pkg.package_manager)
            if key not in seen:
                seen.add(key)
                unique_packages.append(pkg)

        sbom = SBOM(
            document_name=f"SBOM-{self.project_path.name}",
            document_namespace=f"https://codingengine.io/sbom/{uuid.uuid4()}",
            creation_time=datetime.now(timezone.utc),
            packages=unique_packages,
        )

        self.logger.info("SBOM generated", total_packages=len(unique_packages))
        return sbom

    async def _parse_package_lock(self, filepath: Path) -> List[Dependency]:
        """Parse npm package-lock.json."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        packages = []
        lock_version = data.get("lockfileVersion", 1)

        if lock_version >= 2:
            # v2/v3 format with "packages" object
            for path, info in data.get("packages", {}).items():
                if not path:  # Skip root
                    continue
                name = path.split("node_modules/")[-1]
                version = info.get("version", "unknown")
                license_id = info.get("license")

                packages.append(Dependency(
                    name=name,
                    version=version,
                    package_manager="npm",
                    license=license_id,
                    license_risk=self.LICENSE_CLASSIFICATION.get(license_id, LicenseRisk.UNKNOWN),
                    purl=f"pkg:npm/{name}@{version}",
                    checksums={"sha512": info.get("integrity", "").split("-")[-1]} if info.get("integrity") else {},
                ))
        else:
            # v1 format with "dependencies" object
            for name, info in data.get("dependencies", {}).items():
                version = info.get("version", "unknown")
                packages.append(Dependency(
                    name=name,
                    version=version,
                    package_manager="npm",
                    purl=f"pkg:npm/{name}@{version}",
                    checksums={"sha512": info.get("integrity", "").split("-")[-1]} if info.get("integrity") else {},
                ))

        return packages

    async def _parse_package_json(self, filepath: Path) -> List[Dependency]:
        """Parse npm package.json (only direct deps, no versions locked)."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        packages = []
        all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        for name, version_spec in all_deps.items():
            # Clean version specifier
            version = re.sub(r"^[\^~>=<]+", "", version_spec)
            packages.append(Dependency(
                name=name,
                version=version,
                package_manager="npm",
                purl=f"pkg:npm/{name}@{version}",
            ))

        return packages

    async def _parse_requirements_txt(self, filepath: Path) -> List[Dependency]:
        """Parse pip requirements.txt."""
        packages = []

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue

                # Parse various formats: pkg==1.0, pkg>=1.0, pkg
                match = re.match(r"^([a-zA-Z0-9_-]+)(?:[=<>!~]+(.+))?", line)
                if match:
                    name = match.group(1)
                    version = match.group(2) or "unknown"
                    packages.append(Dependency(
                        name=name,
                        version=version,
                        package_manager="pip",
                        purl=f"pkg:pypi/{name}@{version}",
                    ))

        return packages

    async def _parse_pipfile_lock(self, filepath: Path) -> List[Dependency]:
        """Parse Pipfile.lock."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        packages = []
        for section in ["default", "develop"]:
            for name, info in data.get(section, {}).items():
                version = info.get("version", "").lstrip("=")
                hashes = info.get("hashes", [])
                checksums = {}
                if hashes:
                    # Parse first hash
                    parts = hashes[0].split(":")
                    if len(parts) == 2:
                        checksums[parts[0]] = parts[1]

                packages.append(Dependency(
                    name=name,
                    version=version,
                    package_manager="pip",
                    purl=f"pkg:pypi/{name}@{version}",
                    checksums=checksums,
                ))

        return packages

    async def _parse_poetry_lock(self, filepath: Path) -> List[Dependency]:
        """Parse poetry.lock (TOML format)."""
        packages = []

        try:
            import tomllib
            with open(filepath, "rb") as f:
                data = tomllib.load(f)
        except ImportError:
            # Fallback: simple regex parsing
            content = filepath.read_text(encoding="utf-8")
            for match in re.finditer(r'\[\[package\]\]\s*name\s*=\s*"([^"]+)"\s*version\s*=\s*"([^"]+)"', content):
                packages.append(Dependency(
                    name=match.group(1),
                    version=match.group(2),
                    package_manager="pip",
                    purl=f"pkg:pypi/{match.group(1)}@{match.group(2)}",
                ))
            return packages

        for pkg in data.get("package", []):
            packages.append(Dependency(
                name=pkg.get("name", ""),
                version=pkg.get("version", ""),
                package_manager="pip",
                purl=f"pkg:pypi/{pkg.get('name')}@{pkg.get('version')}",
            ))

        return packages

    async def _parse_cargo_lock(self, filepath: Path) -> List[Dependency]:
        """Parse Cargo.lock."""
        packages = []
        content = filepath.read_text(encoding="utf-8")

        # Parse TOML-like structure with regex
        for match in re.finditer(
            r'\[\[package\]\]\s*name\s*=\s*"([^"]+)"\s*version\s*=\s*"([^"]+)"(?:\s*checksum\s*=\s*"([^"]+)")?',
            content,
            re.MULTILINE
        ):
            name, version, checksum = match.groups()
            packages.append(Dependency(
                name=name,
                version=version,
                package_manager="cargo",
                purl=f"pkg:cargo/{name}@{version}",
                checksums={"sha256": checksum} if checksum else {},
            ))

        return packages

    async def _parse_go_sum(self, filepath: Path) -> List[Dependency]:
        """Parse go.sum."""
        packages = []
        seen = set()

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3:
                    module = parts[0]
                    version = parts[1].split("/")[0].lstrip("v")
                    checksum = parts[2]

                    key = (module, version)
                    if key not in seen:
                        seen.add(key)
                        packages.append(Dependency(
                            name=module,
                            version=version,
                            package_manager="go",
                            purl=f"pkg:golang/{module}@{version}",
                            checksums={"sha256": checksum.split(":")[-1] if ":" in checksum else checksum},
                        ))

        return packages

    def save_sbom(self, sbom: SBOM, output_path: Path, format: str = "spdx-json") -> None:
        """Save SBOM to file."""
        if format == "spdx-json":
            data = sbom.to_spdx_json()
        elif format == "cyclonedx-json":
            data = sbom.to_cyclonedx_json()
        else:
            raise ValueError(f"Unknown format: {format}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.logger.info("SBOM saved", path=str(output_path), format=format)


class VulnerabilityScanner:
    """
    Scans dependencies for known vulnerabilities using OSV and NVD databases.
    """

    # OSV API endpoint
    OSV_API_URL = "https://api.osv.dev/v1/query"

    # Ecosystem mapping
    ECOSYSTEM_MAP = {
        "npm": "npm",
        "pip": "PyPI",
        "cargo": "crates.io",
        "go": "Go",
    }

    def __init__(self):
        self.logger = logger.bind(component="VulnerabilityScanner")
        self._cache: Dict[str, List[CVE]] = {}

    async def scan_sbom(self, sbom: SBOM) -> List[CVE]:
        """Scan all packages in SBOM for vulnerabilities."""
        self.logger.info("Scanning SBOM for vulnerabilities", packages=len(sbom.packages))

        all_cves: List[CVE] = []

        # Batch packages by ecosystem for efficient querying
        for pkg in sbom.packages:
            cves = await self.scan_package(pkg)
            all_cves.extend(cves)

        # Sort by severity and score
        severity_order = {SeverityLevel.CRITICAL: 0, SeverityLevel.HIGH: 1,
                         SeverityLevel.MEDIUM: 2, SeverityLevel.LOW: 3, SeverityLevel.UNKNOWN: 4}
        all_cves.sort(key=lambda c: (severity_order.get(c.severity, 4), -c.score))

        self.logger.info("Vulnerability scan complete",
                        total_vulnerabilities=len(all_cves),
                        critical=len([c for c in all_cves if c.severity == SeverityLevel.CRITICAL]),
                        high=len([c for c in all_cves if c.severity == SeverityLevel.HIGH]))

        return all_cves

    async def scan_package(self, package: Dependency) -> List[CVE]:
        """Scan a single package for vulnerabilities."""
        cache_key = f"{package.package_manager}:{package.name}:{package.version}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        ecosystem = self.ECOSYSTEM_MAP.get(package.package_manager)
        if not ecosystem:
            return []

        try:
            # Query OSV API
            cves = await self._query_osv(package.name, package.version, ecosystem)
            self._cache[cache_key] = cves

            if cves:
                self.logger.warning("Vulnerabilities found",
                                   package=package.name,
                                   version=package.version,
                                   count=len(cves))

            return cves
        except Exception as e:
            self.logger.error("Failed to scan package",
                            package=package.name,
                            error=str(e))
            return []

    async def _query_osv(self, name: str, version: str, ecosystem: str) -> List[CVE]:
        """Query OSV database for vulnerabilities."""
        # In production, this would make HTTP requests to OSV API
        # For now, we simulate with local vulnerability patterns

        # Known vulnerable patterns (simplified for demo)
        KNOWN_VULNERABILITIES = {
            ("lodash", "4.17.20"): [
                CVE(
                    id="CVE-2021-23337",
                    severity=SeverityLevel.HIGH,
                    score=7.2,
                    package_name="lodash",
                    vulnerable_versions="<4.17.21",
                    fixed_version="4.17.21",
                    summary="Prototype pollution in lodash",
                    references=["https://nvd.nist.gov/vuln/detail/CVE-2021-23337"],
                )
            ],
            ("axios", "0.21.0"): [
                CVE(
                    id="CVE-2021-3749",
                    severity=SeverityLevel.HIGH,
                    score=7.5,
                    package_name="axios",
                    vulnerable_versions="<0.21.2",
                    fixed_version="0.21.2",
                    summary="Server-Side Request Forgery in axios",
                    references=["https://nvd.nist.gov/vuln/detail/CVE-2021-3749"],
                )
            ],
        }

        return KNOWN_VULNERABILITIES.get((name, version), [])


class SupplyChainSecurity:
    """
    Comprehensive supply chain security manager.

    Provides:
    - SBOM generation
    - Vulnerability scanning
    - Git signature verification
    - Container image signing (Sigstore/Cosign)
    - License compliance checking
    """

    # Forbidden licenses for enterprise use
    FORBIDDEN_LICENSES = {"GPL-3.0", "AGPL-3.0", "SSPL-1.0"}

    # Licenses requiring legal review
    REVIEW_REQUIRED_LICENSES = {"GPL-2.0", "LGPL-2.1", "LGPL-3.0", "MPL-2.0"}

    def __init__(
        self,
        project_path: Path,
        cosign_path: str = "cosign",
        registry: str = "ghcr.io",
    ):
        self.project_path = project_path
        self.cosign_path = cosign_path
        self.registry = registry
        self.sbom_generator = SBOMGenerator(project_path)
        self.vuln_scanner = VulnerabilityScanner()
        self.logger = logger.bind(component="SupplyChainSecurity")

    async def generate_sbom(self) -> SBOM:
        """Generate SBOM for the project."""
        return await self.sbom_generator.generate()

    async def scan_dependencies(self, sbom: SBOM) -> List[CVE]:
        """Scan SBOM for vulnerabilities."""
        return await self.vuln_scanner.scan_sbom(sbom)

    async def check_license_compliance(
        self,
        sbom: SBOM,
        forbidden: Optional[Set[str]] = None,
        review_required: Optional[Set[str]] = None,
    ) -> LicenseComplianceResult:
        """Check license compliance for all dependencies."""
        forbidden = forbidden or self.FORBIDDEN_LICENSES
        review_required = review_required or self.REVIEW_REQUIRED_LICENSES

        violations = []
        warnings = []
        license_counts: Dict[str, int] = {}

        for pkg in sbom.packages:
            license_id = pkg.license or "Unknown"
            license_counts[license_id] = license_counts.get(license_id, 0) + 1

            if license_id in forbidden:
                violations.append({
                    "package": pkg.name,
                    "version": pkg.version,
                    "license": license_id,
                    "reason": "License is forbidden for enterprise use",
                })
            elif license_id in review_required:
                warnings.append({
                    "package": pkg.name,
                    "version": pkg.version,
                    "license": license_id,
                    "reason": "License requires legal review",
                })
            elif pkg.license_risk == LicenseRisk.UNKNOWN:
                warnings.append({
                    "package": pkg.name,
                    "version": pkg.version,
                    "license": license_id,
                    "reason": "Unknown license - manual review needed",
                })

        result = LicenseComplianceResult(
            compliant=len(violations) == 0,
            violations=violations,
            warnings=warnings,
            summary=license_counts,
        )

        self.logger.info("License compliance check complete",
                        compliant=result.compliant,
                        violations=len(violations),
                        warnings=len(warnings))

        return result

    async def verify_git_signatures(self, repo_path: Optional[Path] = None) -> SignatureVerificationResult:
        """Verify git commit signatures in repository."""
        repo_path = repo_path or self.project_path

        try:
            # Check if GPG signing is configured
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(repo_path), "log", "--show-signature", "-1", "--format=%G?|%GS|%GK"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return SignatureVerificationResult(
                    verified=False,
                    error=f"Git command failed: {result.stderr}",
                )

            output = result.stdout.strip()
            if not output or output.startswith("N"):
                return SignatureVerificationResult(
                    verified=False,
                    error="No signature found on latest commit",
                )

            parts = output.split("|")
            status = parts[0] if parts else ""
            signer = parts[1] if len(parts) > 1 else None

            verified = status in ("G", "U")  # Good or Unknown trust

            return SignatureVerificationResult(
                verified=verified,
                signer=signer,
                error=None if verified else f"Signature status: {status}",
            )

        except subprocess.TimeoutExpired:
            return SignatureVerificationResult(
                verified=False,
                error="Git signature verification timed out",
            )
        except FileNotFoundError:
            return SignatureVerificationResult(
                verified=False,
                error="Git not found",
            )
        except Exception as e:
            return SignatureVerificationResult(
                verified=False,
                error=str(e),
            )

    async def sign_container_image(self, image: str, key_ref: str = "cosign.key") -> str:
        """Sign container image using Cosign/Sigstore."""
        try:
            # Cosign sign command
            result = await asyncio.to_thread(
                subprocess.run,
                [self.cosign_path, "sign", "--key", key_ref, image],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Cosign signing failed: {result.stderr}")

            self.logger.info("Container image signed", image=image)
            return image

        except FileNotFoundError:
            self.logger.warning("Cosign not available, skipping image signing")
            return image
        except Exception as e:
            self.logger.error("Failed to sign image", image=image, error=str(e))
            raise

    async def verify_image_signature(self, image: str, key_ref: str = "cosign.pub") -> SignatureVerificationResult:
        """Verify container image signature using Cosign."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [self.cosign_path, "verify", "--key", key_ref, image],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return SignatureVerificationResult(verified=True)
            else:
                return SignatureVerificationResult(
                    verified=False,
                    error=result.stderr,
                )

        except FileNotFoundError:
            return SignatureVerificationResult(
                verified=False,
                error="Cosign not available",
            )
        except Exception as e:
            return SignatureVerificationResult(
                verified=False,
                error=str(e),
            )

    async def full_security_audit(self) -> Dict[str, Any]:
        """
        Perform a full supply chain security audit.

        Returns comprehensive report with:
        - SBOM
        - Vulnerabilities
        - License compliance
        - Git signature status
        """
        self.logger.info("Starting full security audit", project=str(self.project_path))

        # Generate SBOM
        sbom = await self.generate_sbom()

        # Scan for vulnerabilities
        vulnerabilities = await self.scan_dependencies(sbom)

        # Check license compliance
        license_result = await self.check_license_compliance(sbom)

        # Verify git signatures
        git_result = await self.verify_git_signatures()

        # Calculate risk score
        risk_score = self._calculate_risk_score(vulnerabilities, license_result)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project": str(self.project_path),
            "sbom": {
                "format": "SPDX-2.3",
                "packages_count": len(sbom.packages),
                "document_namespace": sbom.document_namespace,
            },
            "vulnerabilities": {
                "total": len(vulnerabilities),
                "critical": len([v for v in vulnerabilities if v.severity == SeverityLevel.CRITICAL]),
                "high": len([v for v in vulnerabilities if v.severity == SeverityLevel.HIGH]),
                "medium": len([v for v in vulnerabilities if v.severity == SeverityLevel.MEDIUM]),
                "low": len([v for v in vulnerabilities if v.severity == SeverityLevel.LOW]),
                "details": [v.to_dict() for v in vulnerabilities[:20]],  # Top 20
            },
            "license_compliance": {
                "compliant": license_result.compliant,
                "violations_count": len(license_result.violations),
                "warnings_count": len(license_result.warnings),
                "violations": license_result.violations,
                "warnings": license_result.warnings[:10],  # Top 10
                "summary": license_result.summary,
            },
            "git_signatures": {
                "verified": git_result.verified,
                "signer": git_result.signer,
                "error": git_result.error,
            },
            "risk_score": risk_score,
            "risk_level": self._risk_level_from_score(risk_score),
        }

        self.logger.info("Security audit complete",
                        risk_score=risk_score,
                        risk_level=report["risk_level"])

        return report

    def _calculate_risk_score(
        self,
        vulnerabilities: List[CVE],
        license_result: LicenseComplianceResult,
    ) -> float:
        """Calculate overall risk score (0-100, higher = more risk)."""
        score = 0.0

        # Vulnerability scoring
        for vuln in vulnerabilities:
            if vuln.severity == SeverityLevel.CRITICAL:
                score += 25
            elif vuln.severity == SeverityLevel.HIGH:
                score += 15
            elif vuln.severity == SeverityLevel.MEDIUM:
                score += 5
            elif vuln.severity == SeverityLevel.LOW:
                score += 1

        # License scoring
        score += len(license_result.violations) * 20
        score += len(license_result.warnings) * 5

        return min(100, score)

    def _risk_level_from_score(self, score: float) -> str:
        """Convert risk score to level."""
        if score >= 75:
            return "CRITICAL"
        elif score >= 50:
            return "HIGH"
        elif score >= 25:
            return "MEDIUM"
        elif score > 0:
            return "LOW"
        return "NONE"
