import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ShieldX } from "lucide-react";

export default function Unauthorised() {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <ShieldX className="h-12 w-12 text-muted-foreground" />
      <h1 className="mt-4 text-2xl font-bold tracking-tight">Access Denied</h1>
      <p className="mt-2 text-muted-foreground">
        You don't have permission to view this page.
      </p>
      <Button variant="outline" className="mt-6" onClick={() => navigate("/")}>
        Back to Dashboard
      </Button>
    </div>
  );
}
