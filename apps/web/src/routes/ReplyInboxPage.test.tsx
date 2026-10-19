import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReplyInboxPage } from "./ReplyInboxPage";
import { ApiError } from "@/lib/api";
import type { InboxThread, MessageTemplate, Page, WhatsAppMessage } from "@/lib/types";

vi.mock("@/lib/messaging", () => ({
  listInboxThreads: vi.fn(),
  listPatientMessages: vi.fn(),
  sendReply: vi.fn(),
}));
vi.mock("@/lib/schedules", () => ({
  listTemplates: vi.fn(),
}));

import { listInboxThreads, listPatientMessages, sendReply } from "@/lib/messaging";
import { listTemplates } from "@/lib/schedules";

const listInboxThreadsMock = vi.mocked(listInboxThreads);
const listThreadMock = vi.mocked(listPatientMessages);
const sendReplyMock = vi.mocked(sendReply);
const listTemplatesMock = vi.mocked(listTemplates);

const THREAD: InboxThread = {
  patient_id: "patient-1",
  patient_name: "Asha Patil",
  latest_message_id: "m1",
  latest_direction: "inbound",
  latest_text_body: "Is fasting sugar fine?",
  latest_media_mime_type: null,
  latest_at: "2026-10-12T06:00:00Z",
  inbound_count: 2,
};

function makeMessage(overrides: Partial<WhatsAppMessage>): WhatsAppMessage {
  return {
    id: "m1",
    patient_id: "patient-1",
    follow_up_instance_id: null,
    direction: "inbound",
    provider_message_id: null,
    message_type: "text",
    from_phone: "+91 98765 43210",
    to_phone: null,
    text_body: "Is fasting sugar fine?",
    media_reference: null,
    media_mime_type: null,
    template_code: null,
    delivery_status: null,
    processing_status: "processed",
    error_code: null,
    error_message: null,
    provider_timestamp: null,
    sent_at: null,
    received_at: "2026-10-12T06:00:00Z",
    created_at: "2026-10-12T06:00:00Z",
    updated_at: "2026-10-12T06:00:00Z",
    media_url: null,
    ...overrides,
  };
}

const INBOUND = makeMessage({ id: "m1", direction: "inbound", text_body: "Is fasting sugar fine?" });
const OUTBOUND = makeMessage({
  id: "m2",
  direction: "outbound",
  text_body: "Fasting sugar of 95 is fine, keep it up.",
});

const APPROVED_TEMPLATE: MessageTemplate = {
  id: "template-1",
  code: "CK-DAILY",
  name: "daily_check_in",
  category: "scheduled_check_in",
  language: "en",
  body: "Hi {{name}}, time to check in.",
  is_active: true,
  approved: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function pageOf<T>(items: T[]): Page<T> {
  return { items, total: items.length, page: 1, size: 100, pages: 1 };
}

function renderPage(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ReplyInboxPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReplyInboxPage", () => {
  beforeEach(() => {
    listInboxThreadsMock.mockReset();
    listThreadMock.mockReset();
    sendReplyMock.mockReset();
    listTemplatesMock.mockReset();

    listInboxThreadsMock.mockResolvedValue(pageOf([THREAD]));
    listThreadMock.mockResolvedValue(pageOf([INBOUND, OUTBOUND]));
    listTemplatesMock.mockResolvedValue([APPROVED_TEMPLATE]);
  });

  it("lists one row per patient with the reply count", async () => {
    renderPage();

    expect(await screen.findByText("Is fasting sugar fine?")).toBeInTheDocument();
    expect(screen.getByText("Asha Patil")).toBeInTheDocument();
    expect(screen.getByText(/2\s+messages/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Reply" }).length).toBeGreaterThan(0);
  });

  it("opens the conversation and sends a free-form reply", async () => {
    sendReplyMock.mockResolvedValue(
      makeMessage({ id: "m3", direction: "outbound", text_body: "Please log it tomorrow." }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Reply" }));

    expect(await screen.findByText("Reply — Asha Patil")).toBeInTheDocument();
    // Thread-only message (not present in the inbox list).
    expect(
      await screen.findByText("Fasting sugar of 95 is fine, keep it up."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Please log it tomorrow." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send reply" }));

    await waitFor(() => {
      expect(sendReplyMock).toHaveBeenCalledWith({
        patient_id: "patient-1",
        body: "Please log it tomorrow.",
      });
    });
  });

  it("prompts for an approved template when a reply is blocked outside the window", async () => {
    sendReplyMock.mockRejectedValue(
      new ApiError(
        422,
        "session_window_required",
        "Outside the 24-hour session window Meta does not allow free-form messages.",
      ),
    );
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Reply" }));
    await screen.findByText("Reply — Asha Patil");

    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Still outside." } });
    fireEvent.click(screen.getByRole("button", { name: "Send reply" }));

    expect(
      await screen.findByText(/send an approved template instead/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Approved template/)).toBeInTheDocument();
  });
});