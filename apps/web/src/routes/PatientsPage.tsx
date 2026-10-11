import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, Card, EmptyState, ErrorNotice, Label, Loading, Modal, SelectInput, TextInput } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { createPatient, listPatients } from "@/lib/patients";
import type { PatientCategoryType, PatientStatus } from "@/lib/types";

const CATEGORY_LABELS: Record<PatientCategoryType, string> = {
  thyroid: "Thyroid",
  obesity: "Obesity",
  blood_pressure: "Blood pressure",
  diabetes: "Diabetes",
};

const STATUS_TONES: Record<PatientStatus, string> = {
  active: "green",
  inactive: "slate",
  archived: "amber",
};

function RegisterPatientModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): JSX.Element | null {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [language, setLanguage] = useState("en");
  const [categories, setCategories] = useState<PatientCategoryType[]>([]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createPatient({
        full_name: fullName,
        phone_number: phone || null,
        preferred_language: language,
        categories,
      }),
    onSuccess: () => {
      setFullName("");
      setPhone("");
      setLanguage("en");
      setCategories([]);
      setError(null);
      onClose();
      void queryClient.invalidateQueries({ queryKey: ["patients"] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Unable to register patient.");
    },
  });

  if (!open) return null;

  const toggleCategory = (category: PatientCategoryType): void => {
    setCategories((current) =>
      current.includes(category)
        ? current.filter((item) => item !== category)
        : [...current, category],
    );
  };

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <Modal open={open} onClose={onClose} title="Register patient">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <Label>Full name</Label>
          <TextInput
            required
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="e.g. Asha Patil"
          />
        </div>
        <div>
          <Label>Phone number</Label>
          <TextInput
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="e.g. +91 98765 43210"
          />
        </div>
        <div>
          <Label>Preferred language</Label>
          <SelectInput value={language} onChange={(event) => setLanguage(event.target.value)}>
            <option value="en">English</option>
            <option value="mr">Marathi</option>
            <option value="hi">Hindi</option>
          </SelectInput>
        </div>
        <div>
          <Label>Categories</Label>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(CATEGORY_LABELS) as PatientCategoryType[]).map((category) => (
              <button
                key={category}
                type="button"
                onClick={() => toggleCategory(category)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  categories.includes(category)
                    ? "bg-brand-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {CATEGORY_LABELS[category]}
              </button>
            ))}
          </div>
        </div>
        {error ? <ErrorNotice message={error} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Register"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function PatientsPage(): JSX.Element {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [page, setPage] = useState(1);
  const [registerOpen, setRegisterOpen] = useState(false);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["patients", search, category, status, page],
    queryFn: () =>
      listPatients({
        search: search || undefined,
        category: (category || undefined) as PatientCategoryType | undefined,
        status: (status || undefined) as PatientStatus | undefined,
        page,
        size: 20,
      }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Patients</h1>
          <p className="text-sm text-slate-500">Register, search and open patient records.</p>
        </div>
        <Button onClick={() => setRegisterOpen(true)}>Register patient</Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-52 flex-1">
          <TextInput
            placeholder="Search by name, ID or phone…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <SelectInput
          className="w-44"
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All categories</option>
          {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectInput>
        <SelectInput
          className="w-40"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {(["active", "inactive", "archived"] as PatientStatus[]).map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </SelectInput>
      </div>

      <Card>
        {isPending ? (
          <Loading />
        ) : isError ? (
          <ErrorNotice message={error instanceof Error ? error.message : "Failed to load patients."} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No patients match the current filters." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Categories</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((patient) => (
                <tr key={patient.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{patient.internal_id}</td>
                  <td className="px-4 py-3">
                    <Link to={`/patients/${patient.id}`} className="font-medium text-brand-700 hover:underline">
                      {patient.full_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{patient.phone_number ?? "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {patient.categories.length === 0 ? (
                        <span className="text-slate-400">—</span>
                      ) : (
                        patient.categories.map((categoryItem) => (
                          <Badge key={categoryItem.id} tone="brand">
                            {CATEGORY_LABELS[categoryItem.category_type]}
                          </Badge>
                        ))
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={STATUS_TONES[patient.status]}>{patient.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {data && data.pages > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-500">
            Page {data.page} of {data.pages} · {data.total} patients
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>
              Previous
            </Button>
            <Button variant="ghost" disabled={page >= data.pages} onClick={() => setPage((current) => current + 1)}>
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <RegisterPatientModal open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  );
}