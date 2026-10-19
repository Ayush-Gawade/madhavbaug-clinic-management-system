/** Typed API calls for the clinic's runtime settings screen. */

import { apiFetch } from "./api";
import type { AppSetting, SettingsResponse } from "./types";

export const AUTO_REPLY_ENABLED_KEY = "ai_autoreply_enabled";
export const DOCTOR_PHONE_KEY = "ai_autoreply_doctor_phone";
export const DOCTOR_TEMPLATE_KEY = "ai_autoreply_doctor_template";

/** International E.164, mirroring the server-side validator. */
const E164 = /^\+[1-9]\d{7,14}$/;

/** Meta's rule for template names; mirrors the server-side validator. */
const TEMPLATE_NAME = /^[a-z0-9_]{1,64}$/;

export function isValidPhone(value: string): boolean {
  return E164.test(value.trim());
}

/** Empty means "not configured", which is a valid answer. */
export function isValidTemplateName(value: string): boolean {
  const trimmed = value.trim();
  return trimmed === "" || TEMPLATE_NAME.test(trimmed);
}

export async function listSettings(): Promise<AppSetting[]> {
  const payload = await apiFetch<SettingsResponse>("/settings");
  return payload.settings;
}

export async function updateSetting(
  key: string,
  value: boolean | string,
): Promise<AppSetting> {
  return apiFetch<AppSetting>(`/settings/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: { value },
  });
}
