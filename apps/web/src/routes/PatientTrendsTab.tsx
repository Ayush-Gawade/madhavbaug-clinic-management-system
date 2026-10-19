import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { LineChart } from "@/components/LineChart";
import { SkeletonTable } from "@/components/Skeletons";
import { TD, TH, THead, TR, Table } from "@/components/Table";
import { Card, CardHeader, EmptyState, ErrorNotice, Label, SelectInput } from "@/components/ui";
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
      <Card>
        <div className="flex flex-wrap items-end gap-3 p-4">
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
        </div>
      </Card>

      <Card>
        <CardHeader
          title={data ? data.observation_type.replace("_", " ") : "Trend"}
          description={data && data.unit ? `${data.unit} — ${data.date_from} → ${data.date_to}` : undefined}
        />
        <div className="p-4">
          {isPending ? (
            <SkeletonTable rows={5} cols={5} />
          ) : isError || !data ? (
            <ErrorNotice message="Failed to load trends." />
          ) : data.points.length === 0 ? (
            <EmptyState message="No observations recorded in this range." />
          ) : (
            <div className="space-y-5">
              {data.missing_buckets > 0 ? (
                <p className="text-xs text-ink-muted">{data.missing_buckets} missing buckets in range</p>
              ) : null}
              <LineChart
                points={data.points.map((point) => ({
                  label: point.bucket,
                  value: Number(point.average_value),
                }))}
                unit={data.unit}
                ariaLabel={`${data.observation_type} trend`}
              />
              <Table minClassName="min-w-[520px]">
                <THead>
                  <TH>Bucket</TH>
                  <TH align="right">Average</TH>
                  <TH align="right">Latest</TH>
                  <TH align="right">Verified</TH>
                  <TH align="right">Reported</TH>
                </THead>
                <tbody>
                  {data.points.map((point) => (
                    <TR key={point.bucket}>
                      <TD className="font-medium text-ink">{point.bucket}</TD>
                      <TD align="right" className="tabular-nums">{point.average_value}</TD>
                      <TD align="right" className="tabular-nums">{point.latest_value ?? "—"}</TD>
                      <TD align="right" className="tabular-nums">{point.verified_count}</TD>
                      <TD align="right" className="tabular-nums">{point.patient_reported_count}</TD>
                    </TR>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
