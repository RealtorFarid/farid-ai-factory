/**
 * Dashboard panels, plus the rules that decide what belongs on them.
 *
 * Each list takes already-fetched data so a page can load everything in one
 * round trip, and each is reused verbatim on its dedicated page.
 *
 * The selectors below live here rather than in a page because they are
 * business rules, not presentation. When a second page needs them they belong
 * in `lib/rules.ts`; today the dashboard is the only consumer.
 */

import type { KeyboardEvent, ReactNode } from "react";

import { Badge, Score, type Tone } from "../ui";
import type {
  CalendarEvent,
  CalendarSummary,
  EmailSummary,
  EmailThread,
  Lead,
  LeadSummary,
  Suggestion,
  Task,
} from "@/lib/types";
import { budget, day, initials, isOverdue, relative, time, titleCase } from "@/lib/format";

// ---- Business rules ------------------------------------------------------

/**
 * Mirrors `FOLLOW_UP_AFTER` in the backend's WorkspaceService.
 *
 * The API exposes the *count* of stale leads but not the list, so the
 * threshold is duplicated here to render which ones. Keep the two in sync — if
 * they drift, the dashboard's count and its list will disagree.
 */
export const FOLLOW_UP_AFTER_DAYS = 7;

/**
 * Live pipeline stages, most urgent first: a deal in flight outranks a new
 * enquiry. Closed and lost are absent on purpose — nobody needs calling.
 */
const CALL_PRIORITY: Lead["stage"][] = ["offer", "showing", "qualified", "contacted", "new"];

function daysSince(iso: string, now: Date): number {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 0;
  return (now.getTime() - then) / 86_400_000;
}

/** Who to call: stage urgency first, then whoever has waited longest. */
export function callList(leads: Lead[], limit = 6, now: Date = new Date()): Lead[] {
  return leads
    .filter((lead) => CALL_PRIORITY.includes(lead.stage))
    .sort((a, b) => {
      const byStage = CALL_PRIORITY.indexOf(a.stage) - CALL_PRIORITY.indexOf(b.stage);
      if (byStage !== 0) return byStage;
      return daysSince(b.last_contact_at, now) - daysSince(a.last_contact_at, now);
    })
    .slice(0, limit);
}

/** Active leads nobody has touched in a week, coldest first. */
export function coldLeads(leads: Lead[], now: Date = new Date()): Lead[] {
  return leads
    .filter(
      (lead) =>
        CALL_PRIORITY.includes(lead.stage) &&
        daysSince(lead.last_contact_at, now) > FOLLOW_UP_AFTER_DAYS,
    )
    .sort((a, b) => daysSince(b.last_contact_at, now) - daysSince(a.last_contact_at, now));
}

export function overdueTasks(tasks: Task[], now: Date = new Date()): Task[] {
  return tasks.filter((task) => task.status !== "done" && isOverdue(task.due_at, now));
}

/** High-priority work due today, minus anything already shown as overdue. */
export function priorityToday(tasks: Task[], now: Date = new Date()): Task[] {
  return tasks.filter(
    (task) =>
      task.status !== "done" &&
      task.priority === "high" &&
      !isOverdue(task.due_at, now) &&
      new Date(task.due_at).toDateString() === now.toDateString(),
  );
}

export function todaysEvents(events: CalendarEvent[], now: Date = new Date()): CalendarEvent[] {
  return events.filter(
    (event) => new Date(event.starts_at).toDateString() === now.toDateString(),
  );
}

export function awaitingReply(threads: EmailThread[]): EmailThread[] {
  return threads.filter((thread) => thread.needs_response);
}

// ---- Row behaviour -------------------------------------------------------

/** Make a row behave like a link when the caller wants navigation. */
function rowProps(id: string | null | undefined, onSelect?: (id: string) => void) {
  if (!id || !onSelect) return {};
  return {
    onClick: () => onSelect(id),
    onKeyDown: (event: KeyboardEvent<HTMLLIElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(id);
      }
    },
    role: "button",
    tabIndex: 0,
    style: { cursor: "pointer" },
  };
}

/**
 * Call, text or email without leaving the page.
 *
 * `tel:` and `sms:` hand off to the OS, so this works from a Mac with a paired
 * phone and from mobile directly. Clicks stop propagating, so acting on a row
 * never also navigates away from it.
 */
export function LeadActions({
  lead,
  onNote,
}: {
  lead: Lead;
  onNote?: (leadId: string) => void;
}) {
  const stop = (event: { stopPropagation: () => void }) => event.stopPropagation();
  return (
    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
      {lead.phone && (
        <a className="chip" href={`tel:${lead.phone}`} onClick={stop}>
          Call
        </a>
      )}
      {lead.phone && (
        <a className="chip" href={`sms:${lead.phone}`} onClick={stop}>
          SMS
        </a>
      )}
      {lead.email && (
        <a className="chip" href={`mailto:${lead.email}`} onClick={stop}>
          Email
        </a>
      )}
      {onNote && (
        <button
          className="chip"
          onClick={(event) => {
            event.stopPropagation();
            onNote(lead.id);
          }}
        >
          Note
        </button>
      )}
    </div>
  );
}

// ---- Tasks ---------------------------------------------------------------

const PRIORITY_TONE: Record<Task["priority"], Tone> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
};

export function TaskList({
  tasks,
  onSelect,
}: {
  tasks: Task[];
  onSelect?: (leadId: string) => void;
}) {
  return (
    <ul className="list">
      {tasks.map((task) => {
        const overdue = isOverdue(task.due_at) && task.status !== "done";
        return (
          <li className="list__row" key={task.id} {...rowProps(task.lead_id, onSelect)}>
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
  actions,
}: {
  leads: Lead[];
  onSelect?: (id: string) => void;
  actions?: (lead: Lead) => ReactNode;
}) {
  return (
    <ul className="list">
      {leads.map((lead) => (
        <li className="list__row" key={lead.id} {...rowProps(lead.id, onSelect)}>
          <span className="avatar">{initials(lead.name)}</span>
          <div className="list__main">
            <p className="list__title">{lead.name}</p>
            <p className="list__meta">
              <Badge tone={STAGE_TONE[lead.stage]}>{titleCase(lead.stage)}</Badge>{" "}
              {budget(lead.budget_min, lead.budget_max)} · last touch{" "}
              {relative(lead.last_contact_at)}
            </p>
            {actions && <div style={{ marginTop: 6 }}>{actions(lead)}</div>}
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

export function EmailList({
  summary,
  onSelect,
}: {
  summary: EmailSummary;
  onSelect?: (leadId: string) => void;
}) {
  return (
    <ul className="list">
      {summary.threads.map((thread) => (
        <li className="list__row" key={thread.id} {...rowProps(thread.lead_id, onSelect)}>
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

export function CalendarList({
  summary,
  onSelect,
}: {
  summary: CalendarSummary;
  onSelect?: (leadId: string) => void;
}) {
  return (
    <ul className="list">
      {summary.events.map((event) => (
        <li className="list__row" key={event.id} {...rowProps(event.lead_id, onSelect)}>
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
