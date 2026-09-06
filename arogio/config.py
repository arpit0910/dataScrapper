from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent


def load_yaml(name: str) -> dict[str, Any]:
    path = ROOT / "config" / name
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def location(city: str, state: str | None = None) -> dict[str, Any]:
    locations = load_yaml("locations.yaml").get("locations", {})
    value = locations.get(city.casefold(), {"city": city, "state": state or "", "country": "India"})
    if state and value.get("state", "").casefold() != state.casefold():
        raise ValueError(f"Configured location state does not match {city}, {state}")
    return value


def source(name: str) -> dict[str, Any]:
    sources = load_yaml("sources.yaml").get("sources", {})
    value = sources.get(name)
    if not value:
        raise ValueError(f"Unknown source: {name}")
    return value
