# KipFP — Architecture

> Financial planning, consolidation, and budgeting platform for the Kip Group of Companies.

---

## 1. What This Is

KipFP is an internal finance tool that pulls trial-balance data from **NetSuite** and **Xero**, maps it to a unified chart of accounts, consolidates across 10+ Australian entities, and produces group-level financial statements. On top of actuals it layers a **three-statement budget model** (Income Statement, Balance Sheet, Cash Flow) with working-capital schedules, debt waterfalls, and site-level budgets that roll up to entity totals.

Everything runs on an Australian financial year (1 Jul – 30 Jun) in AUD.

---

## 2. High-Level Architecture

```
┌────────────┐   ┌────────────┐
│  NetSuite  │   │    Xero    │
│ (OAuth 1)  │   │ (OAuth 2)  │
└─────┬──────┘   └─────┬──────┘
      │                 │
      ▼                 ▼
┌─────────────────────────────────────────┐
│            FastAPI  Backend             │
│  ┌──────────┐  ┌────────────────────┐   │
│  │Connectors│→ │    je_lines        │   │
│  └──────────┘  └────────┬───────────┘   │
│                         │ account       │
│                         │ mappings      │
│                         ▼               │
│                ┌────────────────────┐   │
│                │consolidated_actuals│   │
│                └────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │  Budget Model Engine            │    │
│  │  assumptions → IS → BS → CF     │    │
│  │  + WC engine  + debt engine     │    │
│  │  + site rollup                  │    │
│  └─────────────────────────────────┘    │
│                                         │
│  Celery workers  ←──  Redis             │
└──────────────┬──────────────────────────┘
               │
          PostgreSQL 15
               │
┌──────────────┴──────────────────────────┐
│          React / Vite Frontend          │
│  Zustand · TanStack Query · Tailwind   │
└─────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **API** | FastAPI + Uvicorn | Async-native, automatic OpenAPI docs, Pydantic validation |
| **ORM** | SQLAlchemy 2.0 (async) | Mature, async support via `asyncpg`, declarative models |
| **Database** | PostgreSQL 15 | JSONB for flexible assumption values, reliable, good async driver |
| **Migrations** | Alembic | SQLAlchemy's companion tool, autogenerate from models |
| **Task queue** | Celery + Redis | Long-running syncs and model calculations off the request path |
| **Auth** | JWT (python-jose) + bcrypt | Stateless tokens, simple role-based access |
| **Frontend** | React 18 + TypeScript + Vite | Fast dev, type safety, instant HMR |
| **Styling** | Tailwind CSS + shadcn/ui pattern | Utility-first, Radix primitives for accessible components |
| **State** | Zustand (client) + TanStack Query (server) | Minimal boilerplate; Query handles cache, refetch, polling |
| **HTTP client** | Axios | Interceptors for auth token and 401 handling |
| **Containers** | Docker Compose | One command to spin up Postgres, Redis, backend, workers, frontend |

---

## 4. Backend Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router mounting
│   ├── worker.py             # Celery app + task definitions
│   ├── core/
│   │   ├── config.py         # Pydantic Settings (DB, Redis, JWT, API creds)
│   │   ├── deps.py           # get_db, get_current_user, require_role
│   │   └── auth.py           # password hashing, JWT create/decode
│   ├── api/                  # Route handlers (one file per domain)
│   │   ├── health.py
│   │   ├── auth.py           # login, /me, refresh
│   │   ├── admin.py          # user creation
│   │   ├── auth_xero.py      # Xero OAuth flow
│   │   ├── sync.py           # trigger syncs, list runs
│   │   ├── consolidation.py  # trigger consolidation, IS/BS endpoints
│   │   ├── entities.py
│   │   ├── dashboard.py      # KPIs
│   │   └── budget.py         # full budget CRUD
│   ├── db/
│   │   ├── base.py           # engine, session factory, Base
│   │   └── models/           # one file per domain (see Data Model)
│   ├── schemas/              # Pydantic request/response models
│   ├── services/             # Business logic engines
│   │   ├── consolidation_engine.py
│   │   ├── model_engine.py   # three-statement model
│   │   ├── wc_engine.py      # working capital schedule
│   │   ├── debt_engine.py    # debt waterfall
│   │   ├── site_rollup_service.py
│   │   ├── netsuite_sync_service.py
│   │   └── xero_sync_service.py
│   └── connectors/           # External API clients
│       ├── netsuite.py       # OAuth 1.0a, SuiteQL
│       └── xero.py           # OAuth 2.0, Fernet-encrypted creds
├── alembic/                  # Migrations (0001–0005)
├── scripts/                  # Seed data, one-off sync/fix scripts
└── requirements.txt
```

