/**
 * Chat state: streaming a run, surfacing approvals, resuming after a decision.
 *
 * The transcript is a flat list of entries rather than a nested tree, because
 * an approval interleaves with the agent's prose and the user reads it in
 * order.
 *
 * Every gated action a run proposes is collected into **one** approval entry
 * with a single confirm step. Submitting per-action would be wrong: the API
 * denies anything left out of a decision set, so resolving one card would
 * silently reject the others before the user had looked at them.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { startRunStream } from "@/lib/sse";
import type { PendingApproval, Run, RunStatus, ToolCall } from "@/lib/types";

export type Entry =
  | { kind: "user"; id: string; text: string }
  | {
      kind: "agent";
      id: string;
      runId: string | null;
      text: string;
      tools: string[];
      streaming: boolean;
    }
  | {
      kind: "approvals";
      id: string;
      runId: string;
      approvals: PendingApproval[];
      /** tool_call_id -> the user's choice, before submitting. */
      choices: Record<string, boolean>;
      state: "deciding" | "submitting" | "resolved";
      outcome: { status: RunStatus; calls: ToolCall[] } | null;
    }
  | { kind: "error"; id: string; message: string; offline: boolean };

let counter = 0;
const nextId = () => `e${++counter}`;

function sessionId(): string {
  const key = "propilot.session";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  sessionStorage.setItem(key, created);
  return created;
}

