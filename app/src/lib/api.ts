const BASE = process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8123";

export type Resource = {
  resource_id: string;
  resource_type: string;
  name: string | null;
  state: string | null;
  region: string;
  size_gb: number | null;
  attached_to: string | null;
  estimated_monthly_cost: number | null;
  billing_while_stopped: boolean;
  tags: Record<string, string>;
};

export type Evidence = {
  metric_window_days: number;
  avg_cpu_percent: number | null;
  max_cpu_percent: number | null;
  idle_days: number | null;
  network_in_bytes: number | null;
  network_out_bytes: number | null;
  estimated_monthly_cost: number | null;
  billing_while_stopped: boolean;
};

export type Recommendation = {
  action: "keep" | "investigate_more" | "stop" | "retire";
  reason: string;
  confidence: number;
  severity: "low" | "medium" | "high";
  estimated_monthly_saving: number;
};

export type Step = {
  order: number;
  action: string;
  resource_id: string;
  resource_type: string;
  reason: string;
  monthly_saving: number;
  reversible: boolean;
};

export type Plan = {
  root_resource_id: string;
  steps: Step[];
  blocked: string[];
  restore: Record<string, unknown> | null;
};

export type ReasoningEvent = {
  ts: string;
  node: string;
  event: string;
  resource_id: string;
  message: string;
};

export type SweepRow = {
  resource_id: string;
  action: Recommendation["action"] | null;
  severity: string | null;
  confidence: number | null;
  reason: string | null;
  steps: number;
  blocked: string[];
  monthly_saving: number;
};

export type SweepResult = {
  results: SweepRow[];
  recoverable_monthly: number;
  recoverable_yearly: number;
  reasoning: ReasoningEvent[];
};

export type Run = {
  run_id: string;
  at: string;
  dry_run: boolean;
  resource_id: string;
  resource_type: string;
  resource_name: string | null;
  verdict: string | null;
  severity: string | null;
  reason: string | null;
  planned_steps: number;
  blocked: string[];
  monthly_saving: number;
  decision: string | null;
  approved_by: string | null;
  executed: number;
  verified: boolean | null;
};

export type HistoryTotals = {
  runs: number;
  approved: number;
  kept: number;
  blocked: number;
  realised_monthly: number;
  simulated_monthly: number;
};

export type Investigation = {
  thread_id: string;
  resource: Resource;
  evidence: Evidence | null;
  recommendation: Recommendation | null;
  plan: Plan | null;
  awaiting_approval: boolean;
  reasoning: ReasoningEvent[];
};

export type ApprovalResult = {
  decision: string;
  reason: string | null;
  action_results: { action: string; resource_id: string; ok: boolean; detail: string; dry_run: boolean }[];
  verification_passed: boolean | null;
  reasoning: ReasoningEvent[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  inventory: (refresh = false) =>
    req<{ resources: Resource[]; total_monthly: number; wasting: string[] }>(
      `/inventory${refresh ? "?refresh=true" : ""}`
    ),
  investigate: (resource_id: string, force_plan = false) =>
    req<Investigation>("/investigate", {
      method: "POST",
      body: JSON.stringify({ resource_id, force_plan }),
    }),
  sweep: () => req<SweepResult>("/sweep", { method: "POST" }),
  history: (limit = 50) =>
    req<{ runs: Run[]; totals: HistoryTotals }>(`/history?limit=${limit}`),
  approve: (thread_id: string, command: string) =>
    req<ApprovalResult>("/approve", {
      method: "POST",
      body: JSON.stringify({ thread_id, command }),
    }),
};

export const money = (n: number | null | undefined) =>
  `$${(n ?? 0).toFixed(2)}`;
