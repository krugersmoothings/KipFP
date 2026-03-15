export type UserRole = "admin" | "finance" | "viewer";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

// ── Entities ────────────────────────────────────────────────────────────

export interface EntityRead {
  id: string;
  code: string;
  name: string | null;
  source_system: string | null;
  is_active: boolean;
  currency: string;
  consolidation_method: string;
  acquisition_date: string | null;
}

// ── Locations ────────────────────────────────────────────────────────────

export interface LocationRead {
  id: string;
  code: string | null;
  name: string | null;
  entity_id: string | null;
  state: string | null;
  capacity_dogs: number | null;
  is_active: boolean;
}

// ── Sync ────────────────────────────────────────────────────────────────

export interface SyncRunRead {
  id: string;
  entity_id: string | null;
  entity_code: string | null;
  entity_name: string | null;
  source_system: string | null;
  started_at: string | null;
  completed_at: string | null;
  status: string | null;
  records_upserted: number;
  error_detail: string | null;
  triggered_by: string;
}

// ── Consolidated financials ─────────────────────────────────────────────

export interface FinancialRow {
  account_code: string;
  label: string;
  is_subtotal: boolean;
  is_section_header: boolean;
  indent_level: number;
  values: Record<string, number>;
  entity_breakdown: Record<string, Record<string, number>>;
}

export interface FinancialStatementResponse {
  periods: string[];
  rows: FinancialRow[];
}

// ── Dashboard KPIs ──────────────────────────────────────────────────────

export interface DashboardKPIs {
  revenue_mtd: number;
  revenue_pcp: number;
  gm_pct: number | null;
  gm_pct_pcp: number | null;
  ebitda_mtd: number;
  ebitda_ytd: number;
  net_cash: number;
  total_debt: number;
  last_sync_at: string | null;
}

// ── Consolidation ───────────────────────────────────────────────────────

