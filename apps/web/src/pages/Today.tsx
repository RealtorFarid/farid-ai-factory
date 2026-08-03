/** The home screen: one dashboard round trip, six panels. */

import { useNavigate } from "react-router-dom";

import { CalendarList, EmailList, LeadPipeline, Stat, SuggestionList, TaskList } from
  "@/components/panels";
import { Async, Card, Skeleton, SkeletonRows } from "@/components/ui";
import { useResource } from "@/hooks/useResource";
import { api } from "@/lib/api";
import { relative, time } from "@/lib/format";
import type { Dashboard, Suggestion } from "@/lib/types";

function StatSkeleton() {
  return (
    <div className="stats">
      {Array.from({ length: 4 }, (_, index) => (
        <div className="stat" key={index}>
          <Skeleton width="52%" height={12} />
          <div style={{ marginTop: 10 }}>
            <Skeleton width="34%" height={26} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function TodayPage() {
  const navigate = useNavigate();
  const dashboard = useResource<Dashboard>(() => api.dashboard());

  function askAtlas(suggestion: Suggestion) {
    navigate("/chat", { state: { prompt: suggestion.prompt } });
  }

  return (
    <div className="stack" style={{ gap: "var(--s-5)" }}>
      <Async
        data={dashboard.data}
        error={dashboard.error}
        loading={dashboard.loading}
        onRetry={dashboard.reload}
        skeleton={<StatSkeleton />}
      >
        {(data) => (
          <div className="stats">
            <Stat
              label="Tasks due today"
              value={data.tasks.length}
              meta={
                data.tasks.filter((t) => t.priority === "high").length + " high priority"
              }
            />
            <Stat
              label="Unread email"
              value={data.emails.unread}
              meta={`${data.emails.needs_response} need a reply`}
            />
            <Stat
              label="Appointments today"
              value={data.calendar.today_count}
              meta={
                data.calendar.next_event
                  ? `next at ${time(data.calendar.next_event.starts_at)}`
                  : "nothing scheduled"
              }
            />
            <Stat
              label="Active leads"
              value={data.leads.total}
              meta={`${data.leads.needs_follow_up} need a follow-up`}
            />
          </div>
        )}
      </Async>

      <div className="grid grid--dashboard">
        <div className="col-7">
          <Card
            title="Today’s tasks"
            hint={dashboard.data ? `${dashboard.data.tasks.length} open` : undefined}
            flush
          >
            <Async
              data={dashboard.data}
              error={dashboard.error}
              loading={dashboard.loading}
              onRetry={dashboard.reload}
              skeleton={<SkeletonRows rows={5} />}
              empty={{
                title: "Nothing due today",
                body: "Enjoy it, or ask Atlas what is coming up.",
                when: (d) => d.tasks.length === 0,
              }}
            >
              {(data) => <TaskList tasks={data.tasks} />}
            </Async>
          </Card>
        </div>

        <div className="col-5">
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

        <div className="col-4">
          <Card
            title="Pipeline"
            action={
              <button className="card__action" onClick={() => navigate("/leads")}>
                View all
              </button>
            }
          >
            <Async
              data={dashboard.data}
              error={dashboard.error}
              loading={dashboard.loading}
              onRetry={dashboard.reload}
              skeleton={<SkeletonRows rows={4} />}
            >
              {(data) => <LeadPipeline summary={data.leads} />}
            </Async>
          </Card>
        </div>

        <div className="col-4">
          <Card
            title="Inbox"
            hint={dashboard.data ? `${dashboard.data.emails.unread} unread` : undefined}
            action={
              <button className="card__action" onClick={() => navigate("/inbox")}>
                Open
              </button>
            }
            flush
          >
            <Async
              data={dashboard.data}
              error={dashboard.error}
              loading={dashboard.loading}
              onRetry={dashboard.reload}
              skeleton={<SkeletonRows rows={3} />}
              empty={{ title: "Inbox zero", when: (d) => d.emails.threads.length === 0 }}
            >
              {(data) => <EmailList summary={data.emails} />}
            </Async>
          </Card>
        </div>

        <div className="col-4">
          <Card
            title="Schedule"
            hint={
              dashboard.data?.calendar.next_event
                ? `next ${relative(dashboard.data.calendar.next_event.starts_at)}`
                : undefined
            }
            action={
              <button className="card__action" onClick={() => navigate("/calendar")}>
                Open
              </button>
            }
            flush
          >
            <Async
              data={dashboard.data}
              error={dashboard.error}
              loading={dashboard.loading}
              onRetry={dashboard.reload}
              skeleton={<SkeletonRows rows={3} />}
              empty={{ title: "Nothing scheduled", when: (d) => d.calendar.events.length === 0 }}
            >
              {(data) => <CalendarList summary={data.calendar} />}
            </Async>
          </Card>
        </div>
      </div>
    </div>
  );
}
