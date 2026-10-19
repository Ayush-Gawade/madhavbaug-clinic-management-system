import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CalendarClock, FileText, MessageSquare, Users } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import { toast } from "@/components/Toast";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorNotice,
  Label,
  Loading,
  Modal,
  SelectInput,
  TextArea,
  TextInput,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { FOLLOW_UP_LABELS } from "@/lib/followUps";
import { listPatients } from "@/lib/patients";
import {
  createSchedule,
  createTemplate,
  listSchedules,
  listTemplates,
  materializeSchedule,
  updateSchedule,
  updateTemplate,
  type ScheduleCreatePayload,
} from "@/lib/schedules";
import type {
  FollowUpSchedule,
  FollowUpType,
  MessageTemplate,
  Patient,
  PatientCategoryType,
  RecurrenceRule,
  ScheduleStatus,
  TemplateCategory,
} from "@/lib/types";

const CATEGORY_LABELS: Record<PatientCategoryType, string> = {
  thyroid: "Thyroid",
  obesity: "Obesity",
  blood_pressure: "Blood pressure",
  diabetes: "Diabetes",
};

const TEMPLATE_CATEGORY_LABELS: Record<TemplateCategory, string> = {
  scheduled_check_in: "Scheduled check-in",
  reminder: "Reminder",
  acknowledgement: "Acknowledgement",
  clarification_request: "Clarification request",
  human_assistance: "Human assistance",
};

const WEEKDAY_OPTIONS = [
  { value: 1, label: "Mon" },
  { value: 2, label: "Tue" },
  { value: 3, label: "Wed" },
  { value: 4, label: "Thu" },
  { value: 5, label: "Fri" },
  { value: 6, label: "Sat" },
  { value: 7, label: "Sun" },
];

const STATUS_TONES: Record<ScheduleStatus, string> = {
  active: "green",
  paused: "amber",
  completed: "slate",
  archived: "slate",
};

const TIMEZONE_OPTIONS = ["Asia/Kolkata", "Asia/Kathmandu", "Asia/Dhaka", "Asia/Dubai", "Asia/Singapore", "UTC"];

function recurrenceSummary(rule: RecurrenceRule): string {
  if (rule.freq === "daily") {
    return rule.interval && rule.interval > 1 ? `Every ${rule.interval} days` : "Daily";
  }
  if (rule.freq === "weekly") {
    const labels = WEEKDAY_OPTIONS.filter((day) => rule.on_weekdays?.includes(day.value)).map(
      (day) => day.label,
    );
    return `Weekly · ${labels.join(", ")}`;
  }
  return `Monthly · day ${rule.day_of_month}`;
}

function truncate(text: string, max = 60): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function FormSection({
  step,
  title,
  description,
  icon,
  children,
  footer,
}: {
  step: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}): JSX.Element {
  return (
    <section className="border-b border-line px-5 py-5 last:border-0">
      <div className="mb-4 flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-600/10 text-brand-700 dark:bg-brand-400/15 dark:text-brand-300">
          {icon}
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{title}</h3>
            <span className="rounded-full bg-surface-sunken px-1.5 py-px text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Step {step}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-muted">{description}</p>
        </div>
      </div>
      {children}
      {footer}
    </section>
  );
}

