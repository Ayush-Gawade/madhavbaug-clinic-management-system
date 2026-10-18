/**
 * Renders stored inbound/outbound WhatsApp media.
 *
 * Media is served through a short-lived signed URL (``media_url``) so an
 * ``<img>`` element can load it without an Authorization header. Anything that
 * is not an image is offered as a download link. If the bytes are missing
 * server-side (a download that never completed) the image is replaced with a
 * quiet placeholder rather than a broken-image icon.
 */

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
          compact ? "text-xs text-slate-400" : "mt-2 inline-block text-xs text-slate-400"
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
        className={compact ? "block shrink-0" : "mt-2 block"}
      >
        <img
          src={mediaUrl}
          alt="Patient attachment"
          onError={() => setFailed(true)}
          className={
            compact
              ? "h-10 w-10 rounded border border-slate-200 object-cover"
              : "max-h-64 rounded-md border border-slate-200"
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
          ? "text-xs font-medium text-brand-700 underline"
          : "mt-2 inline-block text-xs font-medium text-brand-700 underline"
      }
    >
      {compact ? "Attachment" : "Download attachment"}
    </a>
  );
}
