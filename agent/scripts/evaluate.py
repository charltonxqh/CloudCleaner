"""Evaluation harness for the ASSESS step — the piece README.md §2.9 / PLAN.md §7
call for and that didn't exist yet: is the agent's *judgment* actually good?

    uv run scripts/evaluate.py

This is deliberately separate from policy/metrics.py (which counts pipeline
*outcomes* - allow/block/rolled back) and from tools/aws/metrics.py (which
pulls raw CloudWatch numbers). This script asks a different question: given
evidence where we already know the right answer, how often does the agent
agree?

Measures, per PLAN.md §7:
  - Recommendation accuracy against a labelled set (10 resources: 5 should be
    kept, 5 should be retired) - reported as accuracy plus a full confusion
    breakdown, because recall on "keep" matters most: a false retire is the
    expensive error, a false keep just costs a few more dollars.
  - Schema validation pass rate - how often the LLM's structured-output call
    parses cleanly on the first try, vs. needing the rules-only fallback.
  - Token cost per case and per run.

Tool-call success rate and teardown-plan correctness are NOT measured here -
those need real AWS actions / the dependency-graph tests respectively, not a
labelled evidence set. See test_teardown_policy.py and test_cost_and_actions.py
for those.

Runs against the real Groq LLM if GROQ_API_KEY is available; otherwise falls
back to the deterministic rules-only path (policy.risk.rules_only_verdict) so
the harness itself - the labelled set, the scoring, the reporting - can be
built and verified without waiting on a key. Same script either way.
"""

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cloudcleaner.config import GROQ_API_KEY
from cloudcleaner.policy.risk import rules_only_verdict
from cloudcleaner.schemas import AWSEvidence, CloudResource, GitHubEvidence, Recommendation


@dataclass
class Case:
    id: str
    resource: CloudResource
    aws: AWSEvidence
    github: GitHubEvidence
    expected: str  # "keep" or "retire" - the ground truth
    note: str = ""


def _resource(id_, **overrides) -> CloudResource:
    defaults = dict(resource_id=id_, resource_type="ec2", region="us-east-1", state="running")
    defaults.update(overrides)
    return CloudResource(**defaults)


