# CLAUDE_CONTEXT.md — KipFP

⚠️ CURSOR INSTRUCTION — READ THIS FIRST ⚠️

This file must be updated at the end of EVERY Cursor chat session, no exceptions.
Updating this file is always the final step before the closing commit of any session.
The commit message must always end with "| CLAUDE_CONTEXT updated".

Before closing any session, Cursor must:
1. Re-read the entire codebase for any changes made in this session
2. Update every section of this document to reflect the current state
3. Add a "Last updated" timestamp at the top
4. Commit with message format: "[phase description] | CLAUDE_CONTEXT updated"

If this file has not been updated, the session is not complete.

---

**Last updated:** 2026-03-15 (AASB16 toggle fix — query key cache invalidation on analytics pages)

---

## 1. Tech Stack

| Layer | Technology | Version / Notes |
|-------|-----------|-----------------|
| Backend framework | FastAPI | >=0.115.0 |
| ORM | SQLAlchemy 2.x (async) | >=2.0.36, asyncpg driver |
| Migrations | Alembic | >=1.14.0 |
| Task queue | Celery + Redis | celery >=5.4.0, redis 7-alpine |
| Database | PostgreSQL 15 | async via asyncpg >=0.30.0 |
| Auth | JWT (python-jose), bcrypt | HS256, 24h expiry |
| Validation | Pydantic 2.x, pydantic-settings | >=2.10.0 |
| Frontend framework | React 18 | 18.3.1 |
| Build tool | Vite | 6.0.5 |
| Language | TypeScript | 5.6.3 |
| Routing | react-router-dom | 7.1.0 |
| State management | Zustand | 5.0.2 |
| Server state | TanStack React Query | 5.62.0 |
| HTTP client | Axios | 1.7.9 |
| Styling | Tailwind CSS | 3.4.17 |
| UI primitives | Radix UI (Label, Slot) | — |
| Charts | Recharts | 3.8.0 |
| Icons | lucide-react | — |
| Excel export | openpyxl | >=3.1.0 |
| Connectors | NetSuite (OAuth 1.0a TBA), Xero (OAuth 2.0), BigQuery | — |
| Monitoring | Celery Flower | >=2.0.1 |
| Containerisation | Docker Compose | 6 services |

## 2. Database Schema (as built — through migration 0013)

### users
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| email | String(255) | unique, indexed |
| hashed_password | String | |
| role | Enum(admin, finance, viewer) | |
| is_active | Boolean | default True |
| created_at | DateTime(tz) | |

### entities
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | String(20) | unique |
| name | String(200) | |
| source_system | Enum(netsuite, xero, manual, bigquery) | |
| source_entity_id | String(100) | |
| parent_entity_id | UUID | FK → entities.id |
| is_active | Boolean | default True |
| currency | CHAR(3) | default AUD |
| coa_type | Enum(netsuite, xero, custom) | |
| consolidation_method | Enum(full, equity, none) | |
| acquisition_date | Date | |

### periods
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| fy_year | Integer | |
| fy_month | Integer | Unique(fy_year, fy_month) |
| calendar_year | Integer | |
| calendar_month | Integer | |
| period_start | Date | |
| period_end | Date | |
| is_locked | Boolean | default False |

### weekly_periods
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| week_start_date | Date | unique |
| week_end_date | Date | |
| fy_year | Integer | |
| fy_month | Integer | |
| fy_quarter | Integer | |
| calendar_year | Integer | |
| calendar_month | Integer | |
| days_in_fy_month | Integer | |
| days_this_week_in_fy_month | Integer | |
| week_label | String(20) | |

### accounts
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | String(50) | unique |
| name | String(200) | |
| account_type | Enum(income, cogs, opex, depreciation, interest, tax, asset, liability, equity) | |
| statement | Enum(is, bs, cf) | |
| parent_account_id | UUID | FK → accounts.id |
| sort_order | Integer | |
| is_subtotal | Boolean | default False |
| subtotal_formula | JSONB | |
| is_elimination | Boolean | default False |
| normal_balance | Enum(debit, credit) | |

### account_mappings
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| entity_id | UUID | FK → entities.id |
| source_account_code | String(100) | |
| source_account_name | String(200) | |
| target_account_id | UUID | FK → accounts.id |
| multiplier | Numeric(5,4) | default 1.0 |
| effective_from | Date | |
| effective_to | Date | |
| notes | Text | |

### sync_runs
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| entity_id | UUID | FK → entities.id |
| source_system | Enum(netsuite, xero, bigquery) | |
| started_at | DateTime(tz) | |
| completed_at | DateTime(tz) | |
| status | Enum(running, success, partial, failed) | |
| records_upserted | Integer | default 0 |
| error_detail | Text | |
| triggered_by | Enum(schedule, manual) | |

### je_lines
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| entity_id | UUID | FK → entities.id |
| period_id | UUID | FK → periods.id |
| source_account_code | String(100) | |
| source_account_name | String(200) | |
| amount | Numeric(18,2) | |
| sync_run_id | UUID | FK → sync_runs.id |
| source_ref | String(200) | |
| ingested_at | DateTime(tz) | |
| location_id | UUID | FK → locations.id |
| is_aasb16 | Boolean | default False (added 0007) |
| is_opening_balance | Boolean | default False (added 0012) |

