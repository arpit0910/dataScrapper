from typing import Any

from .models import SourceStatus, SourceUsage


class SourceNotApprovedError(RuntimeError):
    pass


class AutomatedAccessNotPermittedError(RuntimeError):
    pass


def assert_source_can_run(config: dict[str, Any], usage: SourceUsage = SourceUsage.INGESTION) -> None:
    """Fail closed unless approval and the requested usage are explicitly true."""
    status = config.get("source_status", SourceStatus.ACCESS_REVIEW_PENDING.value)
    if status != SourceStatus.APPROVED.value:
        raise SourceNotApprovedError(f"Source is not approved for production retrieval (status={status}).")
    machine = config.get("machine_access", {})
    if machine.get("automation_permitted") is not True:
        raise AutomatedAccessNotPermittedError("Automated access permission is not explicitly true.")
    usage_config = config.get("approved_usage", {})
    if usage_config.get(usage.value) is not True:
        raise SourceNotApprovedError(f"Source is not approved for usage={usage.value}.")
