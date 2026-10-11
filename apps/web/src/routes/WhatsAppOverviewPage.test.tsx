import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WhatsAppOverviewPage } from "./WhatsAppOverviewPage";
import type { MessagingOverview, Page, StaffUser } from "@/lib/types";

vi.mock("@/lib/analytics", () => ({
  getMessagingOverview: vi.fn(),
}));

vi.mock("@/lib/users", () => ({
  listUsers: vi.fn(),
}));

import { getMessagingOverview } from "@/lib/analytics";
import { listUsers } from "@/lib/users";

const overviewMock = vi.mocked(getMessagingOverview);
const usersMock = vi.mocked(listUsers);

const OVERVIEW: MessagingOverview = {
  date_from: "2026-10-11",
  date_to: "2026-10-11",
  patients_in_scope: 10,
  messages_sent: 5,
  replies_received: 3,
  non_responders: 2,
  delivery_failures: 1,
  critical_alerts: 1,
  pending_observation_reviews: 4,
  ai_needs_clarification: 1,
  open_message_exceptions: 2,
  recent_messages: [
    {
      id: "message-1",
      patient_id: "patient-1",
      patient_name: "Asha Patil",
      direction: "inbound",
      message_type: "text",
      text_body: "My sugar is 130",
      delivery_status: null,
      occurred_at: "2026-10-11T09:00:00Z",
    },
    {
      id: "message-2",
      patient_id: "patient-1",
      patient_name: "Asha Patil",
      direction: "outbound",
      message_type: "text",
      text_body: "Morning check-in",
      delivery_status: "failed",
      occurred_at: "2026-10-11T08:00:00Z",
    },
  ],
};

const DOCTOR: StaffUser = {
  id: "doctor-1",
  email: "doctor@example.com",
  full_name: "Dr. Girish",
  role: "doctor",
  is_active: true,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function pageOf<T>(items: T[]): Page<T> {
  return { items, total: items.length, page: 1, size: 20, pages: 1 };
}

function renderPage(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WhatsAppOverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WhatsAppOverviewPage", () => {
  beforeEach(() => {
    overviewMock.mockReset();
    usersMock.mockReset();
    overviewMock.mockResolvedValue(OVERVIEW);
    usersMock.mockResolvedValue(pageOf([DOCTOR]));
  });

  it("renders WhatsApp traffic stats, queues and recent messages", async () => {
    renderPage();

    expect(await screen.findByText("Messages sent")).toBeInTheDocument();
    expect(screen.getByText("Replies received")).toBeInTheDocument();
    expect(screen.getByText("Non-responders")).toBeInTheDocument();
    expect(screen.getByText("Delivery failures")).toBeInTheDocument();

    expect(screen.getByText("My sugar is 130")).toBeInTheDocument();
    expect(screen.getByText("Morning check-in")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("Message exceptions")).toBeInTheDocument();
  });

  it("refetches with the category filter when it changes", async () => {
    renderPage();

    await screen.findByText("Messages sent");
    fireEvent.change(screen.getByLabelText("Category"), {
      target: { value: "diabetes" },
    });

    await waitFor(() => {
      expect(overviewMock).toHaveBeenCalledWith(
        expect.objectContaining({ category: "diabetes" }),
      );
    });
  });

  it("exposes the doctor filter from the staff directory", async () => {
    renderPage();

    await screen.findByText("Messages sent");
    expect(screen.getByLabelText("Doctor")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Dr. Girish" })).toBeInTheDocument();
  });
});