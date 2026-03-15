import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";
import AppLayout from "@/components/layout/AppLayout";
import RoleGuard from "@/components/RoleGuard";
import Login from "@/pages/Login";
import Unauthorised from "@/pages/Unauthorised";
import Dashboard from "@/pages/Dashboard";
import IncomeStatement from "@/pages/financials/IncomeStatement";
import BalanceSheet from "@/pages/financials/BalanceSheet";
import SyncRuns from "@/pages/sync/SyncRuns";
import TriggerSync from "@/pages/sync/TriggerSync";
import RunConsolidation from "@/pages/consolidation/RunConsolidation";
import UsersPage from "@/pages/admin/Users";
import Connections from "@/pages/admin/Connections";
import Entities from "@/pages/admin/Entities";
import BudgetAssumptions from "@/pages/budget/Assumptions";
import BudgetWorkingCapital from "@/pages/budget/WorkingCapital";
import BudgetDebtSchedule from "@/pages/budget/DebtSchedule";
import BudgetOutput from "@/pages/budget/Output";
import SiteBudget from "@/pages/budget/SiteBudget";
import VariancePage from "@/pages/reports/Variance";
import ScenarioList from "@/pages/scenarios/ScenarioList";
import ScenarioCompare from "@/pages/scenarios/ScenarioCompare";
import CoaMapping from "@/pages/admin/CoaMapping";
import BlendedPL from "@/pages/financials/BlendedPL";
import CashFlow from "@/pages/financials/CashFlow";
import TimeSeries from "@/pages/analytics/TimeSeries";
import LocationPerformance from "@/pages/analytics/LocationPerformance";
import SiteSetup from "@/pages/budget/SiteSetup";
import SiteWeeklyGrid from "@/pages/budget/SiteWeeklyGrid";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PublicOnly({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (token) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route
          path="/login"
          element={
            <PublicOnly>
              <Login />
            </PublicOnly>
          }
        />

        {/* Protected — wrapped in AppLayout */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="unauthorised" element={<Unauthorised />} />

          {/* Actuals — consolidated financials */}
          <Route path="actuals/consolidated" element={<IncomeStatement />} />
          <Route path="actuals/bs" element={<BalanceSheet />} />
          <Route path="actuals/blended" element={
            <RoleGuard minRole="finance"><BlendedPL /></RoleGuard>
          } />
          <Route path="actuals/cashflow" element={
            <RoleGuard minRole="finance"><CashFlow /></RoleGuard>
          } />
          <Route
            path="actuals/sync"
            element={
              <RoleGuard minRole="finance">
                <SyncRuns />
              </RoleGuard>
            }
          />

          {/* Budget — finance+ */}
          <Route
            path="budget/assumptions"
            element={
              <RoleGuard minRole="finance">
                <BudgetAssumptions />
              </RoleGuard>
            }
          />
          <Route
            path="budget/wc"
            element={
              <RoleGuard minRole="finance">
                <BudgetWorkingCapital />
              </RoleGuard>
            }
          />
          <Route
            path="budget/debt"
            element={
              <RoleGuard minRole="finance">
                <BudgetDebtSchedule />
              </RoleGuard>
            }
          />
          <Route
            path="budget/output"
            element={
              <RoleGuard minRole="finance">
                <BudgetOutput />
              </RoleGuard>
            }
          />
          <Route
            path="budget/sites"
            element={
              <RoleGuard minRole="finance">
                <SiteBudget />
              </RoleGuard>
            }
          />
          <Route
            path="budget/sites/setup"
            element={
              <RoleGuard minRole="finance">
                <SiteSetup />
              </RoleGuard>
            }
          />
          <Route
            path="budget/sites/overview"
            element={
              <RoleGuard minRole="finance">
                <SiteWeeklyGrid />
              </RoleGuard>
            }
          />

          {/* Variance & Scenarios — finance+ */}
          <Route
            path="variance"
            element={
              <RoleGuard minRole="finance">
                <VariancePage />
              </RoleGuard>
            }
          />
          <Route
            path="scenarios"
            element={
              <RoleGuard minRole="finance">
                <ScenarioList />
              </RoleGuard>
            }
          />
          <Route
            path="scenarios/compare"
            element={
              <RoleGuard minRole="finance">
                <ScenarioCompare />
              </RoleGuard>
            }
          />

          {/* Admin — COA Mapping */}
          <Route
            path="admin/coa"
            element={
              <RoleGuard minRole="admin">
                <CoaMapping />
              </RoleGuard>
            }
          />

          {/* Analytics — all roles */}
          <Route
            path="analytics/timeseries"
            element={
              <RoleGuard minRole="viewer">
                <TimeSeries />
              </RoleGuard>
            }
          />
          <Route
            path="analytics/locations"
            element={
              <RoleGuard minRole="viewer">
                <LocationPerformance />
              </RoleGuard>
            }
          />

          {/* Legacy routes — redirect to new paths */}
          <Route path="financials/is" element={<Navigate to="/actuals/consolidated" replace />} />
          <Route path="financials/bs" element={<Navigate to="/actuals/bs" replace />} />
          <Route path="sync/runs" element={<Navigate to="/actuals/sync" replace />} />

          {/* Sync trigger — admin only */}
          <Route
            path="sync/trigger"
            element={
              <RoleGuard minRole="admin">
                <TriggerSync />
              </RoleGuard>
            }
          />

          {/* Consolidation — admin only */}
          <Route
            path="consolidation/run"
            element={
              <RoleGuard minRole="admin">
                <RunConsolidation />
              </RoleGuard>
            }
          />

          {/* Admin — admin only */}
          <Route
            path="admin/users"
            element={
              <RoleGuard minRole="admin">
                <UsersPage />
              </RoleGuard>
            }
          />
          <Route
            path="admin/connections"
            element={
              <RoleGuard minRole="admin">
                <Connections />
              </RoleGuard>
            }
          />
          <Route
            path="admin/entities"
            element={
              <RoleGuard minRole="admin">
                <Entities />
              </RoleGuard>
            }
          />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