Unique: (entity_id, period_id, source_account_code, is_aasb16)

### api_credentials
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| service | String(50) | |
| credential_key | String(100) | |
| credential_value | Text | |
| updated_at | DateTime(tz) | |

### locations
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | String(20) | unique |
| name | String(200) | |
| entity_id | UUID | FK → entities.id |
| state | String(3) | |
| opened_date | Date | |
| closed_date | Date | |
| capacity_dogs | Integer | |
| netsuite_location_id | String(50) | |
| is_active | Boolean | default True |

### property_mappings (added 0009)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| bigquery_property_id | Integer | unique |
| bigquery_property_name | String(200) | |
| bigquery_url_slug | String(100) | |
| location_id | UUID | FK → locations.id |
| is_active | Boolean | default True |
| notes | Text | |

### budget_versions
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(200) | |
| fy_year | Integer | |
| version_type | Enum(budget, forecast, scenario) | |
| status | Enum(draft, approved, locked) | |
| base_version_id | UUID | FK → budget_versions.id |
| created_by | UUID | FK → users.id |
| approved_by | UUID | FK → users.id |
| created_at | DateTime(tz) | |
| locked_at | DateTime(tz) | |

### model_assumptions
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| budget_version_id | UUID | FK → budget_versions.id |
| entity_id | UUID | FK → entities.id |
| assumption_key | String(100) | |
| assumption_value | JSONB | |
| updated_by | UUID | FK → users.id |
| updated_at | DateTime(tz) | |
| location_id | UUID | FK → locations.id |

### model_outputs
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| version_id | UUID | FK → budget_versions.id |
| period_id | UUID | FK → periods.id |
| account_id | UUID | FK → accounts.id |
| entity_id | UUID | FK → entities.id |
| amount | Numeric(18,2) | default 0 |
| calculated_at | DateTime(tz) | |

Unique: (version_id, period_id, account_id, entity_id)

### wc_drivers
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| budget_version_id | UUID | FK → budget_versions.id |
| entity_id | UUID | FK → entities.id |
| account_id | UUID | FK → accounts.id |
| driver_type | Enum(dso, dpo, dii, fixed_balance, pct_revenue) | |
| base_days | Numeric(6,2) | |
| seasonal_factors | JSONB | |
| notes | Text | |
| last_updated_by | UUID | FK → users.id |
| last_updated_at | DateTime(tz) | |

### debt_facilities
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| code | String(50) | unique |
| name | String(200) | |
| entity_id | UUID | FK → entities.id |
| facility_type | Enum(property_loan, equipment_loan, vehicle_loan, revolving, overdraft) | |
| limit_amount | Numeric(18,2) | |
| opening_balance | Numeric(18,2) | |
| interest_rate_type | Enum(fixed, variable) | |
| base_rate | Numeric(8,6) | |
| margin | Numeric(8,6) | default 0 |
| interest_calc_method | Enum(daily, monthly) | |
| amort_type | Enum(interest_only, principal_and_interest, bullet, custom) | |
| monthly_repayment | Numeric(18,2) | |
| repayment_day | Integer | |
| maturity_date | Date | |
| sort_order | Integer | default 0 |
| is_active | Boolean | default True |

### debt_schedules
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| facility_id | UUID | FK → debt_facilities.id |
| budget_version_id | UUID | FK → budget_versions.id |
| period_id | UUID | FK → periods.id |
| opening_balance | Numeric(18,2) | |
| drawdown | Numeric(18,2) | default 0 |
| repayment | Numeric(18,2) | default 0 |
| closing_balance | Numeric(18,2) | |
| interest_expense | Numeric(18,2) | |
| interest_rate_applied | Numeric(8,6) | |

### site_budget_entries
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| version_id | UUID | FK → budget_versions.id |
| location_id | UUID | FK → locations.id |
| model_line_item | String(100) | |
| week_id | UUID | FK → weekly_periods.id |
| amount | Numeric(18,2) | |
| driver_type | Enum(manual, occupancy_rate, per_dog_night, headcount_x_rate, pct_revenue) | |
| driver_params | JSONB | |
| entered_by | UUID | FK → users.id |
| updated_at | DateTime(tz) | |

