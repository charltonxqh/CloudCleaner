"""In-process counters for the policy/action/verification pipeline.
Good enough for a hackathon demo - no external metrics store needed.
"""

from collections import Counter


class PolicyMetrics:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def record(self, key: str) -> None:
        self.counts[key] += 1

    def summary(self) -> dict[str, int]:
        return dict(self.counts)

    def reset(self) -> None:
        self.counts.clear()


METRICS = PolicyMetrics()
