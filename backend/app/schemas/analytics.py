"""Schemas for analytics endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


# ── Time Series ──────────────────────────────────────────────────────────────

class TimeSeriesPoint(BaseModel):
    period_label: str
    fy_year: int
    fy_month: int
    value: float
    prior_year_value: float | None = None
    mom_change_pct: float | None = None
    rolling_3m_avg: float | None = None
    rolling_12m_avg: float | None = None


class MultiTimeSeriesSeries(BaseModel):
    metric: str
    values: list[float]


class MultiTimeSeriesResponse(BaseModel):
    periods: list[str]
    series: list[MultiTimeSeriesSeries]


# ── Location Performance ─────────────────────────────────────────────────────

class LocationPerformanceRow(BaseModel):
    location_id: uuid.UUID
    location_code: str | None = None
    location_name: str | None = None
    state: str | None = None
    entity_code: str | None = None
    revenue: float = 0
    direct_costs: float = 0
    site_pl: float = 0
    budget_revenue: float | None = None
    budget_direct_costs: float | None = None
    budget_site_pl: float | None = None
    variance_abs: float | None = None
    variance_pct: float | None = None
    is_favourable: bool | None = None


class LocationTimeSeriesPoint(BaseModel):
    period_label: str
    fy_year: int
    fy_month: int
    revenue: float = 0
    direct_costs: float = 0
    site_pl: float = 0
    mom_change_pct: float | None = None


# ── Export ────────────────────────────────────────────────────────────────────

class AnalyticsExportRequest(BaseModel):
    report_type: str  # 'timeseries' | 'locations'
    params: dict
    format: str = "xlsx"
    include_aasb16: bool = True
