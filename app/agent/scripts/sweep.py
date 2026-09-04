"""Investigate every waste candidate in the account, not just the worst one."""

import sys
import uuid

from langgraph.types import Command

from cloudcleaner.config import DRY_RUN, PROVIDER
from cloudcleaner.graph.graph import graph
from cloudcleaner.graph.nodes.detect import detect_node
from cloudcleaner.graph.render import render_plan


def _run(state):
    """Drive one resource through the graph, answering any approval interrupt."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    result = graph.invoke(state, config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value

        if not sys.stdin.isatty():
            print(render_plan(payload).rstrip() + " [no terminal, skipped]")
            result = graph.invoke(Command(resume=""), config)
            continue

        answer = input(render_plan(payload))
        result = graph.invoke(Command(resume=answer), config)

    return result


def main():
    print(f"provider={PROVIDER}  dry_run={DRY_RUN}\n")

    scan = detect_node({})
    candidates = (scan.get("inventory") or []) + (scan.get("orphans") or [])
    if not candidates:
        print("Nothing to investigate.")
        return

    print(f"{len(candidates)} resources in scope\n" + "=" * 78)

    total = 0.0
    for resource in candidates:
        result = _run({**scan, "resource": resource})
        rec, plan = result.get("recommendation"), result.get("plan")

        print(f"\n{resource.resource_id}  {resource.name or '-'}  "
              f"({resource.resource_type}/{resource.state})  "
              f"${resource.estimated_monthly_cost or 0}/mo")
        print(f"  -> {rec.action} ({rec.confidence:.0%}, {rec.severity}) {rec.reason}")

        if plan and plan.blocked:
            print(f"  -> BLOCKED by policy: {'; '.join(plan.blocked)}")
        elif plan and plan.steps:
            total += plan.total_monthly_saving
            for s in plan.steps:
                mark = "!" if not s.reversible else " "
                print(f"     {mark} {s.order}. {s.action:<21} {s.resource_id:<20} "
                      f"${s.monthly_saving:>6.2f}  {s.reason}")

        for a in result.get("action_results") or []:
            print(f"     -> {a['action']} {a['resource_id']}: {a['detail']}")

    print("\n" + "=" * 78)
    print(f"Recoverable: ${total:.2f}/month  (${total * 12:.2f}/year)")


if __name__ == "__main__":
    main()
