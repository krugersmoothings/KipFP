import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">
            KipFP Dashboard
          </h1>
          <Button variant="outline" size="sm" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </header>
      <main className="container py-10">
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          <p className="text-lg">
            Welcome to the Kip Group Financial Planning &amp; Consolidation
            platform.
          </p>
          <p className="mt-2 text-sm">
            Dashboard modules will appear here as they are built.
          </p>
        </div>
      </main>
    </div>
  );
}
