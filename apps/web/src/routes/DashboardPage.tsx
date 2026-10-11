import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Card, ErrorNotice } from "@/components/ui";
import { getAlertSummary } from "@/lib/alerts";
import { listPatients } from "@/lib/patients";
import { getFollowUpDayCount } from "@/lib/schedules";

interface HealthResponse {
  status: string;
  app: string;
  env: string;
  version: string;
  time: string;
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch("/health");
  if (!response.ok) {
    throw new Error("Health check failed");
  }
  return (await response.json()) as HealthResponse;
}

function StatCard({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
    </div>
  );
}

export function DashboardPage(): JSX.Element {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: false,
  });

  const active = useQuery({
    queryKey: ["dash-active-patients"],
    queryFn: () => listPatients({ status: "active", size: 1 }),
  });

  const all = useQuery({
    queryKey: ["dash-all-patients"],
    queryFn: () => listPatients({ size: 1 }),
  });

  const counts = useQuery({
    queryKey: ["dash-follow-ups"],
    queryFn: getFollowUpDayCount,
  });

  const alerts = useQuery({
    queryKey: ["dash-alerts"],
    queryFn: () => getAlertSummary(),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500">Operational overview for the clinic.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Active patients" value={active.isPending ? "…" : String(active.data?.total ?? "—")} />
        <StatCard label="Registered patients" value={all.isPending ? "…" : String(all.data?.total ?? "—")} />
        <StatCard label="Follow-ups due today" value={counts ? String(counts.data?.due_today ?? 0) : "—"} />
        <StatCard label="Overdue follow-ups" value={counts ? String(counts.data?.overdue ?? 0) : "—"} />
        <StatCard
          label="Open alerts"
          value={alerts.isPending ? "…" : String(alerts.data?.open_total ?? "—")}
        />
        <StatCard
          label="Urgent alerts"
          value={alerts.isPending ? "…" : String(alerts.data?.open_urgent ?? "—")}
        />
      </div>

      <Card className="p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-slate-700">Backend status</p>
          <Link to="/patients" className="text-sm font-medium text-brand-700 hover:underline">
            Open patients →
          </Link>
        </div>
        {health.isError ? (
          <ErrorNotice message="Backend unreachable" />
        ) : health.data ? (
          <p className="mt-1 text-sm text-slate-600">
            {health.data.status} · {health.data.app} v{health.data.version} ({health.data.env})
          </p>
        ) : (
          <p className="mt-1 text-sm text-slate-400">Checking…</p>
        )}
      </Card>
    </div>
  );
}
