import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { Avatar } from "@/components/Avatar";
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
  SelectInput,
  TabBar,
  TextArea,
  TextInput,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PatientAIInsightsTab } from "@/routes/PatientAIInsightsTab";
import { PatientFinanceTab } from "@/routes/PatientFinanceTab";
import { PatientMessagesTab } from "@/routes/PatientMessagesTab";
import { PatientTrendsTab } from "@/routes/PatientTrendsTab";
import {
  addConsent,
  addObservation,
  assignCategory,
  createCarePlan,
  getPatient,
  listCarePlans,
  listConsents,
  listObservations,
  listTimeline,
} from "@/lib/patients";
import type { ConsentType, PatientCategoryType, TimelineEventType } from "@/lib/types";

const CATEGORY_LABELS: Record<PatientCategoryType, string> = {
  thyroid: "Thyroid",
  obesity: "Obesity",
  blood_pressure: "Blood pressure",
  diabetes: "Diabetes",
};

const OBSERVATION_OPTIONS = [
  { type: "blood_pressure", unit: "mmHg" },
  { type: "blood_glucose", unit: "mg/dL" },
  { type: "weight", unit: "kg" },
  { type: "pulse", unit: "bpm" },
  { type: "waist", unit: "cm" },
];

const EVENT_TONES: Record<TimelineEventType, string> = {
  observation: "brand",
  care_plan: "green",
  category: "amber",
  consent: "slate",
};

