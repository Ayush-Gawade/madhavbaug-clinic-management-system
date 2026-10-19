import type { ReactNode } from "react";
import { useEffect } from "react";
import { Inbox, Loader2, TriangleAlert, X } from "lucide-react";

/* ────────────────────────── Inputs ────────────────────────── */

const inputClasses =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-hairline transition placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 disabled:cursor-not-allowed disabled:opacity-60";

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }): JSX.Element {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-semibold text-ink-secondary">
      {children}
    </label>
  );
}

export function TextInput(
  props: React.InputHTMLAttributes<HTMLInputElement>,
): JSX.Element {
  return <input {...props} className={`${inputClasses} ${props.className ?? ""}`} />;
}

export function SelectInput(
  props: React.SelectHTMLAttributes<HTMLSelectElement>,
): JSX.Element {
  return (
    <select
      {...props}
      className={`${inputClasses} select-chevron ${props.className ?? ""}`}
    />
  );
}

export function TextArea(
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
): JSX.Element {
  return <textarea {...props} className={`${inputClasses} resize-y ${props.className ?? ""}`} />;
}

/* ────────────────────────── Button ────────────────────────── */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-600 text-white shadow-hairline hover:bg-brand-700 active:bg-brand-800",
  secondary:
    "border border-line-strong bg-surface text-ink-secondary shadow-hairline hover:bg-surface-sunken hover:text-ink",
  ghost: "text-ink-secondary hover:bg-surface-sunken hover:text-ink",
  danger: "bg-red-600 text-white shadow-hairline hover:bg-red-700 active:bg-red-800",
  link: "text-brand-700 underline-offset-2 hover:underline dark:text-brand-300",
};

export function Button(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    size?: "sm" | "md";
    loading?: boolean;
  },
): JSX.Element {
  const {
    variant = "primary",
    size = "md",
    loading = false,
    className,
    children,
    disabled,
    ...rest
  } = props;
  const sizing =
    size === "sm" ? "h-8 px-3 text-[13px]" : "h-9.5 px-4 text-sm";
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg font-semibold transition duration-150 focus-visible:outline-2 disabled:pointer-events-none disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${sizing} ${className ?? ""}`}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

/* ────────────────────────── Card ──────────────────────────── */

export function Card({
  children,
  className,
  hover = false,
  id,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  id?: string;
}): JSX.Element {
  return (
    <div
      id={id}
      className={`rounded-xl border border-line bg-surface shadow-card ${
        hover ? "transition duration-200 hover:-translate-y-0.5 hover:shadow-card-hover" : ""
      } ${className ?? ""}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 ${
        className ?? ""
      }`}
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {description ? <p className="mt-0.5 text-xs text-ink-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/* ────────────────────────── Badge ─────────────────────────── */

export type BadgeTone =
  | "slate"
  | "green"
  | "amber"
  | "red"
  | "blue"
  | "brand"
  | "accent";

const BADGE_TONES: Record<BadgeTone, string> = {
  slate: "bg-surface-sunken text-ink-secondary ring-line-strong",
  green: "bg-brand-50 text-brand-700 ring-brand-600/25 dark:bg-brand-400/15 dark:text-brand-300 dark:ring-brand-400/30",
  amber:
    "bg-amber-50 text-amber-700 ring-amber-600/25 dark:bg-amber-400/15 dark:text-amber-300 dark:ring-amber-400/30",
  red: "bg-red-50 text-red-700 ring-red-600/25 dark:bg-red-400/15 dark:text-red-300 dark:ring-red-400/30",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/25 dark:bg-sky-400/15 dark:text-sky-300 dark:ring-sky-400/30",
  brand:
    "bg-brand-50 text-brand-700 ring-brand-600/25 dark:bg-brand-400/15 dark:text-brand-300 dark:ring-brand-400/30",
  accent:
    "bg-accent-50 text-accent-800 ring-accent-500/30 dark:bg-accent-400/15 dark:text-accent-300 dark:ring-accent-400/30",
};

export function Badge({
  children,
  tone = "slate",
  dot = false,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone | string;
  dot?: boolean;
  className?: string;
}): JSX.Element {
  const styles = BADGE_TONES[tone as BadgeTone] ?? BADGE_TONES.slate;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${styles} ${
        className ?? ""
      }`}
    >
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/* ────────────────────────── Callout ───────────────────────── */

