import json

from cloudcleaner.storage.repository import list_runs, record_run, totals
from cloudcleaner.schemas import (
    ApprovalDecision, CloudResource, Recommendation, RestoreRecipe,
    TeardownPlan, TeardownStep,
)


def _resource():
    return CloudResource(resource_id="i-1", resource_type="ec2", region="us-east-1",
                         state="stopped", estimated_monthly_cost=4.93)


def _plan():
    return TeardownPlan(
        root_resource_id="i-1",
        steps=[TeardownStep(order=1, action="terminate_instance", resource_id="i-1",
                            resource_type="ec2", reason="idle", monthly_saving=4.93,
                            reversible=False)],
        restore=RestoreRecipe(resource_id="i-1", resource_type="ec2"),
    )


def test_run_is_appended_as_one_json_line(tmp_path):
    path = tmp_path / "history.jsonl"
    record_run(_resource(), path=path)
    record_run(_resource(), path=path)

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["resource_id"] == "i-1" for line in lines)


def test_history_is_newest_first(tmp_path):
    path = tmp_path / "history.jsonl"
    record_run(_resource(), path=path)
    record_run(CloudResource(resource_id="i-2", resource_type="ec2", region="us-east-1"), path=path)

    assert [r["resource_id"] for r in list_runs(path=path)] == ["i-2", "i-1"]


def test_dry_run_savings_are_not_counted_as_realised(tmp_path):
    path = tmp_path / "history.jsonl"
    record_run(
        _resource(), recommendation=Recommendation(action="retire", reason="t", confidence=0.9),
        plan=_plan(), approval=ApprovalDecision(decision="approve", approved_resource_ids=["i-1"]),
        action_results=[{"action": "terminate_instance", "resource_id": "i-1", "ok": True,
                         "detail": "dry run", "dry_run": True}],
        verification_passed=True, dry_run=True, path=path,
    )

    t = totals(path=path)
    assert t["realised_monthly"] == 0
    assert t["simulated_monthly"] == 4.93


def test_a_kept_resource_is_still_recorded(tmp_path):
    path = tmp_path / "history.jsonl"
    record_run(_resource(), recommendation=Recommendation(action="keep", reason="busy",
                                                          confidence=0.9), path=path)

    runs = list_runs(path=path)
    assert runs[0]["verdict"] == "keep"
    assert runs[0]["executed"] == 0
    assert totals(path=path)["kept"] == 1


def test_corrupt_line_does_not_break_history(tmp_path):
    path = tmp_path / "history.jsonl"
    record_run(_resource(), path=path)
    with path.open("a") as f:
        f.write("{not json\n")
    record_run(_resource(), path=path)

    assert len(list_runs(path=path)) == 2


def test_missing_history_file_is_empty_not_an_error(tmp_path):
    assert list_runs(path=tmp_path / "nope.jsonl") == []
