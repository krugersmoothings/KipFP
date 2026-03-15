import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";
import type { UserRole } from "@/types/api";

const ROLE_LEVEL: Record<string, number> = {
  viewer: 0,
  finance: 1,
  admin: 2,
};

interface RoleGuardProps {
  minRole: UserRole;
  children: React.ReactNode;
}

export default function RoleGuard({ minRole, children }: RoleGuardProps) {
  const { user, token } = useAuthStore();

  if (!user) {
    if (!token) return <Navigate to="/login" replace />;
    return null;
  }

  const userLevel = ROLE_LEVEL[user.role] ?? -1;
  const requiredLevel = ROLE_LEVEL[minRole] ?? Infinity;

  if (userLevel < requiredLevel) {
    return <Navigate to="/unauthorised" replace />;
  }

  return <>{children}</>;
}