### API Routes (all under `/api/v1`)

| Area | Key Endpoints |
|------|--------------|
| **Auth** | `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh` |
| **Admin** | `POST /admin/users` |
| **Xero OAuth** | `GET /auth/xero/connect`, `GET /auth/xero/callback` |
| **Sync** | `POST /sync/netsuite/{entity_id}`, `POST /sync/xero/{entity_id}`, `GET /sync/runs` |
| **Consolidation** | `POST /consolidate/{fy_year}/{fy_month}`, `GET /consolidated/is`, `GET /consolidated/bs` |
| **Dashboard** | `GET /dashboard/kpis` |
| **Entities** | `GET /entities` |
| **Budget** | `GET/POST /budgets/`, `GET/PUT /budgets/{id}/assumptions`, `GET/PUT /budgets/{id}/wc-drivers`, `GET/PUT /budgets/{id}/debt/facilities/{fid}`, `GET/PUT /budgets/{id}/sites/{location_id}`, `GET /budgets/{id}/site-rollup`, `POST /budgets/{id}/calculate`, `GET /budgets/{id}/output/{is\|bs\|cf}` |

### Roles

Three roles enforced via `require_role` dependency:

| Role | Access |
|------|--------|
| `admin` | Everything including user creation, sync triggers |
| `finance` | Budget editing, consolidation |
| `viewer` | Read-only dashboards and statements |

---

## 5. Frontend Structure

```
frontend/src/
├── main.tsx                 # React root, QueryClientProvider
├── App.tsx                  # Router, route guards
├── utils/api.ts             # Axios instance with auth interceptor
├── lib/utils.ts             # cn() for Tailwind class merging
├── types/api.ts             # TypeScript interfaces for API responses
├── stores/
│   ├── auth.ts              # token, user, login/logout
│   ├── period.ts            # FY year + month selector state
│   └── budget.ts            # active budget version ID
├── components/
│   ├── layout/AppLayout.tsx # sidebar, header, period selector
│   ├── FinancialTable.tsx   # reusable expandable financial table
│   ├── PeriodSelector.tsx   # FY year/month dropdowns
│   ├── RoleGuard.tsx        # role-based route protection
│   └── ui/                  # shadcn-style primitives (Button, Card, Input, Label)
└── pages/
    ├── Login.tsx
    ├── Dashboard.tsx         # KPIs + condensed P&L
    ├── Unauthorised.tsx
    ├── financials/
    │   ├── IncomeStatement.tsx
    │   └── BalanceSheet.tsx
    ├── sync/
    │   ├── SyncRuns.tsx
    │   └── TriggerSync.tsx
    ├── consolidation/
    │   └── RunConsolidation.tsx
    ├── budget/
    │   ├── Assumptions.tsx    # budget assumptions by entity/period
    │   ├── WorkingCapital.tsx # DSO, DPO, DII drivers
    │   ├── DebtSchedule.tsx   # debt facilities and amortisation
    │   ├── SiteBudget.tsx     # weekly site-level entry
    │   └── Output.tsx         # calculated IS/BS/CF
    └── admin/
        ├── Users.tsx
        ├── Connections.tsx
        └── Entities.tsx
```

### Key Patterns

- **Route guards**: `ProtectedRoute` checks for JWT token; `PublicOnly` redirects authenticated users away from login; `RoleGuard` enforces minimum role level.
- **Server state**: TanStack Query handles all API data — caching, refetch, polling (e.g. budget calculation status polls every 2 s).
- **Client state**: Zustand stores for auth, period selection, and active budget version. No Redux or Context API.
- **Financial tables**: A shared `FinancialTable` component renders rows with expandable entity-level breakdowns, variance highlighting, and compact mode. Used across Dashboard, IS, BS, and Budget Output.

---

## 6. Data Model

### Core Financial Tables

