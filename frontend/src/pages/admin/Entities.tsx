import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function Entities() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Entities</h1>
        <p className="text-muted-foreground">
          Manage group entities and their source-system mappings.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Entity List</CardTitle>
          <CardDescription>
            Entity management will be built in a future phase.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This page will display all entities, their connected accounting
            systems, and allow administrators to add or edit entity
            configurations.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
