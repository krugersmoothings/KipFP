"""IC Elimination Rules — CRUD and preview for consolidation review."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, require_finance
from app.db.models.consolidation import ICEliminationRule
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine
from app.db.models.user import User

router = APIRouter(prefix="/ic-rules", tags=["ic-rules"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class ICRuleRead(BaseModel):
    id: uuid.UUID
    label: str
    entity_a_id: uuid.UUID
    entity_a_code: str | None = None
    entity_a_name: str | None = None
    account_code_a: str
    entity_b_id: uuid.UUID
    entity_b_code: str | None = None
    entity_b_name: str | None = None
    account_code_b: str
    is_active: bool
    tolerance: float
    notes: str | None = None

    model_config = {"from_attributes": True}


class ICRuleCreate(BaseModel):
    label: str
    entity_a_id: uuid.UUID
    account_code_a: str
    entity_b_id: uuid.UUID
    account_code_b: str
    is_active: bool = True
    tolerance: float = 10.00
    notes: str | None = None


class ICRuleUpdate(BaseModel):
    label: str | None = None
    entity_a_id: uuid.UUID | None = None
    account_code_a: str | None = None
    entity_b_id: uuid.UUID | None = None
    account_code_b: str | None = None
    is_active: bool | None = None
    tolerance: float | None = None
    notes: str | None = None


class ICPreviewRow(BaseModel):
    rule_id: uuid.UUID
    label: str
    entity_a_code: str
    account_code_a: str
    balance_a: float
    entity_b_code: str
    account_code_b: str
    balance_b: float
    net: float
    tolerance: float
    status: str  # "balanced" | "within_tolerance" | "imbalance"


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _enrich_rule(rule: ICEliminationRule, entities: dict[uuid.UUID, Entity]) -> ICRuleRead:
    ea = entities.get(rule.entity_a_id)
    eb = entities.get(rule.entity_b_id)
    return ICRuleRead(
        id=rule.id,
        label=rule.label,
        entity_a_id=rule.entity_a_id,
        entity_a_code=ea.code if ea else None,
        entity_a_name=ea.name if ea else None,
        account_code_a=rule.account_code_a,
        entity_b_id=rule.entity_b_id,
        entity_b_code=eb.code if eb else None,
        entity_b_name=eb.name if eb else None,
        account_code_b=rule.account_code_b,
        is_active=rule.is_active,
        tolerance=float(rule.tolerance),
        notes=rule.notes,
    )


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ICRuleRead])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    result = await db.execute(select(ICEliminationRule).order_by(ICEliminationRule.label))
    rules = result.scalars().all()

    ent_result = await db.execute(select(Entity))
    entities = {e.id: e for e in ent_result.scalars().all()}

    return [await _enrich_rule(r, entities) for r in rules]


@router.post("", response_model=ICRuleRead, status_code=201)
async def create_rule(
    payload: ICRuleCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    # FIX(M13): validate entity FKs before insert
    ea = await db.get(Entity, payload.entity_a_id)
    if ea is None:
        raise HTTPException(status_code=422, detail="entity_a_id does not exist")
    eb = await db.get(Entity, payload.entity_b_id)
    if eb is None:
        raise HTTPException(status_code=422, detail="entity_b_id does not exist")

    rule = ICEliminationRule(
        label=payload.label,
        entity_a_id=payload.entity_a_id,
        account_code_a=payload.account_code_a,
        entity_b_id=payload.entity_b_id,
        account_code_b=payload.account_code_b,
        is_active=payload.is_active,
        tolerance=payload.tolerance,
        notes=payload.notes,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    ent_result = await db.execute(select(Entity))
    entities = {e.id: e for e in ent_result.scalars().all()}
    return await _enrich_rule(rule, entities)


@router.put("/{rule_id}", response_model=ICRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    payload: ICRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    rule = await db.get(ICEliminationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    await db.commit()
    await db.refresh(rule)

    ent_result = await db.execute(select(Entity))
    entities = {e.id: e for e in ent_result.scalars().all()}
    return await _enrich_rule(rule, entities)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    rule = await db.get(ICEliminationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()


# ── Preview ──────────────────────────────────────────────────────────────────


@router.get("/preview", response_model=list[ICPreviewRow])
async def preview_eliminations(
    fy_year: int = Query(...),
    fy_month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Preview IC balances for all active rules in a given period."""
    result = await db.execute(
        select(Period).where(Period.fy_year == fy_year, Period.fy_month == fy_month)
    )
    period = result.scalar_one_or_none()
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    result = await db.execute(
        select(ICEliminationRule).where(ICEliminationRule.is_active.is_(True)).order_by(ICEliminationRule.label)
    )
    rules = result.scalars().all()
    if not rules:
        return []

    ent_result = await db.execute(select(Entity))
    entities = {e.id: e for e in ent_result.scalars().all()}

    relevant_entity_ids = set()
    for r in rules:
        relevant_entity_ids.add(r.entity_a_id)
        relevant_entity_ids.add(r.entity_b_id)

    je_result = await db.execute(
        select(JeLine).where(
            JeLine.period_id == period.id,
            JeLine.entity_id.in_(relevant_entity_ids),
        )
    )
    je_lines = je_result.scalars().all()

    balances: dict[tuple[uuid.UUID, str], float] = {}
    for jl in je_lines:
        key = (jl.entity_id, jl.source_account_code)
        balances[key] = balances.get(key, 0.0) + float(jl.amount)

    rows: list[ICPreviewRow] = []
    for rule in rules:
        bal_a = balances.get((rule.entity_a_id, rule.account_code_a), 0.0)
        bal_b = balances.get((rule.entity_b_id, rule.account_code_b), 0.0)
        net = bal_a + bal_b
        tol = float(rule.tolerance)

        if abs(net) <= 0.01:
            status = "balanced"
        elif abs(net) <= tol:
            status = "within_tolerance"
        else:
            status = "imbalance"

        ea = entities.get(rule.entity_a_id)
        eb = entities.get(rule.entity_b_id)

        rows.append(ICPreviewRow(
            rule_id=rule.id,
            label=rule.label,
            entity_a_code=ea.code if ea else "?",
            account_code_a=rule.account_code_a,
            balance_a=round(bal_a, 2),
            entity_b_code=eb.code if eb else "?",
            account_code_b=rule.account_code_b,
            balance_b=round(bal_b, 2),
            net=round(net, 2),
            tolerance=tol,
            status=status,
        ))

    return rows
