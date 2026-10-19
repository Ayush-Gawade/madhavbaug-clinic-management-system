import { Link } from "react-router-dom";
import { Compass } from "lucide-react";

import { LogoMark } from "@/components/Logo";

export function NotFoundPage(): JSX.Element {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-5 bg-canvas px-4 text-center">
      <LogoMark className="h-14 w-14" />
      <div>
        <p className="text-5xl font-extrabold tracking-tight text-ink">404</p>
        <p className="mt-2 text-sm text-ink-muted">
          This page does not exist — the record may have moved or never existed.
        </p>
      </div>
      <Link
        to="/"
        className="inline-flex h-9 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-semibold text-white shadow-hairline transition hover:bg-brand-700"
      >
        <Compass className="h-4 w-4" />
        Back to dashboard
      </Link>
    </div>
  );
}
