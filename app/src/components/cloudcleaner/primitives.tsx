"use client";

import type { ReactNode } from "react";

export function Panel({
  title, right, children, className = "",
}: { title?: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section
      className={`flex min-h-0 flex-col ${className}`}
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      {title && (
        <header
          className="flex shrink-0 items-center justify-between px-4 py-2"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <h2
            className="text-[11px] font-semibold uppercase tracking-[0.09em]"
            style={{ color: "var(--fg-muted)" }}
          >
            {title}
          </h2>
          {right}
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  );
}

const TONE: Record<string, { fg: string; bd: string }> = {
  danger: { fg: "var(--danger)", bd: "var(--danger)" },
  warn: { fg: "var(--warn)", bd: "var(--warn)" },
  ok: { fg: "var(--ok)", bd: "var(--ok)" },
  info: { fg: "var(--primary)", bd: "var(--primary)" },
  muted: { fg: "var(--fg-faint)", bd: "var(--border-strong)" },
};

export function Tag({
  children, tone = "muted", title,
}: { children: ReactNode; tone?: keyof typeof TONE; title?: string }) {
  const t = TONE[tone] ?? TONE.muted;
  return (
    <span
      title={title}
      className="mono inline-block shrink-0 px-1.5 py-[1px] text-[10px] font-medium uppercase tracking-wide"
      style={{ color: t.fg, border: `1px solid ${t.bd}`, borderRadius: 2 }}
    >
      {children}
    </span>
  );
}

export function Stat({
  label, value, tone, hint,
}: { label: string; value: ReactNode; tone?: string; hint?: string }) {
  return (
    <div className="px-4 py-3" style={{ borderRight: "1px solid var(--border)" }}>
      <div
        className="text-[10px] font-medium uppercase tracking-[0.09em]"
        style={{ color: "var(--fg-faint)" }}
      >
        {label}
      </div>
      <div className="num mt-1 text-[19px] font-semibold leading-none" style={{ color: tone }}>
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-[11px]" style={{ color: "var(--fg-faint)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div
      className="flex h-full items-center justify-center px-6 text-center text-[13px]"
      style={{ color: "var(--fg-faint)" }}
    >
      {children}
    </div>
  );
}
