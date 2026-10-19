import { useQuery } from "@tanstack/react-query";

import { MediaAttachment } from "@/components/MediaAttachment";
import { Badge, EmptyState, ErrorNotice, Loading } from "@/components/ui";
import { formatTime } from "@/lib/format";
import { listPatientMessages } from "@/lib/messaging";
import type { WhatsAppMessage } from "@/lib/types";

function deliveryTone(message: WhatsAppMessage): string {
  if (message.direction !== "outbound") return "slate";
  switch (message.delivery_status) {
    case "delivered":
    case "read":
      return "green";
    case "failed":
      return "red";
    case "sent":
      return "brand";
    default:
      return "slate";
  }
}

function messageLabel(message: WhatsAppMessage): string {
  if (message.text_body) return message.text_body;
  if (message.message_type === "unsupported") return "[Unsupported message type]";
  if (message.media_reference) return `[${message.message_type}]`;
  return "[No content]";
}

function MessageBubble({ message }: { message: WhatsAppMessage }): JSX.Element {
  const inbound = message.direction === "inbound";
  return (
    <div className={`flex ${inbound ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 shadow-hairline ${
          inbound
            ? "rounded-bl-md border border-line bg-surface text-ink"
            : "rounded-br-md bg-brand-600 text-white"
        }`}
      >
        <p className="whitespace-pre-wrap break-words text-sm">{messageLabel(message)}</p>
        <MediaAttachment mediaUrl={message.media_url} mediaMimeType={message.media_mime_type} />
        <div
          className={`mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] ${
            inbound ? "text-ink-muted" : "text-brand-100"
          }`}
        >
          <span>{formatTime(message.received_at ?? message.sent_at ?? message.created_at)}</span>
          {message.message_type !== "text" ? (
            <span
              className={`rounded-full px-1.5 py-px font-medium ${
                inbound ? "bg-surface-sunken text-ink-secondary" : "bg-white/15 text-brand-50"
              }`}
            >
              {message.message_type}
            </span>
          ) : null}
          {!inbound && message.delivery_status ? (
            <Badge tone={deliveryTone(message)} className="px-1.5 py-px text-[10px]">
              {message.delivery_status}
            </Badge>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function PatientMessagesTab({ patientId }: { patientId: string }): JSX.Element {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["messages", patientId],
    queryFn: () => listPatientMessages(patientId, { size: 100 }),
  });

  if (isLoading) return <Loading />;
  if (isError) return <ErrorNotice message="Unable to load the conversation." />;

  const messages = data?.items ?? [];
  if (messages.length === 0) {
    return <EmptyState message="No messages exchanged with this patient yet." />;
  }

  return (
    <div className="rounded-xl border border-line bg-surface-sunken/50 p-4 shadow-card">
      <div className="flex max-h-[32rem] flex-col gap-2.5 overflow-y-auto">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </div>
    </div>
  );
}
