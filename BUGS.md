# KipFP Bug Audit Report

**Date:** 2026-03-15
**Scope:** Full-stack audit — frontend pages/components, backend API endpoints, services, database queries
**Status:** Audit only — no fixes applied

---

## Critical — Blocks Core Workflow / Data Corruption / Security

| # | Location | What's Wrong |
|---|----------|-------------|
| C1 | `backend/app/core/config.py:12` | **Default SECRET_KEY allows JWT forgery.** `SECRET_KEY` defaults to `"change-me-to-a-random-64-char-string"`. If the env var is unset, any attacker who sees this source code can forge valid JWT tokens for any user, including admins. |
| C2 | `backend/app/services/model_engine.py:162-167` | **Model engine silently ignores site-level revenue budgets.** Site rollup writes revenue as `{"value": 0, "1": 12000, ...}` with `"value"` always `0`. The model engine reads the `"value"` field, which is always zero, so the `manual_val != ZERO` check always fails and all bottom-up site revenue is dropped. The entire site budget feature produces no effect on the model output. |
| C3 | `backend/app/services/model_engine.py:348-365` | **BS opening balances use monthly activity instead of cumulative balances.** `prior_actuals.get(("BS-CASH", 12))` reads June's monthly activity, not the closing balance as at June 30. Cash, PPE, and retained earnings opening figures are all wrong, making the 3-statement model output unreliable. |
| C4 | `backend/app/services/consolidation_engine.py:183-187` | **Consolidation deletes ALL actuals for a period regardless of AASB16 flag.** Running consolidation with `include_aasb16=False` destroys the previously stored AASB16-inclusive results. There is no separate storage for ex-lease vs. statutory views. |
| C5 | `backend/app/services/consolidation_engine.py:325-330` | **Consolidation commits partial/corrupt data on failure.** If an exception occurs after the DELETE (line 183) but before success, the `except` handler calls `db.commit()` to save the run's failed status — also committing the already-executed DELETE and any partial inserts. The `consolidated_actuals` table is left corrupted. |
| C6 | `backend/app/api/auth_xero.py:37-42` | **Xero OAuth CSRF protection is entirely bypassable.** `state` defaults to `""`. The check `if state and state not in _oauth_states` is `False` when state is empty (falsy). Calling `/callback?code=X` with no state skips CSRF validation entirely. |
| C7 | `backend/app/api/auth_xero.py:34-38` | **Xero OAuth callback has no authentication.** No `Depends(require_admin)`. Combined with C6, any unauthenticated user can overwrite stored Xero credentials, connecting the system to an attacker-controlled tenant. |
| C8 | `frontend/src/utils/api.ts:19-21` | **AASB16 interceptor corrupts POST/PUT request bodies.** When `includeAasb16` is `false`, the interceptor spreads `config.data` to inject `include_aasb16`. This (a) destroys `FormData` uploads (entries not enumerable), (b) converts arrays to objects, and (c) injects an extra field that may trigger Pydantic 422 if schemas use `extra="forbid"`. Affects file imports, batch saves, and any POST/PUT when the toggle is off. |
| C9 | `frontend/src/pages/financials/BlendedPL.tsx:27-31` | **Blended P&L page always 404s.** Calls `/api/v1/budget/versions` but the backend route is `GET /api/v1/budgets/`. Budget versions never load, so `versionId` is never set, and the entire blended P&L never renders data. |
| C10 | `frontend/src/pages/sync/TriggerSync.tsx:27` | **Trigger Sync page always 422s.** POST to `/api/v1/sync/{source}/{entityId}` sends no request body, but the backend requires `fy_year` (int) and `fy_month` (int). FastAPI rejects every request. The sync trigger feature is completely non-functional. |
| C11 | `frontend/src/pages/analytics/TimeSeries.tsx:30-34, 104-106` | **Entity filter sends entity codes instead of UUIDs.** `ENTITIES` contains codes like `"SH"`, `"KPT"`. Backend parses them as `uuid.UUID()` which throws `ValueError` → 500. Entity filtering on the time series page is completely broken. |
| C12 | `frontend/src/pages/Login.tsx:29-34` | **User data not fetched after login.** `setToken()` is called and user is navigated to `/`, but `fetchUser()` is never called. `user` remains `null`. Any component checking `user.role` may crash or incorrectly deny access. |

