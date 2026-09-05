"use client";

import { Fragment, useState } from "react";

import {
  api,
  money,
  type HistoryTotals,
  type ReasoningEvent,
  type Run,
} from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

const EVENT_TONE: Record<string, Tone> = {
  finding: "warn", decision: "info", action: "danger", error: "danger",
  skip: "muted", check: "muted", handoff: "muted",
};

const VERDICT_TONE: Record<string, Tone> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

function when(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function outcome(r: Run) {
  if (r.blocked.length) {
    return { text: `blocked — ${r.blocked[0]}`, tone: "var(--warn)" };
  }

  if (r.decision === "reject") {
    return { text: "rejected by human", tone: "var(--fg-muted)" };
  }

  if (r.executed > 0) {
    return {
      text: r.dry_run
        ? `${r.executed} of ${r.planned_steps} steps simulated`
        : `${r.executed} of ${r.planned_steps} steps executed${r.verified === false ? " (unverified)" : ""}`,
      tone: "var(--ok)",
    };
  }

  if (r.verdict === "keep") {
    return { text: "no action needed", tone: "var(--fg-faint)" };
  }

  if (r.decision === "approve") {
    return { text: "approved — no action executed", tone: "var(--fg-muted)" };
  }

  return { text: "awaiting / not approved", tone: "var(--fg-faint)" };
}

function Summary({ totals }: { totals: HistoryTotals }) {
  const cards = [
    { label: "Runs", value: String(totals.runs), sub: "recorded agent runs" },
    { label: "Approved", value: String(totals.approved), sub: "human approvals" },
    { label: "Kept", value: String(totals.kept), sub: "resources left untouched" },
    {
      label: "Realised savings",
      value: money(totals.realised_monthly),
      tone: "var(--ok)",
      sub: "actual monthly saving",
    },
    {
      label: "Simulated savings",
      value: money(totals.simulated_monthly),
      tone: "var(--fg)",
      sub: "dry-run saving only",
    },
  ];

  return (
    <div className="grid gap-3 px-5 py-4 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map((c) => (
        <div
          key={c.label}
          className="px-4 py-4"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
          }}
        >
          <div className="label text-[11px]">{c.label}</div>

          <div
            className="num mt-2 text-[25px] font-semibold leading-none"
            style={{ color: c.tone ?? "var(--fg)" }}
          >
            {c.value}
          </div>

          <div className="mt-2 text-[11px]" style={{ color: "var(--fg-faint)" }}>
            {c.sub}
          </div>
        </div>
      ))}
    </div>
  );
}

