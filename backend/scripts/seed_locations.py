"""Seed locations from NetSuite into the locations table.

Queries the NetSuite location record type via SuiteQL to get all active
locations, then maps each to its parent entity via the subsidiary → entity
relationship.

Run from the backend container:
    python -m scripts.seed_locations
"""

import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.netsuite import NetSuiteClient
from app.db.base import async_session_factory
from app.db.models.entity import Entity
from app.db.models.location import Location

# Australian state abbreviations for rough name-based detection
STATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NSW", re.compile(r"\b(NSW|Sydney|Syd|Newcastle|Wollongong|Central Coast)\b", re.I)),
    ("ACT", re.compile(r"\b(ACT|Canberra)\b", re.I)),
    ("VIC", re.compile(r"\b(VIC|Melbourne|Melb|Geelong|Bendigo|Ballarat)\b", re.I)),
    ("QLD", re.compile(r"\b(QLD|Brisbane|Gold Coast|Sunshine Coast|Townsville|Cairns|Toowoomba)\b", re.I)),
    ("SA",  re.compile(r"\b(SA|Adelaide)\b", re.I)),
    ("WA",  re.compile(r"\b(WA|Perth|Fremantle)\b", re.I)),
    ("TAS", re.compile(r"\b(TAS|Hobart|Launceston)\b", re.I)),
    ("NT",  re.compile(r"\b(NT|Darwin)\b", re.I)),
]


def _guess_state(name: str) -> str | None:
    for state, pattern in STATE_PATTERNS:
        if pattern.search(name):
            return state
    return None


async def seed() -> None:
    # ── 1. Pull locations from NetSuite ──────────────────────────────────
    print("Connecting to NetSuite...")
    ns = NetSuiteClient()
    ns_locations = await ns.list_locations()
    print(f"NetSuite returned {len(ns_locations)} active locations")

    if not ns_locations:
        print("No locations returned from NetSuite. Nothing to seed.")
        return

    # Also pull subsidiaries so we can map subsidiary ID → entity
    ns_subsidiaries = await ns.list_subsidiaries()
    print(f"NetSuite returned {len(ns_subsidiaries)} subsidiaries")

    # ── 2. Build subsidiary ID → NetSuite name mapping ───────────────────
    sub_name_map: dict[str, str] = {}
    for sub in ns_subsidiaries:
        sub_name_map[str(sub["internalId"])] = sub.get("name", "")

    async with async_session_factory() as db:
        db: AsyncSession

        # ── 3. Load entities and build source_entity_id → entity mapping ──
        result = await db.execute(
            select(Entity).where(Entity.is_active.is_(True))
        )
        entities = list(result.scalars().all())

        # Map NetSuite subsidiary ID (source_entity_id) → Entity
        sub_to_entity: dict[str, Entity] = {}
        for e in entities:
            if e.source_entity_id:
                sub_to_entity[str(e.source_entity_id)] = e

        if not sub_to_entity:
            print("WARNING: No entities have source_entity_id set.")
            print("Available entities:", [(e.code, e.source_entity_id) for e in entities])

        # ── 4. Check for existing locations ────────────────────────────────
        result = await db.execute(select(Location).limit(1))
        if result.scalar_one_or_none() is not None:
            existing_count = await db.execute(select(Location))
            count = len(list(existing_count.scalars().all()))
            print(f"Locations already seeded ({count} rows).")
            print("To re-seed, delete existing rows first.")
            return

        # ── 5. Insert locations ────────────────────────────────────────────
        added = 0
        skipped = 0

        for loc in ns_locations:
            ns_id = str(loc.get("id", ""))
            name = loc.get("name", "").strip()
            subsidiary_id = str(loc.get("subsidiary", ""))

            if not name:
                skipped += 1
                continue

            # Map subsidiary → entity
            entity = sub_to_entity.get(subsidiary_id)
            entity_id = entity.id if entity else None

            # Derive a short code from the name
            code = re.sub(r"[^A-Za-z0-9]", "-", name)[:20].upper().strip("-")

            state = _guess_state(name)

            db.add(Location(
                id=uuid.uuid4(),
                code=code,
                name=name,
                entity_id=entity_id,
                state=state,
                netsuite_location_id=ns_id,
                is_active=True,
            ))
            added += 1

            entity_label = entity.code if entity else f"(sub {subsidiary_id}, no entity match)"
            print(f"  + {name:<40s}  state={state or '?':<3s}  entity={entity_label}")

        await db.commit()

        print(f"\nSeeded {added} locations ({skipped} skipped).")
        if added == 0:
            print("No locations were inserted. Check NetSuite location data.")


if __name__ == "__main__":
    asyncio.run(seed())
