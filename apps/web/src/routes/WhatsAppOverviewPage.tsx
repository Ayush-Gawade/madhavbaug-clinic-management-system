import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  Badge,
  Card,
  EmptyState,
  ErrorNotice,
  Label,
  Loading,
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

function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number | undefined;
  tone?: "default" | "warning" | "danger";
}): JSX.Element {
  const tones = {
    default: "text-slate-900",
    warning: "text-amber-600",
    danger: "text-red-600",
  };
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tones[tone]}`}>{value ?? "—"}</p>
    </div>
  );
}

function typeLabel(messageType: string): string {
  return messageType.charAt(0).toUpperCase() + messageType.slice(1).replace("_", " ");
}

function RecentMessages({ messages }: { messages: OverviewMessage[] }): JSX.Element {
  if (messages.length === 0) {
    return <EmptyState message="No WhatsApp activity in the selected range." />;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <th className="px-4 py-3">Time</th>
          <th className="px-4 py-3">Patient</th>
          <th className="px-4 py-3">Direction</th>
          <th className="px-4 py-3">Type</th>
          <th className="px-4 py-3">Message</th>
          <th className="px-4 py-3">Delivery</th>
        </tr>
      </thead>
      <tbody>
        {messages.map((message) => (
          <tr key={message.id} className="border-b border-slate-100 last:border-0">
            <td className="px-4 py-3 text-slate-600">
              {message.occurred_at ? formatDate(message.occurred_at) : "—"}
            </td>
            <td className="px-4 py-3 text-slate-800">
              {message.patient_name ?? message.patient_id?.slice(0, 8) ?? "unknown"}
            </td>
            <td className="px-4 py-3">
              <Badge tone={message.direction === "inbound" ? "green" : "brand"}>
                {message.direction}
              </Badge>
            </td>
            <td className="px-4 py-3 text-slate-600">{typeLabel(message.message_type)}</td>
            <td className="max-w-72 px-4 py-3 text-slate-700">
              {message.text_body ?? "—"}
            </td>
            <td className="px-4 py-3">
              {message.delivery_status ? (
                <Badge tone={message.delivery_status === "failed" ? "red" : "slate"}>
                  {message.delivery_status}
                </Badge>
              ) : (
                "—"
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
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

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">WhatsApp overview</h1>
          <p className="text-sm text-slate-500">
            Messages sent, replies, non-responders, delivery failures and review queues for the
            selected scope.
          </p>
        </div>
      </div>

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

      {overview.isPending ? (
        <Loading />
      ) : overview.isError ? (
        <ErrorNotice message="Failed to load the WhatsApp overview." />
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <StatCard label="Patients in scope" value={data.patients_in_scope} />
            <StatCard label="Messages sent" value={data.messages_sent} />
            <StatCard label="Replies received" value={data.replies_received} />
            <StatCard label="Non-responders" value={data.non_responders} tone="warning" />
            <StatCard label="Delivery failures" value={data.delivery_failures} tone="danger" />
            <StatCard label="Critical alerts" value={data.critical_alerts} tone="danger" />
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-800">Review queues</h2>
            <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <Link
                to="/alerts"
                className="rounded-md border border-slate-200 p-3 hover:border-brand-300 hover:bg-brand-50"
              >
                <p className="font-medium text-slate-800">Open alerts</p>
                <p className="text-2xl font-semibold text-slate-900">{data.critical_alerts} urgent</p>
              </Link>
              <Link
                to="/message-exceptions"
                className="rounded-md border border-slate-200 p-3 hover:border-brand-300 hover:bg-brand-50"
              >
                <p className="font-medium text-slate-800">Message exceptions</p>
                <p className="text-2xl font-semibold text-slate-900">
                  {data.open_message_exceptions} open
                </p>
              </Link>
              <Link
                to="/follow-ups"
                className="rounded-md border border-slate-200 p-3 hover:border-brand-300 hover:bg-brand-50"
              >
                <p className="font-medium text-slate-800">Follow-up queue</p>
                <p className="text-2xl font-semibold text-slate-900">{data.non_responders} waiting</p>
              </Link>
              <Link
                to="/analytics"
                className="rounded-md border border-slate-200 p-3 hover:border-brand-300 hover:bg-brand-50"
              >
                <p className="font-medium text-slate-800">Pending reviews</p>
                <p className="text-2xl font-semibold text-slate-900">{pendingReviews} pending</p>
                <p className="mt-1 text-xs text-slate-500">
                  {data.pending_observation_reviews} observation · {data.ai_needs_clarification} AI
                </p>
              </Link>
            </div>
          </div>

          <Card>
            <div className="border-b border-slate-200 px-4 py-3">
              <h2 className="text-sm font-semibold text-slate-800">Recent message activity</h2>
            </div>
            <RecentMessages messages={data.recent_messages} />
          </Card>
        </>
      ) : null}
    </div>
  );
}