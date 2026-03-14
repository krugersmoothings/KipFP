"""Xero REST API connector — OAuth 2.0 authorization_code flow.

Credentials (refresh token, tenant ID) are stored Fernet-encrypted in
the ``api_credentials`` table keyed by service='xero'.
"""

import asyncio
import base64
import calendar
import hashlib
import logging
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_BASE = "https://api.xero.com"

MAX_RETRIES = 3


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from SECRET_KEY."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def encrypt_value(plaintext: str) -> str:
    f = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    f = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return f.decrypt(ciphertext.encode()).decode()


class XeroAuthError(Exception):
    """Raised when Xero OAuth credentials are invalid or missing."""


class XeroAPIError(Exception):
    """Raised for non-auth Xero API errors."""


class XeroClient:
    """Xero API client using OAuth 2.0 bearer tokens."""

    def __init__(self, access_token: str, tenant_id: str):
        self.access_token = access_token
        self.tenant_id = tenant_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Xero-Tenant-Id": self.tenant_id,
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{API_BASE}{path}"

        for attempt in range(MAX_RETRIES + 1):
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.request(
                    method, url, params=params, headers=self._headers(),
                )
            elapsed = time.monotonic() - t0

            logger.debug(
                "Xero %s %s → %s (%.2fs)", method, path, resp.status_code, elapsed,
            )

            if resp.status_code == 429 and attempt < MAX_RETRIES:
                retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    "Xero 429 rate-limit, retry %d/%d in %ds",
                    attempt + 1, MAX_RETRIES, retry_after,
                )
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code == 401:
                raise XeroAuthError(
                    f"Xero authentication failed ({resp.status_code}): {resp.text[:500]}"
                )

            if resp.status_code >= 400:
                raise XeroAPIError(
                    f"Xero API error {resp.status_code}: {resp.text[:500]}"
                )

            return resp

        raise XeroAPIError("Xero request failed: max retries exceeded (429)")

    @staticmethod
    def _normalize_account_name(raw_name: str) -> str:
        """Strip trailing Xero account code, e.g. 'Sales (200)' → 'Sales'."""
        import re
        return re.sub(r"\s*\(\d+\)\s*$", "", raw_name).strip()

    async def get_trial_balance_at_date(
        self,
        as_at: date,
    ) -> dict[str, dict[str, Any]]:
        """Fetch trial balance as at a specific date.

        Returns ``{normalised_name: {"raw": str, "amount": float, "id": str}}``.
        Amount is debit-positive (debit − credit).
        """
        resp = await self._request(
            "GET",
            "/api.xro/2.0/Reports/TrialBalance",
            params={"date": as_at.isoformat()},
        )
        data = resp.json()
        result: dict[str, dict[str, Any]] = {}

        for report in data.get("Reports", []):
            for section in report.get("Rows", []):
                if section.get("RowType") != "Section":
                    continue
                for row in section.get("Rows", []):
                    if row.get("RowType") != "Row":
                        continue
                    cells = row.get("Cells", [])
                    if len(cells) < 3:
                        continue
                    raw_name = cells[0].get("Value", "")
                    if not raw_name:
                        continue
                    account_id = ""
                    for attr in cells[0].get("Attributes", []):
                        if attr.get("Id") == "account" and "Value" in attr:
                            account_id = attr["Value"]
                    debit = float(cells[1].get("Value", "0") or "0")
                    credit = float(cells[2].get("Value", "0") or "0")
                    norm = self._normalize_account_name(raw_name)
                    result[norm] = {
                        "raw": raw_name,
                        "amount": debit - credit,
                        "id": account_id,
                    }

        logger.debug(
            "Xero TB as-at %s returned %d accounts", as_at.isoformat(), len(result),
        )
        return result

    async def get_monthly_activity(
        self,
        month_end: date,
        prev_month_end: date | None,
    ) -> list[dict[str, Any]]:
        """Compute monthly P&L/BS activity by differencing two TB snapshots.

        If *prev_month_end* is ``None`` (first month of FY), the current
        month-end TB is used directly as the activity.

        Returns rows compatible with the old ``get_trial_balance`` format:
        ``[{AccountID, AccountName, Debit, Credit}, ...]``
        """
        current = await self.get_trial_balance_at_date(month_end)

        if prev_month_end is not None:
            previous = await self.get_trial_balance_at_date(prev_month_end)
        else:
            previous = {}

        rows: list[dict[str, Any]] = []
        all_names = set(current.keys()) | set(previous.keys())
        for name in sorted(all_names):
            cur_amt = current.get(name, {}).get("amount", 0.0)
            prev_amt = previous.get(name, {}).get("amount", 0.0)
            activity = cur_amt - prev_amt
            account_id = current.get(name, previous.get(name, {})).get("id", "")

            if abs(activity) < 0.005:
                continue

            if activity >= 0:
                rows.append({
                    "AccountID": account_id,
                    "AccountName": name,
                    "Debit": activity,
                    "Credit": 0.0,
                })
            else:
                rows.append({
                    "AccountID": account_id,
                    "AccountName": name,
                    "Debit": 0.0,
                    "Credit": -activity,
                })

        logger.debug(
            "Xero monthly activity %s→%s: %d accounts with movement",
            prev_month_end, month_end, len(rows),
        )
        return rows

    async def get_trial_balance(
        self,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch monthly activity via two TB snapshots.

        Uses month-end differencing under the hood.  The first month of the
        Australian FY (July, i.e. ``from_date.month == 7``) uses the month-end
        TB directly; all other months diff against the previous month-end.
        """
        prev_month_end: date | None = None
        if from_date.day == 1:
            prev_last_day = from_date - timedelta(days=1)
            prev_month_end = prev_last_day

        return await self.get_monthly_activity(to_date, prev_month_end)

    async def get_accounts(self) -> list[dict[str, Any]]:
        """Fetch full chart of accounts."""
        resp = await self._request("GET", "/api.xro/2.0/Accounts")
        data = resp.json()
        return data.get("Accounts", [])


# ── OAuth 2.0 helpers (used by auth_xero.py) ─────────────────────────────


def build_authorize_url(state: str) -> str:
    """Build the Xero OAuth consent URL."""
    params = {
        "response_type": "code",
        "client_id": settings.XERO_CLIENT_ID,
        "redirect_uri": settings.XERO_REDIRECT_URI,
        "scope": "openid profile email offline_access accounting.reports.trialbalance.read accounting.reports.balancesheet.read accounting.settings.read accounting.contacts.read",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.XERO_REDIRECT_URI,
            },
            auth=(settings.XERO_CLIENT_ID, settings.XERO_CLIENT_SECRET),
        )
    if resp.status_code != 200:
        raise XeroAuthError(f"Token exchange failed: {resp.status_code} {resp.text[:500]}")
    return resp.json()


async def refresh_access_token(encrypted_refresh_token: str) -> dict[str, Any]:
    """Use a stored refresh token to get a new access token."""
    refresh_token = decrypt_value(encrypted_refresh_token)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(settings.XERO_CLIENT_ID, settings.XERO_CLIENT_SECRET),
        )
    if resp.status_code != 200:
        raise XeroAuthError(f"Token refresh failed: {resp.status_code} {resp.text[:500]}")
    return resp.json()


async def fetch_tenant_id(access_token: str) -> str:
    """Fetch the first Xero tenant (organisation) ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        raise XeroAuthError(f"Failed to fetch Xero tenants: {resp.text[:500]}")
    connections = resp.json()
    if not connections:
        raise XeroAuthError("No Xero tenants/organisations found for this user")
    return connections[0]["tenantId"]


async def get_authenticated_client() -> XeroClient:
    """Build an authenticated XeroClient from stored credentials.

    Refreshes the access token automatically using the stored refresh token.
    """
    from sqlalchemy import select
    from app.db.base import async_session_factory
    from app.db.models.credential import ApiCredential

    async with async_session_factory() as db:
        result = await db.execute(
            select(ApiCredential).where(
                ApiCredential.service == "xero",
                ApiCredential.credential_key == "refresh_token",
            )
        )
        refresh_row = result.scalar_one_or_none()
        if not refresh_row:
            raise XeroAuthError("No Xero refresh token stored — connect via /auth/xero/connect first")

        result = await db.execute(
            select(ApiCredential).where(
                ApiCredential.service == "xero",
                ApiCredential.credential_key == "tenant_id",
            )
        )
        tenant_row = result.scalar_one_or_none()
        if not tenant_row:
            raise XeroAuthError("No Xero tenant ID stored — reconnect via /auth/xero/connect")

        tenant_id = decrypt_value(tenant_row.credential_value)

        tokens = await refresh_access_token(refresh_row.credential_value)

        refresh_row.credential_value = encrypt_value(tokens["refresh_token"])
        await db.commit()

    return XeroClient(
        access_token=tokens["access_token"],
        tenant_id=tenant_id,
    )
