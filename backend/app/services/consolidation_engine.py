"""Consolidation engine — maps je_lines through account_mappings and produces
consolidated actuals with IC elimination and BS validation.
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.consolidation import (
    ConsolidatedActual,
    ConsolidationRun,
    ConsolidationStatus,
)
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine

logger = logging.getLogger(__name__)

IC_TOLERANCE = Decimal("10.00")
BS_TOLERANCE = Decimal("1.00")


async def consolidate_period(fy_year: int, fy_month: int) -> uuid.UUID:
    """Run full consolidation for a single period.

    Steps:
      1. Fetch je_lines for all active entities
      2. Map through account_mappings (with multiplier + effective dates)
      3. IC elimination check
      4. Aggregate to group-level + entity-level
      5. Write consolidated_actuals
      6. Calculate subtotals via account hierarchy
      7. BS validation (assets ≈ liabilities + equity)

    Returns consolidation_run id.
    """
    run_id = uuid.uuid4()

    async with async_session_factory() as db:
        run = ConsolidationRun(
            id=run_id,
            period_id=uuid.uuid4(),  # placeholder, updated below
            status=ConsolidationStatus.running,
        )

        try:
            # ── Find period ──────────────────────────────────────────────
            result = await db.execute(
                select(Period).where(
                    Period.fy_year == fy_year,
                    Period.fy_month == fy_month,
                )
            )
            period = result.scalar_one_or_none()
            if period is None:
                raise ValueError(f"Period FY{fy_year} M{fy_month} not found")

            run.period_id = period.id
            db.add(run)
            await db.flush()

            # ── Load all accounts ────────────────────────────────────────
            result = await db.execute(select(Account).order_by(Account.sort_order))
            all_accounts = result.scalars().all()
            account_by_id: dict[uuid.UUID, Account] = {a.id: a for a in all_accounts}
            account_by_code: dict[str, Account] = {a.code: a for a in all_accounts}

            # ── Load active entities ─────────────────────────────────────
            result = await db.execute(
                select(Entity).where(Entity.is_active.is_(True))
            )
            entities = result.scalars().all()
            entity_ids = {e.id for e in entities}

            # ── Step 1: Fetch all je_lines for this period ───────────────
            result = await db.execute(
                select(JeLine).where(
                    JeLine.period_id == period.id,
                    JeLine.entity_id.in_(entity_ids),
                )
            )
            je_lines = result.scalars().all()
            logger.info(
                "Consolidating FY%dM%02d: %d je_lines across %d entities",
                fy_year, fy_month, len(je_lines), len(entities),
            )

            # ── Load account mappings (scoped to period dates) ───────────
            result = await db.execute(
                select(AccountMapping).where(
                    AccountMapping.effective_from <= period.period_end,
                )
            )
            all_mappings = result.scalars().all()

            mapping_lookup: dict[tuple[uuid.UUID, str], AccountMapping] = {}
            for m in all_mappings:
                if m.effective_to is not None and m.effective_to < period.period_start:
                    continue
                mapping_lookup[(m.entity_id, m.source_account_code)] = m

            # ── Step 2: Map je_lines → target accounts ───────────────────
            # entity_amounts[entity_id][account_code] = Decimal
            entity_amounts: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(
                lambda: defaultdict(Decimal)
            )
            unmapped_count = 0

            for jl in je_lines:
                key = (jl.entity_id, jl.source_account_code)
                mapping = mapping_lookup.get(key)
                if mapping is None:
                    unmapped_count += 1
                    continue
                target_acct = account_by_id.get(mapping.target_account_id)
                if target_acct is None:
                    continue
                multiplier = Decimal(str(mapping.multiplier))
                mapped_amount = Decimal(str(jl.amount)) * multiplier
                entity_amounts[jl.entity_id][target_acct.code] += mapped_amount

            if unmapped_count:
                logger.warning("%d je_lines had no account mapping", unmapped_count)

            # ── Step 3: IC elimination check ─────────────────────────────
            ic_alerts: list[str] = []

            mc_sales = Decimal("0")
            sh_62300 = Decimal("0")
            for eid, amounts in entity_amounts.items():
                for code, amt in amounts.items():
                    pass

            for m in all_mappings:
                if m.multiplier and Decimal(str(m.multiplier)) == Decimal("-1"):
                    eid = m.entity_id
                    src = m.source_account_code
                    if eid in entity_amounts and src in [
                        jl.source_account_code for jl in je_lines if jl.entity_id == eid
                    ]:
                        for jl in je_lines:
                            if jl.entity_id == eid and jl.source_account_code == src:
                                mc_sales += Decimal(str(jl.amount)) * Decimal(str(m.multiplier))

            for jl in je_lines:
                if jl.source_account_code == "62300":
                    sh_62300 += Decimal(str(jl.amount))

            if mc_sales != Decimal("0") or sh_62300 != Decimal("0"):
                ic_net = mc_sales + sh_62300
                if abs(ic_net) > IC_TOLERANCE:
                    alert = (
                        f"IC imbalance: MC Sales (mapped)={mc_sales}, "
                        f"SH 62300={sh_62300}, net={ic_net} (tolerance={IC_TOLERANCE})"
                    )
                    ic_alerts.append(alert)
                    logger.warning(alert)
                else:
                    logger.info(
                        "IC elimination OK: MC Sales=%s, SH 62300=%s, net=%s",
                        mc_sales, sh_62300, ic_net,
                    )

            # ── Step 4: Aggregate to group totals ────────────────────────
            group_amounts: dict[str, Decimal] = defaultdict(Decimal)
            for eid, amounts in entity_amounts.items():
                for code, amt in amounts.items():
                    group_amounts[code] += amt

            # ── Step 5: Write consolidated_actuals ───────────────────────
            await db.execute(
                delete(ConsolidatedActual).where(
                    ConsolidatedActual.period_id == period.id,
                )
            )

            now = datetime.now(timezone.utc)
            rows_written = 0

            for eid, amounts in entity_amounts.items():
                for code, amt in amounts.items():
                    acct = account_by_code.get(code)
                    if acct is None:
                        continue
                    db.add(ConsolidatedActual(
                        period_id=period.id,
                        account_id=acct.id,
                        entity_id=eid,
                        amount=float(amt),
                        is_group_total=False,
                        calculated_at=now,
                    ))
                    rows_written += 1

            for code, amt in group_amounts.items():
                acct = account_by_code.get(code)
                if acct is None:
                    continue
                db.add(ConsolidatedActual(
                    period_id=period.id,
                    account_id=acct.id,
                    entity_id=None,
                    amount=float(amt),
                    is_group_total=True,
                    calculated_at=now,
                ))
                rows_written += 1

            # ── Step 6: Calculate subtotals ──────────────────────────────
            subtotal_accounts = [a for a in all_accounts if a.is_subtotal and a.subtotal_formula]

            for acct in subtotal_accounts:
                formula = acct.subtotal_formula
                add_codes = formula.get("add", [])
                sub_codes = formula.get("subtract", [])
                total = Decimal("0")
                for c in add_codes:
                    total += group_amounts.get(c, Decimal("0"))
                for c in sub_codes:
                    total -= group_amounts.get(c, Decimal("0"))

                group_amounts[acct.code] = total

                result2 = await db.execute(
                    select(ConsolidatedActual).where(
                        ConsolidatedActual.period_id == period.id,
                        ConsolidatedActual.account_id == acct.id,
                        ConsolidatedActual.is_group_total.is_(True),
                    )
                )
                existing_row = result2.scalar_one_or_none()
                if existing_row:
                    existing_row.amount = float(total)
                else:
                    db.add(ConsolidatedActual(
                        period_id=period.id,
                        account_id=acct.id,
                        entity_id=None,
                        amount=float(total),
                        is_group_total=True,
                        calculated_at=now,
                    ))
                    rows_written += 1

            # ── Step 7: Trial balance validation ────────────────────────
            # Monthly activity TB: sum of ALL line items (IS + BS) = 0.
            # Compute raw IS total (non-subtotal IS accounts) and BS total.
            is_total = Decimal("0")
            bs_total = Decimal("0")
            for acct in all_accounts:
                if acct.is_subtotal:
                    continue
                amt = group_amounts.get(acct.code, Decimal("0"))
                if acct.statement and acct.statement.value == "is":
                    is_total += amt
                elif acct.statement and acct.statement.value == "bs":
                    bs_total += amt

            tb_variance = is_total + bs_total
            bs_balanced = abs(tb_variance) <= BS_TOLERANCE

            # Also compute conventional BS check for reporting
            total_assets = group_amounts.get("BS-TOTALASSETS", Decimal("0"))
            total_liab = group_amounts.get("BS-TOTALLIAB", Decimal("0"))
            total_equity = group_amounts.get("BS-TOTALEQUITY", Decimal("0"))
            bs_variance = total_assets - (total_liab + total_equity)

            if not bs_balanced:
                logger.warning(
                    "TB IMBALANCED: IS_total=%s, BS_total=%s, variance=%s",
                    is_total, bs_total, tb_variance,
                )
            else:
                logger.info(
                    "TB balanced (IS=%s + BS=%s = %s)",
                    is_total, bs_total, tb_variance,
                )

            # ── Finalise run ─────────────────────────────────────────────
            run.status = ConsolidationStatus.success
            run.bs_balanced = bs_balanced
            run.bs_variance = float(tb_variance)
            run.ic_alerts = "\n".join(ic_alerts) if ic_alerts else None
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Consolidation complete FY%dM%02d: %d rows, BS balanced=%s",
                fy_year, fy_month, rows_written, bs_balanced,
            )

        except Exception as exc:
            logger.exception("Consolidation failed FY%dM%02d", fy_year, fy_month)
            run.status = ConsolidationStatus.failed
            run.error_detail = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

    return run_id
