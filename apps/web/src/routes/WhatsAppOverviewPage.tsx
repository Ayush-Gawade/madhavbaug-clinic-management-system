import { useQuery } from "@tanstack/react-query";
import { CalendarDays, MessageCircle, Send, TriangleAlert, UserX, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { MediaAttachment } from "@/components/MediaAttachment";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { StatCard } from "@/components/StatCard";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorNotice,
  Label,
  SelectInput,
  TextInput,
} from "@/components/ui";
import { getMessagingOverview } from "@/lib/analytics";
import { formatDate } from "@/lib/format";
import { listUsers } from "@/lib/users";
import type { OverviewMessage, PatientCategoryType, PatientStatus } from "@/lib/types";

const CATEGORY_LABELS: Record<PatientCategoryType, string> = {
  thyroid: "Thyroid",
  obesity: "Obesity",
  blood_pressure: "Blood pressure",
  diabetes: "Diabetes",
};

const STATUS_LABELS: Record<PatientStatus, string> = {
  active: "Active",
  inactive: "Inactive",
  archived: "Archived",
};

function todayLocal(): string {
  return new Date().toISOString().slice(0, 10);
}

function typeLabel(messageType: string): string {
  return messageType.charAt(0).toUpperCase() + messageType.slice(1).replace("_", " ");
}

