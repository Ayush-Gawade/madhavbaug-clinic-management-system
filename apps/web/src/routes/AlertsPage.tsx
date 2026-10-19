import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, TriangleAlert } from "lucide-react";
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
  Card,
  CardHeader,
  EmptyState,
  ErrorNotice,
  Label,
  Loading,
  Modal,
  Pagination,
  SelectInput,
  TextArea,
} from "@/components/ui";
import {
  acknowledgeAlert,
  createSafetyRule,
  deactivateSafetyRule,
  dismissAlert,
  escalateAlert,
  getAlert,
  getAlertSummary,
  listAlerts,
  listSafetyRules,
  resolveAlert,
} from "@/lib/alerts";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type {
  AlertPriority,
  AlertStatus,
  RuleComparator,
  RuleMetric,
  SafetyRuleCreatePayload,
} from "@/lib/types";

const STATUS_OPTIONS: AlertStatus[] = ["open", "acknowledged", "resolved", "dismissed"];
const PRIORITY_OPTIONS: AlertPriority[] = ["routine", "priority", "urgent"];
const METRIC_OPTIONS: RuleMetric[] = ["blood_glucose", "weight", "systolic", "diastolic"];
const COMPARATOR_OPTIONS: RuleComparator[] = ["gt", "gte", "lt", "lte"];

const PRIORITY_TONE: Record<AlertPriority, "slate" | "amber" | "red"> = {
  urgent: "red",
  priority: "amber",
  routine: "slate",
};

const STATUS_TONE: Record<AlertStatus, "slate" | "green" | "amber" | "red"> = {
  open: "red",
  acknowledged: "amber",
  resolved: "green",
  dismissed: "slate",
};

