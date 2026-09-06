"""Command line entry point.

    cloudcleaner scan                     what the account holds, and what it costs
    cloudcleaner sweep                    investigate everything, approve nothing
    cloudcleaner investigate <id>         one resource, with an approval prompt
    cloudcleaner history                  past runs and realised savings
    cloudcleaner doctor                   check credentials and configuration
    cloudcleaner serve                    the HTTP API (needs the [server] extra)

Every command is read-only unless you approve something, and even then
CLOUDCLEANER_DRY_RUN defaults to true.
"""

import argparse
import sys
import uuid


def _fmt(amount) -> str:
    return f"${amount or 0:,.2f}"


def cmd_scan(args) -> int:
    from cloudcleaner.config import DRY_RUN, PROVIDER
    from cloudcleaner.graph.nodes.detect import detect_node

    scan = detect_node({})
    rows = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    if not rows:
        print("Nothing found. Either the account is empty or the credentials cannot see it.")
        return 0

    total = sum(r.estimated_monthly_cost or 0 for r in rows)
    wasted = sum(r.estimated_monthly_cost or 0 for r in rows if r.billing_while_stopped)

    print(f"provider={PROVIDER}  dry_run={DRY_RUN}\n")
    print(f"{'RESOURCE':<26} {'TYPE':<6} {'STATE':<14} {'$/MO':>8}")
    for r in sorted(rows, key=lambda r: -(r.estimated_monthly_cost or 0)):
        flag = " *" if r.billing_while_stopped else ""
        print(f"{r.resource_id:<26} {r.resource_type:<6} {(r.state or '-'):<14} "
              f"{_fmt(r.estimated_monthly_cost):>8}{flag}")

    print(f"\n{len(rows)} resources · {_fmt(total)}/mo total · {_fmt(wasted)}/mo not running "
          f"but still billing (*)")
    return 0


def cmd_sweep(args) -> int:
    """Assess every candidate. Approves nothing, so it is safe to run anywhere."""
    from langgraph.types import Command

    from cloudcleaner.config import DRY_RUN, PROVIDER
    from cloudcleaner.graph.graph import graph
    from cloudcleaner.graph.nodes.detect import detect_node

    scan = detect_node({})
    candidates = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    if not candidates:
        print("Nothing to investigate.")
        return 0

    print(f"provider={PROVIDER}  dry_run={DRY_RUN}\n")
    recoverable = 0.0

    for resource in candidates:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke({**scan, "resource": resource}, config)
        if result.get("__interrupt__"):
            result = graph.invoke(Command(resume=""), config)

        rec, plan = result.get("recommendation"), result.get("plan")
        saving = sum(s.monthly_saving for s in plan.steps) if plan and plan.steps else 0.0
        recoverable += saving

        print(f"{resource.resource_id}  {resource.resource_type}/{resource.state}  "
              f"{_fmt(resource.estimated_monthly_cost)}/mo")
        if rec:
            print(f"  -> {rec.action} ({rec.confidence:.0%}, {rec.severity}) {rec.reason}")
        if plan and plan.blocked:
            print(f"  -> blocked: {'; '.join(plan.blocked)}")
        for s in (plan.steps if plan else []):
            mark = "!" if not s.reversible else " "
            print(f"   {mark} {s.order}. {s.action:<21} {s.resource_id:<22} "
                  f"{_fmt(s.monthly_saving):>8}  {s.reason}")
        print()

    print(f"Recoverable: {_fmt(recoverable)}/month  ({_fmt(recoverable * 12)}/year)")
    return 0


