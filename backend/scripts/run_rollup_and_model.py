"""Run site rollup and model calculation for a budget version.

Usage:
    python scripts/run_rollup_and_model.py <version_id>
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.base import async_session_factory
from app.services.site_rollup_service import rollup_sites_to_entity
from app.services.model_engine import run_model


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_rollup_and_model.py <version_id>")
        sys.exit(1)

    version_id = uuid.UUID(sys.argv[1])
    print(f"Version ID: {version_id}")

    # Step 1: Site rollup
    print("\n=== Running site rollup ===")
    async with async_session_factory() as db:
        result = await rollup_sites_to_entity(db, version_id)
        await db.commit()
        print(f"Rollup result: {result}")

    # Step 2: Model calculation
    print("\n=== Running model calculation ===")
    result = await run_model(version_id)
    print(f"Model result: {result}")

    print("\nAll done.")


if __name__ == "__main__":
    asyncio.run(main())
