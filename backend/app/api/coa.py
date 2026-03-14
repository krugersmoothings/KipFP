"""Chart of Accounts mapping management."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.db.models.account import Account, AccountMapping
from app.db.models.entity import Entity
from app.db.models.sync import JeLine
from app.db.models.user import User
from app.schemas.coa import (
    AccountMappingRead,
    AccountMappingSave,
    SourceAccountRead,
    TargetAccountRead,
    ValidationResult,
)

router = APIRouter(prefix="/coa", tags=["coa"])


# ── GET /coa/source-accounts ────────────────────────────────────────────────


@router.get("/source-accounts", response_model=list[SourceAccountRead])
async def list_source_accounts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    # Get distinct (entity_id, source_account_code, source_account_name) from je_lines
    result = await db.execute(
        select(
            JeLine.entity_id,
            JeLine.source_account_code,
            JeLine.source_account_name,
        ).distinct()
    )
    source_rows = result.all()

    # Load entities
    ent_result = await db.execute(select(Entity))
    entity_map = {e.id: e for e in ent_result.scalars().all()}

    # Load all mappings
    mapping_result = await db.execute(select(AccountMapping))
    mappings = list(mapping_result.scalars().all())

    # Load target accounts for mapped items
    target_ids = {m.target_account_id for m in mappings}
    target_map: dict[uuid.UUID, Account] = {}
    if target_ids:
        target_result = await db.execute(
            select(Account).where(Account.id.in_(target_ids))
        )
        target_map = {a.id: a for a in target_result.scalars().all()}

    # Index mappings by (entity_id, source_account_code)
    mapping_index: dict[tuple[uuid.UUID, str], AccountMapping] = {}
    for m in mappings:
        mapping_index[(m.entity_id, m.source_account_code)] = m

    accounts: list[SourceAccountRead] = []
    for entity_id, src_code, src_name in source_rows:
        entity = entity_map.get(entity_id)
        mapping = mapping_index.get((entity_id, src_code))
        target = target_map.get(mapping.target_account_id) if mapping else None

        accounts.append(SourceAccountRead(
            entity_id=entity_id,
            entity_code=entity.code if entity else "?",
            entity_name=entity.name if entity else None,
            source_account_code=src_code,
            source_account_name=src_name,
            is_mapped=mapping is not None,
            mapping_id=mapping.id if mapping else None,
            target_account_code=target.code if target else None,
            target_account_name=target.name if target else None,
        ))

    # Sort: unmapped first, then by entity code + source code
    accounts.sort(key=lambda a: (a.is_mapped, a.entity_code, a.source_account_code))
    return accounts


# ── GET /coa/target-accounts ────────────────────────────────────────────────


@router.get("/target-accounts", response_model=list[TargetAccountRead])
async def list_target_accounts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    result = await db.execute(
        select(Account).order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())
    return [
        TargetAccountRead(
            id=a.id,
            code=a.code,
            name=a.name,
            account_type=a.account_type.value if a.account_type else None,
            statement=a.statement.value if a.statement else None,
        )
        for a in accounts
    ]


# ── GET /coa/mappings/{entity_id}/{source_code} ─────────────────────────────


@router.get("/mappings/{entity_id}/{source_code}", response_model=AccountMappingRead | None)
async def get_mapping(
    entity_id: uuid.UUID,
    source_code: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    result = await db.execute(
        select(AccountMapping).where(
            AccountMapping.entity_id == entity_id,
            AccountMapping.source_account_code == source_code,
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping is None:
        return None

    target = await db.get(Account, mapping.target_account_id)
    return AccountMappingRead(
        id=mapping.id,
        entity_id=mapping.entity_id,
        source_account_code=mapping.source_account_code,
        source_account_name=mapping.source_account_name,
        target_account_id=mapping.target_account_id,
        target_account_code=target.code if target else None,
        target_account_name=target.name if target else None,
        multiplier=float(mapping.multiplier),
        effective_from=mapping.effective_from,
        effective_to=mapping.effective_to,
        notes=mapping.notes,
    )


# ── PUT /coa/mappings ────────────────────────────────────────────────────────


@router.put("/mappings", response_model=AccountMappingRead)
async def save_mapping(
    payload: AccountMappingSave,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    result = await db.execute(
        select(AccountMapping).where(
            AccountMapping.entity_id == payload.entity_id,
            AccountMapping.source_account_code == payload.source_account_code,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.target_account_id = payload.target_account_id
        existing.multiplier = payload.multiplier
        existing.effective_from = payload.effective_from
        existing.source_account_name = payload.source_account_name
        existing.notes = payload.notes
        await db.commit()
        await db.refresh(existing)
        mapping = existing
    else:
        mapping = AccountMapping(
            entity_id=payload.entity_id,
            source_account_code=payload.source_account_code,
            source_account_name=payload.source_account_name,
            target_account_id=payload.target_account_id,
            multiplier=payload.multiplier,
            effective_from=payload.effective_from,
            notes=payload.notes,
        )
        db.add(mapping)
        await db.commit()
        await db.refresh(mapping)

    target = await db.get(Account, mapping.target_account_id)
    return AccountMappingRead(
        id=mapping.id,
        entity_id=mapping.entity_id,
        source_account_code=mapping.source_account_code,
        source_account_name=mapping.source_account_name,
        target_account_id=mapping.target_account_id,
        target_account_code=target.code if target else None,
        target_account_name=target.name if target else None,
        multiplier=float(mapping.multiplier),
        effective_from=mapping.effective_from,
        effective_to=mapping.effective_to,
        notes=mapping.notes,
    )


# ── POST /coa/validate ──────────────────────────────────────────────────────


@router.post("/validate", response_model=ValidationResult)
async def validate_mappings(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    # Get distinct source accounts with transactions
    result = await db.execute(
        select(
            JeLine.entity_id,
            JeLine.source_account_code,
            JeLine.source_account_name,
        ).distinct()
    )
    source_rows = result.all()

    # Load entities
    ent_result = await db.execute(select(Entity))
    entity_map = {e.id: e for e in ent_result.scalars().all()}

    # Load all mappings
    mapping_result = await db.execute(select(AccountMapping))
    mappings = list(mapping_result.scalars().all())
    mapping_keys = {(m.entity_id, m.source_account_code) for m in mappings}

    unmapped: list[SourceAccountRead] = []
    mapped_count = 0

    for entity_id, src_code, src_name in source_rows:
        if (entity_id, src_code) in mapping_keys:
            mapped_count += 1
        else:
            entity = entity_map.get(entity_id)
            unmapped.append(SourceAccountRead(
                entity_id=entity_id,
                entity_code=entity.code if entity else "?",
                entity_name=entity.name if entity else None,
                source_account_code=src_code,
                source_account_name=src_name,
                is_mapped=False,
            ))

    unmapped.sort(key=lambda a: (a.entity_code, a.source_account_code))

    return ValidationResult(
        total_source_accounts=len(source_rows),
        mapped_count=mapped_count,
        unmapped_count=len(unmapped),
        unmapped_accounts=unmapped,
    )