### site_budget_assumptions (added 0011)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| version_id | UUID | FK → budget_versions.id |
| location_id | UUID | FK → locations.id |
| fy_year | Integer | |
| price_growth_pct | Numeric(6,4) | default 0.03 |
| pet_day_growth_pct | Numeric(6,4) | default 0.02 |
| bath_price | Numeric(8,2) | |
| other_services_per_pet_day | Numeric(8,4) | |
| membership_pct_revenue | Numeric(6,4) | |
| mpp_mins | Numeric(6,2) | |
| min_daily_hours | Numeric(6,2) | |
| wage_increase_pct | Numeric(6,4) | default 0.05 |
| cogs_pct | Numeric(6,4) | |
| rent_monthly | Numeric(10,2) | |
| rent_growth_pct | Numeric(6,4) | default 0.03 |
| utilities_monthly | Numeric(10,2) | |
| utilities_growth_pct | Numeric(6,4) | default 0.03 |
| rm_monthly | Numeric(10,2) | |
| rm_growth_pct | Numeric(6,4) | default 0.05 |
| it_monthly | Numeric(10,2) | |
| it_growth_pct | Numeric(6,4) | default 0.05 |
| general_monthly | Numeric(10,2) | |
| general_growth_pct | Numeric(6,4) | default 0.05 |
| advertising_pct_revenue | Numeric(6,4) | |
| assumptions_locked | Boolean | default False |
| last_updated_by | UUID | FK → users.id |
| last_updated_at | DateTime(tz) | |

Unique: (version_id, location_id)

### site_weekly_budget (added 0011)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| version_id | UUID | FK → budget_versions.id |
| location_id | UUID | FK → locations.id |
| week_id | UUID | FK → weekly_periods.id |
| prior_year_boarding | Integer | |
| prior_year_daycare | Integer | |
| prior_year_grooming | Integer | |
| prior_year_wash | Integer | |
| prior_year_training | Integer | |
| prior_year_revenue | Numeric(12,2) | |
| budget_pet_days_boarding | Integer | |
| budget_pet_days_daycare | Integer | |
| budget_pet_days_grooming | Integer | |
| budget_pet_days_wash | Integer | |
| budget_pet_days_training | Integer | |
| budget_revenue | Numeric(12,2) | |
| budget_labour | Numeric(12,2) | |
| budget_cogs | Numeric(12,2) | |
| budget_rent | Numeric(12,2) | |
| budget_utilities | Numeric(12,2) | |
| budget_rm | Numeric(12,2) | |
| budget_it | Numeric(12,2) | |
| budget_general | Numeric(12,2) | |
| budget_advertising | Numeric(12,2) | |
| is_overridden | Boolean | default False |
| override_revenue | Numeric(12,2) | |
| override_labour | Numeric(12,2) | |
| calculated_at | DateTime(tz) | |

Unique: (version_id, location_id, week_id)

### site_pet_days (added 0010)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| location_id | UUID | FK → locations.id |
| date | Date | |
| service_type | Enum(boarding, daycare, grooming, wash, training) | |
| pet_days | Integer | |
| revenue_aud | Numeric(12,2) | |
| sync_run_id | UUID | FK → sync_runs.id |
| ingested_at | DateTime(tz) | |

Unique: (location_id, date, service_type)

### consolidated_actuals
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| period_id | UUID | FK → periods.id |
| account_id | UUID | FK → accounts.id |
| entity_id | UUID | FK → entities.id |
| amount | Numeric(18,2) | default 0 |
| is_group_total | Boolean | default False |
| include_aasb16 | Boolean | default True (added 0013) |
| calculated_at | DateTime(tz) | |

### ic_elimination_rules (added 0008)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| label | String(200) | |
| entity_a_id | UUID | FK → entities.id |
| account_code_a | String(100) | |
| entity_b_id | UUID | FK → entities.id |
| account_code_b | String(100) | |
| is_active | Boolean | default True |
| tolerance | Numeric(18,2) | default 10.00 |
| notes | Text | |

### consolidation_runs
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| period_id | UUID | FK → periods.id |
| status | Enum(running, success, failed) | |
| bs_balanced | Boolean | |
| bs_variance | Numeric(18,2) | |
| ic_alerts | Text | |
| error_detail | Text | |
| started_at | DateTime(tz) | |
| completed_at | DateTime(tz) | |

### report_commentary (added 0006 — migration 0006 added model_outputs)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| version_id | UUID | FK → budget_versions.id |
| account_id | UUID | FK → accounts.id |
| period_id | UUID | FK → periods.id |
| comment | Text | |
| updated_by | UUID | FK → users.id |
| updated_at | DateTime(tz) | |

## 3. API Endpoints

Base prefix: `/api/v1`

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns status + version |

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Login → JWT |
| GET | `/auth/me` | Current user |
| POST | `/auth/refresh` | Refresh JWT |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/users` | Create user (admin only) |

### Entities
| Method | Path | Description |
|--------|------|-------------|
| GET | `/entities` | List active entities |
| GET | `/entities/locations` | List active locations |

### Sync
| Method | Path | Description |
|--------|------|-------------|
| POST | `/sync/netsuite/{entity_id}` | Trigger NetSuite sync |
| POST | `/sync/xero/{entity_id}` | Trigger Xero sync |
| GET | `/sync/runs` | List recent sync runs |
| GET | `/sync/runs/{run_id}` | Get sync run detail |

### Xero OAuth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/xero/connect` | Redirect to Xero OAuth |
| GET | `/auth/xero/callback` | Xero OAuth callback |