function ActionHistory({
  entries,
}: {
  entries: { id: string; action_type: string; to_status: string | null; occurred_at: string; notes: string | null }[];
}): JSX.Element {
  return (
    <div className="border-t border-line pt-4">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-ink-muted">
        Action history
      </p>
      {entries.length === 0 ? (
        <p className="text-sm text-ink-muted">No actions recorded yet.</p>
      ) : (
        <ul className="space-y-1.5 text-sm text-ink-secondary">
          {entries.map((entry) => (
            <li key={entry.id} className="flex flex-wrap items-center gap-1.5">
              <Badge tone="slate">{entry.action_type}</Badge>
              {entry.to_status ? <span>→ {entry.to_status}</span> : null}
              <span className="text-ink-muted">{formatDate(entry.occurred_at)}</span>
              {entry.notes ? <span className="text-ink-muted">· {entry.notes}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AlertReviewModal({ alertId, onClose }: { alertId: string; onClose: () => void }): JSX.Element {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");

  const detail = useQuery({ queryKey: ["alert", alertId], queryFn: () => getAlert(alertId) });

  const onSuccess = (): void => {
    setNotes("");
    void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    void queryClient.invalidateQueries({ queryKey: ["alert-summary"] });
    void queryClient.invalidateQueries({ queryKey: ["alert", alertId] });
  };

  const ack = useMutation({
    mutationFn: () => acknowledgeAlert(alertId, notes || undefined),
    onSuccess,
  });
  const escalate = useMutation({
    mutationFn: () => escalateAlert(alertId, notes || undefined),
    onSuccess,
  });
  const resolve = useMutation({
    mutationFn: () => resolveAlert(alertId, notes || undefined),
    onSuccess,
  });
  const dismiss = useMutation({
    mutationFn: () => dismissAlert(alertId, notes || undefined),
    onSuccess,
  });

  const alert = detail.data;
  const closed = alert?.status === "resolved" || alert?.status === "dismissed";
  const errors = [ack.error, escalate.error, resolve.error, dismiss.error].filter(
    (error): error is Error => error instanceof Error,
  );

  return (
    <Modal open onClose={onClose} title="Review alert">
      {detail.isPending ? (
        <Loading />
      ) : detail.isError || !alert ? (
        <ErrorNotice message="Failed to load alert." />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={PRIORITY_TONE[alert.priority]} dot>
              {alert.priority}
            </Badge>
            <Badge tone={STATUS_TONE[alert.status]}>{alert.status}</Badge>
            <span className="text-xs text-ink-muted">created {formatDate(alert.created_at)}</span>
          </div>

          <p className="rounded-lg bg-surface-sunken px-3.5 py-3 text-sm font-medium text-ink">
            {alert.reason}
          </p>

          <dl className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-line px-3.5 py-2.5">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Patient</dt>
              <dd className="mt-0.5 text-sm font-medium text-ink">
                <Link
                  to={`/patients/${alert.patient_id}`}
                  className="underline-offset-2 hover:text-brand-700 hover:underline dark:hover:text-brand-300"
                >
                  {alert.patient_name ?? alert.patient_id.slice(0, 8)}
                </Link>
              </dd>
            </div>
            <div className="rounded-lg border border-line px-3.5 py-2.5">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Metric</dt>
              <dd className="mt-0.5 text-sm text-ink">
                {alert.metric ?? "—"}
                {alert.value ? ` · ${alert.value} ${alert.unit ?? ""}` : ""}
              </dd>
            </div>
            <div className="rounded-lg border border-line px-3.5 py-2.5">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Rule version</dt>
              <dd className="mt-0.5 text-sm text-ink">{alert.rule_version ?? "—"}</dd>
            </div>
            <div className="rounded-lg border border-line px-3.5 py-2.5">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">Type</dt>
              <dd className="mt-0.5 text-sm capitalize text-ink">{alert.alert_type}</dd>
            </div>
          </dl>

          {!closed ? (
            <div className="space-y-3 border-t border-line pt-4">
              <div>
                <Label htmlFor="alert-notes">Notes</Label>
                <TextArea
                  id="alert-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  placeholder="Clinical note (optional)"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  disabled={alert.status === "acknowledged" || ack.isPending}
                  onClick={() => ack.mutate()}
                >
                  Acknowledge
                </Button>
                <Button
                  variant="secondary"
                  disabled={escalate.isPending}
                  onClick={() => escalate.mutate()}
                >
                  Escalate
                </Button>
                <Button
                  variant="secondary"
                  disabled={resolve.isPending}
                  onClick={() => resolve.mutate()}
                >
                  Resolve
                </Button>
                <Button
                  variant="secondary"
                  disabled={dismiss.isPending}
                  onClick={() => dismiss.mutate()}
                >
                  Dismiss
                </Button>
              </div>
              {errors.map((error, index) => (
                <ErrorNotice
                  key={index}
                  message={error instanceof ApiError ? error.message : "Action failed."}
                />
              ))}
            </div>
          ) : null}

          <ActionHistory entries={alert.actions} />
        </div>
      )}
    </Modal>
  );
}

function NewRuleModal({ open, onClose }: { open: boolean; onClose: () => void }): JSX.Element | null {
  const queryClient = useQueryClient();
  const [payload, setPayload] = useState<SafetyRuleCreatePayload>({
    rule_key: "",
    metric: "blood_glucose",
    comparator: "gt",
    threshold: 200,
    unit: "mg/dL",
    priority: "priority",
    description: "",
  });

  const create = useMutation({
    mutationFn: () => createSafetyRule(payload),
    onSuccess: () => {
      toast.success("Safety rule published");
      void queryClient.invalidateQueries({ queryKey: ["safety-rules"] });
      onClose();
    },
  });

  if (!open) return null;

  return (
    <Modal open onClose={onClose} title="New safety rule">
      <div className="space-y-4">
        <div>
          <Label htmlFor="rule-key">Rule key</Label>
          <input
            id="rule-key"
            value={payload.rule_key}
            onChange={(event) => setPayload({ ...payload, rule_key: event.target.value })}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-hairline focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10"
            placeholder="e.g. glucose_high"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="rule-metric">Metric</Label>
            <SelectInput
              id="rule-metric"
              value={payload.metric}
              onChange={(event) =>
                setPayload({ ...payload, metric: event.target.value as RuleMetric })
              }
            >
              {METRIC_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </SelectInput>
          </div>
          <div>
            <Label htmlFor="rule-comparator">Comparator</Label>
            <SelectInput
              id="rule-comparator"
              value={payload.comparator}
              onChange={(event) => setPayload({ ...payload, comparator: event.target.value as RuleComparator })}
            >
              {COMPARATOR_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </SelectInput>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="rule-threshold">Threshold</Label>
            <input
              id="rule-threshold"
              value={String(payload.threshold)}
              inputMode="decimal"
              onChange={(event) => setPayload({ ...payload, threshold: event.target.value })}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-hairline focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10"
            />
          </div>
          <div>
            <Label htmlFor="rule-unit">Unit</Label>
            <input
              id="rule-unit"
              value={payload.unit}
              onChange={(event) => setPayload({ ...payload, unit: event.target.value })}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-hairline focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10"
            />
          </div>
        </div>
        <div>
          <Label htmlFor="rule-priority">Priority</Label>
          <SelectInput
            id="rule-priority"
            value={payload.priority}
            onChange={(event) => setPayload({ ...payload, priority: event.target.value as AlertPriority })}
          >
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </SelectInput>
        </div>
        {create.isError ? (
          <ErrorNotice
            message={create.error instanceof ApiError ? create.error.message : "Failed to create rule."}
          />
        ) : null}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={create.isPending} loading={create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Publishing…" : "Publish rule"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function AlertsPage(): JSX.Element {
  const queryClient = useQueryClient();
  // Seed the filters from the URL so cards elsewhere (Dashboard, WhatsApp
  // overview) can deep-link into a pre-filtered alert list.
  const [searchParams] = useSearchParams();
  const initialStatus = searchParams.get("status") ?? "";
  const initialPriority = searchParams.get("priority") ?? "";
  const [status, setStatus] = useState<AlertStatus | "">(() => {
    // Keep the original default (open) when no filter is supplied, otherwise
    // honour a valid deep-linked status.
    if (initialStatus === "") return "open";
    return (STATUS_OPTIONS as string[]).includes(initialStatus)
      ? (initialStatus as AlertStatus)
      : "open";
  });
  const [priority, setPriority] = useState<AlertPriority | "">(() =>
    (PRIORITY_OPTIONS as string[]).includes(initialPriority)
      ? (initialPriority as AlertPriority)
      : "",
  );
  const [page, setPage] = useState(1);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [showNewRule, setShowNewRule] = useState(false);

  const summary = useQuery({ queryKey: ["alert-summary"], queryFn: () => getAlertSummary() });
  const alerts = useQuery({
    queryKey: ["alerts", status, priority, page],
    queryFn: () =>
      listAlerts({
        status: status || undefined,
        priority: priority || undefined,
        page,
        size: 20,
      }),
  });
  const rules = useQuery({ queryKey: ["safety-rules"], queryFn: () => listSafetyRules() });

  const deactivate = useMutation({
    mutationFn: deactivateSafetyRule,
    onSuccess: () => {
      toast.success("Rule deactivated");
      void queryClient.invalidateQueries({ queryKey: ["safety-rules"] });
    },
  });

  const totalPages = alerts.data ? Math.max(1, Math.ceil(alerts.data.total / 20)) : 1;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts & review"
        description="Rule-driven clinical alerts awaiting staff review and disposition."
      />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          label="Open"
          icon={<TriangleAlert className="h-4 w-4" />}
          isLoading={summary.isPending}
          value={summary.data?.open_total ?? "—"}
        />
        <StatCard
          label="Urgent open"
          icon={<TriangleAlert className="h-4 w-4" />}
          tone="danger"
          isLoading={summary.isPending}
          value={summary.data?.open_urgent ?? "—"}
        />
        <StatCard
          label="Priority open"
          icon={<TriangleAlert className="h-4 w-4" />}
          tone="warning"
          isLoading={summary.isPending}
          value={summary.data?.open_priority ?? "—"}
        />
        <StatCard
          label="Acknowledged"
          isLoading={summary.isPending}
          value={summary.data?.acknowledged ?? "—"}
        />
      </div>

      <Card>
        <CardHeader
          title="Review queue"
          actions={
            <div className="flex gap-2">
              <SelectInput
                aria-label="Filter by status"
                className="w-40"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as AlertStatus | "");
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
              <SelectInput
                aria-label="Filter by priority"
                className="w-40"
                value={priority}
                onChange={(event) => {
                  setPriority(event.target.value as AlertPriority | "");
                  setPage(1);
                }}
              >
                <option value="">All priorities</option>
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </SelectInput>
            </div>
          }
        />

        {alerts.isPending ? (
          <SkeletonTable rows={6} cols={6} />
        ) : alerts.isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load alerts." />
          </div>
        ) : !alerts.data || alerts.data.items.length === 0 ? (
          <EmptyState
            icon={<TriangleAlert className="h-5 w-5" />}
            message="No alerts for this filter."
          />
        ) : (
          <Table minClassName="min-w-[760px]">
            <THead>
              <TH>Created</TH>
              <TH>Patient</TH>
              <TH>Alert</TH>
              <TH>Priority</TH>
              <TH>Status</TH>
              <TH align="right" />
            </THead>
            <tbody>
              {alerts.data.items.map((alert) => (
                <TR key={alert.id}>
                  <TD className="whitespace-nowrap text-ink-secondary">
                    {formatDate(alert.created_at)}
                  </TD>
                  <TD className="font-medium text-ink">
                    <Link
                      to={`/patients/${alert.patient_id}`}
                      className="underline-offset-2 hover:text-brand-700 hover:underline dark:hover:text-brand-300"
                    >
                      {alert.patient_name ?? alert.patient_id.slice(0, 8)}
                    </Link>
                  </TD>
                  <TD className="max-w-md text-ink-secondary">{alert.reason}</TD>
                  <TD>
                    <Badge tone={PRIORITY_TONE[alert.priority]} dot>
                      {alert.priority}
                    </Badge>
                  </TD>
                  <TD>
                    <Badge tone={STATUS_TONE[alert.status]}>{alert.status}</Badge>
                  </TD>
                  <TD align="right">
                    <Button variant="secondary" size="sm" onClick={() => setReviewId(alert.id)}>
                      Review
                    </Button>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}

        <Pagination
          page={page}
          totalPages={totalPages}
          total={alerts.data?.total ?? 0}
          itemLabel="alerts"
          onPageChange={setPage}
        />
      </Card>

      <Card>
        <CardHeader
          title="Safety rules"
          description="Deterministic thresholds. Publishing a change creates a new version."
          actions={
            <Button size="sm" onClick={() => setShowNewRule(true)}>
              <Plus className="h-4 w-4" />
              New rule
            </Button>
          }
        />

        {rules.isPending ? (
          <SkeletonTable rows={4} cols={5} />
        ) : rules.isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load safety rules." />
          </div>
        ) : !rules.data || rules.data.length === 0 ? (
          <EmptyState message="No active safety rules configured." />
        ) : (
          <Table minClassName="min-w-[640px]">
            <THead>
              <TH>Key</TH>
              <TH>Version</TH>
              <TH>Condition</TH>
              <TH>Priority</TH>
              <TH align="right" />
            </THead>
            <tbody>
              {rules.data.map((rule) => (
                <TR key={rule.id}>
                  <TD className="font-medium text-ink">{rule.rule_key}</TD>
                  <TD className="text-ink-secondary">v{rule.version}</TD>
                  <TD className="text-ink-secondary">
                    <code className="rounded bg-surface-sunken px-1.5 py-0.5 text-xs">
                      {rule.metric} {rule.comparator} {rule.threshold} {rule.unit}
                    </code>
                  </TD>
                  <TD>
                    <Badge tone={PRIORITY_TONE[rule.priority]}>{rule.priority}</Badge>
                  </TD>
                  <TD align="right">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={deactivate.isPending}
                      onClick={() => deactivate.mutate(rule.id)}
                    >
                      Deactivate
                    </Button>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {reviewId ? <AlertReviewModal alertId={reviewId} onClose={() => setReviewId(null)} /> : null}
      <NewRuleModal open={showNewRule} onClose={() => setShowNewRule(false)} />
    </div>
  );
}
