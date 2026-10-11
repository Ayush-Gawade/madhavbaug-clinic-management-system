import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/whatsapp", label: "WhatsApp" },
  { to: "/queues", label: "Queues" },
  { to: "/patients", label: "Patients" },
  { to: "/scheduler", label: "Scheduler" },
  { to: "/follow-ups", label: "Follow-ups" },
  { to: "/alerts", label: "Alerts" },
  { to: "/message-exceptions", label: "Message exceptions" },
  { to: "/analytics", label: "Analytics" },
  { to: "/finance", label: "Finance" },
];

export function AppLayout(): JSX.Element {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async (): Promise<void> => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="border-b border-slate-200 px-5 py-4">
          <p className="text-sm font-semibold text-brand-700">Madhavbaug</p>
          <p className="text-xs text-slate-500">Clinic Management</p>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                [
                  "block rounded-md px-3 py-2 text-sm font-medium",
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                ].join(" ")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <div>
            <p className="text-sm font-medium text-slate-800">{user?.full_name}</p>
            <p className="text-xs uppercase tracking-wide text-slate-500">{user?.role}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Sign out
          </button>
        </header>
        <main className="min-h-0 flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
