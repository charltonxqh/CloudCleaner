"use client";

import { useMemo, useState } from "react";

import { money, type Recommendation, type Resource } from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

const TYPE_LABEL: Record<string, string> = {
  ec2: "EC2", ebs: "EBS", eip: "EIP", snapshot: "SNAP",
};

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
  resources, selected, busy, verdicts, onSelect,
}: {
  resources: Resource[];
  selected: string | null;
  busy: string | null;
  verdicts: Record<string, Recommendation["action"]>;
  onSelect: (r: Resource) => void;
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

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        className="flex shrink-0 flex-wrap items-center gap-2 px-5 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex gap-1" role="group" aria-label="Filter resources">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              aria-pressed={filter === f.id}
              className="px-2.5 text-[12px] transition-colors duration-150"
              style={{
                minHeight: 30,
                borderRadius: "var(--radius)",
                background: filter === f.id ? "var(--primary-dim)" : "transparent",
                color: filter === f.id ? "var(--primary)" : "var(--fg-muted)",
                border: `1px solid ${filter === f.id ? "var(--primary)" : "var(--border)"}`,
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
          className="mono ml-auto w-[220px] px-2.5 text-[12px] outline-none"
          style={{
            minHeight: 30, background: "var(--bg)", color: "var(--fg)",
            border: "1px solid var(--border-strong)", borderRadius: "var(--radius)",
          }}
        />
        <span className="num text-[11px]" style={{ color: "var(--fg-faint)" }}>
          {rows.length} · {money(shown)}/mo
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <Empty>No resources match that filter.</Empty>
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead className="sticky top-0 z-10">
              <tr style={{ background: "var(--surface-2)" }}>
                {["Resource", "Type", "State", "Attached to", "Verdict", "$/mo"].map((h, i) => (
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
                      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(r); }
                    }}
                    className="rise cursor-pointer transition-colors duration-150"
                    style={{
                      ["--i" as string]: i,
                      background: isSelected ? "var(--surface-3)" : "transparent",
                      boxShadow: isSelected ? "inset 2px 0 0 var(--primary)" : "none",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <td className="px-4 py-2.5">
                      <div className="mono truncate text-[12px]">{r.resource_id}</div>
                      <div
                        className={`truncate text-[11px] ${isBusy ? "pulse" : ""}`}
                        style={{ color: isBusy ? "var(--primary)" : "var(--fg-faint)" }}
                      >
                        {isBusy ? "investigating…" : r.name || (r.size_gb ? `${r.size_gb} GB` : "untagged")}
                      </div>
                    </td>
                    <td className="mono px-4 py-2.5 text-[11px]" style={{ color: "var(--fg-muted)" }}>
                      {TYPE_LABEL[r.resource_type] ?? r.resource_type.toUpperCase()}
                    </td>
                    <td className="px-4 py-2.5">
                      <Tag
                        tone={r.billing_while_stopped ? "danger" : r.state === "running" ? "ok" : "muted"}
                        dot={r.billing_while_stopped}
                      >
                        {r.state ?? "—"}
                      </Tag>
                    </td>
                    <td className="mono px-4 py-2.5 text-[11px]" style={{ color: "var(--fg-muted)" }}>
                      {r.attached_to ?? <span style={{ color: "var(--fg-faint)" }}>nothing</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      {verdict ? (
                        <Tag tone={VERDICT_TONE[verdict]}>{verdict.replace("_", " ")}</Tag>
                      ) : (
                        <span className="text-[11px]" style={{ color: "var(--fg-faint)" }}>—</span>
                      )}
                    </td>
                    <td
                      className="num px-4 py-2.5 text-right"
                      style={{ color: r.billing_while_stopped ? "var(--danger)" : "var(--fg)" }}
                    >
                      {money(r.estimated_monthly_cost)}
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
