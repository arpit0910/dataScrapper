from dataclasses import dataclass
from typing import Any

from .models import SourceUsage
from .source_governance import assert_source_can_run


@dataclass(frozen=True)
class Location:
    city: str
    state: str
    country: str = "India"
    pincode_prefixes: tuple[str, ...] = ()
    statewide: bool = False


class BaseSource:
    source_name = "base"

    def supports(self, entity_type: str) -> bool:
        return False

    def discover(self, location: Location):
        raise NotImplementedError

    def fetch(self, item):
        raise NotImplementedError

    def parse(self, response):
        raise NotImplementedError

    def normalize_source_record(self, record):
        raise NotImplementedError


class ApprovedSource(BaseSource):
    source_name = "approved_source"

    def __init__(self, base_url: str, enabled: bool = False, config: dict[str, Any] | None = None) -> None:
        self.base_url = base_url.strip()
        self.enabled = enabled
        self.config = config or {}

    def supports(self, entity_type: str) -> bool:
        return self.enabled and bool(self.base_url) and entity_type in {"hospital", "doctor"}

    def discover(self, location: Location):
        assert_source_can_run(self.config, SourceUsage.INGESTION)
        if not self.supports("hospital") and not self.supports("doctor"):
            raise RuntimeError("approved_source is disabled: configure an explicitly approved public source URL in config/sources.yaml")
        raise NotImplementedError("The approved source parser is intentionally pending source-owner configuration")


def build_source(name: str, config: dict) -> BaseSource:
    if name == "approved_source":
        return ApprovedSource(config.get("base_url", ""), config.get("enabled", False), config)
    if name == "icici_lombard_network":
        from .sources_icici import ICICILombardSource
        return ICICILombardSource(config)
    raise ValueError(f"No adapter is registered for source: {name}")
