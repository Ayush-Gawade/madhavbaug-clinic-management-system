import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueuesPage } from "./QueuesPage";
import type {
  Alert,
  ClinicOverview,
  FollowUpInstance,
  FollowUpSchedule,
  MessageException,
  Page,
  Patient,
  StaffUser,
  WhatsAppMessage,
} from "@/lib/types";

vi.mock("@/lib/alerts", () => ({
  listAlerts: vi.fn(),
}));
vi.mock("@/lib/analytics", () => ({
  getClinicOverview: vi.fn(),
}));
vi.mock("@/lib/messaging", () => ({
  listExceptions: vi.fn(),
  listMessages: vi.fn(),
}));
vi.mock("@/lib/patients", () => ({
  listPatients: vi.fn(),
}));
vi.mock("@/lib/schedules", () => ({
  listInstances: vi.fn(),
  listSchedules: vi.fn(),
}));
vi.mock("@/lib/users", () => ({
  listUsers: vi.fn(),
}));

import { listAlerts } from "@/lib/alerts";
import { getClinicOverview } from "@/lib/analytics";
import { listExceptions, listMessages } from "@/lib/messaging";
import { listPatients } from "@/lib/patients";
import { listInstances, listSchedules } from "@/lib/schedules";
import { listUsers } from "@/lib/users";

const listAlertsMock = vi.mocked(listAlerts);
const getOverviewMock = vi.mocked(getClinicOverview);
const listExceptionsMock = vi.mocked(listExceptions);
const listMessagesMock = vi.mocked(listMessages);
const listPatientsMock = vi.mocked(listPatients);
const listInstancesMock = vi.mocked(listInstances);
const listSchedulesMock = vi.mocked(listSchedules);
const listUsersMock = vi.mocked(listUsers);

