import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IndianRupee, Receipt, Wallet } from "lucide-react";
import { useState, type FormEvent } from "react";

import { StatCard } from "@/components/StatCard";
import { Skeleton } from "@/components/Skeletons";
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
  TextInput,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  assignTreatment,
  getFinanceSummary,
  listAssignments,
  listPayments,
  listTreatments,
  recordPayment,
} from "@/lib/finance";
import { formatCurrency, formatDate } from "@/lib/format";

function SummaryCards({
  totalCharges,
  totalPaid,
  outstanding,
}: {
  totalCharges: string;
  totalPaid: string;
  outstanding: string;
}): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatCard
        label="Total charges"
        icon={<Receipt className="h-4 w-4" />}
        value={formatCurrency(totalCharges)}
      />
      <StatCard
        label="Total paid"
        icon={<Wallet className="h-4 w-4" />}
        tone="success"
        value={formatCurrency(totalPaid)}
      />
      <StatCard
        label="Outstanding"
        icon={<IndianRupee className="h-4 w-4" />}
        tone="warning"
        value={formatCurrency(outstanding)}
      />
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
      toast.success("Treatment assigned");
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
    <Card>
      <CardHeader title="Assign treatment" />
      <div className="p-4">
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
          <Button type="submit" disabled={mutation.isPending || !treatmentId} loading={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Assign"}
          </Button>
        </form>
        {error ? (
          <div className="mt-3">
            <ErrorNotice message={error} />
          </div>
        ) : null}
        <div className="mt-4 space-y-2">
          {assignments && assignments.length > 0 ? (
            assignments.map((assignment) => (
              <div
                key={assignment.id}
                className="flex items-center justify-between rounded-lg border border-line bg-surface-sunken/60 px-3.5 py-2.5 text-sm"
              >
                <span className="font-medium text-ink">{assignment.treatment?.name ?? "—"}</span>
                <span className="flex items-center gap-2">
                  {assignment.discount_percent ? (
                    <Badge tone="amber">{assignment.discount_percent}% off</Badge>
                  ) : null}
                  <Badge tone={assignment.status === "active" ? "green" : "slate"} dot>
                    {assignment.status}
                  </Badge>
                </span>
              </div>
            ))
          ) : (
            <p className="text-sm text-ink-muted">No treatments assigned.</p>
          )}
        </div>
      </div>
    </Card>
  );
}

function RecordPaymentForm({
  patientId,
  treatments,
}: {
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
      toast.success("Payment recorded");
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
    <Card>
      <CardHeader title="Record payment" />
      <div className="p-4">
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
          <Button type="submit" disabled={mutation.isPending} loading={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Record"}
          </Button>
        </form>
        {error ? (
          <div className="mt-3">
            <ErrorNotice message={error} />
          </div>
        ) : null}
      </div>
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard label="Total charges" value={<Skeleton className="h-7 w-24" />} />
          <StatCard label="Total paid" value={<Skeleton className="h-7 w-24" />} />
          <StatCard label="Outstanding" value={<Skeleton className="h-7 w-24" />} />
        </div>
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
        <RecordPaymentForm patientId={patientId} treatments={treatments.data ?? []} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Charges" description="Active treatment lines" />
          {summary.data && summary.data.lines.length > 0 ? (
            <ul className="divide-y divide-line">
              {summary.data.lines.map((line) => (
                <li key={line.treatment_id} className="flex items-center justify-between px-5 py-3.5">
                  <div>
                    <p className="text-sm font-medium text-ink">{line.name}</p>
                    <p className="mt-0.5 text-xs text-ink-muted">
                      List ₹{line.list_price}
                      {line.discount_percent ? ` · ${line.discount_percent}% off` : ""}
                    </p>
                  </div>
                  <p className="text-sm font-bold tabular-nums text-ink">{formatCurrency(line.charge)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState message="No active treatment charges." />
          )}
        </Card>

        <Card>
          <CardHeader title="Payments" description="Receipts and refunds" />
          {payments.isPending ? (
            <Loading />
          ) : payments.data && payments.data.length > 0 ? (
            <ul className="divide-y divide-line">
              {payments.data.map((payment) => (
                <li key={payment.id} className="flex items-center justify-between px-5 py-3.5">
                  <div>
                    <p className="text-sm font-medium capitalize text-ink">
                      {payment.payment_type.replace("_", " ")} · {payment.payment_method.replace("_", " ")}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-muted">{formatDate(payment.payment_date)}</p>
                  </div>
                  <p
                    className={`text-sm font-bold tabular-nums ${
                      payment.payment_type === "refund" ? "text-red-600 dark:text-red-400" : "text-ink"
                    }`}
                  >
                    {payment.payment_type === "refund" ? "−" : "+"}
                    {formatCurrency(payment.amount)}
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