export interface ConsolidationRunRead {
  id: string;
  period_id: string;
  status: string;
  bs_balanced: boolean | null;
  bs_variance: number | null;
  ic_alerts: string | null;
  error_detail: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// ── Budget ──────────────────────────────────────────────────────────────

export type VersionType = "budget" | "forecast" | "scenario";
export type VersionStatus = "draft" | "approved" | "locked";

export interface BudgetVersion {
  id: string;
  name: string;
  fy_year: number;
  version_type: VersionType;
  status: VersionStatus;
  base_version_id: string | null;
  created_by: string | null;
  approved_by: string | null;
  created_at: string;
  locked_at: string | null;
}

export interface BudgetVersionCreate {
  name: string;
  fy_year: number;
  version_type: VersionType;
  base_version_id?: string | null;
}

export type AssumptionKey =
  | "revenue_growth"
  | "cogs_pct"
  | "employment_wages"
  | "other_opex"
  | "capex"
  | "tax_rate";

export interface ModelAssumptionRead {
  id: string;
  entity_id: string | null;
  location_id: string | null;
  assumption_key: AssumptionKey;
  assumption_value: Record<string, unknown>;
  updated_at: string;
}

export interface AssumptionPayload {
  entity_id: string | null;
  location_id: string | null;
  assumption_key: AssumptionKey;
  assumption_value: Record<string, unknown>;
}

export interface CalculationTriggerResponse {
  task_id: string;
  status: string;
}

export interface CalculationStatusResponse {
  task_id: string | null;
  status: string;
  result: Record<string, unknown> | null;
}

export interface ModelOutputResponse {
  version_id: string;
  fy_year: number;
  statement: string;
  periods: string[];
  rows: FinancialRow[];
}

// ── Working Capital ─────────────────────────────────────────────────────

export type WcDriverType = "dso" | "dpo" | "dii" | "fixed_balance" | "pct_revenue";

export interface WcDriverRead {
  id: string;
  entity_id: string;
  account_id: string;
  account_label: string;
  driver_type: WcDriverType;
  base_days: number | null;
  seasonal_factors: Record<string, number> | number[] | null;
  notes: string | null;
}

export interface WcDriverUpdate {
  id: string;
  base_days: number | null;
  seasonal_factors: Record<string, number> | number[] | null;
}

// ── Debt ────────────────────────────────────────────────────────────────

export type FacilityType = "property_loan" | "equipment_loan" | "vehicle_loan" | "revolving" | "overdraft";
export type AmortType = "interest_only" | "principal_and_interest" | "bullet" | "custom";

export interface DebtHistoryPoint {
  period_label: string;
  fy_year: number;
  fy_month: number;
  balance: number;
  movement: number;
  implied_monthly_amort: number | null;
}

export interface DebtScheduleRow {
  period_label: string;
  opening_balance: number;
  drawdown: number;
  repayment: number;
  closing_balance: number;
  interest_expense: number;
  interest_rate_applied: number;
}

export interface DebtFacilityRead {
  id: string;
  code: string;
  name: string;
  entity_id: string;
  entity_code: string | null;
  facility_type: FacilityType | null;
  opening_balance: number;
  current_balance: number | null;
  base_rate: number | null;
  margin: number;
  amort_type: AmortType | null;
  monthly_repayment: number | null;
  maturity_date: string | null;
  is_active: boolean;
  schedule: DebtScheduleRow[];
  history: DebtHistoryPoint[];
  implied_interest_rate: number | null;
  avg_monthly_repayment: number | null;
}

export interface DebtFacilityWithSchedule extends DebtFacilityRead {
  schedule: DebtScheduleRow[];
}

export interface DebtFacilityUpdate {
  base_rate: number | null;
  margin: number;
  monthly_repayment: number | null;
}

export interface DebtSummary {
  total_debt: number;
  total_interest_budget: number;
  total_repayment_budget: number;
  facility_count: number;
  facilities: DebtFacilityRead[];
  total_debt_history: DebtHistoryPoint[];
}

// ── Site Budgets ────────────────────────────────────────────────────────

export interface SiteSummary {
  location_id: string;
  code: string;
  name: string;
  state: string | null;
  entity_id: string | null;
  capacity_dogs: number | null;
  monthly_totals: Record<string, number>;
}

export interface SiteBudgetLine {
  line_item: string;
  values: Record<string, number>;
}

export interface SiteBudgetGrid {
  location_id: string;
  location_name: string;
  periods: string[];
  lines: SiteBudgetLine[];
}

export interface SiteBudgetSavePayload {
  lines: { line_item: string; values: Record<string, number> }[];
}

export interface SiteRollupRow {
  entity_code: string;
  entity_name: string | null;
  line_item: string;
  site_total: Record<string, number>;
  model_assumption: Record<string, number>;
  variance: Record<string, number>;
}

// ── Variance Report ────────────────────────────────────────────────────

export interface VarianceRow {
  account_id: string | null;
  account_code: string;
  label: string;
  is_subtotal: boolean;
  is_section_header: boolean;
  indent_level: number;
  actual: number;
  budget: number;
  variance_abs: number;
  variance_pct: number | null;
  is_favourable: boolean | null;
  prior_year_actual: number;
  vs_pcp_abs: number;
  vs_pcp_pct: number | null;
  commentary: string | null;
}

export interface VarianceReportResponse {
  fy_year: number;
  period_label: string;
  version_id: string;
  view_mode: string;
  rows: VarianceRow[];
}

export interface CommentaryPayload {
  version_id: string;
  account_id: string;
  period_id: string | null;
  comment: string;
}

// ── Scenarios ──────────────────────────────────────────────────────────

export interface ScenarioRead {
  id: string;
  name: string;
  fy_year: number;
  version_type: string;
  status: string;
  base_version_id: string | null;
  description: string | null;
  created_at: string;
}

export interface ScenarioCreate {
  name: string;
  base_version_id: string;
  description?: string;
}

export interface ScenarioMetric {
  scenario_id: string;
  scenario_name: string;
  revenue: number;
  gm_pct: number | null;
  ebitda: number;
  ebitda_pct: number | null;
  npat: number;
  operating_cf: number;
  closing_cash: number;
  total_debt: number;
}

export interface ScenarioCompareResponse {
  fy_year: number;
  scenarios: ScenarioMetric[];
}

// ── Export ──────────────────────────────────────────────────────────────

export interface ExportRequest {
  type: "variance" | "budget" | "actuals";
  version_id?: string;
  fy_year: number;
  format: "xlsx" | "pdf";
}

// ── COA Mapping ────────────────────────────────────────────────────────

export interface SourceAccountRead {
  entity_id: string;
  entity_code: string;
  entity_name: string | null;
  source_account_code: string;
  source_account_name: string | null;
  is_mapped: boolean;
  mapping_id: string | null;
  target_account_code: string | null;
  target_account_name: string | null;
}

export interface TargetAccountRead {
  id: string;
  code: string;
  name: string;
  account_type: string | null;
  statement: string | null;
}

export interface AccountMappingRead {
  id: string;
  entity_id: string;
  source_account_code: string;
  source_account_name: string | null;
  target_account_id: string;
  target_account_code: string | null;
  target_account_name: string | null;
  multiplier: number;
  effective_from: string;
  effective_to: string | null;
  notes: string | null;
}

export interface AccountMappingSave {
  entity_id: string;
  source_account_code: string;
  source_account_name?: string;
  target_account_id: string;
  multiplier: number;
  effective_from: string;
  notes?: string;
}

export interface ValidationResult {
  total_source_accounts: number;
  mapped_count: number;
  unmapped_count: number;
  unmapped_accounts: SourceAccountRead[];
}

// ── IC Elimination Rules ─────────────────────────────────────────

export interface ICRuleRead {
  id: string;
  label: string;
  entity_a_id: string;
  entity_a_code: string | null;
  entity_a_name: string | null;
  account_code_a: string;
  entity_b_id: string;
  entity_b_code: string | null;
  entity_b_name: string | null;
  account_code_b: string;
  is_active: boolean;
  tolerance: number;
  notes: string | null;
}

export interface ICPreviewRow {
  rule_id: string;
  label: string;
  entity_a_code: string;
  account_code_a: string;
  balance_a: number;
  entity_b_code: string;
  account_code_b: string;
  balance_b: number;
  net: number;
  tolerance: number;
  status: "balanced" | "within_tolerance" | "imbalance";
}

// ── Analytics ─────────────────────────────────────────────────────────

export interface TimeSeriesPoint {
  period_label: string;
  fy_year: number;
  fy_month: number;
  value: number;
  prior_year_value: number | null;
  mom_change_pct: number | null;
  rolling_3m_avg: number | null;
  rolling_12m_avg: number | null;
}

export interface MultiTimeSeriesSeries {
  metric: string;
  values: number[];
}

export interface MultiTimeSeriesResponse {
  periods: string[];
  series: MultiTimeSeriesSeries[];
}

export interface LocationPerformanceRow {
  location_id: string;
  location_code: string | null;
  location_name: string | null;
  state: string | null;
  entity_code: string | null;
  revenue: number;
  direct_costs: number;
  site_pl: number;
  budget_revenue: number | null;
  budget_direct_costs: number | null;
  budget_site_pl: number | null;
  variance_abs: number | null;
  variance_pct: number | null;
  is_favourable: boolean | null;
}

export interface LocationTimeSeriesPoint {
  period_label: string;
  fy_year: number;
  fy_month: number;
  revenue: number;
  direct_costs: number;
  site_pl: number;
  mom_change_pct: number | null;
}

export interface SiteBudgetImportResult {
  status: string;
  rows_imported: number;
  entries_created: number;
  locations_updated: number;
  matched_locations: string[];
  unmatched_locations: string[];
  matched_line_items: string[];
  unmatched_line_items: string[];
  periods_matched: number;
}

export interface AnalyticsExportRequest {
  report_type: "timeseries" | "locations";
  params: Record<string, unknown>;
  format: "xlsx";
}

// ── Site Budget Engine (Operational Budget) ─────────────────────────────

export interface SiteBudgetAssumption {
  id: string;
  version_id: string;
  location_id: string;
  fy_year: number;
  price_growth_pct: number | null;
  pet_day_growth_pct: number | null;
  bath_price: number | null;
  other_services_per_pet_day: number | null;
  membership_pct_revenue: number | null;
  mpp_mins: number | null;
  min_daily_hours: number | null;
  wage_increase_pct: number | null;
  cogs_pct: number | null;
  rent_monthly: number | null;
  rent_growth_pct: number | null;
  utilities_monthly: number | null;
  utilities_growth_pct: number | null;
  rm_monthly: number | null;
  rm_growth_pct: number | null;
  it_monthly: number | null;
  it_growth_pct: number | null;
  general_monthly: number | null;
  general_growth_pct: number | null;
  advertising_pct_revenue: number | null;
  assumptions_locked: boolean;
  prior_year_avg_price: number | null;
  prior_year_total_pet_days: number | null;
  prior_year_avg_wage: number | null;
}

export interface SiteBudgetAssumptionUpdate {
  price_growth_pct?: number;
  pet_day_growth_pct?: number;
  bath_price?: number;
  other_services_per_pet_day?: number;
  membership_pct_revenue?: number;
  mpp_mins?: number;
  min_daily_hours?: number;
  wage_increase_pct?: number;
  cogs_pct?: number;
  rent_monthly?: number;
  rent_growth_pct?: number;
  utilities_monthly?: number;
  utilities_growth_pct?: number;
  rm_monthly?: number;
  rm_growth_pct?: number;
  it_monthly?: number;
  it_growth_pct?: number;
  general_monthly?: number;
  general_growth_pct?: number;
  advertising_pct_revenue?: number;
}

export interface SiteWeeklyBudgetRow {
  week_id: string;
  week_label: string | null;
  week_start: string | null;
  week_end: string | null;
  fy_month: number | null;
  prior_year_pet_days_boarding: number | null;
  prior_year_pet_days_daycare: number | null;
  prior_year_pet_days_grooming: number | null;
  prior_year_pet_days_wash: number | null;
  prior_year_pet_days_training: number | null;
  prior_year_revenue: number | null;
  budget_pet_days_boarding: number | null;
  budget_pet_days_daycare: number | null;
  budget_pet_days_grooming: number | null;
  budget_pet_days_wash: number | null;
  budget_pet_days_training: number | null;
  budget_revenue: number | null;
  budget_labour: number | null;
  budget_cogs: number | null;
  budget_rent: number | null;
  budget_utilities: number | null;
  budget_rm: number | null;
  budget_it: number | null;
  budget_general: number | null;
  budget_advertising: number | null;
  is_overridden: boolean;
  override_revenue: number | null;
  override_labour: number | null;
  is_month_subtotal: boolean;
}

export interface SiteAnnualSummary {
  location_id: string;
  location_name: string;
  state: string | null;
  total_prior_pet_days: number;
  total_budget_pet_days: number;
  total_prior_revenue: number;
  total_budget_revenue: number;
  total_budget_labour: number;
  total_budget_costs: number;
  budget_contribution: number;
  assumptions_status: string;
}

export interface ForwardBookingWeek {
  property_name: string;
  location_id: string | null;
  location_name: string | null;
  service_type: string;
  week_start: string;
  pet_days_booked: number;
  revenue_booked: number;
}
