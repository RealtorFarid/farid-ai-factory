/**
 * The workspace pages: Leads, Inbox, Calendar, Activity.
 *
 * Each is backed by a real endpoint — there are no placeholder screens.
 */

import { CalendarList, EmailList, LeadList, LeadPipeline, Stat } from "@/components/panels";
import { Async, Badge, Card, SkeletonRows, type Tone } from "@/components/ui";
import { useResource } from "@/hooks/useResource";
import { api } from "@/lib/api";
import { day, relative, time, titleCase } from "@/lib/format";
import type {
  CalendarSummary,
  EmailSummary,
  Lead,
  LeadSummary,
  Run,
  RunStatus,
} from "@/lib/types";

// ---- Leads ---------------------------------------------------------------

export function LeadsPage() {
  const leads = useResource<Lead[]>(() => api.leads());
  const summary = useResource<LeadSummary>(() => api.leadSummary());

  return (
    <div className="grid grid--dashboard">
      <div className="col-8">
        <Card title="All leads" hint={leads.data ? `${leads.data.length} total` : undefined} flush>
          <Async
            data={leads.data}
            error={leads.error}
            loading={leads.loading}
            onRetry={leads.reload}
            skeleton={<SkeletonRows rows={6} />}
            empty={{ title: "No leads yet", when: (d) => d.length === 0 }}
          >
            {(data) => <LeadList leads={data} />}
          </Async>
        </Card>
      </div>

      <div className="col-4 stack" style={{ gap: "var(--s-5)" }}>
        <Card title="By stage">
          <Async
            data={summary.data}
            error={summary.error}
            loading={summary.loading}
            onRetry={summary.reload}
            skeleton={<SkeletonRows rows={4} />}
          >
            {(data) => <LeadPipeline summary={data} />}
          </Async>
        </Card>

        <Async
          data={summary.data}
          error={summary.error}
          loading={summary.loading}
          onRetry={summary.reload}
          skeleton={<SkeletonRows rows={2} />}
        >
          {(data) => (
            <div className="stats">
              <Stat label="Need a follow-up" value={data.needs_follow_up} meta="7+ days quiet" />
              <Stat label="Touched this week" value={data.new_this_week} />
            </div>
          )}
        </Async>
      </div>
    </div>
  );
}

// ---- Inbox ---------------------------------------------------------------

export function InboxPage() {
  const inbox = useResource<EmailSummary>(() => api.emailSummary(25));

  return (
    <div className="stack" style={{ gap: "var(--s-5)" }}>
      <Async
        data={inbox.data}
        error={inbox.error}
        loading={inbox.loading}
        onRetry={inbox.reload}
        skeleton={<SkeletonRows rows={2} />}
      >
        {(data) => (
          <div className="stats">
            <Stat label="Unread" value={data.unread} />
            <Stat label="Awaiting your reply" value={data.needs_response} />
            <Stat label="Threads shown" value={data.threads.length} />
          </div>
        )}
      </Async>

      <Card title="Recent threads" flush>
        <Async
          data={inbox.data}
          error={inbox.error}
          loading={inbox.loading}
          onRetry={inbox.reload}
          skeleton={<SkeletonRows rows={6} />}
          empty={{ title: "Inbox zero", body: "Nothing waiting.", when: (d) => !d.threads.length }}
        >
          {(data) => <EmailList summary={data} />}
        </Async>
      </Card>
    </div>
  );
}

// ---- Calendar ------------------------------------------------------------

export function CalendarPage() {
  const calendar = useResource<CalendarSummary>(() => api.calendarSummary(14));

  return (
    <div className="stack" style={{ gap: "var(--s-5)" }}>
      <Async
        data={calendar.data}
        error={calendar.error}
        loading={calendar.loading}
        onRetry={calendar.reload}
        skeleton={<SkeletonRows rows={2} />}
      >
        {(data) => (
          <div className="stats">
            <Stat label="Today" value={data.today_count} meta="appointments" />
            <Stat
              label="Next up"
              value={data.next_event ? time(data.next_event.starts_at) : "—"}
              meta={data.next_event ? data.next_event.title : "nothing scheduled"}
            />
            <Stat label="Next 14 days" value={data.events.length} meta="events" />
          </div>
        )}
      </Async>

      <Card title="Upcoming" hint="Next 14 days" flush>
        <Async
          data={calendar.data}
          error={calendar.error}
          loading={calendar.loading}
          onRetry={calendar.reload}
          skeleton={<SkeletonRows rows={5} />}
          empty={{ title: "Nothing scheduled", when: (d) => d.events.length === 0 }}
        >
          {(data) => <CalendarList summary={data} />}
        </Async>
      </Card>
    </div>
  );
}

// ---- Activity ------------------------------------------------------------

const RUN_TONE: Record<RunStatus, Tone> = {
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  partial: "warning",
  failed: "danger",
};

export function ActivityPage() {
  const runs = useResource<{ runs: Run[] }>(() => api.runs(50));

  return (
    <Card
      title="Agent activity"
      hint="Every run, tool call and approval"
      action={
        <button className="card__action" onClick={runs.reload}>
          Refresh
        </button>
      }
      flush
    >
      <Async
        data={runs.data}
        error={runs.error}
        loading={runs.loading}
        onRetry={runs.reload}
        skeleton={<SkeletonRows rows={6} />}
        empty={{
          title: "No runs yet",
          body: "Ask Atlas something and it will show up here.",
          when: (d) => d.runs.length === 0,
        }}
      >
        {(data) => (
          <ul className="list">
            {data.runs.map((run) => {
              const approved = run.tool_calls.filter((c) => c.approved === true).length;
              const denied = run.tool_calls.filter((c) => c.approved === false).length;
              return (
                <li className="list__row" key={run.id}>
                  <div className="list__main">
                    <p className="list__title truncate">{run.prompt}</p>
                    <p className="list__meta">
                      <Badge tone={RUN_TONE[run.status]}>
                        {titleCase(run.status)}
                      </Badge>{" "}
                      {run.model} · {run.duration_ms}ms
                      {run.usage ? ` · ${run.usage.total_tokens} tokens` : ""}
                      {approved > 0 && ` · ${approved} approved`}
                      {denied > 0 && ` · ${denied} denied`}
                      {run.error ? ` · ${run.error}` : ""}
                    </p>
                  </div>
                  <div className="list__side stack" style={{ alignItems: "flex-end", gap: 2 }}>
                    <span>{relative(run.created_at)}</span>
                    <span style={{ fontSize: "var(--text-xs)" }}>{day(run.created_at)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Async>
    </Card>
  );
}
