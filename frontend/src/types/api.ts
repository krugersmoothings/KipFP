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
