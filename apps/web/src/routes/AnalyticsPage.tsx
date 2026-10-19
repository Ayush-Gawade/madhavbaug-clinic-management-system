import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, ClipboardList, IndianRupee, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { StatCard } from "@/components/StatCard";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import { Badge, Card, CardHeader, EmptyState, ErrorNotice, Loading } from "@/components/ui";
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

function OverviewSection(): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics-overview"],
    queryFn: getClinicOverview,
  });

  if (isPending) return <SkeletonTable rows={3} cols={4} />;
  if (isError || !data) return <ErrorNotice message="Failed to load clinic overview." />;

  const categories = data.category_counts
    .map((item) => `${item.category_type.replace("_", " ")}: ${item.count}`)
    .join(" · ");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        <StatCard
          label="Active patients"
          icon={<Activity className="h-4 w-4" />}
          tone="brand"
          value={`${data.active_patients} / ${data.total_patients}`}
        />
        <StatCard label="Follow-ups due today" value={data.follow_ups_due_today} />
        <StatCard label="Completed today" tone="success" value={data.follow_ups_completed_today} />
        <StatCard label="Overdue follow-ups" tone="danger" value={data.follow_ups_overdue} />
        <StatCard label="Open alerts" value={data.open_alerts} />
        <StatCard label="Urgent alerts" tone="danger" value={data.open_urgent_alerts} />
        <StatCard label="Pending reviews" tone="warning" value={data.pending_observation_reviews} />
        <StatCard label="Open exceptions" value={data.open_message_exceptions} />
        <StatCard label="Failed deliveries" tone="danger" value={data.failed_deliveries} />
        <StatCard label="Pending clarifications" value={data.pending_clarifications} />
        <StatCard label="AI clarifications" value={data.ai_needs_clarification} />
      </div>
      <Card className="p-4">
        <p className="text-sm font-medium text-ink">Patients by category</p>
        <p className="mt-1 text-sm text-ink-secondary">{categories || "No categories assigned."}</p>
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
      <CardHeader
        title="Patients requiring action"
        description="Prioritised by latest activity and alert severity."
        actions={data ? <Badge tone="slate">{data.total} total</Badge> : null}
      />
      {isPending ? (
        <SkeletonTable rows={4} cols={3} />
      ) : isError || !data ? (
        <div className="p-4">
          <ErrorNotice message="Failed to load daily operations." />
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={<ClipboardList className="h-5 w-5" />}
          message="Nothing requires action right now."
        />
      ) : (
        <ul className="divide-y divide-line/70">
          {data.items.map((item) => (
            <li
              key={item.patient_id}
              className="flex items-start justify-between gap-3 px-5 py-3.5 transition-colors hover:bg-surface-sunken/40"
            >
              <div className="min-w-0">
                <Link
                  to={`/patients/${item.patient_id}`}
                  className="text-sm font-semibold text-brand-700 transition hover:text-brand-800 dark:text-brand-300"
                >
                  {item.patient_name}
                </Link>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-ink-muted">
                  {item.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
              <div className="shrink-0 text-right">
                <Badge tone={PRIORITY_TONES[item.priority]} dot={item.priority !== "routine"}>
                  {item.priority}
                </Badge>
                <p className="mt-1 text-xs text-ink-faint">{formatDate(item.latest_activity)}</p>
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
    <Card>
      <CardHeader
        title="Follow-up adherence"
        actions={
          <span className="text-xs text-ink-muted">
            {data.date_from} → {data.date_to}
          </span>
        }
      />
      <div className="grid grid-cols-2 gap-3 p-4 text-sm sm:grid-cols-5">
        {[
          { label: "Scheduled", value: data.scheduled_total },
          { label: "Completed", value: data.completed },
          { label: "Overdue", value: data.overdue },
          { label: "Skipped", value: data.skipped },
          { label: "Completion", value: `${data.completion_rate_percent}%`, highlight: true },
        ].map((item) => (
          <div
            key={item.label}
            className="rounded-xl border border-line bg-surface-sunken/50 px-3.5 py-3"
          >
            <p className="text-xs text-ink-muted">{item.label}</p>
            <p
              className={`mt-0.5 text-lg font-bold tabular-nums ${
                item.highlight ? "text-brand-700 dark:text-brand-300" : "text-ink"
              }`}
            >
              {item.value}
            </p>
          </div>
        ))}
      </div>
      <p className="px-4 pb-4 text-xs text-ink-muted">{data.rate_definition}</p>
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
        <StatCard
          label="Total billed (est.)"
          icon={<IndianRupee className="h-4 w-4" />}
          value={data.total_charges}
        />
        <StatCard
          label="Recorded revenue"
          icon={<TrendingUp className="h-4 w-4" />}
          tone="success"
          value={data.recorded_revenue}
        />
        <StatCard label="Outstanding" tone="warning" value={data.outstanding} />
        <StatCard
          label="Est. contribution"
          icon={<BarChart3 className="h-4 w-4" />}
          tone="brand"
          value={data.estimated_contribution}
        />
      </div>
      <Card>
        <CardHeader title="Contribution by treatment (estimated)" />
        {data.lines.length === 0 ? (
          <EmptyState message="No active treatment assignments." />
        ) : (
          <Table minClassName="min-w-[600px]">
            <THead>
              <TH>Treatment</TH>
              <TH align="right">Assignments</TH>
              <TH align="right">Billed</TH>
              <TH align="right">Direct cost</TH>
              <TH align="right">Contribution</TH>
            </THead>
            <tbody>
              {data.lines.map((line) => (
                <TR key={line.treatment_id}>
                  <TD className="font-medium text-ink">{line.name}</TD>
                  <TD align="right" className="tabular-nums text-ink-secondary">
                    {line.assignments}
                  </TD>
                  <TD align="right" className="tabular-nums text-ink-secondary">
                    {line.billed}
                  </TD>
                  <TD align="right" className="tabular-nums text-ink-secondary">
                    {line.estimated_direct_costs}
                  </TD>
                  <TD align="right" className="font-semibold tabular-nums text-ink">
                    {line.estimated_contribution}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <Card className="p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Notes</p>
        <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-ink-secondary">
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
      <PageHeader
        title="Analytics"
        description="Clinic overview, operations and financial reporting."
      />

      {canViewClinical ? <OverviewSection /> : null}
      {canViewClinical ? <OperationsSection /> : null}
      {canViewClinical ? <AdherenceSection /> : null}
      {canViewFinance ? (
        <div className="space-y-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-ink-muted">
            <IndianRupee className="h-4 w-4" />
            Financial overview
          </h2>
          <FinanceSection />
        </div>
      ) : null}
    </div>
  );
}
