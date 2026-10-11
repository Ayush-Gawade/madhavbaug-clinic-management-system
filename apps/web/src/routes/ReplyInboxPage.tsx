import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNotice,
  Label,
  Loading,
  Modal,
  SelectInput,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { listMessages, listPatientMessages, sendReply } from "@/lib/messaging";
import { listPatients } from "@/lib/patients";
import { listTemplates } from "@/lib/schedules";
import type { WhatsAppMessage } from "@/lib/types";

function timeLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

function ThreadModal({
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
    <Modal open onClose={onClose} title={`Reply — ${patientName}`}>
      <div className="space-y-4">
        <div className="max-h-80 space-y-2 overflow-y-auto rounded-md bg-slate-50 p-3">
          {thread.isPending ? (
            <Loading />
          ) : thread.isError ? (
            <ErrorNotice message="Failed to load the conversation." />
          ) : messages.length === 0 ? (
            <EmptyState message="No messages in this conversation yet." />
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.direction === "outbound" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                    message.direction === "outbound"
                      ? "bg-brand-600 text-white"
                      : "border border-slate-200 bg-white text-slate-800"
                  }`}
                >
                  {message.message_type === "template" && message.template_code ? (
                    <p className={`text-[11px] ${message.direction === "outbound" ? "text-white/70" : "text-slate-400"}`}>
                      {message.template_code}
                    </p>
                  ) : null}
                  <p>{message.text_body ?? (message.media_mime_type ? `Sent a ${message.media_mime_type}` : "Message")}</p>
                  <p
                    className={`mt-1 text-[11px] ${
                      message.direction === "outbound" ? "text-white/70" : "text-slate-400"
                    }`}
                  >
                    {timeLabel(message.created_at)}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>

        {error ? (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {error}
          </div>
        ) : null}

        <div className="space-y-3">
          <div>
            <Label htmlFor="reply-template">
              Approved template <span className="font-normal text-slate-500">(required outside the 24h window)</span>
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
            <textarea
              id="reply-body"
              rows={3}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
          </div>
          <div className="flex items-center justify-end gap-3">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button disabled={!canSend} onClick={() => send.mutate()}>
              {send.isPending ? "Sending…" : "Send reply"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

export function ReplyInboxPage(): JSX.Element {
  const [openPatientId, setOpenPatientId] = useState<string | null>(null);

  const patients = useQuery({
    queryKey: ["inbox-patients"],
    queryFn: () => listPatients({ size: 1000 }),
  });
  const messages = useQuery({
    queryKey: ["inbox-messages"],
    queryFn: () => listMessages({ direction: "inbound", size: 100 }),
  });

  const nameMap = useMemo(
    () => new Map((patients.data?.items ?? []).map((patient) => [patient.id, patient.full_name])),
    [patients.data],
  );
  const rows = useMemo(
    () => (messages.data?.items ?? []).filter((m): m is WhatsAppMessage => Boolean(m.patient_id)),
    [messages.data],
  );

  const openPatient = openPatientId
    ? { id: openPatientId, name: nameMap.get(openPatientId) ?? openPatientId.slice(0, 8) }
    : null;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Replies inbox</h1>
        <p className="text-sm text-slate-500">
          Inbound WhatsApp messages from patients. Open a conversation to reply — free-form
          inside the 24-hour Meta session window, approved templates outside it.
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">Patient messages</h2>
            <p className="text-xs text-slate-500">Latest inbound first</p>
          </div>
          <span className="text-sm text-slate-600">{messages.data?.total ?? "—"} inbound</span>
        </div>

        {messages.isPending ? (
          <Loading />
        ) : messages.isError ? (
          <ErrorNotice message="Failed to load the inbox." />
        ) : rows.length === 0 ? (
          <EmptyState message="No inbound patient messages yet." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.map((message) => (
              <li key={message.id}>
                <div className="flex items-center justify-between gap-4 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-800">
                      {nameMap.get(message.patient_id ?? "") ?? message.patient_id?.slice(0, 8)}
                    </p>
                    <p className="truncate text-sm text-slate-600">
                      {message.text_body ?? (message.media_mime_type ? `Sent a ${message.media_mime_type}` : "Message")}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="text-xs text-slate-400">{timeLabel(message.created_at)}</span>
                    <Badge tone="slate">inbound</Badge>
                    <Button variant="ghost" onClick={() => setOpenPatientId(message.patient_id)}>
                      Reply
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {openPatient ? (
        <ThreadModal
          patientId={openPatient.id}
          patientName={openPatient.name}
          onClose={() => setOpenPatientId(null)}
        />
      ) : null}
    </div>
  );
}