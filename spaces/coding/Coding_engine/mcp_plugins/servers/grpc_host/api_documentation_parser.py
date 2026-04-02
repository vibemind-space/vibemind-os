#!/usr/bin/env python3
"""
API Documentation Parser - Phase 3.5

Parst api_documentation.md und extrahiert alle API Endpoints mit Details.

Features:
- Parst alle 359 Endpoints aus api_documentation.md
- Extrahiert Method, Path, Parameters, Responses, Requirement-Links
- Gruppiert Endpoints nach Resource/Tag
- Generiert API-spezifische Tasks
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class HTTPMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass
class APIParameter:
    """API Parameter (path, query, body)"""
    name: str
    location: str  # path, query, body
    type: str  # string, integer, boolean, etc.
    required: bool
    description: str = ""


@dataclass
class APIResponse:
    """API Response definition"""
    status_code: int
    description: str


@dataclass
class APIEndpoint:
    """Single API Endpoint"""
    method: str
    path: str
    summary: str
    description: str
    requirement: str  # WA-XXX-NNN
    parameters: List[APIParameter] = field(default_factory=list)
    responses: List[APIResponse] = field(default_factory=list)
    request_body: Optional[str] = None  # DTO name
    tags: List[str] = field(default_factory=list)  # Resource tags

    @property
    def safe_id(self) -> str:
        """Generate safe ID for task creation"""
        return self.path.replace("/", "_").replace("{", "").replace("}", "").strip("_")

    @property
    def resource(self) -> str:
        """Extract resource name from path"""
        parts = self.path.split("/")
        # Skip /api/v1/ prefix and get first meaningful segment
        for part in parts:
            if part and part not in ["api", "v1", ""]:
                return part.replace("{", "").replace("}", "")
        return "unknown"


class APIDocumentationParser:
    """
    Parst api_documentation.md und extrahiert alle Endpoints.

    Format des Markdown:
    ### ResourceName

    #### `METHOD` /path/to/endpoint

    **Summary**

    Description text

    *Requirement:* WA-XXX-NNN

    **Parameters:**
    | Name | In | Type | Required | Description |

    **Request Body:** `DTOName`

    **Responses:**
    - `200`: Success
    """

    # Regex patterns
    RESOURCE_PATTERN = r"^### ([A-Za-z][A-Za-z0-9_]+)$"
    ENDPOINT_PATTERN = r"^####\s+`?(GET|POST|PUT|DELETE|PATCH)`?\s+(/[^\s]+)"
    SUMMARY_PATTERN = r"^\*\*([^*]+)\*\*$"
    REQUIREMENT_PATTERN = r"\*Requirement:\*\s+(WA-[A-Z]+-\d{3})"
    PARAM_ROW_PATTERN = r"\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(True|False)\s*\|\s*([^|]*)\s*\|"
    REQUEST_BODY_PATTERN = r"\*\*Request Body:\*\*\s+`?([A-Za-z][A-Za-z0-9_]+)`?"
    RESPONSE_PATTERN = r"-\s+`?(\d{3})`?:\s*(.+)"

    def __init__(self, project_path: str):
        """
        Args:
            project_path: Path to the input project
        """
        self.project_path = Path(project_path)
        self.api_doc_path = self.project_path / "api" / "api_documentation.md"

        # Caches
        self._endpoints: List[APIEndpoint] = []
        self._requirement_to_endpoints: Dict[str, List[APIEndpoint]] = {}
        self._resource_to_endpoints: Dict[str, List[APIEndpoint]] = {}
        self._parsed = False

        logger.info(f"APIDocumentationParser initialized for: {project_path}")

    def parse_all_endpoints(self) -> List[APIEndpoint]:
        """
        Parse all endpoints from api_documentation.md.

        Returns:
            List of APIEndpoint objects
        """
        if self._parsed:
            return self._endpoints

        if not self.api_doc_path.exists():
            logger.warning(f"api_documentation.md not found at {self.api_doc_path}")
            return []

        content = self.api_doc_path.read_text(encoding="utf-8")
        self._endpoints = self._parse_endpoints_from_content(content)
        self._build_indexes()
        self._parsed = True

        logger.info(f"Parsed {len(self._endpoints)} API endpoints")
        return self._endpoints

    def _parse_endpoints_from_content(self, content: str) -> List[APIEndpoint]:
        """Parse endpoint blocks from markdown content"""
        endpoints = []
        lines = content.split('\n')

        current_resource = None
        current_endpoint = None
        current_section = None  # 'description', 'parameters', 'responses'
        param_header_found = False

        for i, line in enumerate(lines):
            # Check for resource header
            resource_match = re.match(self.RESOURCE_PATTERN, line)
            if resource_match:
                current_resource = resource_match.group(1)
                continue

            # Check for endpoint header
            endpoint_match = re.match(self.ENDPOINT_PATTERN, line)
            if endpoint_match:
                # Save previous endpoint
                if current_endpoint:
                    endpoints.append(current_endpoint)

                method = endpoint_match.group(1)
                path = endpoint_match.group(2)

                current_endpoint = APIEndpoint(
                    method=method,
                    path=path,
                    summary="",
                    description="",
                    requirement="",
                    tags=[current_resource] if current_resource else []
                )
                current_section = "description"
                param_header_found = False
                continue

            if not current_endpoint:
                continue

            # Check for summary (bold text after endpoint)
            if current_section == "description" and not current_endpoint.summary:
                summary_match = re.match(self.SUMMARY_PATTERN, line)
                if summary_match:
                    current_endpoint.summary = summary_match.group(1).strip()
                    continue

            # Check for requirement
            req_match = re.search(self.REQUIREMENT_PATTERN, line)
            if req_match:
                current_endpoint.requirement = req_match.group(1)
                continue

            # Check for section changes
            if line.startswith("**Parameters:**"):
                current_section = "parameters"
                param_header_found = False
                continue
            elif line.startswith("**Responses:**"):
                current_section = "responses"
                continue
            elif line.startswith("**Request Body:**"):
                body_match = re.search(self.REQUEST_BODY_PATTERN, line)
                if body_match:
                    current_endpoint.request_body = body_match.group(1)
                continue
            elif line.startswith("---"):
                # Section separator
                if current_endpoint:
                    endpoints.append(current_endpoint)
                    current_endpoint = None
                current_section = None
                continue

            # Parse parameters table
            if current_section == "parameters":
                # Skip header row
                if "|---" in line:
                    param_header_found = True
                    continue
                if "| Name |" in line:
                    continue

                if param_header_found:
                    param_match = re.match(self.PARAM_ROW_PATTERN, line)
                    if param_match:
                        current_endpoint.parameters.append(APIParameter(
                            name=param_match.group(1).strip(),
                            location=param_match.group(2).strip(),
                            type=param_match.group(3).strip(),
                            required=param_match.group(4).strip().lower() == "true",
                            description=param_match.group(5).strip()
                        ))

            # Parse responses
            elif current_section == "responses":
                resp_match = re.match(self.RESPONSE_PATTERN, line)
                if resp_match:
                    current_endpoint.responses.append(APIResponse(
                        status_code=int(resp_match.group(1)),
                        description=resp_match.group(2).strip()
                    ))

            # Collect description text
            elif current_section == "description" and line.strip() and not line.startswith("*"):
                if current_endpoint.description:
                    current_endpoint.description += " " + line.strip()
                else:
                    current_endpoint.description = line.strip()

        # Don't forget the last endpoint
        if current_endpoint:
            endpoints.append(current_endpoint)

        return endpoints

    def _build_indexes(self):
        """Build lookup indexes for fast access"""
        self._requirement_to_endpoints = {}
        self._resource_to_endpoints = {}

        for endpoint in self._endpoints:
            # Index by requirement
            if endpoint.requirement:
                if endpoint.requirement not in self._requirement_to_endpoints:
                    self._requirement_to_endpoints[endpoint.requirement] = []
                self._requirement_to_endpoints[endpoint.requirement].append(endpoint)

            # Index by resource
            resource = endpoint.resource
            if resource not in self._resource_to_endpoints:
                self._resource_to_endpoints[resource] = []
            self._resource_to_endpoints[resource].append(endpoint)

    def get_endpoints_by_requirement(self, req_id: str) -> List[APIEndpoint]:
        """
        Get all endpoints for a specific requirement.

        Args:
            req_id: Requirement ID (e.g., "WA-AUTH-001")

        Returns:
            List of matching endpoints
        """
        if not self._parsed:
            self.parse_all_endpoints()

        return self._requirement_to_endpoints.get(req_id, [])

    def get_endpoints_by_resource(self, resource: str) -> List[APIEndpoint]:
        """
        Get all endpoints for a specific resource.

        Args:
            resource: Resource name (e.g., "users", "auth")

        Returns:
            List of matching endpoints
        """
        if not self._parsed:
            self.parse_all_endpoints()

        return self._resource_to_endpoints.get(resource, [])

    def get_all_requirements(self) -> Set[str]:
        """Get all unique requirement IDs referenced in API docs"""
        if not self._parsed:
            self.parse_all_endpoints()

        return set(self._requirement_to_endpoints.keys())

    def get_all_resources(self) -> Set[str]:
        """Get all unique resource names"""
        if not self._parsed:
            self.parse_all_endpoints()

        return set(self._resource_to_endpoints.keys())

    def get_endpoints_summary(self) -> Dict[str, Any]:
        """Get summary statistics of parsed endpoints"""
        if not self._parsed:
            self.parse_all_endpoints()

        method_counts = {}
        for endpoint in self._endpoints:
            method_counts[endpoint.method] = method_counts.get(endpoint.method, 0) + 1

        return {
            "total_endpoints": len(self._endpoints),
            "total_requirements": len(self._requirement_to_endpoints),
            "total_resources": len(self._resource_to_endpoints),
            "methods": method_counts,
            "resources": list(self._resource_to_endpoints.keys())
        }

    def to_json(self, output_path: Optional[str] = None) -> str:
        """
        Export parsed endpoints to JSON.

        Args:
            output_path: Optional path to save JSON file

        Returns:
            JSON string
        """
        if not self._parsed:
            self.parse_all_endpoints()

        def to_dict(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return {k: to_dict(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, list):
                return [to_dict(item) for item in obj]
            return obj

        data = {
            "summary": self.get_endpoints_summary(),
            "endpoints": [to_dict(e) for e in self._endpoints]
        }

        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        if output_path:
            Path(output_path).write_text(json_str, encoding="utf-8")
            logger.info(f"Saved API endpoints to: {output_path}")

        return json_str


# =============================================================================
# Test
# =============================================================================

def test_api_documentation_parser():
    """Test the APIDocumentationParser"""
    print("=== API Documentation Parser Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    parser = APIDocumentationParser(str(test_path))

    # Test 1: Parse all endpoints
    print("1. Parsing all endpoints:")
    endpoints = parser.parse_all_endpoints()
    print(f"   Found {len(endpoints)} endpoints")

    # Test 2: Get summary
    print("\n2. Summary:")
    summary = parser.get_endpoints_summary()
    print(f"   Total: {summary['total_endpoints']} endpoints")
    print(f"   Requirements: {summary['total_requirements']}")
    print(f"   Resources: {summary['total_resources']}")
    print(f"   Methods: {summary['methods']}")

    # Test 3: Show first 5 endpoints
    print("\n3. First 5 endpoints:")
    for ep in endpoints[:5]:
        print(f"\n   {ep.method} {ep.path}")
        print(f"      Summary: {ep.summary[:50]}..." if len(ep.summary) > 50 else f"      Summary: {ep.summary}")
        print(f"      Requirement: {ep.requirement}")
        print(f"      Parameters: {len(ep.parameters)}")
        print(f"      Responses: {[r.status_code for r in ep.responses]}")

    # Test 4: Get endpoints by requirement
    print("\n4. Endpoints for WA-AUTH-001:")
    auth_endpoints = parser.get_endpoints_by_requirement("WA-AUTH-001")
    print(f"   Found {len(auth_endpoints)} endpoints")
    for ep in auth_endpoints[:3]:
        print(f"      {ep.method} {ep.path}")

    # Test 5: Get all requirements
    print("\n5. All unique requirements:")
    requirements = parser.get_all_requirements()
    print(f"   Found {len(requirements)} unique requirements")
    print(f"   Sample: {list(requirements)[:10]}")

    # Test 6: Get endpoints by resource
    print("\n6. Endpoints for 'users' resource:")
    user_endpoints = parser.get_endpoints_by_resource("users")
    print(f"   Found {len(user_endpoints)} endpoints")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_api_documentation_parser()
