"use client";

import { useCallback, useEffect, useState } from "react";

import { History } from "@/components/cloudcleaner/history";
import { InvestigationPanel } from "@/components/cloudcleaner/investigation";
import { Panel, Stat } from "@/components/cloudcleaner/primitives";
import { ReasoningTrail } from "@/components/cloudcleaner/reasoning-trail";
import { ResourceTable } from "@/components/cloudcleaner/resource-table";
import {
  api, money,
  type ApprovalResult, type HistoryTotals, type Investigation,
  type Recommendation, type Resource, type Run,
} from "@/lib/api";

export default function Home() {
  const [resources, setResources] = useState<Resource[]>([]);
  const [totals, setTotals] = useState({ total: 0, wasting: 0 });
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [result, setResult] = useState<ApprovalResult | null>(null);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, Recommendation["action"]>>({});
  const [recoverable, setRecoverable] = useState<{ monthly: number; yearly: number } | null>(null);
  const [sweeping, setSweeping] = useState(false);
  const [sweepEvents, setSweepEvents] = useState<Investigation["reasoning"]>([]);
  const [tab, setTab] = useState<"trail" | "history">("trail");
  const [runs, setRuns] = useState<Run[]>([]);
  const [historyTotals, setHistoryTotals] = useState<HistoryTotals | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      const inv = await api.inventory(refresh);
      setResources(inv.resources);
      const wasting = inv.resources
        .filter((r) => inv.wasting.includes(r.resource_id))
        .reduce((s, r) => s + (r.estimated_monthly_cost ?? 0), 0);
      setTotals({ total: inv.total_monthly, wasting });
      setError(null);
    } catch {
      setError("Cannot reach the agent on :8123. Start it with `npm run dev`.");
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.history();
      setRuns(h.runs);
      setHistoryTotals(h.totals);
    } catch {
      /* history is non-critical */
    }
  }, []);

  useEffect(() => { load(); loadHistory(); }, [load, loadHistory]);

  async function investigate(r: Resource, forcePlan = false) {
    setSelected(r.resource_id);
    setBusy(r.resource_id);
    setInvestigation(null);
    setResult(null);
    try {
      const data = await api.investigate(r.resource_id, forcePlan);
      setInvestigation(data);
      if (data.recommendation) {
        setVerdicts((v) => ({ ...v, [r.resource_id]: data.recommendation!.action }));
      }
      if (!data.awaiting_approval) loadHistory();
    } catch {
      setError(`Investigation failed for ${r.resource_id}.`);
    } finally {
      setBusy(null);
    }
  }

  async function sweep() {
    setSweeping(true);
    setInvestigation(null);
    setResult(null);
    setSelected(null);
    try {
      const s = await api.sweep();
      setVerdicts(
        Object.fromEntries(
          s.results.filter((r) => r.action).map((r) => [r.resource_id, r.action!])
        ) as Record<string, Recommendation["action"]>
      );
      setRecoverable({ monthly: s.recoverable_monthly, yearly: s.recoverable_yearly });
      setSweepEvents(s.reasoning);
      setError(null);
      loadHistory();
    } catch {
      setError("Sweep failed.");
    } finally {
      setSweeping(false);
    }
  }

  async function approve(command: string) {
    if (!investigation) return;
    setApproving(true);
    try {
      setResult(await api.approve(investigation.thread_id, command));
      await Promise.all([load(true), loadHistory()]);
    } catch {
      setError("Approval failed.");
    } finally {
      setApproving(false);
    }
  }

  const events = result?.reasoning ?? investigation?.reasoning ?? sweepEvents;

  return (
    <main className="flex h-dvh flex-col" style={{ background: "var(--bg)" }}>
      <header
        className="flex shrink-0 flex-wrap items-stretch"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}
      >
        <div className="flex items-center px-4 py-3" style={{ borderRight: "1px solid var(--border)" }}>
          <div>
            <h1 className="text-[15px] font-semibold tracking-tight">CloudCleaner</h1>
            <p className="text-[11px]" style={{ color: "var(--fg-faint)" }}>
              AWS lifecycle agent · us-east-1
            </p>
          </div>
        </div>
        <Stat label="Resources" value={resources.length} />
        <Stat label="Total spend" value={money(totals.total)} hint="per month" />
        <Stat
          label="Wasted"
          value={money(totals.wasting)}
          tone="var(--danger)"
          hint="not running, still billing"
        />
        {recoverable && (
          <Stat
            label="Recoverable"
            value={money(recoverable.monthly)}
            tone="var(--ok)"
            hint={`${money(recoverable.yearly)} per year`}
          />
        )}
        <div className="flex flex-1 items-center justify-end gap-2 px-4">
          <button
            onClick={() => load(true)}
            className="px-3 py-2 text-[12px] transition-colors duration-150"
            style={{
              color: "var(--fg-muted)", border: "1px solid var(--border-strong)",
              borderRadius: 2, minHeight: 44,
            }}
          >
            Rescan
          </button>
          <button
            onClick={sweep}
            disabled={sweeping}
            className="px-3 py-2 text-[12px] font-semibold transition-colors duration-150"
            style={{
              background: "var(--primary)", color: "var(--on-primary)",
              border: "1px solid var(--primary)", borderRadius: 2, minHeight: 44,
            }}
          >
            {sweeping ? "Sweeping…" : "Sweep account"}
          </button>
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className="shrink-0 px-4 py-2 text-[12px]"
          style={{ background: "var(--danger-dim)", color: "var(--danger)" }}
        >
          {error}
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-px lg:grid-cols-[minmax(320px,1fr)_minmax(420px,1.1fr)]">
        <Panel title="Inventory" className="min-h-[240px]">
          <ResourceTable
            resources={resources}
            selected={selected}
            busy={busy}
            verdicts={verdicts}
            onSelect={(r) => investigate(r)}
          />
        </Panel>

        <Panel title="Investigation">
          <InvestigationPanel
            data={investigation}
            result={result}
            approving={approving}
            onApprove={approve}
            onForcePlan={() => {
              const r = resources.find((x) => x.resource_id === selected);
              if (r) investigate(r, true);
            }}
          />
        </Panel>
      </div>

      <Panel
        className="h-[188px] shrink-0"
        title={tab === "trail" ? "Reasoning trail" : "Run history"}
        right={
          <div role="tablist" aria-label="Bottom panel" className="flex gap-1">
            {(["trail", "history"] as const).map((id) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className="px-2 py-1 text-[11px] transition-colors duration-150"
                style={{
                  color: tab === id ? "var(--fg)" : "var(--fg-faint)",
                  borderBottom: `1px solid ${tab === id ? "var(--primary)" : "transparent"}`,
                }}
              >
                {id === "trail" ? "Trail" : `History (${runs.length})`}
              </button>
            ))}
          </div>
        }
      >
        {tab === "trail" ? (
          <ReasoningTrail events={events} />
        ) : (
          <History runs={runs} totals={historyTotals} />
        )}
      </Panel>
    </main>
  );
}
