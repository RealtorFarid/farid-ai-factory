export type AgentStatus =
  | "idle"
  | "planning"
  | "running"
  | "verifying"
  | "completed"
  | "failed";

export interface Goal {
  id: string;
  title: string;
  description?: string;
}

export interface Task {
  id: string;
  title: string;
  completed: boolean;
}

export class CoreEngine {
  private status: AgentStatus = "idle";

  start(goal: Goal) {
    this.status = "planning";

    console.log("=================================");
    console.log("🚀 AI Factory Core Engine");
    console.log("=================================");
    console.log("Goal:", goal.title);
    console.log("Status:", this.status);
  }

  setStatus(status: AgentStatus) {
    this.status = status;
  }

  getStatus() {
    return this.status;
  }
}