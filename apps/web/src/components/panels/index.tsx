/**
 * Dashboard panels.
 *
 * Each takes already-fetched data so the dashboard can load everything in one
 * round trip, and each is reused verbatim on its dedicated page.
 */

import type { KeyboardEvent } from "react";

import { Badge, Score, type Tone } from "../ui";
import type {
  CalendarEvent,
  CalendarSummary,
  EmailSummary,
  Lead,
  LeadSummary,
  Suggestion,
  Task,
} from "@/lib/types";
import { budget, day, initials, isOverdue, relative, time, titleCase } from "@/lib/format";

// ---- Tasks ---------------------------------------------------------------

const PRIORITY_TONE: Record<Task["priority"], Tone> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
};

export function TaskList({ tasks }: { tasks: Task[] }) {
  return (
    <ul className="list">
      {tasks.map((task) => {
        const overdue = isOverdue(task.due_at) && task.status !== "done";
        return (
          <li className="list__row" key={task.id}>
            <div className="list__main">
              <p className="list__title">{task.title}</p>
              <p className="list__meta">
                <Badge tone={PRIORITY_TONE[task.priority]}>{task.priority}</Badge>{" "}
                {task.status === "in_progress" && <Badge tone="info">in progress</Badge>}{" "}
                <span style={{ color: overdue ? "var(--danger)" : undefined }}>
                  {overdue ? "overdue · " : ""}
                  {time(task.due_at)}
                </span>
              </p>
            </div>
            <span className="list__side">{relative(task.due_at)}</span>
          </li>
        );
      })}
    </ul>
  );
}

// ---- Leads ---------------------------------------------------------------

const STAGE_TONE: Record<Lead["stage"], Tone> = {
  new: "info",
  contacted: "neutral",
  qualified: "accent",
  showing: "accent",
  offer: "warning",
  closed: "success",
  lost: "neutral",
};

const STAGE_ORDER: Lead["stage"][] = [
  "new",
  "contacted",
  "qualified",
  "showing",
  "offer",
  "closed",
];

export function LeadPipeline({ summary }: { summary: LeadSummary }) {
  const max = Math.max(1, ...Object.values(summary.by_stage));
  return (
    <div className="stage-bars">
      {STAGE_ORDER.map((stage) => {
        const count = summary.by_stage[stage] ?? 0;
        return (
          <div className="stage-bar" key={stage}>
            <span style={{ color: "var(--text-muted)" }}>{titleCase(stage)}</span>
            <span className="stage-bar__track">
              <span
                className="stage-bar__fill"
                style={{
                  width: `${(count / max) * 100}%`,
                  opacity: count ? 1 : 0,
                }}
              />
            </span>
            <span className="stage-bar__count">{count}</span>
          </div>
        );
      })}
    </div>
  );
}

export function LeadList({
  leads,
  onSelect,
}: {
  leads: Lead[];
  onSelect?: (id: string) => void;
}) {
  return (
    <ul className="list">
      {leads.map((lead) => (
        <li
          className="list__row"
          key={lead.id}
          {...(onSelect
            ? {
                onClick: () => onSelect(lead.id),
                onKeyDown: (event: KeyboardEvent<HTMLLIElement>) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(lead.id);
                  }
                },
                role: "button",
                tabIndex: 0,
                style: { cursor: "pointer" },
              }
            : {})}
        >
          <span className="avatar">{initials(lead.name)}</span>
          <div className="list__main">
            <p className="list__title">{lead.name}</p>
            <p className="list__meta">
              <Badge tone={STAGE_TONE[lead.stage]}>{titleCase(lead.stage)}</Badge>{" "}
              {budget(lead.budget_min, lead.budget_max)} · last touch{" "}
              {relative(lead.last_contact_at)}
            </p>
          </div>
          <span className="list__side">
            <Score value={lead.score} />
          </span>
        </li>
      ))}
    </ul>
  );
}

// ---- Email ---------------------------------------------------------------

export function EmailList({ summary }: { summary: EmailSummary }) {
  return (
    <ul className="list">
      {summary.threads.map((thread) => (
        <li className="list__row" key={thread.id}>
          <span className="avatar">{initials(thread.sender)}</span>
          <div className="list__main">
            <p className="list__title">
              {thread.unread && (
                <span
                  className="dot"
                  style={{
                    display: "inline-block",
                    marginRight: 6,
                    background: "var(--accent)",
                  }}
                />
              )}
              {thread.subject}
            </p>
            <p className="list__meta truncate">
              {thread.sender} — {thread.preview}
            </p>
          </div>
          <div className="list__side stack" style={{ alignItems: "flex-end", gap: 4 }}>
            <span>{relative(thread.received_at)}</span>
            {thread.needs_response && <Badge tone="warning">reply</Badge>}
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---- Calendar ------------------------------------------------------------

const KIND_TONE: Record<CalendarEvent["kind"], Tone> = {
  showing: "accent",
  call: "info",
  meeting: "neutral",
  open_house: "success",
};

export function CalendarList({ summary }: { summary: CalendarSummary }) {
  return (
    <ul className="list">
      {summary.events.map((event) => (
        <li className="list__row" key={event.id}>
          <div className="stack" style={{ minWidth: 58, gap: 0 }}>
            <span style={{ fontWeight: 620, fontVariantNumeric: "tabular-nums" }}>
              {time(event.starts_at)}
            </span>
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-subtle)" }}>
              {day(event.starts_at)}
            </span>
          </div>
          <div className="list__main">
            <p className="list__title">{event.title}</p>
            <p className="list__meta">
              <Badge tone={KIND_TONE[event.kind]}>{titleCase(event.kind)}</Badge> {event.location}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---- Suggestions ---------------------------------------------------------

const IMPACT_TONE: Record<Suggestion["impact"], Tone> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
};

export function SuggestionList({
  suggestions,
  onAct,
}: {
  suggestions: Suggestion[];
  onAct: (suggestion: Suggestion) => void;
}) {
  return (
    <div>
      {suggestions.map((suggestion) => (
        <article className="suggestion" key={suggestion.id}>
          <div className="suggestion__head">
            <Badge tone={IMPACT_TONE[suggestion.impact]}>{suggestion.impact}</Badge>
            <h3 className="suggestion__title">{suggestion.title}</h3>
          </div>
          <p className="suggestion__why">{suggestion.rationale}</p>
          <div>
            <button className="chip" onClick={() => onAct(suggestion)}>
              Ask Atlas to handle this
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

// ---- Stat tile -----------------------------------------------------------

export function Stat({
  label,
  value,
  meta,
}: {
  label: string;
  value: string | number;
  meta?: string;
}) {
  return (
    <div className="stat">
      <p className="stat__label">{label}</p>
      <p className="stat__value">{value}</p>
      {meta && <p className="stat__meta">{meta}</p>}
    </div>
  );
}
