"use client";

import { money, type Recommendation, type Resource } from "@/lib/api";
import { Tag } from "./primitives";

const TYPE_LABEL: Record<string, string> = {
  ec2: "EC2", ebs: "EBS", eip: "EIP", snapshot: "SNAP",
};

function stateTone(r: Resource) {
  if (r.billing_while_stopped) return "danger" as const;
  if (r.state === "running") return "ok" as const;
  return "muted" as const;
}

const VERDICT_TONE: Record<string, "ok" | "warn" | "danger"> = {
  keep: "ok", investigate_more: "warn", stop: "warn", retire: "danger",
};

export function ResourceTable({
  resources, selected, busy, verdicts, onSelect,
}: {
  resources: Resource[];
  selected: string | null;
  busy: string | null;
  verdicts: Record<string, Recommendation["action"]>;
  onSelect: (r: Resource) => void;
}) {
  return (
    <table className="w-full border-collapse text-[13px]">
      <thead className="sticky top-0 z-10" style={{ background: "var(--surface-2)" }}>
        <tr style={{ color: "var(--fg-faint)" }}>
          {["Resource", "Type", "State", "Verdict", "$/mo"].map((h, i) => (
            <th
              key={h}
              scope="col"
              className={`px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.09em] ${
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
        {resources.map((r) => {
          const isSelected = r.resource_id === selected;
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
              className="cursor-pointer transition-colors duration-150"
              style={{
                background: isSelected ? "var(--surface-2)" : "transparent",
                borderLeft: `2px solid ${isSelected ? "var(--primary)" : "transparent"}`,
                borderBottom: "1px solid var(--border)",
              }}
            >
              <td className="px-3 py-2">
                <div className="mono truncate text-[12px]" style={{ color: "var(--fg)" }}>
                  {r.resource_id}
                </div>
                <div className="truncate text-[11px]" style={{ color: "var(--fg-faint)" }}>
                  {r.name || (r.size_gb ? `${r.size_gb} GB` : "untagged")}
                  {busy === r.resource_id && " · investigating…"}
                </div>
              </td>
              <td className="px-3 py-2">
                <span className="mono text-[11px]" style={{ color: "var(--fg-muted)" }}>
                  {TYPE_LABEL[r.resource_type] ?? r.resource_type.toUpperCase()}
                </span>
              </td>
              <td className="px-3 py-2">
                <Tag
                  tone={stateTone(r)}
                  title={r.billing_while_stopped ? "Not running, but still billing" : undefined}
                >
                  {r.state ?? "—"}
                </Tag>
              </td>
              <td className="px-3 py-2">
                {verdicts[r.resource_id] ? (
                  <Tag tone={VERDICT_TONE[verdicts[r.resource_id]]}>
                    {verdicts[r.resource_id].replace("_", " ")}
                  </Tag>
                ) : (
                  <span className="text-[11px]" style={{ color: "var(--fg-faint)" }}>—</span>
                )}
              </td>
              <td
                className="num px-3 py-2 text-right"
                style={{ color: r.billing_while_stopped ? "var(--danger)" : "var(--fg)" }}
              >
                {money(r.estimated_monthly_cost)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
