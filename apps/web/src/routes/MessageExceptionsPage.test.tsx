import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MessageExceptionsPage } from "./MessageExceptionsPage";
import { detailSummary, reasonLabel, statusTone } from "@/lib/messageExceptions";
import type { Page } from "@/lib/types";
import type { MessageException } from "@/lib/types";

vi.mock("@/lib/messaging", () => ({
  listExceptions: vi.fn(),
  resolveException: vi.fn(),
}));

import { listExceptions, resolveException } from "@/lib/messaging";

const listMock = vi.mocked(listExceptions);
const resolveMock = vi.mocked(resolveException);

const EXCEPTION: MessageException = {
  id: "11111111-1111-1111-1111-111111111111",
  patient_id: null,
  message_id: "22222222-2222-2222-2222-222222222222",
  reason: "unknown_sender",
  status: "open",
  details: { from_phone: "919800000000", message_type: "text" },
  resolved_by: null,
  resolved_at: null,
  resolution_notes: null,
  created_at: "2026-01-02T03:04:05Z",
  updated_at: "2026-01-02T03:04:05Z",
};

function pageOf(items: MessageException[]): Page<MessageException> {
  return { items, total: items.length, page: 1, size: 20, pages: 1 };
}

function renderPage(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MessageExceptionsPage />
    </QueryClientProvider>,
  );
}

describe("message exception helpers", () => {
  it("labels known reasons and falls back to the raw value", () => {
    expect(reasonLabel("unknown_sender")).toBe("Unknown sender");
    expect(reasonLabel("ambiguous_sender")).toBe("Ambiguous sender");
    expect(reasonLabel("something_new")).toBe("something_new");
  });

  it("maps statuses to tones", () => {
    expect(statusTone("open")).toBe("amber");
    expect(statusTone("resolved")).toBe("green");
    expect(statusTone("dismissed")).toBe("slate");
  });

  it("summarises details", () => {
    expect(detailSummary(null)).toBe("—");
    expect(detailSummary({ from_phone: "919800000000" })).toBe("919800000000");
    expect(detailSummary({ candidate_patient_ids: ["a", "b"] })).toBe("2 candidate patients");
    expect(detailSummary({ candidate_patient_ids: ["a"] })).toBe("1 candidate patient");
  });
});

describe("MessageExceptionsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    resolveMock.mockReset();
    listMock.mockResolvedValue(pageOf([EXCEPTION]));
    resolveMock.mockResolvedValue({ ...EXCEPTION, status: "resolved" });
  });

  it("lists exceptions and resolves one from the review modal", async () => {
    renderPage();

    expect(await screen.findByText("Unknown sender")).toBeInTheDocument();
    expect(screen.getByText("919800000000")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    const notes = await screen.findByLabelText("Notes");
    fireEvent.change(notes, { target: { value: "Matched to a new patient" } });
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => {
      expect(resolveMock).toHaveBeenCalledWith(EXCEPTION.id, {
        resolved: true,
        notes: "Matched to a new patient",
      });
    });
  });

  it("shows an empty state when there are no exceptions", async () => {
    listMock.mockResolvedValue(pageOf([]));
    renderPage();
    expect(await screen.findByText("No message exceptions for this filter.")).toBeInTheDocument();
  });
});
