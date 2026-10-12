import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import {
  Badge,
  Button,
  Card,
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
          <textarea
            required
            id="template-body"
            rows={4}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none"
            placeholder="Keep it short. WhatsApp templates limit free-form sends to the 24h session window."
          />
        </div>
        <div className="flex flex-wrap items-center gap-5">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            Active
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={approved}
              onChange={(event) => setApproved(event.target.checked)}
              className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            Approved for outbound use
          </label>
        </div>
        {error ? <ErrorNotice message={error} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
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
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">Message templates</h2>
          <p className="text-xs text-slate-500">
            Templates must be approved before they can be used in schedules.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>New template</Button>
      </div>

      {templates.isPending ? (
        <Loading />
      ) : templates.isError ? (
        <ErrorNotice message="Failed to load templates." />
      ) : !templates.data || templates.data.length === 0 ? (
        <EmptyState message="No templates yet. Create and approve one so schedules can use it." />
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Body</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {templates.data.map((template) => (
              <tr key={template.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-mono text-xs text-slate-500">{template.code}</td>
                <td className="px-4 py-3 font-medium text-slate-800">{template.name}</td>
                <td className="px-4 py-3 text-slate-600">
                  {TEMPLATE_CATEGORY_LABELS[template.category]}
                </td>
                <td className="max-w-64 px-4 py-3 text-slate-600">{truncate(template.body)}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-1">
                    <Badge tone={template.approved ? "green" : "amber"}>
                      {template.approved ? "Approved" : "Unapproved"}
                    </Badge>
                    <Badge tone={template.is_active ? "slate" : "slate"}>
                      {template.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <Button variant="ghost" onClick={() => setEditing(template)}>
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => toggle.mutate(template)}
                      disabled={toggle.isPending}
                    >
                      {template.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-800">Create schedule</h2>
        <p className="text-xs text-slate-500">
          Pick patients (optionally grouped by category), choose a template, set the time and
          recurrence — e.g. a diet check-in every morning at 8 AM.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5 p-4">
        <div>
          <Label>Patients</Label>
          <div className="mb-2 flex flex-wrap items-center gap-3">
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
              variant="ghost"
              type="button"
              onClick={() => setSelected(filtered.map((patient) => patient.id))}
              disabled={filtered.length === 0}
            >
              Select all ({filtered.length})
            </Button>
            <Button variant="ghost" type="button" onClick={() => setSelected([])}>
              Clear
            </Button>
          </div>

          {patients.isPending ? (
            <Loading />
          ) : patients.isError ? (
            <ErrorNotice message="Failed to load patients." />
          ) : (
            <div className="max-h-56 space-y-1 overflow-auto rounded-md border border-slate-200 p-2">
              {filtered.length === 0 ? (
                <p className="px-2 py-3 text-center text-sm text-slate-400">
                  No patients with a phone number match.
                </p>
              ) : (
                filtered.map((patient) => (
                  <label
                    key={patient.id}
                    className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(patient.id)}
                      onChange={() => togglePatient(patient.id)}
                      aria-label={patient.full_name}
                      className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    />
                    <span className="text-sm font-medium text-slate-800">{patient.full_name}</span>
                    <span className="text-xs text-slate-500">{patient.phone_number}</span>
                  </label>
                ))
              )}
            </div>
          )}
          <p className="mt-1 text-xs text-slate-500">
            {selected.length} patient{selected.length === 1 ? "" : "s"} selected.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
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
              <p className="mt-1 text-xs text-amber-600">
                No approved templates yet — free-form text will only deliver within the 24h session
                window.
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
          <div>
            <Label htmlFor="schedule-body">Message text</Label>
            <TextArea
              id="schedule-body"
              rows={3}
              maxLength={4000}
              placeholder="Type the message to send (e.g. Please share your today's meal photo.)"
              value={messageBody}
              onChange={(event) => setMessageBody(event.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              Free-form text is only delivered by WhatsApp inside the 24-hour session window;
              outside it an approved template is required.
            </p>
          </div>
        ) : null}

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
                    className={`rounded-full px-3 py-1 text-xs font-medium ${
                      weekdays.includes(day.value)
                        ? "bg-brand-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
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

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
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

        <div>
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

        {error ? <ErrorNotice message={error} /> : null}
        {createdNote ? (
          <p className="rounded-md border border-green-200 bg-green-50 px-4 py-2 text-sm text-green-800">
            {createdNote}
          </p>
        ) : null}
        {mutation.isError && !error ? (
          <ErrorNotice message="Failed to create the schedule(s)." />
        ) : null}

        <div className="flex justify-end">
          <Button type="submit" disabled={mutation.isPending || patients.isPending}>
            {mutation.isPending ? "Creating…" : "Create schedule"}
          </Button>
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
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["schedules"] }),
  });

  const materialize = useMutation({
    mutationFn: (scheduleId: string) => materializeSchedule(scheduleId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["schedules"] }),
  });

  return (
    <Card>
      <div className="border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-800">Active schedules</h2>
        <p className="text-xs text-slate-500">Pause, resume or materialise upcoming instances.</p>
      </div>

      {schedules.isPending ? (
        <Loading />
      ) : schedules.isError ? (
        <ErrorNotice message="Failed to load schedules." />
      ) : !schedules.data || schedules.data.items.length === 0 ? (
        <EmptyState message="No schedules yet. Create one above to start sending check-ins." />
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">Patient</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Recurrence</th>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Deadline</th>
              <th className="px-4 py-3">Template</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {schedules.data.items.map((schedule) => {
              const patient = nameMap.get(schedule.patient_id);
              const templateName = schedule.message_template_id
                ? templateMap.get(schedule.message_template_id)?.name ?? "—"
                : "Free-form";
              return (
                <tr key={schedule.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-800">
                    {patient?.full_name ?? schedule.patient_id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {FOLLOW_UP_LABELS[schedule.follow_up_type]}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {recurrenceSummary(schedule.recurrence_rule)}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{schedule.scheduled_local_time ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {schedule.response_deadline_hours}h
                  </td>
                  <td className="px-4 py-3 text-slate-600">{templateName}</td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONES[schedule.status]}>{schedule.status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      {schedule.status === "active" || schedule.status === "paused" ? (
                        <Button
                          variant="ghost"
                          disabled={toggleStatus.isPending}
                          onClick={() => toggleStatus.mutate(schedule)}
                        >
                          {schedule.status === "active" ? "Pause" : "Resume"}
                        </Button>
                      ) : null}
                      <Button
                        variant="ghost"
                        disabled={materialize.isPending || schedule.status !== "active"}
                        onClick={() => materialize.mutate(schedule.id)}
                      >
                        Materialise
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export function MessageSchedulerPage(): JSX.Element {
  const templates = useQuery({ queryKey: ["templates"], queryFn: () => listTemplates(false) });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Message scheduler</h1>
        <p className="text-sm text-slate-500">
          Schedule WhatsApp check-ins for patients or groups using approved templates.
        </p>
      </div>

      <ScheduleForm templates={templates.data} />
      <TemplateManager />
      <ScheduleList templates={templates.data} />
    </div>
  );
}