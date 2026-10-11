/** Typed API calls for the financial module. */

import { apiFetch } from "./api";
import type {
  EstimateResult,
  FinanceSummary,
  PatientTreatmentAssignment,
  Payment,
  Treatment,
} from "./types";

export async function listTreatments(activeOnly = true): Promise<Treatment[]> {
  return apiFetch<Treatment[]>(`/treatments?active_only=${activeOnly}`);
}

export async function createTreatment(payload: Partial<Treatment>): Promise<Treatment> {
  return apiFetch<Treatment>("/treatments", { method: "POST", body: payload });
}

export async function estimateTreatment(
  treatmentId: string,
  discountPercent: number,
): Promise<EstimateResult> {
  return apiFetch<EstimateResult>("/estimator", {
    method: "POST",
    body: { treatment_id: treatmentId, discount_percent: discountPercent },
  });
}

export async function assignTreatment(
  patientId: string,
  payload: {
    treatment_id: string;
    discount_percent?: number | null;
    start_date?: string | null;
  },
): Promise<PatientTreatmentAssignment> {
  return apiFetch<PatientTreatmentAssignment>(`/patients/${patientId}/treatments`, {
    method: "POST",
    body: payload,
  });
}

export async function listAssignments(patientId: string): Promise<PatientTreatmentAssignment[]> {
  return apiFetch<PatientTreatmentAssignment[]>(`/patients/${patientId}/treatments`);
}

export async function recordPayment(
  patientId: string,
  payload: {
    treatment_id?: string | null;
    amount: number;
    payment_method?: string;
    reference?: string | null;
  },
): Promise<Payment> {
  return apiFetch<Payment>(`/patients/${patientId}/payments`, {
    method: "POST",
    body: payload,
  });
}

export async function listPayments(patientId: string): Promise<Payment[]> {
  return apiFetch<Payment[]>(`/patients/${patientId}/payments`);
}

export async function getFinanceSummary(patientId: string): Promise<FinanceSummary> {
  return apiFetch<FinanceSummary>(`/patients/${patientId}/finance`);
}