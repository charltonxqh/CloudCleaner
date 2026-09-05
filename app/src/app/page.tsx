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
    if (initialAnalysisStarted.current) return;
    initialAnalysisStarted.current = true;

    void (async () => {
      await Promise.all([load(), loadHistory()]);
      await runSweep();
    })();
  }, [load, loadHistory]);

  useEffect(() => {
    const threadId = investigation?.thread_id;

    if (!threadId || !investigation.awaiting_approval) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const status = await api.threadStatus(threadId!);

        if (cancelled) return;

        setThreadStatus(status);

        const finished =
          !status.awaiting_approval &&
          (status.phase === "completed" ||
            status.phase === "error" ||
            status.decision === "approve" ||
            status.decision === "reject");

        if (finished) {
          setInvestigation((current) => {
            if (!current || current.thread_id !== threadId) {
              return current;
            }

            return {
              ...current,
              awaiting_approval: false,
            };
          });

          if (status.decision) {
            setResult({
              decision: status.decision,
              reason: status.reason,
              approved_by: status.approved_by,
              action_results: status.action_results,
              verification_passed: status.verification_passed,
              reasoning: status.reasoning,
              run_id: status.run_id,
            });
          }

          setCache((current) => {
            if (!selected) return current;
            const next = { ...current };
            delete next[selected];
            return next;
          });

          setCachedAt(null);

          if (!syncedThreads.current.has(threadId!)) {
            syncedThreads.current.add(threadId!);
            await Promise.all([load(true), loadHistory()]);
          }

          return;
        }
      } catch {
        if (cancelled) return;
      }

      if (!cancelled) {
        timer = window.setTimeout(poll, 2000);
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [
    investigation?.thread_id,
    investigation?.awaiting_approval,
    load,
    loadHistory,
    selected,
  ]);

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
      setCachedAt(cached.cachedAt);
      return;
    }

    setCachedAt(null);
    setBusy(id);
    setInvestigation(null);

    try {
      const data = await api.investigate(id, opts.forcePlan ?? false);

      setInvestigation(data);

      setCache((c) => ({
        ...c,
        [id]: {
          data,
          cachedAt: Date.now(),
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