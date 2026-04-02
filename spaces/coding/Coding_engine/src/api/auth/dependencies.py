"""
FastAPI authentication dependencies.
"""

from functools import wraps
from typing import Callable, List, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.portal import TenantMember, TenantRole
from src.models.portal.base import get_db
from .jwt import (
    JWTManager,
    TokenData,
    TokenExpiredError,
    InvalidTokenError,
    get_jwt_manager,
)

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    jwt_manager: JWTManager = Depends(get_jwt_manager),
) -> TokenData:
    """
    Get current authenticated user from JWT token.

    Raises 401 if not authenticated.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token_data = jwt_manager.decode_token(credentials.credentials)

        if token_data.token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return token_data

    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    jwt_manager: JWTManager = Depends(get_jwt_manager),
) -> Optional[TokenData]:
    """
    Get current user if authenticated, None otherwise.

    Does not raise 401 for unauthenticated requests.
    """
    if not credentials:
        return None

    try:
        token_data = jwt_manager.decode_token(credentials.credentials)
        if token_data.token_type == "access":
            return token_data
        return None
    except (TokenExpiredError, InvalidTokenError):
        return None


async def get_current_tenant(
    request: Request,
    user: TokenData = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Get current tenant ID from header or user's default tenant.

    Validates that user has access to the tenant.
    """
    tenant_id = x_tenant_id

    # If no tenant specified, use first available
    if not tenant_id:
        if user.tenant_ids:
            tenant_id = user.tenant_ids[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No tenant specified and user has no tenants",
            )

    # Validate access
    if tenant_id not in user.tenant_ids:
        # Double-check in database in case token is stale
        result = await db.execute(
            select(TenantMember).where(
                TenantMember.user_id == user.user_id,
                TenantMember.tenant_id == tenant_id,
                TenantMember.is_active == True,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this tenant",
            )

    # Store tenant in request state for later use
    request.state.tenant_id = tenant_id
    return tenant_id


def require_role(allowed_roles: List[TenantRole]) -> Callable:
    """
    Decorator/dependency for requiring specific roles.

    Usage:
        @router.post("/admin")
        async def admin_endpoint(
            user: TokenData = Depends(require_role([TenantRole.OWNER, TenantRole.ADMIN]))
        ):
            ...
    """
    async def check_role(
        user: TokenData = Depends(get_current_user),
        tenant_id: str = Depends(get_current_tenant),
        db: AsyncSession = Depends(get_db),
    ) -> TokenData:
        # Check role from token
        user_role = user.roles.get(tenant_id)

        if user_role:
            try:
                role_enum = TenantRole(user_role)
                if role_enum in allowed_roles:
                    return user
            except ValueError:
                pass

        # Fallback to database check
        result = await db.execute(
            select(TenantMember).where(
                TenantMember.user_id == user.user_id,
                TenantMember.tenant_id == tenant_id,
                TenantMember.is_active == True,
            )
        )
        member = result.scalar_one_or_none()

        if not member or member.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {[r.value for r in allowed_roles]}",
            )

        return user

    return check_role


def require_admin():
    """Require OWNER or ADMIN role."""
    return require_role([TenantRole.OWNER, TenantRole.ADMIN])


def require_developer():
    """Require OWNER, ADMIN, or DEVELOPER role."""
    return require_role([TenantRole.OWNER, TenantRole.ADMIN, TenantRole.DEVELOPER])


class TenantContext:
    """
    Context manager for tenant-scoped operations.

    Sets PostgreSQL session variable for RLS.
    """

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def __aenter__(self):
        # Set tenant context for RLS
        await self.db.execute(
            f"SET app.current_tenant_id = '{self.tenant_id}'"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Reset tenant context
        await self.db.execute("RESET app.current_tenant_id")


async def get_tenant_context(
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """Get tenant context for RLS-enabled queries."""
    ctx = TenantContext(db, tenant_id)
    await ctx.__aenter__()
    return ctx
