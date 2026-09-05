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
      className="flex-1 px-5 py-4"
      style={{
        background: emphasis ? "var(--surface-2)" : "var(--surface)",
        border: "1px solid var(--border)",
        borderLeft: emphasis ? `2px solid ${tone ?? "var(--primary)"}` : "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <div className="label">{label}</div>
      <div
        className="num mt-1.5 font-semibold leading-none tracking-tight"
        style={{
          color: tone ?? "var(--fg)",
          fontSize: emphasis && !String(value).includes(" ") ? 38 : 30,
        }}
      >
        {value}
      </div>
      {sub && (
        <div className="mt-1.5 text-[11.5px] leading-snug" style={{ color: "var(--fg-faint)" }}>
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
      className="px-5 py-4"
      style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <div className="label">Spend by resource type</div>
      <table className="mt-3 w-full border-collapse">
        <caption className="sr-only">
          Monthly spend per resource type, with the wasted portion highlighted
        </caption>
        <tbody>
          {rows.map(([type, v], i) => (
            <tr key={type} className="rise" style={{ ["--i" as string]: i }}>
              <th scope="row" className="w-[122px] py-1.5 pr-3 text-left text-[12px] font-normal"
                  style={{ color: "var(--fg-muted)" }}>
                {TYPE_LABEL[type] ?? type}
                <span className="ml-1.5 text-[11px]" style={{ color: "var(--fg-faint)" }}>
                  ×{v.count}
                </span>
              </th>
              <td className="py-1.5">
                <div className="h-[22px] w-full" style={{ background: "var(--surface-2)" }}>
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
              <td className="num w-[74px] py-1.5 pl-3 text-right text-[12px]">
                {money(v.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex gap-4 text-[11px]" style={{ color: "var(--fg-faint)" }}>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-3" style={{ background: "var(--danger)" }} /> wasted
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-3" style={{ background: "var(--border-strong)" }} /> in use
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

  return (
    <div className="space-y-3 p-5">
      <div className="flex flex-wrap gap-3">
        <BigStat
          label="Recoverable"
          value={sweep ? money(sweep.recoverable_monthly) : "not yet analysed"}
          sub={
            sweep
              ? `${money(sweep.recoverable_yearly)} a year, across ${
                  sweep.results.filter((r) => r.steps > 0).length
                } resources`
              : "Run an analysis to find out"
          }
          tone="var(--ok)"
          emphasis
        />
        <BigStat
          label="Wasted spend"
          value={money(totals.wasting)}
          sub={`${pct}% of the monthly bill pays for nothing`}
          tone="var(--danger)"
        />
        <BigStat
          label="Total spend"
          value={money(totals.total)}
          sub={`${resources.length} resources in scope`}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <WasteBreakdown resources={resources} />

        <div
          className="flex flex-col px-5 py-4"
          style={{
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="label">Paying for nothing</div>
            <span className="num text-[13px]" style={{ color: "var(--danger)" }}>
              {money(wasteful.reduce((s, r) => s + (r.estimated_monthly_cost ?? 0), 0))}/mo
            </span>
          </div>

          {wasteful.length === 0 ? (
            <Empty>Nothing is billing while stopped. This account is clean.</Empty>
          ) : (
            <ul className="mt-3 space-y-1">
              {wasteful.map((r, i) => (
                <li key={r.resource_id} className="rise" style={{ ["--i" as string]: i }}>
                  <button
                    onClick={() => onOpen(r)}
                    className="flex w-full items-center gap-3 px-2 text-left transition-colors duration-150"
                    style={{ minHeight: 38, borderRadius: "var(--radius)" }}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="mono block truncate text-[12px]">{r.resource_id}</span>
                      <span className="block truncate text-[11px]" style={{ color: "var(--fg-faint)" }}>
                        {r.name || (r.size_gb ? `${r.size_gb} GB` : "untagged")} · {r.state}
                      </span>
                    </span>
                    {verdicts[r.resource_id] && (
                      <Tag tone={VERDICT_TONE[verdicts[r.resource_id]]}>
                        {verdicts[r.resource_id].replace("_", " ")}
                      </Tag>
                    )}
                    <span className="num shrink-0 text-[13px]" style={{ color: "var(--danger)" }}>
                      {money(r.estimated_monthly_cost)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-auto pt-3 text-[11px] leading-relaxed" style={{ color: "var(--fg-faint)" }}>
            Stopping an instance releases compute only. Attached volumes and public IPv4
            addresses keep billing until they are explicitly released.
          </p>
        </div>
      </div>
    </div>
  );
}