def cmd_investigate(args) -> int:
    from langgraph.types import Command

    from cloudcleaner.config import DRY_RUN, PROVIDER
    from cloudcleaner.graph.graph import graph
    from cloudcleaner.graph.nodes.detect import detect_node
    from cloudcleaner.graph.render import render_plan

    scan = detect_node({})
    pool = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    resource = next((r for r in pool if r.resource_id == args.resource_id), None)
    if resource is None:
        print(f"No resource {args.resource_id} in this account.", file=sys.stderr)
        print("Run `cloudcleaner scan` to see what is visible.", file=sys.stderr)
        return 1

    print(f"provider={PROVIDER}  dry_run={DRY_RUN}\n")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke({**scan, "resource": resource, "force_plan": args.force_plan}, config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if not sys.stdin.isatty():
            print(render_plan(payload).rstrip() + "  [not a terminal, skipped]")
            result = graph.invoke(Command(resume=""), config)
            continue
        result = graph.invoke(Command(resume=input(render_plan(payload))), config)

    rec = result.get("recommendation")
    if rec:
        print(f"\nverdict  {rec.action} ({rec.confidence:.0%}, {rec.severity})")
        print(f"         {rec.reason}")
    for a in result.get("action_results") or []:
        print(f"action   {a['action']} {a['resource_id']} -> {a['detail']}")
    return 0


def cmd_history(args) -> int:
    from cloudcleaner.storage.repository import list_runs, totals

    runs = list_runs(args.limit)
    if not runs:
        print("No runs recorded yet.")
        return 0

    t = totals()
    print(f"{t['runs']} runs · {t['approved']} approved · {t['kept']} kept")
    print(f"realised {_fmt(t['realised_monthly'])}/mo   "
          f"simulated {_fmt(t['simulated_monthly'])}/mo (dry run, not saved)\n")

    for r in runs:
        outcome = (f"blocked: {r['blocked'][0]}" if r["blocked"]
                   else f"{r['executed']}/{r['planned_steps']} steps" if r["executed"]
                   else "no action")
        print(f"{r['at'][:16]}  {r['resource_id']:<26} {str(r['verdict']):<10} {outcome}")
    return 0


def cmd_doctor(args) -> int:
    """Check the things that actually stop this working."""
    from cloudcleaner import config

    ok = True
    print(f"config file   {config.ENV_FILE or 'none found'}")
    print(f"data dir      {config.DATA_DIR}")
    print(f"provider      {config.PROVIDER}")
    print(f"dry run       {config.DRY_RUN}")
    print(f"model         {config.GROQ_MODEL if config.AI_ENABLED else 'disabled, rules only'}")
    print()

    def check(label, passed, hint=""):
        nonlocal ok
        ok = ok and passed
        print(f"[{'ok ' if passed else 'FAIL'}] {label}" + (f"  — {hint}" if not passed else ""))

    check("Groq key", bool(config.GROQ_API_KEY) or not config.AI_ENABLED,
          "set GROQ_API_KEY, or CLOUDCLEANER_AI_ENABLED=false for rules only")

    if config.PROVIDER == "fixture":
        print("[ok ] AWS not needed — running against the built-in demo account")
    else:
        try:
            from cloudcleaner.tools.aws.client import get_sts_client
            who = get_sts_client().get_caller_identity()
            check(f"AWS account {who['Account']}", True)
        except Exception as e:
            check("AWS credentials", False, str(e)[:80])

    check("GitHub token", bool(config.GITHUB_TOKEN),
          "optional — without it, code activity is skipped, not fatal")

    return 0 if ok else 1


def cmd_serve(args) -> int:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("The HTTP API needs the server extra:\n\n"
              "    pip install 'cloudcleaner[server]'\n", file=sys.stderr)
        return 1

    import uvicorn
    uvicorn.run("cloudcleaner.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cloudcleaner",
        description="Find AWS resources nobody is using, prove it, and plan a safe teardown.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="list resources and what they cost").set_defaults(fn=cmd_scan)
    sub.add_parser("sweep", help="investigate every candidate").set_defaults(fn=cmd_sweep)

    inv = sub.add_parser("investigate", help="investigate one resource")
    inv.add_argument("resource_id")
    inv.add_argument("--force-plan", action="store_true",
                     help="plan a teardown even when the verdict is keep")
    inv.set_defaults(fn=cmd_investigate)

    hist = sub.add_parser("history", help="past runs and realised savings")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(fn=cmd_history)

    sub.add_parser("doctor", help="check credentials and configuration").set_defaults(fn=cmd_doctor)

    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8123)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(fn=cmd_serve)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
