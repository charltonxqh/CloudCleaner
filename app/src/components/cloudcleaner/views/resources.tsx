"use client";

import { useMemo, useState } from "react";

import { money, type Recommendation, type Resource } from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

const TYPE_LABEL: Record<string, string> = {
  ec2: "EC2", ebs: "EBS", eip: "EIP", snapshot: "SNAP",
};

/** Type gets its own colour and 7x7 glyph, so a long list can be scanned by
 *  shape rather than read row by row. */
const TYPE_STYLE: Record<string, { fg: string; bg: string; px: [number, number][] }> = {
  ec2: {
    fg: "var(--blue-on-dark)", bg: "rgb(144 170 255 / 0.12)",
    px: [[1,1],[2,1],[3,1],[4,1],[5,1],[1,2],[5,2],[1,3],[5,3],[1,4],[2,4],[3,4],[4,4],[5,4],
         [2,5],[4,5]],
  },
  ebs: {
    fg: "var(--green-on-dark)", bg: "rgb(103 227 196 / 0.12)",
    px: [[2,0],[3,0],[4,0],[1,1],[5,1],[1,2],[5,2],[2,3],[3,3],[4,3],[1,4],[5,4],[1,5],[5,5],
         [2,6],[3,6],[4,6]],
  },
  eip: {
    fg: "var(--yellow-on-dark)", bg: "rgb(255 215 110 / 0.12)",
    px: [[3,0],[3,1],[2,2],[3,2],[4,2],[1,3],[5,3],[3,4],[3,5],[2,6],[3,6],[4,6]],
  },
  snapshot: {
    fg: "#b9a3ff", bg: "rgb(185 163 255 / 0.12)",
    px: [[1,1],[2,1],[3,1],[4,1],[5,1],[1,2],[3,2],[5,2],[1,3],[5,3],[1,4],[2,4],[3,4],[4,4],[5,4]],
  },
};

function TypeBadge({ type }: { type: string }) {
  const s = TYPE_STYLE[type];
  const label = TYPE_LABEL[type] ?? type.toUpperCase();
  if (!s) return <span className="mono text-[12px]">{label}</span>;

  return (
    <span
      className="pixel-sm mono inline-flex items-center gap-1.5 px-1.5 py-[3px] text-[11px] font-semibold"
      style={{ color: s.fg, background: s.bg }}
    >
      <svg viewBox="0 0 7 7" width="11" height="11" shape-rendering="crispEdges" aria-hidden="true">
        {s.px.map(([x, y]) => (
          <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill="currentColor" />
        ))}
      </svg>
      {label}
    </span>
  );
}

const VERDICT_TONE: Record<string, Tone> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

type Filter = "all" | "wasting" | "ec2" | "orphans";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "wasting", label: "Billing while stopped" },
  { id: "orphans", label: "Orphans" },
  { id: "ec2", label: "Instances" },
];

function matches(r: Resource, f: Filter) {
  if (f === "wasting") return r.billing_while_stopped;
  if (f === "ec2") return r.resource_type === "ec2";
  if (f === "orphans") return r.attached_to === null && r.resource_type !== "ec2";
  return true;
}

