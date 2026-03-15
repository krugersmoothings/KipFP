"""Seed BigQuery property → KipFP location mappings.

Run once after migration 0009:
    python -m scripts.seed_property_mappings
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.base import async_session_factory
from app.db.models.location import Location, PropertyMapping

MAPPINGS: list[dict] = [
    {"bq_id": 34, "bq_name": "Doggos on Shelomith",       "location_name": "Kip Cambridge"},
    {"bq_id": 36, "bq_name": "Hanrob Brisbane Airport",    "location_name": "Hanrob Brisbane"},
    {"bq_id": 37, "bq_name": "Hanrob Canberra",           "location_name": "Hanrob Canberra"},
    {"bq_id": 38, "bq_name": "Hanrob Darwin Airport",     "location_name": "Hanrob Darwin"},
    {"bq_id": 39, "bq_name": "Hanrob Duffy's Forest",     "location_name": "Hanrob Duffys"},
    {"bq_id": 40, "bq_name": "Hanrob Heathcote",          "location_name": "Hanrob Heathcote"},
    {"bq_id": 41, "bq_name": "Hanrob Melbourne Airport",  "location_name": "Hanrob Melbourne"},
    {"bq_id": 42, "bq_name": "Hanrob North Perth",        "location_name": "Hanrob Perth"},
    {"bq_id": 43, "bq_name": "Hanrob Sydney Airport",     "location_name": "Hanrob Mascot"},
    {"bq_id": 44, "bq_name": "Hanrob Wyee",               "location_name": "Hanrob Wyee"},
    {"bq_id": 17, "bq_name": "Kip Adelaide Hills",        "location_name": "Kip Adelaide Hills"},
    {"bq_id": 20, "bq_name": "Kip Adelaide North",        "location_name": "Kip Adelaide North"},
    {"bq_id": 18, "bq_name": "Kip Alexandria",            "location_name": "Kip Alexandria"},
    {"bq_id": 10, "bq_name": "Kip Bayside",               "location_name": "Kip Bayside"},
    {"bq_id":  9, "bq_name": "Kip Bayswater",             "location_name": "Kip Bayswater"},
    {"bq_id":  8, "bq_name": "Kip Blackburn",             "location_name": "Kip Blackburn"},
    {"bq_id": 22, "bq_name": "Kip Brisbane",              "location_name": "Kip Brisbane"},
    {"bq_id": 13, "bq_name": "Kip Broadview",             "location_name": "Kip Broadview"},
    {"bq_id": 15, "bq_name": "Kip Brunswick",             "location_name": "Kip Brunswick"},
    {"bq_id": 33, "bq_name": "Kip Caloundra",             "location_name": "Kip Caloundra"},
    {"bq_id": 23, "bq_name": "Kip Canberra",              "location_name": "Kip Canberra"},
    {"bq_id": 14, "bq_name": "Kip Fairfield",             "location_name": "Kip Fairfield"},
    {"bq_id": 11, "bq_name": "Kip Hobart",                "location_name": "Kip Hobart"},
    {"bq_id": 30, "bq_name": "Kip Homestead Yarra Valley", "location_name": "Kip Homestead Yarra Valley"},
    {"bq_id": 21, "bq_name": "Kip Hunter Valley",         "location_name": "Kip Hunter Valley"},
    {"bq_id": 35, "bq_name": "Kip Imparra",               "location_name": "Kip Imparra"},
    {"bq_id": 32, "bq_name": "Kip Ipswich",               "location_name": "Kip Ipswich"},
    {"bq_id": 16, "bq_name": "Kip Kew",                   "location_name": "Kip Kew"},
    {"bq_id": 24, "bq_name": "Kip Lake Macquarie",        "location_name": "Kip Lake Macquarie"},
    {"bq_id": 25, "bq_name": "Kip Marrickville",          "location_name": "Kip Marrickville"},
    {"bq_id": 26, "bq_name": "Kip Melbourne South East",  "location_name": "Kip Melbourne South East"},
    {"bq_id":  4, "bq_name": "Kip Melbourne West",        "location_name": "Kip Melbourne West"},
    {"bq_id": 29, "bq_name": "Kip Mornington",            "location_name": "Kip Mornington"},
    {"bq_id": 31, "bq_name": "Kip Newstead",              "location_name": "Kip Newstead"},
    {"bq_id": 27, "bq_name": "Kip Newtown",               "location_name": "Kip Newtown"},
    {"bq_id": 28, "bq_name": "Kip Thomastown",            "location_name": "Kip Thomastown"},
    {"bq_id": 19, "bq_name": "Kip West Hindmarsh",        "location_name": "Kip West Hindmarsh"},
    {"bq_id": 45, "bq_name": "Pacific Pet Resort",        "location_name": "Pacific Pet Resort"},
]


async def seed():
    async with async_session_factory() as db:
        result = await db.execute(select(Location))
        locations = {loc.name: loc.id for loc in result.scalars().all()}

        inserted = 0
        skipped = 0
        for m in MAPPINGS:
            loc_id = locations.get(m["location_name"])
            if loc_id is None:
                print(f"  WARNING: location '{m['location_name']}' not found — mapping saved without location_id")

            stmt = insert(PropertyMapping).values(
                id=uuid.uuid4(),
                bigquery_property_id=m["bq_id"],
                bigquery_property_name=m["bq_name"],
                location_id=loc_id,
                is_active=True,
            ).on_conflict_do_update(
                index_elements=["bigquery_property_id"],
                set_={
                    "bigquery_property_name": m["bq_name"],
                    "location_id": loc_id,
                },
            )
            await db.execute(stmt)
            inserted += 1

        await db.commit()
        print(f"Seeded {inserted} property mappings.")

        result = await db.execute(select(PropertyMapping))
        for pm in result.scalars().all():
            loc_name = locations.get(pm.location_id) if pm.location_id else None
            status = "mapped" if pm.location_id else "UNMAPPED"
            print(f"  [{status}] BQ#{pm.bigquery_property_id} {pm.bigquery_property_name}")


if __name__ == "__main__":
    asyncio.run(seed())
