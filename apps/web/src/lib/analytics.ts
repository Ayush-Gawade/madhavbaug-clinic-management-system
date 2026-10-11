/** Typed API calls for analytics and reporting dashboards. */

import { apiFetch } from "./api";
import type {
  AdherenceSummary,
  ClinicOverview,
  DailyOperations,
  FinanceOverview,
  MessagingOverview,
  ObservationTrend,
  TrendGranularity,
} from "./types";

export async function getClinicOverview(): Promise<ClinicOverview> {
  return apiFetch<ClinicOverview>("/analytics/overview");
}

export async function getMessagingOverview(params?: {
  date_from?: string;
  date_to?: string;
  category?: string;
  doctor_id?: string;
  status?: string;
}): Promise<MessagingOverview> {
  const query = new URLSearchParams();
  if (params?.date_from) query.set("date_from", params.date_from);
  if (params?.date_to) query.set("date_to", params.date_to);
  if (params?.category) query.set("category", params.category);
  if (params?.doctor_id) query.set("doctor_id", params.doctor_id);
  if (params?.status) query.set("status", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<MessagingOverview>(`/analytics/messaging${suffix}`);
}

export async function getDailyOperations(): Promise<DailyOperations> {
  return apiFetch<DailyOperations>("/analytics/operations");
}

export async function getAdherence(params?: {
  date_from?: string;
  date_to?: string;
  patient_id?: string;
}): Promise<AdherenceSummary> {
  const query = new URLSearchParams();
  if (params?.date_from) query.set("date_from", params.date_from);
  if (params?.date_to) query.set("date_to", params.date_to);
  if (params?.patient_id) query.set("patient_id", params.patient_id);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<AdherenceSummary>(`/analytics/adherence${suffix}`);
}

export async function getObservationTrends(
  patientId: string,
  params: { observation_type: string; granularity?: TrendGranularity; date_from?: string; date_to?: string },
): Promise<ObservationTrend> {
  const query = new URLSearchParams();
  query.set("observation_type", params.observation_type);
  if (params.granularity) query.set("granularity", params.granularity);
  if (params.date_from) query.set("date_from", params.date_from);
  if (params.date_to) query.set("date_to", params.date_to);
  return apiFetch<ObservationTrend>(`/analytics/patients/${patientId}/trends?${query.toString()}`);
}

export async function getFinanceOverview(): Promise<FinanceOverview> {
  return apiFetch<FinanceOverview>("/analytics/finance");
}
