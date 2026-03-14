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
  assumption_key: AssumptionKey;
  assumption_value: Record<string, unknown>;
  updated_at: string;
}

export interface AssumptionPayload {
  entity_id: string | null;
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

export interface DebtFacilityRead {
  id: string;
  code: string;
  name: string;
  entity_id: string;
  facility_type: FacilityType | null;
  opening_balance: number;
  base_rate: number | null;
  margin: number;
  amort_type: AmortType | null;
  monthly_repayment: number | null;
  maturity_date: string | null;
  is_active: boolean;
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

export interface DebtFacilityWithSchedule extends DebtFacilityRead {
  schedule: DebtScheduleRow[];
}

export interface DebtFacilityUpdate {
  base_rate: number | null;
  margin: number;
  monthly_repayment: number | null;
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
