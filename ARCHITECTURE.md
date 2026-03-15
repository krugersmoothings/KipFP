# KipFP Architecture Guide

**Audience:** New developers joining the project
**Last updated:** 2026-03-15

---

## 1. What KipFP Does

KipFP is a financial planning and consolidation platform for a multi-entity pet care business (Kip & Co / Hanrob). It pulls trial balance data from NetSuite and Xero, pet-day operational data from BigQuery (PetBooking), maps everything to a canonical chart of accounts, consolidates across entities, and produces a 3-statement budget model (Income Statement, Balance Sheet, Cash Flow). The frontend provides dashboards, variance reporting, scenario analysis, site-level budgeting, and Excel exports including board-ready management packs.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        External Systems                          │
│  ┌──────────┐   ┌──────────┐   ┌────────────────────────────┐   │
│  │ NetSuite │   │   Xero   │   │ BigQuery (PetBooking)      │   │
│  │ (OAuth1) │   │ (OAuth2) │   │ (Service Account)          │   │
│  └────┬─────┘   └────┬─────┘   └────────────┬───────────────┘   │
└───────┼──────────────┼──────────────────────┼───────────────────┘
        │              │                      │
        ▼              ▼                      ▼
┌───────────────────────────────────────────────────────────────┐
│                     Connectors Layer                          │
│  netsuite.py (SuiteQL)  │  xero.py (Reports API)  │  bigquery.py │
└───────────────┬─────────┴──────────┬───────────────┴─────────┘
                │                    │
                ▼                    ▼
┌───────────────────────────────────────────────────────────────┐
│                      Sync Services                           │
│  netsuite_sync_service  │  xero_sync_service  │  bigquery_sync │
│        ↓ je_lines       │     ↓ je_lines      │  ↓ site_pet_days│
└───────────────┬─────────┴──────────┬───────────┴─────────────┘
                │                    │
                ▼                    ▼
┌───────────────────────────────────────────────────────────────┐
│                       PostgreSQL 15                           │
│  je_lines │ site_pet_days │ consolidated_actuals │ model_outputs│
│  accounts │ account_mappings │ entities │ periods │ locations  │
│  budget_versions │ model_assumptions │ debt_* │ wc_drivers     │
│  site_budget_* │ site_weekly_budget │ ic_elimination_rules     │
└───────────────┬───────────────────────────────────────────────┘
                │
    ┌───────────┴──────────────────────────────────┐
    │                                              │
    ▼                                              ▼
┌────────────────────┐              ┌──────────────────────────┐
│ Consolidation      │              │ Budget / Model Engine    │
│ Engine             │              │                          │
│ je_lines           │              │ site_budget_engine       │
│ → account_mappings │              │ → site_rollup_service    │
│ → IC elimination   │              │ → model_engine           │
│ → consolidated_    │              │   (IS, BS, CF)           │
│   actuals          │              │ → wc_engine              │
│                    │              │ → debt_engine            │
│                    │              │ → model_outputs          │
└────────┬───────────┘              └──────────┬───────────────┘
         │                                     │
         └──────────────┬──────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│                    FastAPI (port 8000)                        │
