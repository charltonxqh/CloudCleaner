"use client";

import { money, type HistoryTotals, type Run } from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

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

function Summary({ totals }: { totals: HistoryTotals }) {
  const cards = [
    { label: "Runs", value: String(totals.runs) },
    { label: "Approved", value: String(totals.approved) },
    { label: "Kept", value: String(totals.kept) },
    { label: "Realised", value: money(totals.realised_monthly), tone: "var(--ok)", sub: "per month" },
    { label: "Simulated", value: money(totals.simulated_monthly), tone: "var(--fg-faint)", sub: "dry run only" },
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

export function HistoryView({ runs, totals }: { runs: Run[]; totals: HistoryTotals | null }) {
  if (!runs.length) {
    return <Empty>No runs recorded yet. Investigate a resource and its outcome lands here.</Empty>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {totals && <Summary totals={totals} />}

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
              {["When", "Resource", "Verdict", "Outcome", "$/mo"].map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  className={`label px-4 py-2 ${i === 4 ? "text-right" : "text-left"}`}
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
              return (
                <tr
                  key={r.run_id}
                  className="rise"
                  style={{ ["--i" as string]: i, borderBottom: "1px solid var(--border)" }}
                >
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
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