---

## High — Feature Broken / Significant Logic Error

| # | Location | What's Wrong |
|---|----------|-------------|
| H1 | `backend/app/api/reports.py:60-69` | **`is_favourable` flag inverted for revenue accounts.** Revenue is stored as negative (debit-positive convention). For income accounts `is_expense=False`, so the test is `actual > budget`, but -100k > -90k is `False` even when revenue exceeds budget. Every revenue variance row has an inverted favourability flag. |
| H2 | `backend/app/api/reports.py:431-434` | **Variance export uses raw signed values (no sign flip).** Revenue appears as negative in the spreadsheet. The actuals export correctly applies `sign = -1.0` for IS accounts, but the variance export does not. |
| H3 | `backend/app/api/reports.py:100-119` | **YTD and full-year variance return identical data.** Both branches query `fy_month >= 1` for the full FY. YTD should filter to periods up to the current/latest actual month, not all 12. |
| H4 | `backend/app/services/consolidation_engine.py:86-90` | **Consolidation ignores entity `consolidation_method`.** All active entities are fully consolidated regardless of their method (`full`, `equity`, `none`). Equity-method and excluded entities are incorrectly included. |
| H5 | `backend/app/services/consolidation_engine.py:57-59` | **Consolidation run created with bogus `period_id`.** Uses `uuid.uuid4()` as placeholder. If the period lookup fails, the exception handler commits this non-existent FK, causing a constraint violation — the failure itself can't be recorded. |
| H6 | `backend/app/services/site_budget_engine.py:440-445` | **Weekly-to-entry rollup is missing most budget line items.** Only rolls up 4 items (revenue, wages, COGS, rent) but the weekly budget calculates 9+ including utilities, R&M, IT, general, advertising. The model underestimates costs. |
| H7 | `backend/app/services/bigquery_sync_service.py:59` | **BigQuery sync uses `source_system="bigquery"` not in the DB enum.** The `SyncRun.source_system` column only allows `"netsuite"` and `"xero"`. PostgreSQL raises an enum violation, causing the entire BigQuery sync to fail. |
| H8 | `backend/app/services/aasb16_helpers.py:45-48` | **AASB16 helpers load account mappings without effective-date filtering.** Expired or future mappings are applied to AASB16 adjustments, producing incorrect ex-lease views. The consolidation engine correctly filters by date; AASB16 helpers do not. |
| H9 | `backend/app/api/auth_xero.py:20` | **In-memory OAuth state storage breaks multi-worker deployments.** `_oauth_states` is a module-level dict. With multiple workers/containers, `/connect` and `/callback` may hit different processes, causing the flow to fail. |
| H10 | `backend/app/api/dashboard.py:114-126` | **Debug instrumentation in production dashboard endpoint.** Every `GET /dashboard/kpis` call runs 3 extra DB queries + synchronous file I/O (`open()`/`write()`), blocking the async event loop. The log file grows unbounded. |
| H11 | `backend/app/services/consolidation_engine.py:222-228, 246-253` | **Debug logging in production consolidation engine.** Two blocks write JSON to `debug-b67ed3.log` on every consolidation run with synchronous file I/O in an async context. |
| H12 | `frontend/src/pages/budget/SiteWeeklyGrid.tsx:155-159 vs 252-261` | **CSV export contribution formula omits 5 cost categories.** Table subtracts all 8 cost items; CSV export only subtracts 3 (labour, COGS, rent). Exported figures are inflated. |
| H13 | `frontend/src/pages/budget/SiteWeeklyGrid.tsx:120-127` | **Weekly override save nulls the other override field.** Editing revenue sends `override_labour: null` and vice versa. If the backend treats `null` as "clear", editing one override destroys the other. |
| H14 | `frontend/src/pages/analytics/LocationPerformance.tsx:87` | **Location performance budget versions call always 404s.** Same wrong URL as C9: `/api/v1/budget/versions` instead of `/api/v1/budgets/`. Also missing `fy_year` param. |
| H15 | `frontend/src/components/RoleGuard.tsx:5-9, 21` | **RoleGuard silently grants access for unknown roles.** `ROLE_LEVEL[unknownRole]` returns `undefined`. `undefined < 2` evaluates to `false`, so the guard passes. Unknown roles get full access instead of being denied. |
| H16 | `frontend/src/components/RoleGuard.tsx:19` | **RoleGuard shows blank screen when `user` is null without token.** If `fetchUser` fails due to a network error (not 401), `user` stays `null` forever. The guard returns `null` — permanent blank screen with no redirect. |
| H17 | `frontend/src/components/FinancialTable.tsx:14-18` | **`fmtAUD` shows "(0)" for small negative values.** Values between -0.5 and 0 round to 0, but the negative check uses the pre-rounded value, displaying "(0)" — implying a negative amount when it's actually zero. |
| H18 | `frontend/src/components/layout/AppLayout.tsx:74-81` | **Multiple sidebar links highlight simultaneously.** `NavLink` without `end` uses prefix matching. `/budget/sites/overview` activates both "Site Budgets" (`/budget/sites`) and "Site Overview". |
| H19 | `frontend/src/pages/budget/DebtSchedule.tsx:362-386 vs 174-195` | **Debt schedule header/data column count mismatch for non-admin.** Schedule rows render 6 columns but the non-admin header only has 5 — closing balance appears under no header. |
| H20 | `frontend/src/pages/budget/DebtSchedule.tsx:297-311` | **Admin rate input displays raw decimal, users expect percentage.** Non-admins see "5.25%" but the admin input shows/accepts "0.0525". Typing "5" sets 500%. No unit label or conversion. |
| H21 | `frontend/src/pages/budget/SiteSetup.tsx:63` | **PctField propagates NaN to state.** `parseFloat("") / 100` = NaN. Unlike MoneyField and NumField which use `|| 0`, PctField has no NaN guard. NaN propagates to the backend. |
| H22 | `backend/app/services/bigquery_sync_service.py:86-87` | **BigQuery sync blocks the async event loop.** Synchronous `client.query().result()` is called directly in an async function without `run_in_executor()`. Blocks all concurrent requests. |

