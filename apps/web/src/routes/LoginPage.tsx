import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, Leaf, LockKeyhole, Loader2 } from "lucide-react";

import { LogoMark } from "@/components/Logo";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface LocationState {
  from?: string;
}

export function LoginPage(): JSX.Element {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  const redirectTo = (location.state as LocationState | null)?.from ?? "/";

  const handleSubmit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unable to sign in. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-800 via-brand-900 to-brand-950 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-accent-400/10 blur-3xl"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute -bottom-40 -left-24 h-[28rem] w-[28rem] rounded-full bg-brand-400/10 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative flex items-center gap-3">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20">
            <Leaf className="h-5 w-5 text-accent-300" />
          </span>
          <div>
            <p className="text-lg font-bold tracking-tight text-white">Madhavbaug</p>
            <p className="text-xs font-medium text-brand-200">Clinic Management</p>
          </div>
        </div>

        <div className="relative max-w-md">
          <p className="text-3xl font-bold leading-snug tracking-tight text-white">
            Patient care, coordinated over WhatsApp.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-brand-100/80">
            Automated check-ins, rule-driven clinical alerts, AI-assisted monitoring and
            treatment profitability — one workspace for the whole clinic.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-brand-100/90">
            {[
              "Never miss an overdue follow-up",
              "Deterministic safety thresholds on every reading",
              "Delivery failures and non-response kept distinct",
            ].map((item) => (
              <li key={item} className="flex items-center gap-3">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent-300" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-brand-200/60">
          Proprietary — for the Madhavbaug clinic engagement.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center bg-canvas px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm animate-slide-up">
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <LogoMark className="h-12 w-12" />
            <p className="mt-3 text-lg font-bold tracking-tight text-ink">Madhavbaug Clinic</p>
          </div>

          <div className="rounded-2xl border border-line bg-surface p-8 shadow-card">
            <div className="mb-6">
              <h1 className="text-lg font-bold tracking-tight text-ink">Welcome back</h1>
              <p className="mt-1 text-sm text-ink-muted">Sign in to the staff dashboard</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label
                  htmlFor="email"
                  className="mb-1.5 block text-[13px] font-semibold text-ink-secondary"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-hairline transition placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10"
                  placeholder="you@madhavbaug.in"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="mb-1.5 block text-[13px] font-semibold text-ink-secondary"
                >
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-hairline transition placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10"
                  placeholder="••••••••"
                />
              </div>

              {error ? (
                <p
                  role="alert"
                  className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800 ring-1 ring-inset ring-red-200 dark:bg-red-400/10 dark:text-red-300 dark:ring-red-400/25"
                >
                  {error}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={submitting}
                className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand-600 text-sm font-semibold text-white shadow-hairline transition duration-150 hover:bg-brand-700 active:bg-brand-800 disabled:pointer-events-none disabled:opacity-60"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Signing in…
                  </>
                ) : (
                  <>
                    Sign in
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>
          </div>

          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-ink-muted">
            <LockKeyhole className="h-3.5 w-3.5" />
            Staff access only · Madhavbaug Clinic Management
          </p>
        </div>
      </div>
    </div>
  );
}
