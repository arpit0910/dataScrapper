"""Enrich hospitals that carry an OSM `wikidata` tag using the Wikidata API.

Wikidata is public, free, and requires no key.  Values are stored under their
own key with the property they came from, so an enriched value is never
mistaken for something the primary source asserted.
"""

import json
from typing import Any, Iterable
from urllib.parse import quote

from .scraping import RateLimiter, fetch_public_url

API_URL = "https://www.wikidata.org/w/api.php"
BATCH_SIZE = 50  # the API's documented maximum for wbgetentities

# Property -> field name.  Entity-valued properties are resolved to labels in a
# second pass so the output carries readable names, not bare Q-ids.
PROPERTIES: dict[str, str] = {
    "P856": "website",
    "P571": "inception",
    "P6801": "beds",
    "P137": "operator",
    "P749": "parent_organization",
    "P1329": "phone",
    "P968": "email",
    "P281": "postal_code",
    "P6375": "street_address",
    "P1448": "official_name",
    "P18": "image",
    "P31": "instance_of",
    "P131": "administrative_area",
    "P17": "country",
    "P2078": "user_manual",
    "P3492": "clinical_speciality",
}
ENTITY_PROPERTIES = {"P137", "P749", "P31", "P131", "P17", "P3492"}


def batched(items: list[str], size: int = BATCH_SIZE) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _claim_value(claim: dict[str, Any]) -> Any:
    snak = claim.get("mainsnak", {})
    if snak.get("snaktype") != "value":
        return None
    value = snak.get("datavalue", {}).get("value")
    kind = snak.get("datavalue", {}).get("type")
    if kind == "string":
        return value
    if kind == "wikibase-entityid":
        return value.get("id")
    if kind == "monolingualtext":
        return value.get("text")
    if kind == "quantity":
        return str(value.get("amount", "")).lstrip("+") or None
    if kind == "time":
        # Wikidata times look like "+1902-01-01T00:00:00Z"; keep the date part.
        return str(value.get("time", "")).lstrip("+").split("T")[0] or None
    if kind == "globecoordinate":
        return {"latitude": value.get("latitude"), "longitude": value.get("longitude")}
    return None


def fetch_entities(ids: list[str], limiter: RateLimiter, timeout: int = 30, retries: int = 3) -> dict[str, Any]:
    """Fetch raw entity payloads for up to BATCH_SIZE Wikidata ids."""
    if not ids:
        return {}
    url = (
        f"{API_URL}?action=wbgetentities&ids={quote('|'.join(ids))}"
        "&props=labels|claims&languages=en&format=json"
    )
    _, body = fetch_public_url(url, limiter, timeout, retries)
    return json.loads(body).get("entities", {}) or {}


def extract(entity: dict[str, Any]) -> dict[str, Any]:
    """Pull the properties of interest out of one raw entity payload."""
    claims = entity.get("claims", {}) or {}
    result: dict[str, Any] = {}
    for prop, field in PROPERTIES.items():
        statements = claims.get(prop) or []
        values = [v for v in (_claim_value(c) for c in statements) if v not in (None, "")]
        if not values:
            continue
        result[field] = values[0] if len(values) == 1 else values
    label = (entity.get("labels", {}) or {}).get("en", {}).get("value")
    if label:
        result["label"] = label
    return result


def referenced_ids(enrichments: dict[str, dict[str, Any]]) -> list[str]:
    """Collect Q-ids that appear as values and therefore still need labels."""
    fields = {PROPERTIES[p] for p in ENTITY_PROPERTIES}
    found: set[str] = set()
    for payload in enrichments.values():
        for field in fields:
            value = payload.get(field)
            for item in (value if isinstance(value, list) else [value]):
                if isinstance(item, str) and item.startswith("Q") and item[1:].isdigit():
                    found.add(item)
    return sorted(found)


def resolve_labels(enrichments: dict[str, dict[str, Any]], labels: dict[str, str]) -> None:
    """Replace Q-ids with human-readable labels, in place."""
    fields = {PROPERTIES[p] for p in ENTITY_PROPERTIES}
    for payload in enrichments.values():
        for field in fields:
            if field not in payload:
                continue
            value = payload[field]
            if isinstance(value, list):
                payload[field] = [labels.get(v, v) if isinstance(v, str) else v for v in value]
            elif isinstance(value, str):
                payload[field] = labels.get(value, value)