### Consolidation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/consolidate/{fy_year}/{fy_month}` | Run consolidation for period |
| GET | `/consolidated/is` | Consolidated IS (monthly + YTD + budget + var%) |
| GET | `/consolidated/bs` | Consolidated balance sheet |
| GET | `/consolidated/is/blended` | Blended IS (actuals + forecast) |

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/dashboard/kpis` | Dashboard KPIs for selected period |

### Budgets
| Method | Path | Description |
|--------|------|-------------|
| GET | `/budgets/` | List budget versions |
| POST | `/budgets/` | Create budget version |
| GET | `/budgets/{id}/assumptions` | Get assumptions |
| PUT | `/budgets/{id}/assumptions` | Save assumptions |
| GET | `/budgets/{id}/wc-drivers` | Get WC drivers |
| PUT | `/budgets/{id}/wc-drivers` | Update WC drivers |
| GET | `/budgets/{id}/debt` | Get debt summary (auto-seeds from BS-DEBT-* accounts; returns DebtSummary with facilities, history, schedule) |
| PUT | `/budgets/{id}/debt/facilities/{fid}` | Update debt facility forecast assumptions (rate, margin, repayment) |
| GET | `/budgets/{id}/sites` | List sites summary |
| GET | `/budgets/{id}/sites/annual-summary` | Sites annual summary |
| PUT | `/budgets/{id}/sites/bulk-assumptions` | Bulk update site assumptions |
| GET | `/budgets/{id}/sites/{location_id}` | Site budget grid |
| PUT | `/budgets/{id}/sites/{location_id}` | Save site budget |
| GET | `/budgets/{id}/sites/import/template` | Download import template |
| POST | `/budgets/{id}/sites/import` | Import site budgets |
| GET | `/budgets/{id}/site-rollup` | Site rollup data |
| POST | `/budgets/{id}/calculate` | Trigger model calculation |
| GET | `/budgets/{id}/status` | Calculation status |
| GET | `/budgets/{id}/output/is` | Budget IS output |
| GET | `/budgets/{id}/output/bs` | Budget BS output |
| GET | `/budgets/{id}/output/cf` | Budget CF output |
| GET | `/budgets/{id}/sites/{location_id}/assumptions` | Site assumptions |
| PUT | `/budgets/{id}/sites/{location_id}/assumptions` | Save site assumptions |
| POST | `/budgets/{id}/sites/{location_id}/calculate` | Calculate single site |
| POST | `/budgets/{id}/calculate-all-sites` | Calculate all sites |
| GET | `/budgets/{id}/sites/{location_id}/weekly` | Weekly budget grid |
| PUT | `/budgets/{id}/sites/{location_id}/weekly/{week_id}/override` | Override weekly line |

### Reports
| Method | Path | Description |
|--------|------|-------------|
| GET | `/reports/variance` | Variance report (actual vs budget) |
| PUT | `/reports/commentary` | Save commentary |
| POST | `/reports/export` | Export to xlsx |

### Scenarios
| Method | Path | Description |
|--------|------|-------------|
| GET | `/scenarios/` | List scenarios for base version |
| POST | `/scenarios/` | Create scenario |
| PUT | `/scenarios/{id}/assumptions` | Update scenario assumption |
| GET | `/scenarios/compare` | Compare scenarios |

### COA Mapping
| Method | Path | Description |
|--------|------|-------------|
| GET | `/coa/source-accounts` | List source accounts |
| GET | `/coa/target-accounts` | List target accounts |
| GET | `/coa/mappings/{entity_id}/{source_code}` | Get mapping |
| PUT | `/coa/mappings` | Save mapping |
| POST | `/coa/validate` | Validate mappings |

### Analytics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/analytics/timeseries` | Time series for metric |
| GET | `/analytics/timeseries/multi` | Multi-metric time series |
| GET | `/analytics/locations` | Location performance |
| GET | `/analytics/locations/{id}/timeseries` | Location time series |
| POST | `/analytics/export` | Export analytics (xlsx) |

### IC Elimination Rules
| Method | Path | Description |
|--------|------|-------------|
| GET | `/ic-rules` | List IC rules |
| POST | `/ic-rules` | Create IC rule |
| PUT | `/ic-rules/{rule_id}` | Update IC rule |
| DELETE | `/ic-rules/{rule_id}` | Delete IC rule |
| GET | `/ic-rules/preview` | Preview eliminations |

### Pet Days
| Method | Path | Description |
|--------|------|-------------|
| POST | `/pet-days/sync/bigquery` | Trigger BigQuery sync |
| GET | `/pet-days/actuals` | Pet day actuals for location |
| GET | `/pet-days/weekly` | Weekly pet days |
| GET | `/pet-days/summary` | All-locations summary |
| GET | `/pet-days/forward-bookings` | Forward bookings |
| GET | `/pet-days/mappings` | Property mappings |

## 4. Services

