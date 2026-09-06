"use client";

import { money, type Recommendation, type Resource, type SweepResult } from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

const TYPE_LABEL: Record<string, string> = {
  ec2: "EC2 instances", ebs: "EBS volumes", eip: "Elastic IPs", snapshot: "Snapshots",
};

const VERDICT_TONE: Record<string, Tone> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

const TINT = {
  pink:   { bg: "var(--pink)",   fg: "var(--pink-fg)" },
  blue:   { bg: "var(--blue)",   fg: "var(--blue-fg)" },
  yellow: { bg: "var(--yellow)", fg: "var(--yellow-fg)" },
  green:  { bg: "var(--green)",  fg: "var(--green-fg)" },
  lilac:  { bg: "var(--lilac)",  fg: "var(--lilac-fg)" },
} as const;

/** Small pixel glyphs, drawn on the same 8x8 grid idea as the logo. */
const GLYPHS: Record<string, [number, number][]> = {
  // coins
  green: [[1,5],[2,5],[3,5],[1,6],[2,6],[3,6],[4,2],[5,2],[6,2],[4,3],[5,3],[6,3],
          [4,4],[5,4],[6,4],[3,1],[4,1],[5,1]],
  // a dripping tap
  pink: [[1,1],[2,1],[3,1],[4,1],[5,1],[1,2],[5,2],[1,3],[2,3],[3,3],[4,3],[5,3],
         [3,5],[3,6],[2,6],[4,6],[3,7]],
  // stacked layers
  blue: [[2,1],[3,1],[4,1],[5,1],[1,2],[6,2],[2,3],[3,3],[4,3],[5,3],
         [1,5],[2,5],[3,5],[4,5],[5,5],[6,5],[1,6],[6,6],[2,7],[3,7],[4,7],[5,7]],
  yellow: [[3,1],[4,1],[3,2],[4,2],[3,3],[4,3],[3,4],[4,4],[3,6],[4,6]],
  lilac: [[3,1],[4,1],[3,2],[4,2],[3,3],[4,3],[3,4],[4,4],[3,6],[4,6]],
};

function PixelGlyph({ tint }: { tint: keyof typeof TINT }) {
  const px = GLYPHS[tint] ?? [];
  return (
    <svg viewBox="0 0 8 9" className="h-6 w-6 shrink-0" shape-rendering="crispEdges"
         aria-hidden="true" style={{ opacity: 0.32 }}>
      {px.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill="currentColor" />
      ))}
    </svg>
  );
}

function BigStat({
  label, value, sub, tint,
}: {
  label: string;
  value: string;
  sub?: string;
  tint: keyof typeof TINT;
}) {
  const c = TINT[tint];
  const wordy = String(value).includes(" ");
  return (
    <div className="pixel-shadow min-w-[228px] flex-1">
      <div className="pixel-card h-full px-6 py-5" style={{ background: c.bg, color: c.fg }}>
        <div className="flex items-start justify-between gap-3">
          <div className="label" style={{ color: c.fg, opacity: 0.72 }}>{label}</div>
          <PixelGlyph tint={tint} />
        </div>

        <div
          className="num mt-2 font-semibold leading-none tracking-tight"
          style={{ fontSize: wordy ? 24 : 38 }}
        >
          {value}
        </div>

        <div className="pixel-rule mt-3.5" />

        {sub && (
          <div className="mt-3 text-[12.5px] leading-snug" style={{ opacity: 0.8 }}>
            {sub}
          </div>
        )}
      </div>
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
      className="pixel-card h-full px-6 py-5"
      style={{
        background:
          "linear-gradient(180deg, rgb(144 170 255 / 0.06), transparent 55%), var(--surface)",
        borderTop: "3px solid var(--blue-on-dark)",
      }}
    >
      <div className="text-[13px] font-semibold uppercase tracking-[0.08em]"
           style={{ color: "var(--blue-on-dark)" }}>
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
                {/* Segmented like a health bar — discrete blocks read as pixel
                    art, and make small differences easier to compare. */}
                <div className="pixel-bar h-[20px] w-full overflow-hidden"
                     style={{ background: "var(--surface-2)" }}>
                  <div className="flex h-full">
                    <span
                      className="h-full transition-[width] duration-500"
                      style={{ width: `${(v.wasted / max) * 100}%`, background: "var(--pink)" }}
                      title={`${money(v.wasted)} wasted`}
                    />
                    <span
                      className="h-full transition-[width] duration-500"
                      style={{
                        width: `${((v.total - v.wasted) / max) * 100}%`,
                        background: "var(--surface-3)",
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
          <span className="h-2.5 w-3.5" style={{ background: "var(--pink)" }} /> wasted
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
          tint="green"
        />

        <BigStat
          label="Wasted spend"
          value={money(totals.wasting)}
          sub={`${pct}% of the current monthly cloud bill`}
          tint="pink"
        />

        <BigStat
          label="Total cloud spend"
          value={money(totals.total)}
          sub={`${resources.length} resources currently in scope`}
          tint="blue"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="pixel-shadow h-full">
          <WasteBreakdown resources={resources} />
        </div>

        <div className="pixel-shadow h-full">
        <div
          className="pixel-card flex h-full flex-col px-6 py-5"
          style={{
            background:
              "linear-gradient(180deg, rgb(255 157 192 / 0.07), transparent 55%), var(--surface)",
            borderTop: "3px solid var(--pink-on-dark)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="text-[13px] font-semibold uppercase tracking-[0.08em]"
                 style={{ color: "var(--pink-on-dark)" }}>
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
                    className="pixel-sm flex w-full items-center gap-3 px-3 text-left transition-colors duration-150"
                    style={{ minHeight: 50, background: "var(--surface-2)" }}
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
    </div>
  );
}