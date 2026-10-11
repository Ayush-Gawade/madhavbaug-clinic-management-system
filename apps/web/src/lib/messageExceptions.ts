/** Presentation helpers for the message-exception review queue. */

const REASON_LABELS: Record<string, string> = {
  unknown_sender: "Unknown sender",
  ambiguous_sender: "Ambiguous sender",
  no_matching_follow_up: "No matching follow-up",
  ambiguous_follow_up: "Ambiguous follow-up",
  unsupported_type: "Unsupported type",
  processing_error: "Processing error",
};

export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

export function statusTone(status: string): "amber" | "green" | "slate" {
  if (status === "open") return "amber";
  if (status === "resolved") return "green";
  return "slate";
}

export function detailSummary(details: Record<string, unknown> | null): string {
  if (!details) return "—";
  const phone = details.from_phone;
  if (typeof phone === "string" && phone) return phone;
  const candidates = details.candidate_patient_ids;
  if (Array.isArray(candidates)) {
    return `${candidates.length} candidate patient${candidates.length === 1 ? "" : "s"}`;
  }
  return Object.keys(details).join(", ") || "—";
}
