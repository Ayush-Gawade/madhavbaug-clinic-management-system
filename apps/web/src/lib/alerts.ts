/** Typed API calls for the alert review queue and safety rules. */

import { apiFetch } from "./api";
import type {
  Alert,
  AlertDetail,
  AlertPriority,
  AlertStatus,
  AlertSummary,
  Page,
  SafetyRule,
  SafetyRuleCreatePayload,
} from "./types";

export async function getAlertSummary(params?: { patient_id?: string }): Promise<AlertSummary> {
  const query = new URLSearchParams();
  if (params?.patient_id) query.set("patient_id", params.patient_id);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<AlertSummary>(`/alerts/summary${suffix}`);
}

export async function listAlerts(params?: {
  status?: AlertStatus;
  priority?: AlertPriority;
  patient_id?: string;
  assigned_to?: string;
  page?: number;
  size?: number;
}): Promise<Page<Alert>> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.priority) query.set("priority", params.priority);
  if (params?.patient_id) query.set("patient_id", params.patient_id);
  if (params?.assigned_to) query.set("assigned_to", params.assigned_to);
  if (params?.page) query.set("page", String(params.page));
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<Alert>>(`/alerts${suffix}`);
}

export async function getAlert(alertId: string): Promise<AlertDetail> {
  return apiFetch<AlertDetail>(`/alerts/${alertId}`);
}

export async function acknowledgeAlert(alertId: string, notes?: string): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${alertId}/acknowledge`, {
    method: "POST",
    body: { notes: notes ?? null },
  });
}

export async function escalateAlert(alertId: string, notes?: string): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${alertId}/escalate`, {
    method: "POST",
    body: { notes: notes ?? null },
  });
}

export async function resolveAlert(alertId: string, notes?: string): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${alertId}/resolve`, {
    method: "POST",
    body: { notes: notes ?? null },
  });
}

export async function dismissAlert(alertId: string, notes?: string): Promise<Alert> {
  return apiFetch<Alert>(`/alerts/${alertId}/dismiss`, {
    method: "POST",
    body: { notes: notes ?? null },
  });
}

export async function listSafetyRules(params?: { active_only?: boolean }): Promise<SafetyRule[]> {
  const query = new URLSearchParams();
  if (params?.active_only === false) query.set("active_only", "false");
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<SafetyRule[]>(`/safety-rules${suffix}`);
}

export async function createSafetyRule(payload: SafetyRuleCreatePayload): Promise<SafetyRule> {
  return apiFetch<SafetyRule>("/safety-rules", { method: "POST", body: payload });
}

export async function deactivateSafetyRule(ruleId: string): Promise<SafetyRule> {
  return apiFetch<SafetyRule>(`/safety-rules/${ruleId}/deactivate`, { method: "POST" });
}