---

## Medium — Incorrect Behaviour

| # | Location | What's Wrong |
|---|----------|-------------|
| M1 | `backend/app/api/consolidation.py:198-203, 364-369` | **Consolidated IS/BS loads ALL actuals with no account filter.** Every period query fetches all accounts across all statements. Performance degrades as data grows; wastes memory. |
| M2 | `backend/app/api/sync.py:33-41, 66-74` | **SyncRun created without `started_at` timestamp.** Field stays NULL. List sort by `started_at desc nullslast` pushes new runs to the bottom. |
| M3 | `backend/app/api/sync.py:33-41, 66-74` | **No entity existence check before FK insert.** Non-existent `entity_id` causes IntegrityError → unhandled 500. |
| M4 | `backend/app/api/consolidation.py:104-107` | **Consolidation trigger returns dummy zero UUID.** Returns `00000000-...` instead of the actual run ID. Clients can't poll for status. |
| M5 | `backend/app/api/budget.py:1359-1384` | **Model output includes `fy_month=0` opening balance periods.** `_period_label` maps month 0 to `MONTH_ABBR[-1]` = "Jun", mislabelling the opening balance. |
| M6 | `backend/app/api/budget.py:1670-1714` | **Site assumptions save bypasses `assumptions_locked` check.** The bulk endpoint correctly filters locked sites, but the individual save does not. Locked site assumptions can be silently modified. |
| M7 | `backend/app/api/budget.py:773-779` | **Rollup failure silently swallowed after site budget save.** Exception logged but endpoint returns success. User has no idea the rollup failed; entity-level data is stale. |
| M8 | `backend/app/api/budget.py:1046-1055` | **Site import fuzzy matching can assign data to wrong location.** Substring matching is non-deterministic: "Perth" matches "Perth East" depending on dict iteration order. |
| M9 | `backend/app/api/analytics.py:313-316` | **Full-year location performance includes `fy_month=0` opening balance periods.** OB period JE lines inflate revenue and cost figures. |
| M10 | `backend/app/api/scenarios.py:207` | **Scenario compare crashes on invalid UUID input.** `uuid.UUID("abc")` raises unhandled `ValueError` → 500. |
| M11 | `backend/app/api/scenarios.py:220` | **Scenario compare assumes all versions share the same FY year.** Periods loaded from first version only; other-year versions produce zeros. |
| M12 | `backend/app/api/coa.py:168-189` | **COA mapping save has no FK validation.** Non-existent `target_account_id` or `entity_id` causes IntegrityError → unhandled 500. |
| M13 | `backend/app/api/ic_rules.py:126-134` | **IC rule creation has no FK validation on entity IDs.** Same unhandled IntegrityError pattern. |
| M14 | `backend/app/api/auth_xero.py:45-49` | **Xero callback has unhandled KeyError from token response.** If `exchange_code` returns error JSON, `tokens["access_token"]` raises KeyError → 500. |
| M15 | `backend/app/services/consolidation_engine.py:239-244` | **Subtotal sign logic inconsistency.** Consolidation engine ADDs "subtract" codes for IS accounts; model engine always subtracts. One must be wrong. |
| M16 | `backend/app/services/debt_engine.py:118` | **Debt engine ignores `interest_calc_method` field.** Always uses `annual_rate / 12` regardless of daily vs monthly setting on the facility. |
| M17 | `backend/app/services/debt_engine.py:112-116` | **P&I loans carry residual balance past maturity.** After maturity, closing = opening with zero repayment. Bullet repayment logic only fires for `AmortType.bullet`. |
| M18 | `backend/app/services/opening_balance_service.py:88-90` | **Opening balance sync may assign `source_system="manual"` which is not in the DB enum.** Same enum constraint issue as H7. |
| M19 | `backend/app/services/xero_sync_service.py:107` | **Xero sync hardcodes `is_aasb16=False`.** Xero entities with lease adjustments are never identified for the ex-lease view. |
| M20 | `backend/app/services/site_budget_engine.py:175-183` | **Site budget calculation commits partial data on exception.** `finally` block calls `db.commit()` even after an exception when `own_session` is True. |
| M21 | `backend/app/connectors/bigquery.py:68-70` | **BigQuery connector is vulnerable to SQL injection.** Date parameters interpolated via f-string instead of using parameterised queries. |
| M22 | `frontend/src/pages/financials/IncomeStatement.tsx:27-45` | **Export failure silently swallowed.** `try...finally` with no `catch` — no error feedback to user on export failure. |
| M23 | `frontend/src/pages/financials/BlendedPL.tsx:22` | **`lastActualMonth` stale after store change.** `useState(dataPreparedToFyMonth)` only uses the initial value; doesn't track later store updates. |
| M24 | `frontend/src/pages/consolidation/RunConsolidation.tsx:97` | **Hardcoded 3s timeout for consolidation refresh.** IC preview invalidation assumes the Celery task completes in 3 seconds. Stale data if slower. |
| M25 | `frontend/src/pages/financials/BalanceSheet.tsx:74` | **`highlightVariance` always true on Balance Sheet.** Contra-asset accounts and retained losses naturally have negative values and are incorrectly highlighted red. |
| M26 | `frontend/src/pages/budget/WorkingCapital.tsx:83-87` | **setState called during render.** `useState` used as a previous-value tracker with setter called during render — triggers synchronous re-render. Should use `useEffect` or `useRef`. |
| M27 | `frontend/src/pages/budget/WorkingCapital.tsx:58-71 vs 106-108` | **Seasonal factors indexing inconsistency.** Load handles both 0-indexed and 1-indexed keys; save always writes 1-indexed. First save silently converts all data. |
| M28 | `frontend/src/pages/budget/SiteBudget.tsx:165` | **Manual `Content-Type` for FormData omits boundary.** `"multipart/form-data"` set explicitly without the boundary parameter. Browser/axios should set this automatically; overriding can break multipart parsing. |
| M29 | `frontend/src/pages/budget/DebtSchedule.tsx:226-227` | **`updateMutation.isPending` shared across all facilities.** Saving facility A disables save buttons on all facilities. |
| M30 | `frontend/src/pages/budget/SiteWeeklyGrid.tsx:176-183` | **CSV download anchor not appended to DOM.** Click on detached element; Firefox requires DOM attachment for downloads. |
| M31 | `frontend/src/pages/reports/Variance.tsx:245, 274` | **Commentary editing keyed on `account_code` but save requires `account_id`.** For rows with `account_id=null`, user can open the edit field but can never save. |
| M32 | `frontend/src/pages/reports/Variance.tsx:34-45` | **Zero-variance rows highlighted red when `is_favourable=false`.** `mag=0` still returns `"bg-red-50"`. Should return `""` for zero variance. |
| M33 | `frontend/src/pages/analytics/TimeSeries.tsx:140-145` | **Chart data alignment by array index, not period label.** If single-metric and multi-metric queries return different period ranges, prior-year and rolling-average values attach to wrong periods. |
| M34 | `frontend/src/pages/admin/CoaMapping.tsx:84-89` | **`effectiveFrom` not reset when selecting new source account.** Stale date carries over from previous selection. |
| M35 | `frontend/src/pages/admin/CoaMapping.tsx:74-81` | **COA validation has no error handling.** `try...finally` without `catch` — validation failure produces no user feedback. |
| M36 | `frontend/src/pages/analytics/LocationPerformance.tsx:451-453` | **Missing React key on Fragment in mapped table rows.** `<>` instead of `<React.Fragment key={...}>` — causes warnings and potentially incorrect reconciliation. |
| M37 | `frontend/src/pages/analytics/LocationPerformance.tsx:40-45` | **SparkLine crashes with single data point.** `i / (values.length - 1)` = `0/0` = NaN. Produces invalid SVG coordinates. |
| M38 | `frontend/src/pages/budget/SiteSetup.tsx:132-159` | **Multiple `useEffect` API calls have no error handling.** `.then()` without `.catch()` — failed calls produce unhandled rejections and leave UI in indeterminate state. |
| M39 | `frontend/src/pages/budget/SiteSetup.tsx:193-228` | **`handleSave` and `handleSaveAndCalculate` swallow errors.** `try...finally` without `catch` — user sees no error feedback. |
| M40 | `frontend/src/components/FinancialTable.tsx:139` | **Indentation only supports one level.** `indent_level > 0` gives uniform `pl-6` regardless of nesting depth. Multi-level COA hierarchy appears flat. |
| M41 | `frontend/src/components/FinancialTable.tsx:200-201` | **CSS class conflict in entity breakdown rows.** `text-muted-foreground` and `text-red-500` both applied for negative values. Tailwind can't guarantee which wins. |
| M42 | `frontend/src/components/layout/AppLayout.tsx:134` | **Unauthenticated users see a partially functional app shell.** When `user` is null, role defaults to `"viewer"`. Sidebar renders viewer-accessible links but every API call fails. |
| M43 | `frontend/src/stores/app.ts:9-10` | **AASB16 toggle state not persisted across page refreshes.** Always resets to `true`. User who toggled ex-lease view silently gets statutory view after refresh. |
| M44 | `frontend/src/pages/budget/SiteSetup.tsx:179` | **`impliedLabour` uses hardcoded 365 operating days.** Overstates minimum labour for sites closed on weekends/holidays. |
| M45 | `frontend/src/pages/scenarios/ScenarioCompare.tsx:199-206` | **Delta column compares first vs last scenario regardless of selection order.** Backend may return scenarios in any order; delta may not be meaningful. |

