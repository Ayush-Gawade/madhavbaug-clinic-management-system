import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Button, Card, EmptyState, ErrorNotice, Loading, SelectInput } from "@/components/ui";
import { formatDate } from "@/lib/format";
import {
  acknowledgeInstance,
  getFollowUpDayCount,
  listInstances,
  processDue,
  processNonResponse,
  resolveInstance,
} from "@/lib/schedules";
import type { FollowUpInstanceStatus } from "@/lib/types";

const STATUS_OPTIONS: FollowUpInstanceStatus[] = [
  "scheduled",
  "queued",
  "sent",
  "delivered",
  "read",
  "responded",
  "overdue",
  "failed",
  "skipped",
];

const STATUS_TONE: Record<FollowUpInstanceStatus, "slate" | "green" | "amber" | "red" | "blue"> = {
  scheduled: "slate",
  queued: "blue",
  sent: "blue",
  delivered: "blue",
  read: "blue",
  responded: "green",
  overdue: "amber",
  failed: "red",
  skipped: "slate",
};

function StatCard({ label, value }: { label: string; value: number | undefined }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value ?? "—"}</p>
    </div>
  );
}

export function FollowUpsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<FollowUpInstanceStatus | "">("");
  const [page, setPage] = useState(1);

  const counts = useQuery({ queryKey: ["follow-up-counts"], queryFn: getFollowUpDayCount });
  const instances = useQuery({
    queryKey: ["instances", status, page],
    queryFn: () => listInstances({ status: status || undefined, page, size: 20 }),
  });

  const dispatch = useMutation({
    mutationFn: processDue,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instances"] });
      void queryClient.invalidateQueries({ queryKey: ["follow-up-counts"] });
    },
  });

  const nonResponse = useMutation({
    mutationFn: processNonResponse,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instances"] });
      void queryClient.invalidateQueries({ queryKey: ["follow-up-counts"] });
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const acknowledge = useMutation({
    mutationFn: (instanceId: string) => acknowledgeInstance(instanceId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["instances"] }),
  });

  const resolve = useMutation({
    mutationFn: (instanceId: string) => resolveInstance(instanceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instances"] });
      void queryClient.invalidateQueries({ queryKey: ["follow-up-counts"] });
    },
  });

  const totalPages = instances.data ? Math.max(1, Math.ceil(instances.data.total / 20)) : 1;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Follow-up operations</h1>
          <p className="text-sm text-slate-500">Scheduled, sent, responded and overdue check-ins.</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            onClick={() => nonResponse.mutate()}
            disabled={nonResponse.isPending}
          >
            {nonResponse.isPending ? "Running…" : "Run non-response"}
          </Button>
          <Button onClick={() => dispatch.mutate()} disabled={dispatch.isPending}>
            {dispatch.isPending ? "Running…" : "Run dispatch now"}
          </Button>
        </div>
      </div>

      {nonResponse.data ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
          Reminders sent: {nonResponse.data.reminders_sent} · Failed:{" "}
          {nonResponse.data.reminders_failed} · Flagged overdue:{" "}
          {nonResponse.data.marked_overdue} · Escalations: {nonResponse.data.escalations_created}
        </div>
      ) : null}

      {dispatch.data ? (
        <div className="rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-800">
          Dispatched: {dispatch.data.eligible_to_send} queued · {dispatch.data.skipped_consent} held
          (missing consent).
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Due today" value={counts.data?.due_today} />
        <StatCard label="Overdue" value={counts.data?.overdue} />
        <StatCard label="Done today" value={counts.data?.done_today} />
      </div>

      <Card>
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Queue</h2>
          <SelectInput
            className="w-44"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as FollowUpInstanceStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </SelectInput>
        </div>

        {instances.isPending ? (
          <Loading />
        ) : instances.isError ? (
          <ErrorNotice message="Failed to load follow-up instances." />
        ) : !instances.data || instances.data.items.length === 0 ? (
          <EmptyState message="No follow-up instances for this filter." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Due</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Deadline</th>
                <th className="px-4 py-3">Reminders</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {instances.data.items.map((instance) => (
                <tr key={instance.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3">{formatDate(instance.due_at)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {instance.patient_id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {instance.response_deadline_at ? formatDate(instance.response_deadline_at) : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{instance.reminder_count}</td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONE[instance.status]}>{instance.status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    {instance.status === "overdue" ? (
                      <div className="flex gap-2">
                        <Button
                          variant="ghost"
                          onClick={() => acknowledge.mutate(instance.id)}
                          disabled={acknowledge.isPending || instance.acknowledged_at !== null}
                        >
                          Acknowledge
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => resolve.mutate(instance.id)}
                          disabled={resolve.isPending}
                        >
                          Resolve
                        </Button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
          <span>
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </Button>
            <Button
              variant="ghost"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}