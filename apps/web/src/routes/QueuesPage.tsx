import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { Badge, Card, EmptyState, ErrorNotice, Loading } from "@/components/ui";
import { listAlerts } from "@/lib/alerts";
import { getClinicOverview } from "@/lib/analytics";
import { FOLLOW_UP_LABELS } from "@/lib/followUps";
import { detailSummary, reasonLabel } from "@/lib/messageExceptions";
import { listExceptions, listMessages } from "@/lib/messaging";
import { listPatients } from "@/lib/patients";
import { listInstances, listSchedules } from "@/lib/schedules";
import { listUsers } from "@/lib/users";
import type {
  FollowUpInstance,
  MessageException,
  WhatsAppMessage,
} from "@/lib/types";

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

function SectionHeader({
  title,
  subtitle,
  count,
  viewAllTo,
}: {
  title: string;
  subtitle: string;
  count: number | undefined;
  viewAllTo: string;
}): JSX.Element {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
      <div>
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
        <p className="text-xs text-slate-500">{subtitle}</p>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-600">{count ?? "—"} total</span>
        <Link
          to={viewAllTo}
          className="text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          View all →
        </Link>
      </div>
    </div>
  );
}

function QueueTable({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <th className="px-4 py-3">Patient</th>
          <th className="px-4 py-3">Why</th>
          <th className="px-4 py-3">Priority</th>
          <th className="px-4 py-3">Owner</th>
          <th className="px-4 py-3"></th>
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
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
  ) =>
    rows.map((instance) => (
      <tr key={instance.id} className="border-b border-slate-100 last:border-0">
        <td className="px-4 py-3 font-medium text-slate-800">
          {patientLabel(nameMap, instance.patient_id)}
        </td>
        <td className="px-4 py-3 text-slate-700">
          {FOLLOW_UP_LABELS[scheduleMap.get(instance.schedule_id) ?? "observation"] ?? "Follow-up"}
          <span className="text-slate-500"> · due {instance.due_date}</span>
        </td>
        <td className="px-4 py-3">
          <Badge tone={tone}>{statusLabel}</Badge>
        </td>
        <td className="px-4 py-3 text-slate-600">
          {ownerLabel(userMap, instance.assigned_staff_id)}
        </td>
        <td className="px-4 py-3 text-right">
          <Link
            to="/follow-ups"
            className="text-sm font-medium text-brand-600 hover:text-brand-700"
          >
            Work queue
          </Link>
        </td>
      </tr>
    ));

  const failureRows = (messages: WhatsAppMessage[]) =>
    messages.map((message) => (
      <tr key={message.id} className="border-b border-slate-100 last:border-0">
        <td className="px-4 py-3 font-medium text-slate-800">
          {patientLabel(nameMap, message.patient_id)}
        </td>
        <td className="max-w-md px-4 py-3 text-slate-700">
          {(message.text_body ?? "outbound message").slice(0, 90)}
          {message.error_message ? (
            <span className="text-slate-500"> · {message.error_message}</span>
          ) : null}
        </td>
        <td className="px-4 py-3">
          <Badge tone="red">failed</Badge>
        </td>
        <td className="px-4 py-3 text-slate-600">—</td>
        <td className="px-4 py-3 text-right">
          {message.patient_id ? (
            <Link
              to={`/patients/${message.patient_id}`}
              className="text-sm font-medium text-brand-600 hover:text-brand-700"
            >
              Patient
            </Link>
          ) : null}
        </td>
      </tr>
    ));

  const exceptionRows = (rows: MessageException[]) =>
    rows.map((exception) => (
      <tr key={exception.id} className="border-b border-slate-100 last:border-0">
        <td className="px-4 py-3 font-medium text-slate-800">
          {patientLabel(nameMap, exception.patient_id)}
        </td>
        <td className="px-4 py-3 text-slate-700">
          {reasonLabel(exception.reason)}
          <span className="text-slate-500"> · {detailSummary(exception.details)}</span>
        </td>
        <td className="px-4 py-3">
          <Badge tone="amber">needs review</Badge>
        </td>
        <td className="px-4 py-3 text-slate-600">—</td>
        <td className="px-4 py-3 text-right">
          <Link
            to="/message-exceptions"
            className="text-sm font-medium text-brand-600 hover:text-brand-700"
          >
            Review
          </Link>
        </td>
      </tr>
    ));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Operations queue</h1>
        <p className="text-sm text-slate-500">
          Everything needing attention: alerts, overdue and unanswered follow-ups, failed
          deliveries and pending reviews.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Open alerts</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">
            {alerts.data?.total ?? "—"}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Overdue</p>
          <p className="mt-1 text-2xl font-semibold text-red-600">{overdue.data?.total ?? "—"}</p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Awaiting reply</p>
          <p className="mt-1 text-2xl font-semibold text-amber-600">
            {awaiting.data?.total ?? "—"}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Failed sends</p>
          <p className="mt-1 text-2xl font-semibold text-red-600">
            {failures.data?.total ?? "—"}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Reviews</p>
          <p className="mt-1 text-2xl font-semibold text-amber-600">
            {(exceptions.data?.total ?? 0) + reviewCount}
          </p>
        </div>
      </div>

      <Card>
        <SectionHeader
          title="Open alerts"
          subtitle="Urgent and priority rule alerts awaiting disposition"
          count={alerts.data?.total}
          viewAllTo="/alerts"
        />
        {alerts.isPending ? (
          <Loading />
        ) : alerts.isError ? (
          <ErrorNotice message="Failed to load alerts." />
        ) : !alerts.data || alerts.data.items.length === 0 ? (
          <EmptyState message="No open alerts." />
        ) : (
          <QueueTable>
            {alerts.data.items.map((alert) => (
              <tr key={alert.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-800">
                  {patientLabel(nameMap, alert.patient_id)}
                </td>
                <td className="max-w-md px-4 py-3 text-slate-700">
                  {alert.reason}
                  {alert.metric ? (
                    <span className="text-slate-500">
                      {" "}
                      · {alert.metric} {alert.value ?? ""} {alert.unit ?? ""}
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={ALERT_PRIORITY_TONE[alert.priority]}>{alert.priority}</Badge>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {ownerLabel(userMap, alert.assigned_to)}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    to="/alerts"
                    className="text-sm font-medium text-brand-600 hover:text-brand-700"
                  >
                    Review
                  </Link>
                </td>
              </tr>
            ))}
          </QueueTable>
        )}
      </Card>

      <Card>
        <SectionHeader
          title="Overdue follow-ups"
          subtitle="Missed response deadlines that need a nudge or manual follow-up"
          count={overdue.data?.total}
          viewAllTo="/follow-ups"
        />
        {overdue.isPending ? (
          <Loading />
        ) : overdue.isError ? (
          <ErrorNotice message="Failed to load overdue follow-ups." />
        ) : !overdue.data || overdue.data.items.length === 0 ? (
          <EmptyState message="Nothing is overdue." />
        ) : (
          <QueueTable>{instanceRows(overdue.data.items, "overdue", "red")}</QueueTable>
        )}
      </Card>

      <Card>
        <SectionHeader
          title="Unanswered check-ins"
          subtitle="Messages delivered or read with no patient reply yet"
          count={awaiting.data?.total}
          viewAllTo="/follow-ups"
        />
        {awaiting.isPending ? (
          <Loading />
        ) : awaiting.isError ? (
          <ErrorNotice message="Failed to load unanswered check-ins." />
        ) : !awaiting.data || awaiting.data.items.length === 0 ? (
          <EmptyState message="No check-ins awaiting a reply." />
        ) : (
          <QueueTable>{instanceRows(awaiting.data.items, "awaiting reply", "amber")}</QueueTable>
        )}
      </Card>

      <Card>
        <SectionHeader
          title="Failed deliveries"
          subtitle="Outbound WhatsApp messages that failed to deliver"
          count={failures.data?.total}
          viewAllTo="/message-exceptions"
        />
        {failures.isPending ? (
          <Loading />
        ) : failures.isError ? (
          <ErrorNotice message="Failed to load delivery failures." />
        ) : !failures.data || failures.data.items.length === 0 ? (
          <EmptyState message="No failed deliveries in this window." />
        ) : (
          <QueueTable>{failureRows(failures.data.items)}</QueueTable>
        )}
      </Card>

      <Card>
        <SectionHeader
          title="Pending reviews"
          subtitle={`Open inbound exceptions, plus ${overview.data?.pending_observation_reviews ?? 0} observation reviews and ${overview.data?.ai_needs_clarification ?? 0} AI clarifications`}
          count={(exceptions.data?.total ?? 0) + reviewCount}
          viewAllTo="/message-exceptions"
        />
        {exceptions.isPending ? (
          <Loading />
        ) : exceptions.isError ? (
          <ErrorNotice message="Failed to load pending reviews." />
        ) : !exceptions.data || exceptions.data.items.length === 0 ? (
          <EmptyState message="No inbound messages waiting for review." />
        ) : (
          <QueueTable>{exceptionRows(exceptions.data.items)}</QueueTable>
        )}
      </Card>
    </div>
  );
}