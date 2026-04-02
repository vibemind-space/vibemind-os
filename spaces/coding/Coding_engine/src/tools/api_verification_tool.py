"""
API Verification Tool - Verifies database state via API calls.

Used by E2EIntegrationTeamAgent to confirm CRUD operations worked:
- After CREATE: Verify record exists in list endpoint
- After UPDATE: Verify record has new values
- After DELETE: Verify record no longer exists

Works independently of UI to provide reliable verification.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class APIVerificationResult:
    """Result of a single API verification."""
    endpoint: str
    method: str
    status_code: int
    verification_passed: bool
    response_data: Optional[dict] = None
    expected_count: Optional[int] = None
    actual_count: Optional[int] = None
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "verification_passed": self.verification_passed,
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class CRUDVerificationResult:
    """Complete CRUD verification result."""
    entity: str
    create_verified: bool = False
    read_verified: bool = False
    update_verified: bool = False
    delete_verified: bool = False
    verifications: list[APIVerificationResult] = field(default_factory=list)

    @property
    def all_verified(self) -> bool:
        return all([
            self.create_verified,
            self.read_verified,
            self.update_verified,
            self.delete_verified,
        ])


# =============================================================================
# API Verification Tool
# =============================================================================

class APIVerificationTool:
    """
    Verifies database state by calling API endpoints directly.

    Used to confirm CRUD operations succeeded independent of UI state.

    Usage:
        tool = APIVerificationTool("http://localhost:8000")

        # After CREATE
        result = await tool.verify_create("/api/users", created_data, ["email"])

        # After UPDATE
        result = await tool.verify_update("/api/users/123", {"name": "New Name"})

        # After DELETE
        result = await tool.verify_delete("/api/users", "123")
    """

    DEFAULT_TIMEOUT = 10.0  # seconds

    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the API verification tool.

        Args:
            base_url: Base URL for API (e.g., "http://localhost:8000")
            auth_token: Optional auth token (JWT or Basic)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self.logger = logger.bind(component="api_verification_tool")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.auth_token:
                if self.auth_token.startswith("Basic "):
                    headers["Authorization"] = self.auth_token
                else:
                    headers["Authorization"] = f"Bearer {self.auth_token}"

            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
    ) -> tuple[int, Optional[dict], Optional[str]]:
        """
        Make an HTTP request.

        Returns:
            Tuple of (status_code, response_data, error_message)
        """
        url = f"{self.base_url}{endpoint}"

        try:
            session = await self._get_session()

            async with session.request(method, url, json=json_data) as response:
                status = response.status

                try:
                    data = await response.json()
                except Exception:
                    data = None

                return status, data, None

        except asyncio.TimeoutError:
            return 0, None, f"Request timeout ({self.timeout}s)"
        except aiohttp.ClientError as e:
            return 0, None, f"Client error: {str(e)}"
        except Exception as e:
            return 0, None, f"Request failed: {str(e)}"

    async def get_record_count(self, list_endpoint: str) -> int:
        """
        Get current record count from list endpoint.

        Args:
            list_endpoint: API endpoint for listing records

        Returns:
            Number of records, or -1 on error
        """
        status, data, error = await self._make_request("GET", list_endpoint)

        if error or status != 200:
            self.logger.debug(
                "count_request_failed",
                endpoint=list_endpoint,
                status=status,
                error=error,
            )
            return -1

        # Try to extract count from response
        if isinstance(data, list):
            return len(data)
        elif isinstance(data, dict):
            # Common patterns
            if "data" in data and isinstance(data["data"], list):
                return len(data["data"])
            if "items" in data and isinstance(data["items"], list):
                return len(data["items"])
            if "results" in data and isinstance(data["results"], list):
                return len(data["results"])
            if "total" in data:
                return int(data["total"])
            if "count" in data:
                return int(data["count"])

        return -1

    async def verify_create(
        self,
        list_endpoint: str,
        created_data: dict,
        match_fields: list[str],
    ) -> APIVerificationResult:
        """
        Verify a record was created.

        Args:
            list_endpoint: API endpoint for listing records (e.g., "/api/users")
            created_data: Data that was submitted in create form
            match_fields: Fields to match when finding the created record

        Returns:
            APIVerificationResult with verification status
        """
        start = datetime.now()

        status, data, error = await self._make_request("GET", list_endpoint)

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = APIVerificationResult(
            endpoint=list_endpoint,
            method="GET",
            status_code=status,
            verification_passed=False,
            response_data=data,
            duration_ms=duration,
            error=error,
        )

        if error or status != 200:
            return result

        # Extract records from response
        records = self._extract_records(data)

        if records is None:
            result.error = "Could not extract records from response"
            return result

        # Find matching record
        for record in records:
            if self._record_matches(record, created_data, match_fields):
                result.verification_passed = True
                self.logger.debug(
                    "create_verified",
                    endpoint=list_endpoint,
                    matched_fields=match_fields,
                )
                break

        if not result.verification_passed:
            result.error = f"No record matching {match_fields} found"

        return result

    async def verify_read(
        self,
        detail_endpoint: str,
        expected_values: Optional[dict] = None,
    ) -> APIVerificationResult:
        """
        Verify a record can be read.

        Args:
            detail_endpoint: API endpoint for single record (e.g., "/api/users/123")
            expected_values: Optional expected field values to verify

        Returns:
            APIVerificationResult with verification status
        """
        start = datetime.now()

        status, data, error = await self._make_request("GET", detail_endpoint)

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = APIVerificationResult(
            endpoint=detail_endpoint,
            method="GET",
            status_code=status,
            verification_passed=False,
            response_data=data,
            duration_ms=duration,
            error=error,
        )

        if error or status not in (200, 201):
            return result

        if data is None:
            result.error = "No data in response"
            return result

        # Extract record (may be wrapped in data field)
        record = data.get("data", data) if isinstance(data, dict) else data

        # If expected values provided, verify they match
        if expected_values:
            for key, expected in expected_values.items():
                actual = record.get(key) if isinstance(record, dict) else None
                if str(actual) != str(expected):
                    result.error = f"Field {key}: expected {expected}, got {actual}"
                    return result

        result.verification_passed = True
        return result

    async def verify_update(
        self,
        detail_endpoint: str,
        record_id: str,
        expected_values: dict,
    ) -> APIVerificationResult:
        """
        Verify a record was updated.

        Args:
            detail_endpoint: API endpoint template (e.g., "/api/users/:id")
            record_id: ID of the updated record
            expected_values: Expected field values after update

        Returns:
            APIVerificationResult with verification status
        """
        # Replace ID placeholder
        endpoint = detail_endpoint.replace(":id", record_id).replace("{id}", record_id)
        if record_id not in endpoint:
            endpoint = f"{detail_endpoint}/{record_id}"

        start = datetime.now()

        status, data, error = await self._make_request("GET", endpoint)

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = APIVerificationResult(
            endpoint=endpoint,
            method="GET",
            status_code=status,
            verification_passed=False,
            response_data=data,
            duration_ms=duration,
            error=error,
        )

        if error or status != 200:
            return result

        # Extract record
        record = data.get("data", data) if isinstance(data, dict) else data

        if not isinstance(record, dict):
            result.error = "Invalid record format"
            return result

        # Verify expected values
        mismatches = []
        for key, expected in expected_values.items():
            actual = record.get(key)
            if str(actual) != str(expected):
                mismatches.append(f"{key}: expected {expected}, got {actual}")

        if mismatches:
            result.error = f"Value mismatches: {', '.join(mismatches)}"
            return result

        result.verification_passed = True
        self.logger.debug(
            "update_verified",
            endpoint=endpoint,
            verified_fields=list(expected_values.keys()),
        )

        return result

    async def verify_delete(
        self,
        list_endpoint: str,
        deleted_id: str,
    ) -> APIVerificationResult:
        """
        Verify a record was deleted.

        Args:
            list_endpoint: API endpoint for listing records
            deleted_id: ID of the deleted record

        Returns:
            APIVerificationResult with verification status
        """
        start = datetime.now()

        status, data, error = await self._make_request("GET", list_endpoint)

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = APIVerificationResult(
            endpoint=list_endpoint,
            method="GET",
            status_code=status,
            verification_passed=False,
            response_data=data,
            duration_ms=duration,
            error=error,
        )

        if error or status != 200:
            return result

        # Extract records
        records = self._extract_records(data)

        if records is None:
            result.error = "Could not extract records from response"
            return result

        # Check that deleted ID is not in list
        for record in records:
            record_id = self._get_record_id(record)
            if str(record_id) == str(deleted_id):
                result.error = f"Record {deleted_id} still exists"
                return result

        result.verification_passed = True
        self.logger.debug(
            "delete_verified",
            endpoint=list_endpoint,
            deleted_id=deleted_id,
        )

        return result

    async def verify_detail_not_found(
        self,
        detail_endpoint: str,
        record_id: str,
    ) -> APIVerificationResult:
        """
        Verify a record returns 404 (alternative delete verification).

        Args:
            detail_endpoint: API endpoint template
            record_id: ID of the deleted record

        Returns:
            APIVerificationResult with verification status
        """
        endpoint = detail_endpoint.replace(":id", record_id).replace("{id}", record_id)
        if record_id not in endpoint:
            endpoint = f"{detail_endpoint}/{record_id}"

        start = datetime.now()

        status, data, error = await self._make_request("GET", endpoint)

        duration = int((datetime.now() - start).total_seconds() * 1000)

        result = APIVerificationResult(
            endpoint=endpoint,
            method="GET",
            status_code=status,
            verification_passed=status == 404,
            response_data=data,
            duration_ms=duration,
        )

        if status != 404:
            result.error = f"Expected 404, got {status}"

        return result

    def _extract_records(self, data: Any) -> Optional[list]:
        """Extract list of records from API response."""
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            # Common wrapper patterns
            for key in ("data", "items", "results", "records", "users", "orders", "products"):
                if key in data and isinstance(data[key], list):
                    return data[key]

        return None

    def _get_record_id(self, record: dict) -> Optional[str]:
        """Extract ID from a record."""
        for key in ("id", "_id", "ID", "Id"):
            if key in record:
                return str(record[key])
        return None

    def _record_matches(
        self,
        record: dict,
        expected: dict,
        match_fields: list[str],
    ) -> bool:
        """Check if a record matches expected values on specified fields."""
        for field in match_fields:
            expected_value = expected.get(field)
            actual_value = record.get(field)

            if expected_value is None:
                continue

            if str(actual_value) != str(expected_value):
                return False

        return True

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