| Service | File | Purpose |
|---------|------|---------|
| NetSuite sync | `netsuite_sync_service.py` | Sync trial balance from NetSuite via SuiteQL → `je_lines` |
| Xero sync | `xero_sync_service.py` | Sync trial balance from Xero → `je_lines` |
| BigQuery sync | `bigquery_sync_service.py` | Sync pet days + revenue from BigQuery → `site_pet_days` |
| Consolidation engine | `consolidation_engine.py` | Map je_lines via account_mappings, IC elimination, write consolidated_actuals, BS validation |
| Site budget engine | `site_budget_engine.py` | Site-level operational budget from pet-day assumptions |
| Site rollup | `site_rollup_service.py` | Roll site budgets → entity-level model_assumptions |
| Model engine | `model_engine.py` | 3-statement model (IS, BS, CF) from assumptions, WC, debt, D&A, tax |
| Debt engine | `debt_engine.py` | Debt waterfall: interest, repayment, closing balance per facility |
| WC engine | `wc_engine.py` | Working capital schedule (DSO, DPO, DII, etc.) |
| AASB16 helpers | `aasb16_helpers.py` | AASB16 lease adjustments for ex-lease view |
| Opening balance | `opening_balance_service.py` | Import opening balances (fy_month=0) from NetSuite/Xero |

## 5. Connectors

| Connector | File | Auth | Purpose |
|-----------|------|------|---------|
| NetSuite | `netsuite.py` | OAuth 1.0a TBA | SuiteQL trial balance queries |
| Xero | `xero.py` | OAuth 2.0 (stored in api_credentials) | Trial balance via Xero Reports API |
| BigQuery | `bigquery.py` | Service account JSON | Pet days + revenue from PetBooking |

## 6. Celery Worker & Scheduled Tasks

App name: `kipfp`, broker/backend: Redis.

| Task | Schedule | Description |
|------|----------|-------------|
| `sync_entity_task` | On demand | NetSuite sync for entity + period |
| `sync_all_netsuite` | 2:00 AM AEST daily | Sync all NetSuite entities, last 2 unlocked periods |
| `sync_xero_entity_task` | On demand | Xero sync for entity + period |
| `consolidate_period_task` | On demand / after sync | Run consolidation for period |
| `sync_bigquery_task` | On demand | BigQuery pet days sync |
| `sync_bigquery_nightly` | 3:00 AM AEST daily | Last 90 days from BigQuery |
| `calculate_all_sites_task` | On demand | Calculate all sites → rollup → model |
| `run_model_task` | On demand | Run budget model for version |

## 7. Frontend Routes & Pages

| Path | Page | Min Role | Status |
|------|------|----------|--------|
| `/` | Dashboard | — | Built |
| `/login` | Login | — | Built |
| `/unauthorised` | Unauthorised | — | Built |
| `/actuals/consolidated` | Consolidated P&L | — | Built |
| `/actuals/bs` | Balance Sheet | — | Built |
| `/actuals/blended` | Blended P&L (actuals + forecast) | finance | Built |
| `/actuals/cashflow` | Cash Flow (actuals + forecast) | finance | Built |
| `/actuals/sync` | Sync Status | finance | Built |
| `/budget/assumptions` | Budget Assumptions (location-based; tax by subsidiary) | finance | Built |
| `/budget/wc` | Working Capital Drivers | finance | Built |
| `/budget/debt` | Debt Schedule | finance | Built |
| `/budget/output` | 3-Statement Output | finance | Built |
| `/budget/sites` | Site Budgets | finance | Built |
| `/budget/sites/setup` | Site Assumption Setup | finance | Built |
| `/budget/sites/overview` | Site Weekly Grid | finance | Built |
| `/variance` | Variance Report | finance | Built |
| `/scenarios` | Scenario List | finance | Built |
| `/scenarios/compare` | Scenario Compare | finance | Built |
| `/analytics/timeseries` | Time Series Analytics | viewer | Built |
| `/analytics/locations` | Location Performance | viewer | Built |
| `/sync/trigger` | Trigger Sync | admin | Built |
| `/consolidation/run` | Run Consolidation | admin | Built |
| `/admin/users` | User Management | admin | Built |
| `/admin/entities` | Entity Management | admin | Placeholder |
| `/admin/connections` | Xero/NetSuite Connections | admin | Built |
| `/admin/coa` | COA Mapping | admin | Built |

Legacy redirects: `/financials/is` → `/actuals/consolidated`, `/financials/bs` → `/actuals/bs`, `/sync/runs` → `/actuals/sync`

## 8. Frontend Stores (Zustand)

| Store | State | Actions |
|-------|-------|---------|
| auth | `token`, `user` | `setToken`, `setUser`, `logout`, `fetchUser` |
| period | `fyYear`, `fyMonth`, `dataPreparedToFyYear`, `dataPreparedToFyMonth` | `setFyYear`, `setFyMonth`, `setPeriod`, `setDataPreparedTo` |
| app | `includeAasb16` | `setIncludeAasb16`, `toggleAasb16` |
| budget | `activeVersionId` | `setActiveVersionId` |

## 9. Feature Status

