import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  FileSpreadsheet,
  RefreshCw,
  Play,
  Calculator,
  Users,
  Link as LinkIcon,
  Building2,
  LogOut,
  Menu,
  X,
  ChevronDown,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import PeriodSelector from "@/components/PeriodSelector";
import type { UserRole } from "@/types/api";

interface NavItem {
  label: string;
  to: string;
  icon: React.ReactNode;
  minRole?: UserRole;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const ROLE_LEVEL: Record<UserRole, number> = {
  viewer: 0,
  finance: 1,
  admin: 2,
};

function hasAccess(userRole: UserRole, minRole?: UserRole): boolean {
  if (!minRole) return true;
  return ROLE_LEVEL[userRole] >= ROLE_LEVEL[minRole];
}

const iconClass = "h-4 w-4";

const NAV_GROUPS: NavGroup[] = [
  {
    title: "",
    items: [
      { label: "Dashboard", to: "/", icon: <LayoutDashboard className={iconClass} /> },
    ],
  },
  {
    title: "Actuals",
    items: [
      { label: "Consolidated P&L", to: "/actuals/consolidated", icon: <FileText className={iconClass} /> },
      { label: "Balance Sheet", to: "/actuals/bs", icon: <FileSpreadsheet className={iconClass} /> },
      { label: "Sync Status", to: "/actuals/sync", icon: <RefreshCw className={iconClass} />, minRole: "finance" },
    ],
  },
  {
    title: "Operations",
    items: [
      { label: "Trigger Sync", to: "/sync/trigger", icon: <Play className={iconClass} />, minRole: "admin" },
      { label: "Run Consolidation", to: "/consolidation/run", icon: <Calculator className={iconClass} />, minRole: "admin" },
    ],
  },
  {
    title: "Admin",
    items: [
      { label: "Users", to: "/admin/users", icon: <Users className={iconClass} />, minRole: "admin" },
      { label: "Entities", to: "/admin/entities", icon: <Building2 className={iconClass} />, minRole: "admin" },
      { label: "Connections", to: "/admin/connections", icon: <LinkIcon className={iconClass} />, minRole: "admin" },
    ],
  },
];

const linkBase =
  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors";
const linkActive = "bg-primary text-primary-foreground";
const linkInactive =
  "text-muted-foreground hover:bg-accent hover:text-accent-foreground";

export default function AppLayout() {
  const { user, logout, fetchUser, token } = useAuthStore();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (token && !user) {
      fetchUser();
    }
  }, [token, user, fetchUser]);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const role: UserRole = user?.role ?? "viewer";

  const visibleGroups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((item) => hasAccess(role, item.minRole)),
  })).filter((g) => g.items.length > 0);

  const sidebarContent = (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-16 shrink-0 items-center border-b px-6">
        <Link to="/" className="flex items-center gap-2" onClick={() => setSidebarOpen(false)}>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-bold">
            K
          </div>
          <span className="text-lg font-bold tracking-tight">KipFP</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {visibleGroups.map((group) => (
          <div key={group.title || "_root"} className="mb-4">
            {group.title && (
              <div className="mb-1 flex items-center gap-1 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                <ChevronDown className="h-3 w-3" />
                {group.title}
              </div>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  onClick={() => setSidebarOpen(false)}
                  className={({ isActive }) =>
                    `${linkBase} ${isActive ? linkActive : linkInactive}`
                  }
                >
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User section */}
      <div className="shrink-0 border-t p-4">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{user?.email ?? "..."}</p>
            <p className="text-xs capitalize text-muted-foreground">{role}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={handleLogout} title="Sign out">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — desktop */}
      <aside className="hidden w-64 shrink-0 border-r bg-card lg:block">
        {sidebarContent}
      </aside>

      {/* Sidebar — mobile drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 transform border-r bg-card transition-transform lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <button
          className="absolute right-3 top-5 rounded-md p-1 text-muted-foreground hover:text-foreground lg:hidden"
          onClick={() => setSidebarOpen(false)}
        >
          <X className="h-5 w-5" />
        </button>
        {sidebarContent}
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-16 shrink-0 items-center gap-4 border-b px-4 lg:px-6">
          <button
            className="rounded-md p-1 text-muted-foreground hover:text-foreground lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <PeriodSelector />
          <div className="flex-1" />
          <span className="hidden text-sm text-muted-foreground sm:inline">
            {user?.email}
          </span>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <div className="container max-w-7xl py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
