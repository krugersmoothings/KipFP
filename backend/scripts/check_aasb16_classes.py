"""Diagnostic: check what class names NetSuite returns for June periods.

Run from the backend container:
    python -m scripts.check_aasb16_classes
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.base import async_session_factory
from app.db.models.entity import Entity
from app.connectors.netsuite import NetSuiteClient


async def run():
    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity)
            .where(Entity.is_active.is_(True), Entity.source_system == "netsuite")
            .order_by(Entity.code)
            .limit(3)
        )
        entities = list(result.scalars().all())

    client = NetSuiteClient()

    for ent in entities:
        if not ent.source_entity_id:
            continue
        print(f"\n{'='*60}")
        print(f"Entity: {ent.code} ({ent.name}), subsidiary={ent.source_entity_id}")
        print(f"{'='*60}")

        # FY2024 M12 = Jun 2024 (cal_year=2024, cal_month=6)
        # FY2025 M12 = Jun 2025 (cal_year=2025, cal_month=6)
        for cal_year, fy_label in [(2024, "FY2024 M12"), (2025, "FY2025 M12")]:
            print(f"\n--- {fy_label} (Jun {cal_year}) ---")
            rows = await client.get_trial_balance(ent.source_entity_id, cal_year, 6)

            classes_seen = set()
            rows_with_class = []
            for row in rows:
                cn = row.get("class_name")
                if cn:
                    classes_seen.add(cn)
                    rows_with_class.append(row)

            print(f"  Total rows: {len(rows)}")
            print(f"  Rows with class_name set: {len(rows_with_class)}")
            print(f"  Distinct class_name values: {classes_seen or '{none}'}")

            if rows_with_class:
                print(f"\n  Rows with class_name:")
                for r in rows_with_class[:15]:
                    print(f"    {r.get('acctnumber'):>8}  {r.get('fullname','')[:40]:<40}  class={r.get('class_name')!r}  amt={r.get('amount')}")

    # Also run a raw SuiteQL to list all classification names
    print(f"\n{'='*60}")
    print("All NetSuite classifications:")
    print(f"{'='*60}")
    class_rows = await client._suiteql(
        "SELECT id, name, fullname FROM classification ORDER BY name"
    )
    for r in class_rows:
        print(f"  id={r.get('id')}  name={r.get('name')!r}  fullname={r.get('fullname')!r}")

    if not class_rows:
        print("  No classifications found in NetSuite")


if __name__ == "__main__":
    asyncio.run(run())
