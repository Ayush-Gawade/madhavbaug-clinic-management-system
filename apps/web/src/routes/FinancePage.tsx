import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { Badge, Button, Card, EmptyState, ErrorNotice, Label, Loading, Modal, SelectInput, TextInput } from "@/components/ui";
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
          <Label>Name</Label>
          <TextInput required value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div>
          <Label>Code</Label>
          <TextInput
            required
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="e.g. PK-100"
          />
        </div>
        <div>
          <Label>Service category</Label>
          <TextInput
            value={serviceCategory}
            onChange={(event) => setServiceCategory(event.target.value)}
            placeholder="e.g. Panchakarma"
          />
        </div>
        <div>
          <Label>List price</Label>
          <TextInput
            type="number"
            step="0.01"
            min="0"
            required
            value={listPrice}
            onChange={(event) => setListPrice(event.target.value)}
          />
        </div>
        {error ? <ErrorNotice message={error} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
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
    <Card className="p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-800">Cost estimation</h2>
      {isPending ? (
        <Loading />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-3">
            <div>
              <Label>Treatment</Label>
              <SelectInput value={treatmentId} onChange={(event) => setTreatmentId(event.target.value)}>
                {treatments?.map((treatment) => (
                  <option key={treatment.id} value={treatment.id}>
                    {treatment.name} — ₹{treatment.list_price}
                  </option>
                ))}
              </SelectInput>
            </div>
            <div>
              <Label>Discount {discount}%</Label>
              <input
                type="range"
                min={0}
                max={99}
                step={1}
                value={discount}
                onChange={(event) => setDiscount(Number(event.target.value))}
                className="w-full accent-brand-600"
              />
            </div>
            <div className="text-xs text-slate-500">
              Official max discount at configured boundaries:{" "}
              <span className="font-semibold text-slate-700">
                {result ? `${result.official_max_discount_percent}%` : "—"}
              </span>
            </div>
          </div>

          <div className="lg:col-span-2">
            {isFetching || !result ? (
              <p className="text-sm text-slate-400">Select a treatment to estimate…</p>
            ) : (
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-md bg-slate-50 px-3 py-2">
                    <p className="text-xs text-slate-500">List price</p>
                    <p className="font-semibold">₹{result.list_price}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2">
                    <p className="text-xs text-slate-500">Estimated revenue</p>
                    <p className="font-semibold">₹{result.estimated_revenue}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2">
                    <p className="text-xs text-slate-500">Direct costs</p>
                    <p className="font-semibold">₹{result.total_direct_cost}</p>
                  </div>
                  <div className="rounded-md bg-slate-50 px-3 py-2">
                    <p className="text-xs text-slate-500">Contribution margin</p>
                    <p className="font-semibold">{result.contribution_margin_percent}%</p>
                  </div>
                </div>
                <p className="text-xs text-slate-500">
                  Contribution: ₹{result.contribution} · Allocated net profit:
                  ₹{result.allocated_net_profit} · Max allowable discount:
                  {result.max_allowable_discount_percent}%
                </p>
                {result.violates_boundary ? (
                  <ErrorNotice message={result.warnings[0] ?? "Discount breaches the profitability boundary."} />
                ) : (
                  <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
                    Within configured profitability boundaries.
                  </p>
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Finance</h1>
          <p className="text-sm text-slate-500">Treatment catalog, costs and discount estimation.</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>Create treatment</Button>
      </div>

      <EstimatorCard />

      <Card>
        <h2 className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-800">
          Treatment catalog
        </h2>
        {isPending ? (
          <Loading />
        ) : isError ? (
          <ErrorNotice message="Failed to load treatments." />
        ) : !data || data.length === 0 ? (
          <EmptyState message="No treatments yet. Create one to begin." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3 text-right">List price</th>
                <th className="px-4 py-3 text-right">Direct costs</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((treatment) => (
                <tr key={treatment.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {treatment.treatment_code}
                  </td>
                  <td className="px-4 py-3 font-medium">{treatment.name}</td>
                  <td className="px-4 py-3 text-slate-600">{treatment.service_category ?? "—"}</td>
                  <td className="px-4 py-3 text-right font-semibold">₹{treatment.list_price}</td>
                  <td className="px-4 py-3 text-right text-slate-600">
                    ₹
                    {(
                      Number(treatment.therapist_cost) +
                      Number(treatment.material_cost) +
                      Number(treatment.other_direct_cost)
                    ).toFixed(2)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={treatment.is_active ? "green" : "slate"}>
                      {treatment.is_active ? "active" : "inactive"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <CreateTreatmentModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}