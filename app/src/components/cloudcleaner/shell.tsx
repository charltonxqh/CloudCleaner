"use client";

import type { ReactNode } from "react";

export type ViewId = "overview" | "resources" | "investigation" | "history" | "activity";

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
    id: "investigation",
    label: "Investigation",
    icon: (
      <path d="M10 2a8 8 0 1 0 4.9 14.32l5.39 5.39 1.42-1.42-5.39-5.39A8 8 0 0 0 10 2Zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12Z" />
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
    id: "activity",
    label: "Activity",
    icon: (
      <path d="M3 12h3l3 8 6-16 3 8h3" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
];

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true">
      {children}
    </svg>
  );
}

export function Sidebar({
  view, onNavigate, badges, potentialSavings,
}: {
  view: ViewId;
  onNavigate: (v: ViewId) => void;
  badges?: Partial<Record<ViewId, string | number>>;
  potentialSavings?: { monthly: number; yearly: number } | null;
}) {
  return (
    <nav
      aria-label="Sections"
      className="flex shrink-0 gap-1 overflow-x-auto px-2 py-2 lg:w-[188px] lg:flex-col lg:overflow-visible lg:px-2.5 lg:py-3"
      style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
    >
      <div className="mb-1 hidden items-center gap-2.5 px-2 pb-3 lg:flex"
           style={{ borderBottom: "1px solid var(--border)" }}>
        <span
          aria-hidden="true"
          className="grid h-7 w-7 shrink-0 place-items-center text-[13px] font-bold"
          style={{
            background: "var(--primary)", color: "var(--on-primary)",
            borderRadius: "var(--radius)", boxShadow: "var(--shadow)",
          }}
        >
          C
        </span>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold leading-tight">CloudCleaner</div>
          <div className="truncate text-[10px] leading-tight" style={{ color: "var(--fg-faint)" }}>
            us-east-1
          </div>
        </div>
      </div>

      {potentialSavings && (
        <div
          className="mb-2 hidden px-2.5 py-3 lg:block"
          style={{
            background: "var(--ok-dim)",
            border: "1px solid var(--ok)",
            borderRadius: "var(--radius)",
          }}
        >
          <div className="label" style={{ color: "var(--ok)" }}>Potential savings</div>
          <div className="num mt-1 text-[22px] font-semibold leading-none" style={{ color: "var(--ok)" }}>
            ${potentialSavings.monthly.toFixed(2)}
          </div>
          <div className="mt-1 text-[10px]" style={{ color: "var(--fg-faint)" }}>
            per month · ${potentialSavings.yearly.toFixed(2)}/yr
          </div>
        </div>
      )}

      {NAV.map((item) => {
        const active = view === item.id;
        return (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            aria-current={active ? "page" : undefined}
            className="flex shrink-0 items-center gap-2.5 px-2.5 text-[12.5px] transition-colors duration-150"
            style={{
              minHeight: 34,
              borderRadius: "var(--radius)",
              background: active ? "var(--primary-dim)" : "transparent",
              color: active ? "var(--primary)" : "var(--fg-muted)",
              fontWeight: active ? 600 : 400,
            }}
          >
            <Icon>{item.icon}</Icon>
            <span className="whitespace-nowrap">{item.label}</span>
            {badges?.[item.id] !== undefined && (
              <span
                className="num ml-auto hidden px-1.5 text-[10px] lg:inline"
                style={{
                  background: "var(--surface-3)", color: "var(--fg-faint)",
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
      className="flex shrink-0 flex-wrap items-center justify-between gap-3 px-5 py-3"
      style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}
    >
      <div className="min-w-0">
        <h1 className="text-[16px] font-semibold leading-tight tracking-tight">{title}</h1>
        {subtitle && (
          <p className="mt-0.5 text-[12px] leading-tight" style={{ color: "var(--fg-faint)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
