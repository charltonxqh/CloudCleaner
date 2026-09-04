"use client";

import type { ReasoningEvent } from "@/lib/api";
import { Empty } from "./primitives";

const EVENT_COLOR: Record<string, string> = {
  finding: "var(--warn)",
  decision: "var(--primary)",
  action: "var(--danger)",
  skip: "var(--fg-faint)",
  error: "var(--danger)",
  check: "var(--fg-muted)",
  handoff: "var(--fg-muted)",
};

export function ReasoningTrail({ events }: { events: ReasoningEvent[] }) {
  if (!events.length) return <Empty>The agent&apos;s reasoning appears here as it works.</Empty>;

  return (
    <ol className="px-3 py-2">
      {events.map((e, i) => (
        <li key={i} className="mono flex gap-2 py-[3px] text-[11px] leading-snug">
          <span className="w-[76px] shrink-0 truncate" style={{ color: "var(--fg-faint)" }}>
            {e.node}
          </span>
          <span className="w-[68px] shrink-0 truncate" style={{ color: EVENT_COLOR[e.event] ?? "var(--fg-muted)" }}>
            {e.event}
          </span>
          <span className="w-40 shrink-0 truncate" style={{ color: "var(--fg-muted)" }}>
            {e.resource_id}
          </span>
          <span className="min-w-0 flex-1" style={{ color: "var(--fg)", overflowWrap: "anywhere" }}>
            {e.message}
          </span>
        </li>
      ))}
    </ol>
  );
}