export type CalloutTone = "info" | "success" | "warning" | "danger";

const CALLOUT_TONES: Record<CalloutTone, string> = {
  info: "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-400/10 dark:text-sky-300 dark:ring-sky-400/25",
  success:
    "bg-brand-50 text-brand-800 ring-brand-200 dark:bg-brand-400/10 dark:text-brand-300 dark:ring-brand-400/25",
  warning:
    "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/25",
  danger:
    "bg-red-50 text-red-800 ring-red-200 dark:bg-red-400/10 dark:text-red-300 dark:ring-red-400/25",
};

export function Callout({
  tone = "info",
  children,
  className,
}: {
  tone?: CalloutTone;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${CALLOUT_TONES[tone]} ${
        className ?? ""
      }`}
    >
      {children}
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }): JSX.Element {
  return (
    <p
      role="alert"
      className="flex items-start gap-2.5 rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-800 ring-1 ring-inset ring-red-200 dark:bg-red-400/10 dark:text-red-300 dark:ring-red-400/25"
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

/* ────────────────────────── Modal ─────────────────────────── */

const MODAL_SIZES = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
} as const;

export function Modal({
  open,
  onClose,
  title,
  children,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  size?: keyof typeof MODAL_SIZES;
}): JSX.Element | null {
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-overlay p-4 backdrop-blur-[2px] animate-fade-in"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`my-auto w-full ${MODAL_SIZES[size]} animate-scale-in rounded-2xl bg-surface shadow-modal`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-ink-muted transition hover:bg-surface-sunken hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[calc(100vh-9rem)] overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

/* ────────────────────── Loading / Empty ───────────────────── */

export function Loading(): JSX.Element {
  return (
    <div
      className="flex items-center justify-center gap-2.5 py-10 text-ink-muted"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      <span className="text-sm">Loading…</span>
    </div>
  );
}

export function EmptyState({
  message,
  icon,
  action,
}: {
  message: string;
  icon?: ReactNode;
  action?: ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-4 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-sunken text-ink-muted">
        {icon ?? <Inbox className="h-5 w-5" aria-hidden="true" />}
      </span>
      <p className="max-w-sm text-sm text-ink-muted">{message}</p>
      {action}
    </div>
  );
}

/* ────────────────────────── Tabs ──────────────────────────── */

export function TabBar({
  tabs,
  active,
  onChange,
}: {
  tabs: readonly string[];
  active: string;
  onChange: (tab: string) => void;
}): JSX.Element {
  return (
    <div
      role="tablist"
      className="-mx-1 flex gap-0.5 overflow-x-auto border-b border-line px-1"
    >
      {tabs.map((tab) => (
        <button
          key={tab}
          role="tab"
          type="button"
          aria-selected={tab === active}
          onClick={() => onChange(tab)}
          className={`relative whitespace-nowrap rounded-t-lg px-3.5 py-2.5 text-sm font-medium transition duration-150 ${
            tab === active
              ? "text-brand-700 after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-brand-600 dark:text-brand-300 dark:after:bg-brand-400"
              : "text-ink-muted hover:bg-surface-sunken/60 hover:text-ink"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

/* ──────────────────────── Pagination ──────────────────────── */

export function Pagination({
  page,
  totalPages,
  total,
  onPageChange,
  itemLabel = "items",
}: {
  page: number;
  totalPages: number;
  total?: number;
  onPageChange: (page: number) => void;
  itemLabel?: string;
}): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 text-sm text-ink-muted">
      <span>
        Page {page} of {totalPages}
        {total !== undefined ? (
          <>
            {" "}
            · {total.toLocaleString("en-IN")} {itemLabel}
          </>
        ) : null}
      </span>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
        >
          Previous
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
