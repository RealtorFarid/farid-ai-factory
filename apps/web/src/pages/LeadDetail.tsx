/**
 * One lead, everything about them.
 *
 * The daily workflow this exists for: open the person before a call, see what
 * Atlas remembers, talk to them, record a note on the way out. Recording lives
 * here rather than only on Voice Notes so the loop stays on one screen.
 *
 * There is no `GET /v1/leads/{id}`, so the lead, tasks, threads and events are
 * filtered client-side from the existing list endpoints. Only claims have a
 * per-lead endpoint.
 */

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { IconMic, IconStop } from "@/components/layout/Icons";
import { CalendarList, EmailList, TaskList } from "@/components/panels";
import { Async, Badge, Card, Score, SkeletonRows, type Tone } from "@/components/ui";
import { useRecorder } from "@/hooks/useRecorder";
import { useResource } from "@/hooks/useResource";
import { ApiError, api } from "@/lib/api";
import { budget, initials, relative, titleCase } from "@/lib/format";
import type {
  CalendarSummary,
  ClaimInfo,
  EmailSummary,
  Lead,
  Task,
} from "@/lib/types";

const STAGE_TONE: Record<Lead["stage"], Tone> = {
  new: "info",
  contacted: "neutral",
  qualified: "accent",
  showing: "accent",
  offer: "warning",
  closed: "success",
  lost: "neutral",
};

function confidenceTone(value: number): Tone {
  if (value >= 0.85) return "success";
  if (value >= 0.6) return "accent";
  return "warning";
}

