import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BotMessageSquare, MessageSquareText, Phone } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { toast } from "@/components/Toast";
import {
  Button,
  Callout,
  Card,
  CardHeader,
  ErrorNotice,
  Label,
  Loading,
  TextInput,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  AUTO_REPLY_ENABLED_KEY,
  DOCTOR_PHONE_KEY,
  DOCTOR_TEMPLATE_KEY,
  isValidPhone,
  isValidTemplateName,
  listSettings,
  updateSetting,
} from "@/lib/settings";
import type { AppSetting } from "@/lib/types";

const PHONE_HINT = "Enter the doctor's number in international format, e.g. +919359883349.";
const TEMPLATE_HINT =
  "Use the template's Meta name: lowercase letters, digits and underscores only, or leave it empty.";

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Saving settings failed.";
}

function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}): JSX.Element {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 ${
        checked ? "bg-brand-600" : "bg-surface-sunken ring-1 ring-inset ring-line-strong"
      }`}
    >
      <span
        className={`inline-block h-4.5 w-4.5 rounded-full bg-white shadow-hairline transition duration-200 ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}

function fieldOf(settings: AppSetting[] | undefined, key: string): AppSetting | undefined {
  return settings?.find((setting) => setting.key === key);
}

export function SettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: listSettings });

  const [enabled, setEnabled] = useState(false);
  const [doctorPhone, setDoctorPhone] = useState("");
  const [doctorTemplate, setDoctorTemplate] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);

  useEffect(() => {
    if (hydrated || !settings.data) return;
    setEnabled(fieldOf(settings.data, AUTO_REPLY_ENABLED_KEY)?.value === true);
    setDoctorPhone(String(fieldOf(settings.data, DOCTOR_PHONE_KEY)?.value ?? ""));
    setDoctorTemplate(String(fieldOf(settings.data, DOCTOR_TEMPLATE_KEY)?.value ?? ""));
    setHydrated(true);
  }, [settings.data, hydrated]);

  const save = useMutation({
    mutationFn: async () => {
      await updateSetting(AUTO_REPLY_ENABLED_KEY, enabled);
      await updateSetting(DOCTOR_PHONE_KEY, doctorPhone.trim());
      await updateSetting(DOCTOR_TEMPLATE_KEY, doctorTemplate.trim());
    },
    onSuccess: () => {
      toast.success("Settings saved");
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const handleSave = (): void => {
    if (!isValidPhone(doctorPhone)) {
      setPhoneError(PHONE_HINT);
      return;
    }
    setPhoneError(null);
    if (!isValidTemplateName(doctorTemplate)) {
      setTemplateError(TEMPLATE_HINT);
      return;
    }
    setTemplateError(null);
    save.mutate();
  };

  const enabledSetting = fieldOf(settings.data, AUTO_REPLY_ENABLED_KEY);
  const phoneSetting = fieldOf(settings.data, DOCTOR_PHONE_KEY);
  const templateSetting = fieldOf(settings.data, DOCTOR_TEMPLATE_KEY);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Clinic-wide switches that take effect on the next message, with no restart."
      />

      {settings.isPending ? (
        <Loading />
      ) : settings.isError || !settings.data ? (
        <ErrorNotice message="Failed to load settings." />
      ) : (
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <BotMessageSquare className="h-4 w-4 text-brand-700 dark:text-brand-300" />
                AI auto-reply
              </span>
            }
            description={enabledSetting?.description}
          />

          <div className="space-y-6 px-5 py-5">
            <Callout tone="info">
              <span className="text-xs leading-5">
                When this is on, a reading the patient sends is acknowledged with a short,
                automatically-written WhatsApp reply. Readings inside the safe zone get a normal
                confirmation; readings outside it get a careful one and open an alert as usual. Only
                urgent findings notify the doctor on WhatsApp. Greetings and open questions are left
                for staff to answer. This is off until you switch it on.
              </span>
            </Callout>

            <div className="flex flex-wrap items-start justify-between gap-4 rounded-lg border border-line px-4 py-3.5">
              <div className="min-w-0 max-w-xl">
                <p className="text-sm font-semibold text-ink">Reply to patients automatically</p>
                <p className="mt-1 text-xs leading-5 text-ink-muted">
                  Requires AI extraction to be enabled. Turning this off stops new replies
                  immediately; replies already sent are unaffected.
                </p>
                <p className="mt-1.5 text-[11px] text-ink-faint">
                  {enabledSetting?.updated_at
                    ? "Saved to the database"
                    : "Not saved yet — using the default"}
                </p>
              </div>
              <div className="flex items-center gap-2.5">
                <span className="text-xs font-semibold text-ink-secondary">
                  {enabled ? "On" : "Off"}
                </span>
                <Switch
                  checked={enabled}
                  onChange={setEnabled}
                  label="Automatically reply to patient messages"
                />
              </div>
            </div>

            <div className="max-w-md">
              <Label htmlFor="doctor-phone">Doctor notified on urgent readings</Label>
              <div className="mt-1.5 flex items-center gap-2">
                <Phone className="h-4 w-4 shrink-0 text-ink-faint" aria-hidden="true" />
                <TextInput
                  id="doctor-phone"
                  type="tel"
                  inputMode="tel"
                  value={doctorPhone}
                  onChange={(event) => {
                    setDoctorPhone(event.target.value);
                    setPhoneError(null);
                  }}
                  placeholder="+919359883349"
                  aria-invalid={phoneError !== null}
                />
              </div>
              <p className="mt-1.5 text-xs text-ink-muted">{phoneSetting?.description}</p>
              {phoneError ? (
                <p role="alert" className="mt-1.5 text-xs font-medium text-red-600">
                  {phoneError}
                </p>
              ) : null}
            </div>

            <div className="max-w-md">
              <Label htmlFor="doctor-template">Urgent-alert template name</Label>
              <div className="mt-1.5 flex items-center gap-2">
                <MessageSquareText className="h-4 w-4 shrink-0 text-ink-faint" aria-hidden="true" />
                <TextInput
                  id="doctor-template"
                  type="text"
                  value={doctorTemplate}
                  onChange={(event) => {
                    setDoctorTemplate(event.target.value);
                    setTemplateError(null);
                  }}
                  placeholder="urgent_reading_alert"
                  aria-invalid={templateError !== null}
                />
              </div>
              <p className="mt-1.5 text-xs text-ink-muted">{templateSetting?.description}</p>
              <p className="mt-1.5 text-[11px] leading-5 text-ink-faint">
                The template body must name the patient so the doctor can identify them, e.g.
                <code className="mx-1 rounded bg-surface-sunken px-1 py-0.5">
                  Urgent reading from {"{{patient_name}}"}: {"{{reason}}"}
                </code>
                Available values: {"{{patient_name}}"}, {"{{patient_phone}}"}, {"{{reason}}"}.
              </p>
              {templateError ? (
                <p role="alert" className="mt-1.5 text-xs font-medium text-red-600">
                  {templateError}
                </p>
              ) : null}
            </div>

            {save.isError ? <ErrorNotice message={messageOf(save.error)} /> : null}

            <div className="flex items-center gap-3 border-t border-line pt-4">
              <Button onClick={handleSave} loading={save.isPending}>
                Save changes
              </Button>
              <span className="text-xs text-ink-muted">Applies to the next inbound message.</span>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
