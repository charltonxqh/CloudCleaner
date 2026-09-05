"use client";

import { money, type Recommendation, type Resource, type SweepResult } from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

const TYPE_LABEL: Record<string, string> = {
  ec2: "EC2 instances", ebs: "EBS volumes", eip: "Elastic IPs", snapshot: "Snapshots",
};

const VERDICT_TONE: Record<string, Tone> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

function BigStat({
  label, value, sub, tone, emphasis = false,
}: { label: string; value: string; sub?: string; tone?: string; emphasis?: boolean }) {
  return (
    <div
      className="min-w-[220px] flex-1 px-6 py-6"
      style={{
        background: emphasis ? "var(--surface-2)" : "var(--surface)",
        border: "1px solid var(--border)",
        borderLeft: emphasis ? `3px solid ${tone ?? "var(--primary)"}` : "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <div className="label text-[12px]">{label}</div>
      <div
        className="num mt-3 font-semibold leading-none tracking-tight"
        style={{
          color: tone ?? "var(--fg)",
          fontSize: emphasis && !String(value).includes(" ") ? 48 : 40,
        }}
      >
        {value}
        {!String(value).includes("analysed") && (
          <span className="ml-1 text-[15px] font-normal" style={{ color: "var(--fg-faint)" }}>
            /mo
          </span>
        )}
      </div>
      {sub && (
        <div className="mt-3 text-[13px] leading-snug" style={{ color: "var(--fg-muted)" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

/** Horizontal bar — a chart type that survives a screen reader, unlike a pie. */
function WasteBreakdown({ resources }: { resources: Resource[] }) {
  const byType = new Map<string, { total: number; wasted: number; count: number }>();
  for (const r of resources) {
    const e = byType.get(r.resource_type) ?? { total: 0, wasted: 0, count: 0 };
    e.total += r.estimated_monthly_cost ?? 0;
    if (r.billing_while_stopped) e.wasted += r.estimated_monthly_cost ?? 0;
    e.count += 1;
    byType.set(r.resource_type, e);
  }

  const rows = [...byType.entries()].sort((a, b) => b[1].total - a[1].total);
  const max = Math.max(...rows.map(([, v]) => v.total), 1);

  return (
    <div
      className="px-6 py-5"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <div className="text-[13px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--fg-muted)" }}>
        Spend by resource type
      </div>
      <table className="mt-4 w-full border-collapse">
        <caption className="sr-only">
          Monthly spend per resource type, with the wasted portion highlighted
        </caption>
        <tbody>
          {rows.map(([type, v], i) => (
            <tr key={type} className="rise" style={{ ["--i" as string]: i }}>
              <th
                scope="row"
                className="w-[150px] py-2 pr-4 text-left text-[13px] font-normal"
                style={{ color: "var(--fg-muted)" }}
              >
                {TYPE_LABEL[type] ?? type}
                <span className="ml-2 text-[12px]" style={{ color: "var(--fg-faint)" }}>
                  ×{v.count}
                </span>
              </th>
              <td className="py-2">
                <div className="h-[26px] w-full" style={{ background: "var(--surface-2)" }}>
                  <div className="flex h-full">
                    <div
                      className="h-full transition-[width] duration-500"
                      style={{ width: `${(v.wasted / max) * 100}%`, background: "var(--danger)" }}
                      title={`${money(v.wasted)} wasted`}
                    />
                    <div
                      className="h-full transition-[width] duration-500"
                      style={{
                        width: `${((v.total - v.wasted) / max) * 100}%`,
                        background: "var(--border-strong)",
                      }}
                      title={`${money(v.total - v.wasted)} in use`}
                    />
                  </div>
                </div>
              </td>
              <td className="num w-[88px] py-2 pl-4 text-right text-[13px]">
                {money(v.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-4 flex gap-5 text-[12px]" style={{ color: "var(--fg-faint)" }}>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-3.5" style={{ background: "var(--danger)" }} /> wasted
        </span>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-3.5" style={{ background: "var(--border-strong)" }} /> in use
        </span>
      </div>
    </div>
  );
}

export function OverviewView({
  resources, totals, sweep, verdicts, onOpen,
}: {
  resources: Resource[];
  totals: { total: number; wasting: number };
  sweep: SweepResult | null;
  verdicts: Record<string, Recommendation["action"]>;
  onOpen: (r: Resource) => void;
}) {
  const wasteful = resources
    .filter((r) => r.billing_while_stopped)
    .sort((a, b) => (b.estimated_monthly_cost ?? 0) - (a.estimated_monthly_cost ?? 0));

  const pct = totals.total ? Math.round((totals.wasting / totals.total) * 100) : 0;
  const actionable = sweep?.results.filter(
    (r) => (r.action === "stop" || r.action === "retire") && r.monthly_saving > 0
  ).length ?? 0;

  return (
    <div className="space-y-4 p-6">
      <div className="grid gap-4 xl:grid-cols-3">
        <BigStat
          label="Potential savings"
          value={sweep ? money(sweep.recoverable_monthly) : "not yet analysed"}
          sub={
            sweep
              ? `${money(sweep.recoverable_yearly)} per year · ${actionable} resources can be cleaned up`
              : "Run an analysis to estimate recoverable cloud spend"
          }
          tone="var(--ok)"
          emphasis
        />

        <BigStat
          label="Wasted spend"
          value={money(totals.wasting)}
          sub={`${pct}% of the current monthly cloud bill`}
          tone="var(--danger)"
        />

        <BigStat
          label="Total cloud spend"
          value={money(totals.total)}
          sub={`${resources.length} resources currently in scope`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <WasteBreakdown resources={resources} />

        <div
          className="flex flex-col px-6 py-5"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="text-[13px] font-semibold uppercase tracking-[0.08em]" style={{ color: "var(--fg-muted)" }}>
              Paying for nothing
            </div>
            <span className="num text-[15px] font-semibold" style={{ color: "var(--danger)" }}>
              {money(wasteful.reduce((s, r) => s + (r.estimated_monthly_cost ?? 0), 0))}/mo
            </span>
          </div>

          {wasteful.length === 0 ? (
            <Empty>Nothing is billing while stopped. This account is clean.</Empty>
          ) : (
            <ul className="mt-4 space-y-1.5">
              {wasteful.map((r, i) => (
                <li key={r.resource_id} className="rise" style={{ ["--i" as string]: i }}>
                  <button
                    onClick={() => onOpen(r)}
                    className="flex w-full items-center gap-3 px-3 text-left transition-colors duration-150"
                    style={{
                      minHeight: 50,
                      borderRadius: "var(--radius)",
                      background: "var(--surface-2)",
                    }}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="mono block truncate text-[13px]">{r.resource_id}</span>
                      <span className="mt-0.5 block truncate text-[12px]" style={{ color: "var(--fg-faint)" }}>
                        {r.name || (r.size_gb ? `${r.size_gb} GB` : "untagged")} · {r.state}
                      </span>
                    </span>

                    {verdicts[r.resource_id] && (
                      <Tag tone={VERDICT_TONE[verdicts[r.resource_id]]}>
                        {verdicts[r.resource_id].replace("_", " ")}
                      </Tag>
                    )}

                    <span className="num shrink-0 text-[14px]" style={{ color: "var(--danger)" }}>
                      {money(r.estimated_monthly_cost)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-auto pt-4 text-[12px] leading-relaxed" style={{ color: "var(--fg-faint)" }}>
            Stopping an instance releases compute only. Attached volumes and public IPv4
            addresses keep billing until they are explicitly released.
          </p>
        </div>
      </div>
    </div>
  );
}