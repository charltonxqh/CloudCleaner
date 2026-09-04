import os
import sys

from cloudcleaner.config import DRY_RUN
from cloudcleaner.graph.graph import graph


def main():
    if DRY_RUN:
        print("DRY RUN — no AWS resources will be changed. Set CLOUDCLEANER_DRY_RUN=false to act.\n")

    result = graph.invoke({})

    if result.get("done_reason"):
        print(f"Finished: {result['done_reason']}")
        return

    r = result["resource"]
    print(f"\nResource        {r.resource_id}  {r.name or '-'}  ({r.state})")
    print(f"Cost            ${r.estimated_monthly_cost}/mo"
          f"{'  <- still billing while stopped' if r.billing_while_stopped else ''}")

    aws = result["aws_evidence"]
    print(f"Usage           cpu avg {aws.avg_cpu_percent}%  peak {aws.max_cpu_percent}%  "
          f"idle {aws.idle_days}d")

    rec = result["recommendation"]
    print(f"Recommendation  {rec.action}  ({rec.confidence:.0%}, {rec.severity})")
    print(f"                {rec.reason}")

    if result.get("approval"):
        print(f"Approval        {result['approval'].decision}")
    for a in result.get("action_results") or []:
        print(f"Action          {a['action']} -> {a['detail']}")
    if "verification_passed" in result:
        print(f"Verified        {result['verification_passed']}")

    print(f"\nReasoning trail: {len(_events())} events -> output/reasoning.jsonl")


def _events():
    from cloudcleaner.evidence.collector import log
    return log.events


if __name__ == "__main__":
    sys.exit(main())
