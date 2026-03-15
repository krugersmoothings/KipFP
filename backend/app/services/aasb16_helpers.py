"""Shared helpers for computing AASB16 adjustments.

Used by consolidation, analytics, and reports API routes to subtract AASB16
amounts from pre-computed consolidated_actuals when rendering ex-lease views.
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account, AccountMapping
from app.db.models.entity import Entity
from app.db.models.sync import JeLine


async def compute_aasb16_by_account_period(
    db: AsyncSession,
    period_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict[uuid.UUID, float]]:
    """Compute mapped AASB16 amounts per (target_account_id, period_id).

    Returns {account_id: {period_id: mapped_amount}}.
    """
    entity_result = await db.execute(
        select(Entity).where(Entity.is_active.is_(True))
    )
    entity_ids = {e.id for e in entity_result.scalars().all()}

    je_result = await db.execute(
        select(JeLine).where(
            JeLine.period_id.in_(period_ids),
            JeLine.entity_id.in_(entity_ids),
            JeLine.is_aasb16.is_(True),
        )
    )
    aasb16_lines = je_result.scalars().all()
    if not aasb16_lines:
        return {}

    acct_result = await db.execute(select(Account))
    account_by_id = {a.id: a for a in acct_result.scalars().all()}

    mapping_result = await db.execute(select(AccountMapping))
    mapping_lookup: dict[tuple[uuid.UUID, str], AccountMapping] = {}
    for m in mapping_result.scalars().all():
        mapping_lookup[(m.entity_id, m.source_account_code)] = m

    result: dict[uuid.UUID, dict[uuid.UUID, float]] = defaultdict(lambda: defaultdict(float))

    for jl in aasb16_lines:
        key = (jl.entity_id, jl.source_account_code)
        mapping = mapping_lookup.get(key)
        if mapping is None:
            continue
        target_acct = account_by_id.get(mapping.target_account_id)
        if target_acct is None:
            continue
        multiplier = float(mapping.multiplier)
        mapped_amount = float(jl.amount) * multiplier
        result[target_acct.id][jl.period_id] += mapped_amount

    return dict(result)


async def compute_aasb16_per_period_with_entities(
    db: AsyncSession,
    period_ids: list[uuid.UUID],
    period_id_to_label: dict[uuid.UUID, str],
) -> dict[uuid.UUID, dict]:
    """Compute mapped AASB16 amounts broken down by period label and entity.

    Returns {account_id: {"group": {label: amount}, "entities": {ecode: {label: amount}}}}
    """
    entity_result = await db.execute(
        select(Entity).where(Entity.is_active.is_(True))
    )
    entities = {e.id: e for e in entity_result.scalars().all()}
    entity_ids = set(entities.keys())

    je_result = await db.execute(
        select(JeLine).where(
            JeLine.period_id.in_(period_ids),
            JeLine.entity_id.in_(entity_ids),
            JeLine.is_aasb16.is_(True),
        )
    )
    aasb16_lines = je_result.scalars().all()
    if not aasb16_lines:
        return {}

    acct_result = await db.execute(select(Account))
    account_by_id = {a.id: a for a in acct_result.scalars().all()}

    mapping_result = await db.execute(select(AccountMapping))
    mapping_lookup: dict[tuple[uuid.UUID, str], AccountMapping] = {}
    for m in mapping_result.scalars().all():
        mapping_lookup[(m.entity_id, m.source_account_code)] = m

    result: dict[uuid.UUID, dict] = defaultdict(
        lambda: {"group": defaultdict(float), "entities": defaultdict(lambda: defaultdict(float))}
    )

    for jl in aasb16_lines:
        label = period_id_to_label.get(jl.period_id)
        if label is None:
            continue
        key = (jl.entity_id, jl.source_account_code)
        mapping = mapping_lookup.get(key)
        if mapping is None:
            continue
        target_acct = account_by_id.get(mapping.target_account_id)
        if target_acct is None:
            continue
        multiplier = float(mapping.multiplier)
        mapped_amount = float(jl.amount) * multiplier
        ent = entities.get(jl.entity_id)
        ecode = ent.code if ent else "?"
        result[target_acct.id]["group"][label] += mapped_amount
        result[target_acct.id]["entities"][ecode][label] += mapped_amount

    return dict(result)
