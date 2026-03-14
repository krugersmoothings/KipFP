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
          <Route
            path="actuals/sync"
            element={
              <RoleGuard minRole="finance">
                <SyncRuns />
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
