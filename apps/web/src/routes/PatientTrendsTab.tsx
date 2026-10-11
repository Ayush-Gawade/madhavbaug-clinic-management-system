import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { LineChart } from "@/components/LineChart";
import { Card, EmptyState, ErrorNotice, Label, Loading, SelectInput } from "@/components/ui";
import { getObservationTrends } from "@/lib/analytics";
import type { TrendGranularity } from "@/lib/types";

const TYPE_OPTIONS = [
  { type: "blood_glucose", label: "Blood glucose" },
  { type: "weight", label: "Weight" },
  { type: "pulse", label: "Pulse" },
  { type: "waist", label: "Waist" },
];

export function PatientTrendsTab({ patientId }: { patientId: string }): JSX.Element {
  const [observationType, setObservationType] = useState(TYPE_OPTIONS[0].type);
  const [granularity, setGranularity] = useState<TrendGranularity>("day");

  const { data, isPending, isError } = useQuery({
    queryKey: ["patient-trends", patientId, observationType, granularity],
    queryFn: () => getObservationTrends(patientId, { observation_type: observationType, granularity }),
  });

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-end gap-3 p-4">
        <div>
          <Label>Metric</Label>
          <SelectInput
            className="w-48"
            value={observationType}
            onChange={(event) => setObservationType(event.target.value)}
          >
            {TYPE_OPTIONS.map((option) => (
              <option key={option.type} value={option.type}>
                {option.label}
              </option>
            ))}
          </SelectInput>
        </div>
        <div>
          <Label>Granularity</Label>
          <SelectInput
            className="w-40"
            value={granularity}
            onChange={(event) => setGranularity(event.target.value as TrendGranularity)}
          >
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
          </SelectInput>
        </div>
      </Card>

      <Card className="p-4">
        {isPending ? (
          <Loading />
        ) : isError || !data ? (
          <ErrorNotice message="Failed to load trends." />
        ) : data.points.length === 0 ? (
          <EmptyState message="No observations recorded in this range." />
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-700">
                {data.observation_type.replace("_", " ")} {data.unit ? `(${data.unit})` : ""}
              </p>
              <p className="text-xs text-slate-400">
                {data.date_from} → {data.date_to}
                {data.missing_buckets > 0 ? ` · ${data.missing_buckets} gaps` : ""}
              </p>
            </div>
            <LineChart
              points={data.points.map((point) => ({
                label: point.bucket,
                value: Number(point.average_value),
              }))}
              unit={data.unit}
              ariaLabel={`${data.observation_type} trend`}
            />
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2">Bucket</th>
                  <th className="py-2">Average</th>
                  <th className="py-2">Latest</th>
                  <th className="py-2">Verified</th>
                  <th className="py-2">Reported</th>
                </tr>
              </thead>
              <tbody>
                {data.points.map((point) => (
                  <tr key={point.bucket} className="border-b border-slate-50">
                    <td className="py-2">{point.bucket}</td>
                    <td className="py-2">{point.average_value}</td>
                    <td className="py-2">{point.latest_value ?? "—"}</td>
                    <td className="py-2">{point.verified_count}</td>
                    <td className="py-2">{point.patient_reported_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
