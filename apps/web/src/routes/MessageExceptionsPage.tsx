import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, EmptyState, ErrorNotice, Loading, Modal } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { detailSummary, reasonLabel, statusTone } from "@/lib/messageExceptions";
import { listExceptions, resolveException } from "@/lib/messaging";
import type { MessageException } from "@/lib/types";

const STATUS_OPTIONS = ["open", "resolved", "dismissed"] as const;

function ExceptionReviewModal({
  exceptionId,
  onClose,
}: {
  exceptionId: string;
  onClose: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const exception = useQuery({
    queryKey: ["message-exceptions", "detail", exceptionId],
    queryFn: async () => {
      const page = await listExceptions({ page: 1, size: 100 });
      const found = page.items.find((item) => item.id === exceptionId);
      if (!found) throw new Error("Exception not found.");
      return found;
    },
  });

  const onSuccess = (): void => {
    void queryClient.invalidateQueries({ queryKey: ["message-exceptions"] });
    onClose();
  };
  const resolve = useMutation({
    mutationFn: () => resolveException(exceptionId, { resolved: true, notes: notes || null }),
    onSuccess,
  });
  const dismiss = useMutation({
    mutationFn: () => resolveException(exceptionId, { resolved: false, notes: notes || null }),
    onSuccess,
  });

  const item = exception.data;
  const closed = item?.status === "resolved" || item?.status === "dismissed";
  const errors = [resolve.error, dismiss.error].filter(
    (error): error is Error => error instanceof Error,
  );

  return (
    <Modal open onClose={onClose} title="Review message exception">
      {exception.isPending ? (
        <Loading />
      ) : exception.isError || !item ? (
        <ErrorNotice message="Failed to load the exception." />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(item.status)}>{item.status}</Badge>
            <span className="text-xs text-slate-500">created {formatDate(item.created_at)}</span>
          </div>

          <p className="text-sm font-medium text-slate-800">{reasonLabel(item.reason)}</p>

          <dl className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Details</dt>
              <dd className="text-slate-700">{detailSummary(item.details)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Linked message</dt>
              <dd className="font-mono text-xs text-slate-600">
                {item.message_id ? item.message_id.slice(0, 8) : "—"}
              </dd>
            </div>
          </dl>

          {!closed ? (
            <div className="space-y-3 border-t border-slate-200 pt-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="exception-notes">
                  Notes
                </label>
                <textarea
                  id="exception-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-brand-500 focus:outline-none"
                  placeholder="How was this resolved? (optional)"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={resolve.isPending}
                  onClick={() => resolve.mutate()}
                  className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
                >
                  Resolve
                </button>
                <button
                  type="button"
                  disabled={dismiss.isPending}
                  onClick={() => dismiss.mutate()}
                  className="rounded-md border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Dismiss
                </button>
              </div>
              {errors.map((error, index) => (
                <ErrorNotice
                  key={index}
                  message={error instanceof ApiError ? error.message : "Action failed."}
                />
              ))}
            </div>
          ) : (
            <p className="border-t border-slate-200 pt-3 text-xs text-slate-500">
              {item.resolution_notes ? `Note: ${item.resolution_notes}` : "No notes recorded."}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}

export function MessageExceptionsPage(): JSX.Element {
  const [status, setStatus] = useState<string>("open");
  const [page, setPage] = useState(1);
  const [reviewId, setReviewId] = useState<string | null>(null);

  const exceptions = useQuery({
    queryKey: ["message-exceptions", status, page],
    queryFn: () => listExceptions({ status: status || undefined, page, size: 20 }),
  });

  const totalPages = exceptions.data ? Math.max(1, Math.ceil(exceptions.data.total / 20)) : 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Message exceptions</h1>
        <p className="text-sm text-slate-500">
          Inbound messages that could not be matched to a patient or follow-up, held for review.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Review queue</h2>
          <select
            aria-label="Filter by status"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        {exceptions.isPending ? (
          <Loading />
        ) : exceptions.isError ? (
          <ErrorNotice message="Failed to load message exceptions." />
        ) : !exceptions.data || exceptions.data.items.length === 0 ? (
          <EmptyState message="No message exceptions for this filter." />
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Reason</th>
                <th className="px-4 py-3">Details</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {exceptions.data.items.map((item: MessageException) => (
                <tr key={item.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 text-slate-600">{formatDate(item.created_at)}</td>
                  <td className="px-4 py-3 text-slate-700">{reasonLabel(item.reason)}</td>
                  <td className="px-4 py-3 text-slate-600">{detailSummary(item.details)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setReviewId(item.id)}
                      className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
          <span>
            Page {page} of {totalPages} · {exceptions.data?.total ?? 0} total
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {reviewId ? (
        <ExceptionReviewModal exceptionId={reviewId} onClose={() => setReviewId(null)} />
      ) : null}
    </div>
  );
}
