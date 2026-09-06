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
    <svg viewBox="0 0 8 9" className="h-6 w-6 shrink-0" shapeRendering="crispEdges"
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
          <div
            className="label font-bold leading-tight"
            style={{ color: c.fg, fontSize: 25, letterSpacing: "0.01em" }}
          >
            {label}
          </div>
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
          <div className="mt-3 text-[13.5px] leading-snug" style={{ opacity: 0.8 }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}

/** Horizontal bar — a chart type that survives a screen reader, unlike a pie. */

/** 7x7 marks for the two lower panels, same grid as the logo. */
const PANEL_GLYPH: Record<string, [number, number][]> = {
  bars: [[0,6],[1,6],[2,6],[3,6],[4,6],[5,6],[6,6],
         [1,4],[1,5],[3,2],[3,3],[3,4],[3,5],[5,0],[5,1],[5,2],[5,3],[5,4],[5,5]],
  drain: [[1,0],[2,0],[3,0],[4,0],[5,0],[1,1],[5,1],[2,2],[3,2],[4,2],
          [3,3],[3,4],[2,5],[4,5],[3,6]],
};

function PanelMark({ kind, colour }: { kind: "bars" | "drain"; colour: string }) {
  return (
    <svg viewBox="0 0 7 7" width="18" height="18" shapeRendering="crispEdges"
         aria-hidden="true" style={{ color: colour }}>
      {PANEL_GLYPH[kind].map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill="currentColor" />
      ))}
    </svg>
  );
}


const METER_CELLS = 22;

/** A block meter, like a health bar. Discrete cells make small differences
 *  easier to compare than a smooth fill, and they read as pixel art. */
function BlockMeter({ wasted, total, max }: { wasted: number; total: number; max: number }) {
  const cells = (n: number) => Math.round((n / max) * METER_CELLS);
  const wastedCells = Math.min(cells(wasted), METER_CELLS);
  const usedCells = Math.min(cells(total) - wastedCells, METER_CELLS - wastedCells);
  const share = total ? Math.round((wasted / total) * 100) : 0;

  return (
    <div className="group relative">
      <div
        className="flex gap-[3px]"
        role="img"
        aria-label={`${money(wasted)} of ${money(total)} wasted`}
      >
        {Array.from({ length: METER_CELLS }, (_, i) => {
          // Three states, and they have to be told apart at a glance: pink is
          // wasted, blue is genuinely in use, and the rest is empty track.
          // --surface-3 was too close to the empty cells to read as a category.
          const filled = i < wastedCells ? "var(--pink)"
            : i < wastedCells + usedCells ? "rgb(144 170 255 / 0.45)"
            : "rgb(255 255 255 / 0.035)";
          return (
            <span
              key={i}
              className="h-[22px] flex-1 transition-colors duration-300"
              style={{ background: filled, transitionDelay: `${i * 18}ms` }}
            />
          );
        })}
      </div>

      {/* Reveals the split the meter can only approximate. */}
      <div
        className="pixel-sm pointer-events-none absolute -top-1 left-1/2 z-20 hidden
                   -translate-x-1/2 -translate-y-full whitespace-nowrap px-3 py-2
                   group-hover:block"
        style={{ background: "var(--surface-3)", boxShadow: "0 4px 0 rgb(0 0 0 / 0.45)" }}
      >
        <div className="num text-[14px] font-bold" style={{ color: "var(--pink-on-dark)" }}>
          {money(wasted)} wasted
        </div>
        <div className="num mt-0.5 text-[12.5px]" style={{ color: "var(--fg-muted)" }}>
          {money(total - wasted)} in use · {share}% of {money(total)}
        </div>
      </div>
    </div>
  );
}

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
      <div className="flex items-center gap-2.5">
        <PanelMark kind="bars" colour="var(--blue-on-dark)" />
        <span className="font-bold uppercase leading-tight"
              style={{ color: "var(--blue-on-dark)", fontSize: 20, letterSpacing: "0.01em" }}>
          Spend by resource type
        </span>
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
                className="w-[168px] py-2.5 pr-4 text-left text-[16px] font-medium"
                style={{ color: "var(--fg-muted)" }}
              >
                {TYPE_LABEL[type] ?? type}
                <span className="ml-2 text-[14px]" style={{ color: "var(--fg-faint)" }}>
                  ×{v.count}
                </span>
              </th>
              <td className="py-2.5">
                <BlockMeter wasted={v.wasted} total={v.total} max={max} />
              </td>
              <td className="num w-[96px] py-2.5 pl-4 text-right text-[17px] font-semibold">
                {money(v.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-4 flex gap-5 text-[14px]" style={{ color: "var(--fg-muted)" }}>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-3.5" style={{ background: "var(--pink)" }} /> wasted
        </span>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-3.5" style={{ background: "rgb(144 170 255 / 0.45)" }} /> in use
        </span>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-3.5" style={{ background: "rgb(255 255 255 / 0.035)" }} />
          no spend
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
            <div className="flex items-center gap-2.5">
              <PanelMark kind="drain" colour="var(--pink-on-dark)" />
              <span className="font-bold uppercase leading-tight"
                    style={{ color: "var(--pink-on-dark)", fontSize: 20, letterSpacing: "0.01em" }}>
                Paying for nothing
              </span>
            </div>
            <span
              className="pixel-sm num px-2.5 py-[3px] text-[17px] font-bold"
              style={{ background: "var(--pink)", color: "var(--pink-fg)" }}
            >
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
                      <span className="mono block truncate text-[14px]">{r.resource_id}</span>
                      <span className="mt-0.5 block truncate text-[13.5px]" style={{ color: "var(--fg-faint)" }}>
                        {r.name || (r.size_gb ? `${r.size_gb} GB` : "untagged")} · {r.state}
                      </span>
                    </span>

                    {verdicts[r.resource_id] && (
                      <Tag tone={VERDICT_TONE[verdicts[r.resource_id]]}>
                        {verdicts[r.resource_id].replace("_", " ")}
                      </Tag>
                    )}

                    <span className="num shrink-0 text-[15px]" style={{ color: "var(--danger)" }}>
                      {money(r.estimated_monthly_cost)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-auto pt-4 text-[13.5px] leading-relaxed" style={{ color: "var(--fg-faint)" }}>
            Stopping an instance releases compute only. Attached volumes and public IPv4
            addresses keep billing until they are explicitly released.
          </p>
        </div>
        </div>
      </div>
    </div>
  );
}