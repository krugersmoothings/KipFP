import { useAuthStore } from "@/stores/auth";

export default function Dashboard() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back{user?.email ? `, ${user.email}` : ""}.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <DashboardCard
          title="Financials"
          description="View consolidated income statement and balance sheet."
          href="/financials/is"
        />
        <DashboardCard
          title="Data Sync"
          description="Monitor and trigger data synchronisation jobs."
          href="/sync/runs"
        />
        <DashboardCard
          title="Consolidation"
          description="Run period consolidations across all entities."
          href="/consolidation/run"
        />
      </div>
    </div>
  );
}

function DashboardCard({
  title,
  description,
  href,
}: {
  title: string;
  description: string;
  href: string;
}) {
  return (
    <a
      href={href}
      className="group rounded-lg border bg-card p-6 transition-colors hover:border-primary/30 hover:bg-accent"
    >
      <h3 className="font-semibold group-hover:text-primary">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </a>
  );
}
