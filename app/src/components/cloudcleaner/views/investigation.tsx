"use client";

import {
  money,
  type ApprovalResult,
  type Evidence,
  type GitHubEvidence,
  type Investigation,
  type ReasoningEvent,
  type ThreadStatus,
} from "@/lib/api";
import { Button, Empty, Tag, type Tone } from "../primitives";

const VERDICT_TONE: Record<string, Tone> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

const SEVERITY_TONE: Record<string, Tone> = {
  low: "muted", medium: "warn", high: "danger",
};

function ago(iso: string | null): string | null {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days < 1) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

/** One evidence line: label, value, and an optional reading of what it means. */
function Signal({
  label, value, tone, note,
}: { label: string; value: string; tone?: string; note?: string }) {
  return (
    <div className="flex items-start gap-3 py-1.5">
      <span className="w-[105px] shrink-0 text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
        {label}
      </span>
      <span className="mono shrink-0 text-[14px]" style={{ color: tone ?? "var(--fg)" }}>
        {value}
      </span>
      {note && (
        <span className="min-w-0 text-[13.5px] leading-snug" style={{ color: "var(--fg-faint)" }}>
          {note}
        </span>
      )}
    </div>
  );
}

function AwsEvidence({ e }: { e: Evidence }) {
  const idle = e.idle_days;

  return (
    <div className="space-y-0.5">
      <Signal
        label="Average CPU"
        value={e.avg_cpu_percent === null ? "no data" : `${e.avg_cpu_percent}%`}
        tone={e.avg_cpu_percent !== null && e.avg_cpu_percent < 2 ? "var(--danger)" : undefined}
        note={e.avg_cpu_percent === null ? "this resource type emits no CPU metrics" : undefined}
      />
      <Signal
        label="Peak CPU"
        value={e.max_cpu_percent === null ? "no data" : `${e.max_cpu_percent}%`}
      />
      <Signal
        label="Idle for"
        value={idle === null ? "unknown" : `${idle} days`}
        tone={(idle ?? 0) >= 30 ? "var(--danger)" : (idle ?? 0) >= 14 ? "var(--warn)" : undefined}
        note={(idle ?? 0) >= 30 ? "no measurable activity in a month" : undefined}
      />
      <Signal
        label="Window"
        value={`${e.metric_window_days} days`}
      />
    </div>
  );
}

function GithubEvidencePanel({ g }: { g: GitHubEvidence }) {
  if (!g.repo) {
    return (
      <p className="text-[13.5px] leading-relaxed" style={{ color: "var(--fg-faint)" }}>
        No <span className="mono">Repo</span> tag is attached to this resource.
        AWS evidence alone is used for the recommendation.
      </p>
    );
  }

  const commit = ago(g.latest_commit_at);
  const active = g.branch_exists === true || g.pr_status === "open";

  return (
    <div className="space-y-0.5">
      <div className="mb-2 flex items-center justify-between gap-3">
        <a
          href={`https://github.com/${g.repo}`}
          target="_blank"
          rel="noreferrer"
          className="mono truncate text-[14px] underline decoration-dotted underline-offset-2"
          style={{ color: "var(--primary)" }}
        >
          {g.repo}
        </a>

        <Tag tone={active ? "ok" : "danger"} dot>
          {active ? "project alive" : "project finished"}
        </Tag>
      </div>

      <Signal
        label="Last commit"
        value={commit ?? "unknown"}
        tone={commit && commit.includes("mo") ? "var(--danger)" : undefined}
      />

      {g.branch && (
        <Signal
          label="Branch"
          value={g.branch}
          tone={g.branch_exists === false ? "var(--danger)" : undefined}
          note={g.branch_exists === false ? "deleted" : "still exists"}
        />
      )}

      {g.pr_number !== null && (
        <Signal
          label={`PR #${g.pr_number}`}
          value={g.pr_status ?? "unknown"}
          tone={g.pr_status === "open" ? "var(--ok)" : "var(--danger)"}
        />
      )}

      <Signal
        label="Last CI run"
        value={ago(g.last_workflow_run_at) ?? "never"}
        note={g.scheduled_workflow_exists ? "scheduled workflow still exists" : undefined}
      />
    </div>
  );
}

