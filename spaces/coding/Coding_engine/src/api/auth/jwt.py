"""
JWT token management.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt
import structlog

from src.secrets import get_secret

logger = structlog.get_logger()


@dataclass
class JWTConfig:
    """JWT configuration."""
    secret_key: str = field(default_factory=lambda: get_secret("jwt_secret_key", "change-me-in-production"))
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    issuer: str = "cell-colony"
    audience: str = "cell-colony-portal"


@dataclass
class TokenData:
    """Decoded token data."""
    user_id: str
    email: str
    name: Optional[str]
    avatar_url: Optional[str]
    tenant_ids: List[str]
    roles: Dict[str, str]  # tenant_id -> role
    exp: datetime
    iat: datetime
    token_type: str = "access"


class JWTManager:
    """Manages JWT token creation and validation."""

    def __init__(self, config: Optional[JWTConfig] = None):
        self.config = config or JWTConfig()
        self.logger = logger.bind(component="JWTManager")

    def create_access_token(
        self,
        user_id: str,
        email: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        tenant_ids: Optional[List[str]] = None,
        roles: Optional[Dict[str, str]] = None,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new access token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=self.config.access_token_expire_minutes)

        payload = {
            "sub": user_id,
            "email": email,
            "name": name,
            "avatar_url": avatar_url,
            "tenant_ids": tenant_ids or [],
            "roles": roles or {},
            "token_type": "access",
            "iat": now,
            "exp": expires,
            "iss": self.config.issuer,
            "aud": self.config.audience,
        }

        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm,
        )

        self.logger.debug("Created access token", user_id=user_id, expires=expires)
        return token

    def create_refresh_token(
        self,
        user_id: str,
        token_family: Optional[str] = None,
    ) -> str:
        """Create a refresh token for token renewal."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.config.refresh_token_expire_days)

        payload = {
            "sub": user_id,
            "token_type": "refresh",
            "token_family": token_family or user_id,  # For refresh token rotation
            "iat": now,
            "exp": expires,
            "iss": self.config.issuer,
            "aud": self.config.audience,
        }

        token = jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm,
        )

        self.logger.debug("Created refresh token", user_id=user_id, expires=expires)
        return token

    def decode_token(self, token: str, verify_exp: bool = True) -> TokenData:
        """Decode and validate a token."""
        try:
            options = {"verify_exp": verify_exp}
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                audience=self.config.audience,
                issuer=self.config.issuer,
                options=options,
            )

            return TokenData(
                user_id=payload["sub"],
                email=payload.get("email", ""),
                name=payload.get("name"),
                avatar_url=payload.get("avatar_url"),
                tenant_ids=payload.get("tenant_ids", []),
                roles=payload.get("roles", {}),
                exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
                iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
                token_type=payload.get("token_type", "access"),
            )

        except jwt.ExpiredSignatureError:
            self.logger.warning("Token expired")
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidAudienceError:
            self.logger.warning("Invalid audience")
            raise InvalidTokenError("Invalid token audience")
        except jwt.InvalidIssuerError:
            self.logger.warning("Invalid issuer")
            raise InvalidTokenError("Invalid token issuer")
        except jwt.PyJWTError as e:
            self.logger.warning("JWT decode error", error=str(e))
            raise InvalidTokenError(f"Invalid token: {str(e)}")

    def verify_refresh_token(self, token: str) -> Dict[str, Any]:
        """Verify a refresh token and return payload."""
        try:
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                audience=self.config.audience,
                issuer=self.config.issuer,
            )

            if payload.get("token_type") != "refresh":
                raise InvalidTokenError("Not a refresh token")

            return payload

        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Refresh token has expired")
        except jwt.PyJWTError as e:
            raise InvalidTokenError(f"Invalid refresh token: {str(e)}")

    def refresh_access_token(
        self,
        refresh_token: str,
        email: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        tenant_ids: Optional[List[str]] = None,
        roles: Optional[Dict[str, str]] = None,
    ) -> tuple:
        """
        Refresh access token using refresh token.

        Returns (new_access_token, new_refresh_token) for refresh token rotation.
        """
        payload = self.verify_refresh_token(refresh_token)
        user_id = payload["sub"]
        token_family = payload.get("token_family", user_id)

        # Create new tokens
        new_access = self.create_access_token(
            user_id=user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            tenant_ids=tenant_ids,
            roles=roles,
        )

        # Rotate refresh token
        new_refresh = self.create_refresh_token(
            user_id=user_id,
            token_family=token_family,
        )

        return new_access, new_refresh


class TokenExpiredError(Exception):
    """Raised when token has expired."""
    pass


class InvalidTokenError(Exception):
    """Raised when token is invalid."""
    pass


# Module-level singleton
_jwt_manager: Optional[JWTManager] = None


def get_jwt_manager() -> JWTManager:
    """Get or create JWT manager singleton."""
    global _jwt_manager
    if _jwt_manager is None:
        _jwt_manager = JWTManager()
    return _jwt_manager


def create_access_token(
    user_id: str,
    email: str,
    **kwargs,
) -> str:
    """Convenience function to create access token."""
    return get_jwt_manager().create_access_token(user_id, email, **kwargs)


def decode_access_token(token: str) -> TokenData:
    """Convenience function to decode access token."""
    return get_jwt_manager().decode_token(token)
