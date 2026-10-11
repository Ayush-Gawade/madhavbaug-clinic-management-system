/** Typed API calls for staff user administration. */

import { apiFetch } from "./api";
import type { Page, StaffUser } from "./types";

export async function listUsers(params?: { size?: number }): Promise<Page<StaffUser>> {
  const query = new URLSearchParams();
  if (params?.size) query.set("size", String(params.size));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiFetch<Page<StaffUser>>(`/users${suffix}`);
}