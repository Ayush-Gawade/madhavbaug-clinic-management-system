import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge, Button, Card, EmptyState, ErrorNotice, Label, Loading, SelectInput, TextInput } from "@/components/ui";
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
    <Card className="p-4">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <div>
          <Label>Type</Label>
          <SelectInput className="w-44" value={type} onChange={(event) => setType(event.target.value)}>
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
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Record"}
        </Button>
      </form>
      {error ? <div className="mt-3"><ErrorNotice message={error} /></div> : null}
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
          <Loading />
        ) : isError ? (
          <ErrorNotice message="Failed to load observations." />
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No observations recorded yet." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Source</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((observation) => (
                <tr key={observation.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 text-slate-600">{formatDate(observation.observed_at)}</td>
                  <td className="px-4 py-3 capitalize">{observation.observation_type.replace("_", " ")}</td>
                  <td className="px-4 py-3 font-medium">
                    {observation.value} {observation.unit}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone="slate">{observation.source.replace("_", " ")}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
      <Card className="p-4">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label>Diet plan</Label>
            <textarea
              rows={3}
              value={diet}
              onChange={(event) => setDiet(event.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="e.g. Low carb, 6 small meals"
            />
          </div>
          <div>
            <Label>Instructions</Label>
            <textarea
              rows={2}
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              placeholder="e.g. Morning walk 30 min, no fried food"
            />
          </div>
          {error ? <ErrorNotice message={error} /> : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Create new care plan (version)"}
          </Button>
        </form>
      </Card>

      <Card>
        {isPending ? (
          <Loading />
        ) : isError ? (
          <ErrorNotice message="Failed to load care plans." />
        ) : !data || data.length === 0 ? (
          <EmptyState message="No care plans yet." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.map((plan) => (
              <li key={plan.id} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <p className="font-medium">
                    Version {plan.version} <span className="text-xs font-normal text-slate-400">(created {formatDate(plan.created_at)})</span>
                  </p>
                  <Badge tone={plan.status === "active" ? "green" : "slate"}>{plan.status}</Badge>
                </div>
                {plan.content?.diet ? (
                  <p className="mt-1 text-sm text-slate-600">
                    <span className="text-slate-400">Diet:</span> {String(plan.content.diet)}
                  </p>
                ) : null}
                {plan.content?.instructions ? (
                  <p className="mt-0.5 text-sm text-slate-600">
                    <span className="text-slate-400">Instructions:</span> {String(plan.content.instructions)}
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
        <ErrorNotice message="Failed to load timeline." />
      ) : !data || data.length === 0 ? (
        <EmptyState message="No activity yet." />
      ) : (
        <ol className="divide-y divide-slate-100">
          {data.map((event, index) => (
            <li key={`${event.event_type}-${event.entity_id}-${index}`} className="flex items-start gap-3 px-4 py-3">
              <Badge tone={EVENT_TONES[event.event_type]}>{event.event_type.replace("_", " ")}</Badge>
              <div className="min-w-0">
                <p className="text-sm text-slate-800">{event.summary}</p>
                <p className="text-xs text-slate-400">{formatDate(event.occurred_at)}</p>
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
      <Card className="p-4">
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
          <div>
            <Label>Consent type</Label>
            <SelectInput className="w-44" value={consentType} onChange={(event) => setConsentType(event.target.value as ConsentType)}>
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
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Record consent"}
          </Button>
        </form>
        {error ? <div className="mt-3"><ErrorNotice message={error} /></div> : null}
      </Card>

      <Card>
        {isPending ? (
          <Loading />
        ) : isError ? (
          <ErrorNotice message="Failed to load consents." />
        ) : !data || data.length === 0 ? (
          <EmptyState message="No consents recorded." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.map((consent) => (
              <li key={consent.id} className="flex items-center justify-between px-4 py-3">
                <div>
                  <p className="text-sm font-medium capitalize">{consent.consent_type.replace("_", " ")}</p>
                  <p className="text-xs text-slate-500">{consent.purpose} · recorded {formatDate(consent.captured_at)}</p>
                </div>
                <Badge tone={consent.status === "active" ? "green" : "slate"}>{consent.status}</Badge>
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
      void queryClient.invalidateQueries({ queryKey: ["patient-detail", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to assign category."),
  });

  if (isPending) return <Loading />;
  if (isError || !patient) return <ErrorNotice message="Failed to load patient." />;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-800">Patient record</h3>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500">Full name</dt>
            <dd className="font-medium">{patient.full_name}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Phone</dt>
            <dd>{patient.phone_number ?? "—"}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Language</dt>
            <dd className="uppercase">{patient.preferred_language}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Registered</dt>
            <dd>{formatDate(patient.created_at)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500">Status</dt>
            <dd>
              <Badge tone={patient.status === "active" ? "green" : "slate"}>{patient.status}</Badge>
            </dd>
          </div>
        </dl>
      </Card>

      <Card className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-800">Operating categories</h3>
        <div className="mb-3 flex flex-wrap gap-2">
          {patient.categories.length === 0 ? (
            <span className="text-sm text-slate-400">No categories assigned.</span>
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
            <SelectInput value={category} onChange={(event) => setCategory(event.target.value as PatientCategoryType)}>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectInput>
          </div>
          <Button type="submit" disabled={mutation.isPending}>
            Assign
          </Button>
        </form>
        {error ? <div className="mt-3"><ErrorNotice message={error} /></div> : null}
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
      <div className="flex items-start justify-between">
        <div>
          <Link to="/patients" className="text-sm text-slate-500 hover:text-slate-700">
            ← Back to patients
          </Link>
          <div className="mt-1 flex items-center gap-3">
            <h1 className="text-xl font-semibold text-slate-900">{patient.full_name}</h1>
            <Badge tone="slate">{patient.internal_id}</Badge>
            <Badge tone={patient.status === "active" ? "green" : "slate"}>{patient.status}</Badge>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`rounded-t-md px-4 py-2 text-sm font-medium ${
              tab === item
                ? "border-b-2 border-brand-600 text-brand-700"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

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
  );
}