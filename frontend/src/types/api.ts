export type UserRole = "admin" | "finance" | "viewer";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface EntityBreakdown {
  entity_id: string;
  entity_code: string;
  amount: number;
}

export interface ConsolidatedLineItem {
  account_code: string;
  account_name: string;
  amount: number;
  is_subtotal: boolean;
  entity_breakdown: EntityBreakdown[];
}

export interface SyncRunRead {
  id: string;
  entity_id: string | null;
  source_system: string | null;
  started_at: string | null;
  completed_at: string | null;
  status: string | null;
  records_upserted: number;
  error_detail: string | null;
  triggered_by: string;
}

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
