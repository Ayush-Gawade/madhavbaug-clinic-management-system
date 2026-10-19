import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Avatar } from "@/components/Avatar";
import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import { toast } from "@/components/Toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Label,
  Modal,
  Pagination,
  SelectInput,
  TextInput,
} from "@/components/ui";
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
      toast.success("Patient registered", { description: `${fullName} was added to the clinic.` });
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
                className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset transition ${
                  categories.includes(category)
                    ? "bg-brand-600 text-white ring-brand-600"
                    : "bg-surface text-ink-secondary ring-line-strong hover:bg-surface-sunken"
                }`}
              >
                {CATEGORY_LABELS[category]}
              </button>
            ))}
          </div>
        </div>
        {error ? <ErrorNotice message={error} /> : null}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Register"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function PatientsPage(): JSX.Element {
  // Seed the filters from the URL so cards elsewhere (e.g. the WhatsApp
  // overview) can deep-link into a pre-filtered patient list.
  const [searchParams] = useSearchParams();
  const initialCategory = searchParams.get("category") ?? "";
  const initialStatus = searchParams.get("status") ?? "";
  const [search, setSearch] = useState(() => searchParams.get("search") ?? "");
  const [category, setCategory] = useState<string>(
    () => (initialCategory in CATEGORY_LABELS ? initialCategory : ""),
  );
  const [status, setStatus] = useState<string>(
    () => (["active", "inactive", "archived"].includes(initialStatus) ? initialStatus : ""),
  );
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
      <PageHeader
        title="Patients"
        description="Register, search and open patient records."
        actions={
          <Button onClick={() => setRegisterOpen(true)}>
            <UserPlus className="h-4 w-4" />
            Register patient
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
          <TextInput
            className="pl-9"
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
          <SkeletonTable rows={8} cols={5} />
        ) : isError ? (
          <div className="p-4">
            <ErrorNotice message={error instanceof Error ? error.message : "Failed to load patients."} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState message="No patients match the current filters." />
        ) : (
          <Table minClassName="min-w-[720px]">
            <THead>
              <TH>ID</TH>
              <TH>Name</TH>
              <TH>Phone</TH>
              <TH>Categories</TH>
              <TH>Status</TH>
            </THead>
            <tbody>
              {data.items.map((patient) => (
                <TR key={patient.id}>
                  <TD className="font-mono text-xs text-ink-muted">{patient.internal_id}</TD>
                  <TD>
                    <Link
                      to={`/patients/${patient.id}`}
                      className="flex items-center gap-3 font-semibold text-ink transition hover:text-brand-700 dark:hover:text-brand-300"
                    >
                      <Avatar name={patient.full_name} size="sm" />
                      {patient.full_name}
                    </Link>
                  </TD>
                  <TD className="text-ink-secondary">{patient.phone_number ?? "—"}</TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {patient.categories.length === 0 ? (
                        <span className="text-ink-faint">—</span>
                      ) : (
                        patient.categories.map((categoryItem) => (
                          <Badge key={categoryItem.id} tone="brand">
                            {CATEGORY_LABELS[categoryItem.category_type]}
                          </Badge>
                        ))
                      )}
                    </div>
                  </TD>
                  <TD>
                    <Badge tone={STATUS_TONES[patient.status]} dot>
                      {patient.status}
                    </Badge>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}

        {data && data.pages > 1 ? (
          <Pagination
            page={data.page}
            totalPages={data.pages}
            total={data.total}
            itemLabel="patients"
            onPageChange={setPage}
          />
        ) : null}
      </Card>

      <RegisterPatientModal open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  );
}
