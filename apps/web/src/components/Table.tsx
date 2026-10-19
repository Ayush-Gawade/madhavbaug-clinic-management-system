/** Shared table primitives — one consistent look for every data table. */

import type { ReactNode } from "react";

export function Table({
  children,
  minClassName = "min-w-[640px]",
}: {
  children: ReactNode;
  minClassName?: string;
}): JSX.Element {
  return (
    <div className="w-full overflow-x-auto">
      <table className={`w-full text-left text-sm ${minClassName}`}>{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }): JSX.Element {
  return (
    <thead className="bg-surface-sunken/60">
      <tr className="border-b border-line">{children}</tr>
    </thead>
  );
}

export function TH({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
}): JSX.Element {
  const alignment =
    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <th
      scope="col"
      className={`whitespace-nowrap px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted ${alignment} ${
        className ?? ""
      }`}
    >
      {children}
    </th>
  );
}

export function TR({
  children,
  className,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}): JSX.Element {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-line/70 transition-colors last:border-0 ${
        onClick ? "cursor-pointer" : ""
      } hover:bg-surface-sunken/50 ${className ?? ""}`}
    >
      {children}
    </tr>
  );
}

export function TD({
  children,
  align = "left",
  className,
  colSpan,
}: {
  children?: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  colSpan?: number;
}): JSX.Element {
  const alignment =
    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <td colSpan={colSpan} className={`px-5 py-3.5 align-middle ${alignment} ${className ?? ""}`}>
      {children}
    </td>
  );
}
