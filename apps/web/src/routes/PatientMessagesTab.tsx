import { useQuery } from "@tanstack/react-query";

import { MediaAttachment } from "@/components/MediaAttachment";
import { Badge, Card, EmptyState, ErrorNotice, Loading } from "@/components/ui";
import { formatDate } from "@/lib/format";
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
        className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
          inbound ? "bg-slate-100 text-slate-800" : "bg-brand-50 text-brand-900"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{messageLabel(message)}</p>
        <MediaAttachment mediaUrl={message.media_url} mediaMimeType={message.media_mime_type} />
        <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-500">
          <span>{formatDate(message.received_at ?? message.sent_at ?? message.created_at)}</span>
          {message.message_type !== "text" ? (
            <Badge tone="slate">{message.message_type}</Badge>
          ) : null}
          {!inbound && message.delivery_status ? (
            <Badge tone={deliveryTone(message)}>{message.delivery_status}</Badge>
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
    <Card className="p-4">
      <div className="flex max-h-[32rem] flex-col gap-2 overflow-y-auto">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </div>
    </Card>
  );
}
