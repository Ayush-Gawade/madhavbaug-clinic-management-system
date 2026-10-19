import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Tags } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import { toast } from "@/components/Toast";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Callout,
  EmptyState,
  ErrorNotice,
  Label,
  Loading,
  Modal,
  SelectInput,
  TextInput,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { createTreatment, estimateTreatment, listTreatments } from "@/lib/finance";

function CreateTreatmentModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): JSX.Element | null {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [serviceCategory, setServiceCategory] = useState("");
  const [listPrice, setListPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createTreatment({
        name,
        treatment_code: code,
        service_category: serviceCategory || null,
        list_price: String(listPrice),
      }),
    onSuccess: () => {
      setName("");
      setCode("");
      setServiceCategory("");
      setListPrice("");
      setError(null);
      toast.success("Treatment created");
      onClose();
      void queryClient.invalidateQueries({ queryKey: ["treatments"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to create treatment."),
  });

  if (!open) return null;

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <Modal open={open} onClose={onClose} title="Create treatment">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <Label htmlFor="treatment-name">Name</Label>
          <TextInput
            required
            id="treatment-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="treatment-code">Code</Label>
          <TextInput
            required
            id="treatment-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="e.g. PK-100"
          />
        </div>
        <div>
          <Label htmlFor="treatment-category">Service category</Label>
          <TextInput
            id="treatment-category"
            value={serviceCategory}
            onChange={(event) => setServiceCategory(event.target.value)}
            placeholder="e.g. Panchakarma"
          />
        </div>
        <div>
          <Label htmlFor="treatment-price">List price</Label>
          <TextInput
            type="number"
            step="0.01"
            min="0"
            required
            id="treatment-price"
            value={listPrice}
            onChange={(event) => setListPrice(event.target.value)}
          />
        </div>
        {error ? <ErrorNotice message={error} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending} loading={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Create"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function EstimatorCard(): JSX.Element {
  const { data: treatments, isPending } = useQuery({
    queryKey: ["treatments", true],
    queryFn: () => listTreatments(true),
  });
  const [treatmentId, setTreatmentId] = useState("");
  const [discount, setDiscount] = useState(0);

  useEffect(() => {
    if (!treatmentId && treatments && treatments.length > 0) {
      setTreatmentId(treatments[0].id);
    }
  }, [treatmentId, treatments]);

  const { data: result, isFetching } = useQuery({
    queryKey: ["estimate", treatmentId, discount],
    queryFn: () => estimateTreatment(treatmentId, discount),
    enabled: Boolean(treatmentId),
  });

  return (
    <Card>
      <CardHeader
        title="Cost estimation"
        description="Live margin preview as you adjust the discount slider."
      />
      {isPending ? (
        <div className="p-4">
          <Loading />
        </div>
      ) : (
        <div className="grid gap-5 p-4 lg:grid-cols-3">
          <div className="space-y-4">
            <div>
              <Label htmlFor="estimate-treatment">Treatment</Label>
              <SelectInput
                id="estimate-treatment"
                value={treatmentId}
                onChange={(event) => setTreatmentId(event.target.value)}
              >
                {treatments?.map((treatment) => (
                  <option key={treatment.id} value={treatment.id}>
                    {treatment.name} — ₹{treatment.list_price}
                  </option>
                ))}
              </SelectInput>
            </div>
            <div>
              <div className="flex items-center justify-between">
                <Label htmlFor="estimate-discount">Discount</Label>
                <span className="text-sm font-bold tabular-nums text-brand-700 dark:text-brand-300">
                  {discount}%
                </span>
              </div>
              <input
                type="range"
                id="estimate-discount"
                min={0}
                max={99}
                step={1}
                value={discount}
                onChange={(event) => setDiscount(Number(event.target.value))}
                className="mt-1 w-full accent-brand-600"
              />
            </div>
            <p className="text-xs text-ink-muted">
              Official max discount at configured boundaries:{" "}
              <span className="font-semibold text-ink-secondary">
                {result ? `${result.official_max_discount_percent}%` : "—"}
              </span>
            </p>
          </div>

          <div className="lg:col-span-2">
            {isFetching || !result ? (
              <div className="flex h-full min-h-32 items-center justify-center rounded-xl border border-dashed border-line text-sm text-ink-muted">
                Select a treatment to estimate…
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                  {[
                    { label: "List price", value: `₹${result.list_price}` },
                    { label: "Estimated revenue", value: `₹${result.estimated_revenue}` },
                    { label: "Direct costs", value: `₹${result.total_direct_cost}` },
                    { label: "Contribution margin", value: `${result.contribution_margin_percent}%` },
                  ].map((item) => (
                    <div
                      key={item.label}
                      className="rounded-xl border border-line bg-surface-sunken/60 px-3 py-2.5"
                    >
                      <p className="text-[11px] font-medium text-ink-muted">{item.label}</p>
                      <p className="mt-0.5 text-sm font-bold tabular-nums text-ink">{item.value}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-ink-muted">
                  Contribution: <span className="font-medium text-ink-secondary">₹{result.contribution}</span> ·
                  Allocated net profit:{" "}
                  <span className="font-medium text-ink-secondary">₹{result.allocated_net_profit}</span> ·
                  Max allowable discount:{" "}
                  <span className="font-medium text-ink-secondary">
                    {result.max_allowable_discount_percent}%
                  </span>
                </p>
                {result.violates_boundary ? (
                  <ErrorNotice
                    message={result.warnings[0] ?? "Discount breaches the profitability boundary."}
                  />
                ) : (
                  <Callout tone="success">Within configured profitability boundaries.</Callout>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export function FinancePage(): JSX.Element {
  const [createOpen, setCreateOpen] = useState(false);
  const { data, isPending, isError } = useQuery({
    queryKey: ["treatments", false],
    queryFn: () => listTreatments(false),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Finance"
        description="Treatment catalog, costs and discount estimation."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            Create treatment
          </Button>
        }
      />

      <EstimatorCard />

      <Card>
        <CardHeader title="Treatment catalog" description="Every configured service and its direct costs." />
        {isPending ? (
          <SkeletonTable rows={5} cols={6} />
        ) : isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load treatments." />
          </div>
        ) : !data || data.length === 0 ? (
          <EmptyState
            icon={<Tags className="h-5 w-5" />}
            message="No treatments yet. Create one to begin."
          />
        ) : (
          <Table minClassName="min-w-[720px]">
            <THead>
              <TH>Code</TH>
              <TH>Name</TH>
              <TH>Category</TH>
              <TH align="right">List price</TH>
              <TH align="right">Direct costs</TH>
              <TH>Status</TH>
            </THead>
            <tbody>
              {data.map((treatment) => (
                <TR key={treatment.id}>
                  <TD className="font-mono text-xs text-ink-muted">{treatment.treatment_code}</TD>
                  <TD className="font-medium text-ink">{treatment.name}</TD>
                  <TD className="text-ink-secondary">{treatment.service_category ?? "—"}</TD>
                  <TD align="right" className="font-bold tabular-nums text-ink">
                    ₹{treatment.list_price}
                  </TD>
                  <TD align="right" className="tabular-nums text-ink-secondary">
                    ₹
                    {(
                      Number(treatment.therapist_cost) +
                      Number(treatment.material_cost) +
                      Number(treatment.other_direct_cost)
                    ).toFixed(2)}
                  </TD>
                  <TD>
                    <Badge tone={treatment.is_active ? "green" : "slate"} dot={treatment.is_active}>
                      {treatment.is_active ? "active" : "inactive"}
                    </Badge>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <CreateTreatmentModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
