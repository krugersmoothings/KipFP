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

const currentYear = new Date().getFullYear();

export default function RunConsolidation() {
  const [fyYear, setFyYear] = useState(currentYear);
  const [fyMonth, setFyMonth] = useState(new Date().getMonth() + 1);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const { data } = await api.post(
        `/api/v1/consolidate/${fyYear}/${fyMonth}`
      );
      setResult(
        `Consolidation queued — run ID: ${data.consolidation_run_id}`
      );
    } catch {
      setError("Failed to trigger consolidation. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Run Consolidation
        </h1>
        <p className="text-muted-foreground">
          Trigger a financial consolidation run for a specific period.
        </p>
      </div>

      <Card className="max-w-lg">
        <CardHeader>
          <CardTitle>Period Selection</CardTitle>
          <CardDescription>
            Choose the financial year and month to consolidate.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="fy-year">Financial Year</Label>
              <Input
                id="fy-year"
                type="number"
                min={2020}
                max={2035}
                value={fyYear}
                onChange={(e) => setFyYear(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="fy-month">Month</Label>
              <Input
                id="fy-month"
                type="number"
                min={1}
                max={12}
                value={fyMonth}
                onChange={(e) => setFyMonth(Number(e.target.value))}
              />
            </div>
          </div>
          <Button onClick={handleRun} disabled={loading}>
            {loading ? "Running..." : "Run Consolidation"}
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
