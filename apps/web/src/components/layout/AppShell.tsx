/** Application chrome: sidebar, top bar, connection banner. */

import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import {
  IconActivity,
  IconCalendar,
  IconChat,
  IconInbox,
  IconLeads,
  IconMenu,
  IconToday,
} from "./Icons";
import { api } from "@/lib/api";
import { useResource } from "@/hooks/useResource";
import type { Dashboard } from "@/lib/types";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  count?: (d: Dashboard) => number;
}

const PRIMARY: NavItem[] = [
  { to: "/", label: "Today", icon: IconToday },
  { to: "/chat", label: "Ask Atlas", icon: IconChat },
];

const WORKSPACE: NavItem[] = [
  {
    to: "/leads",
    label: "Leads",
    icon: IconLeads,
    count: (d) => d.leads.needs_follow_up,
  },
  { to: "/inbox", label: "Inbox", icon: IconInbox, count: (d) => d.emails.unread },
  {
    to: "/calendar",
    label: "Calendar",
    icon: IconCalendar,
    count: (d) => d.calendar.today_count,
  },
  { to: "/activity", label: "Activity", icon: IconActivity },
];

const TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Today", subtitle: "What needs your attention" },
  "/chat": { title: "Ask Atlas", subtitle: "Your executive agent" },
  "/leads": { title: "Leads", subtitle: "Your pipeline, hottest first" },
  "/inbox": { title: "Inbox", subtitle: "Threads waiting on you" },
  "/calendar": { title: "Calendar", subtitle: "The next seven days" },
  "/activity": { title: "Activity", subtitle: "Every agent run and decision" },
};

function NavSection({
  label,
  items,
  dashboard,
  onNavigate,
}: {
  label?: string;
  items: NavItem[];
  dashboard: Dashboard | null;
  onNavigate: () => void;
}) {
  return (
    <div>
      {label && <p className="sidebar__section-label">{label}</p>}
      <nav className="sidebar__nav">
        {items.map(({ to, label: text, icon: Icon, count }) => {
          const value = dashboard && count ? count(dashboard) : 0;
          return (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={onNavigate}
              className={({ isActive }) =>
                `sidebar__link ${isActive ? "sidebar__link--active" : ""}`
              }
            >
              <Icon />
              <span>{text}</span>
              {value > 0 && <span className="sidebar__count">{value}</span>}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // Badge counts come from the dashboard, which every page needs anyway.
  const { data: dashboard, error } = useResource<Dashboard>(() => api.dashboard());

  useEffect(() => setMenuOpen(false), [pathname]);

  const heading = TITLES[pathname] ?? { title: "Propilot", subtitle: "" };
  const offline = Boolean(error);

  return (
    <div className="shell">
      <aside className={`sidebar ${menuOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__brand">
          <span className="sidebar__mark">PA</span>
          <span className="sidebar__wordmark">Propilot</span>
        </div>

        <NavSection items={PRIMARY} dashboard={dashboard} onNavigate={() => setMenuOpen(false)} />
        <NavSection
          label="Workspace"
          items={WORKSPACE}
          dashboard={dashboard}
          onNavigate={() => setMenuOpen(false)}
        />

        <div className="sidebar__footer">
          <span className="sidebar__avatar">FY</span>
          <div className="stack" style={{ minWidth: 0 }}>
            <span
              className="truncate"
              style={{ fontSize: "var(--text-base)", color: "var(--sidebar-fg-strong)" }}
            >
              Farid Yani
            </span>
            <span className="truncate" style={{ fontSize: "var(--text-xs)" }}>
              Brokerage
            </span>
          </div>
        </div>
      </aside>

      <div
        className={`shell__backdrop ${menuOpen ? "shell__backdrop--open" : ""}`}
        onClick={() => setMenuOpen(false)}
        aria-hidden
      />

      <div className="shell__main">
        <header className="topbar">
          <button
            className="topbar__menu"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="Toggle navigation"
          >
            <IconMenu />
          </button>
          <div className="stack">
            <h1 className="topbar__title">{heading.title}</h1>
            {heading.subtitle && <span className="topbar__subtitle">{heading.subtitle}</span>}
          </div>
        </header>

        {offline && (
          <div className="banner" role="status">
            <span className="dot" />
            Can’t reach the Propilot API. Start it with <code>make run</code>, then reload.
          </div>
        )}

        <main className="shell__content">{children}</main>
      </div>
    </div>
  );
}