function formatSeconds(total: number): string {
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function LeadDetailPage() {
  const { leadId = "" } = useParams();
  const navigate = useNavigate();
  const recorder = useRecorder();

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captured, setCaptured] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Generous limits: these endpoints are list-shaped and filtered here, so a
  // small default would silently hide this lead's older items.
  const leads = useResource<Lead[]>(() => api.leads());
  const tasks = useResource<Task[]>(() => api.tasks());
  const emails = useResource<EmailSummary>(() => api.emailSummary(50));
  const calendar = useResource<CalendarSummary>(() => api.calendarSummary(60));
  const claims = useResource<ClaimInfo[]>(
    () => (leadId ? api.leadClaims(leadId) : Promise.resolve([])),
    [leadId, reloadKey],
  );

  const lead = leads.data?.find((candidate) => candidate.id === leadId) ?? null;
  const theirTasks = (tasks.data ?? []).filter((task) => task.lead_id === leadId);
  const theirThreads = (emails.data?.threads ?? []).filter((t) => t.lead_id === leadId);
  const theirEvents = (calendar.data?.events ?? []).filter((e) => e.lead_id === leadId);

  async function toggleRecording() {
    if (busy) return;
    setError(null);
    setCaptured(null);

    if (recorder.state !== "recording") {
      await recorder.start();
      return;
    }

    const recording = await recorder.stop();
    if (!recording) {
      setError("Nothing was recorded.");
      return;
    }

    setBusy(true);
    try {
      const result = await api.captureVoice(leadId, recording.blob, recording.filename);
      setCaptured(result.claims.length);
      setReloadKey((key) => key + 1);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.isOffline
          ? "Can't reach the Propilot API."
          : cause instanceof Error
            ? cause.message
            : "Could not save that recording.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: "var(--s-5)" }}>
      <button className="card__action" style={{ alignSelf: "flex-start" }} onClick={() => navigate("/leads")}>
        ← All leads
      </button>

      <Async
        data={leads.data}
        error={leads.error}
        loading={leads.loading}
        onRetry={leads.reload}
        skeleton={<SkeletonRows rows={2} />}
      >
        {() =>
          lead === null ? (
            <Card title="Not found">
              <p className="card__hint">No lead with id {leadId}.</p>
            </Card>
          ) : (
            <Card>
              <div className="row" style={{ gap: "var(--s-4)", flexWrap: "wrap" }}>
                <span className="avatar" style={{ width: 48, height: 48 }}>
                  {initials(lead.name)}
                </span>
                <div className="stack" style={{ gap: 4 }}>
                  <span className="page-head__title">{lead.name}</span>
                  <span className="card__hint">
                    <Badge tone={STAGE_TONE[lead.stage]}>{titleCase(lead.stage)}</Badge>{" "}
                    {budget(lead.budget_min, lead.budget_max)} · last touch{" "}
                    {relative(lead.last_contact_at)}
                  </span>
                  <span className="card__hint">
                    {lead.email} · {lead.phone}
                  </span>
                </div>
                <div style={{ marginLeft: "auto" }}>
                  <Score value={lead.score} />
                </div>
              </div>
              {lead.notes && (
                <p className="list__meta" style={{ marginTop: "var(--s-3)" }}>
                  {lead.notes}
                </p>
              )}
            </Card>
          )
        }
      </Async>

      <div className="grid grid--dashboard">
        <div className="col-7 stack" style={{ gap: "var(--s-5)" }}>
          <Card
            title="What Atlas remembers"
            hint={claims.data ? `${claims.data.length} facts` : undefined}
            flush
          >
            <div className="card__body">
              <div className="recorder">
                <button
                  type="button"
                  className={`recorder__button ${
                    recorder.state === "recording" ? "recorder__button--live" : ""
                  }`}
                  onClick={toggleRecording}
                  disabled={busy || !lead}
                  aria-label={
                    recorder.state === "recording" ? "Stop recording" : "Record a note"
                  }
                >
                  {recorder.state === "recording" ? <IconStop /> : <IconMic />}
                </button>
                <div className="stack">
                  <span className="recorder__label">
                    {recorder.state === "recording"
                      ? `Recording — ${formatSeconds(recorder.seconds)}`
                      : busy
                        ? "Transcribing…"
                        : captured !== null
                          ? `Remembered ${captured} new fact${captured === 1 ? "" : "s"}`
                          : "Add a note about them"}
                  </span>
                  <span className="card__hint">
                    {recorder.reason ?? "Speak in English, Persian or Spanish."}
                  </span>
                </div>
                {recorder.state === "recording" && (
                  <button
                    type="button"
                    className="card__action"
                    style={{ marginLeft: "auto" }}
                    onClick={recorder.cancel}
                  >
                    Cancel
                  </button>
                )}
              </div>
              {error && <p className="capture__error">{error}</p>}
            </div>

            <Async
              data={claims.data}
              error={claims.error}
              loading={claims.loading}
              onRetry={claims.reload}
              skeleton={<SkeletonRows rows={4} />}
              empty={{
                title: "Nothing remembered yet",
                body: "Record a note and what you said will appear here, with the quote it came from.",
                when: (data) => data.length === 0,
              }}
            >
              {(data) => (
                <ul className="list">
                  {data.map((claim) => (
                    <li className="list__row" key={claim.id}>
                      <div className="list__main">
                        <p className="list__title">
                          {titleCase(claim.predicate)}: {claim.value}
                        </p>
                        {claim.quote && <p className="claim__quote">“{claim.quote}”</p>}
                      </div>
                      <div
                        className="list__side stack"
                        style={{ alignItems: "flex-end", gap: 4 }}
                      >
                        <Badge tone={confidenceTone(claim.confidence)}>
                          {Math.round(claim.confidence * 100)}%
                        </Badge>
                        <span style={{ fontSize: "var(--text-xs)" }}>
                          {relative(claim.asserted_at)}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Async>
          </Card>
        </div>

        <div className="col-5 stack" style={{ gap: "var(--s-5)" }}>
          <Card title="Their tasks" hint={`${theirTasks.length} open`} flush>
            <Async
              data={tasks.data}
              error={tasks.error}
              loading={tasks.loading}
              onRetry={tasks.reload}
              skeleton={<SkeletonRows rows={2} />}
              empty={{ title: "No tasks for them", when: () => theirTasks.length === 0 }}
            >
              {() => <TaskList tasks={theirTasks} />}
            </Async>
          </Card>

          <Card title="Their threads" hint={`${theirThreads.length}`} flush>
            <Async
              data={emails.data}
              error={emails.error}
              loading={emails.loading}
              onRetry={emails.reload}
              skeleton={<SkeletonRows rows={2} />}
              empty={{ title: "No threads with them", when: () => theirThreads.length === 0 }}
            >
              {(data) => (
                <EmailList summary={{ ...data, threads: theirThreads }} />
              )}
            </Async>
          </Card>

          <Card title="Their appointments" hint={`${theirEvents.length}`} flush>
            <Async
              data={calendar.data}
              error={calendar.error}
              loading={calendar.loading}
              onRetry={calendar.reload}
              skeleton={<SkeletonRows rows={2} />}
              empty={{ title: "Nothing scheduled", when: () => theirEvents.length === 0 }}
            >
              {(data) => <CalendarList summary={{ ...data, events: theirEvents }} />}
            </Async>
          </Card>
        </div>
      </div>
    </div>
  );
}
