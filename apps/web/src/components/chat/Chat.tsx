/** The conversation surface: streamed replies and inline approval gates. */

import { useEffect, useRef, useState } from "react";

import { IconCheck, IconSend, IconShield, IconSpark, IconTool, IconX } from "../layout/Icons";
import { Badge, Button } from "../ui";
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
  return (
    <div className="msg msg--agent">
      <span className="msg__avatar msg__avatar--agent">A</span>
      <div style={{ minWidth: 0 }}>
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

function ApprovalEntry({
  entry,
  onResolve,
}: {
  entry: Extract<Entry, { kind: "approval" }>;
  onResolve: (approved: boolean) => void;
}) {
  const { approval, resolution } = entry;
  const busy = resolution === "submitting";
  const decided = resolution === "approved" || resolution === "denied";

  return (
    <div className="approval">
      <div className="approval__head">
        <IconShield />
        Approval needed — {titleCase(approval.tool_name)}
      </div>
      {approval.description && <p className="approval__desc">{approval.description}</p>}

      <div className="approval__args">
        {argEntries(approval.args).map(([key, value]) => (
          <div key={key} style={{ display: "contents" }}>
            <span className="approval__arg-key">{key}</span>
            <span className="approval__arg-value">{value}</span>
          </div>
        ))}
      </div>

      {decided ? (
        <div
          className="approval__resolved"
          style={{ color: resolution === "approved" ? "var(--success)" : "var(--text-muted)" }}
        >
          {resolution === "approved" ? <IconCheck /> : <IconX />}
          {resolution === "approved" ? "Approved — Atlas carried this out." : "Denied."}
        </div>
      ) : (
        <div className="approval__actions">
          <Button variant="primary" size="sm" disabled={busy} onClick={() => onResolve(true)}>
            <IconCheck /> {busy ? "Working…" : "Approve"}
          </Button>
          <Button variant="danger" size="sm" disabled={busy} onClick={() => onResolve(false)}>
            <IconX /> Deny
          </Button>
        </div>
      )}
    </div>
  );
}

export function Chat({
  entries,
  busy,
  onSend,
  onResolve,
}: {
  entries: Entry[];
  busy: boolean;
  onSend: (text: string) => void;
  onResolve: (entryId: string, runId: string, toolCallId: string, approved: boolean) => void;
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
            case "approval":
              return (
                <ApprovalEntry
                  key={entry.id}
                  entry={entry}
                  onResolve={(approved) =>
                    onResolve(entry.id, entry.runId, entry.approval.tool_call_id, approved)
                  }
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