export function useChat(agent = "atlas") {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Mirror of `entries` for callbacks that need to read current state without
  // taking it as a dependency. A `setEntries` updater cannot be used for this:
  // it runs during the next render, not at the call site.
  const entriesRef = useRef<Entry[]>(entries);
  entriesRef.current = entries;

  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: string, update: (entry: Entry) => Entry) => {
    setEntries((current) => current.map((entry) => (entry.id === id ? update(entry) : entry)));
  }, []);

  /** Add a proposed action to this run's approval entry, creating it if needed. */
  const addApproval = useCallback((runId: string, approval: PendingApproval) => {
    setEntries((current) => {
      const existing = current.find(
        (e) => e.kind === "approvals" && e.runId === runId && e.state === "deciding",
      );
      if (existing && existing.kind === "approvals") {
        if (existing.approvals.some((a) => a.tool_call_id === approval.tool_call_id)) {
          return current;
        }
        return current.map((e) =>
          e === existing ? { ...e, approvals: [...e.approvals, approval] } : e,
        );
      }
      return [
        ...current,
        {
          kind: "approvals",
          id: nextId(),
          runId,
          approvals: [approval],
          choices: {},
          state: "deciding",
          outcome: null,
        },
      ];
    });
  }, []);

  const send = useCallback(
    async (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed || busy) return;

      const agentId = nextId();
      setEntries((current) => [
        ...current,
        { kind: "user", id: nextId(), text: trimmed },
        { kind: "agent", id: agentId, runId: null, text: "", tools: [], streaming: true },
      ]);
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const event of startRunStream(agent, trimmed, {
          sessionId: sessionId(),
          signal: controller.signal,
        })) {
          switch (event.type) {
            case "run.started":
              patch(agentId, (e) => (e.kind === "agent" ? { ...e, runId: event.run_id } : e));
              break;

            case "run.token":
              patch(agentId, (e) =>
                e.kind === "agent" ? { ...e, text: e.text + (event.data.delta ?? "") } : e,
              );
              break;

            // Only executed tools become chips. A proposed call has not run,
            // and showing it as activity would misrepresent the gate.
            case "tool.executed":
              patch(agentId, (e) =>
                e.kind === "agent" && event.data.tool_name
                  ? { ...e, tools: [...e.tools, event.data.tool_name] }
                  : e,
              );
              break;

            case "approval.required":
              addApproval(event.run_id, {
                tool_call_id: String(event.data.tool_call_id),
                tool_name: String(event.data.tool_name),
                args: (event.data.args ?? {}) as Record<string, unknown>,
                description: String(event.data.description ?? ""),
              });
              patch(agentId, (e) => (e.kind === "agent" ? { ...e, streaming: false } : e));
              break;

            case "run.completed":
              patch(agentId, (e) =>
                e.kind === "agent"
                  ? { ...e, streaming: false, text: e.text || String(event.data.output ?? "") }
                  : e,
              );
              break;

            case "run.failed":
              patch(agentId, (e) => (e.kind === "agent" ? { ...e, streaming: false } : e));
              setEntries((current) => [
                ...current,
                {
                  kind: "error",
                  id: nextId(),
                  message: String(event.data.message ?? "The run failed."),
                  offline: false,
                },
              ]);
              break;

            default:
              break;
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          patch(agentId, (e) => (e.kind === "agent" ? { ...e, streaming: false } : e));
          setEntries((current) => [
            ...current,
            {
              kind: "error",
              id: nextId(),
              message:
                error instanceof Error ? error.message : "Could not reach the Propilot API.",
              offline: error instanceof ApiError && error.isOffline,
            },
          ]);
        }
      } finally {
        // Drop a bubble that produced nothing (an approval-only turn).
        setEntries((current) =>
          current.filter(
            (e) => !(e.kind === "agent" && !e.text && !e.streaming && !e.tools.length),
          ),
        );
        setBusy(false);
        abortRef.current = null;
      }
    },
    [agent, busy, patch, addApproval],
  );

  /** Record a choice for one proposed action, before the batch is submitted. */
  const choose = useCallback(
    (entryId: string, toolCallId: string, approved: boolean) => {
      patch(entryId, (e) =>
        e.kind === "approvals"
          ? { ...e, choices: { ...e.choices, [toolCallId]: approved } }
          : e,
      );
    },
    [patch],
  );

  /**
   * Submit every decision for a run at once, then append the continuation.
   *
   * `POST /approvals` runs the agent to completion and returns the final run,
   * so the answer comes from the response rather than a second stream.
   */
  const submit = useCallback(
    async (entryId: string) => {
      const entry = entriesRef.current.find((e) => e.id === entryId);
      if (!entry || entry.kind !== "approvals") return;

      const { runId, approvals, choices } = entry;
      if (approvals.some((a) => choices[a.tool_call_id] === undefined)) return;

      patch(entryId, (e) => (e.kind === "approvals" ? { ...e, state: "submitting" } : e));

      let run: Run;
      try {
        run = await api.resolveApprovals(
          runId,
          approvals.map((a) => ({
            tool_call_id: a.tool_call_id,
            approved: choices[a.tool_call_id] ?? false,
          })),
        );
      } catch (error) {
        patch(entryId, (e) => (e.kind === "approvals" ? { ...e, state: "deciding" } : e));
        setEntries((current) => [
          ...current,
          {
            kind: "error",
            id: nextId(),
            message: error instanceof Error ? error.message : "Could not submit the decision.",
            offline: error instanceof ApiError && error.isOffline,
          },
        ]);
        return;
      }

      patch(entryId, (e) =>
        e.kind === "approvals"
          ? { ...e, state: "resolved", outcome: { status: run.status, calls: run.tool_calls } }
          : e,
      );

      if (run.output) {
        setEntries((current) => [
          ...current,
          {
            kind: "agent",
            id: nextId(),
            runId: run.id,
            text: run.output ?? "",
            tools: run.tool_calls
              .filter((c) => c.status === "executed")
              .map((c) => c.tool_name),
            streaming: false,
          },
        ]);
      }

      // A run can pause again if the agent proposes further gated actions.
      for (const approval of run.pending_approvals) {
        addApproval(run.id, approval);
      }
    },
    [patch, addApproval],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setEntries([]);
    setBusy(false);
  }, []);

  return { entries, busy, send, choose, submit, reset };
}
