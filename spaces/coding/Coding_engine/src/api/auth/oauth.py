"""
OAuth2 provider implementations.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlencode

import httpx
import structlog

from src.secrets import get_secret

logger = structlog.get_logger()


@dataclass
class OAuthUserInfo:
    """User information from OAuth provider."""
    provider: str
    provider_user_id: str
    email: str
    name: Optional[str]
    avatar_url: Optional[str]
    raw_data: dict


@dataclass
class OAuthConfig:
    """OAuth provider configuration."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list


class OAuthProvider(ABC):
    """Base class for OAuth providers."""

    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str

    def __init__(self, config: OAuthConfig):
        self.config = config
        self.logger = logger.bind(provider=self.name)

    def get_authorization_url(self, state: str) -> str:
        """Generate OAuth authorization URL."""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": state,
            "response_type": "code",
        }
        params.update(self._extra_auth_params())
        return f"{self.authorize_url}?{urlencode(params)}"

    def _extra_auth_params(self) -> dict:
        """Override to add provider-specific auth params."""
        return {}

    async def exchange_code(self, code: str) -> Dict:
        """Exchange authorization code for tokens."""
        self.logger.debug("Exchanging code for tokens")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code": code,
                    "redirect_uri": self.config.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user information from provider."""
        pass


class GitHubOAuth(OAuthProvider):
    """GitHub OAuth provider."""

    name = "github"
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    userinfo_url = "https://api.github.com/user"
    emails_url = "https://api.github.com/user/emails"

    def __init__(self, config: Optional[OAuthConfig] = None):
        if config is None:
            config = OAuthConfig(
                client_id=os.environ.get("GITHUB_CLIENT_ID", ""),
                client_secret=get_secret("github_client_secret"),
                redirect_uri=os.environ.get("GITHUB_REDIRECT_URI", "http://localhost:8000/auth/github/callback"),
                scopes=["read:user", "user:email"],
            )
        super().__init__(config)

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user info from GitHub."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            # Get user profile
            response = await client.get(self.userinfo_url, headers=headers)
            response.raise_for_status()
            user_data = response.json()

            # Get primary email if not public
            email = user_data.get("email")
            if not email:
                emails_response = await client.get(self.emails_url, headers=headers)
                emails_response.raise_for_status()
                emails = emails_response.json()

                # Find primary email
                for e in emails:
                    if e.get("primary") and e.get("verified"):
                        email = e["email"]
                        break

            return OAuthUserInfo(
                provider=self.name,
                provider_user_id=str(user_data["id"]),
                email=email or "",
                name=user_data.get("name") or user_data.get("login"),
                avatar_url=user_data.get("avatar_url"),
                raw_data=user_data,
            )


class GoogleOAuth(OAuthProvider):
    """Google OAuth provider."""

    name = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self, config: Optional[OAuthConfig] = None):
        if config is None:
            config = OAuthConfig(
                client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
                client_secret=get_secret("google_client_secret"),
                redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"),
                scopes=["openid", "email", "profile"],
            )
        super().__init__(config)

    def _extra_auth_params(self) -> dict:
        return {"access_type": "offline", "prompt": "consent"}

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Get user info from Google."""
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(self.userinfo_url, headers=headers)
            response.raise_for_status()
            user_data = response.json()

            return OAuthUserInfo(
                provider=self.name,
                provider_user_id=user_data["id"],
                email=user_data["email"],
                name=user_data.get("name"),
                avatar_url=user_data.get("picture"),
                raw_data=user_data,
            )


class OAuthManager:
    """Manages multiple OAuth providers."""

    def __init__(self):
        self.providers: Dict[str, OAuthProvider] = {}
        self.logger = logger.bind(component="OAuthManager")

    def register_provider(self, provider: OAuthProvider) -> None:
        """Register an OAuth provider."""
        self.providers[provider.name] = provider
        self.logger.info("Registered OAuth provider", provider=provider.name)

    def get_provider(self, name: str) -> Optional[OAuthProvider]:
        """Get provider by name."""
        return self.providers.get(name)

    def list_providers(self) -> list:
        """List available providers."""
        return list(self.providers.keys())

    @classmethod
    def create_default(cls) -> "OAuthManager":
        """Create manager with default providers."""
        manager = cls()

        # Register GitHub if configured
        if os.environ.get("GITHUB_CLIENT_ID"):
            manager.register_provider(GitHubOAuth())

        # Register Google if configured
        if os.environ.get("GOOGLE_CLIENT_ID"):
            manager.register_provider(GoogleOAuth())

        return manager
