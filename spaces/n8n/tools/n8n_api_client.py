"""
n8n REST API Client

Communicates with a running n8n instance via REST API.
Auth: X-N8N-API-KEY header (public API) with cookie-based fallback.
Docs: https://docs.n8n.io/api/
"""

import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class N8nApiClient:
    """REST API client for n8n workflow automation platform."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("N8N_API_URL", "http://localhost:15678")).rstrip("/")
        self.api_key = api_key or os.getenv("N8N_API_KEY", "")
        self._auth_token: Optional[str] = None

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["X-N8N-API-KEY"] = self.api_key
        elif self._auth_token:
            h["Cookie"] = f"n8n-auth={self._auth_token}"
        return h

    @property
    def _api_prefix(self) -> str:
        """API key uses /api/v1, cookie auth uses /rest."""
        return "/api/v1" if self.api_key else "/rest"

    def _ensure_auth(self):
        """Login via cookie if no API key configured."""
        if self._auth_token or self.api_key:
            return
        try:
            resp = requests.post(
                f"{self.base_url}/rest/login",
                json={
                    "emailOrLdapLoginId": os.getenv("N8N_OWNER_EMAIL", "admin@vibemind.local"),
                    "password": os.getenv("N8N_OWNER_PASSWORD", "Vibemind1"),
                },
                timeout=5,
            )
            if resp.ok:
                for raw in resp.headers.get("Set-Cookie", "").split(","):
                    if "n8n-auth=" in raw:
                        self._auth_token = raw.split("n8n-auth=")[1].split(";")[0].strip()
                        logger.info("n8n cookie auth successful")
                        return
            else:
                logger.warning(f"n8n login failed: {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"n8n login error: {e}")

    # ── HTTP Methods ─────────────────────────────────────────────────────

    def _get(self, path: str) -> Dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_url}{self._api_prefix}{path}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"n8n GET {path} failed: {e}")
            return {"error": str(e)}

    def _post(self, path: str, data: Dict = None) -> Dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_url}{self._api_prefix}{path}"
        try:
            resp = requests.post(url, headers=self._headers(), json=data or {}, timeout=30)
            if not resp.ok:
                body = resp.text[:500]
                logger.error(f"n8n POST {path} failed ({resp.status_code}): {body}")
                return {"error": f"{resp.status_code}: {body}"}
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"n8n POST {path} failed: {e}")
            return {"error": str(e)}

    def _patch(self, path: str, data: Dict = None) -> Dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_url}{self._api_prefix}{path}"
        try:
            resp = requests.patch(url, headers=self._headers(), json=data or {}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"n8n PATCH {path} failed: {e}")
            return {"error": str(e)}

    def _delete(self, path: str) -> Dict[str, Any]:
        self._ensure_auth()
        url = f"{self.base_url}{self._api_prefix}{path}"
        try:
            resp = requests.delete(url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json() if resp.text else {"success": True}
        except requests.RequestException as e:
            logger.error(f"n8n DELETE {path} failed: {e}")
            return {"error": str(e)}

    # ── Workflow Operations ───────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        try:
            resp = requests.get(f"{self.base_url}/healthz", timeout=5)
            return {"online": resp.status_code == 200, "url": self.base_url, "status_code": resp.status_code}
        except requests.RequestException as e:
            return {"online": False, "url": self.base_url, "error": str(e)}

    def list_workflows(self) -> List[Dict[str, Any]]:
        result = self._get("/workflows")
        if "error" in result:
            return []
        return result.get("data", result if isinstance(result, list) else [])

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return self._get(f"/workflows/{workflow_id}")

    def create_workflow(self, workflow_json: Dict[str, Any]) -> Dict[str, Any]:
        return self._post("/workflows", workflow_json)

    def update_workflow(self, workflow_id: str, workflow_json: Dict[str, Any]) -> Dict[str, Any]:
        return self._patch(f"/workflows/{workflow_id}", workflow_json)

    def delete_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return self._delete(f"/workflows/{workflow_id}")

    def activate_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return self._patch(f"/workflows/{workflow_id}", {"active": True})

    def deactivate_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return self._patch(f"/workflows/{workflow_id}", {"active": False})

    def execute_workflow(self, workflow_id: str, data: Dict = None) -> Dict[str, Any]:
        return self._post(f"/workflows/{workflow_id}/run", data or {})

    def get_executions(self, workflow_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
        path = "/executions"
        if workflow_id:
            path += f"?workflowId={workflow_id}&limit={limit}"
        else:
            path += f"?limit={limit}"
        result = self._get(path)
        if "error" in result:
            return []
        return result.get("data", result if isinstance(result, list) else [])


# Singleton
_client: Optional[N8nApiClient] = None


def get_n8n_client() -> N8nApiClient:
    global _client
    if _client is None:
        _client = N8nApiClient()
    return _client


__all__ = ["N8nApiClient", "get_n8n_client"]
