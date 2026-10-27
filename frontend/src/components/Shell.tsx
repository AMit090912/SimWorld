import {
  Activity,
  BookOpen,
  Bot,
  ChevronRight,
  GitCompareArrows,
  History,
  LayoutDashboard,
  Map,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../lib/api";

const NAV = [
  {
    section: "Lab",
    items: [
      { to: "/", label: "Workspace", icon: LayoutDashboard, end: true },
      { to: "/scenarios", label: "Scenarios", icon: Map },
    ],
  },
  {
    section: "Evidence",
    items: [
      { to: "/runs", label: "Runs", icon: History },
      { to: "/compare", label: "Compare", icon: GitCompareArrows },
    ],
  },
  {
    section: "Reference",
    items: [
      { to: "/agents", label: "Agents", icon: Bot },
      { to: "/docs", label: "Docs", icon: BookOpen },
    ],
  },
];

function Logo({ onDark = false }: { onDark?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden>
        <rect x="1" y="1" width="30" height="30" rx="5" fill="#F4EFE4" />
        <path d="M9 10.5h5.5L20 16l-3 5.5H9.5" stroke="#18211F" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="9" cy="10.5" r="2" fill="#C8552B" />
        <circle cx="20.5" cy="16" r="2" fill="#F4EFE4" stroke="#18211F" strokeWidth="1.6" />
        <circle cx="9.5" cy="21.5" r="2" fill="#C8552B" />
      </svg>
      <div className="leading-none">
        <div className={`text-[13px] font-semibold tracking-[0.22em] ${onDark ? "text-paper-50" : "text-ink-900"}`}>SIMWORLD</div>
        <div className={`mt-1 text-[8px] uppercase tracking-[0.2em] ${onDark ? "text-[#8B978F]" : "text-ink-500"}`}>Agent evaluation lab</div>
      </div>
    </div>
  );
}

export default function Shell() {
  const location = useLocation();
  const [online, setOnline] = useState<boolean | null>(null);
  const [version, setVersion] = useState<string>("");

  useEffect(() => {
    let active = true;
    const check = () => {
      api
        .health()
        .then((health) => {
          if (active) {
            setOnline(health.ok);
            setVersion(health.version);
          }
        })
        .catch(() => active && setOnline(false));
    };
    check();
    const handle = window.setInterval(check, 20000);
    return () => {
      active = false;
      window.clearInterval(handle);
    };
  }, []);

  const current =
    NAV.flatMap((group) => group.items).find((item) =>
      item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
    )?.label || "Run detail";

  return (
    <div className="relative z-10 flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[212px] flex-col border-r border-[#2B3531] bg-[#18211F] px-3.5 py-5 lg:flex">
        <div className="px-1.5">
          <Logo onDark />
        </div>
        <nav className="mt-8 flex-1 space-y-6">
          {NAV.map((group) => (
            <div key={group.section}>
              <div className="mb-2 px-2 text-[9px] font-semibold uppercase tracking-[0.18em] text-[#7E8A83]">{group.section}</div>
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) =>
                        `group flex items-center gap-2.5 rounded-md px-2 py-2 text-xs font-medium transition ${
                          isActive
                            ? "bg-accent/[0.16] text-paper-50 shadow-[inset_2px_0_0_#C8552B]"
                            : "text-[#A4AFA7] hover:bg-white/[0.06] hover:text-paper-50"
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <Icon className={`h-4 w-4 ${isActive ? "text-[#E38B63]" : "text-[#7E8A83] group-hover:text-[#D8DED7]"}`} />
                          <span>{item.label}</span>
                          {isActive ? <span className="ml-auto h-1 w-1 rounded-full bg-accent" /> : null}
                        </>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="space-y-2.5 border-t border-white/10 px-2 pt-3 text-[10px] text-[#8B978F]">
          <div className="flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                online === null ? "bg-[#5C6862]" : online ? "bg-[#8FAF8B] animate-pulse-dot" : "bg-[#C0574A]"
              }`}
            />
            {online === null ? "Connecting" : online ? "Simulation API online" : "API offline"}
          </div>
          <div className="flex items-center justify-between font-mono text-[9px] text-[#6F7B74]">
            <span>v{version || "0.1.0"}</span>
            <span className="rounded border border-white/15 px-1 py-0.5">local</span>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col lg:pl-[212px]">
        <header className="sticky top-0 z-20 border-b border-line/60 bg-paper/80 backdrop-blur">
          <div className="flex h-12 items-center justify-between gap-4 px-4 sm:px-6">
            <div className="flex min-w-0 items-center gap-2 text-[11px] text-ink-500">
              <span className="lg:hidden">
                <Logo />
              </span>
              <span className="hidden items-center gap-1.5 sm:flex">
                <span className="text-ink-500">SimWorld</span>
                <ChevronRight className="h-3 w-3 text-ink-400" />
                <span className="truncate text-ink-700">{current}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-1 text-[10px] text-ink-500 sm:flex">
                <Activity className="h-3 w-3 text-pine" />
                deterministic engine
              </span>
              <NavLink to="/docs" className="btn-ghost !py-1.5 !text-[11px]">
                <BookOpen className="h-3.5 w-3.5" /> Docs
              </NavLink>
            </div>
          </div>
          <nav className="grid grid-cols-3 gap-1 border-t border-line/50 px-3 py-2 lg:hidden">
            {NAV.flatMap((group) => group.items).map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `flex items-center gap-1.5 rounded px-2 py-1.5 text-[11px] ${
                      isActive ? "bg-accent/10 text-accent" : "text-ink-500"
                    }`
                  }
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
        </header>
        <main className="mx-auto w-full max-w-[1640px] flex-1 overflow-x-hidden px-4 py-5 sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}