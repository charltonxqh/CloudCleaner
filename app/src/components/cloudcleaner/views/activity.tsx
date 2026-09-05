"use client";

import { useMemo, useState } from "react";

import type { ReasoningEvent } from "@/lib/api";
import { Empty, Tag, type Tone } from "../primitives";

const EVENT_TONE: Record<string, Tone> = {
  finding: "warn", decision: "info", action: "danger", error: "danger",
  skip: "muted", check: "muted", handoff: "muted",
};

const NODE_ORDER = [
  "detect", "investigate", "assess", "plan", "policy_check",
  "approval", "execute", "verify", "rollback", "record",
];

export function ActivityView({ events }: { events: ReasoningEvent[] }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const nodes = useMemo(() => {
    const seen = new Set(events.map((e) => e.node));
    return NODE_ORDER.filter((n) => seen.has(n));
  }, [events]);

  const shown = events.filter((e) => !hidden.has(e.node));

  if (!events.length) {
    return (
      <Empty>
        The agent&apos;s reasoning appears here, one event per decision. Investigate a
        resource to populate it.
      </Empty>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        className="flex shrink-0 flex-wrap items-center gap-1.5 px-5 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span className="label mr-1">Nodes</span>
        {nodes.map((n) => {
          const off = hidden.has(n);
          return (
            <button
              key={n}
              aria-pressed={!off}
              onClick={() =>
                setHidden((h) => {
                  const next = new Set(h);
                  if (off) next.delete(n); else next.add(n);
                  return next;
                })
              }
              className="mono px-2 text-[11px] transition-colors duration-150"
              style={{
                minHeight: 26,
                borderRadius: "var(--radius)",
                background: off ? "transparent" : "var(--surface-2)",
                color: off ? "var(--fg-faint)" : "var(--fg)",
                border: `1px solid ${off ? "var(--border)" : "var(--border-strong)"}`,
                textDecoration: off ? "line-through" : "none",
              }}
            >
              {n}
            </button>
          );
        })}
        <span className="num ml-auto text-[11px]" style={{ color: "var(--fg-faint)" }}>
          {shown.length} of {events.length} events
        </span>
      </div>

      <ol className="min-h-0 flex-1 overflow-auto px-5 py-2">
        {shown.map((e, i) => (
          <li
            key={i}
            className="flex items-baseline gap-3 py-1"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <span className="mono w-[62px] shrink-0 text-[10.5px]" style={{ color: "var(--fg-faint)" }}>
              {new Date(e.ts).toLocaleTimeString(undefined, { hour12: false })}
            </span>
            <span className="mono w-[86px] shrink-0 truncate text-[11px]" style={{ color: "var(--fg-muted)" }}>
              {e.node}
            </span>
            <span className="w-[72px] shrink-0">
              <Tag tone={EVENT_TONE[e.event] ?? "muted"}>{e.event}</Tag>
            </span>
            <span className="mono w-[176px] shrink-0 truncate text-[11px]" style={{ color: "var(--fg-muted)" }}>
              {e.resource_id}
            </span>
            <span
              className="min-w-0 flex-1 text-[12px] leading-snug"
              style={{ color: "var(--fg)", overflowWrap: "anywhere" }}
            >
              {e.message}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
