import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import api from "@/utils/api";

export default function UsersPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"viewer" | "finance" | "admin">("viewer");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!email.trim() || !password.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      await api.post("/api/v1/admin/users", { email, password, role });
      setResult(`User ${email} created successfully.`);
      setEmail("");
      setPassword("");
      setRole("viewer");
    } catch (err: unknown) {
      // FIX(L19): show actual error detail from the API
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Failed to create user.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">User Management</h1>
        <p className="text-muted-foreground">
          Create and manage platform users.
        </p>
      </div>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Create User</CardTitle>
          <CardDescription>
            Add a new user to the platform.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-email">Email</Label>
            <Input
              id="new-email"
              type="email"
              placeholder="user@kipgroup.com.au"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">Password</Label>
            <Input
              id="new-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <div className="flex gap-2">
              {(["viewer", "finance", "admin"] as const).map((r) => (
                <Button
                  key={r}
                  variant={role === r ? "default" : "outline"}
                  size="sm"
                  onClick={() => setRole(r)}
                  className="capitalize"
                >
                  {r}
                </Button>
              ))}
            </div>
          </div>
          <Button
            onClick={handleCreate}
            disabled={loading || !email.trim() || !password.trim()}
          >
            {loading ? "Creating..." : "Create User"}
          </Button>
          {result && (
            <p className="text-sm text-emerald-700">{result}</p>
          )}
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
