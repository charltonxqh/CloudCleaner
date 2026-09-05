"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/cloudcleaner/primitives";
import { Sidebar, ViewHeader, type ViewId } from "@/components/cloudcleaner/shell";
import { ActivityView } from "@/components/cloudcleaner/views/activity";
import { HistoryView } from "@/components/cloudcleaner/views/history";
import { InvestigationView } from "@/components/cloudcleaner/views/investigation";
import { OverviewView } from "@/components/cloudcleaner/views/overview";
import { ResourcesView } from "@/components/cloudcleaner/views/resources";
import {
  api, money,
  type ApprovalResult, type HistoryTotals, type Investigation,
  type EventStats, type ReasoningEvent, type Recommendation,
  type Resource, type Run, type SweepResult,
} from "@/lib/api";

const SUBTITLE: Record<ViewId, string> = {
  overview: "What this account spends, and how much of it buys nothing",
  resources: "Everything the agent can see, and what each costs",
  investigation: "Evidence, verdict, and the teardown a retirement would take",
  history: "Every run the agent has recorded, and what it actually saved",
  activity: "The agent's reasoning, one event per decision",
};

export default function Home() {
  const [view, setView] = useState<ViewId>("overview");

  const [resources, setResources] = useState<Resource[]>([]);
  const [totals, setTotals] = useState({ total: 0, wasting: 0 });
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [result, setResult] = useState<ApprovalResult | null>(null);
  // Investigations are cached per resource so returning to one is instant.
  // Re-running costs an LLM call, a GitHub call and a row in history, so it is
  // something the user asks for rather than a side effect of navigating.
  const [cache, setCache] = useState<Record<string, Investigation>>({});
  const [stale, setStale] = useState<Set<string>>(new Set());
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [verdicts, setVerdicts] = useState<Record<string, Recommendation["action"]>>({});
  const [sweep, setSweep] = useState<SweepResult | null>(null);
  const [sweeping, setSweeping] = useState(false);

  const [runs, setRuns] = useState<Run[]>([]);
  const [historyTotals, setHistoryTotals] = useState<HistoryTotals | null>(null);
  const [eventStats, setEventStats] = useState<EventStats | null>(null);
  const [events, setEvents] = useState<ReasoningEvent[]>([]);

  const load = useCallback(async (refresh = false) => {
    try {
      const inv = await api.inventory(refresh);
      setResources(inv.resources);
      const wasting = inv.resources
        .filter((r) => inv.wasting.includes(r.resource_id))
        .reduce((s, r) => s + (r.estimated_monthly_cost ?? 0), 0);
      setTotals({ total: inv.total_monthly, wasting });
      if (refresh) setStale(new Set(Object.keys(cache)));
      setError(null);
    } catch {
      setError("Cannot reach the agent on :8123. Start it with `npm run dev`.");
    }
  }, [cache]);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.history();
      setRuns(h.runs);
      setHistoryTotals(h.totals);
      setEventStats(h.stats);
    } catch { /* history is non-critical */ }
  }, []);

  useEffect(() => { load(); loadHistory(); }, [load, loadHistory]);

  async function investigate(r: Resource, opts: { force?: boolean; forcePlan?: boolean } = {}) {
    const id = r.resource_id;
    setSelected(id);
    setResult(null);
    setView("investigation");

    const cached = cache[id];
    if (cached && !opts.force && !opts.forcePlan) {
      setInvestigation(cached);
      setEvents(cached.reasoning);
      return;
    }

    setBusy(id);
    setInvestigation(null);
    try {
      const data = await api.investigate(id, opts.forcePlan ?? false);
      setInvestigation(data);
      setEvents(data.reasoning);
      setCache((c) => ({ ...c, [id]: data }));
      setStale((s) => { const n = new Set(s); n.delete(id); return n; });
      if (data.recommendation) {
        setVerdicts((v) => ({ ...v, [id]: data.recommendation!.action }));
      }
      if (!data.awaiting_approval) loadHistory();
    } catch {
      setError(`Investigation failed for ${id}.`);
    } finally {
      setBusy(null);
    }
  }

  async function runSweep() {
    setSweeping(true);
    try {
      const s = await api.sweep();
      setSweep(s);
      setEvents(s.reasoning);
      setCache({});
      setStale(new Set());
      setVerdicts(
        Object.fromEntries(
          s.results.filter((r) => r.action).map((r) => [r.resource_id, r.action!])
        ) as Record<string, Recommendation["action"]>
      );
      setError(null);
      loadHistory();
    } catch {
      setError("Analysis failed.");
    } finally {
      setSweeping(false);
    }
  }

  async function approve(command: string) {
    if (!investigation) return;
    setApproving(true);
    try {
      const r = await api.approve(investigation.thread_id, command);
      setResult(r);
      setEvents(r.reasoning);
      // The resource changed underneath us, so the cached view no longer holds.
      setCache((c) => {
        const next = { ...c };
        delete next[investigation.resource.resource_id];
        return next;
      });
      await Promise.all([load(true), loadHistory()]);
    } catch {
      setError("Approval failed.");
    } finally {
      setApproving(false);
    }
  }

  const actions = (
    <>
      <span className="num mr-1 hidden text-[12px] sm:inline" style={{ color: "var(--fg-faint)" }}>
        {money(totals.wasting)} wasted of {money(totals.total)}
      </span>
      <Button onClick={() => load(true)} title="Re-read the account inventory">Refresh</Button>
      <Button variant="primary" onClick={runSweep} disabled={sweeping}>
        {sweeping ? "Analysing…" : "Analyse all"}
      </Button>
    </>
  );

  return (
    <main className="flex h-dvh flex-col lg:flex-row" style={{ background: "var(--bg)" }}>
      <Sidebar
        view={view}
        onNavigate={setView}
        badges={{ resources: resources.length, history: runs.length, activity: events.length }}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ViewHeader
          title={
            view === "investigation" && investigation
              ? investigation.resource.name || investigation.resource.resource_id
              : view[0].toUpperCase() + view.slice(1)
          }
          subtitle={SUBTITLE[view]}
          actions={actions}
        />

        {error && (
          <div
            role="alert"
            className="shrink-0 px-5 py-2 text-[12px]"
            style={{ background: "var(--danger-dim)", color: "var(--danger)" }}
          >
            {error}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto">
          {view === "overview" && (
            <OverviewView
              resources={resources}
              totals={totals}
              sweep={sweep}
              verdicts={verdicts}
              onOpen={(r) => investigate(r)}
            />
          )}

          {view === "resources" && (
            <ResourcesView
              resources={resources}
              selected={selected}
              busy={busy}
              verdicts={verdicts}
              onSelect={(r) => investigate(r)}
            />
          )}

          {view === "investigation" && (
            <InvestigationView
              data={investigation}
              result={result}
              busy={busy !== null}
              approving={approving}
              onApprove={approve}
              onBack={() => setView("resources")}
              stale={selected ? stale.has(selected) : false}
              onReinvestigate={() => {
                const r = resources.find((x) => x.resource_id === selected);
                if (r) investigate(r, { force: true });
              }}
              onForcePlan={() => {
                const r = resources.find((x) => x.resource_id === selected);
                if (r) investigate(r, { forcePlan: true });
              }}
            />
          )}

          {view === "history" && (
            <HistoryView runs={runs} totals={historyTotals} stats={eventStats} />
          )}
          {view === "activity" && <ActivityView events={events} />}
        </div>
      </div>
    </main>
  );
}
