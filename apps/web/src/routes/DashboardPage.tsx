import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Activity,
  CalendarClock,
  CircleCheckBig,
  Clock,
  HeartPulse,
  MessageCircle,
  Stethoscope,
  TriangleAlert,
  Users,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { Card, CardHeader } from "@/components/ui";
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
      <PageHeader
        title="Dashboard"
        description="Operational overview for the clinic."
        actions={
          <Link
            to="/queues"
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white shadow-hairline transition hover:bg-brand-700"
          >
            <Activity className="h-4 w-4" />
            Open queues
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Active patients"
          icon={<Users className="h-4 w-4" />}
          tone="brand"
          isLoading={active.isPending}
          value={active.data?.total ?? "—"}
          to="/patients?status=active"
          ariaLabel="View active patients"
        />
        <StatCard
          label="Registered"
          icon={<Stethoscope className="h-4 w-4" />}
          isLoading={all.isPending}
          value={all.data?.total ?? "—"}
          to="/patients"
          ariaLabel="View all registered patients"
        />
        <StatCard
          label="Due today"
          icon={<CalendarClock className="h-4 w-4" />}
          tone="accent"
          value={counts.isPending ? "—" : (counts.data?.patients_due_today ?? 0)}
          hint={counts.data ? `${counts.data.due_today} check-ins` : undefined}
          to="/follow-ups?status=scheduled"
          ariaLabel="View follow-ups due today"
        />
        <StatCard
          label="Overdue"
          icon={<Clock className="h-4 w-4" />}
          tone="danger"
          value={counts.isPending ? "—" : (counts.data?.patients_overdue ?? 0)}
          hint={counts.data ? `${counts.data.overdue} check-ins` : undefined}
          to="/follow-ups?status=overdue"
          ariaLabel="View overdue follow-ups"
        />
        <StatCard
          label="Open alerts"
          icon={<TriangleAlert className="h-4 w-4" />}
          tone="warning"
          isLoading={alerts.isPending}
          value={alerts.data?.patients_open_total ?? "—"}
          hint={alerts.data ? `${alerts.data.open_total} alerts` : undefined}
          to="/alerts?status=open"
          ariaLabel="View open alerts"
        />
        <StatCard
          label="Urgent alerts"
          icon={<TriangleAlert className="h-4 w-4" />}
          tone="danger"
          isLoading={alerts.isPending}
          value={alerts.data?.patients_open_urgent ?? "—"}
          hint={alerts.data ? `${alerts.data.open_urgent} alerts` : undefined}
          to="/alerts?status=open&priority=urgent"
          ariaLabel="View urgent open alerts"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Needs your attention"
            description="Jump straight into the work queues"
          />
          <div className="grid gap-3 p-4 sm:grid-cols-2">
            {[
              {
                to: "/alerts",
                icon: TriangleAlert,
                tone: "bg-red-50 text-red-600 dark:bg-red-400/15 dark:text-red-300",
                title: "Clinical alerts",
                value: alerts.data?.patients_open_total ?? 0,
                sub: `${alerts.data?.open_urgent ?? 0} urgent awaiting disposition`,
              },
              {
                to: "/follow-ups",
                icon: HeartPulse,
                tone: "bg-amber-50 text-amber-600 dark:bg-amber-400/15 dark:text-amber-300",
                title: "Follow-ups due today",
                value: counts.data?.patients_due_today ?? 0,
                sub: `${counts.data?.patients_overdue ?? 0} patients overdue`,
              },
              {
                to: "/inbox",
                icon: MessageCircle,
                tone: "bg-sky-50 text-sky-600 dark:bg-sky-400/15 dark:text-sky-300",
                title: "Patient replies",
                sub: "Inbound WhatsApp messages awaiting a response",
              },
              {
                to: "/queues",
                icon: CircleCheckBig,
                tone: "bg-brand-50 text-brand-700 dark:bg-brand-400/15 dark:text-brand-300",
                title: "Operations queue",
                sub: "Failed deliveries, unanswered check-ins and reviews",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className="group flex items-start gap-3 rounded-xl border border-line bg-surface p-4 shadow-hairline transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover dark:hover:border-brand-700"
                >
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${item.tone}`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                      {item.title}
                      {item.value !== undefined ? (
                        <span className="font-bold tabular-nums">{item.value}</span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-muted">{item.sub}</span>
                  </span>
                </Link>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardHeader title="Backend status" />
          <div className="space-y-3 p-5">
            {health.isError ? (
              <p className="flex items-center gap-2 text-sm font-medium text-red-600 dark:text-red-400">
                <span className="h-2 w-2 rounded-full bg-red-500" />
                Backend unreachable
              </p>
            ) : health.data ? (
              <>
                <p className="flex items-center gap-2 text-sm font-medium text-ink">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
                  <span className="capitalize">{health.data.status}</span>
                </p>
                <dl className="space-y-1.5 text-xs text-ink-muted">
                  <div className="flex justify-between">
                    <dt>App</dt>
                    <dd className="font-medium text-ink-secondary">{health.data.app}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Version</dt>
                    <dd className="font-medium text-ink-secondary">v{health.data.version}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Environment</dt>
                    <dd className="font-medium text-ink-secondary">{health.data.env}</dd>
                  </div>
                </dl>
              </>
            ) : (
              <p className="text-sm text-ink-muted">Checking…</p>
            )}
            <Link
              to="/patients"
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-700 underline-offset-2 hover:underline dark:text-brand-300"
            >
              Open patients →
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