| Feature | Phase | Status | Notes |
|---------|-------|--------|-------|
| Auth (JWT, roles) | 2 | Complete | admin/finance/viewer |
| DB models + migrations | 2 | Complete | Through migration 0012 |
| NetSuite connector + sync | 3 | Complete | OAuth 1.0a TBA, SuiteQL |
| Xero connector + sync | 4 | Complete | OAuth 2.0, stored creds |
| COA mapping engine | 4 | Complete | Per-entity source→target |
| Consolidation engine | 4 | Complete | IC elimination, BS validation |
| AASB16 handling | Post-4 | Complete | is_aasb16 flag, ex-lease toggle |
| Dashboard + KPIs | 6 | Complete | Revenue, GM%, EBITDA, debt |
| Consolidated P&L + BS | 6 | Complete | Entity breakdown, export |
| Sync status UI | 6 | Complete | |
| Budget model engine (3-stmt) | 7 | Complete | IS, BS, CF |
| Working capital engine | 7 | Complete | DSO, DPO, DII drivers |
| Debt waterfall engine | 7 | Complete | Multi-facility |
| Variance reporting | 8 | Complete | Actual vs budget, commentary |
| Scenario analysis | 8 | Complete | Create, compare up to 5 |
| Excel export | 8 | Complete | IS, BS, CF, variance |
| BigQuery pet days connector | Post-8 | Complete | PetBooking data |
| Site budget engine | Post-8 | Complete | 38 sites, weekly granularity |
| Site rollup → model | Post-8 | Complete | Aggregates to entity assumptions |
| Analytics (time series) | Post-8 | Complete | Revenue/GM/EBITDA over time |
| Analytics (location perf) | Post-8 | Complete | Site P&L, state filter |
| Blended P&L | Post-8 | Complete | Actuals + forecast stitching |
| Opening balances | Post-8 | Complete | fy_month=0 support |
| IC elimination rules UI | Post-8 | Complete | CRUD + preview |

## 10. Data State

| Dataset | Period Range | Notes |
|---------|-------------|-------|
| NetSuite entities (SH, KPT, NAR, etc.) | FY2024 M01–12, FY2025 M01–12, FY2026 M01–07 | All synced and consolidated |
| Xero entity (MC) | FY2024 M01–12, FY2025 M01–12, FY2026 M01–07 | All synced and consolidated |
| Opening balances | FY2025 M00 (cumulative TB at 30-Jun-2024) | Consolidated |
| BigQuery pet days | Last 90 days rolling (nightly) | 38 mapped locations |
| Periods seeded | FY2023–FY2028 | Weekly periods also seeded |
| Locations | ~38 sites across entities | Seeded from NetSuite |
| COA | Full IS + BS canonical chart | Multiple entity mappings |
| Budget versions | At least FY2026 budget exists | Site budgets seeded from Excel |

## 11. Environment & Infrastructure

### Docker Compose Services
| Service | Image | Port | Notes |
|---------|-------|------|-------|
| db | postgres:15 | 5432 | Volume: `pgdata` |
| redis | redis:7-alpine | 6379 | |
| backend | ./backend Dockerfile | 8000 | python:3.12-slim, uvicorn |
| celery_worker | ./backend Dockerfile | — | Same image as backend |
| celery_flower | ./backend Dockerfile | 5555 | Monitoring UI |
| frontend | ./frontend Dockerfile | 3000 | node:20-alpine, vite dev |

### Required Environment Variables
| Variable | Description |
|----------|-------------|
| DATABASE_URL | PostgreSQL connection (asyncpg) |
| REDIS_URL | Redis connection |
| SECRET_KEY | JWT signing key |
| NETSUITE_ACCOUNT_ID | NetSuite account |
| NETSUITE_CONSUMER_KEY | NetSuite OAuth consumer key |
| NETSUITE_CONSUMER_SECRET | NetSuite OAuth consumer secret |
| NETSUITE_TOKEN_KEY | NetSuite OAuth token key |
| NETSUITE_TOKEN_SECRET | NetSuite OAuth token secret |
| XERO_CLIENT_ID | Xero OAuth client ID |
| XERO_CLIENT_SECRET | Xero OAuth client secret |
| XERO_REDIRECT_URI | Xero OAuth callback URL |
| BIGQUERY_SERVICE_ACCOUNT_JSON | BigQuery service account (inline JSON) |
| BIGQUERY_SA_KEY_FILE | BigQuery service account key file path |

### URLs (Local Dev)
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Celery Flower | http://localhost:5555 |

## 12. Alembic Migration History

| Migration | Description |
|-----------|-------------|
| 0001 | Create `users` table |
| 0002 | Create entities, periods, accounts, account_mappings, sync_runs, je_lines, locations, budget_versions, model_assumptions, wc_drivers, debt_facilities, debt_schedules, site_budget_entries, weekly_periods |
| 0003 | Add unique constraint on je_lines (entity, period, source_account_code) |
| 0004 | Add api_credentials, consolidated_actuals, consolidation_runs |
| 0005 | Add model_outputs, CF pseudo-accounts |
| 0006 | Add report_commentary |
| 0007 | Add is_aasb16 to je_lines, update unique constraint |
| 0008 | Add ic_elimination_rules |
| 0009 | Add property_mappings, extend source_system enum |
| 0010 | Add site_pet_days |
| 0011 | Add site_budget_assumptions, site_weekly_budget |
| 0012 | Add is_opening_balance to je_lines |

