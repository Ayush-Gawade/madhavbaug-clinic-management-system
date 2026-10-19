import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, Clock, Play, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { StatCard } from "@/components/StatCard";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import { toast } from "@/components/Toast";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  ErrorNotice,
  Pagination,
  SelectInput,
} from "@/components/ui";
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

export function FollowUpsPage(): JSX.Element {
  const queryClient = useQueryClient();
  // Seed the status filter from the URL so cards (Dashboard, WhatsApp overview)
  // can deep-link into a pre-filtered follow-up queue.
  const [searchParams] = useSearchParams();
  const initialStatus = searchParams.get("status") ?? "";
  const [status, setStatus] = useState<FollowUpInstanceStatus | "">(() =>
    (STATUS_OPTIONS as string[]).includes(initialStatus)
      ? (initialStatus as FollowUpInstanceStatus)
      : "",
  );
  const [page, setPage] = useState(1);

  const counts = useQuery({ queryKey: ["follow-up-counts"], queryFn: getFollowUpDayCount });
  const instances = useQuery({
    queryKey: ["instances", status, page],
    queryFn: () => listInstances({ status: status || undefined, page, size: 20 }),
  });

  const dispatch = useMutation({
    mutationFn: processDue,
    onSuccess: () => {
      toast.success("Dispatch run complete");
      void queryClient.invalidateQueries({ queryKey: ["instances"] });
      void queryClient.invalidateQueries({ queryKey: ["follow-up-counts"] });
    },
  });

  const nonResponse = useMutation({
    mutationFn: processNonResponse,
    onSuccess: () => {
      toast.success("Non-response pass complete");
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
    <div className="space-y-6">
      <PageHeader
        title="Follow-up operations"
        description="Scheduled, sent, responded and overdue check-ins."
        actions={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => nonResponse.mutate()}
              disabled={nonResponse.isPending}
              loading={nonResponse.isPending}
            >
              <Sparkles className="h-4 w-4" />
              {nonResponse.isPending ? "Running…" : "Run non-response"}
            </Button>
            <Button
              onClick={() => dispatch.mutate()}
              disabled={dispatch.isPending}
              loading={dispatch.isPending}
            >
              <Play className="h-4 w-4" />
              {dispatch.isPending ? "Running…" : "Run dispatch now"}
            </Button>
          </div>
        }
      />

      {nonResponse.data ? (
        <Callout tone="warning">
          Reminders sent: {nonResponse.data.reminders_sent} · Failed:{" "}
          {nonResponse.data.reminders_failed} · Flagged overdue:{" "}
          {nonResponse.data.marked_overdue} · Escalations: {nonResponse.data.escalations_created}
        </Callout>
      ) : null}

      {dispatch.data ? (
        <Callout tone="info">
          Dispatched: {dispatch.data.eligible_to_send} queued · {dispatch.data.skipped_consent}{" "}
          held (missing consent).
        </Callout>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Due today"
          icon={<Send className="h-4 w-4" />}
          isLoading={counts.isPending}
          value={counts.data?.due_today ?? "—"}
        />
        <StatCard
          label="Overdue"
          icon={<Clock className="h-4 w-4" />}
          tone="danger"
          isLoading={counts.isPending}
          value={counts.data?.overdue ?? "—"}
        />
        <StatCard
          label="Done today"
          icon={<CalendarCheck className="h-4 w-4" />}
          tone="success"
          isLoading={counts.isPending}
          value={counts.data?.done_today ?? "—"}
        />
      </div>

      <Card>
        <CardHeader
          title="Queue"
          description="Every follow-up instance for the current filter."
          actions={
            <SelectInput
              aria-label="Filter by status"
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
          }
        />

        {instances.isPending ? (
          <SkeletonTable rows={6} cols={6} />
        ) : instances.isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load follow-up instances." />
          </div>
        ) : !instances.data || instances.data.items.length === 0 ? (
          <EmptyState message="No follow-up instances for this filter." />
        ) : (
          <Table minClassName="min-w-[780px]">
            <THead>
              <TH>Due</TH>
              <TH>Patient</TH>
              <TH>Deadline</TH>
              <TH align="center">Reminders</TH>
              <TH>Status</TH>
              <TH align="right">Actions</TH>
            </THead>
            <tbody>
              {instances.data.items.map((instance) => (
                <TR key={instance.id}>
                  <TD className="whitespace-nowrap font-medium text-ink">
                    {formatDate(instance.due_at)}
                  </TD>
                  <TD className="font-medium text-ink">
                    <Link
                      to={`/patients/${instance.patient_id}`}
                      className="text-ink underline-offset-2 hover:text-brand-700 hover:underline dark:hover:text-brand-300"
                    >
                      {instance.patient_name ?? instance.patient_id.slice(0, 8)}
                    </Link>
                  </TD>
                  <TD className="text-ink-secondary">
                    {instance.response_deadline_at ? formatDate(instance.response_deadline_at) : "—"}
                  </TD>
                  <TD align="center" className="tabular-nums text-ink-secondary">
                    {instance.reminder_count}
                  </TD>
                  <TD>
                    <Badge tone={STATUS_TONE[instance.status]} dot={instance.status === "overdue"}>
                      {instance.status}
                    </Badge>
                  </TD>
                  <TD align="right">
                    {instance.status === "overdue" ? (
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => acknowledge.mutate(instance.id)}
                          disabled={acknowledge.isPending || instance.acknowledged_at !== null}
                        >
                          Acknowledge
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => resolve.mutate(instance.id)}
                          disabled={resolve.isPending}
                        >
                          Resolve
                        </Button>
                      </div>
                    ) : null}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}

        <Pagination
          page={page}
          totalPages={totalPages}
          total={instances.data?.total ?? 0}
          itemLabel="instances"
          onPageChange={setPage}
        />
      </Card>
    </div>
  );
}
