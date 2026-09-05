"use client";

import type { ReactNode } from "react";

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
      style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
    >
      <div
        className="mb-3 hidden items-center gap-3 px-2 pb-4 lg:flex"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <span
          aria-hidden="true"
          className="grid h-8 w-8 shrink-0 place-items-center text-[14px] font-bold"
          style={{
            background: "var(--primary)",
            color: "var(--on-primary)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow)",
          }}
        >
          C
        </span>
        <div className="min-w-0">
          <div className="truncate text-[15px] font-semibold leading-tight">CloudCleaner</div>
          <div className="mt-0.5 truncate text-[11px] leading-tight" style={{ color: "var(--fg-faint)" }}>
            us-east-1
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
            className="flex shrink-0 items-center gap-3 px-3 text-[14px] transition-colors duration-150"
            style={{
              minHeight: 42,
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
                className="num ml-auto hidden px-2 py-0.5 text-[11px] lg:inline"
                style={{
                  background: "var(--surface-3)",
                  color: "var(--fg-faint)",
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
      className="flex shrink-0 flex-wrap items-center justify-between gap-4 px-6 py-4"
      style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}
    >
      <div className="min-w-0">
        <h1 className="text-[19px] font-semibold leading-tight tracking-tight">{title}</h1>
        {subtitle && (
          <p className="mt-1 text-[13px] leading-tight" style={{ color: "var(--fg-faint)" }}>
            {subtitle}
          </p>
        )}
      </div>

      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}