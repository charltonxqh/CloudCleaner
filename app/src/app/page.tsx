"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/cloudcleaner/primitives";
import { Sidebar, ViewHeader, type ViewId } from "@/components/cloudcleaner/shell";
import { EvaluationView } from "@/components/cloudcleaner/views/evaluation";
import { HistoryView } from "@/components/cloudcleaner/views/history";
import { InvestigationView } from "@/components/cloudcleaner/views/investigation";
import { OverviewView } from "@/components/cloudcleaner/views/overview";
import { ResourcesView } from "@/components/cloudcleaner/views/resources";
import {
  api,
  money,
  type ApprovalResult,
  type EvaluationMetrics,
  type EventStats,
  type HistoryTotals,
  type Investigation,
  type Recommendation,
  type Resource,
  type Run,
  type SweepResult,
  type ThreadStatus,
} from "@/lib/api";

const SUBTITLE: Record<ViewId, string> = {
  overview: "What this account spends, and where CloudCleaner can recover it",
  resources: "Inspect resources without leaving the inventory",
  history: "Every recorded agent run, human decision, and execution outcome",
  evaluation: "How accurately, reliably, and efficiently the agent performs",
};

const TITLE: Record<ViewId, string> = {
  overview: "Overview",
  resources: "Resources",
  history: "History",
  evaluation: "Evaluation",
};

const INVESTIGATION_CACHE_TTL_MS = 5 * 60 * 1000;

type CachedInvestigation = {
  data: Investigation;
  cachedAt: number;
  threadStatus?: ThreadStatus | null;
  result?: ApprovalResult | null;
};

