import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";

import { toast } from "@/components/Toast";
import {
  Badge,
  Button,
  Card,
  Callout,
  EmptyState,
  ErrorNotice,
  Loading,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { analyzeMessage, listPatientExtractions } from "@/lib/ai";
import { formatDate } from "@/lib/format";
import type { AIExtraction, AIExtractionStatus } from "@/lib/types";

const STATUS_TONES: Record<AIExtractionStatus, string> = {
  succeeded: "green",
  needs_clarification: "amber",
  skipped: "slate",
  failed: "red",
};

interface ExtractedObservation {
  type?: string;
  value?: number | null;
  unit?: string | null;
  context?: Record<string, unknown> | null;
}

function observationsOf(extraction: AIExtraction): ExtractedObservation[] {
  const raw = extraction.extracted?.observations;
  return Array.isArray(raw) ? (raw as ExtractedObservation[]) : [];
}

function ExtractionCard({
  extraction,
  onReanalyze,
  busy,
}: {
  extraction: AIExtraction;
  onReanalyze: (messageId: string) => void;
  busy: boolean;
}): JSX.Element {
  const observations = observationsOf(extraction);
  return (
    <li className="space-y-2.5 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONES[extraction.status]} dot>
            {extraction.status.replace("_", " ")}
          </Badge>
          <Badge tone="slate">{extraction.modality}</Badge>
          {extraction.intent ? (
            <span className="text-sm font-medium text-ink-secondary">{extraction.intent}</span>
          ) : null}
        </div>
        <span className="text-xs text-ink-muted">{formatDate(extraction.created_at)}</span>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
        <span>
          Model <span className="font-medium text-ink-secondary">{extraction.model}</span>
        </span>
        <span>
          Prompt <span className="font-medium text-ink-secondary">{extraction.prompt_version}</span>
        </span>
        {extraction.confidence ? (
          <span>
            Confidence{" "}
            <span className="font-semibold text-brand-700 dark:text-brand-300">
              {Number(extraction.confidence).toFixed(2)}
            </span>
          </span>
        ) : null}
        <span>Observations created {extraction.observations_created}</span>
      </div>

      {extraction.clarification_question ? (
        <Callout tone="warning">{extraction.clarification_question}</Callout>
      ) : null}

      {extraction.error_message ? <Callout tone="danger">{extraction.error_message}</Callout> : null}

      {observations.length > 0 ? (
        <ul className="space-y-1 rounded-lg bg-surface-sunken px-3 py-2.5 text-sm">
          {observations.map((observation, index) => (
            <li key={`${observation.type}-${index}`} className="text-ink-secondary">
              <span className="capitalize font-medium text-ink">
                {observation.type?.replace("_", " ")}
              </span>
              {observation.value != null ? `: ${observation.value}` : ""}
              {observation.unit ? ` ${observation.unit}` : ""}
              {observation.context
                ? ` (${Object.entries(observation.context)
                    .map(([key, value]) => `${key} ${value}`)
                    .join(", ")})`
                : ""}
            </li>
          ))}
        </ul>
      ) : null}

      {extraction.message_id ? (
        <div>
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => onReanalyze(extraction.message_id as string)}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {busy ? "Re-analyzing…" : "Re-analyze message"}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

export function PatientAIInsightsTab({ patientId }: { patientId: string }): JSX.Element {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["ai-extractions", patientId],
    queryFn: () => listPatientExtractions(patientId, { size: 50 }),
  });

  const mutation = useMutation({
    mutationFn: (messageId: string) => analyzeMessage(messageId),
    onSuccess: () => {
      setError(null);
      toast.success("Message queued for re-analysis");
      void queryClient.invalidateQueries({ queryKey: ["ai-extractions", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["observations", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to re-analyze the message."),
  });

  if (isPending) return <Loading />;
  if (isError) return <ErrorNotice message="Failed to load AI extractions." />;

  const extractions = data?.items ?? [];
  if (extractions.length === 0) {
    return (
      <EmptyState
        icon={<Sparkles className="h-5 w-5" />}
        message="No AI extractions for this patient yet."
      />
    );
  }

  return (
    <div className="space-y-4">
      {error ? <ErrorNotice message={error} /> : null}
      <Card>
        <ul className="divide-y divide-line">
          {extractions.map((extraction) => (
            <ExtractionCard
              key={extraction.id}
              extraction={extraction}
              onReanalyze={(messageId) => mutation.mutate(messageId)}
              busy={mutation.isPending}
            />
          ))}
        </ul>
      </Card>
    </div>
  );
}
