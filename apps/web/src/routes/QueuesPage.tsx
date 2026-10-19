import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bell, CircleAlert, Clock, MessageCircle, UserX } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/Skeletons";
import { StatCard } from "@/components/StatCard";
import { Badge, Card, EmptyState, ErrorNotice } from "@/components/ui";
import { listAlerts } from "@/lib/alerts";
import { getClinicOverview } from "@/lib/analytics";
import { FOLLOW_UP_LABELS } from "@/lib/followUps";
import { detailSummary, reasonLabel } from "@/lib/messageExceptions";
import { listExceptions, listMessages } from "@/lib/messaging";
import { listPatients } from "@/lib/patients";
import { listInstances, listSchedules } from "@/lib/schedules";
import { listUsers } from "@/lib/users";
import type { FollowUpInstance, MessageException, WhatsAppMessage } from "@/lib/types";

const ALERT_PRIORITY_TONE: Record<string, "slate" | "amber" | "red"> = {
  urgent: "red",
  priority: "amber",
  routine: "slate",
};

function patientLabel(nameMap: Map<string, string>, patientId: string | null): string {
  if (!patientId) return "Unknown sender";
  return nameMap.get(patientId) ?? patientId.slice(0, 8);
}

function ownerLabel(userMap: Map<string, string>, staffId: string | null): string {
  if (!staffId) return "Unassigned";
  return userMap.get(staffId) ?? staffId.slice(0, 8);
}

function QueueCard({
  title,
  subtitle,
  count,
  viewAllTo,
  isError,
  errorMessage,
  isEmpty,
  emptyMessage,
  isLoading,
  children,
  id,
}: {
  title: string;
  subtitle: string;
  count: number | undefined;
  viewAllTo: string;
  isError: boolean;
  errorMessage: string;
  isEmpty: boolean;
  emptyMessage: string;
  isLoading: boolean;
  children: React.ReactNode;
  id?: string;
}): JSX.Element {
  return (
    <Card id={id} className="flex flex-col overflow-hidden scroll-mt-24">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-ink">{title}</h2>
            <span className="rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-bold tabular-nums text-ink-secondary">
              {count ?? "—"}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>
        </div>
        <Link
          to={viewAllTo}
          className="group inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-brand-700 transition hover:text-brand-800 dark:text-brand-300"
        >
          View all
          <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
      <div className="flex-1 divide-y divide-line/70">
        {isLoading ? (
          <div className="space-y-3 p-4">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/5" />
          </div>
        ) : isError ? (
          <div className="p-4">
            <ErrorNotice message={errorMessage} />
          </div>
        ) : isEmpty ? (
          <EmptyState message={emptyMessage} />
        ) : (
          children
        )}
      </div>
    </Card>
  );
}

function QueueRow({
  who,
  badges,
  why,
  owner,
  actionTo,
  actionLabel,
}: {
  who: string;
  badges: JSX.Element;
  why: React.ReactNode;
  owner?: string;
  actionTo: string;
  actionLabel: string;
}): JSX.Element {
  return (
    <div className="group/row flex items-start gap-3 px-4 py-3 transition-colors hover:bg-surface-sunken/50">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-ink">{who}</span>
          {badges}
        </div>
        <p className="mt-1 text-xs leading-relaxed text-ink-secondary">{why}</p>
        {owner ? (
          <p className="mt-1 text-[11px] text-ink-muted">
            Owner <span className="font-medium text-ink-secondary">{owner}</span>
          </p>
        ) : null}
      </div>
      <Link
        to={actionTo}
        className="mt-0.5 shrink-0 rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-ink-secondary shadow-hairline transition group-hover/row:border-brand-300 group-hover/row:text-brand-700 dark:group-hover/row:border-brand-700 dark:group-hover/row:text-brand-300"
      >
        {actionLabel}
      </Link>
    </div>
  );
}

