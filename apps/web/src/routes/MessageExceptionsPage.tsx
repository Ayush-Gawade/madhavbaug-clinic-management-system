import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { SkeletonTable } from "@/components/Skeletons";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorNotice,
  Label,
  Loading,
  Modal,
  Pagination,
  SelectInput,
  TextArea,
} from "@/components/ui";
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
            <Badge tone={statusTone(item.status)} dot={item.status === "open"}>
              {item.status}
            </Badge>
            <span className="text-xs text-ink-muted">created {formatDate(item.created_at)}</span>
          </div>

          <p className="rounded-lg bg-surface-sunken px-3.5 py-3 text-sm font-medium text-ink">
            {reasonLabel(item.reason)}
          </p>

          <dl className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-line px-3.5 py-2.5">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
                Details
              </dt>
              <dd className="mt-0.5 text-sm text-ink-secondary">{detailSummary(item.details)}</dd>
            </div>
            <div className="rounded-lg border border-line px-3.5 py-2.5">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
                Linked message
              </dt>
              <dd className="mt-0.5 font-mono text-xs text-ink-secondary">
                {item.message_id ? item.message_id.slice(0, 8) : "—"}
              </dd>
            </div>
          </dl>

          {!closed ? (
            <div className="space-y-3 border-t border-line pt-4">
              <div>
                <Label htmlFor="exception-notes">Notes</Label>
                <TextArea
                  id="exception-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  placeholder="How was this resolved? (optional)"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button disabled={resolve.isPending} onClick={() => resolve.mutate()}>
                  Resolve
                </Button>
                <Button
                  variant="secondary"
                  disabled={dismiss.isPending}
                  onClick={() => dismiss.mutate()}
                >
                  Dismiss
                </Button>
              </div>
              {errors.map((error, index) => (
                <ErrorNotice
                  key={index}
                  message={error instanceof ApiError ? error.message : "Action failed."}
                />
              ))}
            </div>
          ) : (
            <p className="border-t border-line pt-3 text-xs text-ink-muted">
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
    <div className="space-y-6">
      <PageHeader
        title="Message exceptions"
        description="Inbound messages that could not be matched to a patient or follow-up, held for review."
      />

      <Card>
        <CardHeader
          title="Review queue"
          actions={
            <SelectInput
              aria-label="Filter by status"
              className="w-40"
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
            </SelectInput>
          }
        />

        {exceptions.isPending ? (
          <SkeletonTable rows={5} cols={5} />
        ) : exceptions.isError ? (
          <div className="p-4">
            <ErrorNotice message="Failed to load message exceptions." />
          </div>
        ) : !exceptions.data || exceptions.data.items.length === 0 ? (
          <EmptyState
            icon={<Inbox className="h-5 w-5" />}
            message="No message exceptions for this filter."
          />
        ) : (
          <Table minClassName="min-w-[680px]">
            <THead>
              <TH>Created</TH>
              <TH>Reason</TH>
              <TH>Details</TH>
              <TH>Status</TH>
              <TH align="right" />
            </THead>
            <tbody>
              {exceptions.data.items.map((item: MessageException) => (
                <TR key={item.id}>
                  <TD className="whitespace-nowrap text-ink-secondary">
                    {formatDate(item.created_at)}
                  </TD>
                  <TD className="font-medium text-ink">{reasonLabel(item.reason)}</TD>
                  <TD className="text-ink-secondary">{detailSummary(item.details)}</TD>
                  <TD>
                    <Badge tone={statusTone(item.status)} dot={item.status === "open"}>
                      {item.status}
                    </Badge>
                  </TD>
                  <TD align="right">
                    <Button variant="secondary" size="sm" onClick={() => setReviewId(item.id)}>
                      Review
                    </Button>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        )}

        <Pagination
          page={page}
          totalPages={totalPages}
          total={exceptions.data?.total ?? 0}
          itemLabel="exceptions"
          onPageChange={setPage}
        />
      </Card>

      {reviewId ? (
        <ExceptionReviewModal exceptionId={reviewId} onClose={() => setReviewId(null)} />
      ) : null}
    </div>
  );
}
