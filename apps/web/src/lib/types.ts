/**
 * Mirrors the backend API contracts.
 *
 * These are hand-maintained against the FastAPI schemas in
 * `backend/src/backend/api/schemas.py` and `runtime/workspace/models.py`.
 * Generating them from `/openapi.json` is a Phase 4 task; until then a
 * contract change breaks the TypeScript build rather than the running UI.
 */

// ---- Workspace -----------------------------------------------------------

export type TaskPriority = "low" | "medium" | "high";
export type TaskStatus = "todo" | "in_progress" | "done";

export interface Task {
  id: string;
  title: string;
  due_at: string;
  priority: TaskPriority;
  status: TaskStatus;
  lead_id: string | null;
}

export type LeadStage =
  | "new"
  | "contacted"
  | "qualified"
  | "showing"
  | "offer"
  | "closed"
  | "lost";

export interface Lead {
  id: string;
  name: string;
  email: string;
  phone: string;
  stage: LeadStage;
  budget_min: number;
  budget_max: number;
  last_contact_at: string;
  score: number;
  notes: string;
}

export interface LeadSummary {
  total: number;
  by_stage: Record<string, number>;
  new_this_week: number;
  needs_follow_up: number;
  hottest: Lead[];
}

export interface EmailThread {
  id: string;
  subject: string;
  sender: string;
  preview: string;
  received_at: string;
  unread: boolean;
  needs_response: boolean;
  lead_id: string | null;
}

export interface EmailSummary {
  unread: number;
  needs_response: number;
  threads: EmailThread[];
}

export type EventKind = "showing" | "call" | "meeting" | "open_house";

export interface CalendarEvent {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  location: string;
  kind: EventKind;
  lead_id: string | null;
}

export interface CalendarSummary {
  today_count: number;
  next_event: CalendarEvent | null;
  events: CalendarEvent[];
}

export type Impact = "low" | "medium" | "high";

export interface Suggestion {
  id: string;
  title: string;
  rationale: string;
  impact: Impact;
  prompt: string;
}

export interface Dashboard {
  generated_at: string;
  tasks: Task[];
  leads: LeadSummary;
  emails: EmailSummary;
  calendar: CalendarSummary;
  suggestions: Suggestion[];
}

// ---- Agents and runs -----------------------------------------------------

export type RunStatus =
  | "running"
  | "awaiting_approval"
  | "completed"
  /** Finished, but at least one proposed action was denied or failed. */
  | "partial"
  | "failed";

export type ToolCallStatus = "proposed" | "executed" | "denied" | "failed";

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  requests: number;
}

export interface PendingApproval {
  tool_call_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  description: string;
}

export interface ToolCall {
  tool_name: string;
  tool_call_id: string;
  args: Record<string, unknown>;
  status: ToolCallStatus;
  approved: boolean | null;
  error: string | null;
  requires_approval: boolean;
}

export interface Run {
  id: string;
  agent: string;
  model: string;
  status: RunStatus;
  prompt: string;
  session_id: string | null;
  output: string | null;
  error: string | null;
  error_code: string | null;
  usage: Usage | null;
  duration_ms: number;
  created_at: string;
  updated_at: string;
  pending_approvals: PendingApproval[];
  tool_calls: ToolCall[];
}

export interface AgentInfo {
  name: string;
  description: string;
  model: string;
}

export interface ToolInfo {
  name: string;
  description: string;
  category: string;
  requires_approval: boolean;
}

// ---- Run events (SSE) ----------------------------------------------------

export type RunEventType =
  | "run.started"
  | "run.token"
  | "run.completed"
  | "run.failed"
  | "run.resumed"
  /** A gated tool the agent wants to call. Nothing has run yet. */
  | "tool.proposed"
  /** An ungated tool the agent invoked directly. */
  | "tool.called"
  /** A tool returned. Any effect has now actually happened. */
  | "tool.executed"
  | "tool.failed"
  | "approval.required"
  | "approval.resolved";

export interface RunEvent {
  type: RunEventType;
  run_id: string;
  sequence: number;
  created_at: string;
  data: {
    delta?: string;
    output?: string;
    code?: string;
    message?: string;
    tool_name?: string;
    tool_call_id?: string;
    args?: Record<string, unknown>;
    description?: string;
    approved?: boolean;
    reason?: string | null;
    usage?: Usage;
    [key: string]: unknown;
  };
}

// ---- Errors --------------------------------------------------------------

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string;
  details?: { location: string[]; message: string; type: string }[];
}