export function ResourcesView({
  resources, selected, busy, verdicts, onSelect, compact = false,
}: {
  resources: Resource[];
  selected: string | null;
  busy: string | null;
  verdicts: Record<string, Recommendation["action"]>;
  onSelect: (r: Resource) => void;
  compact?: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return resources
      .filter((r) => matches(r, filter))
      .filter((r) =>
        !q ||
        r.resource_id.toLowerCase().includes(q) ||
        (r.name ?? "").toLowerCase().includes(q) ||
        Object.values(r.tags).some((v) => v.toLowerCase().includes(q))
      )
      .sort((a, b) => (b.estimated_monthly_cost ?? 0) - (a.estimated_monthly_cost ?? 0));
  }, [resources, filter, query]);

  const shown = rows.reduce((s, r) => s + (r.estimated_monthly_cost ?? 0), 0);
  const maxCost = Math.max(...rows.map((r) => r.estimated_monthly_cost ?? 0), 1);

  return (
    <div
      className="flex min-h-0 flex-1 flex-col overflow-hidden"
      style={{ background: "var(--surface)", borderRadius: "var(--radius-lg)" }}
    >
      <div
        className="flex shrink-0 flex-wrap items-center gap-2.5 px-5 py-3.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter resources">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              aria-pressed={filter === f.id}
              className="pixel-sm px-3 text-[13px] transition-colors duration-150"
              style={{
                minHeight: 34,
                background: filter === f.id ? "var(--btn)" : "var(--surface-2)",
                color: filter === f.id ? "var(--btn-fg)" : "var(--fg-muted)",
                border: "1px solid transparent",
                fontWeight: filter === f.id ? 600 : 400,
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <label htmlFor="filter-q" className="sr-only">Search resources</label>
        <input
          id="filter-q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search id, name or tag…"
          className="pixel-sm mono ml-auto px-3 text-[13px] outline-none"
          style={{
            width: compact ? 190 : 250,
            minHeight: 34,
            background: "var(--surface-2)",
            color: "var(--fg)",
            border: "1px solid transparent",
          }}
        />

        <span className="num text-[12px]" style={{ color: "var(--fg-faint)" }}>
          {rows.length} · {money(shown)}/mo
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <Empty>No resources match that filter.</Empty>
        ) : (
          <table className="w-full border-collapse text-[14px]">
            <colgroup>
              {(compact
                ? ["auto", "128px", "132px", "116px"]
                : ["auto", "104px", "148px", "184px", "128px", "116px"]
              ).map((w, i) => <col key={i} style={{ width: w }} />)}
            </colgroup>
            <thead className="sticky top-0 z-10">
              <tr style={{ background: "var(--surface-2)" }}>
                {(compact
                  ? ["Resource", "State", "Verdict", "$/mo"]
                  : ["Resource", "Type", "State", "Attached to", "Verdict", "$/mo"]
                ).map((h, i, headers) => (
                  <th
                    key={h}
                    scope="col"
                    className={`label px-4 py-2.5 ${
                      i === headers.length - 1 ? "text-right" : "text-left"
                    }`}
                    style={{ borderBottom: "2px solid var(--border-strong)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {rows.map((r, i) => {
                const isSelected = r.resource_id === selected;
                const isBusy = busy === r.resource_id;
                const verdict = verdicts[r.resource_id];

                return (
                  <tr
                    key={r.resource_id}
                    onClick={() => onSelect(r)}
                    tabIndex={0}
                    role="button"
                    aria-pressed={isSelected}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelect(r);
                      }
                    }}
                    className="rise row cursor-pointer transition-colors duration-150"
                    style={{
                      ["--i" as string]: i,
                      background: isSelected ? "var(--surface-3)" : "transparent",
                      boxShadow: isSelected ? "inset 3px 0 0 var(--blue-on-dark)" : "none",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <td className="px-4 py-2.5">
                      <div className="mono truncate text-[13px]"
                           style={{ color: isSelected ? "var(--fg)" : "var(--fg)" }}>
                        {r.resource_id}
                      </div>
                      <div
                        className={`mt-1 truncate text-[12px] ${isBusy ? "pulse" : ""}`}
                        style={{ color: isBusy ? "var(--primary)" : "var(--fg-faint)" }}
                      >
                        {isBusy
                          ? "investigating…"
                          : r.name || (r.size_gb ? `${r.size_gb} GB` : "untagged")}
                      </div>
                    </td>

                    {!compact && (
                      <td className="px-4 py-2.5">
                        <TypeBadge type={r.resource_type} />
                      </td>
                    )}

                    <td className="px-4 py-2.5">
                      <Tag
                        tone={r.billing_while_stopped ? "danger" : r.state === "running" ? "ok" : "muted"}
                        dot={r.billing_while_stopped}
                      >
                        {r.state ?? "—"}
                      </Tag>
                    </td>

                    {!compact && (
                      <td className="mono px-4 py-2.5 text-[12px]" style={{ color: "var(--fg-muted)" }}>
                        {r.attached_to ?? <span style={{ color: "var(--fg-faint)" }} title="not attached to anything">—</span>}
                      </td>
                    )}

                    <td className="px-4 py-2.5">
                      {verdict ? (
                        <Tag tone={VERDICT_TONE[verdict]}>{verdict.replace("_", " ")}</Tag>
                      ) : (
                        <span className="text-[12px]" style={{ color: "var(--fg-faint)" }}>—</span>
                      )}
                    </td>

                    <td className="px-4 py-2.5 text-right">
                      <div
                        className="num text-[14px]"
                        style={{ color: r.billing_while_stopped ? "var(--danger)" : "var(--fg)" }}
                      >
                        {money(r.estimated_monthly_cost)}
                      </div>
                      <div
                        className="pixel-bar mt-1.5 ml-auto h-[5px] w-[72px]"
                        style={{ background: "var(--surface-2)" }}
                        title={`${Math.round(((r.estimated_monthly_cost ?? 0) / maxCost) * 100)}% of the largest`}
                      >
                        <span
                          className="block h-full"
                          style={{
                            width: `${((r.estimated_monthly_cost ?? 0) / maxCost) * 100}%`,
                            background: r.billing_while_stopped
                              ? "var(--pink)" : "var(--border-strong)",
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}