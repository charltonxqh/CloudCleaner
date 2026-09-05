"use client";

import { useEffect, useState } from "react";

import {
  money, type ApprovalResult, type Evidence, type GitHubEvidence, type Investigation,
} from "@/lib/api";
import { Button, Empty, SectionLabel, Tag, type Tone } from "../primitives";

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
    <div className="flex items-baseline gap-3 px-4 py-[5px]">
      <span className="w-[104px] shrink-0 text-[11px]" style={{ color: "var(--fg-faint)" }}>
        {label}
      </span>
      <span className="mono shrink-0 text-[12px]" style={{ color: tone ?? "var(--fg)" }}>
        {value}
      </span>
      {note && (
        <span className="truncate text-[11px]" style={{ color: "var(--fg-faint)" }}>
          {note}
        </span>
      )}
    </div>
  );
}

function AwsEvidence({ e }: { e: Evidence }) {
  const idle = e.idle_days;
  return (
    <>
      <SectionLabel right={<span className="label">{e.metric_window_days}d window</span>}>
        AWS activity
      </SectionLabel>
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
      <div className="pb-1" />
    </>
  );
}

function GithubEvidencePanel({ g }: { g: GitHubEvidence }) {
  if (!g.repo) {
    return (
      <>
        <SectionLabel>Code activity</SectionLabel>
        <p className="px-4 pb-3 text-[11px] leading-relaxed" style={{ color: "var(--fg-faint)" }}>
          No <span className="mono">Repo</span> tag, so this resource cannot be traced to a
          codebase. AWS evidence alone decides the verdict.
        </p>
      </>
    );
  }

  const commit = ago(g.latest_commit_at);
  const active = g.branch_exists === true || g.pr_status === "open";

  return (
    <>
      <SectionLabel
        right={
          <Tag tone={active ? "ok" : "danger"} dot>
            {active ? "project alive" : "project finished"}
          </Tag>
        }
      >
        Code activity
      </SectionLabel>

      <div className="px-4 pb-1">
        <a
          href={`https://github.com/${g.repo}`}
          target="_blank"
          rel="noreferrer"
          className="mono text-[12px] underline decoration-dotted underline-offset-2"
          style={{ color: "var(--primary)" }}
        >
          {g.repo}
        </a>
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
          note={g.branch_exists === false ? "deleted — work was merged or abandoned" : "still exists"}
        />
      )}
      {g.pr_number !== null && (
        <Signal
          label={`PR #${g.pr_number}`}
          value={g.pr_status ?? "unknown"}
          tone={g.pr_status === "open" ? "var(--ok)" : "var(--danger)"}
          note={g.pr_status === "open" ? "work still in flight" : undefined}
        />
      )}
      <Signal
        label="Last CI run"
        value={ago(g.last_workflow_run_at) ?? "never"}
        note={g.scheduled_workflow_exists ? "a scheduled workflow still targets this repo" : undefined}
      />
      <div className="pb-1" />
    </>
  );
}

