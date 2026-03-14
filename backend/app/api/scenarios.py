"""Scenario manager — clone, tweak assumptions, compare."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_finance
from app.db.models.account import Account
from app.db.models.budget import BudgetVersion, ModelAssumption, ModelOutput, VersionType
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.user import User
from app.db.models.wc import WcDriver
from app.schemas.scenarios import (
    ScenarioAssumptionUpdate,
    ScenarioCompareResponse,
    ScenarioCreate,
    ScenarioMetric,
    ScenarioRead,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


# ── GET /scenarios ───────────────────────────────────────────────────────────


@router.get("/", response_model=list[ScenarioRead])
async def list_scenarios(
    version_id: uuid.UUID = Query(..., description="Base version to list scenarios for"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    result = await db.execute(
        select(BudgetVersion)
        .where(
            BudgetVersion.version_type == VersionType.scenario,
            BudgetVersion.base_version_id == version_id,
        )
        .order_by(BudgetVersion.created_at.desc())
    )
    versions = list(result.scalars().all())
    return [
        ScenarioRead(
            id=v.id,
            name=v.name,
            fy_year=v.fy_year,
            version_type=v.version_type.value,
            status=v.status.value,
            base_version_id=v.base_version_id,
            description=None,
            created_at=v.created_at,
        )
        for v in versions
    ]


# ── POST /scenarios ──────────────────────────────────────────────────────────


@router.post("/", response_model=ScenarioRead, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    base = await db.get(BudgetVersion, payload.base_version_id)
    if base is None:
        raise HTTPException(status_code=404, detail="Base version not found")

    scenario = BudgetVersion(
        name=payload.name,
        fy_year=base.fy_year,
        version_type=VersionType.scenario,
        base_version_id=base.id,
        created_by=user.id,
    )
    db.add(scenario)
    await db.flush()

    # Clone assumptions
    result = await db.execute(
        select(ModelAssumption).where(
            ModelAssumption.budget_version_id == base.id
        )
    )
    for orig in result.scalars().all():
        db.add(ModelAssumption(
            budget_version_id=scenario.id,
            entity_id=orig.entity_id,
            assumption_key=orig.assumption_key,
            assumption_value=orig.assumption_value,
            updated_by=user.id,
        ))

    # Clone WC drivers
    result = await db.execute(
        select(WcDriver).where(WcDriver.budget_version_id == base.id)
    )
    for orig in result.scalars().all():
        db.add(WcDriver(
            budget_version_id=scenario.id,
            entity_id=orig.entity_id,
            account_id=orig.account_id,
            driver_type=orig.driver_type,
            base_days=orig.base_days,
            seasonal_factors=orig.seasonal_factors,
            notes=orig.notes,
            last_updated_by=user.id,
            last_updated_at=datetime.now(timezone.utc),
        ))

    await db.commit()
    await db.refresh(scenario)

    # Trigger model calculation
    from app.worker import run_model_task
    task_id = f"model-{scenario.id}"
    run_model_task.apply_async(args=[str(scenario.id)], task_id=task_id)

    return ScenarioRead(
        id=scenario.id,
        name=scenario.name,
        fy_year=scenario.fy_year,
        version_type=scenario.version_type.value,
        status=scenario.status.value,
        base_version_id=scenario.base_version_id,
        description=payload.description,
        created_at=scenario.created_at,
    )


# ── PUT /scenarios/{id}/assumptions ──────────────────────────────────────────


@router.put("/{scenario_id}/assumptions", response_model=ScenarioRead)
async def update_scenario_assumption(
    scenario_id: uuid.UUID,
    payload: ScenarioAssumptionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    scenario = await db.get(BudgetVersion, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.version_type != VersionType.scenario:
        raise HTTPException(status_code=400, detail="Not a scenario version")

    result = await db.execute(
        select(ModelAssumption).where(
            ModelAssumption.budget_version_id == scenario_id,
            ModelAssumption.entity_id == payload.entity_id,
            ModelAssumption.assumption_key == payload.assumption_key,
        )
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.assumption_value = payload.assumption_value
        existing.updated_by = user.id
        existing.updated_at = now
    else:
        db.add(ModelAssumption(
            budget_version_id=scenario_id,
            entity_id=payload.entity_id,
            assumption_key=payload.assumption_key,
            assumption_value=payload.assumption_value,
            updated_by=user.id,
        ))

    await db.commit()
    await db.refresh(scenario)

    # Re-trigger model calculation
    from app.worker import run_model_task
    task_id = f"model-{scenario_id}"
    run_model_task.apply_async(args=[str(scenario_id)], task_id=task_id)

    return ScenarioRead(
        id=scenario.id,
        name=scenario.name,
        fy_year=scenario.fy_year,
        version_type=scenario.version_type.value,
        status=scenario.status.value,
        base_version_id=scenario.base_version_id,
        description=None,
        created_at=scenario.created_at,
    )


# ── GET /scenarios/compare ───────────────────────────────────────────────────


@router.get("/compare", response_model=ScenarioCompareResponse)
async def compare_scenarios(
    ids: str = Query(..., description="Comma-separated version IDs (up to 5)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    id_list = [uuid.UUID(s.strip()) for s in ids.split(",") if s.strip()]
    if len(id_list) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 scenarios for comparison")

    # Load versions
    result = await db.execute(
        select(BudgetVersion).where(BudgetVersion.id.in_(id_list))
    )
    versions = {v.id: v for v in result.scalars().all()}

    if not versions:
        raise HTTPException(status_code=404, detail="No versions found")

    fy_year = next(iter(versions.values())).fy_year

    # Load periods
    result = await db.execute(
        select(Period).where(Period.fy_year == fy_year).order_by(Period.fy_month)
    )
    periods = list(result.scalars().all())
    period_ids = [p.id for p in periods]

    # Load key accounts
    key_codes = ["REV-SALES", "COGS", "GM", "EBITDA", "NPAT",
                 "CF-OPERATING", "BS-CASH", "BS-TOTALDEBT"]
    result = await db.execute(
        select(Account).where(Account.code.in_(key_codes))
    )
    key_accounts = {a.code: a for a in result.scalars().all()}

    key_account_ids = [a.id for a in key_accounts.values()]

    # Load model outputs for all scenarios
    result = await db.execute(
        select(ModelOutput).where(
            ModelOutput.version_id.in_(id_list),
            ModelOutput.period_id.in_(period_ids),
            ModelOutput.account_id.in_(key_account_ids),
            ModelOutput.entity_id.is_(None),
        )
    )

    # Aggregate: version_id → account_code → total
    totals: dict[uuid.UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    code_by_id = {a.id: code for code, a in key_accounts.items()}
    for mo in result.scalars().all():
        code = code_by_id.get(mo.account_id)
        if code:
            totals[mo.version_id][code] += float(mo.amount)

    metrics: list[ScenarioMetric] = []
    for vid in id_list:
        v = versions.get(vid)
        if not v:
            continue
        t = totals.get(vid, {})
        revenue = t.get("REV-SALES", 0)
        cogs = t.get("COGS", 0)
        gm = t.get("GM", revenue - cogs)
        ebitda = t.get("EBITDA", 0)

        metrics.append(ScenarioMetric(
            scenario_id=vid,
            scenario_name=v.name,
            revenue=revenue,
            gm_pct=(gm / revenue * 100) if revenue != 0 else None,
            ebitda=ebitda,
            ebitda_pct=(ebitda / revenue * 100) if revenue != 0 else None,
            npat=t.get("NPAT", 0),
            operating_cf=t.get("CF-OPERATING", 0),
            closing_cash=t.get("BS-CASH", 0),
            total_debt=t.get("BS-TOTALDEBT", 0),
        ))

    return ScenarioCompareResponse(fy_year=fy_year, scenarios=metrics)
