/** Typed API calls for WhatsApp messaging. */

import { apiFetch } from "./api";
import type { MessageException, Page, WhatsAppMessage } from "./types";

export async function listPatientMessages(
  patientId: string,
  params?: { page?: number; size?: number },
): Promise<Page<WhatsAppMessage>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<WhatsAppMessage>>(`/patients/${patientId}/messages${suffix}`);
}

export async function listMessages(params?: {
  direction?: string;
  delivery_status?: string;
  patient_id?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
  size?: number;
}): Promise<Page<WhatsAppMessage>> {
  const query = new URLSearchParams();
  if (params?.direction) query.set("direction", params.direction);
  if (params?.delivery_status) query.set("delivery_status", params.delivery_status);
  if (params?.patient_id) query.set("patient_id", params.patient_id);
  if (params?.date_from) query.set("date_from", params.date_from);
  if (params?.date_to) query.set("date_to", params.date_to);
  if (params?.search) query.set("search", params.search);
  if (params?.page) query.set("page", String(params.page));
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<WhatsAppMessage>>(`/messages${suffix}`);
}

export async function listExceptions(params?: {
  status?: string;
  page?: number;
  size?: number;
}): Promise<Page<MessageException>> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.page) query.set("page", String(params.page));
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<MessageException>>(`/messages/exceptions${suffix}`);
}

export async function resolveException(
  exceptionId: string,
  payload: { resolved: boolean; notes?: string | null },
): Promise<MessageException> {
  return apiFetch<MessageException>(`/messages/exceptions/${exceptionId}/resolve`, {
    method: "POST",
    body: payload,
  });
}

export async function dispatchMessages(): Promise<{
  sent: number;
  failed: number;
  held: number;
  scanned: number;
}> {
  return apiFetch<{ sent: number; failed: number; held: number; scanned: number }>(
    "/messages/dispatch",
    { method: "POST" },
  );
}
