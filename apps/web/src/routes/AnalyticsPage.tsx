import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge, Card, EmptyState, ErrorNotice, Loading } from "@/components/ui";
import {
  getAdherence,
  getClinicOverview,
  getDailyOperations,
  getFinanceOverview,
} from "@/lib/analytics";
import { useAuth } from "@/lib/auth-context";
import { formatDate } from "@/lib/format";
import type { AlertPriority } from "@/lib/types";

const PRIORITY_TONES: Record<AlertPriority, string> = {
  urgent: "red",
  priority: "amber",
  routine: "slate",
};

function Stat({ label, value }: { label: string; value: string | number }): JSX.Element {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
    </Card>
  );
}

function OverviewSection(): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics-overview"],
    queryFn: getClinicOverview,
  });

  if (isPending) return <Loading />;
  if (isError || !data) return <ErrorNotice message="Failed to load clinic overview." />;

  const categories = data.category_counts
    .map((item) => `${item.category_type.replace("_", " ")}: ${item.count}`)
    .join(" · ");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Active patients" value={`${data.active_patients} / ${data.total_patients}`} />
        <Stat label="Follow-ups due today" value={data.follow_ups_due_today} />
        <Stat label="Completed today" value={data.follow_ups_completed_today} />
        <Stat label="Overdue follow-ups" value={data.follow_ups_overdue} />
        <Stat label="Open alerts" value={data.open_alerts} />
        <Stat label="Urgent alerts" value={data.open_urgent_alerts} />
        <Stat label="Pending reviews" value={data.pending_observation_reviews} />
        <Stat label="Open exceptions" value={data.open_message_exceptions} />
        <Stat label="Failed deliveries" value={data.failed_deliveries} />
        <Stat label="Pending clarifications" value={data.pending_clarifications} />
        <Stat label="AI clarifications" value={data.ai_needs_clarification} />
      </div>
      <Card className="p-4">
        <p className="text-sm font-medium text-slate-700">Patients by category</p>
        <p className="mt-1 text-sm text-slate-600">{categories || "No categories assigned."}</p>
      </Card>
    </div>
  );
}

function OperationsSection(): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics-operations"],
    queryFn: getDailyOperations,
  });

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-medium text-slate-700">Patients requiring action</p>
        {data ? <Badge tone="slate">{data.total} total</Badge> : null}
      </div>
      {isPending ? (
        <Loading />
      ) : isError || !data ? (
        <div className="p-4">
          <ErrorNotice message="Failed to load daily operations." />
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState message="Nothing requires action right now." />
      ) : (
        <ul className="divide-y divide-slate-100">
          {data.items.map((item) => (
            <li key={item.patient_id} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <Link
                  to={`/patients/${item.patient_id}`}
                  className="text-sm font-medium text-brand-700 hover:underline"
                >
                  {item.patient_name}
                </Link>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-500">
                  {item.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
              <div className="shrink-0 text-right">
                <Badge tone={PRIORITY_TONES[item.priority]}>{item.priority}</Badge>
                <p className="mt-1 text-xs text-slate-400">{formatDate(item.latest_activity)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AdherenceSection(): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics-adherence"],
    queryFn: () => getAdherence(),
  });

  if (isPending) return <Loading />;
  if (isError || !data) return <ErrorNotice message="Failed to load adherence summary." />;

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">Follow-up adherence</p>
        <p className="text-xs text-slate-400">
          {data.date_from} → {data.date_to}
        </p>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <div>
          <p className="text-xs text-slate-500">Scheduled</p>
          <p className="font-semibold">{data.scheduled_total}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Completed</p>
          <p className="font-semibold">{data.completed}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Overdue</p>
          <p className="font-semibold">{data.overdue}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Skipped</p>
          <p className="font-semibold">{data.skipped}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Completion</p>
          <p className="font-semibold text-brand-700">{data.completion_rate_percent}%</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-400">{data.rate_definition}</p>
    </Card>
  );
}

function FinanceSection(): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics-finance"],
    queryFn: getFinanceOverview,
  });

  if (isPending) return <Loading />;
  if (isError || !data) return <ErrorNotice message="Failed to load financial overview." />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Total billed (est.)" value={data.total_charges} />
        <Stat label="Recorded revenue" value={data.recorded_revenue} />
        <Stat label="Outstanding" value={data.outstanding} />
        <Stat label="Est. contribution" value={data.estimated_contribution} />
      </div>
      <Card>
        <p className="border-b border-slate-100 px-4 py-3 text-sm font-medium text-slate-700">
          Contribution by treatment (estimated)
        </p>
        {data.lines.length === 0 ? (
          <EmptyState message="No active treatment assignments." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2">Treatment</th>
                <th className="px-4 py-2">Assignments</th>
                <th className="px-4 py-2">Billed</th>
                <th className="px-4 py-2">Direct cost</th>
                <th className="px-4 py-2">Contribution</th>
              </tr>
            </thead>
            <tbody>
              {data.lines.map((line) => (
                <tr key={line.treatment_id} className="border-b border-slate-50">
                  <td className="px-4 py-2">{line.name}</td>
                  <td className="px-4 py-2">{line.assignments}</td>
                  <td className="px-4 py-2">{line.billed}</td>
                  <td className="px-4 py-2">{line.estimated_direct_costs}</td>
                  <td className="px-4 py-2 font-medium">{line.estimated_contribution}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Card className="p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Notes</p>
        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-slate-500">
          {data.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function AnalyticsPage(): JSX.Element {
  const { user } = useAuth();
  const canViewClinical = user?.role !== "finance";
  const canViewFinance = user?.role === "owner" || user?.role === "finance";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Analytics</h1>
        <p className="text-sm text-slate-500">Clinic overview, operations and financial reporting.</p>
      </div>

      {canViewClinical ? <OverviewSection /> : null}
      {canViewClinical ? <OperationsSection /> : null}
      {canViewClinical ? <AdherenceSection /> : null}
      {canViewFinance ? (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Financial overview
          </h2>
          <FinanceSection />
        </div>
      ) : null}
    </div>
  );
}
