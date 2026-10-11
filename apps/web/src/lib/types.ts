/** Shared API types mirroring backend schemas. */

export type StaffRole = "owner" | "doctor" | "dietitian" | "reception" | "finance";

export interface StaffUser {
  id: string;
  email: string;
  full_name: string;
  role: StaffRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export type PatientStatus = "active" | "inactive" | "archived";
export type PatientCategoryType = "thyroid" | "obesity" | "blood_pressure" | "diabetes";
export type ConsentType = "communication" | "health_data";
export type ConsentStatus = "active" | "withdrawn";
export type CarePlanStatus = "draft" | "active" | "archived";
export type ObservationSource = "patient_report" | "staff_entry" | "whatsapp";
export type TimelineEventType = "observation" | "care_plan" | "category" | "consent";

export interface PatientCategory {
  id: string;
  category_type: PatientCategoryType;
  effective_from: string | null;
  effective_to: string | null;
  assigned_by: string | null;
}

export interface Patient {
  id: string;
  internal_id: string;
  full_name: string;
  phone_number: string | null;
  preferred_language: string;
  date_of_onboarding: string | null;
  assigned_clinician_id: string | null;
  status: PatientStatus;
  dietary_restrictions: Record<string, unknown> | null;
  communication_preferences: Record<string, unknown> | null;
  categories: PatientCategory[];
  created_at: string;
  updated_at: string;
}

export interface PatientCreatePayload {
  full_name: string;
  phone_number?: string | null;
  preferred_language?: string;
  date_of_onboarding?: string | null;
  status?: PatientStatus;
  categories?: PatientCategoryType[];
}

export interface Consent {
  id: string;
  consent_type: ConsentType;
  purpose: string;
  status: ConsentStatus;
  captured_at: string;
  withdrawn_at: string | null;
  evidence_reference: string | null;
  recorded_by: string | null;
}

export interface Observation {
  id: string;
  observation_type: string;
  value: string | number | null;
  unit: string | null;
  observed_at: string;
  reported_at: string;
  source: ObservationSource;
  measurement_context: Record<string, unknown> | null;
  validation_status: string;
  review_status: string;
  recorded_by: string | null;
  ai_extraction_id: string | null;
}

export interface CarePlan {
  id: string;
  version: number;
  status: CarePlanStatus;
  effective_from: string | null;
  effective_to: string | null;
  approved_by: string | null;
  approval_timestamp: string | null;
  plan_reference: string | null;
  content: Record<string, unknown> | null;
  created_at: string;
}

export interface TimelineEvent {
  event_type: TimelineEventType;
  entity_id: string;
  occurred_at: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface Treatment {
  id: string;
  name: string;
  treatment_code: string;
  description: string | null;
  service_category: string | null;
  list_price: string;
  estimated_sessions: number | null;
  royalty_percent: string;
  therapist_cost: string;
  material_cost: string;
  other_direct_cost: string;
  overhead_allocation: string;
  cost_effective_from: string | null;
  is_active: boolean;
}

export interface EstimateResult {
  treatment_id: string;
  name: string;
  treatment_code: string;
  list_price: string;
  discount_percent: string;
  estimated_revenue: string;
  royalty: string;
  therapist_cost: string;
  material_cost: string;
  other_direct_cost: string;
  overhead_allocation: string;
  total_direct_cost: string;
  contribution: string;
  contribution_margin_percent: string;
  allocated_net_profit: string;
  min_contribution_margin: string;
  max_allowable_discount_percent: string;
  official_max_discount_percent: string;
  violates_boundary: boolean;
  warnings: string[];
}

export interface Payment {
  id: string;
  treatment_id: string | null;
  payment_type: string;
  amount: string;
  payment_date: string;
  payment_method: string;
  reference: string | null;
  notes: string | null;
  recorded_by: string | null;
}

export interface PatientTreatmentAssignment {
  id: string;
  treatment_id: string;
  status: string;
  discount_percent: string | null;
  start_date: string | null;
  end_date: string | null;
  assigned_by: string | null;
  treatment: Treatment | null;
}

export interface FinanceLine {
  treatment_id: string;
  name: string;
  list_price: string;
  discount_percent: string | null;
  charge: string;
}

export interface FinanceSummary {
  total_charges: string;
  total_paid: string;
  outstanding: string;
  lines: FinanceLine[];
  recent_payments: Payment[];
}

export type FollowUpType =
  | "meal_check_in"
  | "weight"
  | "blood_glucose"
  | "blood_pressure"
  | "observation"
  | "treatment_adherence";

export type ScheduleStatus = "active" | "paused" | "completed" | "archived";

export type FollowUpInstanceStatus =
  | "scheduled"
  | "queued"
  | "sent"
  | "delivered"
  | "read"
  | "failed"
  | "responded"
  | "overdue"
  | "skipped";

export type TemplateCategory =
  | "scheduled_check_in"
  | "reminder"
  | "acknowledgement"
  | "clarification_request"
  | "human_assistance";

export interface RecurrenceRule {
  freq: "daily" | "weekly" | "monthly";
  interval?: number;
  on_weekdays?: number[];
  day_of_month?: number;
}

export interface FollowUpSchedule {
  id: string;
  patient_id: string;
  care_plan_id: string | null;
  follow_up_type: FollowUpType;
  recurrence_rule: RecurrenceRule;
  scheduled_local_time: string | null;
  timezone: string;
  message_template_id: string | null;
  response_deadline_hours: number;
  reminder_policy: Record<string, unknown> | null;
  escalation_policy: Record<string, unknown> | null;
  status: ScheduleStatus;
  active_from: string | null;
  active_to: string | null;
  responsible_staff_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface FollowUpInstance {
  id: string;
  schedule_id: string;
  patient_id: string;
  due_date: string;
  due_at: string;
  sent_at: string | null;
  response_deadline_at: string | null;
  status: FollowUpInstanceStatus;
  reminder_count: number;
  last_reminded_at: string | null;
  overdue_at: string | null;
  completed_at: string | null;
  assigned_staff_id: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface MessageTemplate {
  id: string;
  code: string;
  name: string;
  category: TemplateCategory;
  language: string;
  body: string;
  is_active: boolean;
  approved: boolean;
  created_at: string;
  updated_at: string;
}

export interface FollowUpDayCount {
  due_today: number;
  overdue: number;
  done_today: number;
}

export type MessageDirection = "inbound" | "outbound";

export type MessageType =
  | "text"
  | "image"
  | "document"
  | "audio"
  | "video"
  | "template"
  | "interactive"
  | "unsupported";

export type DeliveryStatus = "pending" | "sent" | "delivered" | "read" | "failed";

export type MessageProcessingStatus =
  | "received"
  | "queued"
  | "processing"
  | "processed"
  | "needs_clarification"
  | "unassigned"
  | "failed";

export type ExceptionReason =
  | "unknown_sender"
  | "ambiguous_sender"
  | "no_matching_follow_up"
  | "ambiguous_follow_up"
  | "unsupported_type"
  | "processing_error";

export type ExceptionStatus = "open" | "resolved" | "dismissed";

export interface WhatsAppMessage {
  id: string;
  patient_id: string | null;
  follow_up_instance_id: string | null;
  direction: MessageDirection;
  provider_message_id: string | null;
  message_type: MessageType;
  from_phone: string | null;
  to_phone: string | null;
  text_body: string | null;
  media_reference: string | null;
  media_mime_type: string | null;
  template_code: string | null;
  delivery_status: DeliveryStatus | null;
  processing_status: string;
  error_code: string | null;
  error_message: string | null;
  provider_timestamp: string | null;
  sent_at: string | null;
  received_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageException {
  id: string;
  patient_id: string | null;
  message_id: string | null;
  reason: string;
  status: string;
  details: Record<string, unknown> | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  created_at: string;
  updated_at: string;
}

export type RuleMetric = "blood_glucose" | "weight" | "systolic" | "diastolic";
export type RuleComparator = "gt" | "gte" | "lt" | "lte";
export type AlertPriority = "routine" | "priority" | "urgent";
export type AlertStatus = "open" | "acknowledged" | "resolved" | "dismissed";
export type AlertType =
  | "threshold"
  | "non_response"
  | "delivery_failure"
  | "clarification"
  | "manual";
export type ClinicianActionType =
  | "acknowledge"
  | "assign"
  | "escalate"
  | "resolve"
  | "dismiss"
  | "comment";

export interface SafetyRule {
  id: string;
  rule_key: string;
  version: number;
  metric: RuleMetric;
  comparator: RuleComparator;
  threshold: string;
  unit: string;
  priority: AlertPriority;
  context: Record<string, unknown> | null;
  description: string | null;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SafetyRuleCreatePayload {
  rule_key: string;
  metric: RuleMetric;
  comparator: RuleComparator;
  threshold: string | number;
  unit: string;
  priority: AlertPriority;
  description?: string | null;
  context?: Record<string, unknown> | null;
}

export interface Alert {
  id: string;
  patient_id: string;
  observation_id: string | null;
  follow_up_instance_id: string | null;
  rule_id: string | null;
  rule_version: number | null;
  alert_type: AlertType;
  metric: string | null;
  value: string | null;
  unit: string | null;
  priority: AlertPriority;
  status: AlertStatus;
  reason: string;
  context: Record<string, unknown> | null;
  assigned_to: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClinicianAction {
  id: string;
  alert_id: string;
  patient_id: string | null;
  action_type: ClinicianActionType;
  actor_id: string | null;
  from_status: string | null;
  to_status: string | null;
  notes: string | null;
  occurred_at: string;
}

export interface AlertDetail extends Alert {
  actions: ClinicianAction[];
}

export interface AlertSummary {
  open: number;
  acknowledged: number;
  resolved: number;
  dismissed: number;
  open_total: number;
  open_urgent: number;
  open_priority: number;
  open_routine: number;
}

export type AIExtractionModality = "text" | "vision";
export type AIExtractionStatus = "succeeded" | "needs_clarification" | "skipped" | "failed";

export interface AIExtraction {
  id: string;
  patient_id: string | null;
  message_id: string | null;
  modality: AIExtractionModality;
  model: string;
  prompt_version: string;
  status: AIExtractionStatus;
  intent: string | null;
  confidence: string | null;
  needs_clarification: boolean;
  clarification_question: string | null;
  extracted: Record<string, unknown> | null;
  raw_response: Record<string, unknown> | null;
  error_message: string | null;
  observations_created: number;
  created_at: string;
}

export interface CategoryCount {
  category_type: PatientCategoryType;
  count: number;
}

export interface ClinicOverview {
  total_patients: number;
  active_patients: number;
  category_counts: CategoryCount[];
  follow_ups_due_today: number;
  follow_ups_completed_today: number;
  follow_ups_overdue: number;
  failed_deliveries: number;
  pending_clarifications: number;
  open_alerts: number;
  open_urgent_alerts: number;
  pending_observation_reviews: number;
  ai_needs_clarification: number;
  open_message_exceptions: number;
}

export interface DailyActionItem {
  patient_id: string;
  patient_name: string;
  reasons: string[];
  priority: AlertPriority;
  latest_activity: string;
}

export interface DailyOperations {
  generated_at: string;
  total: number;
  items: DailyActionItem[];
}

export interface AdherenceSummary {
  date_from: string;
  date_to: string;
  scheduled_total: number;
  completed: number;
  overdue: number;
  skipped: number;
  failed_deliveries: number;
  awaiting_response: number;
  completion_rate_percent: string;
  rate_definition: string;
}

export type TrendGranularity = "day" | "week" | "month";

export interface TrendPoint {
  bucket: string;
  average_value: string;
  latest_value: string | null;
  count: number;
  verified_count: number;
  patient_reported_count: number;
}

export interface ObservationTrend {
  patient_id: string;
  observation_type: string;
  unit: string | null;
  granularity: TrendGranularity;
  date_from: string;
  date_to: string;
  points: TrendPoint[];
  missing_buckets: number;
}

export interface FinanceTreatmentLine {
  treatment_id: string;
  name: string;
  assignments: number;
  billed: string;
  estimated_direct_costs: string;
  estimated_contribution: string;
}

export interface FinanceOverview {
  total_charges: string;
  recorded_revenue: string;
  recorded_refunds: string;
  net_recorded_revenue: string;
  outstanding: string;
  estimated_direct_costs: string;
  estimated_contribution: string;
  estimated_contribution_margin_percent: string;
  lines: FinanceTreatmentLine[];
  notes: string[];
}
