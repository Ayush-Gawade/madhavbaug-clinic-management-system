/** Typed API calls for follow-up scheduling and message templates. */

import { apiFetch } from "./api";
import type {
  FollowUpInstance,
  FollowUpInstanceStatus,
  FollowUpSchedule,
  MessageTemplate,
  Page,
  RecurrenceRule,
  ScheduleStatus,
  TemplateCategory,
} from "./types";

export interface ScheduleCreatePayload {
  patient_id: string;
  follow_up_type: string;
  recurrence_rule: RecurrenceRule;
  scheduled_local_time?: string | null;
  timezone?: string;
  message_template_id?: string | null;
  response_deadline_hours?: number;
  status?: ScheduleStatus;
  active_from?: string | null;
  active_to?: string | null;
}

export async function createSchedule(payload: ScheduleCreatePayload): Promise<FollowUpSchedule> {
  return apiFetch<FollowUpSchedule>("/schedules", { method: "POST", body: payload });
}

export async function listSchedules(params?: {
  patientId?: string;
  status?: ScheduleStatus;
}): Promise<Page<FollowUpSchedule>> {
  const query = new URLSearchParams();
  if (params?.patientId) query.set("patient_id", params.patientId);
  if (params?.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<FollowUpSchedule>>(`/schedules${suffix}`);
}

export async function updateSchedule(
  scheduleId: string,
  payload: { status?: ScheduleStatus; response_deadline_hours?: number },
): Promise<FollowUpSchedule> {
  return apiFetch<FollowUpSchedule>(`/schedules/${scheduleId}`, {
    method: "PATCH",
    body: payload,
  });
}

export async function materializeSchedule(scheduleId: string): Promise<{ instances_created: number }> {
  return apiFetch<{ instances_created: number }>(`/schedules/${scheduleId}/materialize`, {
    method: "POST",
  });
}

export async function processDue(): Promise<{ eligible_to_send: number; skipped_consent: number }> {
  return apiFetch<{ eligible_to_send: number; skipped_consent: number }>("/schedules/process-due", {
    method: "POST",
  });
}

export interface NonResponseResult {
  instances_scanned: number;
  reminders_sent: number;
  reminders_failed: number;
  marked_overdue: number;
  escalations_created: number;
}

export async function processNonResponse(): Promise<NonResponseResult> {
  return apiFetch<NonResponseResult>("/schedules/process-non-response", { method: "POST" });
}

export async function acknowledgeInstance(
  instanceId: string,
  notes?: string,
): Promise<FollowUpInstance> {
  return apiFetch<FollowUpInstance>(`/instances/${instanceId}/acknowledge`, {
    method: "POST",
    body: { notes: notes ?? null },
  });
}

export async function resolveInstance(
  instanceId: string,
  notes?: string,
): Promise<FollowUpInstance> {
  return apiFetch<FollowUpInstance>(`/instances/${instanceId}/resolve`, {
    method: "POST",
    body: { notes: notes ?? null },
  });
}

export async function listInstances(params?: {
  status?: FollowUpInstanceStatus;
  patientId?: string;
  page?: number;
  size?: number;
}): Promise<Page<FollowUpInstance>> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.patientId) query.set("patient_id", params.patientId);
  if (params?.page) query.set("page", String(params.page));
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<FollowUpInstance>>(`/instances${suffix}`);
}

export async function getFollowUpDayCount(): Promise<{
  due_today: number;
  overdue: number;
  done_today: number;
}> {
  return apiFetch<{ due_today: number; overdue: number; done_today: number }>(
    "/follow-ups/day-count",
  );
}

export async function listTemplates(activeOnly = true): Promise<MessageTemplate[]> {
  return apiFetch<MessageTemplate[]>(`/messages/templates?active_only=${activeOnly}`);
}

export interface TemplateCreatePayload {
  code: string;
  name: string;
  category: TemplateCategory;
  language?: string;
  body: string;
  is_active?: boolean;
  approved?: boolean;
}

export async function createTemplate(payload: TemplateCreatePayload): Promise<MessageTemplate> {
  return apiFetch<MessageTemplate>("/messages/templates", { method: "POST", body: payload });
}

export interface TemplateUpdatePayload {
  body?: string;
  is_active?: boolean;
  approved?: boolean;
}

export async function updateTemplate(
  templateId: string,
  payload: TemplateUpdatePayload,
): Promise<MessageTemplate> {
  return apiFetch<MessageTemplate>(`/messages/templates/${templateId}`, {
    method: "PATCH",
    body: payload,
  });
}