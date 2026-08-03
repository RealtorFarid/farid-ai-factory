/** The conversation surface: streamed replies and inline approval gates. */

import { useEffect, useRef, useState } from "react";

import {
  IconCheck,
  IconPartial,
  IconSend,
  IconShield,
  IconSpark,
  IconTool,
  IconX,
} from "../layout/Icons";
import { Badge, Button, type Tone } from "../ui";
import type { Entry } from "@/hooks/useChat";
import { argEntries, titleCase } from "@/lib/format";

const STARTERS = [
  "What needs my attention today?",
  "Summarise my pipeline.",
  "Which leads have gone cold?",
  "Draft a follow-up to my hottest lead.",
];

function ToolChip({ name }: { name: string }) {
  return (
    <Badge tone="neutral">
      <IconTool />
      {titleCase(name)}
    </Badge>
  );
}

function AgentEntry({ entry }: { entry: Extract<Entry, { kind: "agent" }> }) {
  // A turn can produce tool activity but no prose — when the agent's next step
  // is an approval request. Rendering an empty bubble in that case looks broken,
  // so the chips stand alone.
  const showBubble = Boolean(entry.text) || entry.streaming;

  return (
    <div className="msg msg--agent">
      <span className="msg__avatar msg__avatar--agent">A</span>
      <div style={{ minWidth: 0 }}>
        {showBubble && (
          <div className="msg__bubble">
            {entry.text}
            {entry.streaming && entry.text && <span className="caret" />}
            {entry.streaming && !entry.text && (
              <span className="thinking" aria-label="Atlas is thinking">
                <span />
                <span />
                <span />
              </span>
            )}
          </div>
        )}
        {entry.tools.length > 0 && (
          <div className="msg__tools">
            {entry.tools.map((tool, index) => (
              <ToolChip key={`${tool}-${index}`} name={tool} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const OUTCOME_LABEL: Record<string, { text: string; tone: Tone }> = {
  executed: { text: "Done", tone: "success" },
  denied: { text: "Declined", tone: "neutral" },
  failed: { text: "Failed", tone: "danger" },
  proposed: { text: "Not run", tone: "neutral" },
};

/**
 * One card per run, listing every gated action it proposed.
 *
 * Grouped rather than one card per action: the API denies anything left out of
 * a decision set, so submitting each action separately would silently reject
 * the ones the user had not looked at yet.
 */
function ApprovalsEntry({
  entry,
  onChoose,
  onSubmit,
}: {
  entry: Extract<Entry, { kind: "approvals" }>;
  onChoose: (toolCallId: string, approved: boolean) => void;
  onSubmit: () => void;
}) {
  const { approvals, choices, state, outcome } = entry;
  const undecided = approvals.filter((a) => choices[a.tool_call_id] === undefined).length;
  const busy = state === "submitting";

  if (state === "resolved" && outcome) {
    const gated = outcome.calls.filter((c) => c.requires_approval);
    const done = gated.filter((c) => c.status === "executed").length;
    const stopped = gated.length - done;

    return (
      <div className="approval approval--resolved">
        <div className="approval__head">
          {outcome.status === "partial" ? <IconPartial /> : <IconCheck />}
          {outcome.status === "partial"
            ? `Partly done — ${done} carried out, ${stopped} not`
            : `Done — ${done} action${done === 1 ? "" : "s"} carried out`}
        </div>
        <ul className="approval__outcomes">
          {gated.map((call) => {
            const label = OUTCOME_LABEL[call.status] ?? OUTCOME_LABEL.proposed!;
            return (
              <li key={call.tool_call_id}>
                <Badge tone={label.tone}>{label.text}</Badge>
                <span>{titleCase(call.tool_name)}</span>
                {call.error && <span className="approval__error">{call.error}</span>}
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div className="approval">
      <div className="approval__head">
        <IconShield />
        {approvals.length === 1
          ? "Approval needed"
          : `${approvals.length} actions need your approval`}
      </div>
      <p className="approval__desc">
        Nothing below has happened yet. Choose for each, then confirm.
      </p>

      {approvals.map((approval) => {
        const choice = choices[approval.tool_call_id];
        return (
          <div className="approval__item" key={approval.tool_call_id}>
            <div className="approval__item-head">
              <strong>{titleCase(approval.tool_name)}</strong>
              {choice !== undefined && (
                <Badge tone={choice ? "success" : "neutral"}>
                  {choice ? "Will approve" : "Will decline"}
                </Badge>
              )}
            </div>
            {approval.description && (
              <p className="approval__desc">{approval.description}</p>
            )}
            <div className="approval__args">
              {argEntries(approval.args).map(([key, value]) => (
                <div key={key} style={{ display: "contents" }}>
                  <span className="approval__arg-key">{key}</span>
                  <span className="approval__arg-value">{value}</span>
                </div>
              ))}
            </div>
            <div className="approval__actions">
              <Button
                variant={choice === true ? "primary" : "secondary"}
                size="sm"
                disabled={busy}
                aria-pressed={choice === true}
                onClick={() => onChoose(approval.tool_call_id, true)}
              >
                <IconCheck /> Approve
              </Button>
              <Button
                variant={choice === false ? "danger" : "secondary"}
                size="sm"
                disabled={busy}
                aria-pressed={choice === false}
                onClick={() => onChoose(approval.tool_call_id, false)}
              >
                <IconX /> Decline
              </Button>
            </div>
          </div>
        );
      })}

      <div className="approval__confirm">
        <Button variant="primary" disabled={busy || undecided > 0} onClick={onSubmit}>
          {busy
            ? "Working…"
            : undecided > 0
              ? `Choose ${undecided} more`
              : "Confirm"}
        </Button>
      </div>
    </div>
  );
}

export function Chat({
  entries,
  busy,
  onSend,
  onChoose,
  onSubmit,
}: {
  entries: Entry[];
  busy: boolean;
  onSend: (text: string) => void;
  onChoose: (entryId: string, toolCallId: string, approved: boolean) => void;
  onSubmit: (entryId: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [entries]);

  function submit() {
    const text = draft.trim();
    if (!text || busy) return;
    onSend(text);
    setDraft("");
    if (inputRef.current) inputRef.current.style.height = "auto";
  }

  return (
    <div className="chat">
      <div className="chat__log" ref={logRef}>
        {entries.length === 0 && (
          <div className="state" style={{ margin: "auto" }}>
            <span
              className="msg__avatar msg__avatar--agent"
              style={{ width: 38, height: 38, fontSize: 15 }}
            >
              A
            </span>
            <p className="state__title">Atlas is ready</p>
            <p className="state__body">
              Ask about your day, your pipeline or your inbox. Atlas reads the workspace before it
              answers, and asks before it sends anything on your behalf.
            </p>
          </div>
        )}

        {entries.map((entry) => {
          switch (entry.kind) {
            case "user":
              return (
                <div className="msg msg--user" key={entry.id}>
                  <span className="msg__avatar msg__avatar--user">FY</span>
                  <div className="msg__bubble">{entry.text}</div>
                </div>
              );
            case "agent":
              return <AgentEntry entry={entry} key={entry.id} />;
            case "approvals":
              return (
                <ApprovalsEntry
                  key={entry.id}
                  entry={entry}
                  onChoose={(toolCallId, approved) => onChoose(entry.id, toolCallId, approved)}
                  onSubmit={() => onSubmit(entry.id)}
                />
              );
            case "error":
              return (
                <div className="msg msg--agent" key={entry.id}>
                  <span
                    className="msg__avatar"
                    style={{ background: "var(--danger-soft)", color: "var(--danger)" }}
                  >
                    !
                  </span>
                  <div
                    className="msg__bubble"
                    style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
                  >
                    {entry.offline
                      ? "Can’t reach the Propilot API. Start it with `make run` and try again."
                      : entry.message}
                  </div>
                </div>
              );
          }
        })}
      </div>

      <div className="composer">
        {entries.length === 0 && (
          <div className="chips">
            {STARTERS.map((text) => (
              <button className="chip" key={text} onClick={() => onSend(text)} disabled={busy}>
                <IconSpark size={12} /> {text}
              </button>
            ))}
          </div>
        )}

        <div className="composer__box">
          <textarea
            ref={inputRef}
            className="composer__input"
            rows={1}
            value={draft}
            placeholder="Ask Atlas anything about your day…"
            aria-label="Message Atlas"
            onChange={(event) => {
              setDraft(event.target.value);
              const el = event.target;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
          />
          <Button variant="primary" onClick={submit} disabled={busy || !draft.trim()}>
            <IconSend />
            <span className="visually-hidden">Send</span>
          </Button>
        </div>
        <p className="composer__hint">
          Enter to send · Shift+Enter for a new line · Atlas asks before it acts
        </p>
      </div>
    </div>
  );
}
