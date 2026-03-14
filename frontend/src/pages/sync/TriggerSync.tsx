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

export default function TriggerSync() {
  const [entityId, setEntityId] = useState("");
  const [source, setSource] = useState<"netsuite" | "xero">("xero");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTrigger = async () => {
    if (!entityId.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const { data } = await api.post(`/api/v1/sync/${source}/${entityId}`);
      setResult(`Sync queued — run ID: ${data.sync_run_id}`);
    } catch {
      setError("Failed to trigger sync. Check the entity ID and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Trigger Sync</h1>
        <p className="text-muted-foreground">
          Manually trigger a data sync for a specific entity.
        </p>
      </div>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Sync Configuration</CardTitle>
          <CardDescription>
            Choose a source system and entity to synchronise.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Source System</Label>
            <div className="flex gap-2">
              <Button
                variant={source === "xero" ? "default" : "outline"}
                size="sm"
                onClick={() => setSource("xero")}
              >
                Xero
              </Button>
              <Button
                variant={source === "netsuite" ? "default" : "outline"}
                size="sm"
                onClick={() => setSource("netsuite")}
              >
                NetSuite
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="entity-id">Entity ID</Label>
            <Input
              id="entity-id"
              placeholder="UUID of the entity"
              value={entityId}
              onChange={(e) => setEntityId(e.target.value)}
            />
          </div>
          <Button onClick={handleTrigger} disabled={loading || !entityId.trim()}>
            {loading ? "Triggering..." : "Trigger Sync"}
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