│  /api/v1/consolidated/*  │  /api/v1/budgets/*                │
│  /api/v1/dashboard/*     │  /api/v1/reports/*                │
│  /api/v1/analytics/*     │  /api/v1/scenarios/*              │
│  /api/v1/sync/*          │  /api/v1/pet-days/*               │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────┐
│                    React Frontend (port 3000)                 │
│  Dashboard │ P&L │ BS │ Blended PL │ Cash Flow │ Budget      │
│  Variance  │ Scenarios │ Analytics │ Site Budgets │ Admin     │
└───────────────────────────────────────────────────────────────┘
```

### Infrastructure (Docker Compose)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| db | postgres:15 | 5432 | Primary database |
| redis | redis:7-alpine | 6379 | Celery broker + result backend |
| backend | python:3.12-slim | 8000 | FastAPI + uvicorn |
| celery_worker | (same image) | — | Async task processing |
| celery_flower | (same image) | 5555 | Celery monitoring UI |
| frontend | node:20-alpine | 3000 | Vite dev server |

The `secrets/` directory (mounted read-only at `/app/secrets` in backend containers) holds `bigquery-sa.json` for BigQuery authentication. All other credentials come via `.env`.

---

## 3. Data Flow: Source Systems to Frontend

### 3.1 NetSuite Sync

```
NetSuite (SuiteQL API)
  │
  │  OAuth 1.0a Token-Based Auth (HMAC-SHA256)
  │  GET /services/rest/query/v1/suiteql
  │
  ▼
netsuite.py connector
  │  get_trial_balance(subsidiary_id, year, month)
  │  Returns: [{account_code, account_name, amount, class_name}, ...]
  │
  ▼
netsuite_sync_service.py
  │  1. Creates SyncRun record
  │  2. Converts FY month → calendar month (Australian FY: Jul=M1, Jun=M12)
  │  3. Calls connector
  │  4. For each row:
  │     - Looks up class_name to set is_aasb16 flag
  │     - Upserts into je_lines (ON CONFLICT UPDATE)
  │  5. Updates SyncRun status
  │
  ▼
je_lines table
  Unique key: (entity_id, period_id, source_account_code, is_aasb16)
```

**FY-to-calendar conversion:** The business uses an Australian financial year (July–June). FY months 1–6 map to calendar months Jul–Dec of the prior calendar year. FY months 7–12 map to Jan–Jun of the FY year.

### 3.2 Xero Sync

```
Xero (Reports API)
  │
  │  OAuth 2.0 (authorization_code grant)
  │  Refresh token + tenant_id stored encrypted in api_credentials
  │
  ▼
xero.py connector
  │  get_trial_balance(from_date, to_date)
  │  Amount = Debit - Credit (debit-positive)
  │
  ▼
xero_sync_service.py
  │  Same flow as NetSuite sync
  │  is_aasb16 always False for Xero entities
  │
  ▼
je_lines table
```

### 3.3 BigQuery Sync (Pet Days)

```
BigQuery (petbooking-com-au.pbp_petbooking_prod)
  │
  │  Service account auth (JSON key file)
  │
  ▼
bigquery.py connector
  │  get_pet_days(date_from, date_to)  → daily counts by property + service type
  │  get_revenue(date_from, date_to)   → daily revenue (AUD)
  │  get_forward_bookings(as_at, weeks) → future bookings
  │
  ▼
bigquery_sync_service.py
  │  1. Loads PropertyMapping (BigQuery property_id → KipFP location_id)
  │  2. Upserts into site_pet_days
  │
  ▼
site_pet_days table
  Unique key: (location_id, date, service_type)
  service_type: boarding, daycare, grooming, wash, training
```

### 3.4 Opening Balances

Opening balances represent the cumulative trial balance at the start of a financial year (June 30). They are stored in `je_lines` under a special `fy_month=0` period with `is_opening_balance=True`.

```
opening_balance_service.py
  │  NetSuite: get_trial_balance_as_at(subsidiary_id, year, 6)
  │  Xero:     get_trial_balance_at_date(as_at_date)
  │
  ▼
je_lines with period.fy_month=0, is_opening_balance=True
```

The consolidation engine processes M00 like any other period. Balance sheet queries include these periods when building cumulative balances.

### 3.5 Scheduled Syncs

| Task | Schedule | What it does |
|------|----------|-------------|
| `sync_all_netsuite` | 02:00 AEST daily | Syncs last 2 unlocked periods for all NetSuite entities |
| `sync_bigquery_nightly` | 03:00 AEST daily | Syncs last 90 days of pet day data |

After every NetSuite or Xero sync, `_trigger_auto_consolidation()` queues a consolidation task for the synced period.

---

## 4. The Consolidation Engine

The consolidation engine is the core of the actuals pipeline. It takes raw journal entry lines from multiple source systems and produces a unified, group-level view of the financials.

### 4.1 Pipeline

```
je_lines (raw source data, per entity)
  │
  │  1. Filter: active entities with consolidation_method='full'
  │  2. Filter: optionally exclude is_aasb16=True lines
  │
  ▼
account_mappings (source → target COA)
  │  - Match by (entity_id, source_account_code)
  │  - Apply effective_from / effective_to date filtering
  │  - Multiply amount by mapping.multiplier (default 1.0)
  │
  ▼
IC Elimination Check
  │  - Load ic_elimination_rules
  │  - For each rule pair (entity_a/account_a ↔ entity_b/account_b):
  │    check if amounts net to zero within tolerance
  │  - Flag alerts for mismatches
  │
  ▼
Aggregation
  │  - Sum mapped amounts per (period, target_account, entity)
  │  - Also compute group totals (entity_id=NULL, is_group_total=True)
  │
  ▼
Subtotals
  │  - Walk the COA looking for is_subtotal=True accounts
  │  - Apply subtotal_formula: {"add": ["REV-1","REV-2"], "subtract": ["COGS-1"]}
  │  - See Sign Convention section for how add/subtract work
  │
  ▼
BS Validation
  │  - Sum all IS account totals + BS account totals for the period
  │  - If near zero → balanced; otherwise log variance
  │
  ▼
consolidated_actuals table
  │  Per-entity rows + group total rows
  │  One row per (period, account, entity)
```

### 4.2 What Gets Written

Each consolidation run for a period:
1. **Deletes** existing `consolidated_actuals` for that period
2. **Inserts** one row per (entity, account) with the mapped amount
3. **Inserts** group-total rows (summed across entities, `is_group_total=True`)
4. **Inserts** subtotal rows based on `subtotal_formula`
5. **Creates** a `consolidation_runs` record with BS variance and IC alerts

---

## 5. Sign Convention

This is the single most important concept to understand. Getting it wrong breaks every financial number in the system.

### 5.1 Storage: Debit-Positive (Credit-Normal)

All monetary amounts in `je_lines`, `consolidated_actuals`, and `model_outputs` follow the **debit-positive** convention:

| Account Type | Stored Sign | Example |
|-------------|-------------|---------|
| Revenue (income) | **Negative** | -$500,000 means $500K revenue |
| COGS | **Positive** | +$200,000 means $200K cost of goods |
| Operating expenses | **Positive** | +$100,000 means $100K expense |
| Assets (debit-normal) | **Positive** | +$1,000,000 means $1M in assets |
| Liabilities (credit-normal) | **Negative** | -$800,000 means $800K in liabilities |
| Equity (credit-normal) | **Negative** | -$200,000 means $200K equity |

This is standard accounting double-entry storage. Revenue is a credit (negative), expenses are debits (positive).

### 5.2 Display: User-Facing Sign Flip

For display and Excel export, signs are flipped so users see intuitive positive numbers:

- **Income Statement:** All accounts multiply by `-1.0`. Revenue (stored as -500K) displays as +500K. Expenses (stored as +100K) display as -100K. This means revenue appears positive and expenses appear negative on the P&L.

- **Balance Sheet:** Per-account sign based on `Account.normal_balance`:
  - Assets (debit-normal): multiply by `+1.0` (no flip)
  - Liabilities (credit-normal): multiply by `-1.0` (stored as -800K, displays as +800K)
  - Equity (credit-normal): multiply by `-1.0`

The display sign logic lives in `_display_sign()` in `backend/app/api/consolidation.py`.

### 5.3 Subtotals: The Tricky Part

Both the consolidation engine and model engine compute subtotals using `subtotal_formula` with `add` and `subtract` lists.

**For IS (P&L) accounts:** "Subtract" codes are **added** (not subtracted), because the credit-normal storage already carries the correct sign. Revenue is negative, expenses are positive — summing them naturally produces the right P&L cascade (Gross Margin = Revenue + COGS, where revenue is negative and COGS is positive → GM is negative → correct after display flip).

**For BS accounts:** "Subtract" codes are genuinely subtracted.

### 5.4 Variance

In `reports.py`, `_compute_variance` compares raw credit-normal values:
- `is_favourable = actual < budget` works for both income (more negative = higher revenue = favourable) and expenses (lower positive = less cost = favourable)
- The variance export applies `sign = -1.0` so exported numbers match the display convention

---

## 6. Balance Sheet Cumulative Logic

The balance sheet differs fundamentally from the income statement in how periods work.

### 6.1 The Problem

An income statement shows **activity during a period** (revenue earned in January). A balance sheet shows **point-in-time balances** (total cash as at January 31). The `consolidated_actuals` table stores **monthly movements** (changes during each month), not cumulative balances. The BS display must reconstruct cumulative balances.

### 6.2 How It Works

The API endpoint `GET /consolidated/bs` calls `_get_bs_statement()` which:

1. Calls `_load_all_periods_through()` to load ALL historical periods from the earliest in the database through the selected month — including `fy_month=0` opening balance periods from prior years.

2. Queries `consolidated_actuals` for ALL those periods.

3. Sums amounts cumulatively to produce point-in-time balances.

**Single-month view:** Two columns — the month's movement and the cumulative "Balance" at month-end.

**Full-year view:** Each monthly column shows the cumulative balance at that month-end (a running total across all historical periods).

### 6.3 Opening Balances

Each financial year can have a `fy_month=0` Period representing the cumulative trial balance at FY start (June 30). These are imported via `opening_balance_service.py` and processed through consolidation like any other period. They form the starting point for BS cumulative calculations.

---

## 7. The Budget / Model Engine

The model engine produces a forward-looking 3-statement financial model. It has two paths: top-down (entity-level assumptions) and bottom-up (site-level pet-day-driven budgets that roll up).

### 7.1 Site Budget Engine (Bottom-Up)

```
site_pet_days (actual data from BigQuery)
  │
  ▼
site_budget_assumptions (per site: growth rates, prices, fixed costs)
  │
  ▼
site_budget_engine.py: calculate_site_weekly_budget()
  │  For each week:
  │    - Prior year pet days (from site_pet_days)
  │    - Budget pet days = prior year × (1 + pet_day_growth_pct)
  │    - Revenue = pet_days × avg_price × (1 + price_growth_pct) + bath + services
  │    - Labour = max(mpp_mins × pet_days, min_daily_hours × 7) × wage_rate
  │    - COGS = revenue × cogs_pct
  │    - Fixed costs prorated from monthly: rent, utilities, R&M, IT, general
  │    - Advertising = revenue × advertising_pct_revenue
  │
  ▼
site_weekly_budget table (52 weeks × 38 sites)
  │
  ▼
site_rollup_service.py
  │  - Aggregates weekly → monthly (prorated by days_this_week_in_fy_month / 7)
  │  - Groups by entity + month + line item
  │  - Writes model_assumptions with keys like "site_rollup.revenue", "site_rollup.wages"
  │
  ▼
model_assumptions table (entity-level monthly values)
```

### 7.2 Model Engine (3-Statement)

```
model_assumptions (from site rollup + manual entry)
  │
  ▼
model_engine.py: run_model()
  │
  │  Calculation order:
  │  ┌─────────────────────────────────────────────┐
  │  │  1. Revenue (manual amount or growth rate)   │
  │  │  2. COGS (% of revenue or manual)            │
  │  │  3. Operating expenses                       │
  │  │  4. EBITDA = Rev + COGS + Opex              │
  │  │  5. Working capital (wc_engine)              │
  │  │  6. Debt waterfall (debt_engine)             │
  │  │  7. D&A                                      │
  │  │  8. EBIT → NPBT → Tax → NPAT               │
  │  │  9. Cash flow (indirect method)              │
  │  │  10. Balance sheet assembly + validation      │
  │  └─────────────────────────────────────────────┘
  │
  ▼
model_outputs table
  Unique key: (version_id, period_id, account_id, entity_id)
```

### 7.3 Working Capital Engine

Calculates working capital movements based on driver types:

| Driver | Formula |
|--------|---------|
| DSO (Days Sales Outstanding) | Receivables = DSO × (Revenue / days_in_month) |
| DPO (Days Payable Outstanding) | Payables = DPO × (COGS / days_in_month) |
| DII (Days Inventory Investment) | Inventory = DII × (COGS / days_in_month) |
| Fixed Balance | Constant amount each period |
| % of Revenue | Balance = Revenue × (base_days / 100) |

Seasonal factors can override base_days per month. Returns closing balances and period-to-period movements.

### 7.4 Debt Engine

Processes each `DebtFacility` through a monthly waterfall:

```
For each period:
  opening_balance = prior period closing (or facility.opening_balance for M1)
  interest = opening_balance × annual_rate / 12
  repayment = based on amort_type:
    - interest_only: 0
    - principal_and_interest: monthly_repayment - interest
    - bullet: full balance at maturity
  closing_balance = opening - repayment + drawdown
```

Debt facilities are auto-discovered from `BS-DEBT-*` accounts in the canonical COA, with opening balances seeded from `consolidated_actuals`.

---

## 8. AASB16 Approach

AASB16 is the Australian accounting standard for leases. Under AASB16, operating leases are capitalised on the balance sheet (right-of-use assets + lease liabilities), and P&L shows depreciation + interest instead of rent expense. This creates a "statutory" vs "management" view distinction.

### 8.1 How AASB16 Lines Are Identified

During NetSuite sync, the `class_name` field from the trial balance is checked. Lines tagged with AASB16-related classes (e.g., "AASB16 Lease") have `is_aasb16=True` set on the `je_lines` record.

Xero entities always have `is_aasb16=False` (Xero doesn't use AASB16 classification).

### 8.2 The Toggle

The frontend has a global toggle (`Aasb16Toggle.tsx`) in the top bar, managed by `useAppStore.includeAasb16`. When toggled off:

1. **Axios interceptor** adds `include_aasb16=false` as a query parameter on every GET request
2. **Backend endpoints** receive this parameter and either:
   - Filter `je_lines` to exclude `is_aasb16=True` rows during consolidation queries, or
   - Use `compute_aasb16_by_account_period()` helpers to subtract AASB16 adjustments from consolidated totals

### 8.3 The AASB16 Helpers

`aasb16_helpers.py` provides two functions:

- `compute_aasb16_by_account_period(db, period_ids)` — Returns `{account_id: {period_id: amount}}` for all AASB16 adjustments. Only returns leaf-level accounts.

- `compute_aasb16_per_period_with_entities(...)` — Same but broken down by entity, used for entity-level drill-downs.

For KPI subtotals (like EBITDA), the analytics endpoints use `_resolve_aasb16_for_account()` which recursively walks `subtotal_formula` trees to sum leaf-level adjustments — necessary because the helpers don't compute subtotals directly.

### 8.4 Important Detail

The `consolidated_actuals` table stores the full (AASB16-inclusive) view. The ex-lease view is computed on-the-fly by subtracting AASB16 amounts. There is no separate storage for the ex-lease view. The sign convention for AASB16 subtract items on IS accounts follows the same rule as regular subtotals (items listed under "subtract" are added, not subtracted, because credit-normal values already carry their sign).

---

## 9. The Canonical Chart of Accounts

The COA is stored in the `accounts` table and represents the group-wide target structure. Every source account from NetSuite or Xero is mapped to one of these target accounts via `account_mappings`.

### 9.1 Account Structure

| Field | Purpose |
|-------|---------|
| `code` | e.g., `REV-BOARDING`, `COGS-FOOD`, `BS-CASH`, `CF-OPERATING` |
| `account_type` | income, cogs, opex, depreciation, interest, tax, asset, liability, equity |
| `statement` | is (Income Statement), bs (Balance Sheet), cf (Cash Flow) |
| `normal_balance` | debit or credit — determines display sign for BS accounts |
| `is_subtotal` | True for aggregate rows (e.g., Gross Margin, EBITDA, Total Assets) |
| `subtotal_formula` | JSONB: `{"add": [...codes], "subtract": [...codes]}` |
| `sort_order` | Controls display ordering in reports |
| `parent_account_id` | Hierarchical nesting for indent levels |

### 9.2 Account Mappings

Each entity has its own set of mappings from source account codes to target accounts:

```
Entity: SH (Staying Hydrated Pty Ltd)
  Source: "4000 - Sales Revenue"  →  Target: REV-BOARDING  (multiplier: 1.0)
  Source: "5100 - Direct Labour"  →  Target: COGS-LABOUR   (multiplier: 1.0)

Entity: MC (Management Co)
  Source: "Revenue"               →  Target: REV-MGMT-FEE  (multiplier: 1.0)
```

Mappings have optional `effective_from` / `effective_to` dates for handling COA changes over time.

---

## 10. Frontend Architecture

### 10.1 Tech Stack

- **React 18** + TypeScript 5.6 + Vite 6
- **React Router 7** for routing
- **TanStack React Query** for server state
- **Zustand** for client state (4 stores)
- **Axios** for HTTP (single instance with interceptors)
- **Tailwind CSS** + Radix UI for styling
- **Recharts** for charts

### 10.2 State Management

| Store | Key State | Purpose |
|-------|-----------|---------|
| `auth` | `token`, `user` | JWT token in localStorage, user profile |
| `period` | `fyYear`, `fyMonth`, `dataPreparedToFyYear/Month` | Global period selection and last-closed-month |
| `app` | `includeAasb16` | AASB16 toggle state |
| `budget` | `activeVersionId` | Selected budget version |

Server state (API data) is managed entirely through React Query. The Zustand stores only hold UI/session state.

### 10.3 API Layer

A single Axios instance (`frontend/src/utils/api.ts`) with:
- **Request interceptor:** Adds Bearer token from localStorage; injects `include_aasb16=false` on GET requests when toggle is off
- **Response interceptor:** Catches 401 → clears token → redirects to `/login`
- **Base URL:** `http://localhost:8000` (hardcoded for local dev)

All API calls happen inline in components via `useQuery`/`useMutation` — there is no separate hooks layer.

### 10.4 Route Structure and Roles

Routes are nested under `AppLayout` which provides the sidebar and top bar. Role-based access is enforced by `RoleGuard`:

| Role Level | Access |
|-----------|--------|
| `viewer` | Dashboard, Consolidated P&L/BS, Analytics |
| `finance` | Everything viewer sees + Budget, Variance, Scenarios, Blended P&L, Cash Flow, Sync Status |
| `admin` | Everything + User Management, COA Mapping, Connections, Trigger Sync, Run Consolidation |

### 10.5 Key Components

- **`FinancialTable`** — The workhorse component. Renders `FinancialRow[]` with period columns, entity breakdown, variance highlighting, compact mode, indent levels, and drill-down click handler. Used on P&L, BS, budget output, and variance pages.

- **`DrillDownModal`** — Slide-over panel showing entity-level breakdown for a clicked cell. Each entity row links to the corresponding NetSuite trial balance report.

- **`PeriodSelector`** — Single "Jan-26" style month picker. Controls the global period used across all pages.

- **`Aasb16Toggle`** — Global toggle in the top bar. Controls whether AASB16 lease adjustments are included in all financial views.

- **`AppLayout`** — Sidebar navigation (role-filtered), top bar with PeriodSelector + Aasb16Toggle, content outlet.

---

## 11. Celery Task Architecture

All long-running operations (sync, consolidation, model calculation) run as Celery tasks to avoid blocking the API.

```
Frontend                 FastAPI                  Celery Worker
   │                        │                         │
   │  POST /sync/netsuite   │                         │
   ├───────────────────────>│                         │
   │                        │  sync_entity_task.delay()│
   │                        ├────────────────────────>│
   │  { sync_run_id }       │                         │
   │<───────────────────────│                         │
   │                        │                         │ NetSuite API call
   │                        │                         │ Upsert je_lines
   │                        │                         │ Auto-consolidate
   │                        │                         │
   │  GET /sync/runs        │                         │
   ├───────────────────────>│  Query SyncRun table    │
   │  [{ status: "success"}]│                         │
   │<───────────────────────│                         │
```

Key tasks:
- `sync_entity_task` / `sync_xero_entity_task` — Sync a single entity+period
- `consolidate_period_task` — Run consolidation for a period
- `sync_bigquery_task` — Sync pet day data
- `calculate_all_sites_task` — Calculate all site budgets, rollup, then model
- `run_model_task` — Run the 3-statement model for a budget version

---

## 12. Reporting and Export

### 12.1 Variance Report

Compares actuals (from `consolidated_actuals`) against budget (from `model_outputs`) for the same period. Shows monthly, YTD, and full-year views. Commentary can be attached to specific account/period cells by finance+ users. Export produces Excel with display-sign-corrected values.

### 12.2 Scenarios

Scenarios are cloned budget versions. Creating a scenario copies all `model_assumptions` and `wc_drivers` from the base version, then runs the model. Users can modify individual assumptions and re-run. The compare view shows up to 5 scenarios side-by-side with delta columns.

### 12.3 Management Pack

Board-ready Excel workbook generated via `POST /reports/management-pack`. Contains:
- Income Statement (with GM%/EBITDA%/NPAT% margins across multiple years)
- Balance Sheet (cumulative at reporting dates)
- Cash Flow (indirect method)
- Entity Summary (one row per entity)
- Assumptions (from model_assumptions)
- Per-entity standalone IS/BS sheets

Formatted with navy headers, subtotal shading, red negatives, freeze panes, and coloured tabs.

### 12.4 Analytics

- **Time Series:** Revenue, Gross Margin, EBITDA, and other metrics over time. Supports multi-metric overlay, rolling 3m/12m averages, prior-year comparison, and entity filtering.

- **Location Performance:** Site-level P&L with state filtering, sorting, expandable rows with sparkline charts. Supports monthly and full-year views.

---

## 13. Database Migration History

| Migration | Description |
|-----------|-------------|
| 0001 | `users` table |
| 0002 | Core schema: entities, periods, accounts, account_mappings, sync_runs, je_lines, locations, budget_versions, model_assumptions, wc_drivers, debt_facilities, debt_schedules, site_budget_entries, weekly_periods |
| 0003 | Unique constraint on je_lines (entity, period, source_account_code) |
| 0004 | api_credentials, consolidated_actuals, consolidation_runs |
| 0005 | model_outputs, CF pseudo-accounts |
| 0006 | report_commentary |
| 0007 | `is_aasb16` flag on je_lines, updated unique constraint |
| 0008 | ic_elimination_rules |
| 0009 | property_mappings (BigQuery → KipFP locations) |
| 0010 | site_pet_days |
| 0011 | site_budget_assumptions, site_weekly_budget |
| 0012 | `is_opening_balance` on je_lines |

---

## 14. Key Directories

```
KipFP/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── connectors/       # NetSuite, Xero, BigQuery clients
│   │   ├── core/             # Settings, security, dependencies
│   │   ├── db/
│   │   │   └── models/       # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic engines
│   │   ├── main.py           # FastAPI app setup + router registration
│   │   └── worker.py         # Celery app + tasks + schedules
│   ├── alembic/
│   │   └── versions/         # Database migrations
│   ├── scripts/              # One-off seed and sync scripts
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/       # Shared UI components
│   │   │   └── layout/       # AppLayout, sidebar
│   │   ├── pages/            # Route pages
│   │   │   ├── budget/       # Budget assumptions, debt, sites, output
│   │   │   ├── financials/   # P&L, BS, BlendedPL, CashFlow
│   │   │   ├── consolidation/# Run consolidation
│   │   │   ├── analytics/    # TimeSeries, LocationPerformance
│   │   │   ├── reports/      # Variance
│   │   │   ├── scenarios/    # ScenarioList, ScenarioCompare
│   │   │   ├── admin/        # Users, Connections, CoaMapping
│   │   │   └── sync/         # SyncRuns, TriggerSync
│   │   ├── stores/           # Zustand state stores
│   │   ├── types/            # TypeScript interfaces
│   │   └── utils/            # API client (Axios)
│   ├── package.json
│   └── vite.config.ts
├── secrets/                  # BigQuery SA key (gitignored)
├── docker-compose.yml
├── .env                      # Environment variables (gitignored)
├── ARCHITECTURE.md           # This file
├── CLAUDE_CONTEXT.md         # AI session context
└── BUGS.md                   # Bug audit report
```

---

## 15. Common Tasks for New Developers

### Running locally

```bash
docker compose up --build
```

Then visit http://localhost:3000. Backend API docs at http://localhost:8000/docs.

### Running a sync

From the frontend (as admin): go to Sync Status → click "Sync Now" on an entity.
Or via API: `POST /api/v1/sync/netsuite/{entity_id}` with `{"fy_year": 2026, "fy_month": 7}`.

### Running consolidation

Admin page: Consolidation → Run. Or `POST /api/v1/consolidate/2026/7`.

### Running the model

Budget Output page → "Calculate" button. Or `POST /api/v1/budgets/{version_id}/calculate`.

### Database migrations

```bash
docker compose exec backend alembic upgrade head
```

### Seeding data

Scripts in `backend/scripts/` are one-off seeders run via:
```bash
docker compose exec backend python -m scripts.seed_initial
```

### Checking Celery tasks

Visit http://localhost:5555 (Flower dashboard) to monitor task execution.
