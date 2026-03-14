import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";
import type { UserRole } from "@/types/api";

const ROLE_LEVEL: Record<UserRole, number> = {
  viewer: 0,
  finance: 1,
  admin: 2,
};

interface RoleGuardProps {
  minRole: UserRole;
  children: React.ReactNode;
}

export default function RoleGuard({ minRole, children }: RoleGuardProps) {
  const user = useAuthStore((s) => s.user);

  if (!user) return null;

  if (ROLE_LEVEL[user.role] < ROLE_LEVEL[minRole]) {
    return <Navigate to="/unauthorised" replace />;
  }

  return <>{children}</>;
}
