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
          className="flex h-9 shrink-0 items-center justify-between px-4"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
        >
          <h2 className="label">{title}</h2>
          {right}
        </header>
      )}
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </section>
  );
}

const TONE = {
  danger: { fg: "var(--danger)", bg: "var(--danger-dim)" },
  warn: { fg: "var(--warn)", bg: "var(--warn-dim)" },
  ok: { fg: "var(--ok)", bg: "var(--ok-dim)" },
  info: { fg: "var(--primary)", bg: "var(--primary-dim)" },
  muted: { fg: "var(--fg-faint)", bg: "transparent" },
} as const;

export type Tone = keyof typeof TONE;

export function Tag({
  children, tone = "muted", title, dot = false,
}: { children: ReactNode; tone?: Tone; title?: string; dot?: boolean }) {
  const t = TONE[tone];
  return (
    <span
      title={title}
      className="mono inline-flex shrink-0 items-center gap-1.5 px-1.5 py-[2px] text-[10px] font-medium uppercase tracking-wide"
      style={{
        color: t.fg,
        background: t.bg,
        border: `1px solid ${tone === "muted" ? "var(--border-strong)" : t.fg}`,
        borderRadius: 2,
      }}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: t.fg }}
        />
      )}
      {children}
    </span>
  );
}

export function Stat({
  label, value, tone, hint, loading = false,
}: { label: string; value: ReactNode; tone?: string; hint?: string; loading?: boolean }) {
  return (
    <div
      className="min-w-[112px] px-4 py-2.5"
      style={{ borderRight: "1px solid var(--border)" }}
    >
      <div className="label">{label}</div>
      <div
        className={`num mt-1 text-[20px] font-semibold leading-none tracking-tight ${loading ? "pulse" : ""}`}
        style={{ color: tone ?? "var(--fg)" }}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-[11px] leading-tight" style={{ color: "var(--fg-faint)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}

export function Empty({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
      {icon && <div style={{ color: "var(--fg-faint)", opacity: 0.5 }}>{icon}</div>}
      <p className="max-w-[38ch] text-[13px] leading-relaxed" style={{ color: "var(--fg-faint)" }}>
        {children}
      </p>
    </div>
  );
}

export function Button({
  children, onClick, variant = "ghost", disabled, type = "button", title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "ghost" | "primary" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  const styles = {
    ghost: {
      background: "var(--surface-2)", color: "var(--fg-muted)",
      border: "1px solid var(--border-strong)",
    },
    primary: {
      background: "var(--primary)", color: "var(--on-primary)",
      border: "1px solid var(--primary)",
    },
    danger: {
      background: "var(--danger)", color: "#fff",
      border: "1px solid var(--danger)",
    },
  }[variant];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="shrink-0 px-3 text-[12px] font-medium transition-all duration-150"
      style={{
        ...styles,
        borderRadius: "var(--radius)",
        minHeight: 34,
        opacity: disabled ? 0.4 : 1,
        boxShadow: variant === "ghost" ? "none" : "var(--shadow)",
      }}
    >
      {children}
    </button>
  );
}

export function SectionLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 pt-3.5 pb-1.5">
      <span className="label">{children}</span>
      {right}
    </div>
  );
}
