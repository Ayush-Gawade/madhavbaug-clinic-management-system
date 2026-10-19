import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  CalendarClock,
  ChartNoAxesColumn,
  ChevronDown,
  HeartPulse,
  Inbox,
  LayoutDashboard,
  ListTodo,
  LogOut,
  Menu,
  MessageCircle,
  MessageSquareWarning,
  Moon,
  Settings,
  Sun,
  TriangleAlert,
  Users,
  Wallet,
  X,
} from "lucide-react";

import { Avatar } from "@/components/Avatar";
import { Badge } from "@/components/ui";
import { AppToaster } from "@/components/AppToaster";
import { Wordmark } from "@/components/Logo";
import { getAlertSummary } from "@/lib/alerts";
import { useAuth } from "@/lib/auth-context";
import { useTheme } from "@/lib/theme";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
  badge?: "alerts";
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Overview",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/analytics", label: "Analytics", icon: ChartNoAxesColumn },
    ],
  },
  {
    label: "Messaging",
    items: [
      { to: "/whatsapp", label: "WhatsApp", icon: MessageCircle },
      { to: "/inbox", label: "Inbox", icon: Inbox },
      { to: "/scheduler", label: "Scheduler", icon: CalendarClock },
      { to: "/message-exceptions", label: "Exceptions", icon: MessageSquareWarning },
    ],
  },
  {
    label: "Patients",
    items: [{ to: "/patients", label: "All patients", icon: Users }],
  },
  {
    label: "Operations",
    items: [
      { to: "/queues", label: "Queues", icon: ListTodo },
      { to: "/follow-ups", label: "Follow-ups", icon: HeartPulse },
      { to: "/alerts", label: "Alerts", icon: TriangleAlert, badge: "alerts" },
    ],
  },
  {
    label: "Finance",
    items: [{ to: "/finance", label: "Treatments & costs", icon: Wallet }],
  },
  {
    label: "Clinic",
    items: [{ to: "/settings", label: "Settings", icon: Settings }],
  },
];

function usePageTitle(): string {
  const { pathname } = useLocation();
  return useMemo(() => {
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        const matches = item.end ? pathname === item.to : pathname.startsWith(item.to);
        if (matches) return item.label;
      }
    }
    if (pathname.startsWith("/patients/")) return "Patient record";
    return "Madhavbaug";
  }, [pathname]);
}

function NavLinks({
  onNavigate,
  alertCount,
}: {
  onNavigate?: () => void;
  alertCount: number | undefined;
}): JSX.Element {
  return (
    <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
      {NAV_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="px-3 pb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-ink-faint">
            {group.label}
          </p>
          <div className="space-y-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    [
                      "group flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition duration-150",
                      isActive
                        ? "bg-brand-600/10 text-brand-800 dark:bg-brand-400/15 dark:text-brand-200"
                        : "text-ink-secondary hover:bg-surface-sunken hover:text-ink",
                    ].join(" ")
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={`h-4 w-4 shrink-0 ${
                          isActive
                            ? "text-brand-700 dark:text-brand-300"
                            : "text-ink-muted group-hover:text-ink"
                        }`}
                      />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      {item.badge === "alerts" && (alertCount ?? 0) > 0 ? (
                        <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
                          {alertCount}
                        </span>
                      ) : null}
                    </>
                  )}
                </NavLink>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

export function AppLayout(): JSX.Element {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const pageTitle = usePageTitle();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const alerts = useQuery({
    queryKey: ["alert-summary"],
    queryFn: () => getAlertSummary(),
    refetchInterval: 60_000,
    retry: false,
  });

  useEffect(() => {
    setMobileNavOpen(false);
    setUserMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!userMenuOpen) return undefined;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setUserMenuOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [userMenuOpen]);

  const handleLogout = async (): Promise<void> => {
    await logout();
    navigate("/login", { replace: true });
  };

  const alertCount = alerts.data?.open_urgent ?? alerts.data?.open_total;

  return (
    <div className="flex h-full bg-canvas">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        <div className="border-b border-line px-4 py-4">
          <Wordmark />
        </div>
        <NavLinks alertCount={alertCount} />
        <div className="border-t border-line px-4 py-3">
          <p className="text-[11px] text-ink-faint">Madhavbaug clinic engagement</p>
        </div>
      </aside>

      {/* Mobile drawer */}
      {mobileNavOpen ? (
        <div
          className="fixed inset-0 z-40 bg-overlay backdrop-blur-[2px] animate-fade-in lg:hidden"
          onClick={() => setMobileNavOpen(false)}
          role="presentation"
        />
      ) : null}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-surface transition-transform duration-200 ease-out lg:hidden ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-hidden={!mobileNavOpen}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-4">
          <Wordmark />
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileNavOpen(false)}
            className="rounded-lg p-1.5 text-ink-muted hover:bg-surface-sunken hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <NavLinks alertCount={alertCount} onNavigate={() => setMobileNavOpen(false)} />
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-md sm:px-6">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
            className="rounded-lg p-2 text-ink-secondary transition hover:bg-surface-sunken hover:text-ink lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>

          <h2 className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight text-ink sm:text-base lg:hidden">
            {pageTitle}
          </h2>

          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              onClick={toggle}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              className="rounded-lg p-2 text-ink-secondary transition hover:bg-surface-sunken hover:text-ink"
            >
              {theme === "dark" ? <Sun className="h-4.5 w-4.5" /> : <Moon className="h-4.5 w-4.5" />}
            </button>

            <div className="relative">
              <button
                type="button"
                onClick={() => setUserMenuOpen((open) => !open)}
                aria-haspopup="menu"
                aria-expanded={userMenuOpen}
                className="flex items-center gap-2.5 rounded-xl py-1.5 pl-1.5 pr-2.5 text-left transition hover:bg-surface-sunken"
              >
                <Avatar name={user?.full_name} size="sm" />
                <span className="hidden min-w-0 sm:block">
                  <span className="block max-w-40 truncate text-[13px] font-semibold text-ink">
                    {user?.full_name}
                  </span>
                  <span className="block text-[11px] capitalize text-ink-muted">{user?.role}</span>
                </span>
                <ChevronDown className="hidden h-3.5 w-3.5 shrink-0 text-ink-muted sm:block" />
              </button>

              {userMenuOpen ? (
                <>
                  <div
                    className="fixed inset-0 z-40"
                    onClick={() => setUserMenuOpen(false)}
                    role="presentation"
                  />
                  <div
                    role="menu"
                    className="absolute right-0 z-50 mt-2 w-56 animate-scale-in overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
                  >
                    <div className="border-b border-line px-4 py-3">
                      <p className="truncate text-sm font-semibold text-ink">{user?.full_name}</p>
                      <Badge tone="brand" className="mt-1.5 capitalize">
                        {user?.role}
                      </Badge>
                    </div>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setUserMenuOpen(false);
                        toggle();
                      }}
                      className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm font-medium text-ink-secondary transition hover:bg-surface-sunken hover:text-ink"
                    >
                      {theme === "dark" ? (
                        <Sun className="h-4 w-4" />
                      ) : (
                        <Moon className="h-4 w-4" />
                      )}
                      {theme === "dark" ? "Light mode" : "Dark mode"}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => void handleLogout()}
                      className="flex w-full items-center gap-2.5 border-t border-line px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-400/10"
                    >
                      <LogOut className="h-4 w-4" />
                      Sign out
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-[1440px] animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>

      <AppToaster />
    </div>
  );
}
