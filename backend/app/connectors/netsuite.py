"""NetSuite REST connector — Token-Based Authentication (OAuth 1.0a, HMAC-SHA256).

Reads credentials from environment variables via app.core.config.settings:
    NETSUITE_ACCOUNT_ID, NETSUITE_CONSUMER_KEY, NETSUITE_CONSUMER_SECRET,
    NETSUITE_TOKEN_KEY, NETSUITE_TOKEN_SECRET

Base URL: https://{ACCOUNT_ID}.suitetalk.api.netsuite.com
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
import time
import urllib.parse
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class NetSuiteAuthError(Exception):
    """Raised when TBA credentials are invalid or missing."""


class NetSuiteAPIError(Exception):
    """Raised for non-auth NetSuite API errors."""


class NetSuiteClient:
    """NetSuite REST / SuiteQL client using OAuth 1.0a Token-Based Authentication.

    All public methods are async and safe to call from FastAPI handlers or from
    Celery tasks wrapped in ``asyncio.run()``.
    """

    SIGNATURE_METHOD = "HMAC-SHA256"
    OAUTH_VERSION = "1.0"

    def __init__(
        self,
        account_id: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        token_key: str | None = None,
        token_secret: str | None = None,
    ):
        self.account_id = account_id or settings.NETSUITE_ACCOUNT_ID
        self.consumer_key = consumer_key or settings.NETSUITE_CONSUMER_KEY
        self.consumer_secret = consumer_secret or settings.NETSUITE_CONSUMER_SECRET
        self.token_key = token_key or settings.NETSUITE_TOKEN_KEY
        self.token_secret = token_secret or settings.NETSUITE_TOKEN_SECRET

        if not all([
            self.account_id,
            self.consumer_key,
            self.consumer_secret,
            self.token_key,
            self.token_secret,
        ]):
            raise NetSuiteAuthError(
                "Missing NetSuite TBA credentials — set NETSUITE_ACCOUNT_ID, "
                "NETSUITE_CONSUMER_KEY, NETSUITE_CONSUMER_SECRET, "
                "NETSUITE_TOKEN_KEY, NETSUITE_TOKEN_SECRET in .env"
            )

        # URL-safe account id: lowercase, underscores → hyphens
        url_account = self.account_id.lower().replace("_", "-")
        self.base_url = f"https://{url_account}.suitetalk.api.netsuite.com"
        # Realm uses the raw account id (uppercase, underscores)
        self.realm = self.account_id.upper().replace("-", "_")

    # ── OAuth 1.0a signing ───────────────────────────────────────────────

    @staticmethod
    def _pct(value: str) -> str:
        """RFC 5849 percent-encoding (unreserved chars only)."""
        return urllib.parse.quote(str(value), safe="")

    def _build_auth_header(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
    ) -> str:
        """Build the ``Authorization: OAuth …`` header with HMAC-SHA256 signature."""
        nonce = secrets.token_hex(16)
        timestamp = str(int(time.time()))

        oauth_params: dict[str, str] = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": nonce,
            "oauth_signature_method": self.SIGNATURE_METHOD,
            "oauth_timestamp": timestamp,
            "oauth_token": self.token_key,
            "oauth_version": self.OAUTH_VERSION,
        }

        # Signature base string = OAuth params + URL query params (NOT body)
        sig_params = {**oauth_params}
        if params:
            sig_params.update(params)

        param_string = "&".join(
            f"{self._pct(k)}={self._pct(v)}"
            for k, v in sorted(sig_params.items())
        )

        base_string = "&".join([
            method.upper(),
            self._pct(url),
            self._pct(param_string),
        ])

        signing_key = (
            f"{self._pct(self.consumer_secret)}&{self._pct(self.token_secret)}"
        )

        logger.debug("OAuth base string: %s", base_string)

        signature = base64.b64encode(
            hmac.new(
                signing_key.encode(),
                base_string.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature

        # realm first, then sorted OAuth params
        header_parts = [f'realm="{self.realm}"']
        for k in sorted(oauth_params):
            header_parts.append(f'{k}="{self._pct(oauth_params[k])}"')

        header = "OAuth " + ", ".join(header_parts)
        logger.debug("OAuth Authorization header: %s", header)
        return header

    # ── HTTP transport ───────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request against the NetSuite REST API.

        * 429 → exponential back-off (max ``MAX_RETRIES`` retries).
        * 401 → raise ``NetSuiteAuthError`` with credential guidance.
        * Other 4xx/5xx → raise ``NetSuiteAPIError``.
        """
        url = f"{self.base_url}{path}"

        for attempt in range(MAX_RETRIES + 1):
            # Fresh nonce/timestamp on every attempt
            auth_header = self._build_auth_header(method, url, params)

            headers: dict[str, str] = {"Authorization": auth_header}
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            if extra_headers:
                headers.update(extra_headers)

            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body if json_body is not None else None,
                    headers=headers,
                )
            elapsed = time.monotonic() - t0

            logger.debug(
                "NetSuite %s %s → %s (%.2fs)",
                method, path, resp.status_code, elapsed,
            )

            # Rate-limit → back off and retry
            if resp.status_code == 429 and attempt < MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning(
                    "NetSuite 429 rate-limit, retry %d/%d in %ds",
                    attempt + 1, MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 401:
                body = resp.text[:1000]
                logger.error("NetSuite 401 response body: %s", body)
                raise NetSuiteAuthError(
                    f"NetSuite TBA authentication failed ({resp.status_code}): "
                    f"{body}"
                )

            if resp.status_code >= 400:
                raise NetSuiteAPIError(
                    f"NetSuite API error {resp.status_code}: "
                    f"{resp.text[:500]}"
                )

            return resp

        raise NetSuiteAPIError(
            "NetSuite request failed: max retries exceeded (429)"
        )

    # ── SuiteQL helper ───────────────────────────────────────────────────

    async def _suiteql(
        self,
        query: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Execute a SuiteQL query, auto-paginating through all result pages."""
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            resp = await self._request(
                "POST",
                "/services/rest/query/v1/suiteql",
                params={"limit": str(limit), "offset": str(offset)},
                json_body={"q": query},
                extra_headers={"Prefer": "transient"},
            )
            data = resp.json()
            items = data.get("items", [])
            rows.extend(items)

            if not data.get("hasMore", False):
                break
            offset += limit

        logger.debug("SuiteQL returned %d total rows", len(rows))
        return rows

    # ── Public API ───────────────────────────────────────────────────────

    async def get_trial_balance(
        self,
        subsidiary_id: str,
        year: int,
        month: int,
    ) -> list[dict[str, Any]]:
        """Pull a monthly trial balance for a NetSuite subsidiary.

        Returns rows with keys: acctnumber, fullname, accttype, class_name, amount.
        ``amount`` is the net (positive = debit, negative = credit).
        Rows are grouped by account AND class so AASB16 lines are separated.
        """
        query = (
            "SELECT a.acctnumber, a.fullname, a.accttype, "
            "cl.name AS class_name, "
            "SUM(tl.amount) AS amount "
            "FROM transaction t "
            "JOIN transactionline tl ON t.id = tl.transaction "
            "JOIN account a ON tl.account = a.id "
            "LEFT JOIN classification cl ON tl.class = cl.id "
            f"WHERE t.subsidiary = {int(subsidiary_id)} "
            f"AND EXTRACT(MONTH FROM t.trandate) = {int(month)} "
            f"AND EXTRACT(YEAR FROM t.trandate) = {int(year)} "
            "AND t.posting = 'T' "
            "GROUP BY a.acctnumber, a.fullname, a.accttype, cl.name "
            "ORDER BY a.acctnumber"
        )
        return await self._suiteql(query)

    async def get_trial_balance_as_at(
        self,
        subsidiary_id: str,
        as_at_year: int,
        as_at_month: int,
    ) -> list[dict[str, Any]]:
        """Cumulative trial balance for a subsidiary up to the end of *as_at_month*.

        Returns the same row format as ``get_trial_balance`` (acctnumber, fullname,
        accttype, class_name, amount) but aggregates ALL posted transactions from
        inception through the given month-end.  Used for opening-balance imports.
        """
        import calendar
        last_day = calendar.monthrange(as_at_year, as_at_month)[1]
        as_at_date = f"{as_at_year}-{as_at_month:02d}-{last_day:02d}"

        query = (
            "SELECT a.acctnumber, a.fullname, a.accttype, "
            "cl.name AS class_name, "
            "SUM(tl.amount) AS amount "
            "FROM transaction t "
            "JOIN transactionline tl ON t.id = tl.transaction "
            "JOIN account a ON tl.account = a.id "
            "LEFT JOIN classification cl ON tl.class = cl.id "
            f"WHERE t.subsidiary = {int(subsidiary_id)} "
            f"AND t.trandate <= TO_DATE('{as_at_date}', 'YYYY-MM-DD') "
            "AND t.posting = 'T' "
            "GROUP BY a.acctnumber, a.fullname, a.accttype, cl.name "
            "ORDER BY a.acctnumber"
        )
        return await self._suiteql(query)

    async def list_subsidiaries(self) -> list[dict[str, Any]]:
        """SuiteQL subsidiary list (REST record API omits names in list view).

        Returns list of ``{internalId, name, fullname}``.
        """
        rows = await self._suiteql(
            "SELECT id, name, fullname FROM subsidiary ORDER BY name"
        )
        return [
            {
                "internalId": row["id"],
                "name": row.get("name", ""),
                "fullname": row.get("fullname", ""),
            }
            for row in rows
        ]

    async def list_accounts(self) -> list[dict[str, Any]]:
        """SuiteQL full account list for COA mapping admin.

        Returns rows with keys: id, acctnumber, fullname, accttype.
        """
        return await self._suiteql(
            "SELECT id, acctnumber, fullname, accttype "
            "FROM account ORDER BY acctnumber"
        )

    async def list_locations(self) -> list[dict[str, Any]]:
        """SuiteQL location list with subsidiary assignment.

        Returns rows with keys: id, name, subsidiary, isinactive.
        The ``subsidiary`` field is the internal ID of the owning subsidiary.
        """
        return await self._suiteql(
            "SELECT l.id, l.name, l.subsidiary, l.isinactive "
            "FROM location l "
            "WHERE l.isinactive = 'F' "
            "ORDER BY l.name"
        )
