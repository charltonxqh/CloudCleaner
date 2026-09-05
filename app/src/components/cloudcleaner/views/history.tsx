"use client";

import { useState } from "react";

import {
  api, money,
  type EventStats, type HistoryTotals, type ReasoningEvent, type Run,
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
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function outcome(r: Run) {
  if (r.blocked.length) return { text: `blocked — ${r.blocked[0]}`, tone: "var(--warn)" };
  if (r.executed > 0) {
    return {
      text: `${r.executed} of ${r.planned_steps} steps${r.verified === false ? " (unverified)" : ""}`,
      tone: "var(--ok)",
    };
  }
  if (r.verdict === "keep") return { text: "no action needed", tone: "var(--fg-faint)" };
  return { text: "not approved", tone: "var(--fg-faint)" };
}

function Summary({ totals, stats }: { totals: HistoryTotals; stats: EventStats | null }) {
  const rate = stats?.llm_success_rate;
  const cards = [
    { label: "Runs", value: String(totals.runs) },
    { label: "Approved", value: String(totals.approved) },
    { label: "Kept", value: String(totals.kept) },
    { label: "Realised", value: money(totals.realised_monthly), tone: "var(--ok)", sub: "per month" },
    { label: "Simulated", value: money(totals.simulated_monthly), tone: "var(--fg-faint)", sub: "dry run only" },
    ...(rate === null || rate === undefined ? [] : [{
      label: "Model used",
      value: `${Math.round(rate * 100)}%`,
      tone: rate < 0.9 ? "var(--warn)" : "var(--ok)",
      sub: `${stats!.llm_fallbacks} of ${stats!.assessments} fell back to rules`,
    }]),
  ];

  return (
    <div className="flex flex-wrap gap-3 px-5 py-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className="min-w-[118px] flex-1 px-4 py-3"
          style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
          }}
        >
          <div className="label">{c.label}</div>
          <div className="num mt-1 text-[20px] font-semibold leading-none"
               style={{ color: c.tone ?? "var(--fg)" }}>
            {c.value}
          </div>
          {c.sub && (
            <div className="mt-1 text-[11px]" style={{ color: "var(--fg-faint)" }}>{c.sub}</div>
          )}
        </div>
      ))}
    </div>
  );
}

export function HistoryView({
  runs, totals, stats,
}: { runs: Run[]; totals: HistoryTotals | null; stats: EventStats | null }) {
  const [open, setOpen] = useState<string | null>(null);
  const [trail, setTrail] = useState<Record<string, ReasoningEvent[]>>({});
  const [loading, setLoading] = useState<string | null>(null);

  async function toggle(runId: string) {
    if (open === runId) { setOpen(null); return; }
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

  if (!runs.length) {
    return <Empty>No runs recorded yet. Investigate a resource and its outcome lands here.</Empty>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {totals && <Summary totals={totals} stats={stats} />}

      {totals && totals.realised_monthly === 0 && totals.simulated_monthly > 0 && (
        <p
          className="mx-5 mb-3 px-3 py-2 text-[11.5px] leading-relaxed"
          style={{
            background: "var(--warn-dim)", color: "var(--warn)",
            borderLeft: "2px solid var(--warn)", borderRadius: "0 var(--radius) var(--radius) 0",
          }}
        >
          Every run so far was a dry run, so {money(totals.simulated_monthly)}/mo is simulated,
          not saved. Set <span className="mono">CLOUDCLEANER_DRY_RUN=false</span> to act for real.
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-[12.5px]">
          <thead className="sticky top-0 z-10">
            <tr style={{ background: "var(--surface-2)" }}>
              {["", "When", "Resource", "Verdict", "Outcome", "$/mo"].map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  className={`label px-4 py-2 ${i === 5 ? "text-right" : "text-left"}`}
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
                <>
                <tr
                  key={r.run_id}
                  onClick={() => toggle(r.run_id)}
                  tabIndex={0}
                  role="button"
                  aria-expanded={expanded}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(r.run_id); }
                  }}
                  className="rise cursor-pointer transition-colors duration-150"
                  style={{
                    ["--i" as string]: i,
                    borderBottom: "1px solid var(--border)",
                    background: expanded ? "var(--surface-2)" : "transparent",
                  }}
                >
                  <td className="px-4 py-2" style={{ color: "var(--fg-faint)", width: 24 }}>
                    <span
                      aria-hidden="true"
                      className="inline-block transition-transform duration-150"
                      style={{ transform: expanded ? "rotate(90deg)" : "none" }}
                    >
                      ›
                    </span>
                  </td>
                  <td className="num whitespace-nowrap px-4 py-2" style={{ color: "var(--fg-faint)" }}>
                    {when(r.at)}
                    {r.dry_run && (
                      <Tag tone="warn"><span className="ml-0">dry</span></Tag>
                    )}
                  </td>
                  <td className="mono px-4 py-2">{r.resource_id}</td>
                  <td className="px-4 py-2">
                    {r.verdict ? (
                      <Tag tone={VERDICT_TONE[r.verdict] ?? "muted"}>
                        {r.verdict.replace("_", " ")}
                      </Tag>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2" style={{ color: o.tone }}>{o.text}</td>
                  <td
                    className="num px-4 py-2 text-right"
                    style={{ color: r.monthly_saving ? "var(--ok)" : "var(--fg-faint)" }}
                  >
                    {r.monthly_saving ? money(r.monthly_saving) : "—"}
                  </td>
                </tr>

                {expanded && (
                  <tr key={`${r.run_id}-trail`} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td colSpan={6} style={{ background: "var(--bg)" }}>
                      {loading === r.run_id ? (
                        <p className="px-12 py-3 text-[12.5px] pulse" style={{ color: "var(--fg-faint)" }}>
                          Loading the reasoning…
                        </p>
                      ) : !events?.length ? (
                        <p className="px-12 py-3 text-[12.5px]" style={{ color: "var(--fg-faint)" }}>
                          No reasoning was recorded for this run.
                        </p>
                      ) : (
                        <ol className="px-12 py-2">
                          {events.map((e, j) => (
                            <li key={j} className="flex items-baseline gap-3 py-[3px]">
                              <span className="mono w-[86px] shrink-0 text-[11.5px]"
                                    style={{ color: "var(--fg-muted)" }}>
                                {e.node}
                              </span>
                              <span className="w-[72px] shrink-0">
                                <Tag tone={EVENT_TONE[e.event] ?? "muted"}>{e.event}</Tag>
                              </span>
                              <span className="min-w-0 flex-1 text-[12.5px] leading-snug"
                                    style={{ color: "var(--fg)", overflowWrap: "anywhere" }}>
                                {e.message}
                              </span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </td>
                  </tr>
                )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