## 13. Scripts

| Script | Purpose |
|--------|---------|
| `seed_initial.py` | Seeds admin user, periods FY2023–FY2028, weekly periods |
| `seed_coa.py` | Seeds canonical COA and account mappings for NetSuite/Xero entities |
| `seed_locations.py` | Seeds locations from NetSuite via SuiteQL |
| `seed_property_mappings.py` | Seeds BigQuery property → KipFP location mappings |
| `seed_site_budget_fy2026.py` | Seeds FY2026 site budget from Excel extract (38 sites × 12 months) |
| `sync_xero_mc.py` | Syncs MC (Xero) FY2025–FY2026 |
| `sync_mc_fy2024.py` | Syncs MC (Xero) FY2024 |
| `sync_sh_kpt_fy2024.py` | Syncs SH + KPT (NetSuite) FY2024 |
| `sync_all_netsuite_fy2024.py` | Full batch sync all NetSuite entities × FY2024 |
| `sync_fy2025_fy2026.py` | Batch sync FY2025–FY2026, auto-mapping, consolidation |
| `fix_mc_and_final_mappings.py` | Adds MC + NAR mappings, re-consolidates FY2024 |
| `fix_unmapped_accounts.py` | Maps OPEX-GAINLOSS, BS-DEBT-11526, re-consolidates |
| `fix_remaining_unmapped.py` | Maps remaining unmapped je_lines, re-consolidates |
| `map_fy2025_accounts.py` | Maps unmapped accounts for FY2025–FY2026 |
| `consolidate_verify_fy2024.py` | Consolidates FY2024, verifies MC + IC elimination |
| `check_aasb16_classes.py` | Checks NetSuite class names for AASB16 diagnostics |
| `resync_all_aasb16.py` | Re-syncs all entities to populate is_aasb16, re-consolidates |
| `import_opening_balances.py` | Imports opening balances at FY2025 start |
| `run_rollup_and_model.py` | Runs site rollup + model calculation for a budget version |
| `test_bigquery.py` | Tests BigQuery connectivity |

## 14. Git History (last 14 commits)

```
abdb645 Fix broken pages, financial correctness, and remove debug code (C9-C12, H1-H3, H6, H7, H10-H11, M15)
ce8b8aa Collapse Period and Last Closed selectors into a single Period picker
16f7aca Fix 8 critical security and data corruption bugs (C1-C8)
ae73f75 Fix AASB16 toggle not filtering lease journals on analytics pages
61f26e3 Replace forward bookings with dashboard charts: revenue trend, P&L cascade, top sites
07a6235 Debt schedule: auto-discover facilities from BS, add history + visualisations
bf37908 Architecture overhaul: single month picker, global last-closed-month, cashflow page, drill-down to NetSuite
cca3663 Add Xero MC sync script + 6 MC account mappings for FY2025-2026
c9ee1de Data sync FY2025-FY2026: sync scripts, 38 new account mappings, all periods consolidated and balanced
cbc952b KipFP v1.0 -- full build complete
80ec55e Phase 8: Variance reporting, scenarios, Excel export, COA mapping admin complete
291e8cf Phase 7: Budget model engine and UI complete
5764350 Phase 7A: Budget model engine complete - 3-statement, WC, debt waterfall
f182e02 Phase 6: Full FY2024 sync + COA mapping fixes for all entities
3d94f67 Phase 6: Actuals UI complete - dashboard, consolidated PnL/BS, sync status
5c199b2 Phase 5+6: React shell and actuals UI complete
```

## 15. Known Issues & Caveats