export function HistoryView({
  runs,
  totals,
}: {
  runs: Run[];
  totals: HistoryTotals | null;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [trail, setTrail] = useState<Record<string, ReasoningEvent[]>>({});
  const [loading, setLoading] = useState<string | null>(null);

  async function toggle(runId: string) {
    if (open === runId) {
      setOpen(null);
      return;
    }

    setOpen(runId);

    if (trail[runId]) return;

    setLoading(runId);

    try {
      const r = await api.runEvents(runId);
      setTrail((t) => ({ ...t, [runId]: r.events }));
    } catch {
      setTrail((t) => ({ ...t, [runId]: [] }));
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {totals && <Summary totals={totals} />}

      {totals && totals.realised_monthly === 0 && totals.simulated_monthly > 0 && (
        <p
          className="mx-5 mb-4 px-4 py-3 text-[12px] leading-relaxed"
          style={{
            background: "var(--warn-dim)",
            color: "var(--warn)",
            borderLeft: "2px solid var(--warn)",
            borderRadius: "0 var(--radius) var(--radius) 0",
          }}
        >
          Every execution so far was a dry run. {money(totals.simulated_monthly)}/mo is
          simulated potential saving, not money already saved. Set{" "}
          <span className="mono">CLOUDCLEANER_DRY_RUN=false</span> only when you are ready
          to execute a controlled real remediation.
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        {!runs.length ? (
          <Empty>No runs recorded yet. Investigate a resource and its outcome lands here.</Empty>
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead className="sticky top-0 z-10">
              <tr style={{ background: "var(--surface-2)" }}>
                {["", "When", "Resource", "Verdict", "Outcome", "$/mo"].map((h, i) => (
                  <th
                    key={h || "expand"}
                    scope="col"
                    className={`label px-4 py-2.5 ${i === 5 ? "text-right" : "text-left"}`}
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {runs.map((r, i) => {
                const o = outcome(r);
                const expanded = open === r.run_id;
                const events = trail[r.run_id];

                return (
                  <Fragment key={r.run_id}>
                    <tr
                      onClick={() => toggle(r.run_id)}
                      tabIndex={0}
                      role="button"
                      aria-expanded={expanded}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggle(r.run_id);
                        }
                      }}
                      className="rise cursor-pointer transition-colors duration-150"
                      style={{
                        ["--i" as string]: i,
                        borderBottom: "1px solid var(--border)",
                        background: expanded ? "var(--surface-2)" : "transparent",
                      }}
                    >
                      <td className="px-4 py-3" style={{ color: "var(--fg-faint)", width: 24 }}>
                        <span
                          aria-hidden="true"
                          className="inline-block transition-transform duration-150"
                          style={{ transform: expanded ? "rotate(90deg)" : "none" }}
                        >
                          ›
                        </span>
                      </td>

                      <td
                        className="num whitespace-nowrap px-4 py-3"
                        style={{ color: "var(--fg-faint)" }}
                      >
                        {when(r.at)}
                        {r.dry_run && <Tag tone="warn">dry</Tag>}
                      </td>

                      <td className="mono px-4 py-3">{r.resource_id}</td>

                      <td className="px-4 py-3">
                        {r.verdict ? (
                          <Tag tone={VERDICT_TONE[r.verdict] ?? "muted"}>
                            {r.verdict.replace("_", " ")}
                          </Tag>
                        ) : "—"}
                      </td>

                      <td className="px-4 py-3" style={{ color: o.tone }}>
                        {o.text}
                      </td>

                      <td
                        className="num px-4 py-3 text-right"
                        style={{ color: r.monthly_saving ? "var(--ok)" : "var(--fg-faint)" }}
                      >
                        {r.monthly_saving ? money(r.monthly_saving) : "—"}
                      </td>
                    </tr>

                    {expanded && (
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <td colSpan={6} style={{ background: "var(--bg)" }}>
                          <div className="px-12 py-4">
                            <div
                              className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em]"
                              style={{ color: "var(--fg-muted)" }}
                            >
                              Agent trace
                            </div>

                            {loading === r.run_id ? (
                              <p
                                className="text-[13px] pulse"
                                style={{ color: "var(--fg-faint)" }}
                              >
                                Loading the reasoning…
                              </p>
                            ) : !events?.length ? (
                              <p
                                className="text-[13px]"
                                style={{ color: "var(--fg-faint)" }}
                              >
                                No reasoning was recorded for this run.
                              </p>
                            ) : (
                              <ol className="space-y-1">
                                {events.map((e, j) => (
                                  <li
                                    key={`${r.run_id}:${j}:${e.node}:${e.event}`}
                                    className="flex items-baseline gap-3 py-1"
                                  >
                                    <span
                                      className="mono w-[100px] shrink-0 text-[12px]"
                                      style={{ color: "var(--fg-muted)" }}
                                    >
                                      {e.node}
                                    </span>

                                    <span className="w-[76px] shrink-0">
                                      <Tag tone={EVENT_TONE[e.event] ?? "muted"}>
                                        {e.event}
                                      </Tag>
                                    </span>

                                    <span
                                      className="min-w-0 flex-1 text-[13px] leading-snug"
                                      style={{
                                        color: "var(--fg)",
                                        overflowWrap: "anywhere",
                                      }}
                                    >
                                      {e.message}
                                    </span>
                                  </li>
                                ))}
                              </ol>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}