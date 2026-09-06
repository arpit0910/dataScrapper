import pytest

from arogio.models import SourceUsage
from arogio.source_governance import AutomatedAccessNotPermittedError, SourceNotApprovedError, assert_source_can_run


def approved_config():
    return {
        "source_status": "approved",
        "machine_access": {"automation_permitted": True},
        "approved_usage": {"ingestion": True},
    }


def test_unknown_source_permission_fails_closed():
    with pytest.raises(SourceNotApprovedError):
        assert_source_can_run({})


def test_approved_source_requires_explicit_automation_permission():
    config = approved_config()
    config["machine_access"]["automation_permitted"] = None
    with pytest.raises(AutomatedAccessNotPermittedError):
        assert_source_can_run(config)


def test_approved_source_can_run_only_for_approved_usage():
    assert_source_can_run(approved_config(), SourceUsage.INGESTION)
    with pytest.raises(SourceNotApprovedError):
        assert_source_can_run(approved_config(), SourceUsage.VERIFICATION)