---

## Low — Cosmetic / Code Quality / Minor

| # | Location | What's Wrong |
|---|----------|-------------|
| L1 | `frontend/src/utils/api.ts:5` | **Hardcoded `baseURL: "http://localhost:8000"`.** Will break in any deployed environment. Should use an environment variable. |
| L2 | `frontend/src/utils/api.ts:17` | **Dead code: `config.method === "GET"` branch unreachable.** Axios normalises method to lowercase. |
| L3 | `frontend/src/utils/api.ts:30-33` | **401 interceptor clears localStorage but not Zustand store.** Stale token/user may be visible in components before the hard redirect completes. |
| L4 | `frontend/src/utils/api.ts:30-33` | **401 interceptor can cause infinite redirect loop.** If any API call from `/login` returns 401, it redirects back to `/login` indefinitely. |
| L5 | `frontend/src/pages/financials/BlendedPL.tsx:110-112` | **Forecast legend shows "M13" when lastActualMonth=12.** Should hide the forecast legend when all 12 months are actuals. |
| L6 | `frontend/src/pages/financials/BlendedPL.tsx:51-53` | **Unused `actualLabels` Set computed on every render.** Dead code and wasted computation. |
| L7 | `frontend/src/pages/Dashboard.tsx:213` | **Unused `versionId` variable.** Creates unnecessary Zustand subscription causing extra re-renders. |
| L8 | `frontend/src/pages/sync/SyncRuns.tsx:92-94` | **Relies on backend sort order for "last run".** `runs[0]` assumed to be the latest. No client-side sort guarantees this. |
| L9 | `frontend/src/pages/consolidation/RunConsolidation.tsx:98-99` | **Error catch discards actual error details.** Shows generic "Failed to trigger consolidation" regardless of root cause. |
| L10 | `frontend/src/pages/reports/Variance.tsx:59` | **`fyMonthParam = -1` for full-year is an unconventional sentinel.** If backend doesn't handle `-1`, it could cause errors. |
| L11 | `frontend/src/pages/budget/SiteBudget.tsx:207-214` | **Summary gated on `siteGrid` unnecessarily.** Portfolio summary only appears when a specific site is selected, but data comes from `sites` not `siteGrid`. |
| L12 | `frontend/src/pages/budget/SiteWeeklyGrid.tsx:7` | **Unused `LocationRead` import.** |
| L13 | `frontend/src/pages/analytics/TimeSeries.tsx:36-39` | **`currentFyYear` computed at module level — never updates.** If app stays open across July 1, dropdown options are stale. |
| L14 | `frontend/src/pages/analytics/TimeSeries.tsx:59` | **Dead-code branch.** `dataPreparedToFyMonth <= 12` is always true (range 1-12). The `else` branch is unreachable. |
| L15 | `frontend/src/pages/analytics/LocationPerformance.tsx:24` | **Hardcoded states list.** `["NSW","VIC","QLD","SA","WA"]` — missing ACT, NT, TAS. Should derive from data. |
| L16 | `frontend/src/pages/analytics/TimeSeries.tsx:30-34` | **Hardcoded entities list instead of fetching from API.** Adding/removing entities requires a code change. |
| L17 | `frontend/src/pages/analytics/LocationPerformance.tsx:84-90` | **Budget version query missing `fy_year` param and query key.** Even if URL were fixed (H14), changing FY year won't refetch; returns all versions across all years. |
| L18 | `frontend/src/pages/scenarios/ScenarioList.tsx:21, 43-44` | **Redundant `creating` state alongside `useMutation.isPending`.** Brief desync window allows double-click to trigger mutation twice. |
| L19 | `frontend/src/pages/admin/Users.tsx:33-34` | **Generic error message hides actionable details.** Always shows "email may already be in use" regardless of actual error. |
| L20 | `frontend/src/pages/admin/Users.tsx` | **No user list display on admin page.** Only allows creating users; no way to view, edit, or deactivate existing users. |
| L21 | `frontend/src/components/RoleGuard.tsx:5-9` and `AppLayout.tsx:44-48` | **`ROLE_LEVEL` duplicated across two files.** If roles change in one file but not the other, sidebar visibility and route guards diverge. |
| L22 | `frontend/src/pages/budget/Assumptions.tsx:201` | **`handleSaveAndCalculate` has wrong useCallback dependencies.** Lists `handleSave` (not called) but omits `saveMutation` and `buildPayloads`. |
| L23 | `backend/app/api/budget.py:1704-1707` | **Cannot clear assumption fields to NULL.** `if value is not None` guard prevents clearing; explicit `null` in payload is ignored. |
| L24 | `backend/app/api/reports.py:434` | **Variance `var_pct` is `0` in export but `None` in API when budget=0.** Inconsistent representation across formats. |
| L25 | `backend/app/schemas/user.py:19-22` | **No password strength validation.** Empty string or single-character password accepted. |
| L26 | `backend/app/api/auth.py:50-51` | **Refresh token doesn't check for None `sub` claim.** Works by accident (PK is never NULL) but error message is misleading. |
| L27 | `backend/app/api/auth_xero.py:29` | **OAuth state memory leak — no TTL or cleanup.** Incomplete flows accumulate states in memory forever. |
| L28 | `backend/app/api/auth_xero.py:55` | **Xero callback leaks `tenant_id` in response.** Returned to unauthenticated callers (see C7). |
| L29 | `backend/app/api/pet_days.py:68-70` | **String-to-date comparison in pet days query.** `date_from`/`date_to` are strings compared against a Date column. Relies on implicit casting. |
| L30 | `backend/app/api/pet_days.py:212-214` | **Forward bookings has no error handling for BigQuery failures.** Missing credentials or query errors → unhandled 500. |
| L31 | `backend/app/services/site_budget_engine.py:267-271` | **Systematic upward rounding bias on pet days.** `math.ceil` across 5 service types × 52 weeks inflates pet days by up to 260/year/site. |
| L32 | `backend/app/services/wc_engine.py:154-156` | **WC seasonal factor lookup ambiguous (1-based vs 0-based).** Tries both key conventions; wrong factor may be selected. |
| L33 | Multiple files | **No `fy_month` range validation on query parameters.** Values like 13, 99, or -50 accepted without error. |
| L34 | `backend/app/api/auth.py:14-31` | **No rate limiting on login endpoint.** Unlimited brute-force attempts possible. |
| L35 | `backend/app/services/xero_sync_service.py:96` | **Import statement inside for loop.** `from sqlalchemy import func` re-imported on every row iteration. |
| L36 | `backend/app/services/consolidation_engine.py:114-118` | **Account mappings last-write-wins with no deterministic ordering.** Multiple overlapping mappings for the same key produce non-deterministic results. |

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|-----------|
| **Critical** | 12 | Security (JWT, OAuth), data corruption (consolidation, AASB16 delete, interceptor), broken pages (BlendedPL, TriggerSync, TimeSeries, Login) |
| **High** | 22 | Model engine logic (revenue, BS), variance sign errors, missing rollup items, BigQuery enum, RoleGuard bypass, debug code in production |
| **Medium** | 45 | Missing validation/error handling, incorrect period filtering, stale state, UI rendering issues, debt engine gaps |
| **Low** | 36 | Code quality, hardcoded values, dead code, minor inconsistencies |

**Total: 115 issues identified**

### Recommended Fix Order

1. **C1** (SECRET_KEY) — immediate security risk
2. **C6 + C7** (Xero OAuth) — unauthenticated credential overwrite
3. **C4 + C5** (consolidation data corruption) — protect existing data
4. **C2 + C3** (model engine) — core financial model is unreliable
5. **C8** (AASB16 interceptor) — affects all POST/PUT when toggle is off
6. **C9–C12** (broken frontend pages) — users hitting errors
7. **H1–H3** (variance signs) — financial reports showing wrong data
8. **H10–H11** (debug code) — performance and disk usage
