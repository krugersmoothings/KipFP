"""Seed admin user, periods (FY2023-FY2028), and weekly_periods.

Run from the backend container:
    python -m scripts.seed_initial
"""
import asyncio
import calendar
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

# Ensure the project root (/app) is on sys.path so `app.*` imports work
# regardless of whether this is run as `python -m scripts.seed_initial`
# or `python scripts/seed_initial.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.db.base import async_session_factory
from app.db.models.period import Period, WeeklyPeriod
from app.db.models.user import User, UserRole

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@kipgroup.com.au")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

FY_START_YEAR = 2023
FY_END_YEAR = 2028


def _fy_month_to_calendar(fy_year: int, fy_month: int) -> tuple[int, int]:
    """Convert FY month (1=Jul .. 12=Jun) to (calendar_year, calendar_month)."""
    cal_month = (fy_month + 6 - 1) % 12 + 1  # 1->7, 2->8, ..., 6->12, 7->1, ..., 12->6
    if fy_month <= 6:
        cal_year = fy_year - 1
    else:
        cal_year = fy_year
    return cal_year, cal_month


def _fy_for_date(d: date) -> tuple[int, int, int]:
    """Return (fy_year, fy_month, fy_quarter) for a calendar date."""
    m = d.month
    if m >= 7:
        fy_year = d.year + 1
        fy_month = m - 6  # Jul=1, Aug=2, ..., Dec=6
    else:
        fy_year = d.year
        fy_month = m + 6  # Jan=7, Feb=8, ..., Jun=12
    fy_quarter = (fy_month - 1) // 3 + 1
    return fy_year, fy_month, fy_quarter


def _days_in_cal_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def build_periods() -> list[dict]:
    rows: list[dict] = []
    for fy_year in range(FY_START_YEAR, FY_END_YEAR + 1):
        for fy_month in range(1, 13):
            cal_year, cal_month = _fy_month_to_calendar(fy_year, fy_month)
            start = date(cal_year, cal_month, 1)
            end = date(cal_year, cal_month, _days_in_cal_month(cal_year, cal_month))
            rows.append(
                dict(
                    id=uuid.uuid4(),
                    fy_year=fy_year,
                    fy_month=fy_month,
                    calendar_year=cal_year,
                    calendar_month=cal_month,
                    period_start=start,
                    period_end=end,
                    is_locked=False,
                )
            )
    return rows


def build_weekly_periods() -> list[dict]:
    """Build Mon-Sun weekly periods spanning FY2023-FY2028.

    For weeks that cross a calendar-month boundary, fy_year/fy_month are set
    to the FY month containing the majority of the week's days.  The field
    days_this_week_in_fy_month counts how many of the 7 days fall within that
    majority FY month.
    """
    cal_start_year, cal_start_month = _fy_month_to_calendar(FY_START_YEAR, 1)
    range_start = date(cal_start_year, cal_start_month, 1)
    cal_end_year, cal_end_month = _fy_month_to_calendar(FY_END_YEAR, 12)
    range_end = date(
        cal_end_year, cal_end_month,
        _days_in_cal_month(cal_end_year, cal_end_month),
    )

    # Align to first Monday on or after range_start
    first_monday = range_start + timedelta(days=(7 - range_start.weekday()) % 7)

    rows: list[dict] = []
    current = first_monday
    while current <= range_end:
        week_end = current + timedelta(days=6)

        # Count days per FY month within this week
        fy_month_days: dict[tuple[int, int], int] = {}
        for offset in range(7):
            d = current + timedelta(days=offset)
            if d > range_end:
                break
            fy_y, fy_m, _ = _fy_for_date(d)
            key = (fy_y, fy_m)
            fy_month_days[key] = fy_month_days.get(key, 0) + 1

        # Majority FY month
        majority_key = max(fy_month_days, key=lambda k: fy_month_days[k])
        fy_year, fy_month = majority_key
        fy_quarter = (fy_month - 1) // 3 + 1
        days_this_week = fy_month_days[majority_key]

        # Total days in the majority FY month's calendar month
        maj_cal_year, maj_cal_month = _fy_month_to_calendar(fy_year, fy_month)
        days_in_month = _days_in_cal_month(maj_cal_year, maj_cal_month)

        label = current.strftime("%d%b").lstrip("0") + "-" + week_end.strftime("%d%b").lstrip("0")

        rows.append(
            dict(
                id=uuid.uuid4(),
                week_start_date=current,
                week_end_date=week_end,
                fy_year=fy_year,
                fy_month=fy_month,
                fy_quarter=fy_quarter,
                calendar_year=current.year,
                calendar_month=current.month,
                days_in_fy_month=days_in_month,
                days_this_week_in_fy_month=days_this_week,
                week_label=label,
            )
        )
        current += timedelta(days=7)

    return rows


async def seed() -> None:
    async with async_session_factory() as db:
        db: AsyncSession

        # ── Admin user ──────────────────────────────────────────────────────
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        if result.scalar_one_or_none() is None:
            db.add(
                User(
                    email=ADMIN_EMAIL,
                    hashed_password=hash_password(ADMIN_PASSWORD),
                    role=UserRole.admin,
                )
            )
            print(f"Created admin user: {ADMIN_EMAIL}")
        else:
            print(f"Admin user already exists: {ADMIN_EMAIL}")

        # ── Periods ─────────────────────────────────────────────────────────
        existing = await db.execute(select(Period.id).limit(1))
        if existing.scalar_one_or_none() is None:
            periods = build_periods()
            db.add_all([Period(**p) for p in periods])
            print(f"Seeded {len(periods)} periods (FY{FY_START_YEAR}-FY{FY_END_YEAR})")
        else:
            print("Periods already seeded, skipping")

        # ── Weekly periods ──────────────────────────────────────────────────
        existing = await db.execute(select(WeeklyPeriod.id).limit(1))
        if existing.scalar_one_or_none() is None:
            weeks = build_weekly_periods()
            db.add_all([WeeklyPeriod(**w) for w in weeks])
            print(f"Seeded {len(weeks)} weekly periods")
        else:
            print("Weekly periods already seeded, skipping")

        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
