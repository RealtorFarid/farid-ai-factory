/**
 * The morning screen.
 *
 * This is an action page, not a report. It answers six questions and nothing
 * else: who to call, what is overdue, who has gone cold, what is on today, who
 * is waiting on a reply, and what matters most today.
 *
 * Deliberately absent: totals, charts, and "what I have" metrics. If a number
 * does not change what the next hour looks like, it is not here.
 *
 * Every row leads somewhere. Rows with a person carry Call / SMS / Email / Note
 * so the common actions never need a page change.
 */

import { useNavigate } from "react-router-dom";

import {
  CalendarList,
  EmailList,
  LeadActions,
  LeadList,
  SuggestionList,
  TaskList,
  awaitingReply,
  callList,
  coldLeads,
  overdueTasks,
  priorityToday,
  todaysEvents,
} from "@/components/panels";
import { Async, Card, SkeletonRows } from "@/components/ui";
import { useResource } from "@/hooks/useResource";
import { api } from "@/lib/api";
import type { Dashboard, Lead, Suggestion } from "@/lib/types";

/**
 * AI suggestions are hidden, not removed: the dashboard is scoped to the six
 * questions above, and recommendations return as their own surface later.
 * Flip to true to bring the panel back.
 */
const SHOW_AI_SUGGESTIONS = false;

export function TodayPage() {
  const navigate = useNavigate();
  const dashboard = useResource<Dashboard>(() => api.dashboard());
  const leads = useResource<Lead[]>(() => api.leads());

  const openLead = (leadId: string) => navigate(`/leads/${leadId}`);
  // "Note" goes to the lead's own page, where the recorder sits next to
  // everything already known about them.
  const addNote = (leadId: string) => navigate(`/leads/${leadId}`);
  const askAtlas = (suggestion: Suggestion) =>
    navigate("/chat", { state: { prompt: suggestion.prompt } });

  const actions = (lead: Lead) => <LeadActions lead={lead} onNote={addNote} />;

  const overdue = overdueTasks(dashboard.data?.tasks ?? []);
  const priority = priorityToday(dashboard.data?.tasks ?? []);
  const today = todaysEvents(dashboard.data?.calendar.events ?? []);
  const replies = awaitingReply(dashboard.data?.emails.threads ?? []);
  const toCall = callList(leads.data ?? []);
  const cold = coldLeads(leads.data ?? []);

  return (
    <div className="grid grid--dashboard">
      {/* 1. Who should I call today? */}
      <div className="col-6">
        <Card title="Call today" hint={toCall.length ? `${toCall.length} people` : undefined} flush>
          <Async
            data={leads.data}
            error={leads.error}
            loading={leads.loading}
            onRetry={leads.reload}
            skeleton={<SkeletonRows rows={4} />}
            empty={{
              title: "Nobody to call",
              body: "Every active lead has been contacted recently.",
              when: () => toCall.length === 0,
            }}
          >
            {() => <LeadList leads={toCall} onSelect={openLead} actions={actions} />}
          </Async>
        </Card>
      </div>

      {/* 2. Which follow-ups are overdue? */}
      <div className="col-6">
        <Card
          title="Overdue follow-ups"
          hint={overdue.length ? `${overdue.length} late` : undefined}
          flush
        >
          <Async
            data={dashboard.data}
            error={dashboard.error}
            loading={dashboard.loading}
            onRetry={dashboard.reload}
            skeleton={<SkeletonRows rows={3} />}
            empty={{
              title: "Nothing overdue",
              body: "You are caught up.",
              when: () => overdue.length === 0,
            }}
          >
            {() => <TaskList tasks={overdue} onSelect={openLead} />}
          </Async>
        </Card>
      </div>

      {/* 5. Which conversations are waiting for my reply? */}
      <div className="col-6">
        <Card
          title="Waiting on your reply"
          hint={replies.length ? `${replies.length} threads` : undefined}
          flush
        >
          <Async
            data={dashboard.data}
            error={dashboard.error}
            loading={dashboard.loading}
            onRetry={dashboard.reload}
            skeleton={<SkeletonRows rows={3} />}
            empty={{
              title: "No one is waiting",
              body: "Every thread has been answered.",
              when: () => replies.length === 0,
            }}
          >
            {(data) => (
              <EmailList summary={{ ...data.emails, threads: replies }} onSelect={openLead} />
            )}
          </Async>
        </Card>
      </div>

      {/* 4. What appointments do I have today? */}
      <div className="col-6">
        <Card
          title="Today's appointments"
          hint={today.length ? `${today.length} booked` : undefined}
          flush
        >
          <Async
            data={dashboard.data}
            error={dashboard.error}
            loading={dashboard.loading}
            onRetry={dashboard.reload}
            skeleton={<SkeletonRows rows={3} />}
            empty={{
              title: "Nothing booked today",
              body: "The day is yours.",
              when: () => today.length === 0,
            }}
          >
            {(data) => (
              <CalendarList summary={{ ...data.calendar, events: today }} onSelect={openLead} />
            )}
          </Async>
        </Card>
      </div>

      {/* 3. Which leads have gone cold? */}
      <div className="col-6">
        <Card
          title="Gone cold"
          hint={cold.length ? `${cold.length} untouched` : undefined}
          flush
        >
          <Async
            data={leads.data}
            error={leads.error}
            loading={leads.loading}
            onRetry={leads.reload}
            skeleton={<SkeletonRows rows={3} />}
            empty={{
              title: "Nobody has gone quiet",
              body: "Every active lead has been touched this week.",
              when: () => cold.length === 0,
            }}
          >
            {() => <LeadList leads={cold} onSelect={openLead} actions={actions} />}
          </Async>
        </Card>
      </div>

      {/* 6. What are today's highest-priority tasks? */}
      <div className="col-6">
        <Card
          title="Priority today"
          hint={priority.length ? `${priority.length} to do` : undefined}
          flush
        >
          <Async
            data={dashboard.data}
            error={dashboard.error}
            loading={dashboard.loading}
            onRetry={dashboard.reload}
            skeleton={<SkeletonRows rows={3} />}
            empty={{
              title: "No high-priority work today",
              body: "Nothing urgent is scheduled.",
              when: () => priority.length === 0,
            }}
          >
            {() => <TaskList tasks={priority} onSelect={openLead} />}
          </Async>
        </Card>
      </div>

      {SHOW_AI_SUGGESTIONS && (
        <div className="col-12">
          <Card title="AI suggestions" hint="Ranked by impact" flush>
            <Async
              data={dashboard.data}
              error={dashboard.error}
              loading={dashboard.loading}
              onRetry={dashboard.reload}
              skeleton={<SkeletonRows rows={3} />}
              empty={{ title: "No suggestions", when: (d) => d.suggestions.length === 0 }}
            >
              {(data) => <SuggestionList suggestions={data.suggestions} onAct={askAtlas} />}
            </Async>
          </Card>
        </div>
      )}
    </div>
  );
}