export function QueuesPage(): JSX.Element {
  const patients = useQuery({
    queryKey: ["queue-patients"],
    queryFn: () => listPatients({ size: 1000 }),
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => listUsers({ size: 100 }),
    retry: false,
  });
  const schedules = useQuery({
    queryKey: ["schedules"],
    queryFn: () => listSchedules({}),
  });
  const alerts = useQuery({
    queryKey: ["queues-open-alerts"],
    queryFn: () => listAlerts({ status: "open", page: 1, size: 8 }),
  });
  const overdue = useQuery({
    queryKey: ["queues-overdue"],
    queryFn: () => listInstances({ status: "overdue", page: 1, size: 8 }),
  });
  const awaiting = useQuery({
    queryKey: ["queues-awaiting"],
    queryFn: async () => {
      const [delivered, read] = await Promise.all([
        listInstances({ status: "delivered", page: 1, size: 8 }),
        listInstances({ status: "read", page: 1, size: 8 }),
      ]);
      return {
        items: [...delivered.items, ...read.items].slice(0, 8),
        total: delivered.total + read.total,
        page: 1,
        size: 8,
        pages: 1,
      };
    },
  });
  const failures = useQuery({
    queryKey: ["queues-failures"],
    queryFn: () =>
      listMessages({ direction: "outbound", delivery_status: "failed", page: 1, size: 8 }),
  });
  const exceptions = useQuery({
    queryKey: ["queues-exceptions"],
    queryFn: () => listExceptions({ status: "open", page: 1, size: 8 }),
  });
  const overview = useQuery({
    queryKey: ["clinic-overview"],
    queryFn: () => getClinicOverview(),
  });

  const nameMap = useMemo(() => {
    return new Map((patients.data?.items ?? []).map((p) => [p.id, p.full_name]));
  }, [patients.data]);
  const userMap = useMemo(() => {
    return new Map((users.data?.items ?? []).map((u) => [u.id, u.full_name]));
  }, [users.data]);
  const scheduleMap = useMemo(() => {
    return new Map((schedules.data?.items ?? []).map((s) => [s.id, s.follow_up_type]));
  }, [schedules.data]);

  const reviewCount =
    (overview.data?.pending_observation_reviews ?? 0) +
    (overview.data?.ai_needs_clarification ?? 0);

  const instanceRows = (
    rows: FollowUpInstance[],
    statusLabel: string,
    tone: "amber" | "red",
    actionTo: string,
  ) =>
    rows.map((instance) => (
      <QueueRow
        key={instance.id}
        who={patientLabel(nameMap, instance.patient_id)}
        badges={<Badge tone={tone} dot>{statusLabel}</Badge>}
        why={
          <>
            {FOLLOW_UP_LABELS[scheduleMap.get(instance.schedule_id) ?? "observation"] ?? "Follow-up"}
            <span className="text-ink-muted"> · due {instance.due_date}</span>
          </>
        }
        owner={ownerLabel(userMap, instance.assigned_staff_id)}
        actionTo={actionTo}
        actionLabel="Work queue"
      />
    ));

  const failureRows = (messages: WhatsAppMessage[]) =>
    messages.map((message) => (
      <QueueRow
        key={message.id}
        who={patientLabel(nameMap, message.patient_id)}
        badges={<Badge tone="red" dot>failed</Badge>}
        why={
          <>
            {(message.text_body ?? "outbound message").slice(0, 90)}
            {message.error_message ? (
              <span className="text-ink-muted"> · {message.error_message}</span>
            ) : null}
          </>
        }
        actionTo={message.patient_id ? `/patients/${message.patient_id}` : "/message-exceptions"}
        actionLabel="Patient"
      />
    ));

  const exceptionRows = (rows: MessageException[]) =>
    rows.map((exception) => (
      <QueueRow
        key={exception.id}
        who={patientLabel(nameMap, exception.patient_id)}
        badges={<Badge tone="amber" dot>needs review</Badge>}
        why={
          <>
            {reasonLabel(exception.reason)}
            <span className="text-ink-muted"> · {detailSummary(exception.details)}</span>
          </>
        }
        actionTo="/message-exceptions"
        actionLabel="Review"
      />
    ));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Operations queue"
        description="Everything needing attention: alerts, overdue and unanswered follow-ups, failed deliveries and pending reviews."
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Open alerts"
          icon={<Bell className="h-4 w-4" />}
          isLoading={alerts.isPending}
          value={alerts.data?.total ?? "—"}
        />
        <StatCard
          label="Overdue"
          icon={<Clock className="h-4 w-4" />}
          tone="danger"
          isLoading={overdue.isPending}
          value={overdue.data?.total ?? "—"}
        />
        <StatCard
          label="Awaiting reply"
          icon={<MessageCircle className="h-4 w-4" />}
          tone="warning"
          isLoading={awaiting.isPending}
          value={awaiting.data?.total ?? "—"}
        />
        <StatCard
          label="Failed sends"
          icon={<UserX className="h-4 w-4" />}
          tone="danger"
          isLoading={failures.isPending}
          value={failures.data?.total ?? "—"}
        />
        <StatCard
          label="Reviews"
          icon={<CircleAlert className="h-4 w-4" />}
          tone="warning"
          isLoading={exceptions.isPending || overview.isPending}
          value={(exceptions.data?.total ?? 0) + reviewCount}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <QueueCard
          title="Open alerts"
          subtitle="Urgent and priority rule alerts awaiting disposition"
          count={alerts.data?.total}
          viewAllTo="/alerts"
          id="open-alerts"
          isLoading={alerts.isPending}
          isError={alerts.isError}
          errorMessage="Failed to load alerts."
          isEmpty={!alerts.data || alerts.data.items.length === 0}
          emptyMessage="No open alerts."
        >
          {alerts.data?.items.map((alert) => (
            <QueueRow
              key={alert.id}
              who={patientLabel(nameMap, alert.patient_id)}
              badges={
                <Badge tone={ALERT_PRIORITY_TONE[alert.priority]} dot>
                  {alert.priority}
                </Badge>
              }
              why={
                <>
                  {alert.reason}
                  {alert.metric ? (
                    <span className="text-ink-muted">
                      {" "}
                      · {alert.metric} {alert.value ?? ""} {alert.unit ?? ""}
                    </span>
                  ) : null}
                </>
              }
              owner={ownerLabel(userMap, alert.assigned_to)}
              actionTo="/alerts"
              actionLabel="Review"
            />
          ))}
        </QueueCard>

        <QueueCard
          title="Overdue follow-ups"
          subtitle="Missed response deadlines that need a nudge or manual follow-up"
          count={overdue.data?.total}
          viewAllTo="/follow-ups"
          id="overdue"
          isLoading={overdue.isPending}
          isError={overdue.isError}
          errorMessage="Failed to load overdue follow-ups."
          isEmpty={!overdue.data || overdue.data.items.length === 0}
          emptyMessage="Nothing is overdue."
        >
          {overdue.data ? instanceRows(overdue.data.items, "overdue", "red", "/follow-ups") : null}
        </QueueCard>

        <QueueCard
          title="Unanswered check-ins"
          subtitle="Messages delivered or read with no patient reply yet"
          count={awaiting.data?.total}
          viewAllTo="/follow-ups"
          id="awaiting"
          isLoading={awaiting.isPending}
          isError={awaiting.isError}
          errorMessage="Failed to load unanswered check-ins."
          isEmpty={!awaiting.data || awaiting.data.items.length === 0}
          emptyMessage="No check-ins awaiting a reply."
        >
          {awaiting.data
            ? instanceRows(awaiting.data.items, "awaiting reply", "amber", "/follow-ups")
            : null}
        </QueueCard>

        <QueueCard
          title="Failed deliveries"
          subtitle="Outbound WhatsApp messages that failed to deliver"
          count={failures.data?.total}
          viewAllTo="/message-exceptions"
          id="failures"
          isLoading={failures.isPending}
          isError={failures.isError}
          errorMessage="Failed to load delivery failures."
          isEmpty={!failures.data || failures.data.items.length === 0}
          emptyMessage="No failed deliveries in this window."
        >
          {failures.data ? failureRows(failures.data.items) : null}
        </QueueCard>

        <QueueCard
          title="Pending reviews"
          subtitle={`Open inbound exceptions, plus ${overview.data?.pending_observation_reviews ?? 0} observation reviews and ${overview.data?.ai_needs_clarification ?? 0} AI clarifications`}
          count={(exceptions.data?.total ?? 0) + reviewCount}
          viewAllTo="/message-exceptions"
          id="reviews"
          isLoading={exceptions.isPending}
          isError={exceptions.isError}
          errorMessage="Failed to load pending reviews."
          isEmpty={!exceptions.data || exceptions.data.items.length === 0}
          emptyMessage="No inbound messages waiting for review."
        >
          {exceptions.data ? exceptionRows(exceptions.data.items) : null}
        </QueueCard>

        <Card className="flex flex-col overflow-hidden bg-gradient-to-br from-brand-700 to-brand-900 xl:hidden">
          <div className="flex flex-1 flex-col justify-between gap-4 p-5">
            <p className="text-sm font-medium text-brand-100">
              Shortcuts to the heavier workspaces
            </p>
            <div className="flex flex-wrap gap-2">
              {[
                { to: "/alerts", label: "Alerts" },
                { to: "/follow-ups", label: "Follow-ups" },
                { to: "/inbox", label: "Inbox" },
                { to: "/message-exceptions", label: "Exceptions" },
              ].map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-white ring-1 ring-white/20 transition hover:bg-white/20"
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