LABELLED_CASES: list[Case] = [
    # --- should be RETIRED ---
    Case(
        "eval-retire-01-orphaned-preview",
        _resource("eval-retire-01", name="preview-pr-184", environment="dev", owner="devteam",
                   idle_days=45, estimated_monthly_cost=22.0),
        AWSEvidence(avg_cpu_percent=0.3, network_in_bytes=0, network_out_bytes=0, idle_days=45),
        GitHubEvidence(repo="acme/shopping-app", latest_commit_at="2026-07-20T10:00:00Z",
                        pr_number=184, pr_status="merged", branch="feature/payment",
                        branch_exists=False, scheduled_workflow_exists=False),
        "retire", "textbook orphaned PR-preview environment",
    ),
    Case(
        "eval-retire-02-abandoned-poc",
        _resource("eval-retire-02", environment="dev", owner="alice", idle_days=90),
        AWSEvidence(avg_cpu_percent=1.1, network_in_bytes=512, network_out_bytes=0, idle_days=90),
        GitHubEvidence(repo="acme/ml-poc", latest_commit_at="2026-05-02T09:00:00Z",
                        pr_status="closed", branch_exists=False, scheduled_workflow_exists=False),
        "retire", "no commits in 4 months, branch gone",
    ),
    Case(
        "eval-retire-03-dead-staging",
        _resource("eval-retire-03", environment="staging", owner="bob", idle_days=60),
        AWSEvidence(avg_cpu_percent=0.0, network_in_bytes=0, network_out_bytes=0, idle_days=60),
        GitHubEvidence(repo="acme/checkout-v2", latest_commit_at="2026-06-15T00:00:00Z",
                        pr_status=None, branch_exists=False, scheduled_workflow_exists=False),
        "retire", "zero traffic, no active branch",
    ),
    Case(
        "eval-retire-04-forgotten-demo",
        _resource("eval-retire-04", environment="dev", idle_days=120),  # no owner tag
        AWSEvidence(avg_cpu_percent=2.0, network_in_bytes=0, network_out_bytes=0, idle_days=120),
        GitHubEvidence(repo="acme/investor-demo", latest_commit_at="2026-02-10T00:00:00Z",
                        branch_exists=False, scheduled_workflow_exists=False),
        "retire", "no owner, four months idle, repo effectively dead",
    ),
    Case(
        "eval-retire-05-orphaned-loadgen",
        _resource("eval-retire-05", environment="test", owner="qa-team", idle_days=30),
        AWSEvidence(avg_cpu_percent=0.5, network_in_bytes=0, network_out_bytes=0, idle_days=30),
        GitHubEvidence(repo="acme/loadgen", latest_commit_at="2026-07-01T00:00:00Z",
                        pr_status="merged", branch_exists=False, scheduled_workflow_exists=False),
        "retire", "PR merged two months ago, branch gone",
    ),
    # --- should be KEPT ---
    Case(
        "eval-keep-01-busy-prod",
        _resource("eval-keep-01", environment="prod", owner="platform-team", idle_days=0),
        AWSEvidence(avg_cpu_percent=62.0, network_in_bytes=5_000_000, network_out_bytes=4_000_000, idle_days=0),
        GitHubEvidence(repo="acme/checkout", latest_commit_at="2026-09-04T12:00:00Z",
                        pr_status="open", branch_exists=True, scheduled_workflow_exists=True),
        "keep", "high CPU, high network, active repo",
    ),
    Case(
        "eval-keep-02-active-dev",
        _resource("eval-keep-02", environment="dev", owner="carol", idle_days=1),
        AWSEvidence(avg_cpu_percent=28.0, network_in_bytes=200_000, network_out_bytes=150_000, idle_days=1),
        GitHubEvidence(repo="acme/new-feature", latest_commit_at="2026-09-03T08:00:00Z",
                        pr_status="open", branch_exists=True, scheduled_workflow_exists=True),
        "keep", "moderate load, PR open, commits this week",
    ),
    Case(
        "eval-keep-03-low-cpu-but-active-repo",
        _resource("eval-keep-03", environment="staging", owner="dave", idle_days=0),
        AWSEvidence(avg_cpu_percent=4.0, network_in_bytes=10_000, network_out_bytes=8_000, idle_days=0),
        GitHubEvidence(repo="acme/reporting-service", latest_commit_at="2026-09-05T07:00:00Z",
                        pr_status="open", branch_exists=True, scheduled_workflow_exists=True),
        "keep", "low CPU alone would look idle - GitHub activity is what should save it",
    ),
    Case(
        "eval-keep-04-recently-launched",
        _resource("eval-keep-04", environment="dev", owner="erin", idle_days=1),
        AWSEvidence(avg_cpu_percent=None, network_in_bytes=None, network_out_bytes=None, idle_days=1),
        GitHubEvidence(repo="acme/onboarding-v2", latest_commit_at="2026-09-04T18:00:00Z",
                        pr_status="open", branch_exists=True, scheduled_workflow_exists=True),
        "keep", "too new for CloudWatch data (the §6 trap) - must not be punished for missing metrics",
    ),
    Case(
        "eval-keep-05-scheduled-batch-job",
        _resource("eval-keep-05", environment="prod", owner="data-team", idle_days=0),
        AWSEvidence(avg_cpu_percent=8.0, network_in_bytes=50_000, network_out_bytes=1_000_000, idle_days=0),
        GitHubEvidence(repo="acme/nightly-etl", latest_commit_at="2026-09-01T00:00:00Z",
                        pr_status="open", branch_exists=True, scheduled_workflow_exists=True),
        "keep", "looks idle on average CPU - it's a nightly batch job, still actively maintained",
    ),
]


@dataclass
class CaseResult:
    case: Case
    actual: str
    correct: bool
    schema_ok: bool
    tokens: int
    latency_s: float
    mode: str


