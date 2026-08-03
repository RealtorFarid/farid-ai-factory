/**
 * Chat state: streaming a run, surfacing approvals, resuming after a decision.
 *
 * The transcript is a flat list of entries rather than a nested tree, because
 * an approval interleaves with the agent's prose and the user reads it in
 * order. A run that pauses appears as an approval entry the user can act on;
 * resolving it appends the continuation.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { startRunStream } from "@/lib/sse";
import type { PendingApproval, Run } from "@/lib/types";

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
      kind: "approval";
      id: string;
      runId: string;
      approval: PendingApproval;
      resolution: "pending" | "approved" | "denied" | "submitting";
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

  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: string, update: (entry: Entry) => Entry) => {
    setEntries((current) => current.map((entry) => (entry.id === id ? update(entry) : entry)));
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
              patch(agentId, (e) =>
                e.kind === "agent" ? { ...e, runId: event.run_id } : e,
              );
              break;

            case "run.token":
              patch(agentId, (e) =>
                e.kind === "agent" ? { ...e, text: e.text + (event.data.delta ?? "") } : e,
              );
              break;

            case "tool.called":
              patch(agentId, (e) =>
                e.kind === "agent" && event.data.tool_name
                  ? { ...e, tools: [...e.tools, event.data.tool_name] }
                  : e,
              );
              break;

            case "approval.required":
              setEntries((current) => [
                ...current,
                {
                  kind: "approval",
                  id: nextId(),
                  runId: event.run_id,
                  approval: {
                    tool_call_id: String(event.data.tool_call_id),
                    tool_name: String(event.data.tool_name),
                    args: (event.data.args ?? {}) as Record<string, unknown>,
                    description: String(event.data.description ?? ""),
                  },
                  resolution: "pending",
                },
              ]);
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
        // Drop any bubble that never produced text (an approval-only turn).
        setEntries((current) =>
          current.filter((e) => !(e.kind === "agent" && !e.text && !e.streaming && !e.tools.length)),
        );
        setBusy(false);
        abortRef.current = null;
      }
    },
    [agent, busy, patch],
  );

  /**
   * Resolve one approval and append the continuation.
   *
   * `POST /approvals` runs the agent to completion and returns the final run,
   * so the answer is taken from the response rather than re-opening a stream.
   */
  const resolve = useCallback(
    async (entryId: string, runId: string, toolCallId: string, approved: boolean) => {
      patch(entryId, (e) =>
        e.kind === "approval" ? { ...e, resolution: "submitting" } : e,
      );

      let run: Run;
      try {
        run = await api.resolveApprovals(runId, [{ tool_call_id: toolCallId, approved }]);
      } catch (error) {
        patch(entryId, (e) => (e.kind === "approval" ? { ...e, resolution: "pending" } : e));
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
        e.kind === "approval"
          ? { ...e, resolution: approved ? "approved" : "denied" }
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
            tools: run.tool_calls.filter((c) => c.approved !== false).map((c) => c.tool_name),
            streaming: false,
          },
        ]);
      }

      // A run can pause again if the agent proposes another gated action.
      for (const approval of run.pending_approvals) {
        setEntries((current) => [
          ...current,
          {
            kind: "approval",
            id: nextId(),
            runId: run.id,
            approval,
            resolution: "pending",
          },
        ]);
      }
    },
    [patch],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setEntries([]);
    setBusy(false);
  }, []);

  return { entries, busy, send, resolve, reset };
}
