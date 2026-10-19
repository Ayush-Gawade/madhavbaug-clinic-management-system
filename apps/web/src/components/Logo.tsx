/** Brand marks: a leaf monogram and the wordmark used in the shell and login. */

export function LogoMark({ className = "h-9 w-9" }: { className?: string }): JSX.Element {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-700 to-brand-900 shadow-hairline ${className}`}
    >
      <svg viewBox="0 0 32 32" className="h-[62%] w-[62%]" aria-hidden="true">
        <path
          d="M16 5C9.8 8.2 7.5 13 7.5 18a8.5 8.5 0 0 0 17 0c0-5-2.3-9.8-8.5-13z"
          fill="var(--color-accent-300)"
        />
        <path
          d="M16 9.5v13"
          stroke="var(--color-brand-900)"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }): JSX.Element {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <LogoMark />
      {!compact ? (
        <div className="min-w-0 leading-tight">
          <p className="truncate text-[15px] font-bold tracking-tight text-ink">Madhavbaug</p>
          <p className="truncate text-[11px] font-medium tracking-wide text-ink-muted">
            Clinic Management
          </p>
        </div>
      ) : null}
    </div>
  );
}
