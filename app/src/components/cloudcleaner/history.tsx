"use client";

import { money, type HistoryTotals, type Run } from "@/lib/api";
import { Empty, Tag } from "./primitives";

const VERDICT_TONE: Record<string, "ok" | "warn" | "danger"> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

function when(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export function History({ runs, totals }: { runs: Run[]; totals: HistoryTotals | null }) {
  if (!runs.length) return <Empty>No runs recorded yet. Investigate a resource to start.</Empty>;

  return (
    <div>
      {totals && (
        <div
          className="sticky top-0 z-10 flex flex-wrap gap-x-6 gap-y-1 px-3 py-2 text-[11px]"
          style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}
        >
          <span style={{ color: "var(--fg-muted)" }}>
            {totals.runs} runs · {totals.approved} approved · {totals.kept} kept
            {totals.blocked > 0 && ` · ${totals.blocked} blocked`}
          </span>
          <span className="num" style={{ color: "var(--ok)" }}>
            realised {money(totals.realised_monthly)}/mo
          </span>
          <span className="num" style={{ color: "var(--fg-faint)" }}>
            simulated {money(totals.simulated_monthly)}/mo
          </span>
        </div>
      )}

      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr style={{ color: "var(--fg-faint)" }}>
            {["When", "Resource", "Verdict", "Outcome", "$/mo"].map((h, i) => (
              <th
                key={h}
                scope="col"
                className={`px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.09em] ${
                  i === 4 ? "text-right" : "text-left"
                }`}
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.run_id} style={{ borderBottom: "1px solid var(--border)" }}>
              <td className="num whitespace-nowrap px-3 py-1.5" style={{ color: "var(--fg-faint)" }}>
                {when(r.at)}
                {r.dry_run && (
                  <span className="ml-1.5" style={{ color: "var(--warn)" }}>dry</span>
                )}
              </td>
              <td className="mono px-3 py-1.5" style={{ color: "var(--fg)" }}>
                {r.resource_id}
              </td>
              <td className="px-3 py-1.5">
                {r.verdict ? (
                  <Tag tone={VERDICT_TONE[r.verdict] ?? "muted"}>{r.verdict.replace("_", " ")}</Tag>
                ) : "—"}
              </td>
              <td className="px-3 py-1.5" style={{ color: "var(--fg-muted)" }}>
                {r.blocked.length > 0
                  ? `blocked — ${r.blocked[0]}`
                  : r.executed > 0
                    ? `${r.executed} of ${r.planned_steps} steps${r.verified === false ? " (unverified)" : ""}`
                    : r.decision === "keep"
                      ? "no action"
                      : "not approved"}
              </td>
              <td
                className="num px-3 py-1.5 text-right"
                style={{ color: r.monthly_saving ? "var(--ok)" : "var(--fg-faint)" }}
              >
                {r.monthly_saving ? money(r.monthly_saving) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
