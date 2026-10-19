/**
 * Renders stored inbound/outbound WhatsApp media.
 *
 * Media is served through a short-lived signed URL (``media_url``) so an
 * ``<img>`` element can load it without an Authorization header. Anything that
 * is not an image is offered as a download link. If the bytes are missing
 * server-side (a download that never completed) the image is replaced with a
 * quiet placeholder rather than a broken-image icon.
 */

import { Paperclip } from "lucide-react";
import { useState } from "react";

interface MediaAttachmentProps {
  /** Signed, expiring URL produced by the API (``null`` when there is no media). */
  mediaUrl: string | null;
  mediaMimeType: string | null;
  /** Render a small inline thumbnail for list rows instead of a full preview. */
  compact?: boolean;
}

export function MediaAttachment({
  mediaUrl,
  mediaMimeType,
  compact = false,
}: MediaAttachmentProps): JSX.Element | null {
  const [failed, setFailed] = useState(false);

  if (!mediaUrl) return null;

  if (failed) {
    return (
      <span
        className={
          compact ? "text-xs text-ink-faint" : "mt-2 inline-block text-xs text-ink-faint"
        }
      >
        Media unavailable
      </span>
    );
  }

  if (mediaMimeType?.startsWith("image/")) {
    return (
      <a
        href={mediaUrl}
        target="_blank"
        rel="noreferrer"
        className={
          compact
            ? "block shrink-0 overflow-hidden rounded-lg ring-1 ring-line transition hover:ring-brand-300 dark:hover:ring-brand-700"
            : "mt-2 block overflow-hidden rounded-xl ring-1 ring-line transition hover:ring-brand-300 dark:hover:ring-brand-700"
        }
      >
        <img
          src={mediaUrl}
          alt="Patient attachment"
          onError={() => setFailed(true)}
          className={
            compact
              ? "h-10 w-10 object-cover"
              : "max-h-64 rounded-xl border-0 object-cover"
          }
        />
      </a>
    );
  }

  return (
    <a
      href={mediaUrl}
      target="_blank"
      rel="noreferrer"
      className={
        compact
          ? "inline-flex items-center gap-1 text-xs font-semibold text-brand-700 underline-offset-2 transition hover:underline dark:text-brand-300"
          : "mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-brand-700 underline-offset-2 transition hover:underline dark:text-brand-300"
      }
    >
      <Paperclip className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} />
      {compact ? "Attachment" : "Download attachment"}
    </a>
  );
}
