import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Button, Card, EmptyState, ErrorNotice, Loading } from "@/components/ui";
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
    <li className="px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge tone={STATUS_TONES[extraction.status]}>
            {extraction.status.replace("_", " ")}
          </Badge>
          <Badge tone="slate">{extraction.modality}</Badge>
          {extraction.intent ? <span className="text-sm text-slate-600">{extraction.intent}</span> : null}
        </div>
        <span className="text-xs text-slate-400">{formatDate(extraction.created_at)}</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>
          Model: <span className="text-slate-700">{extraction.model}</span>
        </span>
        <span>
          Prompt: <span className="text-slate-700">{extraction.prompt_version}</span>
        </span>
        {extraction.confidence ? <span>Confidence: {Number(extraction.confidence).toFixed(2)}</span> : null}
        <span>Observations created: {extraction.observations_created}</span>
      </div>

      {extraction.clarification_question ? (
        <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {extraction.clarification_question}
        </p>
      ) : null}

      {extraction.error_message ? (
        <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{extraction.error_message}</p>
      ) : null}

      {observations.length > 0 ? (
        <ul className="mt-2 space-y-1 text-sm">
          {observations.map((observation, index) => (
            <li key={`${observation.type}-${index}`} className="text-slate-700">
              <span className="capitalize">{observation.type?.replace("_", " ")}</span>
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
        <div className="mt-3">
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => onReanalyze(extraction.message_id as string)}
          >
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
      void queryClient.invalidateQueries({ queryKey: ["ai-extractions", patientId] });
      void queryClient.invalidateQueries({ queryKey: ["observations", patientId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Unable to re-analyze the message."),
  });

  if (isPending) return <Loading />;
  if (isError) return <ErrorNotice message="Failed to load AI extractions." />;

  const extractions = data?.items ?? [];
  if (extractions.length === 0) {
    return <EmptyState message="No AI extractions for this patient yet." />;
  }

  return (
    <div className="space-y-4">
      {error ? <ErrorNotice message={error} /> : null}
      <Card>
        <ul className="divide-y divide-slate-100">
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
