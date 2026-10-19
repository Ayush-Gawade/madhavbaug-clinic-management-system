import { Navigate, Outlet, useLocation } from "react-router-dom";

import { LogoMark } from "@/components/Logo";
import { useAuth } from "@/lib/auth-context";

export function ProtectedRoute(): JSX.Element {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div
        className="flex h-full flex-col items-center justify-center gap-4 bg-canvas"
        role="status"
        aria-live="polite"
      >
        <span className="animate-pulse">
          <LogoMark className="h-12 w-12" />
        </span>
        <p className="text-sm text-ink-muted">Loading…</p>
      </div>
    );
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
