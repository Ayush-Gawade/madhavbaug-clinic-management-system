import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, EmptyState, ErrorNotice, Loading, Modal } from "@/components/ui";
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

function StatCard({ label, value, tone }: { label: string; value: number; tone?: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold ${
          tone === "red" ? "text-red-600" : tone === "amber" ? "text-amber-600" : "text-slate-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function ActionHistory({ entries }: { entries: { id: string; action_type: string; to_status: string | null; occurred_at: string; notes: string | null }[] }): JSX.Element {
  return (
    <div className="border-t border-slate-200 pt-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Action history</p>
      {entries.length === 0 ? (
        <p className="text-sm text-slate-400">No actions recorded yet.</p>
      ) : (
        <ul className="space-y-1 text-sm text-slate-700">
          {entries.map((entry) => (
            <li key={entry.id}>
              <span className="font-medium">{entry.action_type}</span>
              {entry.to_status ? ` → ${entry.to_status}` : ""} · {new Date(entry.occurred_at).toLocaleString("en-IN")}
              {entry.notes ? ` · ${entry.notes}` : ""}
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
            <Badge tone={PRIORITY_TONE[alert.priority]}>{alert.priority}</Badge>
            <Badge tone={STATUS_TONE[alert.status]}>{alert.status}</Badge>
            <span className="text-xs text-slate-500">
              created {new Date(alert.created_at).toLocaleString("en-IN")}
            </span>
          </div>

          <p className="text-sm text-slate-800">{alert.reason}</p>

          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Patient</dt>
              <dd className="font-mono text-xs text-slate-600">{alert.patient_id.slice(0, 8)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Metric</dt>
              <dd className="text-slate-700">
                {alert.metric ?? "—"}
                {alert.value ? ` · ${alert.value} ${alert.unit ?? ""}` : ""}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Rule version</dt>
              <dd className="text-slate-700">{alert.rule_version ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Type</dt>
              <dd className="text-slate-700">{alert.alert_type}</dd>
            </div>
          </dl>

          {!closed ? (
            <div className="space-y-3 border-t border-slate-200 pt-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="alert-notes">
                  Notes
                </label>
                <textarea
                  id="alert-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none"
                  placeholder="Clinical note (optional)"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={alert.status === "acknowledged" || ack.isPending}
                  onClick={() => ack.mutate()}
                  className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
                >
                  Acknowledge
                </button>
                <button
                  type="button"
                  disabled={escalate.isPending}
                  onClick={() => escalate.mutate()}
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Escalate
                </button>
                <button
                  type="button"
                  disabled={resolve.isPending}
                  onClick={() => resolve.mutate()}
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Resolve
                </button>
                <button
                  type="button"
                  disabled={dismiss.isPending}
                  onClick={() => dismiss.mutate()}
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Dismiss
                </button>
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
      void queryClient.invalidateQueries({ queryKey: ["safety-rules"] });
      onClose();
    },
  });

  if (!open) return null;

  return (
    <Modal open onClose={onClose} title="New safety rule">
      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="rule-key">
            Rule key
          </label>
          <input
            id="rule-key"
            value={payload.rule_key}
            onChange={(event) => setPayload({ ...payload, rule_key: event.target.value })}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="e.g. glucose_high"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="rule-metric">
              Metric
            </label>
            <select
              id="rule-metric"
              value={payload.metric}
              onChange={(event) =>
                setPayload({ ...payload, metric: event.target.value as RuleMetric })
              }
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {METRIC_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="rule-comparator">
              Comparator
            </label>
            <select
              id="rule-comparator"
              value={payload.comparator}
              onChange={(event) => setPayload({ ...payload, comparator: event.target.value as RuleComparator })}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {COMPARATOR_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="rule-threshold">
              Threshold
            </label>
            <input
              id="rule-threshold"
              value={String(payload.threshold)}
              inputMode="decimal"
              onChange={(event) => setPayload({ ...payload, threshold: event.target.value })}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="rule-unit">
              Unit
            </label>
            <input
              id="rule-unit"
              value={payload.unit}
              onChange={(event) => setPayload({ ...payload, unit: event.target.value })}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="rule-priority">
            Priority
          </label>
          <select
            id="rule-priority"
            value={payload.priority}
            onChange={(event) => setPayload({ ...payload, priority: event.target.value as AlertPriority })}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        {create.isError ? (
          <ErrorNotice
            message={create.error instanceof ApiError ? create.error.message : "Failed to create rule."}
          />
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={create.isPending}
            onClick={() => create.mutate()}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {create.isPending ? "Publishing…" : "Publish rule"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function AlertsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AlertStatus | "">("open");
  const [priority, setPriority] = useState<AlertPriority | "">("");
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
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["safety-rules"] }),
  });

  const totalPages = alerts.data ? Math.max(1, Math.ceil(alerts.data.total / 20)) : 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Alerts &amp; review</h1>
        <p className="text-sm text-slate-500">
          Rule-driven clinical alerts awaiting staff review and disposition.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Open" value={summary.data?.open_total ?? 0} />
        <StatCard label="Urgent open" value={summary.data?.open_urgent ?? 0} tone="red" />
        <StatCard label="Priority open" value={summary.data?.open_priority ?? 0} tone="amber" />
        <StatCard label="Acknowledged" value={summary.data?.acknowledged ?? 0} />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Review queue</h2>
          <div className="flex gap-2">
            <select
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
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
            </select>
            <select
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
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
            </select>
          </div>
        </div>

        {alerts.isPending ? (
          <Loading />
        ) : alerts.isError ? (
          <ErrorNotice message="Failed to load alerts." />
        ) : !alerts.data || alerts.data.items.length === 0 ? (
          <EmptyState message="No alerts for this filter." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Alert</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {alerts.data.items.map((alert) => (
                <tr key={alert.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 text-slate-600">
                    {new Date(alert.created_at).toLocaleString("en-IN")}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {alert.patient_id.slice(0, 8)}
                  </td>
                  <td className="max-w-md px-4 py-3 text-slate-700">{alert.reason}</td>
                  <td className="px-4 py-3">
                    <Badge tone={PRIORITY_TONE[alert.priority]}>{alert.priority}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONE[alert.status]}>{alert.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setReviewId(alert.id)}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
          <span>
            Page {page} of {totalPages} · {alerts.data?.total ?? 0} total
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Safety rules</h2>
            <p className="text-xs text-slate-500">
              Deterministic thresholds. Publishing a change creates a new version.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowNewRule(true)}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
          >
            New rule
          </button>
        </div>

        {rules.isPending ? (
          <Loading />
        ) : rules.isError ? (
          <ErrorNotice message="Failed to load safety rules." />
        ) : !rules.data || rules.data.length === 0 ? (
          <EmptyState message="No active safety rules configured." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Version</th>
                <th className="px-4 py-3">Condition</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {rules.data.map((rule) => (
                <tr key={rule.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-800">{rule.rule_key}</td>
                  <td className="px-4 py-3 text-slate-600">v{rule.version}</td>
                  <td className="px-4 py-3 text-slate-700">
                    {rule.metric} {rule.comparator} {rule.threshold} {rule.unit}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={PRIORITY_TONE[rule.priority]}>{rule.priority}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      disabled={deactivate.isPending}
                      onClick={() => deactivate.mutate(rule.id)}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
                    >
                      Deactivate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {reviewId ? <AlertReviewModal alertId={reviewId} onClose={() => setReviewId(null)} /> : null}
      <NewRuleModal open={showNewRule} onClose={() => setShowNewRule(false)} />
    </div>
  );
}