def _evaluate_with_llm(case: Case) -> CaseResult:
    from cloudcleaner.graph.nodes.assess import PROMPT, _memory_note, _model

    prior = rules_only_verdict(case.resource, case.aws)
    prompt = PROMPT.format(
        prior=f"{prior.action} - {prior.reason}",
        memory=_memory_note(case.resource.resource_id),
        resource=case.resource.model_dump_json(indent=2),
        aws=case.aws.model_dump_json(indent=2),
        github=case.github.model_dump_json(indent=2),
    )

    start = time.monotonic()
    result = (
        _model()
        .with_structured_output(Recommendation, method="json_schema", include_raw=True)
        .invoke(prompt)
    )
    latency = time.monotonic() - start

    parsed = result.get("parsed")
    schema_ok = parsed is not None and result.get("parsing_error") is None
    action = parsed.action if schema_ok else rules_only_verdict(case.resource, case.aws).action

    raw = result.get("raw")
    usage = getattr(raw, "usage_metadata", None) or {}
    tokens = (usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)

    return CaseResult(case, action, action == case.expected, schema_ok, tokens, latency, mode="llm")


def _evaluate_rules_only(case: Case) -> CaseResult:
    start = time.monotonic()
    rec = rules_only_verdict(case.resource, case.aws)
    latency = time.monotonic() - start
    return CaseResult(case, rec.action, rec.action == case.expected, True, 0, latency, mode="rules-only")


def run() -> list[CaseResult]:
    use_llm = bool(GROQ_API_KEY)
    print(f"Mode: {'real Groq LLM' if use_llm else 'rules-only fallback (no GROQ_API_KEY found)'}\n")

    results = []
    for case in LABELLED_CASES:
        try:
            r = _evaluate_with_llm(case) if use_llm else _evaluate_rules_only(case)
        except Exception as e:
            print(f"  [ERROR] {case.id}: {e} - falling back to rules-only for this case")
            r = _evaluate_rules_only(case)
        mark = "OK" if r.correct else "MISS"
        print(f"  [{mark:4}] {case.id:38} expected={case.expected:7} actual={r.actual:16} ({case.note})")
        results.append(r)
    return results


def report(results: list[CaseResult]) -> None:
    total = len(results)
    correct = sum(r.correct for r in results)

    keep_cases = [r for r in results if r.case.expected == "keep"]
    retire_cases = [r for r in results if r.case.expected == "retire"]
    keep_recall = sum(r.correct for r in keep_cases) / len(keep_cases) if keep_cases else float("nan")
    retire_recall = sum(r.correct for r in retire_cases) / len(retire_cases) if retire_cases else float("nan")

    said_retire = [r for r in results if r.actual == "retire"]
    retire_precision = (
        sum(r.case.expected == "retire" for r in said_retire) / len(said_retire) if said_retire else float("nan")
    )

    schema_pass_rate = sum(r.schema_ok for r in results) / total
    total_tokens = sum(r.tokens for r in results)
    avg_latency = sum(r.latency_s for r in results) / total

    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Overall accuracy:          {correct}/{total} ({correct/total:.0%})")
    print(f"Recall on 'keep'  (*):     {sum(r.correct for r in keep_cases)}/{len(keep_cases)} ({keep_recall:.0%})")
    print(f"Recall on 'retire':        {sum(r.correct for r in retire_cases)}/{len(retire_cases)} ({retire_recall:.0%})")
    print(f"Precision on 'retire':     {retire_precision:.0%}  (of everything flagged retire, how much was right)")
    any_llm = any(r.mode == "llm" for r in results)
    if any_llm:
        print(f"Schema validation pass:    {schema_pass_rate:.0%}")
        print(f"Total tokens (this run):   {total_tokens}")
        print(f"Avg latency per case:      {avg_latency:.2f}s")
    else:
        print("Schema validation / token cost: n/a - no LLM call was made (rules-only mode)")
    print()
    print("(*) PLAN.md is explicit this is the number that matters most - a false")
    print("    'retire' is the expensive, irreversible error; a false 'keep' just")
    print("    costs a few more dollars until the next run catches it.")

    misses = [r for r in results if not r.correct]
    if misses:
        print(f"\n{len(misses)} miss(es):")
        for r in misses:
            print(f"  - {r.case.id}: expected {r.case.expected}, got {r.actual} ({r.case.note})")


if __name__ == "__main__":
    results = run()
    report(results)
