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
