import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import api from "@/utils/api";

export default function Connections() {
  const handleConnectXero = async () => {
    try {
      const { data } = await api.get("/api/v1/auth/xero/connect");
      window.location.href = data.redirect_url;
    } catch {
      window.location.href = `${api.defaults.baseURL}/api/v1/auth/xero/connect`;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Connections</h1>
        <p className="text-muted-foreground">
          Manage integrations with external accounting systems.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded bg-blue-100 text-xs font-bold text-blue-700">
                X
              </span>
              Xero
            </CardTitle>
            <CardDescription>
              Connect to Xero for automated trial balance syncing.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={handleConnectXero}>Connect Xero</Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded bg-gray-100 text-xs font-bold text-gray-700">
                NS
              </span>
              NetSuite
            </CardTitle>
            <CardDescription>
              NetSuite uses token-based auth configured via environment
              variables.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Configured server-side. Contact an administrator to update
              credentials.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
