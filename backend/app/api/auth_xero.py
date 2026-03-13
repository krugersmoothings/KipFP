import secrets

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

_oauth_states: dict[str, bool] = {}


@router.get("/connect")
async def xero_connect(
    _user: User = Depends(require_admin),
):
    """Redirect admin to Xero OAuth consent screen."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = True
    url = build_authorize_url(state)
    return RedirectResponse(url)


@router.get("/callback")
async def xero_callback(
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Handle Xero OAuth callback — store refresh token and tenant ID."""
    if state and state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _oauth_states.pop(state, None)

    tokens = await exchange_code(code)
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    tenant_id = await fetch_tenant_id(access_token)

    await _upsert_credential(db, "xero", "refresh_token", encrypt_value(refresh_token))
    await _upsert_credential(db, "xero", "tenant_id", encrypt_value(tenant_id))

    await db.commit()
    return {"status": "connected", "tenant_id": tenant_id}


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
