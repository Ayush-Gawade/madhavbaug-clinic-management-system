/** Initials avatar with a deterministic, brand-aligned tint. */

import { initialsOf } from "@/lib/format";

const TONES = [
  "bg-brand-100 text-brand-800 dark:bg-brand-400/20 dark:text-brand-200",
  "bg-accent-100 text-accent-800 dark:bg-accent-400/20 dark:text-accent-200",
  "bg-sky-100 text-sky-800 dark:bg-sky-400/20 dark:text-sky-200",
  "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/20 dark:text-emerald-200",
  "bg-amber-100 text-amber-800 dark:bg-amber-400/20 dark:text-amber-200",
  "bg-violet-100 text-violet-800 dark:bg-violet-400/20 dark:text-violet-200",
];

const SIZES = {
  sm: "h-8 w-8 text-[11px]",
  md: "h-10 w-10 text-[13px]",
  lg: "h-14 w-14 text-lg",
  xl: "h-20 w-20 text-2xl",
} as const;

function toneFor(name: string): string {
  let sum = 0;
  for (const char of name) sum += char.charCodeAt(0);
  return TONES[sum % TONES.length];
}

export function Avatar({
  name,
  size = "md",
  className,
}: {
  name: string | null | undefined;
  size?: keyof typeof SIZES;
  className?: string;
}): JSX.Element {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-bold tracking-tight ${SIZES[size]} ${toneFor(
        name ?? "?",
      )} ${className ?? ""}`}
      aria-hidden="true"
    >
      {initialsOf(name)}
    </span>
  );
}
