import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Badge, Button, Card, EmptyState, ErrorNotice, Label, Loading, SelectInput, TextInput } from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  assignTreatment,
  getFinanceSummary,
  listAssignments,
  listPayments,
  recordPayment,
} from "@/lib/finance";
import { formatDate } from "@/lib/format";
import { listTreatments } from "@/lib/finance";

function SummaryCards({ totalCharges, totalPaid, outstanding }: {
  totalCharges: string;
  totalPaid: string;
  outstanding: string;
}): JSX.Element {
  const cards = [
    { label: "Total charges", value: totalCharges, tone: "text-slate-900" },
    { label: "Total paid", value: totalPaid, tone: "text-green-700" },
    { label: "Outstanding", value: outstanding, tone: "text-amber-700" },
  ];
  return (
    <div className="grid grid-cols-3 gap-4">
      {cards.map((card) => (
        <div key={card.label} className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{card.label}</p>
          <p className={`mt-1 text-xl font-semibold ${card.tone}`}>₹{card.value}</p>
        </div>
      ))}
    </div>
  );
}

function AssignTreatmentForm({ patientId }: { patientId: string }): JSX.Element {
  const queryClient = useQueryClient();
  const [treatmentId, setTreatmentId] = useState("");
  const [discount, setDiscount] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const { data: treatments } = useQuery({
    queryKey: ["treatments", true],
    queryFn: () => listTreatments(true),
  });
  const { data: assignments } = useQuery({
    queryKey: ["assignments", patientId],
    queryFn: () => listAssignments(patientId),
  });

  const mutation = useMutation({
    mutationFn: () =>
      assignTreatment(patientId, {
        treatment_id: treatmentId,
        discount_percent: Number(discount),
      }),
    onSuccess: () => {
      setDiscount("0");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["assignments", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["finance-summary", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to assign treatment."),
  });

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    if (!treatmentId) return;
    setError(null);
    mutation.mutate();
  };

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Assign treatment</h3>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <div className="min-w-52 flex-1">
          <Label>Treatment</Label>
          <SelectInput
            value={treatmentId}
            onChange={(event) => setTreatmentId(event.target.value)}
            required
          >
            <option value="">Select…</option>
            {treatments?.map((treatment) => (
              <option key={treatment.id} value={treatment.id}>
                {treatment.name} — ₹{treatment.list_price}
              </option>
            ))}
          </SelectInput>
        </div>
        <div>
          <Label>Discount %</Label>
          <TextInput
            type="number"
            min="0"
            max="99"
            className="w-24"
            value={discount}
            onChange={(event) => setDiscount(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={mutation.isPending || !treatmentId}>
          {mutation.isPending ? "Saving…" : "Assign"}
        </Button>
      </form>
      {error ? <div className="mt-3"><ErrorNotice message={error} /></div> : null}
      <div className="mt-4 space-y-2">
        {assignments && assignments.length > 0 ? (
          assignments.map((assignment) => (
            <div
              key={assignment.id}
              className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm"
            >
              <span className="font-medium">{assignment.treatment?.name ?? "—"}</span>
              <span className="flex items-center gap-2">
                {assignment.discount_percent ? (
                  <Badge tone="amber">{assignment.discount_percent}% off</Badge>
                ) : null}
                <Badge tone={assignment.status === "active" ? "green" : "slate"}>{assignment.status}</Badge>
              </span>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-400">No treatments assigned.</p>
        )}
      </div>
    </Card>
  );
}

function RecordPaymentForm({ patientId, treatments }: {
  patientId: string;
  treatments: { id: string; name: string }[];
}): JSX.Element {
  const queryClient = useQueryClient();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [treatmentId, setTreatmentId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      recordPayment(patientId, {
        amount: Number(amount),
        payment_method: method,
        treatment_id: treatmentId || null,
      }),
    onSuccess: () => {
      setAmount("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["payments", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["finance-summary", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to record payment."),
  });

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  };

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-800">Record payment</h3>
      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <div>
          <Label>Amount</Label>
          <TextInput
            type="number"
            step="0.01"
            min="0"
            className="w-32"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            required
          />
        </div>
        <div>
          <Label>Method</Label>
          <SelectInput className="w-36" value={method} onChange={(event) => setMethod(event.target.value)}>
            {["cash", "card", "upi", "bank_transfer", "cheque", "other"].map((item) => (
              <option key={item} value={item}>
                {item.replace("_", " ")}
              </option>
            ))}
          </SelectInput>
        </div>
        <div>
          <Label>Treatment (optional)</Label>
          <SelectInput className="w-44" value={treatmentId} onChange={(event) => setTreatmentId(event.target.value)}>
            <option value="">—</option>
            {treatments.map((treatment) => (
              <option key={treatment.id} value={treatment.id}>
                {treatment.name}
              </option>
            ))}
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

export function PatientFinanceTab({ patientId }: { patientId: string }): JSX.Element {
  const summary = useQuery({
    queryKey: ["finance-summary", patientId],
    queryFn: () => getFinanceSummary(patientId),
  });
  const payments = useQuery({
    queryKey: ["payments", patientId],
    queryFn: () => listPayments(patientId),
  });
  const treatments = useQuery({
    queryKey: ["treatments", true],
    queryFn: () => listTreatments(true),
  });

  return (
    <div className="space-y-4">
      {summary.isPending ? (
        <Loading />
      ) : summary.isError || !summary.data ? (
        <ErrorNotice message="Failed to load financial summary." />
      ) : (
        <SummaryCards
          totalCharges={summary.data.total_charges}
          totalPaid={summary.data.total_paid}
          outstanding={summary.data.outstanding}
        />
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <AssignTreatmentForm patientId={patientId} />
        <RecordPaymentForm
          patientId={patientId}
          treatments={treatments.data ?? []}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-800">
            Charges
          </h3>
          {summary.data && summary.data.lines.length > 0 ? (
            <ul className="divide-y divide-slate-100">
              {summary.data.lines.map((line) => (
                <li key={line.treatment_id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <div>
                    <p className="font-medium">{line.name}</p>
                    <p className="text-xs text-slate-500">
                      List ₹{line.list_price}
                      {line.discount_percent ? ` · ${line.discount_percent}% off` : ""}
                    </p>
                  </div>
                  <p className="font-semibold">₹{line.charge}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="No active treatment charges." />
          )}
        </Card>

        <Card>
          <h3 className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-800">
            Payments
          </h3>
          {payments.isPending ? (
            <Loading />
          ) : payments.data && payments.data.length > 0 ? (
            <ul className="divide-y divide-slate-100">
              {payments.data.map((payment) => (
                <li key={payment.id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <div>
                    <p className="font-medium capitalize">{payment.payment_type.replace("_", " ")} · {payment.payment_method.replace("_", " ")}</p>
                    <p className="text-xs text-slate-500">{formatDate(payment.payment_date)}</p>
                  </div>
                  <p className={`font-semibold ${payment.payment_type === "refund" ? "text-red-600" : "text-slate-900"}`}>
                    {payment.payment_type === "refund" ? "−" : "+"}₹{payment.amount}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="No payments recorded." />
          )}
        </Card>
      </div>
    </div>
  );
}