export default function Home() {
  const [view, setView] = useState<ViewId>("overview");

  const [resources, setResources] = useState<Resource[]>([]);
  const [totals, setTotals] = useState({ total: 0, wasting: 0 });
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [result, setResult] = useState<ApprovalResult | null>(null);
  const [threadStatus, setThreadStatus] = useState<ThreadStatus | null>(null);

  // Investigations are cached per resource so returning to one is instant.
  // Re-running costs an LLM call, a GitHub call and a row in history, so it is
  // something the user asks for rather than a side effect of navigating.
  const [cache, setCache] = useState<Record<string, CachedInvestigation>>({});
  const [stale, setStale] = useState<Set<string>>(new Set());
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const initialAnalysisStarted = useRef(false);
  const syncedThreads = useRef<Set<string>>(new Set());
  const cacheRef = useRef<Record<string, CachedInvestigation>>({});
  const selectedRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [verdicts, setVerdicts] = useState<Record<string, Recommendation["action"]>>({});
  const [sweep, setSweep] = useState<SweepResult | null>(null);
  const [sweeping, setSweeping] = useState(false);

  const [runs, setRuns] = useState<Run[]>([]);
  const [historyTotals, setHistoryTotals] = useState<HistoryTotals | null>(null);
  const [eventStats, setEventStats] = useState<EventStats | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationMetrics | null>(null);

  const load = useCallback(async (refresh = false) => {
    try {
      const inv = await api.inventory(refresh);
      setResources(inv.resources);

      const wasting = inv.resources
        .filter((r) => inv.wasting.includes(r.resource_id))
        .reduce((s, r) => s + (r.estimated_monthly_cost ?? 0), 0);

      setTotals({ total: inv.total_monthly, wasting });

      if (refresh) {
        setStale(new Set(Object.keys(cache)));
      }

      setError(null);
      return inv.resources;
    } catch {
      setError("Cannot reach the agent on :8123. Start it with `npm run dev`.");
      return [];
    }
  }, [cache]);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.history();
      setRuns(h.runs);
      setHistoryTotals(h.totals);
      setEventStats(h.stats);
    } catch {
      /* history is non-critical */
    }

    try {
      setEvaluation(await api.evaluation());
    } catch {
      /* evaluation is non-critical */
    }
  }, []);

  useEffect(() => {
    cacheRef.current = cache;
  }, [cache]);

  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  useEffect(() => {
    if (initialAnalysisStarted.current) return;
    initialAnalysisStarted.current = true;

    void (async () => {
      const [initialResources] = await Promise.all([load(), loadHistory()]);
      await runInitialAnalysis(initialResources);
    })();
  }, [load, loadHistory]);

  useEffect(() => {
    let cancelled = false;
    let polling = false;

    async function pollPendingThreads() {
      if (polling || cancelled) return;
      polling = true;

      try {
        const entries = Object.entries(cacheRef.current).filter(
          ([, cached]) =>
            cached.data.awaiting_approval &&
            Date.now() - cached.cachedAt < INVESTIGATION_CACHE_TTL_MS
        );

        await Promise.all(
          entries.map(async ([resourceId, cached]) => {
            const threadId = cached.data.thread_id;

            try {
              const status = await api.threadStatus(threadId);

              if (cancelled) return;

              const finished =
                !status.awaiting_approval &&
                (status.phase === "completed" ||
                  status.phase === "error" ||
                  status.decision === "approve" ||
                  status.decision === "reject");

              const approvalResult: ApprovalResult | null = status.decision
                ? {
                    decision: status.decision,
                    reason: status.reason,
                    approved_by: status.approved_by,
                    action_results: status.action_results,
                    verification_passed: status.verification_passed,
                    reasoning: status.reasoning,
                    run_id: status.run_id,
                  }
                : null;

              setCache((current) => {
                const existing = current[resourceId];
                if (!existing || existing.data.thread_id !== threadId) {
                  return current;
                }

                const updatedData = finished
                  ? {
                      ...existing.data,
                      awaiting_approval: false,
                      reasoning: status.reasoning,
                    }
                  : existing.data;

                return {
                  ...current,
                  [resourceId]: {
                    ...existing,
                    data: updatedData,
                    cachedAt: finished ? Date.now() : existing.cachedAt,
                    threadStatus: status,
                    result: approvalResult ?? existing.result ?? null,
                  },
                };
              });

              if (selectedRef.current === resourceId) {
                setThreadStatus(status);

                if (finished) {
                  setInvestigation((current) => {
                    if (!current || current.thread_id !== threadId) {
                      return current;
                    }

                    return {
                      ...current,
                      awaiting_approval: false,
                      reasoning: status.reasoning,
                    };
                  });

                  if (approvalResult) {
                    setResult(approvalResult);
                  }

                  setCachedAt(Date.now());
                }
              }

              if (finished && !syncedThreads.current.has(threadId)) {
                syncedThreads.current.add(threadId);
                await loadHistory();
              }
            } catch {
              if (cancelled) return;
            }
          })
        );
      } finally {
        polling = false;
      }
    }

    void pollPendingThreads();
    const timer = window.setInterval(pollPendingThreads, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadHistory]);

  async function investigate(
    r: Resource,
    opts: { force?: boolean; forcePlan?: boolean } = {}
  ) {
    const id = r.resource_id;

    setSelected(id);
    setResult(null);
    setThreadStatus(null);
    setView("resources");

    const cached = cache[id];
    const cacheIsFresh =
      cached &&
      !stale.has(id) &&
      Date.now() - cached.cachedAt < INVESTIGATION_CACHE_TTL_MS;

    if (cacheIsFresh && !opts.force && !opts.forcePlan) {
      setInvestigation(cached.data);
      setThreadStatus(cached.threadStatus ?? null);
      setResult(cached.result ?? null);
      setCachedAt(cached.cachedAt);
      return;
    }

    setCachedAt(null);
    setBusy(id);
    setInvestigation(null);

    try {
      const monitored = !opts.force && !opts.forcePlan
        ? await api.monitoredInvestigation(id)
        : null;
      const data =
        monitored ?? await api.investigate(id, opts.forcePlan ?? false);

      setInvestigation(data);

      setCache((c) => ({
        ...c,
        [id]: {
          data,
          cachedAt: Date.now(),
          threadStatus: null,
          result: null,
        },
      }));

      setStale((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });

      if (data.recommendation) {
        setVerdicts((v) => ({
          ...v,
          [id]: data.recommendation!.action,
        }));
      }

      if (!data.awaiting_approval) {
        loadHistory();
      }
    } catch {
      setError(`Investigation failed for ${id}.`);
    } finally {
      setBusy(null);
    }
  }

  async function runInitialAnalysis(initialResources: Resource[]) {
    if (!initialResources.length) return;

    setSweeping(true);

    try {
      const analysed = await Promise.all(
        initialResources.map(async (resource) => {
          const monitored = await api.monitoredInvestigation(resource.resource_id);
          const data =
            monitored ?? await api.investigate(resource.resource_id, false);

          return { resource, data };
        })
      );

      const now = Date.now();

      setCache(
        Object.fromEntries(
          analysed.map(({ resource, data }) => [
            resource.resource_id,
            {
              data,
              cachedAt: now,
              threadStatus: null,
              result: null,
            },
          ])
        )
      );
      setStale(new Set());
      setCachedAt(null);

      setVerdicts(
        Object.fromEntries(
          analysed
            .filter(({ data }) => data.recommendation)
            .map(({ resource, data }) => [
              resource.resource_id,
              data.recommendation!.action,
            ])
        ) as Record<string, Recommendation["action"]>
      );

      const results = analysed.map(({ resource, data }) => {
        const recommendation = data.recommendation;
        const plan = data.plan;

        const monthlySaving =
          recommendation?.action === "retire" && plan?.steps?.length && !plan.blocked.length
            ? plan.steps.reduce((sum, step) => sum + step.monthly_saving, 0)
            : recommendation?.estimated_monthly_saving ?? 0;

        return {
          resource_id: resource.resource_id,
          action: recommendation?.action ?? null,
          severity: recommendation?.severity ?? null,
          confidence: recommendation?.confidence ?? null,
          reason: recommendation?.reason ?? null,
          steps: plan?.steps.length ?? 0,
          blocked: plan?.blocked ?? [],
          monthly_saving: Math.round(monthlySaving * 100) / 100,
        };
      });

      const recoverableMonthly =
        Math.round(
          results.reduce((sum, row) => sum + row.monthly_saving, 0) * 100
        ) / 100;

      setSweep({
        results,
        recoverable_monthly: recoverableMonthly,
        recoverable_yearly: Math.round(recoverableMonthly * 12 * 100) / 100,
        reasoning: analysed.flatMap(({ data }) => data.reasoning),
      });

      setError(null);
      loadHistory();
    } catch {
      setError("Initial analysis failed.");
    } finally {
      setSweeping(false);
    }
  }

  async function runSweep() {
    setSweeping(true);

    try {
      const s = await api.sweep();

      setSweep(s);
      setCache({});
      setStale(new Set());
      setCachedAt(null);

      setVerdicts(
        Object.fromEntries(
          s.results
            .filter((r) => r.action)
            .map((r) => [r.resource_id, r.action!])
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

  function closeInvestigation() {
    setSelected(null);
    setInvestigation(null);
    setResult(null);
    setThreadStatus(null);
    setCachedAt(null);
  }

  const actions = (
    <>
      <span
        className="num mr-1 hidden text-[13px] sm:inline"
        style={{ color: "var(--fg-faint)" }}
      >
        {money(totals.wasting)} wasted of {money(totals.total)}
      </span>

      <Button
        onClick={() => load(true)}
        title="Re-read the account inventory"
      >
        Refresh
      </Button>

      <Button
        variant="primary"
        onClick={runSweep}
        disabled={sweeping}
      >
        {sweeping ? "Analysing…" : "Analyse all"}
      </Button>
    </>
  );

  return (
    <main
      className="flex h-dvh flex-col lg:flex-row"
      style={{ background: "var(--bg)" }}
    >
      <Sidebar
        view={view}
        onNavigate={setView}
        badges={{
          resources: resources.length,
          history: runs.length,
        }}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ViewHeader
          view={view}
          title={TITLE[view]}
          subtitle={SUBTITLE[view]}
          actions={actions}
        />

        {error && (
          <div
            role="alert"
            className="shrink-0 px-6 py-2.5 text-[13px]"
            style={{
              background: "var(--danger-dim)",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-hidden">
          {view === "overview" && (
            <div className="h-full overflow-auto">
              <OverviewView
                resources={resources}
                totals={totals}
                sweep={sweep}
                verdicts={verdicts}
                onOpen={(r) => investigate(r)}
              />
            </div>
          )}

          {view === "resources" && (
            <div className="flex h-full min-h-0 flex-col lg:flex-row">
              <div
                className="flex min-h-0 min-w-0 flex-1 flex-col transition-[width] duration-200"
                style={{
                  borderRight: selected
                    ? "1px solid var(--border-strong)"
                    : "none",
                }}
              >
                <ResourcesView
                  resources={resources}
                  selected={selected}
                  busy={busy}
                  verdicts={verdicts}
                  compact={selected !== null}
                  onSelect={(r) => investigate(r)}
                />
              </div>

              {selected && (
                <aside
                  className="flex min-h-0 min-w-0 flex-col lg:w-[46%] lg:max-w-[760px] lg:min-w-[480px]"
                  style={{ background: "var(--bg)" }}
                >
                  <InvestigationView
                    data={investigation}
                    result={result}
                    threadStatus={threadStatus}
                    busy={busy !== null}
                    stale={stale.has(selected)}
                    cachedAt={cachedAt}
                    onClose={closeInvestigation}
                    onReinvestigate={() => {
                      const r = resources.find(
                        (x) => x.resource_id === selected
                      );

                      if (r) {
                        investigate(r, { force: true });
                      }
                    }}
                    onForcePlan={() => {
                      const r = resources.find(
                        (x) => x.resource_id === selected
                      );

                      if (r) {
                        investigate(r, { forcePlan: true });
                      }
                    }}
                  />
                </aside>
              )}
            </div>
          )}

          {view === "history" && (
            <div className="h-full overflow-hidden">
              <HistoryView
                runs={runs}
                totals={historyTotals}
              />
            </div>
          )}

          {view === "evaluation" && (
            <EvaluationView
              evaluation={evaluation}
              stats={eventStats}
            />
          )}
        </div>
      </div>
    </main>
  );
}