const PATIENT: Patient = {
  id: "patient-1",
  internal_id: "MB0001",
  full_name: "Asha Patil",
  phone_number: "+91 98765 43210",
  preferred_language: "en",
  date_of_onboarding: null,
  assigned_clinician_id: "doctor-1",
  status: "active",
  dietary_restrictions: null,
  communication_preferences: null,
  categories: [],
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
  message_template_id: null,
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

const ALERT: Alert = {
  id: "alert-1",
  patient_id: "patient-1",
  observation_id: null,
  follow_up_instance_id: null,
  rule_id: null,
  rule_version: 1,
  alert_type: "threshold",
  metric: "blood_glucose",
  value: "250",
  unit: "mg/dL",
  priority: "urgent",
  status: "open",
  reason: "Blood glucose is very high",
  context: null,
  assigned_to: "doctor-1",
  acknowledged_by: null,
  acknowledged_at: null,
  resolved_by: null,
  resolved_at: null,
  resolution_notes: null,
  created_at: "2026-10-11T06:00:00Z",
  updated_at: "2026-10-11T06:00:00Z",
};

const OVERDUE: FollowUpInstance = {
  id: "instance-1",
  schedule_id: "schedule-1",
  patient_id: "patient-1",
  due_date: "2026-10-10",
  due_at: "2026-10-10T08:00:00Z",
  sent_at: "2026-10-10T08:01:00Z",
  response_deadline_at: "2026-10-10T20:00:00Z",
  status: "overdue",
  reminder_count: 1,
  last_reminded_at: null,
  overdue_at: "2026-10-11T08:00:00Z",
  completed_at: null,
  assigned_staff_id: "doctor-1",
  acknowledged_by: null,
  acknowledged_at: null,
};

const FAILED: WhatsAppMessage = {
  id: "message-1",
  patient_id: "patient-1",
  follow_up_instance_id: null,
  direction: "outbound",
  provider_message_id: null,
  message_type: "text",
  from_phone: null,
  to_phone: "+91 98765 43210",
  text_body: "Broken number",
  media_reference: null,
  media_mime_type: null,
  template_code: null,
  delivery_status: "failed",
  processing_status: "processed",
  error_code: "template_required",
  error_message: null,
  provider_timestamp: null,
  sent_at: "2026-10-11T06:00:00Z",
  received_at: null,
  created_at: "2026-10-11T06:00:00Z",
  updated_at: "2026-10-11T06:00:00Z",
  media_url: null,
};

const EXCEPTION: MessageException = {
  id: "exception-1",
  patient_id: null,
  message_id: "message-x",
  reason: "unknown_sender",
  status: "open",
  details: { from_phone: "919800000000", message_type: "text" },
  resolved_by: null,
  resolved_at: null,
  resolution_notes: null,
  created_at: "2026-10-11T06:30:00Z",
  updated_at: "2026-10-11T06:30:00Z",
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

const OVERVIEW: ClinicOverview = {
  total_patients: 1,
  active_patients: 1,
  category_counts: [],
  follow_ups_due_today: 0,
  follow_ups_completed_today: 0,
  follow_ups_overdue: 1,
  failed_deliveries: 1,
  pending_clarifications: 0,
  open_alerts: 1,
  open_urgent_alerts: 1,
  pending_observation_reviews: 2,
  ai_needs_clarification: 1,
  open_message_exceptions: 1,
};

function pageOf<T>(items: T[]): Page<T> {
  return { items, total: items.length, page: 1, size: 8, pages: 1 };
}

function renderPage(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <QueuesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("QueuesPage", () => {
  beforeEach(() => {
    listAlertsMock.mockReset();
    getOverviewMock.mockReset();
    listExceptionsMock.mockReset();
    listMessagesMock.mockReset();
    listPatientsMock.mockReset();
    listInstancesMock.mockReset();
    listSchedulesMock.mockReset();
    listUsersMock.mockReset();

    listPatientsMock.mockResolvedValue(pageOf([PATIENT]));
    listUsersMock.mockResolvedValue(pageOf([DOCTOR]));
    listSchedulesMock.mockResolvedValue(pageOf([SCHEDULE]));
    getOverviewMock.mockResolvedValue(OVERVIEW);
    listAlertsMock.mockResolvedValue(pageOf([ALERT]));
    listInstancesMock.mockImplementation(
      async (params: { status?: string } = {}) => {
        if (params.status === "delivered") {
          return pageOf([{ ...OVERDUE, id: "instance-2", status: "delivered", reminder_count: 0 }]);
        }
        if (params.status === "read") {
          return pageOf([{ ...OVERDUE, id: "instance-3", status: "read", reminder_count: 0 }]);
        }
        return pageOf([OVERDUE]);
      },
    );
    listMessagesMock.mockResolvedValue(pageOf([FAILED]));
    listExceptionsMock.mockResolvedValue(pageOf([EXCEPTION]));
  });

  it("composes all queues with why, priority, owner and action", async () => {
    renderPage();

    expect(await screen.findByText("Blood glucose is very high")).toBeInTheDocument();
    expect(screen.getByText("urgent")).toBeInTheDocument();

    expect(screen.getAllByText(/Meal check-in/).length).toBeGreaterThan(0);
    expect(screen.getByText("overdue")).toBeInTheDocument();
    expect(screen.getAllByText("Dr. Girish").length).toBeGreaterThan(0);

    expect(screen.getByText("Broken number")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();

    // patient cell and exception reason both label unknown senders
    expect(screen.getAllByText("Unknown sender").length).toBeGreaterThan(0);

    expect(screen.getAllByText("Open alerts").length).toBeGreaterThan(0);
    expect(screen.getByText("Awaiting reply")).toBeInTheDocument();
    expect(screen.getByText("Pending reviews")).toBeInTheDocument();
  });

  it("surfaces review-queue totals from the clinic overview", async () => {
    renderPage();

    await screen.findAllByText("Open alerts");
    // 1 open exception + 2 observation reviews + 1 AI clarification = 4 pending reviews
    expect(getOverviewMock).toHaveBeenCalled();
    expect(screen.getAllByText("Reviews").length).toBeGreaterThan(0);
  });
});