function TemplateFormModal({
  initial,
  onClose,
}: {
  initial: MessageTemplate | null;
  onClose: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [code, setCode] = useState(initial?.code ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState<TemplateCategory>(
    initial?.category ?? "scheduled_check_in",
  );
  const [language, setLanguage] = useState(initial?.language ?? "en");
  const [body, setBody] = useState(initial?.body ?? "");
  const [active, setActive] = useState(initial?.is_active ?? true);
  const [approved, setApproved] = useState(initial?.approved ?? false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = initial !== null;
  const mutation = useMutation({
    mutationFn: async (): Promise<MessageTemplate> => {
      if (isEditing && initial) {
        return updateTemplate(initial.id, { body, is_active: active, approved });
      }
      return createTemplate({
        code,
        name,
        category,
        language,
        body,
        is_active: active,
        approved,
      });
    },
    onSuccess: () => {
      toast.success(isEditing ? "Template updated" : "Template created");
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
      onClose();
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Unable to save template.");
    },
  });

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <Modal open onClose={onClose} title={isEditing ? "Edit message template" : "New message template"}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {isEditing ? null : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="template-code">Code</Label>
                <TextInput
                  required
                  id="template-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="diet_check_in"
                />
              </div>
              <div>
                <Label htmlFor="template-name">Name</Label>
                <TextInput
                  required
                  id="template-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Daily diet check-in"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="template-category">Category</Label>
                <SelectInput
                  id="template-category"
                  value={category}
                  onChange={(event) => setCategory(event.target.value as TemplateCategory)}
                >
                  {Object.entries(TEMPLATE_CATEGORY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </SelectInput>
              </div>
              <div>
                <Label htmlFor="template-language">Language</Label>
                <SelectInput
                  id="template-language"
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                >
                  <option value="en">English</option>
                  <option value="mr">Marathi</option>
                  <option value="hi">Hindi</option>
                </SelectInput>
              </div>
            </div>
          </>
        )}
        <div>
          <Label htmlFor="template-body">Message body</Label>
          <TextArea
            required
            id="template-body"
            rows={4}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder="Keep it short. WhatsApp templates limit free-form sends to the 24h session window."
          />
        </div>
        <div className="flex flex-wrap items-center gap-5">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-secondary">
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
              className="h-4 w-4 rounded border-line-strong accent-brand-600"
            />
            Active
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-secondary">
            <input
              type="checkbox"
              checked={approved}
              onChange={(event) => setApproved(event.target.checked)}
              className="h-4 w-4 rounded border-line-strong accent-brand-600"
            />
            Approved for outbound use
          </label>
        </div>
        {error ? <ErrorNotice message={error} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending} loading={mutation.isPending}>
            {mutation.isPending ? "Saving…" : isEditing ? "Save changes" : "Create template"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function TemplateManager(): JSX.Element {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<MessageTemplate | null>(null);

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () => listTemplates(false),
  });

  const toggle = useMutation({
    mutationFn: (template: MessageTemplate) =>
      updateTemplate(template.id, { is_active: !template.is_active }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });

  return (
    <Card>
      <CardHeader
        title="Message templates"
        description="Templates must be approved before they can be used in schedules."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            New template
          </Button>
        }
      />

      {templates.isPending ? (
        <SkeletonTable rows={4} cols={6} />
      ) : templates.isError ? (
        <div className="p-4">
          <ErrorNotice message="Failed to load templates." />
        </div>
      ) : !templates.data || templates.data.length === 0 ? (
        <EmptyState message="No templates yet. Create and approve one so schedules can use it." />
      ) : (
        <Table minClassName="min-w-[760px]">
          <THead>
            <TH>Code</TH>
            <TH>Name</TH>
            <TH>Category</TH>
            <TH>Body</TH>
            <TH>Status</TH>
            <TH align="right">Actions</TH>
          </THead>
          <tbody>
            {templates.data.map((template) => (
              <TR key={template.id}>
                <TD className="font-mono text-xs text-ink-muted">{template.code}</TD>
                <TD className="font-medium text-ink">{template.name}</TD>
                <TD className="text-ink-secondary">{TEMPLATE_CATEGORY_LABELS[template.category]}</TD>
                <TD className="max-w-64 text-ink-secondary">{truncate(template.body)}</TD>
                <TD>
                  <div className="flex gap-1">
                    <Badge tone={template.approved ? "green" : "amber"} dot={template.approved}>
                      {template.approved ? "Approved" : "Unapproved"}
                    </Badge>
                    <Badge tone="slate">{template.is_active ? "Active" : "Inactive"}</Badge>
                  </div>
                </TD>
                <TD align="right">
                  <div className="flex justify-end gap-2">
                    <Button variant="secondary" size="sm" onClick={() => setEditing(template)}>
                      Edit
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => toggle.mutate(template)}
                      disabled={toggle.isPending}
                    >
                      {template.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </div>
                </TD>
              </TR>
            ))}
          </tbody>
        </Table>
      )}

      {createOpen ? <TemplateFormModal initial={null} onClose={() => setCreateOpen(false)} /> : null}
      {editing ? <TemplateFormModal initial={editing} onClose={() => setEditing(null)} /> : null}
    </Card>
  );
}

function ScheduleForm({ templates }: { templates: MessageTemplate[] | undefined }): JSX.Element {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [followUpType, setFollowUpType] = useState<FollowUpType>("meal_check_in");
  const [templateId, setTemplateId] = useState("");
  const [messageBody, setMessageBody] = useState("");
  const [freq, setFreq] = useState<"daily" | "weekly" | "monthly">("daily");
  const [interval, setInterval] = useState(1);
  const [weekdays, setWeekdays] = useState<number[]>([1]);
  const [dayOfMonth, setDayOfMonth] = useState(1);
  const [time, setTime] = useState("08:00");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [deadline, setDeadline] = useState(12);
  const [activeFrom, setActiveFrom] = useState("");
  const [activeTo, setActiveTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [createdNote, setCreatedNote] = useState<string | null>(null);

  const patients = useQuery({
    queryKey: ["scheduler-patients"],
    queryFn: () => listPatients({ size: 1000 }),
  });

  const filtered = useMemo(() => {
    const rows = patients.data?.items ?? [];
    const term = search.trim().toLowerCase();
    return rows.filter(
      (patient) =>
        patient.phone_number !== null &&
        (category === "" ||
          patient.categories.some((item) => item.category_type === category)) &&
        (term === "" ||
          patient.full_name.toLowerCase().includes(term) ||
          patient.internal_id.toLowerCase().includes(term)),
    );
  }, [patients.data, search, category]);

  const approvedTemplates = useMemo(
    () => (templates ?? []).filter((template) => template.approved && template.is_active),
    [templates],
  );

  const togglePatient = (patientId: string): void => {
    setSelected((current) =>
      current.includes(patientId)
        ? current.filter((id) => id !== patientId)
        : [...current, patientId],
    );
  };

  const buildRecurrence = (): RecurrenceRule => {
    if (freq === "weekly") {
      return { freq, on_weekdays: [...weekdays].sort((a, b) => a - b) };
    }
    if (freq === "monthly") {
      return { freq, day_of_month: dayOfMonth };
    }
    return { freq, interval };
  };

  const mutation = useMutation({
    mutationFn: async (): Promise<number> => {
      let created = 0;
      for (const patientId of selected) {
        const payload: ScheduleCreatePayload = {
          patient_id: patientId,
          follow_up_type: followUpType,
          recurrence_rule: buildRecurrence(),
          scheduled_local_time: time || null,
          timezone,
          message_template_id: templateId || null,
          message_body: templateId ? null : messageBody || null,
          response_deadline_hours: deadline,
          status: "active",
          active_from: activeFrom || null,
          active_to: activeTo || null,
        };
        await createSchedule(payload);
        created += 1;
      }
      return created;
    },
    onSuccess: (count: number) => {
      setSelected([]);
      setCreatedNote(`Created ${count} schedule${count === 1 ? "" : "s"}.`);
      toast.success(`Created ${count} schedule${count === 1 ? "" : "s"}.`);
      void queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Unable to create the schedule.");
    },
  });

  const toggleWeekday = (value: number): void => {
    setWeekdays((current) =>
      current.includes(value) ? current.filter((day) => day !== value) : [...current, value],
    );
  };

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    setCreatedNote(null);
    if (selected.length === 0) {
      setError("Select at least one patient to schedule.");
      return;
    }
    if (freq === "weekly" && weekdays.length === 0) {
      setError("Weekly schedules need at least one weekday.");
      return;
    }
    mutation.mutate();
  };

  return (
    <Card>
      <CardHeader
        title="Create schedule"
        description="Pick patients, choose a message, set the time and recurrence — e.g. a diet check-in every morning at 8 AM."
      />

      <form onSubmit={handleSubmit}>
        <FormSection
          step="1"
          title="Patients"
          description="Search or filter by category, then select who receives this check-in."
          icon={<Users className="h-4 w-4" />}
        >
          <div className="mb-2.5 flex flex-wrap items-center gap-3">
            <TextInput
              className="min-w-52 max-w-72"
              placeholder="Search by name or ID…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <SelectInput
              className="w-44"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All categories</option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectInput>
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={() => setSelected(filtered.map((patient) => patient.id))}
              disabled={filtered.length === 0}
            >
              Select all ({filtered.length})
            </Button>
            <Button variant="ghost" size="sm" type="button" onClick={() => setSelected([])}>
              Clear
            </Button>
          </div>

          {patients.isPending ? (
            <Loading />
          ) : patients.isError ? (
            <ErrorNotice message="Failed to load patients." />
          ) : (
            <div className="max-h-56 space-y-0.5 overflow-auto rounded-xl border border-line bg-surface-sunken/40 p-1.5">
              {filtered.length === 0 ? (
                <p className="px-2 py-3 text-center text-sm text-ink-muted">
                  No patients with a phone number match.
                </p>
              ) : (
                filtered.map((patient) => (
                  <label
                    key={patient.id}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 transition hover:bg-surface"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(patient.id)}
                      onChange={() => togglePatient(patient.id)}
                      aria-label={patient.full_name}
                      className="h-4 w-4 rounded border-line-strong accent-brand-600"
                    />
                    <span className="text-sm font-medium text-ink">{patient.full_name}</span>
                    <span className="ml-auto text-xs text-ink-muted">{patient.phone_number}</span>
                  </label>
                ))
              )}
            </div>
          )}
          <p className="mt-1.5 text-xs font-medium text-ink-muted">
            {selected.length} patient{selected.length === 1 ? "" : "s"} selected.
          </p>
        </FormSection>

        <FormSection
          step="2"
          title="Message"
          description="Choose the follow-up type and either an approved template or free-form text."
          icon={<MessageSquare className="h-4 w-4" />}
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div>
              <Label htmlFor="schedule-type">Follow-up type</Label>
              <SelectInput
                id="schedule-type"
                value={followUpType}
                onChange={(event) => setFollowUpType(event.target.value as FollowUpType)}
              >
                {Object.entries(FOLLOW_UP_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </SelectInput>
            </div>
            <div>
              <Label htmlFor="schedule-template">Message template (approved)</Label>
              <SelectInput
                id="schedule-template"
                value={templateId}
                onChange={(event) => setTemplateId(event.target.value)}
              >
                <option value="">No template (free-form text)</option>
                {approvedTemplates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.code} · {template.name}
                  </option>
                ))}
              </SelectInput>
              {approvedTemplates.length === 0 ? (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  No approved templates yet — free-form text will only deliver within the 24h
                  session window.
                </p>
              ) : null}
            </div>
            <div>
              <Label>Status</Label>
              <SelectInput value="active" disabled>
                <option value="active">Active</option>
              </SelectInput>
            </div>
          </div>

          {templateId === "" ? (
            <div className="mt-4">
              <Label htmlFor="schedule-body">Message text</Label>
              <TextArea
                id="schedule-body"
                rows={3}
                maxLength={4000}
                placeholder="Type the message to send (e.g. Please share your today's meal photo.)"
                value={messageBody}
                onChange={(event) => setMessageBody(event.target.value)}
              />
              <p className="mt-1 text-xs text-ink-muted">
                Free-form text is only delivered by WhatsApp inside the 24-hour session window;
                outside it an approved template is required.
              </p>
            </div>
          ) : null}
        </FormSection>

        <FormSection
          step="3"
          title="Schedule"
          description="Recurrence, send time, response deadline and active window."
          icon={<CalendarClock className="h-4 w-4" />}
        >
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <Label htmlFor="schedule-freq">Frequency</Label>
              <SelectInput
                id="schedule-freq"
                value={freq}
                onChange={(event) => setFreq(event.target.value as "daily" | "weekly" | "monthly")}
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </SelectInput>
            </div>

            {freq === "daily" ? (
              <div>
                <Label htmlFor="schedule-interval">Every (days)</Label>
                <TextInput
                  type="number"
                  id="schedule-interval"
                  min={1}
                  max={366}
                  value={interval}
                  onChange={(event) => setInterval(Number(event.target.value) || 1)}
                />
              </div>
            ) : null}

            {freq === "weekly" ? (
              <div className="col-span-3">
                <Label>Days of the week</Label>
                <div className="flex flex-wrap gap-2">
                  {WEEKDAY_OPTIONS.map((day) => (
                    <button
                      key={day.value}
                      type="button"
                      aria-pressed={weekdays.includes(day.value)}
                      onClick={() => toggleWeekday(day.value)}
                      className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset transition ${
                        weekdays.includes(day.value)
                          ? "bg-brand-600 text-white ring-brand-600"
                          : "bg-surface text-ink-secondary ring-line-strong hover:bg-surface-sunken"
                      }`}
                    >
                      {day.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {freq === "monthly" ? (
              <div>
                <Label htmlFor="schedule-day">Day of month</Label>
                <TextInput
                  type="number"
                  id="schedule-day"
                  min={1}
                  max={31}
                  value={dayOfMonth}
                  onChange={(event) => setDayOfMonth(Number(event.target.value) || 1)}
                />
              </div>
            ) : null}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <Label htmlFor="schedule-time">Send time</Label>
              <TextInput
                type="time"
                id="schedule-time"
                value={time}
                onChange={(event) => setTime(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="schedule-deadline">Response deadline (hours)</Label>
              <TextInput
                type="number"
                id="schedule-deadline"
                min={1}
                max={168}
                value={deadline}
                onChange={(event) => setDeadline(Number(event.target.value) || 12)}
              />
            </div>
            <div>
              <Label htmlFor="schedule-from">Active from</Label>
              <TextInput
                type="date"
                id="schedule-from"
                value={activeFrom}
                onChange={(event) => setActiveFrom(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="schedule-to">Active to</Label>
              <TextInput
                type="date"
                id="schedule-to"
                value={activeTo}
                onChange={(event) => setActiveTo(event.target.value)}
              />
            </div>
          </div>

          <div className="mt-4 max-w-xs">
            <Label htmlFor="schedule-timezone">Timezone</Label>
            <SelectInput
              id="schedule-timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
            >
              {TIMEZONE_OPTIONS.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </SelectInput>
          </div>
        </FormSection>

        <div className="space-y-3 border-t border-line bg-surface-sunken/40 px-5 py-4">
          {error ? <ErrorNotice message={error} /> : null}
          {createdNote ? (
            <p className="flex items-center gap-2 rounded-lg bg-brand-50 px-4 py-2.5 text-sm font-medium text-brand-800 ring-1 ring-inset ring-brand-200 dark:bg-brand-400/10 dark:text-brand-300 dark:ring-brand-400/25">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              {createdNote}
            </p>
          ) : null}
          {mutation.isError && !error ? (
            <ErrorNotice message="Failed to create the schedule(s)." />
          ) : null}

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-ink-muted">
              {selected.length} patient{selected.length === 1 ? "" : "s"} · {recurrenceSummary(buildRecurrence())} at{" "}
              {time || "—"}
            </p>
            <Button
              type="submit"
              disabled={mutation.isPending || patients.isPending}
              loading={mutation.isPending}
            >
              <FileText className="h-4 w-4" />
              {mutation.isPending ? "Creating…" : "Create schedule"}
            </Button>
          </div>
        </div>
      </form>
    </Card>
  );
}

function ScheduleList({
  templates,
}: {
  templates: MessageTemplate[] | undefined;
}): JSX.Element {
  const queryClient = useQueryClient();
  const schedules = useQuery({
    queryKey: ["schedules"],
    queryFn: () => listSchedules({}),
  });
  const patients = useQuery({
    queryKey: ["scheduler-patients"],
    queryFn: () => listPatients({ size: 1000 }),
  });

  const nameMap = useMemo(() => {
    return new Map((patients.data?.items ?? []).map((patient: Patient) => [patient.id, patient]));
  }, [patients.data]);
  const templateMap = useMemo(
    () => new Map((templates ?? []).map((template) => [template.id, template])),
    [templates],
  );

  const toggleStatus = useMutation({
    mutationFn: (schedule: FollowUpSchedule) =>
      updateSchedule(schedule.id, {
        status: schedule.status === "active" ? "paused" : "active",
      }),
    onSuccess: () => {
      toast.success("Schedule updated");
      void queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
  });

  const materialize = useMutation({
    mutationFn: (scheduleId: string) => materializeSchedule(scheduleId),
    onSuccess: () => {
      toast.success("Instances materialised");
      void queryClient.invalidateQueries({ queryKey: ["schedules"] });
    },
  });

  return (
    <Card>
      <CardHeader
        title="Active schedules"
        description="Pause, resume or materialise upcoming instances."
      />

      {schedules.isPending ? (
        <SkeletonTable rows={5} cols={8} />
      ) : schedules.isError ? (
        <div className="p-4">
          <ErrorNotice message="Failed to load schedules." />
        </div>
      ) : !schedules.data || schedules.data.items.length === 0 ? (
        <EmptyState message="No schedules yet. Create one above to start sending check-ins." />
      ) : (
        <Table minClassName="min-w-[900px]">
          <THead>
            <TH>Patient</TH>
            <TH>Type</TH>
            <TH>Recurrence</TH>
            <TH>Time</TH>
            <TH>Deadline</TH>
            <TH>Template</TH>
            <TH>Status</TH>
            <TH align="right">Actions</TH>
          </THead>
          <tbody>
            {schedules.data.items.map((schedule) => {
              const patient = nameMap.get(schedule.patient_id);
              const templateName = schedule.message_template_id
                ? templateMap.get(schedule.message_template_id)?.name ?? "—"
                : "Free-form";
              return (
                <TR key={schedule.id}>
                  <TD className="font-medium text-ink">
                    {patient?.full_name ?? schedule.patient_id.slice(0, 8)}
                  </TD>
                  <TD className="text-ink-secondary">{FOLLOW_UP_LABELS[schedule.follow_up_type]}</TD>
                  <TD className="text-ink-secondary">{recurrenceSummary(schedule.recurrence_rule)}</TD>
                  <TD className="tabular-nums text-ink-secondary">
                    {schedule.scheduled_local_time ?? "—"}
                  </TD>
                  <TD className="text-ink-secondary">{schedule.response_deadline_hours}h</TD>
                  <TD className="text-ink-secondary">{templateName}</TD>
                  <TD>
                    <Badge tone={STATUS_TONES[schedule.status]} dot>
                      {schedule.status}
                    </Badge>
                  </TD>
                  <TD align="right">
                    <div className="flex justify-end gap-2">
                      {schedule.status === "active" || schedule.status === "paused" ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={toggleStatus.isPending}
                          onClick={() => toggleStatus.mutate(schedule)}
                        >
                          {schedule.status === "active" ? "Pause" : "Resume"}
                        </Button>
                      ) : null}
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={materialize.isPending || schedule.status !== "active"}
                        onClick={() => materialize.mutate(schedule.id)}
                      >
                        Materialise
                      </Button>
                    </div>
                  </TD>
                </TR>
              );
            })}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

export function MessageSchedulerPage(): JSX.Element {
  const templates = useQuery({ queryKey: ["templates"], queryFn: () => listTemplates(false) });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Message scheduler"
        description="Schedule WhatsApp check-ins for patients or groups using approved templates."
      />

      <ScheduleForm templates={templates.data} />
      <TemplateManager />
      <ScheduleList templates={templates.data} />
    </div>
  );
}
