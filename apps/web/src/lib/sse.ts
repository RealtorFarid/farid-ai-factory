/**
 * Server-Sent Events over `fetch`.
 *
 * `EventSource` cannot issue a POST or send a body, and starting a run needs
 * both — so the wire format is parsed by hand. The same reader serves the POST
 * that starts a run and the GET that re-attaches to one, which is what lets the
 * UI follow a run across an approval pause.
 */

import { ApiError } from "./api";
import type { ApiErrorBody, RunEvent } from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export interface SseFrame {
  event: string;
  data: string;
  id: string | undefined;
}

/** Split a raw SSE buffer into frames, returning any incomplete remainder. */
function drainFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const frames: SseFrame[] = [];
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";

  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = "message";
    let id: string | undefined;
    const dataLines: string[] = [];

    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      else if (line.startsWith("id:")) id = line.slice(3).trim();
    }
    frames.push({ event, data: dataLines.join("\n"), id });
  }
  return { frames, rest };
}

async function* readFrames(response: Response, signal: AbortSignal): AsyncGenerator<SseFrame> {
  const reader = response.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const { frames, rest } = drainFrames(buffer);
      buffer = rest;
      for (const frame of frames) yield frame;
    }
  } finally {
    reader.cancel().catch(() => undefined);
  }
}

async function openStream(
  path: string,
  init: RequestInit,
  signal: AbortSignal,
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, signal });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new ApiError(0, null, "Cannot reach the Propilot API.");
  }

  if (!response.ok) {
    let body: { error?: ApiErrorBody } | null = null;
    try {
      body = (await response.json()) as { error?: ApiErrorBody };
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, body?.error ?? null, response.statusText);
  }
  return response;
}

function parseRunEvent(frame: SseFrame): RunEvent | null {
  try {
    return JSON.parse(frame.data) as RunEvent;
  } catch {
    return null;
  }
}

/** Start a run and stream its events. Resolves the run id from the response header. */
export async function* startRunStream(
  agent: string,
  prompt: string,
  options: { sessionId?: string; signal: AbortSignal },
): AsyncGenerator<RunEvent> {
  const response = await openStream(
    `/v1/agents/${encodeURIComponent(agent)}/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        ...(options.sessionId ? { session_id: options.sessionId } : {}),
      }),
    },
    options.signal,
  );

  for await (const frame of readFrames(response, options.signal)) {
    const event = parseRunEvent(frame);
    if (event) yield event;
  }
}

/** Re-attach to an existing run, optionally resuming after a known sequence. */
export async function* followRunStream(
  runId: string,
  options: { lastEventId?: number; signal: AbortSignal },
): AsyncGenerator<RunEvent> {
  const headers: Record<string, string> = {};
  if (options.lastEventId !== undefined) {
    headers["Last-Event-ID"] = String(options.lastEventId);
  }

  const response = await openStream(
    `/v1/runs/${encodeURIComponent(runId)}/events`,
    { method: "GET", headers },
    options.signal,
  );

  for await (const frame of readFrames(response, options.signal)) {
    const event = parseRunEvent(frame);
    if (event) yield event;
  }
}