export function InvestigationView({
  data, result, onApprove, onForcePlan, onReinvestigate, onBack,
  approving, busy, stale, cachedAt,
}: {
  data: Investigation | null;
  result: ApprovalResult | null;
  approving: boolean;
  busy: boolean;
  stale: boolean;
  cachedAt: number | null;
  onApprove: (command: string) => void;
  onForcePlan: () => void;
  onReinvestigate: () => void;
  onBack: () => void;
}) {
  const [command, setCommand] = useState("");

  useEffect(() => { setCommand(""); }, [data?.thread_id]);

  if (busy) {
    return <Empty>Investigating — querying CloudWatch and GitHub…</Empty>;
  }

  if (!data) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <Empty>
          No investigation open. Pick a resource and the agent will gather its evidence,
          judge it, and plan what retiring it would take.
        </Empty>
        <Button onClick={onBack}>Browse resources</Button>
      </div>
    );
  }

  const { resource: r, evidence, github, recommendation: rec, plan } = data;
  const expected = `APPROVE ${r.resource_id}`;
  const matches = command === expected;
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

  return (
    <div className="flex min-h-0 flex-col">
      {/* identity */}
      <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mono truncate text-[14px]" style={{ color: "var(--fg)" }}>
              {r.resource_id}
            </div>
            <div className="mt-0.5 truncate text-[12px]" style={{ color: "var(--fg-muted)" }}>
              {r.name || "untagged"} · {r.region || "—"}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <div className="num text-[19px] font-semibold leading-none" style={{ color: "var(--fg)" }}>
              {money(r.estimated_monthly_cost)}
            </div>
            <div className="label mt-1">per month</div>
          </div>
        </div>

        {r.billing_while_stopped && (
          <p
            className="mt-2.5 px-2.5 py-2 text-[12px] leading-relaxed"
            style={{
              background: "var(--danger-dim)",
              color: "var(--danger)",
              borderLeft: "2px solid var(--danger)",
              borderRadius: "0 var(--radius) var(--radius) 0",
            }}
          >
            <strong>Not running — and still billing.</strong> Stopping releases compute only;
            attached storage and public IPv4 keep charging.
          </p>
        )}
      </div>

      {(cachedAt !== null || stale) && (
        <div
          className="flex flex-wrap items-center justify-between gap-2 px-4 py-2"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
        >
          <span className="text-[11px]" style={{ color: stale ? "var(--warn)" : "var(--fg-faint)" }}>
            {stale
              ? "Inventory changed since this investigation."
              : `Cached investigation · ${cachedMinutes === 0 ? "less than a minute ago" : `${cachedMinutes}m ago`}`}
          </span>
          <Button onClick={onReinvestigate}>{stale ? "Re-investigate" : "Analyse again"}</Button>
        </div>
      )}

      <div
        className="grid lg:grid-cols-2"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div style={{ borderRight: "1px solid var(--border)" }}>
          {evidence && <AwsEvidence e={evidence} />}
        </div>
        <div>{github && <GithubEvidencePanel g={github} />}</div>
      </div>

      {/* verdict */}
      {rec && (
        <div
          className="px-4 py-3"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Tag tone={VERDICT_TONE[rec.action]} dot>{rec.action.replace("_", " ")}</Tag>
            <Tag tone={SEVERITY_TONE[rec.severity]}>{rec.severity}</Tag>
            <span className="num text-[11px]" style={{ color: "var(--fg-faint)" }}>
              {Math.round(rec.confidence * 100)}% confidence
            </span>
          </div>
          <p className="mt-2 text-[12px] leading-relaxed" style={{ color: "var(--fg-muted)" }}>
            {rec.reason}
          </p>
          {(rec.action === "stop" || rec.action === "retire") && (
            <div
              className="mt-3 grid gap-px sm:grid-cols-3"
              style={{ background: "var(--border)", border: "1px solid var(--border)" }}
            >
              <div className="px-3 py-2" style={{ background: "var(--surface-2)" }}>
                <div className="label">Current cost</div>
                <div className="num mt-1 text-[15px] font-semibold">{money(r.estimated_monthly_cost)}</div>
              </div>
              <div className="px-3 py-2" style={{ background: "var(--surface-2)" }}>
                <div className="label">{rec.action === "stop" ? "After stop" : "After retirement"}</div>
                <div className="num mt-1 text-[15px] font-semibold">{money(costAfterAction)}</div>
              </div>
              <div className="px-3 py-2" style={{ background: "var(--surface-2)" }}>
                <div className="label">Potential saving</div>
                <div className="num mt-1 text-[15px] font-semibold" style={{ color: "var(--ok)" }}>
                  {money(recommendedSaving)}/mo
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {plan && plan.blocked.length > 0 && (
        <div className="px-4 py-3">
          <Tag tone="ok" dot>blocked by policy</Tag>
          <ul className="mt-2 space-y-0.5">
            {plan.blocked.map((b) => (
              <li key={b} className="text-[12px]" style={{ color: "var(--fg-muted)" }}>· {b}</li>
            ))}
          </ul>
          <p className="mt-2 text-[11px]" style={{ color: "var(--fg-faint)" }}>
            Deterministic rules, evaluated outside the model. Neither the agent nor a human
            can override them here.
          </p>
        </div>
      )}

      {!plan?.steps.length && !plan?.blocked.length && rec && (
        <div className="px-4 py-3">
          <p className="text-[12px]" style={{ color: "var(--fg-muted)" }}>
            No teardown planned — the agent recommends {rec.action.replace("_", " ")}.
          </p>
          <div className="mt-2">
            <Button onClick={onForcePlan}>Plan teardown anyway</Button>
          </div>
          <p className="mt-1.5 text-[11px]" style={{ color: "var(--fg-faint)" }}>
            Overrules the model, not the safety policy.
          </p>
        </div>
      )}

      {/* the plan */}
      {plan && plan.steps.length > 0 && (
        <div className="min-h-0 flex-1">
          <SectionLabel right={<span className="label">dependency ordered</span>}>
            Teardown plan
          </SectionLabel>

          <ol className="px-4 pb-2">
            {plan.steps.map((s, i) => (
              <li
                key={`${s.action}:${s.resource_id}`}
                className="rise relative flex items-baseline gap-2.5 py-1.5 pl-6"
                style={{ ["--i" as string]: i }}
              >
                {/* rail + node */}
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
                  className="absolute left-[3px] top-1/2 h-[9px] w-[9px] -translate-y-1/2 rounded-full"
                  style={{
                    background: s.reversible ? "var(--surface)" : "var(--danger)",
                    border: `1.5px solid ${s.reversible ? "var(--border-strong)" : "var(--danger)"}`,
                  }}
                />

                <div className="min-w-0 flex-1">
                  <div className="mono text-[12px]" style={{ color: "var(--fg)" }}>
                    {s.action}{" "}
                    <span style={{ color: "var(--fg-muted)" }}>{s.resource_id}</span>
                    {!s.reversible && <span className="sr-only"> (irreversible)</span>}
                  </div>
                  <div className="text-[11px] leading-snug" style={{ color: "var(--fg-faint)" }}>
                    {s.reason}
                  </div>
                </div>

                <span
                  className="num shrink-0 text-[12px]"
                  style={{ color: s.monthly_saving ? "var(--ok)" : "var(--fg-faint)" }}
                >
                  {s.monthly_saving ? money(s.monthly_saving) : "—"}
                </span>
              </li>
            ))}
          </ol>

          <div
            className="mx-4 mb-3 flex items-baseline justify-between px-3 py-2"
            style={{ background: "var(--surface-2)", borderRadius: "var(--radius)" }}
          >
            <span className="text-[11px]" style={{ color: "var(--fg-faint)" }}>
              {irreversible} of {plan.steps.length} steps cannot be undone
            </span>
            <span className="num text-[16px] font-semibold" style={{ color: "var(--ok)" }}>
              {money(total)}<span className="text-[11px] font-normal">/mo</span>
            </span>
          </div>
        </div>
      )}

      {/* approval */}
      {data.awaiting_approval && !result && (
        <form
          className="shrink-0 px-4 py-3"
          style={{ borderTop: "1px solid var(--border-strong)", background: "var(--surface-2)" }}
          onSubmit={(ev) => { ev.preventDefault(); if (matches) onApprove(command); }}
        >
          <label htmlFor="approve" className="block text-[11px]" style={{ color: "var(--fg-muted)" }}>
            Type the command exactly to authorise {irreversible} irreversible step
            {irreversible === 1 ? "" : "s"}.
          </label>
          <div className="mt-2 flex gap-2">
            <input
              id="approve"
              value={command}
              onChange={(ev) => setCommand(ev.target.value)}
              placeholder={expected}
              autoComplete="off"
              spellCheck={false}
              aria-describedby="approve-help"
              className="mono min-w-0 flex-1 px-2.5 text-[12px] outline-none transition-colors duration-150"
              style={{
                background: "var(--bg)",
                color: "var(--fg)",
                minHeight: 34,
                border: `1px solid ${
                  command ? (matches ? "var(--ok)" : "var(--danger)") : "var(--border-strong)"
                }`,
                borderRadius: "var(--radius)",
              }}
            />
            <Button type="submit" variant="danger" disabled={!matches || approving}>
              {approving ? "Running…" : "Execute"}
            </Button>
          </div>
          <p id="approve-help" className="mt-1.5 text-[11px]" style={{ color: "var(--fg-faint)" }}>
            {command && !matches
              ? "Does not match — the resource ID must be exact."
              : "Every volume is snapshotted before deletion."}
          </p>
        </form>
      )}

      {result && (
        <div
          className="shrink-0 px-4 py-3"
          style={{ borderTop: "1px solid var(--border-strong)", background: "var(--surface-2)" }}
        >
          <div className="flex items-center gap-2">
            <Tag tone={result.decision === "approve" ? "ok" : "muted"} dot>{result.decision}</Tag>
            {result.verification_passed !== null && (
              <span className="text-[11px]" style={{ color: "var(--fg-muted)" }}>
                verification {result.verification_passed ? "passed" : "failed"}
              </span>
            )}
          </div>
          <ul className="mt-2 space-y-0.5">
            {result.action_results.map((a, i) => (
              <li key={i} className="mono text-[11px]" style={{ color: "var(--fg-muted)" }}>
                <span style={{ color: a.ok ? "var(--ok)" : "var(--danger)" }}>
                  {a.ok ? "✓" : "✗"}
                </span>{" "}
                {a.action} {a.resource_id} → {a.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
