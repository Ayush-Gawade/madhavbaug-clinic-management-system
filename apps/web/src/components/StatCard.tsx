/** Shared KPI stat card used across every dashboard-style page. */

import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Skeleton } from "@/components/Skeletons";

export type StatTone = "neutral" | "brand" | "warning" | "danger" | "success" | "accent";

const TONE_CLASSES: Record<StatTone, { icon: string; value: string }> = {
  neutral: {
    icon: "bg-surface-sunken text-ink-secondary",
    value: "text-ink",
  },
  brand: {
    icon: "bg-brand-50 text-brand-700 dark:bg-brand-400/15 dark:text-brand-300",
    value: "text-brand-700 dark:text-brand-300",
  },
  warning: {
    icon: "bg-amber-50 text-amber-600 dark:bg-amber-400/15 dark:text-amber-300",
    value: "text-amber-600 dark:text-amber-300",
  },
  danger: {
    icon: "bg-red-50 text-red-600 dark:bg-red-400/15 dark:text-red-300",
    value: "text-red-600 dark:text-red-300",
  },
  success: {
    icon: "bg-emerald-50 text-emerald-600 dark:bg-emerald-400/15 dark:text-emerald-300",
    value: "text-emerald-600 dark:text-emerald-300",
  },
  accent: {
    icon: "bg-accent-50 text-accent-700 dark:bg-accent-400/15 dark:text-accent-300",
    value: "text-accent-700 dark:text-accent-300",
  },
};

export function StatCard({
  label,
  value,
  icon,
  tone = "neutral",
  hint,
  isLoading = false,
  className,
  to,
  ariaLabel,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: StatTone;
  hint?: ReactNode;
  isLoading?: boolean;
  className?: string;
  /** When set, the whole card becomes a link to a pre-filtered destination. */
  to?: string;
  ariaLabel?: string;
}): JSX.Element {
  const toneClasses = TONE_CLASSES[tone];
  const interactive = Boolean(to);

  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{label}</p>
        <span className="flex shrink-0 items-center gap-1.5">
          {interactive ? (
            <ArrowUpRight
              className="h-3.5 w-3.5 text-ink-faint transition duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-brand-600 dark:group-hover:text-brand-300"
              aria-hidden="true"
            />
          ) : null}
          {icon ? (
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${toneClasses.icon}`}
              aria-hidden="true"
            >
              {icon}
            </span>
          ) : null}
        </span>
      </div>
      {isLoading ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <p className={`mt-1.5 text-2xl font-bold tracking-tight ${toneClasses.value}`}>{value}</p>
      )}
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </>
  );

  const base = `rounded-xl border border-line bg-surface p-4 shadow-card sm:p-5 ${className ?? ""}`;

  if (to) {
    return (
      <Link
        to={to}
        aria-label={ariaLabel ?? `View ${label}`}
        className={`group block transition duration-200 hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-card-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 dark:hover:border-brand-700 ${base}`}
      >
        {body}
      </Link>
    );
  }

  return <div className={base}>{body}</div>;
}