```
entities
  id, code, name, source_system (netsuite|xero), consolidation_method (full|none)

periods
  id, fy_year, fy_month (1–12 where 1=Jul), period_start, period_end

weekly_periods
  id, week_start_date, fy_month, days_this_week_in_fy_month

accounts
  id, code, name, account_type (revenue|cogs|opex|asset|liability|equity|cf_ops|cf_inv|cf_fin),
  statement (IS|BS|CF), subtotal_formula
```

### Data Pipeline Tables

```
je_lines
  entity_id, period_id, source_account_code, amount
  UNIQUE(entity_id, period_id, source_account_code)  ← upsert-safe

account_mappings
  entity_id, source_account_code → target_account_id, multiplier

consolidated_actuals
  period_id, account_id, entity_id, amount, is_group_total

consolidation_runs
  period_id, status, bs_balanced, ic_alerts
```

### Budget Tables

```
budget_versions
  id, name, fy_year, version_type (budget|forecast|scenario), status (draft|approved|locked)

model_assumptions
  budget_version_id, entity_id, assumption_key, assumption_value (JSONB)
  Keys: revenue, cogs, opex_salaries, opex_rent, opex_marketing, opex_other,
        depreciation, tax_rate, capex, other_income

model_outputs
  version_id, period_id, account_id, entity_id, amount

wc_drivers
  budget_version_id, entity_id, account_id, driver_type (dso|dpo|dii|fixed|pct_revenue),
  base_days, seasonal_factors (JSONB)

debt_facilities
  id, code, entity_id, opening_balance, base_rate, margin,
  amort_type (straight_line|bullet|custom), amort_periods, facility_type

debt_schedules
  facility_id, period_id, opening_balance, interest, repayment, closing_balance

locations
  id, code, name, entity_id, state, capacity_dogs

site_budget_entries
  version_id, location_id, model_line_item, week_id, amount
```

### Auth & Integration

```
users
  id, email, hashed_password, role (admin|finance|viewer), is_active

api_credentials
  id, service, credential_key, credential_value (Fernet-encrypted for Xero)

sync_runs
  id, entity_id, source_system, status, started_at, finished_at, records_upserted, error_message
```

### Entity-Relationship Summary

```
entity ──┬── je_lines ──→ (mapped via account_mappings) ──→ consolidated_actuals
         ├── locations ──→ site_budget_entries
         ├── model_assumptions
         ├── model_outputs
         ├── wc_drivers
         └── debt_facilities ──→ debt_schedules

budget_version ──┬── model_assumptions
                 ├── model_outputs
                 ├── wc_drivers
                 └── site_budget_entries

period ──┬── je_lines
         ├── consolidated_actuals
         ├── model_outputs
         ├── debt_schedules
         └── weekly_periods
```

---

## 7. Key Data Flows

### 7.1 Actuals: Source → Consolidated Statements

1. **Sync** — Celery task calls NetSuite (SuiteQL via OAuth 1.0a) or Xero (REST via OAuth 2.0) to fetch a trial balance for an entity + period.
2. **je_lines** — Raw amounts are upserted (unique on entity + period + source account code) so re-syncs are idempotent.
3. **Account mapping** — `account_mappings` translates source account codes to the unified chart of accounts, applying a sign multiplier where needed.
4. **Consolidation** — `consolidation_engine` reads `je_lines`, applies mappings, writes `consolidated_actuals` per entity and a group-total row. Checks for intercompany imbalances and balance-sheet balance.
5. **Presentation** — The frontend fetches `/consolidated/is` or `/consolidated/bs`, which returns `FinancialRow[]` with entity-level breakdowns.

### 7.2 Budget: Assumptions → Three-Statement Output

1. **Assumptions** — Users enter monthly assumptions per entity (revenue growth, COGS %, opex line items, tax rate, capex, depreciation). Stored as JSONB in `model_assumptions`.
2. **Site budgets** (optional) — Weekly granularity per location. `site_rollup_service` aggregates site entries into entity-level `model_assumptions`, replacing the manual assumptions for those line items.
3. **Working capital** — `wc_engine` calculates receivables, payables, and inventory from driver types (DSO, DPO, DII, fixed, pct_revenue) with seasonal factors.
4. **Debt** — `debt_engine` calculates interest, repayments, and closing balances per facility per period.
5. **Model engine** — `model_engine` runs a 10-step calculation:
   - Revenue → COGS → Gross Profit
   - Opex lines → EBITDA
   - Depreciation → EBIT → Tax → Net Income
   - Working capital movements → Operating cash flow
   - Capex → Investing cash flow
   - Debt service → Financing cash flow
   - Opening cash + net cash movement → Closing cash
   - Balance sheet assembly