function NowInput() {
  const { patientId } = useParams();
  const queryClient = useQueryClient();
  const [type, setType] = useState(OBSERVATION_OPTIONS[0].type);
  const [value, setValue] = useState("");
  const [session, setSession] = useState("");
  const [error, setError] = useState<string | null>(null);
  const unit = OBSERVATION_OPTIONS.find((option) => option.type === type)?.unit ?? "";

  const mutation = useMutation({
    mutationFn: () =>
      addObservation(patientId!, {
        observation_type: type,
        value: value === "" ? null : Number(value),
        unit,
        observed_at: new Date().toISOString(),
        measurement_context: session ? { session } : null,
      }),
    onSuccess: () => {
      setValue("");
      setSession("");
      setError(null);
      toast.success("Observation recorded");
      void queryClient.invalidateQueries({ queryKey: ["patient-detail", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["observations", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to save observation."),
  });

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <Card>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3 p-4">
        <div>
          <Label>Type</Label>
          <SelectInput className="w-48" value={type} onChange={(event) => setType(event.target.value)}>
            {OBSERVATION_OPTIONS.map((option) => (
              <option key={option.type} value={option.type}>
                {option.type.replace("_", " ")} ({option.unit})
              </option>
            ))}
          </SelectInput>
        </div>
        <div>
          <Label>Value</Label>
          <TextInput
            type="number"
            step="any"
            className="w-32"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            required
          />
        </div>
        <div>
          <Label>Context (optional)</Label>
          <SelectInput className="w-40" value={session} onChange={(event) => setSession(event.target.value)}>
            <option value="">—</option>
            <option value="fasting">Fasting</option>
            <option value="post_meal">Post meal</option>
            <option value="morning">Morning</option>
            <option value="evening">Evening</option>
          </SelectInput>
        </div>
        <Button type="submit" loading={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Record"}
        </Button>
      </form>
      {error ? (
        <div className="px-4 pb-4">
          <ErrorNotice message={error} />
        </div>
      ) : null}
    </Card>
  );
}

function ObservationsTab({ patientId }: { patientId: string }): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["observations", patientId],
    queryFn: () => listObservations(patientId),
  });

  return (
    <div className="space-y-4">
      <NowInput />
      <Card>
        {isPending ? (
          <SkeletonTable rows={5} cols={4} />
        ) : isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load observations." />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No observations recorded yet." />
        ) : (
          <Table minClassName="min-w-[520px]">
            <THead>
              <TH>Date</TH>
              <TH>Type</TH>
              <TH>Value</TH>
              <TH>Source</TH>
            </THead>
            <tbody>
              {data.items.map((observation) => (
                <TR key={observation.id}>
                  <TD className="text-ink-secondary">{formatDate(observation.observed_at)}</TD>
                  <TD className="font-medium capitalize text-ink">
                    {observation.observation_type.replace("_", " ")}
                  </TD>
                  <TD className="font-semibold tabular-nums">
                    {observation.value} <span className="font-normal text-ink-muted">{observation.unit}</span>
                  </TD>
                  <TD>
                    <Badge tone="slate">{observation.source.replace("_", " ")}</Badge>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

function CarePlansTab({ patientId }: { patientId: string }): JSX.Element {
  const queryClient = useQueryClient();
  const [diet, setDiet] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["care-plans", patientId],
    queryFn: () => listCarePlans(patientId),
  });

  const mutation = useMutation({
    mutationFn: () =>
      createCarePlan(patientId, {
        status: "active",
        content: {
          diet: diet || null,
          instructions: instructions || null,
        },
      }),
    onSuccess: () => {
      setDiet("");
      setInstructions("");
      setError(null);
      toast.success("Care plan version created");
      void queryClient.invalidateQueries({ queryKey: ["care-plans", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["timeline", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to create care plan."),
  });

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="New care plan version" description="Creating a new version keeps the history intact." />
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <div>
            <Label>Diet plan</Label>
            <TextArea
              rows={3}
              value={diet}
              onChange={(event) => setDiet(event.target.value)}
              placeholder="e.g. Low carb, 6 small meals"
            />
          </div>
          <div>
            <Label>Instructions</Label>
            <TextArea
              rows={2}
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder="e.g. Morning walk 30 min, no fried food"
            />
          </div>
          {error ? <ErrorNotice message={error} /> : null}
          <div className="flex justify-end">
            <Button type="submit" loading={mutation.isPending}>
              <Plus className="h-4 w-4" />
              {mutation.isPending ? "Saving…" : "Create new care plan (version)"}
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        {isPending ? (
          <div className="space-y-3 p-4">
            <p className="text-sm text-ink-muted">Loading…</p>
          </div>
        ) : isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load care plans." />
          </div>
        ) : !data || data.length === 0 ? (
          <EmptyState message="No care plans yet." />
        ) : (
          <ul className="divide-y divide-line">
            {data.map((plan) => (
              <li key={plan.id} className="px-5 py-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-ink">
                    Version {plan.version}{" "}
                    <span className="text-xs font-normal text-ink-muted">
                      (created {formatDate(plan.created_at)})
                    </span>
                  </p>
                  <Badge tone={plan.status === "active" ? "green" : "slate"} dot>
                    {plan.status}
                  </Badge>
                </div>
                {plan.content?.diet ? (
                  <p className="mt-1.5 text-sm text-ink-secondary">
                    <span className="font-medium text-ink-muted">Diet:</span> {String(plan.content.diet)}
                  </p>
                ) : null}
                {plan.content?.instructions ? (
                  <p className="mt-0.5 text-sm text-ink-secondary">
                    <span className="font-medium text-ink-muted">Instructions:</span>{" "}
                    {String(plan.content.instructions)}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function TimelineTab({ patientId }: { patientId: string }): JSX.Element {
  const { data, isPending, isError } = useQuery({
    queryKey: ["timeline", patientId],
    queryFn: () => listTimeline(patientId),
  });

  return (
    <Card>
      {isPending ? (
        <Loading />
      ) : isError ? (
        <div className="p-4">
          <ErrorNotice message="Failed to load timeline." />
        </div>
      ) : !data || data.length === 0 ? (
        <EmptyState message="No activity yet." />
      ) : (
        <ol className="divide-y divide-line">
          {data.map((event, index) => (
            <li
              key={`${event.event_type}-${event.entity_id}-${index}`}
              className="flex items-start gap-3 px-5 py-3.5"
            >
              <Badge tone={EVENT_TONES[event.event_type]} className="mt-0.5 capitalize">
                {event.event_type.replace("_", " ")}
              </Badge>
              <div className="min-w-0">
                <p className="text-sm text-ink">{event.summary}</p>
                <p className="mt-0.5 text-xs text-ink-muted">{formatDate(event.occurred_at)}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function ConsentsTab({ patientId }: { patientId: string }): JSX.Element {
  const queryClient = useQueryClient();
  const [consentType, setConsentType] = useState<ConsentType>("communication");
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["consents", patientId],
    queryFn: () => listConsents(patientId),
  });

  const mutation = useMutation({
    mutationFn: () => addConsent(patientId, { consent_type: consentType, purpose }),
    onSuccess: () => {
      setPurpose("");
      setError(null);
      toast.success("Consent recorded");
      void queryClient.invalidateQueries({ queryKey: ["consents", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to record consent."),
  });

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <div className="space-y-4">
      <Card>
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3 p-4">
          <div>
            <Label>Consent type</Label>
            <SelectInput
              className="w-48"
              value={consentType}
              onChange={(event) => setConsentType(event.target.value as ConsentType)}
            >
              <option value="communication">Communication</option>
              <option value="health_data">Health data</option>
            </SelectInput>
          </div>
          <div className="min-w-52 flex-1">
            <Label>Purpose</Label>
            <TextInput
              required
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
              placeholder="e.g. WhatsApp reminders"
            />
          </div>
          <Button type="submit" loading={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Record consent"}
          </Button>
        </form>
        {error ? (
          <div className="px-4 pb-4">
            <ErrorNotice message={error} />
          </div>
        ) : null}
      </Card>

      <Card>
        {isPending ? (
          <Loading />
        ) : isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load consents." />
          </div>
        ) : !data || data.length === 0 ? (
          <EmptyState message="No consents recorded." />
        ) : (
          <ul className="divide-y divide-line">
            {data.map((consent) => (
              <li key={consent.id} className="flex items-center justify-between px-5 py-3.5">
                <div>
                  <p className="text-sm font-medium capitalize text-ink">
                    {consent.consent_type.replace("_", " ")}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-muted">
                    {consent.purpose} · recorded {formatDate(consent.captured_at)}
                  </p>
                </div>
                <Badge tone={consent.status === "active" ? "green" : "slate"} dot>
                  {consent.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function OverviewTab({ patientId }: { patientId: string }): JSX.Element {
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<PatientCategoryType>("blood_pressure");
  const [error, setError] = useState<string | null>(null);

  const { data: patient, isPending, isError } = useQuery({
    queryKey: ["patient-detail", patientId],
    queryFn: () => getPatient(patientId),
  });

  const mutation = useMutation({
    mutationFn: () => assignCategory(patientId, category),
    onSuccess: () => {
      setError(null);
      toast.success("Category assigned");
      void queryClient.invalidateQueries({ queryKey: ["patient-detail", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to assign category."),
  });

  if (isPending) return <Loading />;
  if (isError || !patient) return <ErrorNotice message="Failed to load patient." />;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Patient record" />
        <dl className="divide-y divide-line px-5 py-1">
          <div className="flex items-center justify-between py-2.5">
            <dt className="text-sm text-ink-muted">Full name</dt>
            <dd className="text-sm font-semibold text-ink">{patient.full_name}</dd>
          </div>
          <div className="flex items-center justify-between py-2.5">
            <dt className="text-sm text-ink-muted">Phone</dt>
            <dd className="text-sm text-ink-secondary">{patient.phone_number ?? "—"}</dd>
          </div>
          <div className="flex items-center justify-between py-2.5">
            <dt className="text-sm text-ink-muted">Language</dt>
            <dd className="text-sm uppercase text-ink-secondary">{patient.preferred_language}</dd>
          </div>
          <div className="flex items-center justify-between py-2.5">
            <dt className="text-sm text-ink-muted">Registered</dt>
            <dd className="text-sm text-ink-secondary">{formatDate(patient.created_at)}</dd>
          </div>
          <div className="flex items-center justify-between py-2.5">
            <dt className="text-sm text-ink-muted">Status</dt>
            <dd>
              <Badge tone={patient.status === "active" ? "green" : "slate"} dot>
                {patient.status}
              </Badge>
            </dd>
          </div>
        </dl>
      </Card>

      <Card>
        <CardHeader title="Operating categories" description="Used for scheduling and analytics scope." />
        <div className="p-4">
          <div className="mb-4 flex flex-wrap gap-2">
            {patient.categories.length === 0 ? (
              <span className="text-sm text-ink-muted">No categories assigned.</span>
            ) : (
              patient.categories.map((item) => (
                <Badge key={item.id} tone="brand">
                  {CATEGORY_LABELS[item.category_type]}
                </Badge>
              ))
            )}
          </div>
          <form
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              setError(null);
              mutation.mutate();
            }}
            className="flex items-end gap-3"
          >
            <div className="flex-1">
              <Label>Assign category</Label>
              <SelectInput
                value={category}
                onChange={(event) => setCategory(event.target.value as PatientCategoryType)}
              >
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </SelectInput>
            </div>
            <Button type="submit" loading={mutation.isPending}>
              Assign
            </Button>
          </form>
          {error ? (
            <div className="mt-3">
              <ErrorNotice message={error} />
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}

const TABS = [
  "Overview",
  "Observations",
  "Trends",
  "Care plan",
  "Timeline",
  "AI insights",
  "Consents",
  "Finance",
  "Messages",
] as const;
type Tab = (typeof TABS)[number];

export function PatientDetailPage(): JSX.Element {
  const { patientId } = useParams();
  const [tab, setTab] = useState<Tab>("Overview");

  const { data: patient, isPending, isError } = useQuery({
    queryKey: ["patient-detail", patientId],
    queryFn: () => getPatient(patientId!),
    enabled: Boolean(patientId),
  });

  if (!patientId) return <ErrorNotice message="No patient specified." />;
  if (isPending) return <Loading />;
  if (isError || !patient) return <ErrorNotice message="Failed to load patient." />;

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/patients"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-muted transition hover:text-ink"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to patients
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <Avatar name={patient.full_name} size="lg" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">
                {patient.full_name}
              </h1>
              <Badge tone="slate" className="font-mono">
                {patient.internal_id}
              </Badge>
              <Badge tone={patient.status === "active" ? "green" : "slate"} dot>
                {patient.status}
              </Badge>
            </div>
            <p className="mt-0.5 text-sm text-ink-muted">
              {patient.phone_number ?? "No phone on record"} · {patient.categories.length}{" "}
              categor{patient.categories.length === 1 ? "y" : "ies"}
            </p>
          </div>
        </div>
      </div>

      <TabBar tabs={TABS} active={tab} onChange={(next) => setTab(next as Tab)} />

      <div className="animate-fade-in">
        {tab === "Overview" ? (
          <OverviewTab patientId={patientId} />
        ) : tab === "Observations" ? (
          <ObservationsTab patientId={patientId} />
        ) : tab === "Trends" ? (
          <PatientTrendsTab patientId={patientId} />
        ) : tab === "Care plan" ? (
          <CarePlansTab patientId={patientId} />
        ) : tab === "Timeline" ? (
          <TimelineTab patientId={patientId} />
        ) : tab === "Finance" ? (
          <PatientFinanceTab patientId={patientId} />
        ) : tab === "Messages" ? (
          <PatientMessagesTab patientId={patientId} />
        ) : tab === "AI insights" ? (
          <PatientAIInsightsTab patientId={patientId} />
        ) : (
          <ConsentsTab patientId={patientId} />
        )}
      </div>
    </div>
  );
}
