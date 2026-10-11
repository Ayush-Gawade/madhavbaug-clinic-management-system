import type { ReactNode } from "react";

const inputClasses =
  "w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

export function Label({ children }: { children: ReactNode }): JSX.Element {
  return (
    <label className="mb-1 block text-sm font-medium text-slate-700">{children}</label>
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
  return <select {...props} className={`${inputClasses} ${props.className ?? ""}`} />;
}

export function Button(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" },
): JSX.Element {
  const { variant = "primary", className, ...rest } = props;
  const styles =
    variant === "primary"
      ? "bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-60"
      : "border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-60";
  return (
    <button
      {...rest}
      className={`rounded-md px-4 py-2 text-sm font-semibold ${styles} ${className ?? ""}`}
    />
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }): JSX.Element {
  return (
    <div className={`rounded-lg border border-slate-200 bg-white ${className ?? ""}`}>
      {children}
    </div>
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: string }): JSX.Element {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    green: "bg-green-100 text-green-700",
    amber: "bg-amber-100 text-amber-700",
    red: "bg-red-100 text-red-700",
    brand: "bg-brand-50 text-brand-700",
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone] ?? tones.slate}`}>
      {children}
    </span>
  );
}

export function Modal({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}): JSX.Element | null {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-400 hover:text-slate-600"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }): JSX.Element {
  return (
    <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </p>
  );
}

export function Loading(): JSX.Element {
  return <p className="py-6 text-center text-sm text-slate-400">Loading…</p>;
}

export function EmptyState({ message }: { message: string }): JSX.Element {
  return <p className="py-6 text-center text-sm text-slate-400">{message}</p>;
}