"use client";

import { useState } from "react";

import { money, type ApprovalResult, type Investigation } from "@/lib/api";
import { Empty, Tag } from "./primitives";

const VERDICT_TONE = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
} as const;

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-4 py-1.5">
      <span className="text-[11px]" style={{ color: "var(--fg-faint)" }}>{label}</span>
      <span className="mono text-[12px]" style={{ color: tone ?? "var(--fg)" }}>{value}</span>
    </div>
  );
}

export function InvestigationPanel({
  data, result, onApprove, onForcePlan, approving,
}: {
  data: Investigation | null;
  result: ApprovalResult | null;
  approving: boolean;
  onApprove: (command: string) => void;
  onForcePlan: () => void;
}) {
  const [command, setCommand] = useState("");

  if (!data) {
    return <Empty>Select a resource to investigate.</Empty>;
  }

  const { resource: r, evidence: e, recommendation: rec, plan } = data;
  const expected = `APPROVE ${r.resource_id}`;
  const matches = command === expected;
  const total = plan?.steps.reduce((s, x) => s + x.monthly_saving, 0) ?? 0;
  const irreversible = plan?.steps.filter((s) => !s.reversible).length ?? 0;

  return (
    <div className="flex min-h-0 flex-col">
      <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="mono text-[14px]" style={{ color: "var(--fg)" }}>{r.resource_id}</div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--fg-muted)" }}>
          {r.name || "untagged"} · {r.region || "—"} · {money(r.estimated_monthly_cost)}/mo
        </div>
        {r.billing_while_stopped && (
          <p
            className="mt-2 px-2 py-1.5 text-[12px]"
            style={{ background: "var(--danger-dim)", color: "var(--danger)", borderRadius: 2 }}
          >
            Not running — and still billing. Stopping releases compute only; storage and public
            IPv4 keep charging.
          </p>
        )}
      </div>

      {e && (
        <div style={{ borderBottom: "1px solid var(--border)" }}>
          <SectionLabel>Evidence · {e.metric_window_days}d window</SectionLabel>
          <Row label="Average CPU" value={e.avg_cpu_percent === null ? "no data" : `${e.avg_cpu_percent}%`} />
          <Row label="Peak CPU" value={e.max_cpu_percent === null ? "no data" : `${e.max_cpu_percent}%`} />
          <Row
            label="Idle for"
            value={e.idle_days === null ? "no metrics emitted" : `${e.idle_days} days`}
            tone={(e.idle_days ?? 0) >= 30 ? "var(--danger)" : undefined}
          />
          <div className="pb-2" />
        </div>
      )}

      {rec && (
        <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="flex items-center gap-2">
            <Tag tone={VERDICT_TONE[rec.action]}>{rec.action.replace("_", " ")}</Tag>
            <span className="num text-[11px]" style={{ color: "var(--fg-faint)" }}>
              {Math.round(rec.confidence * 100)}% confidence · {rec.severity} severity
            </span>
          </div>
          <p className="mt-2 text-[12px] leading-relaxed" style={{ color: "var(--fg-muted)" }}>
            {rec.reason}
          </p>
        </div>
      )}

      {!plan?.steps.length && !plan?.blocked.length && rec && (
        <div className="px-4 py-3">
          <p className="text-[12px]" style={{ color: "var(--fg-muted)" }}>
            No teardown was planned — the agent recommends {rec.action.replace("_", " ")}.
          </p>
          <button
            onClick={onForcePlan}
            className="mt-2 px-3 py-2 text-[12px] transition-colors duration-150"
            style={{
              color: "var(--fg-muted)", border: "1px solid var(--border-strong)",
              borderRadius: 2, minHeight: 44,
            }}
          >
            Plan teardown anyway
          </button>
          <p className="mt-1.5 text-[11px]" style={{ color: "var(--fg-faint)" }}>
            Overrides the model, not the safety policy.
          </p>
        </div>
      )}

      {plan && plan.blocked.length > 0 && (
        <div className="px-4 py-3">
          <Tag tone="ok">blocked by policy</Tag>
          <ul className="mt-2 text-[12px]" style={{ color: "var(--fg-muted)" }}>
            {plan.blocked.map((b) => <li key={b}>· {b}</li>)}
          </ul>
        </div>
      )}

      {plan && plan.steps.length > 0 && (
        <div className="min-h-0 flex-1">
          <SectionLabel>Teardown plan · dependency ordered</SectionLabel>
          <ol className="px-4 pb-2">
            {plan.steps.map((s) => (
              <li
                key={`${s.action}:${s.resource_id}`}
                className="flex items-baseline gap-2 py-1"
                style={{ borderBottom: "1px dashed var(--border)" }}
              >
                <span className="num w-4 shrink-0 text-[11px]" style={{ color: "var(--fg-faint)" }}>
                  {s.order}
                </span>
                <span
                  aria-hidden="true"
                  className="w-2 shrink-0 text-[12px]"
                  style={{ color: s.reversible ? "transparent" : "var(--danger)" }}
                >
                  !
                </span>
                <div className="min-w-0 flex-1">
                  <div className="mono text-[12px]" style={{ color: "var(--fg)" }}>
                    {s.action}{" "}
                    <span style={{ color: "var(--fg-muted)" }}>{s.resource_id}</span>
                    {!s.reversible && <span className="sr-only"> (irreversible)</span>}
                  </div>
                  <div className="text-[11px]" style={{ color: "var(--fg-faint)" }}>{s.reason}</div>
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
          <div className="flex items-baseline justify-between px-4 py-2">
            <span className="text-[11px]" style={{ color: "var(--fg-faint)" }}>
              {irreversible} of {plan.steps.length} steps cannot be undone
            </span>
            <span className="num text-[15px] font-semibold" style={{ color: "var(--ok)" }}>
              {money(total)}/mo
            </span>
          </div>
        </div>
      )}

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
              className="mono min-w-0 flex-1 px-2 py-2 text-[12px] outline-none"
              style={{
                background: "var(--bg)",
                color: "var(--fg)",
                border: `1px solid ${command && !matches ? "var(--danger)" : "var(--border-strong)"}`,
                borderRadius: 2,
              }}
            />
            <button
              type="submit"
              disabled={!matches || approving}
              className="shrink-0 px-4 py-2 text-[12px] font-semibold transition-colors duration-150"
              style={{
                background: matches ? "var(--danger)" : "var(--surface)",
                color: matches ? "#fff" : "var(--fg-faint)",
                border: `1px solid ${matches ? "var(--danger)" : "var(--border-strong)"}`,
                borderRadius: 2,
                minHeight: 44,
              }}
            >
              {approving ? "Running…" : "Execute"}
            </button>
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
            <Tag tone={result.decision === "approve" ? "ok" : "muted"}>{result.decision}</Tag>
            {result.verification_passed !== null && (
              <span className="text-[11px]" style={{ color: "var(--fg-muted)" }}>
                verification {result.verification_passed ? "passed" : "failed"}
              </span>
            )}
          </div>
          <ul className="mt-2">
            {result.action_results.map((a, i) => (
              <li key={i} className="mono py-0.5 text-[11px]" style={{ color: "var(--fg-muted)" }}>
                {a.ok ? "✓" : "✗"} {a.action} {a.resource_id} → {a.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.09em]"
      style={{ color: "var(--fg-faint)" }}
    >
      {children}
    </div>
  );
}
