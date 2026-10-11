/** Typed API calls for the patient clinical domain. */

import { apiFetch } from "./api";
import type {
  CarePlan,
  Consent,
  ConsentType,
  Observation,
  Page,
  Patient,
  PatientCategory,
  PatientCategoryType,
  PatientCreatePayload,
  PatientStatus,
  TimelineEvent,
} from "./types";

export interface PatientListParams {
  search?: string;
  category?: PatientCategoryType;
  status?: PatientStatus;
  page?: number;
  size?: number;
}

export async function listPatients(
  params: PatientListParams = {},
): Promise<Page<Patient>> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.category) query.set("category", params.category);
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  query.set("size", String(params.size ?? 20));
  return apiFetch<Page<Patient>>(`/patients?${query.toString()}`);
}

export async function getPatient(id: string): Promise<Patient> {
  return apiFetch<Patient>(`/patients/${id}`);
}

export async function createPatient(payload: PatientCreatePayload): Promise<Patient> {
  return apiFetch<Patient>("/patients", { method: "POST", body: payload });
}

export async function assignCategory(
  patientId: string,
  categoryType: PatientCategoryType,
): Promise<PatientCategory> {
  return apiFetch<PatientCategory>(`/patients/${patientId}/categories`, {
    method: "POST",
    body: { category_type: categoryType },
  });
}

export async function addObservation(
  patientId: string,
  payload: {
    observation_type: string;
    value: number | null;
    unit?: string | null;
    observed_at: string;
    measurement_context?: Record<string, unknown> | null;
  },
): Promise<Observation> {
  return apiFetch<Observation>(`/patients/${patientId}/observations`, {
    method: "POST",
    body: payload,
  });
}

export async function listObservations(
  patientId: string,
  page = 1,
  size = 20,
): Promise<Page<Observation>> {
  return apiFetch<Page<Observation>>(
    `/patients/${patientId}/observations?page=${page}&size=${size}`,
  );
}

export async function createCarePlan(
  patientId: string,
  payload: { content?: Record<string, unknown>; status?: "active" | "draft" },
): Promise<CarePlan> {
  return apiFetch<CarePlan>(`/patients/${patientId}/care-plans`, {
    method: "POST",
    body: payload,
  });
}

export async function listCarePlans(patientId: string): Promise<CarePlan[]> {
  return apiFetch<CarePlan[]>(`/patients/${patientId}/care-plans`);
}

export async function addConsent(
  patientId: string,
  payload: { consent_type: ConsentType; purpose: string },
): Promise<Consent> {
  return apiFetch<Consent>(`/patients/${patientId}/consents`, {
    method: "POST",
    body: payload,
  });
}

export async function listConsents(patientId: string): Promise<Consent[]> {
  return apiFetch<Consent[]>(`/patients/${patientId}/consents`);
}

export async function listTimeline(patientId: string): Promise<TimelineEvent[]> {
  return apiFetch<TimelineEvent[]>(`/patients/${patientId}/timeline`);
}