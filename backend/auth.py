"""Supabase JWT verification for FastAPI using JWKS (ECC P-256).

If SUPABASE_URL is not set, auth is disabled (dev mode).
"""
import os
from typing import Optional

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
AUTH_ENABLED = bool(SUPABASE_URL)

_jwks_client = None

if AUTH_ENABLED:
    import jwt as pyjwt
    from jwt import PyJWKClient

    _jwks_client = PyJWKClient(
        f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        lifespan=3600,
    )

security = HTTPBearer(auto_error=False)

DEV_USER = {"user_id": "dev-user", "email": "dev@local"}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Decode and verify Supabase JWT via JWKS.

    If SUPABASE_URL is not set, returns a dev user (no auth required).
    """
    if not AUTH_ENABLED:
        return DEV_USER

    if not credentials:
        raise HTTPException(401, "Authentication required")

    token = credentials.credentials
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token: missing sub claim")
        return {"user_id": user_id, "email": payload.get("email", "")}
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(401, f"Auth error: {e}")
