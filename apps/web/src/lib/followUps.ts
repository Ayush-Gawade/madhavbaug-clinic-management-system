/** Presentation helpers for follow-up instances. */

import type { FollowUpType } from "./types";

export const FOLLOW_UP_LABELS: Record<FollowUpType, string> = {
  meal_check_in: "Meal check-in",
  weight: "Weight",
  blood_glucose: "Blood glucose",
  blood_pressure: "Blood pressure",
  observation: "Observation",
  treatment_adherence: "Treatment adherence",
};

export const INSTANCE_STATUS_TONES: Record<string, "slate" | "amber" | "green" | "red"> = {
  scheduled: "slate",
  queued: "slate",
  sent: "amber",
  delivered: "amber",
  read: "amber",
  responded: "green",
  failed: "red",
  overdue: "red",
  skipped: "slate",
};