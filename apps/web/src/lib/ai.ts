/** Typed API calls for AI extraction provenance and review. */

import { apiFetch } from "./api";
import type { AIExtraction, Page } from "./types";

export async function listPatientExtractions(
  patientId: string,
  params?: { page?: number; size?: number },
): Promise<Page<AIExtraction>> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<AIExtraction>>(`/patients/${patientId}/ai-extractions${suffix}`);
}

export async function getExtraction(extractionId: string): Promise<AIExtraction> {
  return apiFetch<AIExtraction>(`/ai-extractions/${extractionId}`);
}

export async function analyzeMessage(messageId: string): Promise<AIExtraction> {
  return apiFetch<AIExtraction>(`/messages/${messageId}/analyze`, { method: "POST" });
}
