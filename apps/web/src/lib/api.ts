/**
 * Typed API client.
 *
 * Every call goes through `request`, so error handling, the error envelope and
 * the request id are handled in exactly one place. Callers get either data or
 * an `ApiError` — never a half-parsed response.
 */

import type {
  AgentInfo,
  ApiErrorBody,
  CalendarSummary,
  CaptureResult,
  ClaimInfo,
  Dashboard,
  EmailSummary,
  Lead,
  LeadSummary,
  Run,
  Suggestion,
  Task,
  ToolInfo,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | undefined;

  constructor(status: number, body: Partial<ApiErrorBody> | null, fallback: string) {
    super(body?.message ?? fallback);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? "unknown_error";
    this.requestId = body?.request_id;
  }

  /** True when the API could not be reached at all, rather than refusing. */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        // FormData sets its own Content-Type, including the boundary.
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, null, "Cannot reach the Propilot API.");
  }

  if (!response.ok) {
    let body: { error?: ApiErrorBody } | null = null;
    try {
      body = (await response.json()) as { error?: ApiErrorBody };
    } catch {
      // A non-JSON error body (a proxy 502, say) is still an error.
    }
    throw new ApiError(response.status, body?.error ?? null, response.statusText);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  // ---- Workspace ---------------------------------------------------------
  dashboard: () => request<Dashboard>("/v1/workspace/dashboard"),
  tasks: () => request<Task[]>("/v1/workspace/tasks"),
  leads: () => request<Lead[]>("/v1/workspace/leads"),
  leadSummary: () => request<LeadSummary>("/v1/workspace/leads/summary"),
  emailSummary: (limit = 10) =>
    request<EmailSummary>(`/v1/workspace/email/summary?limit=${limit}`),
  calendarSummary: (days = 7) =>
    request<CalendarSummary>(`/v1/workspace/calendar/summary?days=${days}`),
  suggestions: () => request<Suggestion[]>("/v1/workspace/suggestions"),

  // ---- Capture -----------------------------------------------------------
  capture: (leadId: string, note: string) =>
    request<CaptureResult>("/v1/capture", {
      method: "POST",
      body: JSON.stringify({ lead_id: leadId, note }),
    }),
  leadClaims: (leadId: string) =>
    request<ClaimInfo[]>(`/v1/leads/${encodeURIComponent(leadId)}/claims`),

  captureVoice: (leadId: string, audio: Blob, filename: string) => {
    const form = new FormData();
    form.append("lead_id", leadId);
    form.append("audio", audio, filename);
    // No Content-Type header: the browser must set the multipart boundary.
    return request<CaptureResult>("/v1/capture/voice", { method: "POST", body: form });
  },

  // ---- Agents ------------------------------------------------------------
  agents: () => request<{ agents: AgentInfo[]; default: string }>("/v1/agents"),
  tools: () => request<{ tools: ToolInfo[] }>("/v1/agents/tools"),

  // ---- Runs --------------------------------------------------------------
  runs: (limit = 25) => request<{ runs: Run[] }>(`/v1/runs?limit=${limit}`),
  run: (id: string) => request<Run>(`/v1/runs/${id}`),

  resolveApprovals: (
    runId: string,
    decisions: { tool_call_id: string; approved: boolean; reason?: string }[],
  ) =>
    request<Run>(`/v1/runs/${runId}/approvals`, {
      method: "POST",
      body: JSON.stringify({ decisions }),
    }),
};

export { BASE as API_BASE };
