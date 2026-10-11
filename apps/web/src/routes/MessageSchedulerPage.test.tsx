import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MessageSchedulerPage } from "./MessageSchedulerPage";
import type {
  FollowUpSchedule,
  MessageTemplate,
  Page,
  Patient,
} from "@/lib/types";

vi.mock("@/lib/schedules", () => ({
  createSchedule: vi.fn(),
  createTemplate: vi.fn(),
  listSchedules: vi.fn(),
  listTemplates: vi.fn(),
  materializeSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  updateTemplate: vi.fn(),
}));

vi.mock("@/lib/patients", () => ({
  listPatients: vi.fn(),
}));

import {
  createSchedule,
  createTemplate,
  listSchedules,
  listTemplates,
} from "@/lib/schedules";
import { listPatients } from "@/lib/patients";

const createScheduleMock = vi.mocked(createSchedule);
const createTemplateMock = vi.mocked(createTemplate);
const listSchedulesMock = vi.mocked(listSchedules);
const listTemplatesMock = vi.mocked(listTemplates);
const listPatientsMock = vi.mocked(listPatients);

const PATIENT: Patient = {
  id: "patient-1",
  internal_id: "MB0001",
  full_name: "Asha Patil",
  phone_number: "+91 98765 43210",
  preferred_language: "en",
  date_of_onboarding: null,
  assigned_clinician_id: null,
  status: "active",
  dietary_restrictions: null,
  communication_preferences: null,
  categories: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const TEMPLATE: MessageTemplate = {
  id: "template-1",
  code: "diet_check_in",
  name: "Daily diet check-in",
  category: "scheduled_check_in",
  language: "en",
  body: "Namaskar {{1}}, please send your meal photo.",
  is_active: true,
  approved: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const SCHEDULE: FollowUpSchedule = {
  id: "schedule-1",
  patient_id: "patient-1",
  care_plan_id: null,
  follow_up_type: "meal_check_in",
  recurrence_rule: { freq: "daily", interval: 1 },
  scheduled_local_time: "08:00:00",
  timezone: "Asia/Kolkata",
  message_template_id: "template-1",
  response_deadline_hours: 12,
  reminder_policy: null,
  escalation_policy: null,
  status: "active",
  active_from: null,
  active_to: null,
  responsible_staff_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function pageOf<T>(items: T[]): Page<T> {
  return { items, total: items.length, page: 1, size: 20, pages: 1 };
}

function renderPage(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MessageSchedulerPage />
    </QueryClientProvider>,
  );
}

describe("MessageSchedulerPage", () => {
  beforeEach(() => {
    createScheduleMock.mockReset();
    createTemplateMock.mockReset();
    listSchedulesMock.mockReset();
    listTemplatesMock.mockReset();
    listPatientsMock.mockReset();
    listTemplatesMock.mockResolvedValue([TEMPLATE]);
    listPatientsMock.mockResolvedValue(pageOf([PATIENT]));
    listSchedulesMock.mockResolvedValue(pageOf([SCHEDULE]));
    createScheduleMock.mockResolvedValue(SCHEDULE);
    createTemplateMock.mockResolvedValue(TEMPLATE);
  });

  it("lists templates and active schedules", async () => {
    renderPage();

    expect(await screen.findByText("diet_check_in")).toBeInTheDocument();
    expect(screen.getByText("08:00:00")).toBeInTheDocument();
    expect(screen.getAllByText("Asha Patil").length).toBeGreaterThan(0);
  });

  it("creates a daily schedule for a selected patient with the approved template", async () => {
    renderPage();

    const checkbox = await screen.findByRole("checkbox", { name: "Asha Patil" });
    fireEvent.click(checkbox);

    fireEvent.change(screen.getByLabelText(/Message template/), {
      target: { value: TEMPLATE.id },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    await waitFor(() => {
      expect(createScheduleMock).toHaveBeenCalledTimes(1);
    });
    expect(createScheduleMock).toHaveBeenCalledWith({
      patient_id: PATIENT.id,
      follow_up_type: "meal_check_in",
      recurrence_rule: { freq: "daily", interval: 1 },
      scheduled_local_time: "08:00",
      timezone: "Asia/Kolkata",
      message_template_id: TEMPLATE.id,
      response_deadline_hours: 12,
      status: "active",
      active_from: null,
      active_to: null,
    });
  });

  it("requires at least one patient before creating a schedule", async () => {
    renderPage();

    await screen.findByRole("checkbox", { name: "Asha Patil" });
    fireEvent.click(screen.getByRole("button", { name: "Create schedule" }));

    expect(await screen.findByText("Select at least one patient to schedule.")).toBeInTheDocument();
    expect(createScheduleMock).not.toHaveBeenCalled();
  });

  it("creates a message template from the management modal", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "New template" }));

    fireEvent.change(await screen.findByLabelText("Code"), {
      target: { value: "bp_check" },
    });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "BP check" } });
    fireEvent.change(screen.getByLabelText(/Message body/), {
      target: { value: "Please send your BP reading." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create template" }));

    await waitFor(() => {
      expect(createTemplateMock).toHaveBeenCalledTimes(1);
    });
    expect(createTemplateMock).toHaveBeenCalledWith({
      code: "bp_check",
      name: "BP check",
      category: "scheduled_check_in",
      language: "en",
      body: "Please send your BP reading.",
      is_active: true,
      approved: false,
    });
  });
});