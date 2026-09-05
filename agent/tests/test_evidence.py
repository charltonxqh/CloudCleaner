import json

from cloudcleaner.storage.repository import (
    list_runs, recall, record_run, restore_recipe, runs_for, totals,
)
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


def test_each_run_is_one_row(tmp_path):
    path = tmp_path / "cc.db"
    record_run(_resource(), path=path)
    record_run(_resource(), path=path)

    runs = list_runs(path=path)
    assert len(runs) == 2
    assert all(r["resource_id"] == "i-1" for r in runs)
    assert len({r["run_id"] for r in runs}) == 2


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


def test_json_columns_come_back_as_lists(tmp_path):
    path = tmp_path / "cc.db"
    record_run(
        _resource(),
        recommendation=Recommendation(action="retire", reason="t", confidence=0.9),
        plan=_plan(),
        approval=ApprovalDecision(decision="approve", approved_resource_ids=["i-1"]),
        action_results=[{"action": "terminate_instance", "resource_id": "i-1",
                         "ok": True, "detail": "dry run", "dry_run": True}],
        path=path,
    )
    run = list_runs(path=path)[0]
    assert run["blocked"] == []
    assert run["actions"][0]["action"] == "terminate_instance"


def test_missing_database_is_empty_not_an_error(tmp_path):
    assert list_runs(path=tmp_path / "nope.db") == []
    assert totals(path=tmp_path / "nope.db")["runs"] == 0


# --- long-term memory -------------------------------------------------------

def test_first_sight_of_a_resource_has_no_memory(tmp_path):
    assert recall("i-never-seen", path=tmp_path / "cc.db") is None


def test_repeat_sightings_accumulate(tmp_path):
    path = tmp_path / "cc.db"
    keep = Recommendation(action="keep", reason="busy", confidence=0.9)
    for _ in range(3):
        record_run(_resource(), recommendation=keep, path=path)

    memory = recall("i-1", path=path)
    assert memory["times_seen"] == 3
    assert memory["times_kept"] == 3
    assert memory["last_verdict"] == "keep"


def test_a_human_decision_is_remembered_across_later_runs(tmp_path):
    path = tmp_path / "cc.db"
    record_run(
        _resource(),
        recommendation=Recommendation(action="retire", reason="idle", confidence=0.8),
        approval=ApprovalDecision(decision="keep", reason="still needed"),
        path=path,
    )
    # a later run where nobody was asked must not erase what the human said
    record_run(_resource(), recommendation=Recommendation(action="retire", reason="idle",
                                                          confidence=0.8), path=path)

    memory = recall("i-1", path=path)
    assert memory["human_decision"] == "keep"
    assert memory["human_decided_at"] is not None


def test_restore_recipe_is_kept_only_when_something_executed(tmp_path):
    path = tmp_path / "cc.db"
    record_run(_resource(), plan=_plan(), path=path)
    assert restore_recipe("i-1", path=path) is None

    record_run(
        _resource(), plan=_plan(),
        approval=ApprovalDecision(decision="approve", approved_resource_ids=["i-1"]),
        action_results=[{"action": "terminate_instance", "resource_id": "i-1",
                         "ok": True, "detail": "i-1", "dry_run": False}],
        dry_run=False, path=path,
    )
    recipe = restore_recipe("i-1", path=path)
    assert recipe["resource_id"] == "i-1"


def test_runs_for_a_resource_are_newest_first(tmp_path):
    path = tmp_path / "cc.db"
    a = record_run(_resource(), path=path)
    b = record_run(_resource(), path=path)
    ids = [r["run_id"] for r in runs_for("i-1", path=path)]
    assert ids[0] == b["run_id"] and ids[1] == a["run_id"]