function RecentMessages({ messages }: { messages: OverviewMessage[] }): JSX.Element {
  if (messages.length === 0) {
    return <EmptyState message="No WhatsApp activity in the selected range." />;
  }
  return (
    <Table minClassName="min-w-[760px]">
      <THead>
        <TH>Time</TH>
        <TH>Patient</TH>
        <TH>Direction</TH>
        <TH>Type</TH>
        <TH>Message</TH>
        <TH>Delivery</TH>
      </THead>
      <tbody>
        {messages.map((message) => (
          <TR key={message.id}>
            <TD className="whitespace-nowrap text-ink-secondary">
              {message.occurred_at ? formatDate(message.occurred_at) : "—"}
            </TD>
            <TD className="font-medium text-ink">
              {message.patient_name ?? message.patient_id?.slice(0, 8) ?? "unknown"}
            </TD>
            <TD>
              <Badge tone={message.direction === "inbound" ? "green" : "brand"} dot>
                {message.direction}
              </Badge>
            </TD>
            <TD className="text-ink-secondary">{typeLabel(message.message_type)}</TD>
            <TD className="max-w-72">
              <div className="flex items-center gap-3">
                <MediaAttachment
                  mediaUrl={message.media_url}
                  mediaMimeType={message.media_mime_type}
                  compact
                />
                <span className="truncate text-ink-secondary">{message.text_body ?? "—"}</span>
              </div>
            </TD>
            <TD>
              {message.delivery_status ? (
                <Badge tone={message.delivery_status === "failed" ? "red" : "slate"} dot={message.delivery_status === "failed"}>
                  {message.delivery_status}
                </Badge>
              ) : (
                <span className="text-ink-faint">—</span>
              )}
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

export function WhatsAppOverviewPage(): JSX.Element {
  const [dateFrom, setDateFrom] = useState(todayLocal);
  const [dateTo, setDateTo] = useState(todayLocal);
  const [category, setCategory] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [status, setStatus] = useState("");

  // The doctor filter options come from the staff directory (owner-only); other
  // roles simply omit the selector and leave the scope unfiltered by clinician.
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => listUsers({ size: 100 }),
    retry: false,
  });
  const clinicians = useMemo(
    () =>
      (users.data?.items ?? []).filter(
        (user) => user.role === "doctor" || user.role === "dietitian",
      ),
    [users.data],
  );

  const overview = useQuery({
    queryKey: ["messaging-overview", dateFrom, dateTo, category, doctorId, status],
    queryFn: () =>
      getMessagingOverview({
        date_from: dateFrom,
        date_to: dateTo,
        category: category || undefined,
        doctor_id: doctorId || undefined,
        status: status || undefined,
      }),
  });

  const data = overview.data;
  const pendingReviews =
    (data?.pending_observation_reviews ?? 0) +
    (data?.ai_needs_clarification ?? 0) +
    (data?.open_message_exceptions ?? 0);

  // Carry the active scope filters into the patient list so a card click opens
  // the same population it is summarising.
  const patientsScopeQuery = new URLSearchParams();
  if (category) patientsScopeQuery.set("category", category);
  if (status) patientsScopeQuery.set("status", status);
  const patientsScopeTo = `/patients${
    patientsScopeQuery.toString() ? `?${patientsScopeQuery.toString()}` : ""
  }`;

  return (
    <div className="space-y-6">
      <PageHeader
        title="WhatsApp overview"
        description="Messages sent, replies, non-responders, delivery failures and review queues for the selected scope."
      />

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="overview-from">From</Label>
            <TextInput
              id="overview-from"
              type="date"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="overview-to">To</Label>
            <TextInput
              id="overview-to"
              type="date"
              value={dateTo}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="overview-category">Category</Label>
            <SelectInput
              id="overview-category"
              className="w-44"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All categories</option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectInput>
          </div>
          {!users.isError && clinicians.length > 0 ? (
            <div>
              <Label htmlFor="overview-doctor">Doctor</Label>
              <SelectInput
                id="overview-doctor"
                className="w-52"
                value={doctorId}
                onChange={(event) => setDoctorId(event.target.value)}
              >
                <option value="">All clinicians</option>
                {clinicians.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </SelectInput>
            </div>
          ) : null}
          <div>
            <Label htmlFor="overview-status">Status</Label>
            <SelectInput
              id="overview-status"
              className="w-36"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectInput>
          </div>
        </div>
      </Card>

      {overview.isPending ? (
        <SkeletonTable rows={6} cols={6} />
      ) : overview.isError ? (
        <ErrorNotice message="Failed to load the WhatsApp overview." />
      ) : data ? (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <StatCard
              label="Patients in scope"
              icon={<Users className="h-4 w-4" />}
              value={data.patients_in_scope}
              to={patientsScopeTo}
              ariaLabel={`View ${data.patients_in_scope} patients in scope`}
            />
            <StatCard
              label="Patients messaged"
              icon={<Send className="h-4 w-4" />}
              tone="brand"
              value={data.patients_messaged}
              hint={`${data.messages_sent} messages sent`}
              to="/follow-ups"
              ariaLabel={`View the ${data.messages_sent} sent check-ins`}
            />
            <StatCard
              label="Patients who replied"
              icon={<MessageCircle className="h-4 w-4" />}
              value={data.patients_replied}
              hint={`${data.replies_received} replies received`}
              to="/inbox"
              ariaLabel={`View the ${data.patients_replied} patient conversations`}
            />
            <StatCard
              label="Non-responders"
              icon={<UserX className="h-4 w-4" />}
              tone="warning"
              value={data.non_responders}
              hint="no reply in window"
              to="/queues#awaiting"
              ariaLabel="View unanswered check-ins in the operations queue"
            />
            <StatCard
              label="Patients with failures"
              icon={<TriangleAlert className="h-4 w-4" />}
              tone="danger"
              value={data.patients_with_failures}
              hint={`${data.delivery_failures} failed messages`}
              to="/queues#failures"
              ariaLabel="View failed deliveries in the operations queue"
            />
            <StatCard
              label="Patients with critical alerts"
              icon={<TriangleAlert className="h-4 w-4" />}
              tone="danger"
              value={data.patients_with_critical_alerts}
              hint={`${data.critical_alerts} urgent alerts`}
              to="/alerts?status=open&priority=urgent"
              ariaLabel="View urgent open alerts"
            />
          </div>

          <Card>
            <CardHeader title="Review queues" description="Jump to the right workspace" />
            <div className="grid gap-3 p-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <Link
                to="/alerts"
                className="group rounded-xl border border-line bg-surface p-4 shadow-hairline transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover dark:hover:border-brand-700"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Open alerts
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">
                  {data.critical_alerts}{" "}
                  <span className="text-sm font-semibold text-red-600 dark:text-red-400">urgent</span>
                </p>
              </Link>
              <Link
                to="/message-exceptions"
                className="group rounded-xl border border-line bg-surface p-4 shadow-hairline transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover dark:hover:border-brand-700"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Message exceptions
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">
                  {data.open_message_exceptions}{" "}
                  <span className="text-sm font-semibold text-ink-muted">open</span>
                </p>
              </Link>
              <Link
                to="/follow-ups"
                className="group rounded-xl border border-line bg-surface p-4 shadow-hairline transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover dark:hover:border-brand-700"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Follow-up queue
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">
                  {data.non_responders}{" "}
                  <span className="text-sm font-semibold text-ink-muted">waiting</span>
                </p>
              </Link>
              <Link
                to="/analytics"
                className="group rounded-xl border border-line bg-surface p-4 shadow-hairline transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover dark:hover:border-brand-700"
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  Pending reviews
                </p>
                <p className="mt-1 text-2xl font-bold tabular-nums text-ink">
                  {pendingReviews}{" "}
                  <span className="text-sm font-semibold text-ink-muted">pending</span>
                </p>
                <p className="mt-1 text-xs text-ink-muted">
                  {data.pending_observation_reviews} observation · {data.ai_needs_clarification} AI
                </p>
              </Link>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Recent message activity"
              actions={
                <span className="flex items-center gap-1.5 text-xs text-ink-muted">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {data.date_from} → {data.date_to}
                </span>
              }
            />
            <RecentMessages messages={data.recent_messages} />
          </Card>
        </div>
      ) : null}
    </div>
  );
}
