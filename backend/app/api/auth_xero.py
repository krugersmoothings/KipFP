import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.xero import (
    build_authorize_url,
    encrypt_value,
    exchange_code,
    fetch_tenant_id,
)
from app.core.deps import get_db, require_admin
from app.db.models.credential import ApiCredential
from app.db.models.user import User

router = APIRouter(prefix="/auth/xero", tags=["xero-auth"])

_STATE_TTL_SECONDS = 600
_oauth_states: dict[str, float] = {}


def _purge_expired_states() -> None:
    cutoff = time.monotonic() - _STATE_TTL_SECONDS
    expired = [k for k, ts in _oauth_states.items() if ts < cutoff]
    for k in expired:
        _oauth_states.pop(k, None)


@router.get("/connect")
async def xero_connect(
    _user: User = Depends(require_admin),
):
    """Redirect admin to Xero OAuth consent screen."""
    _purge_expired_states()
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.monotonic()
    url = build_authorize_url(state)
    return RedirectResponse(url)


@router.get("/callback")
async def xero_callback(
    code: str = Query(...),
    # FIX(C6): state was optional+empty-default, allowing CSRF bypass
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
    # FIX(C7): callback had no auth — anyone could overwrite Xero credentials
    _user: User = Depends(require_admin),
):
    """Handle Xero OAuth callback — store refresh token and tenant ID."""
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _oauth_states.pop(state, None)

    tokens = await exchange_code(code)
    # FIX(M14): handle missing keys in token exchange response
    if "access_token" not in tokens or "refresh_token" not in tokens:
        error_desc = tokens.get("error_description", tokens.get("error", "Unknown OAuth error"))
        raise HTTPException(status_code=502, detail=f"Xero token exchange failed: {error_desc}")
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    tenant_id = await fetch_tenant_id(access_token)

    await _upsert_credential(db, "xero", "refresh_token", encrypt_value(refresh_token))
    await _upsert_credential(db, "xero", "tenant_id", encrypt_value(tenant_id))

    await db.commit()
    # FIX(L28): don't leak tenant_id to the response
    return {"status": "connected"}


async def _upsert_credential(
    db: AsyncSession, service: str, key: str, value: str
) -> None:
    result = await db.execute(
        select(ApiCredential).where(
            ApiCredential.service == service,
            ApiCredential.credential_key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.credential_value = value
    else:
        db.add(ApiCredential(
            service=service,
            credential_key=key,
            credential_value=value,
        ))
