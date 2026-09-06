"use client";

import type { ReactNode } from "react";

/** 24x24 pixel logo — see app/scripts/make_logo.py, which also emits the PNGs. */
type P = [number, number];
const L_CLOUD: P[] = [[4,9], [5,9], [3,10], [4,10], [5,10], [6,10], [9,10], [10,10], [2,11], [3,11], [4,11], [5,11], [6,11], [7,11], [8,11], [9,11], [10,11], [11,11], [1,12], [2,12], [3,12], [4,12], [5,12], [6,12], [7,12], [8,12], [9,12], [10,12], [11,12], [12,12], [1,13], [2,13], [3,13], [4,13], [5,13], [6,13], [7,13], [8,13], [9,13], [10,13], [11,13], [12,13], [2,14], [3,14], [4,14], [5,14], [6,14], [7,14], [8,14], [9,14], [10,14], [11,14]];
const L_SHINE: P[] = [[3,11], [4,10]];
const L_HANDLE: P[] = [[21,3], [21,4], [21,5], [20,6], [20,7], [19,8], [19,9], [18,10]];
const L_BAND: P[] = [[17,11], [18,11], [19,11]];
const L_STRAW: P[] = [[16,12], [17,12], [18,12], [19,12], [20,12], [15,13], [16,13], [17,13], [18,13], [19,13], [20,13], [21,13], [15,14], [16,14], [17,14], [18,14], [19,14], [20,14], [21,14], [15,15], [17,15], [19,15], [21,15]];
const L_MOTES: P[] = [[6,18], [10,19], [13,18], [16,17]];
/** Tight box around the ink. Padding inside the viewBox would push the visible
 *  glyph off-centre even when the element itself is centred. */
const L_BOX = "1 3 21 17";

export type ViewId = "overview" | "resources" | "history" | "evaluation";

const NAV: { id: ViewId; label: string; icon: ReactNode }[] = [
  {
    id: "overview",
    label: "Overview",
    icon: (
      <path d="M3 13h6V3H3v10Zm0 8h6v-6H3v6Zm8 0h10V11H11v10Zm0-18v6h10V3H11Z" />
    ),
  },
  {
    id: "resources",
    label: "Resources",
    icon: (
      <path d="M4 5h16v4H4V5Zm0 6h16v4H4v-4Zm0 6h16v4H4v-4Z" />
    ),
  },
  {
    id: "history",
    label: "History",
    icon: (
      <path d="M13 3a9 9 0 1 0 8.94 10h-2.02A7 7 0 1 1 13 5v4l5-5-5-5v4Zm-1 5v5l4 2 .75-1.23L13.5 12.2V8H12Z" />
    ),
  },
  {
    id: "evaluation",
    label: "Evaluation",
    icon: (
      <path d="M4 20h16v2H4v-2Zm1-3h3V9H5v8Zm5 0h3V3h-3v14Zm5 0h3V6h-3v11Z" />
    ),
  },
];

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">
      {children}
    </svg>
  );
}

export function Sidebar({
  view, onNavigate, badges,
}: {
  view: ViewId;
  onNavigate: (v: ViewId) => void;
  badges?: Partial<Record<ViewId, string | number>>;
}) {
  return (
    <nav
      aria-label="Sections"
      className="flex shrink-0 gap-1 overflow-x-auto px-2 py-2 lg:w-[210px] lg:flex-col lg:overflow-visible lg:px-3 lg:py-4"
      style={{ background: "var(--nav)", color: "var(--nav-fg)" }}
    >
      <div
        className="mb-4 hidden flex-col items-center gap-1 px-2 pb-5 text-center lg:flex"
        style={{ borderBottom: "1px solid var(--nav-2)" }}
      >
        <svg
          viewBox={L_BOX}
          className="h-[86px] w-[112px] shrink-0"
          shapeRendering="crispEdges"
          role="img"
          aria-label="CloudCleaner"
          style={{ color: "var(--nav-fg)" }}
        >
          <title>CloudCleaner</title>
          {L_CLOUD.map(([x, y]) => (
            <rect key={`c${x}-${y}`} x={x} y={y} width="1" height="1" fill="currentColor" />
          ))}
          {L_SHINE.map(([x, y]) => (
            <rect key={`s${x}-${y}`} x={x} y={y} width="1" height="1" fill="#c9cdd4" />
          ))}
          {L_HANDLE.map(([x, y]) => (
            <rect key={`h${x}-${y}`} x={x} y={y} width="1" height="1" fill="#c08b4e" />
          ))}
          {L_BAND.map(([x, y]) => (
            <rect key={`b${x}-${y}`} x={x} y={y} width="1" height="1" fill="#8a5f2e" />
          ))}
          {L_STRAW.map(([x, y]) => (
            <rect key={`w${x}-${y}`} x={x} y={y} width="1" height="1" fill="#f0cf5a" />
          ))}
          {L_MOTES.map(([x, y]) => (
            <rect key={`m${x}-${y}`} x={x} y={y} width="1" height="1"
                  fill="currentColor" opacity=".45" />
          ))}
        </svg>
        <div className="min-w-0">
          <div className="pixel-type text-[26px] leading-tight"
               style={{ color: "var(--nav-fg)" }}>
            CloudCleaner
          </div>
          <div className="mt-1 text-[13px] leading-snug"
               style={{ color: "var(--nav-fg-muted)" }}>
            AWS lifecycle agent · us-east-1
          </div>
        </div>
      </div>

      {NAV.map((item) => {
        const active = view === item.id;
        return (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            aria-current={active ? "page" : undefined}
            className={`${active ? "pixel-sm" : ""} flex shrink-0 items-center gap-3 px-3 text-[15px] transition-colors duration-150`}
            style={{
              minHeight: 42,
              borderRadius: active ? 0 : "var(--radius)",
              background: active ? "var(--nav-2)" : "transparent",
              color: active ? "var(--nav-fg)" : "var(--nav-fg-muted)",
              fontWeight: active ? 600 : 400,
            }}
          >
            <Icon>{item.icon}</Icon>
            <span className="whitespace-nowrap">{item.label}</span>

            {badges?.[item.id] !== undefined && (
              <span
                className="num ml-auto hidden px-2 py-0.5 text-[12.5px] lg:inline"
                style={{
                  background: "rgb(255 255 255 / 0.1)",
                  color: "var(--nav-fg-muted)",
                  borderRadius: 999,
                }}
              >
                {badges[item.id]}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

export function ViewHeader({
  title, subtitle, actions,
}: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header
      className="flex shrink-0 flex-wrap items-center justify-between gap-4 px-6 pb-4 pt-5"
      style={{ background: "var(--bg)" }}
    >
      <div className="min-w-0">
        <h1 className="pixel-type truncate text-[34px] leading-tight">{title}</h1>
        {subtitle && (
          <p className="mt-1 text-[15px] leading-snug" style={{ color: "var(--fg-muted)" }}>
            {subtitle}
          </p>
        )}
      </div>

      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}