6. **model_outputs** — Results written per period × account × entity. The frontend renders IS, BS, and CF tabs.

### 7.3 Scheduled Sync

A Celery beat schedule runs `sync_all_netsuite` daily at 02:00 AEST to keep actuals current.

---

## 8. Infrastructure

### Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | postgres:15 | 5432 | Primary database |
| `redis` | redis:7-alpine | 6379 | Celery broker + result backend |
| `backend` | Custom (Python) | 8000 | FastAPI + Uvicorn |
| `celery_worker` | Same as backend | — | Async task execution |
| `celery_flower` | Same as backend | 5555 | Task monitoring UI |
| `frontend` | Custom (Node 20) | 3000 | Vite dev server |

### Migrations

Alembic migrations live in `backend/alembic/versions/`. Five migrations so far:

1. `0001` — `users` table
2. `0002` — All core tables (entities, periods, accounts, locations, budget_versions, mappings, sync_runs, je_lines, model_assumptions, wc_drivers, debt, site_budget_entries)
3. `0003` — Unique constraint on `je_lines` (entity, period, source_account_code)
4. `0004` — `api_credentials`, `consolidated_actuals`, `consolidation_runs`
5. `0005` — `model_outputs` table and cash-flow pseudo-accounts in `accounts`

### Seed Scripts

| Script | What it seeds |
|--------|--------------|
| `seed_initial.py` | Admin user, FY periods 2023–2028, weekly periods |
| `seed_coa.py` | Chart of accounts + NetSuite/Xero account mappings |
| `seed_locations.py` | Locations from NetSuite |

---

## 9. Key Design Decisions

### Why JSONB for assumptions?

Budget assumptions vary by line item — some are a flat monthly number, others a percentage, others have seasonal adjustments. JSONB in `model_assumptions.assumption_value` avoids a rigid column-per-metric schema and makes it trivial to add new assumption types without migrations.

### Why a unified chart of accounts?

Entities come from two different systems (NetSuite and Xero) with different account codes. `account_mappings` translates each source code to a single `accounts` table so consolidated statements are always on the same basis. The `multiplier` field handles sign conventions (e.g. NetSuite credits as negatives).

### Why Celery for syncs and model runs?

NetSuite and Xero API calls can take 10–30 seconds per entity. The 10-step model engine touches every period × account × entity. Running these synchronously would timeout HTTP requests. Celery moves them off the request path; the frontend polls for status.

### Why separate je_lines from consolidated_actuals?

`je_lines` stores raw source data exactly as received. `consolidated_actuals` is the output of the mapping and consolidation process. This separation means you can re-consolidate (after fixing mappings) without re-syncing from source systems.

### Why weekly periods for site budgets?

Kip's site operations (dog daycare/boarding) have strong day-of-week patterns. Weekly granularity captures this while monthly totals wash out the variance. `weekly_periods` maps each week to an FY month, and `site_rollup_service` aggregates into monthly model assumptions.

### Why Zustand over Redux or Context?

Minimal global state (auth token, selected period, active budget version). Zustand is far less boilerplate than Redux and avoids the re-render issues of raw React Context. Server state is handled entirely by TanStack Query.

### Why shadcn/ui pattern instead of a component library?

Components are copied into the project (`components/ui/`) rather than imported from a package. This gives full control over styling and behaviour, avoids version-lock to a library, and keeps the Tailwind-first approach consistent.

---

## 10. Getting Started

```bash
git clone <repo>
cp .env.example .env          # fill in NetSuite/Xero creds + SECRET_KEY
docker compose up --build -d
# in the backend container:
alembic upgrade head
python -m scripts.seed_initial
python -m scripts.seed_coa
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | Frontend |
| http://localhost:8000/docs | API docs (Swagger) |
| http://localhost:5555 | Flower (task monitor) |

Default admin: seeded by `seed_initial.py` — check the script for credentials.