- **Uncommitted changes:** Significant uncommitted work exists across backend and frontend (see git status). Includes analytics endpoints, IC rules UI, pet days, AASB16 toggle, blended P&L, site budget engine, opening balances, BigQuery connector, and several new migrations (0007–0012).
- **Admin entities page:** `/admin/entities` is a placeholder — no CRUD UI yet.
- **No automated tests:** No test suite exists. `pytest` referenced in README but no test files present.
- **Secrets directory:** `secrets/bigquery-sa.json` is untracked — ensure it stays out of git.
- **AASB16 toggle:** Sends `include_aasb16` as a query param on every request via Axios interceptor. Backend endpoints need to respect this consistently.
- **Xero token refresh:** OAuth 2.0 tokens stored in `api_credentials`. Automatic refresh logic is in the connector but depends on valid stored credentials.
- **Multiple file copies:** Some files appear duplicated in git status with both forward-slash and backslash paths (Windows path normalisation issue). These are the same files.
- **Opening balances:** Stored as `fy_month=0` in je_lines with `is_opening_balance=True`. Consolidation handles M00 separately. Script `import_opening_balances.py` must be run after migration 0012 and before the BS will show correct cumulative balances.
- **Balance sheet fix (this session):** Two bugs fixed: (1) sign convention — liabilities/equity now display as positive via per-account `_display_sign`; (2) cumulative display — BS now shows point-in-time balances via `_get_bs_statement` + `_load_all_periods_through`. Excel export also updated.
- **Budget version management:** No UI for locking/approving versions — only draft status is used in practice.
- **Period selector simplified:** The "Last Closed" dropdown was removed from the top bar. `setPeriod()` now syncs `dataPreparedTo` to the selected month automatically. The `beyondPreparedTo` warnings were removed from TimeSeries and LocationPerformance since the two values are always in sync.
- **Debt auto-seed:** The `GET /budgets/{id}/debt` endpoint auto-creates `DebtFacility` records from `BS-DEBT-*` accounts (excluding `BS-TOTALDEBT` subtotal) if the `debt_facilities` table is empty. Opening balances come from `consolidated_actuals` (group totals). Facility type is inferred from account code/name (EQUIP → equipment_loan, VEHICLE → vehicle_loan, else property_loan). Entity is determined by the entity with the highest absolute balance for that account. Historical balance data and implied amortisation are derived from consolidated_actuals movements over time.
- **Site rollup monthly fix:** `site_rollup_service.py` was patched to handle monthly-grain entries (`week_id=None`) by reading `fy_month` from `driver_params`. Previously these entries were silently skipped.
- **FY2026 model BS imbalance:** Model calculation produces a consistent ~$990K/mo BS imbalance (Assets vs L+E). Likely due to missing opening balance assumptions or equity accounts not yet configured for FY2026 — not caused by site budget data.

## 16. Balance Sheet Architecture

The balance sheet display differs from the income statement in two critical ways:

### Sign convention (`_display_sign` in `consolidation.py`)
- IS: All accounts use `sign = -1.0` (credit-normal revenue stored as negative, negated for display).
- BS: Per-account sign based on `Account.normal_balance`. Assets (debit-normal) use `sign = 1.0`, liabilities and equity (credit-normal) use `sign = -1.0`. Same sign logic is applied in `_export_actuals_sheet` in `reports.py`.

### Cumulative display (`_get_bs_statement` in `consolidation.py`)
- BS shows **point-in-time balances**, not monthly movements. The helper `_load_all_periods_through()` loads ALL historical periods (including `fy_month=0` opening-balance periods) from the earliest in the DB through the selected period.
- **Single-month view:** Columns are `[<month movement>, "Balance"]` where Balance is the cumulative sum through that month-end.
- **Full-year view:** Each monthly column shows the cumulative balance at that month-end (running total across all historical periods).
- The `_get_statement_by_entity` function also loads all historical periods when `statement == Statement.bs`.
- All IS/variance/blended period queries use `fy_month >= 1` to exclude opening-balance periods.

### Opening balances (`fy_month=0`)
- Each FY can have a `fy_month=0` Period representing the cumulative TB at FY start (June 30).
- `opening_balance_service.py` pulls cumulative TB from NetSuite (`get_trial_balance_as_at`) or Xero (`get_trial_balance_at_date`) and stores as `je_lines` with `is_opening_balance=True`.
- The consolidation engine processes `fy_month=0` like any other period (maps through account_mappings → consolidated_actuals).
- `import_opening_balances.py` is the script to run the one-time import.

## 17. Deviations from Original Spec

- **Weekly granularity for site budgets** was not in the original spec but was added post-v1.0 to support operational-level budgeting at each Kip location.
- **BigQuery connector** was added post-spec to bring in PetBooking pet-day and revenue data for the site budget engine.
- **AASB16 toggle** was added post-spec to allow ex-lease views of P&L (statutory vs management reporting).
- **Analytics module** (time series + location performance) was added post-spec as a reporting enhancement.
- **Blended P&L** (actuals + forecast stitching) was added post-spec for forward-looking reporting.
- **Opening balance support** (migration 0012) was added post-spec to handle cumulative TB at year start.
- **Property mappings** (migration 0009) added to link BigQuery properties to KipFP locations — not in original spec.
- **Route restructure:** Original routes used `/financials/*` and `/sync/*`; restructured to `/actuals/*` with legacy redirects preserved.
- **Budget assumptions by location:** Revenue, COGS, Employment, Other Opex, and Capex assumptions are entered per **location** (not per entity/subsidiary). Tax assumptions remain per **subsidiary**. The `ModelAssumption` table uses `location_id` for location-based rows and `entity_id` for tax rows. The `AssumptionPayload` schema carries both `entity_id` and `location_id`; the backend matches on both when upserting. A `GET /entities/locations` endpoint was added to serve the locations list to the frontend.
- **Debt schedule auto-discovery:** The original spec assumed `debt_facilities` would be manually populated. The endpoint now auto-seeds from BS-DEBT-* COA accounts with balances from consolidated_actuals. The response changed from `list[DebtFacilityRead]` to `DebtSummary` (wrapping facilities with summary totals + history). Frontend was rebuilt with Recharts visualisations (stacked area, bar charts, sparklines) and a click-to-expand detail panel.
