/**
 * Capture: say what happened, and the workspace remembers it.
 *
 * Every remembered fact shows the quote it came from. That is the whole trust
 * model — nothing is presented as known unless the note actually said it.
 */

import { useState } from "react";

import { IconCheck, IconSpark } from "@/components/layout/Icons";
import { Async, Badge, Button, Card, SkeletonRows, type Tone } from "@/components/ui";
import { useResource } from "@/hooks/useResource";
import { ApiError, api } from "@/lib/api";
import { relative, titleCase } from "@/lib/format";
import type { CaptureResult, ClaimInfo, Lead } from "@/lib/types";

const EXAMPLE =
  "Met Priya at the Yonge showing. Her husband Reza came too — he cared more " +
  "about the commute than the layout. They want to move before September.";

function confidenceTone(value: number): Tone {
  if (value >= 0.85) return "success";
  if (value >= 0.6) return "accent";
  return "warning";
}

function ClaimRow({ claim }: { claim: ClaimInfo }) {
  return (
    <li className="list__row">
      <div className="list__main">
        <p className="list__title">
          {titleCase(claim.predicate)}: {claim.value}
        </p>
        {claim.quote && <p className="claim__quote">“{claim.quote}”</p>}
      </div>
      <div className="list__side stack" style={{ alignItems: "flex-end", gap: 4 }}>
        <Badge tone={confidenceTone(claim.confidence)}>
          {Math.round(claim.confidence * 100)}%
        </Badge>
        <span style={{ fontSize: "var(--text-xs)" }}>{relative(claim.asserted_at)}</span>
      </div>
    </li>
  );
}

export function CapturePage() {
  const leads = useResource<Lead[]>(() => api.leads());
  const [leadId, setLeadId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CaptureResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const selected = leadId || leads.data?.[0]?.id || "";
  const known = useResource<ClaimInfo[]>(
    () => (selected ? api.leadClaims(selected) : Promise.resolve([])),
    [selected, reloadKey],
  );

  async function submit() {
    if (!selected || !note.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.capture(selected, note.trim()));
      setNote("");
      setReloadKey((k) => k + 1);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.isOffline
          ? "Can’t reach the Propilot API."
          : cause instanceof Error
            ? cause.message
            : "Could not save that note.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid--dashboard">
      <div className="col-7 stack" style={{ gap: "var(--s-5)" }}>
        <Card title="After the showing" hint="Say what happened — Atlas remembers it">
          <div className="stack" style={{ gap: "var(--s-3)" }}>
            <label className="capture__label">
              Who was it about?
              <select
                className="capture__select"
                value={selected}
                onChange={(event) => setLeadId(event.target.value)}
                disabled={busy || !leads.data}
              >
                {(leads.data ?? []).map((lead) => (
                  <option key={lead.id} value={lead.id}>
                    {lead.name}
                  </option>
                ))}
              </select>
            </label>

            <textarea
              className="capture__note"
              rows={6}
              value={note}
              placeholder={EXAMPLE}
              aria-label="What happened"
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void submit();
                }
              }}
            />

            <div className="row" style={{ gap: "var(--s-3)" }}>
              <Button
                variant="primary"
                onClick={submit}
                disabled={busy || !note.trim() || !selected}
              >
                <IconSpark /> {busy ? "Reading…" : "Remember this"}
              </Button>
              <span className="card__hint">⌘/Ctrl + Enter</span>
            </div>

            {error && <p className="capture__error">{error}</p>}
          </div>
        </Card>

        {result && (
          <Card
            title="Captured"
            hint={`${result.claims.length} remembered${
              result.discarded ? ` · ${result.discarded} discarded` : ""
            }`}
            flush
          >
            <div className="card__body">
              <p className="capture__summary">
                <IconCheck /> {result.summary}
              </p>
              {result.discarded > 0 && (
                <p className="card__hint">
                  {result.discarded} suggested fact
                  {result.discarded === 1 ? "" : "s"} could not be quoted from your note, so
                  {result.discarded === 1 ? " it was" : " they were"} discarded.
                </p>
              )}
            </div>
            {result.claims.length > 0 && (
              <ul className="list">
                {result.claims.map((claim) => (
                  <ClaimRow claim={claim} key={claim.id} />
                ))}
              </ul>
            )}
            {result.follow_ups.length > 0 && (
              <div className="card__footer">
                Follow-ups: {result.follow_ups.join(" · ")}
              </div>
            )}
          </Card>
        )}
      </div>

      <div className="col-5">
        <Card
          title="What we remember"
          hint={known.data ? `${known.data.length} facts` : undefined}
          flush
        >
          <Async
            data={known.data}
            error={known.error}
            loading={known.loading}
            onRetry={known.reload}
            skeleton={<SkeletonRows rows={4} />}
            empty={{
              title: "Nothing remembered yet",
              body: "Capture a note and it will appear here, with the quote it came from.",
              when: (d) => d.length === 0,
            }}
          >
            {(data) => (
              <ul className="list">
                {data.map((claim) => (
                  <ClaimRow claim={claim} key={claim.id} />
                ))}
              </ul>
            )}
          </Async>
        </Card>
      </div>
    </div>
  );
}
