import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";
import type { AppSetting } from "@/lib/types";

vi.mock("@/lib/settings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/settings")>();
  return { ...actual, listSettings: vi.fn(), updateSetting: vi.fn() };
});

import { listSettings, updateSetting } from "@/lib/settings";

const listMock = vi.mocked(listSettings);
const updateMock = vi.mocked(updateSetting);

const SETTINGS: AppSetting[] = [
  {
    key: "ai_autoreply_enabled",
    value: false,
    default: false,
    description: "Let the assistant reply to patient WhatsApp messages automatically.",
    type: "boolean",
    updated_by: null,
    updated_at: null,
  },
  {
    key: "ai_autoreply_doctor_phone",
    value: "+919359883349",
    default: "+919359883349",
    description: "Doctor's WhatsApp number notified when a critical reading arrives.",
    type: "string",
    updated_by: null,
    updated_at: null,
  },
];

function renderPage(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    updateMock.mockReset();
    listMock.mockResolvedValue(SETTINGS);
    updateMock.mockImplementation(async (key, value) => ({
      ...(SETTINGS[0].key === key ? SETTINGS[0] : SETTINGS[1]),
      key,
      value,
    }));
  });

  it("loads the current values and saves both settings", async () => {
    renderPage();

    const toggle = await screen.findByRole("switch");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getByLabelText("Doctor notified on urgent readings")).toHaveValue(
      "+919359883349",
    );

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "true");

    fireEvent.change(screen.getByLabelText("Doctor notified on urgent readings"), {
      target: { value: "+911234567890" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateMock).toHaveBeenCalledTimes(2);
    });
    expect(updateMock).toHaveBeenNthCalledWith(1, "ai_autoreply_enabled", true);
    expect(updateMock).toHaveBeenNthCalledWith(2, "ai_autoreply_doctor_phone", "+911234567890");
  });

  it("rejects a malformed doctor number before calling the API", async () => {
    renderPage();

    fireEvent.change(await screen.findByLabelText("Doctor notified on urgent readings"), {
      target: { value: "9359883349" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(
      await screen.findByText(/Enter the doctor's number in international format/),
    ).toBeInTheDocument();
    expect(updateMock).not.toHaveBeenCalled();
  });

  it("surfaces a load failure", async () => {
    listMock.mockRejectedValueOnce(new Error("offline"));
    renderPage();

    expect(await screen.findByText("Failed to load settings.")).toBeInTheDocument();
  });
});
