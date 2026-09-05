"""Cost model (stopped != free) and teardown action defaults."""

from cloudcleaner.tools.aws import actions
from cloudcleaner.tools.aws.cost import ebs_cost, instance_cost, public_ipv4_cost


def test_running_instance_pays_for_compute_storage_and_address():
    cost, residual = instance_cost("running", "t3.micro", attached_volumes_gb=16, has_public_ip=True)
    assert cost > 0 and residual is False


def test_stopped_instance_still_bills_storage_and_address():
    cost, residual = instance_cost("stopped", "t3.micro", attached_volumes_gb=16, has_public_ip=True)
    assert residual is True
    assert cost == round(ebs_cost(16) + public_ipv4_cost(), 2)


def test_stopped_instance_with_nothing_attached_is_free():
    cost, residual = instance_cost("stopped", "t3.micro", 0, False)
    assert cost == 0.0 and residual is False


def test_stopping_does_not_save_the_whole_bill():
    running, _ = instance_cost("running", "t3.micro", 16, True)
    stopped, _ = instance_cost("stopped", "t3.micro", 16, True)
    assert 0 < stopped < running


def test_every_action_is_dry_run_by_default():
    for name, fn in actions.ACTIONS.items():
        result = fn("x-1")
        assert result["dry_run"] is True, name