type TraceState = "done" | "current" | "muted" | "error";

type TraceItem = {
  label: string;
  detail?: string;
  state: TraceState;
};

function Trace({
  data,
  result,
  status,
}: {
  data: Investigation;
  result: ApprovalResult | null;
  status: ThreadStatus | null;
}) {
  const rec = data.recommendation;
  const reasoning: ReasoningEvent[] = status?.reasoning?.length
    ? status.reasoning
    : result?.reasoning?.length
      ? result.reasoning
      : data.reasoning;

  const decision = status?.decision ?? result?.decision ?? null;
  const actionResults = status?.action_results?.length
    ? status.action_results
    : result?.action_results ?? [];

  const verified = status
    ? status.verification_passed
    : result?.verification_passed ?? null;

  const ownerNotification = [...reasoning]
    .reverse()
    .find((e) => e.node === "notify");

  const items: TraceItem[] = [
    {
      label: "Resource detected",
      detail: data.resource.resource_id,
      state: "done",
    },
    {
      label: "Cloud evidence collected",
      detail: data.github?.repo ? "AWS, GitHub and CI/CD evidence" : "AWS evidence",
      state: "done",
    },
  ];

  if (rec) {
    items.push({
      label: "Recommendation generated",
      detail: `${rec.action.replace("_", " ").toUpperCase()} · ${Math.round(rec.confidence * 100)}% confidence`,
      state: "done",
    });
  }

  if (data.plan?.blocked.length) {
    items.push({
      label: "Safety policy blocked teardown",
      detail: data.plan.blocked[0],
      state: "done",
    });
  } else if (data.plan?.steps.length) {
    items.push({
      label: "Dependency-safe plan built",
      detail: `${data.plan.steps.length} ordered step${data.plan.steps.length === 1 ? "" : "s"}`,
      state: "done",
    });
  }

  if (ownerNotification) {
    items.push({
      label: ownerNotification.event === "error" ? "Owner notification failed" : "Owner notified by email",
      detail: ownerNotification.message,
      state: ownerNotification.event === "error" ? "error" : "done",
    });
  }

  if (decision === "reject") {
    items.push({
      label: "Human decision: Rejected",
      detail: "Rejected via Slack",
      state: "done",
    });
    items.push({
      label: "Execution skipped",
      detail: "No AWS action was performed",
      state: "muted",
    });
    items.push({
      label: "Decision recorded",
      state: "done",
    });
  } else if (decision === "approve") {
    items.push({
      label: "Human decision: Approved",
      detail: status?.approved_by?.startsWith("slack:") ? "Approved via Slack" : "Approved by human",
      state: "done",
    });

    if (!actionResults.length && status?.phase !== "completed") {
      items.push({
        label: "Executing teardown",
        state: "current",
      });
    }

    for (const action of actionResults) {
      items.push({
        label: action.action.replaceAll("_", " "),
        detail: action.dry_run ? `Simulated · ${action.detail}` : action.detail,
        state: action.ok ? "done" : "error",
      });
    }

    if (actionResults.length && verified !== null) {
      items.push({
        label: verified ? "Verification passed" : "Verification failed",
        detail: actionResults.some((a) => a.dry_run)
          ? "Dry run verification"
          : "AWS state checked after execution",
        state: verified ? "done" : "error",
      });
    }

    if (status?.phase === "completed") {
      items.push({
        label: "Workflow completed",
        state: "done",
      });
    }
  } else if (data.awaiting_approval || status?.awaiting_approval) {
    items.push({
      label: "Waiting for human approval",
      detail: "Approve, Reject, or Email Owner from Slack",
      state: "current",
    });
  } else if (rec?.action === "keep" || rec?.action === "investigate_more") {
    items.push({
      label: "No destructive action required",
      detail: rec.action === "keep" ? "Resource remains in place" : "More evidence is required",
      state: "done",
    });
  }

  return (
    <ol className="mt-3 space-y-0">
      {items.map((item, i) => {
        const done = item.state === "done";
        const current = item.state === "current";
        const error = item.state === "error";

        return (
          <li key={`${item.label}-${i}`} className="relative flex gap-3 pb-4">
            {i < items.length - 1 && (
              <span
                aria-hidden="true"
                className="absolute left-[7px] top-[17px] bottom-0 w-px"
                style={{ background: "var(--border-strong)" }}
              />
            )}

            <span
              aria-hidden="true"
              className={current ? "pulse mt-1 h-[15px] w-[15px] shrink-0 rounded-full" : "mt-1 grid h-[15px] w-[15px] shrink-0 place-items-center rounded-full text-[9px]"}
              style={{
                background: error
                  ? "var(--danger)"
                  : done
                    ? "var(--ok)"
                    : current
                      ? "var(--primary)"
                      : "var(--surface-3)",
                color: "var(--bg)",
                border: `1px solid ${
                  error
                    ? "var(--danger)"
                    : done
                      ? "var(--ok)"
                      : current
                        ? "var(--primary)"
                        : "var(--border-strong)"
                }`,
              }}
            >
              {done ? "✓" : error ? "!" : ""}
            </span>

            <div className="min-w-0">
              <div
                className="text-[14px] font-medium capitalize"
                style={{
                  color: error
                    ? "var(--danger)"
                    : current
                      ? "var(--primary)"
                      : item.state === "muted"
                        ? "var(--fg-faint)"
                        : "var(--fg)",
                }}
              >
                {item.label}
              </div>

              {item.detail && (
                <div className="mt-0.5 text-[13.5px] leading-snug" style={{ color: "var(--fg-faint)" }}>
                  {item.detail}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function InvestigationView({
  data,
  result,
  threadStatus,
  onForcePlan,
  onReinvestigate,
  onClose,
  busy,
  stale,
  cachedAt,
}: {
  data: Investigation | null;
  result: ApprovalResult | null;
  threadStatus: ThreadStatus | null;
  busy: boolean;
  stale: boolean;
  cachedAt: number | null;
  onForcePlan: () => void;
  onReinvestigate: () => void;
  onClose: () => void;
}) {
  if (busy && !data) {
    return (
      <div className="flex h-full flex-col">
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <div className="text-[16px] font-semibold">Investigating resource</div>
            <div className="mt-1 text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
              Querying AWS, GitHub and lifecycle evidence…
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close investigation"
            title="Close investigation"
            className="grid h-10 w-10 shrink-0 place-items-center text-[28px] font-light transition-colors duration-150"
            style={{
              color: "var(--fg)",
              background: "var(--surface-2)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius)",
            }}
          >
            ×
          </button>
        </div>

        <Empty>CloudCleaner is building the evidence package…</Empty>
      </div>
    );
  }

  if (!data) {
    return <Empty>Select a resource to investigate it.</Empty>;
  }

  const { resource: r, evidence, github, recommendation: rec, plan } = data;
  const total = plan?.steps.reduce((s, x) => s + x.monthly_saving, 0) ?? 0;
  const irreversible = plan?.steps.filter((s) => !s.reversible).length ?? 0;

  const recommendedSaving = rec?.action === "stop"
    ? (r.monthly_saving_if_stopped ?? rec.estimated_monthly_saving)
    : rec?.action === "retire"
      ? (total || rec.estimated_monthly_saving)
      : 0;

  const costAfterAction = rec?.action === "stop"
    ? r.monthly_cost_if_stopped
    : rec?.action === "retire"
      ? Math.max((r.estimated_monthly_cost ?? 0) - recommendedSaving, 0)
      : null;

  const cachedMinutes = cachedAt === null
    ? null
    : Math.max(0, Math.floor((Date.now() - cachedAt) / 60_000));

  const decision = threadStatus?.decision ?? result?.decision ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className="flex shrink-0 items-start justify-between gap-3 px-5 py-4"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}
      >
        <div className="min-w-0">
          <div className="mono truncate text-[15px] font-semibold">{r.resource_id}</div>
          <div className="mt-1 truncate text-[13.5px]" style={{ color: "var(--fg-muted)" }}>
            {r.name || "untagged"} · {r.resource_type.toUpperCase()} · {r.region}
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close investigation"
          className="grid h-8 w-8 shrink-0 place-items-center text-[21px]"
          style={{ color: "var(--fg-muted)", borderRadius: "var(--radius)" }}
        >
          ×
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {(cachedAt !== null || stale) && (
          <div
            className="flex flex-wrap items-center justify-between gap-2 px-5 py-2.5"
            style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
          >
            <span className="text-[13.5px]" style={{ color: stale ? "var(--warn)" : "var(--fg-faint)" }}>
              {stale
                ? "Inventory changed since this investigation."
                : `Cached investigation · ${
                    cachedMinutes === 0 ? "less than a minute ago" : `${cachedMinutes}m ago`
                  }`}
            </span>

            <Button onClick={onReinvestigate}>
              {stale ? "Re-investigate" : "Analyse again"}
            </Button>
          </div>
        )}

        {rec && (
          <section className="p-5">
            <div
              className="p-5"
              style={{
                background: "var(--surface-2)",
                border: `1px solid ${
                  rec.action === "keep" ? "var(--ok)" : rec.action === "retire" ? "var(--danger)" : "var(--border)"
                }`,
                borderRadius: "var(--radius)",
              }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Tag tone={VERDICT_TONE[rec.action]} dot>
                  {rec.action.replace("_", " ")}
                </Tag>
                <Tag tone={SEVERITY_TONE[rec.severity]}>{rec.severity} risk</Tag>
                <span className="num text-[13.5px]" style={{ color: "var(--fg-muted)" }}>
                  {Math.round(rec.confidence * 100)}% confidence
                </span>
              </div>

              <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <div className="text-[13.5px] uppercase tracking-[0.08em]" style={{ color: "var(--fg-faint)" }}>
                    Potential saving
                  </div>
                  <div className="num mt-1 text-[36px] font-semibold leading-none" style={{ color: "var(--ok)" }}>
                    {money(recommendedSaving)}
                    <span className="ml-1 text-[14px] font-normal" style={{ color: "var(--fg-faint)" }}>
                      /mo
                    </span>
                  </div>
                  <div className="num mt-2 text-[14px]" style={{ color: "var(--fg-muted)" }}>
                    {money(recommendedSaving * 12)} per year
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
                    Current → after action
                  </div>
                  <div className="num mt-1 text-[17px] font-semibold">
                    {money(r.estimated_monthly_cost)}
                    <span className="mx-2" style={{ color: "var(--fg-faint)" }}>→</span>
                    {money(costAfterAction)}
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {rec && (
          <section
            className="px-5 pb-5"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="text-[15px] font-semibold">Why CloudCleaner flagged it</h2>
            <p className="mt-2 text-[14px] leading-relaxed" style={{ color: "var(--fg-muted)" }}>
              {rec.reason}
            </p>

            <div className="mt-4 grid gap-2">
              <details
                className="px-4 py-3"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                }}
              >
                <summary className="cursor-pointer text-[14px] font-medium">
                  AWS evidence
                </summary>
                <div className="mt-3">
                  {evidence ? <AwsEvidence e={evidence} /> : (
                    <p className="text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
                      No AWS evidence available.
                    </p>
                  )}
                </div>
              </details>

              <details
                className="px-4 py-3"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                }}
              >
                <summary className="cursor-pointer text-[14px] font-medium">
                  Code & CI/CD evidence
                </summary>
                <div className="mt-3">
                  {github ? <GithubEvidencePanel g={github} /> : (
                    <p className="text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
                      No code evidence available.
                    </p>
                  )}
                </div>
              </details>
            </div>
          </section>
        )}

        {plan && plan.blocked.length > 0 && (
          <section
            className="px-5 py-5"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="text-[15px] font-semibold">Safety policy</h2>

            <div className="mt-3">
              <Tag tone="ok" dot>blocked by policy</Tag>
            </div>

            <ul className="mt-3 space-y-1">
              {plan.blocked.map((b) => (
                <li key={b} className="text-[14px]" style={{ color: "var(--fg-muted)" }}>
                  · {b}
                </li>
              ))}
            </ul>

            <p className="mt-3 text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
              Deterministic rules, evaluated outside the model. Neither the agent nor a human
              can override them here.
            </p>
          </section>
        )}

        {!plan?.steps.length && !plan?.blocked.length && rec && (
          <section
            className="px-5 py-5"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="text-[15px] font-semibold">Teardown plan</h2>
            <p className="mt-2 text-[14px]" style={{ color: "var(--fg-muted)" }}>
              No teardown is required for the current recommendation.
            </p>

            <div className="mt-3">
              <Button onClick={onForcePlan}>Plan teardown anyway</Button>
            </div>

            <p className="mt-2 text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
              Overrules the model, not the safety policy.
            </p>
          </section>
        )}

        {plan && plan.steps.length > 0 && (
          <section
            className="px-5 py-5"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-[15px] font-semibold">Teardown plan</h2>
              <span className="text-[12.5px] uppercase tracking-[0.08em]" style={{ color: "var(--fg-faint)" }}>
                dependency ordered
              </span>
            </div>

            <ol className="mt-3">
              {plan.steps.map((s, i) => (
                <li
                  key={`${s.action}:${s.resource_id}`}
                  className="relative flex items-start gap-3 py-2 pl-6"
                >
                  <span
                    aria-hidden="true"
                    className="absolute left-[7px] top-0 bottom-0 w-px"
                    style={{
                      background: "var(--border-strong)",
                      top: i === 0 ? "50%" : 0,
                      bottom: i === plan.steps.length - 1 ? "50%" : 0,
                    }}
                  />

                  <span
                    aria-hidden="true"
                    className="absolute left-[2px] top-[15px] h-[11px] w-[11px] rounded-full"
                    style={{
                      background: s.reversible ? "var(--surface)" : "var(--danger)",
                      border: `2px solid ${s.reversible ? "var(--border-strong)" : "var(--danger)"}`,
                    }}
                  />

                  <div className="min-w-0 flex-1">
                    <div className="mono text-[14px]" style={{ color: "var(--fg)" }}>
                      {s.action.replaceAll("_", " ")}
                    </div>
                    <div className="mt-0.5 mono text-[12.5px]" style={{ color: "var(--fg-faint)" }}>
                      {s.resource_id}
                    </div>
                    <div className="mt-1 text-[13.5px] leading-snug" style={{ color: "var(--fg-muted)" }}>
                      {s.reason}
                    </div>
                  </div>

                  <div className="shrink-0 text-right">
                    <div
                      className="num text-[14px]"
                      style={{ color: s.monthly_saving ? "var(--ok)" : "var(--fg-faint)" }}
                    >
                      {s.monthly_saving ? money(s.monthly_saving) : "—"}
                    </div>

                    {!s.reversible && (
                      <div className="mt-1 text-[12px] uppercase" style={{ color: "var(--danger)" }}>
                        irreversible
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>

            <div
              className="mt-3 flex items-center justify-between px-4 py-3"
              style={{
                background: "var(--surface-2)",
                borderRadius: "var(--radius)",
              }}
            >
              <span className="text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
                {irreversible} of {plan.steps.length} steps cannot be undone
              </span>
              <span className="num text-[17px] font-semibold" style={{ color: "var(--ok)" }}>
                {money(total)}
                <span className="text-[12.5px] font-normal">/mo</span>
              </span>
            </div>
          </section>
        )}

        <section className="px-5 py-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-[15px] font-semibold">Live agent trace</h2>

            {(data.awaiting_approval || threadStatus?.awaiting_approval) && !decision && (
              <Tag tone="warn" dot>waiting on Slack</Tag>
            )}

            {decision === "approve" && <Tag tone="ok" dot>approved</Tag>}
            {decision === "reject" && <Tag tone="muted" dot>rejected</Tag>}
          </div>

          <p className="mt-1 text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
            This updates automatically when the Slack approval workflow changes.
          </p>

          <Trace data={data} result={result} status={threadStatus} />
        </section>
      </div>
    </div>
  );
}