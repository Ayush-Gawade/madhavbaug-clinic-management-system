import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Inbox, MessageCircle, Send, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Avatar } from "@/components/Avatar";
import { MediaAttachment } from "@/components/MediaAttachment";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/Skeletons";
import { toast } from "@/components/Toast";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Label,
  SelectInput,
  TextArea,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { listInboxThreads, listPatientMessages, sendReply } from "@/lib/messaging";
import { listTemplates } from "@/lib/schedules";

function timeLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

function ThreadPane({
  patientId,
  patientName,
  onClose,
}: {
  patientId: string;
  patientName: string;
  onClose: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const thread = useQuery({
    queryKey: ["inbox-thread", patientId],
    queryFn: () => listPatientMessages(patientId, { size: 100 }),
  });
  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () => listTemplates(false),
  });
  const approvedTemplates = useMemo(
    () => (templates.data ?? []).filter((template) => template.approved && template.is_active),
    [templates.data],
  );

  const send = useMutation({
    mutationFn: () =>
      sendReply({
        patient_id: patientId,
        body: body.trim() || undefined,
        template_id: templateId || undefined,
      }),
    onSuccess: () => {
      setBody("");
      setTemplateId("");
      setError(null);
      toast.success("Reply sent");
      void queryClient.invalidateQueries({ queryKey: ["inbox-messages"] });
      void queryClient.invalidateQueries({ queryKey: ["inbox-thread"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "session_window_required") {
        setError("Outside the 24-hour Meta session window — send an approved template instead.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to send the reply.");
      }
    },
  });

  const messages = useMemo(() => [...(thread.data?.items ?? [])].reverse(), [thread.data]);

  const canSend = (body.trim().length > 0 || templateId !== "") && !send.isPending;

  return (
    <Card className="flex flex-col overflow-hidden lg:min-h-0">
      {/* Pane header */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar name={patientName} size="sm" />
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-ink">Reply — {patientName}</h2>
            <p className="text-[11px] text-ink-muted">WhatsApp conversation</p>
          </div>
        </div>
        <button
          type="button"
          aria-label="Close conversation"
          onClick={onClose}
          className="rounded-lg p-1.5 text-ink-muted transition hover:bg-surface-sunken hover:text-ink"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Thread */}
      <div className="min-h-48 flex-1 space-y-2.5 overflow-y-auto bg-surface-sunken/40 p-4 lg:max-h-[calc(100vh-27rem)]">
        {thread.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-14 w-2/3" />
            <Skeleton className="ml-auto h-14 w-1/2" />
            <Skeleton className="h-14 w-3/5" />
          </div>
        ) : thread.isError ? (
          <ErrorNotice message="Failed to load the conversation." />
        ) : messages.length === 0 ? (
          <EmptyState icon={<MessageCircle className="h-5 w-5" />} message="No messages in this conversation yet." />
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.direction === "outbound" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 shadow-hairline ${
                  message.direction === "outbound"
                    ? "rounded-br-md bg-brand-600 text-white"
                    : "rounded-bl-md border border-line bg-surface text-ink"
                }`}
              >
                {message.message_type === "template" && message.template_code ? (
                  <p
                    className={`text-[11px] font-medium ${
                      message.direction === "outbound" ? "text-brand-100" : "text-ink-muted"
                    }`}
                  >
                    {message.template_code}
                  </p>
                ) : null}
                {message.text_body ? <p className="text-sm">{message.text_body}</p> : null}
                {!message.text_body && !message.media_url ? (
                  <p className="text-sm">
                    {message.media_mime_type ? `Sent a ${message.media_mime_type}` : "Message"}
                  </p>
                ) : null}
                <MediaAttachment
                  mediaUrl={message.media_url}
                  mediaMimeType={message.media_mime_type}
                />
                <p
                  className={`mt-1 text-[10px] ${
                    message.direction === "outbound" ? "text-brand-100" : "text-ink-muted"
                  }`}
                >
                  {timeLabel(message.created_at)}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Composer */}
      <div className="space-y-3 border-t border-line p-4">
        {error ? (
          <p
            role="alert"
            className="rounded-lg bg-amber-50 px-3 py-2.5 text-sm font-medium text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/25"
          >
            {error}
          </p>
        ) : null}

        <div>
          <Label htmlFor="reply-template">
            Approved template{" "}
            <span className="font-normal text-ink-muted">
              (required outside the 24h window)
            </span>
          </Label>
          <SelectInput
            id="reply-template"
            value={templateId}
            onChange={(event) => setTemplateId(event.target.value)}
          >
            <option value="">Free-form reply (inside 24h window)</option>
            {approvedTemplates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name} — {template.body}
              </option>
            ))}
          </SelectInput>
        </div>
        <div>
          <Label htmlFor="reply-body">Message</Label>
          <TextArea
            id="reply-body"
            rows={3}
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-muted transition hover:text-ink lg:hidden"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </button>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={!canSend} onClick={() => send.mutate()} loading={send.isPending}>
              <Send className="h-4 w-4" />
              {send.isPending ? "Sending…" : "Send reply"}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

export function ReplyInboxPage(): JSX.Element {
  const [openPatientId, setOpenPatientId] = useState<string | null>(null);

  const threads = useQuery({
    queryKey: ["inbox-threads"],
    queryFn: () => listInboxThreads({ size: 100 }),
  });

  const rows = threads.data?.items ?? [];

  const openPatient = openPatientId
    ? {
        id: openPatientId,
        name:
          rows.find((thread) => thread.patient_id === openPatientId)?.patient_name ??
          openPatientId.slice(0, 8),
      }
    : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Replies inbox"
        description="Inbound WhatsApp messages from patients. Open a conversation to reply — free-form inside the 24-hour Meta session window, approved templates outside it."
      />

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(320px,400px)_1fr] lg:h-[calc(100vh-15rem)] lg:min-h-[30rem]">
        <Card className="flex flex-col overflow-hidden lg:min-h-0">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3.5">
            <div>
              <h2 className="text-sm font-semibold text-ink">Patient conversations</h2>
              <p className="text-xs text-ink-muted">Latest reply first</p>
            </div>
            <span className="rounded-full bg-surface-sunken px-2.5 py-1 text-xs font-bold tabular-nums text-ink-secondary">
              {threads.data?.total ?? "—"} patients
            </span>
          </div>

          {threads.isPending ? (
            <div className="space-y-3 p-4">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : threads.isError ? (
            <div className="p-4">
              <ErrorNotice message="Failed to load the inbox." />
            </div>
          ) : rows.length === 0 ? (
            <EmptyState icon={<Inbox className="h-5 w-5" />} message="No inbound patient messages yet." />
          ) : (
            <ul className="min-h-0 flex-1 divide-y divide-line/70 overflow-y-auto lg:max-h-[calc(100vh-20rem)]">
              {rows.map((thread) => {
                const selected = thread.patient_id === openPatientId;
                return (
                  <li
                    key={thread.patient_id}
                    className={`transition-colors ${
                      selected ? "bg-brand-50 dark:bg-brand-400/10" : "hover:bg-surface-sunken/60"
                    }`}
                  >
                    <div className="flex items-start gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-sm font-semibold text-ink">
                            {thread.patient_name ?? thread.patient_id.slice(0, 8)}
                          </p>
                          <span className="shrink-0 text-[11px] text-ink-muted">
                            {thread.latest_at ? formatRelativeTime(thread.latest_at) : ""}
                          </span>
                        </div>
                        <p className="mt-0.5 line-clamp-2 text-sm text-ink-secondary">
                          {thread.latest_text_body ??
                            (thread.latest_media_mime_type
                              ? `Sent a ${thread.latest_media_mime_type}`
                              : "Message")}
                        </p>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <Badge tone="slate">
                            {thread.inbound_count}{" "}
                            {thread.inbound_count === 1 ? "message" : "messages"}
                          </Badge>
                          <Button
                            variant={selected ? "primary" : "secondary"}
                            size="sm"
                            onClick={() => setOpenPatientId(thread.patient_id)}
                          >
                            Reply
                          </Button>
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        {openPatient ? (
          <ThreadPane
            patientId={openPatient.id}
            patientName={openPatient.name}
            onClose={() => setOpenPatientId(null)}
          />
        ) : (
          <Card className="hidden h-full items-center justify-center lg:flex">
            <EmptyState
              icon={<MessageCircle className="h-5 w-5" />}
              message="Select a conversation to read it and reply."
            />
          </Card>
        )}
      </div>
    </div>
  );
}
