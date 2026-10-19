/** Typed API calls for the clinic's runtime settings screen. */

import { apiFetch } from "./api";
import type { AppSetting, SettingsResponse } from "./types";

export const AUTO_REPLY_ENABLED_KEY = "ai_autoreply_enabled";
export const DOCTOR_PHONE_KEY = "ai_autoreply_doctor_phone";

/** International E.164, mirroring the server-side validator. */
const E164 = /^\+[1-9]\d{7,14}$/;

export function isValidPhone(value: string): boolean {
  return E164.test(value.trim());
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
