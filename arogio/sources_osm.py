"""Live adapter for OpenStreetMap healthcare facilities via the Overpass API.

OpenStreetMap data is published under the Open Database Licence (ODbL 1.0) and
the Overpass API is a public endpoint intended for programmatic queries.  Reuse
is permitted with attribution, so this adapter carries the licence and the
attribution string on every record it produces.

The adapter fetches ordinary public API responses under a rate limiter.  It does
not bypass authentication, CAPTCHA, robots restrictions, or anti-bot controls.
"""

import json
from typing import Any, Iterable, Iterator

from .dedupe import stable_id
from .normalization import (
    clean_text,
    normalize_coordinate,
    normalize_email,
    normalize_phone,
    normalize_pincode,
    normalize_url,
)
from .sources import BaseSource, Location

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
# Public Overpass mirrors carrying full planet data.  Each enforces its own
# small slot limit, so a long run rotates between them instead of exhausting one
# host.  Regional instances (overpass.osm.ch, for example) are deliberately
# excluded: they answer with HTTP 200 and zero elements outside their extract,
# which would look like a legitimately empty area rather than a wrong server.
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# A small area that is known to contain hospitals, used to prove a mirror really
# serves the region being collected before a long run trusts it.
PROBE_STATE = "IN-GA"

# OSM "facility:*"/"healthcare:*" flags describing what a hospital can actually
# do.  These are the clinically meaningful fields the first pass discarded.
FACILITY_TAGS = {
    "opd": ("facility:opd", "healthcare:opd"),
    "ipd": ("facility:ipd", "healthcare:ipd"),
    "icu": ("facility:icu", "healthcare:icu", "facility:intensive_care"),
    "emergency": ("emergency", "facility:emergency", "facility:casualty"),
    "ambulance": ("facility:ambulance", "emergency:ambulance"),
    "blood_bank": ("facility:blood_bank", "healthcare:blood_bank", "blood_bank"),
    "operating_theatre": ("facility:operating_theater", "facility:operation_theatre"),
    "pathology_lab": ("facility:pathology_labs", "facility:pathology_lab"),
    "radiology_lab": ("facility:radiology_labs", "facility:radiology_lab", "facility:xray"),
    "ventilator": ("facility:ventilator",),
    "delivery": ("facility:delivery", "facility:labour_room"),
    "pharmacy": ("pharmacy", "facility:pharmacy", "dispensing"),
    "mortuary": ("facility:mortuary",),
    "ultrasound": ("facility:ultrasound",),
    "dialysis": ("facility:dialysis", "healthcare:dialysis"),
    "helipad": ("aeroway", "facility:helipad"),
}

# Payment methods appear as payment:<method>=yes.
PAYMENT_PREFIX = "payment:"
NAME_PREFIX = "name:"
LICENSE = "ODbL 1.0"
ATTRIBUTION = "© OpenStreetMap contributors"

# Verified against the live Overpass area index: the 36 Indian states and union
# territories that carry an ISO3166-2 boundary.  Ordered so that the largest
# facility counts are collected first, which makes a time-bounded run useful
# even if it is stopped early.
INDIA_STATES: tuple[tuple[str, str], ...] = (
    ("IN-UP", "Uttar Pradesh"),
    ("IN-MH", "Maharashtra"),
    ("IN-WB", "West Bengal"),
    ("IN-BR", "Bihar"),
    ("IN-TN", "Tamil Nadu"),
    ("IN-MP", "Madhya Pradesh"),
    ("IN-RJ", "Rajasthan"),
    ("IN-KA", "Karnataka"),
    ("IN-GJ", "Gujarat"),
    ("IN-AP", "Andhra Pradesh"),
    ("IN-OD", "Odisha"),
    ("IN-TS", "Telangana"),
    ("IN-KL", "Kerala"),
    ("IN-JH", "Jharkhand"),
    ("IN-AS", "Assam"),
    ("IN-PB", "Punjab"),
    ("IN-CG", "Chhattisgarh"),
    ("IN-HR", "Haryana"),
    ("IN-DL", "Delhi"),
    ("IN-JK", "Jammu and Kashmir"),
    ("IN-UK", "Uttarakhand"),
    ("IN-HP", "Himachal Pradesh"),
    ("IN-TR", "Tripura"),
    ("IN-ML", "Meghalaya"),
    ("IN-MN", "Manipur"),
    ("IN-NL", "Nagaland"),
    ("IN-GA", "Goa"),
    ("IN-AR", "Arunachal Pradesh"),
    ("IN-PY", "Puducherry"),
    ("IN-MZ", "Mizoram"),
    ("IN-SK", "Sikkim"),
    ("IN-CH", "Chandigarh"),
    ("IN-AN", "Andaman and Nicobar Islands"),
    ("IN-DH", "Dadra and Nagar Haveli and Daman and Diu"),
    ("IN-LA", "Ladakh"),
    ("IN-LD", "Lakshadweep"),
)

STATE_BY_NAME = {name.casefold(): code for code, name in INDIA_STATES}
STATE_BY_CODE = dict(INDIA_STATES)

# OSM tags that mark a healthcare facility.  "hospital" alone already exceeds
# the ten-thousand target nationwide; clinics and doctors' surgeries are opt-in.
KIND_FILTERS = {
    "hospital": ('nwr["amenity"="hospital"]', 'nwr["healthcare"="hospital"]'),
    "clinic": ('nwr["amenity"="clinic"]', 'nwr["healthcare"="clinic"]'),
    "doctors": ('nwr["amenity"="doctors"]', 'nwr["healthcare"="doctor"]'),
}


def resolve_state_code(state: str) -> str | None:
    value = (state or "").strip()
    if value.upper() in STATE_BY_CODE:
        return value.upper()
    return STATE_BY_NAME.get(value.casefold())


class OsmOverpassHospitalAdapter(BaseSource):
    source_name = "osm_overpass_health_facilities"
    source_url = "https://www.openstreetmap.org"
    endpoint = OVERPASS_ENDPOINT

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.endpoint = self.config.get("api_url", OVERPASS_ENDPOINT)
        configured = self.config.get("api_urls") or list(OVERPASS_ENDPOINTS)
        # Keep the primary endpoint usable on its own while preserving order.
        self.endpoints = list(dict.fromkeys([*configured]))

    def supports(self, entity_type: str) -> bool:
        return entity_type == "hospital"

    # ---- query building -------------------------------------------------

    def build_query(self, state_code: str, kinds: tuple[str, ...] = ("hospital",), timeout: int = 300) -> str:
        clauses: list[str] = []
        for kind in kinds:
            clauses.extend(KIND_FILTERS[kind])
        body = "\n  ".join(f"{clause}(area.a);" for clause in clauses)
        return (
            f"[out:json][timeout:{timeout}];\n"
            f'area["ISO3166-2"="{state_code}"]->.a;\n'
            f"(\n  {body}\n);\n"
            "out center tags;"
        )

    def probe_query(self, timeout: int = 60) -> str:
        return (
            f"[out:json][timeout:{timeout}];\n"
            f'area["ISO3166-2"="{PROBE_STATE}"]->.a;\n'
            'nwr["amenity"="hospital"](area.a);\n'
            "out count;"
        )

    @staticmethod
    def probe_count(body: str) -> int:
        """Read the total from an `out count;` response, or 0 if absent."""
        elements = json.loads(body).get("elements", [])
        if not elements:
            return 0
        try:
            return int(elements[0].get("tags", {}).get("total", 0))
        except (TypeError, ValueError):
            return 0

    # ---- parsing --------------------------------------------------------

    def parse(self, response: str | dict[str, Any]) -> list[dict[str, Any]]:
        payload = json.loads(response) if isinstance(response, str) else response
        return [element for element in payload.get("elements", []) if element.get("tags")]

    # ---- normalization --------------------------------------------------

    def normalize_source_record(self, record: dict[str, Any], location: Location) -> dict[str, Any]:
        tags: dict[str, str] = record.get("tags", {})

        def tag(*names: str) -> str | None:
            for name in names:
                value = clean_text(tags.get(name))
                if value and value.casefold() not in {"", "na", "n/a", "-", "null", "unknown", "yes"}:
                    return value
            return None

        name = tag("name", "name:en", "official_name", "alt_name")
        osm_type = record.get("type", "node")
        osm_id = record.get("id")
        centre = record.get("center") or {}
        latitude = normalize_coordinate(record.get("lat", centre.get("lat")), -90, 90)
        longitude = normalize_coordinate(record.get("lon", centre.get("lon")), -180, 180)

        phones = self._phones(tag("phone", "contact:phone", "contact:mobile", "mobile"))
        emergency_code, emergency_phone = normalize_phone(
            tag("emergency:phone", "contact:emergency", "phone:emergency")
        )

        city = tag("addr:city", "addr:town", "addr:village", "addr:suburb")
        district = tag("addr:district", "addr:subdistrict", "addr:county")
        # addr:state is free text and is misspelled in places ("Maharastra"),
        # which would split one state across several groups.  The query already
        # targeted an authoritative state boundary, so that name wins and the
        # raw tag is kept alongside it for provenance.
        source_state = tag("addr:state")
        state = location.state or source_state
        pincode = normalize_pincode(tag("addr:postcode", "postal_code"))
        address = self._address(tags)
        facility = tag("amenity", "healthcare") or "hospital"
        specialities = self._specialities(tags)
        profile_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else None

        return {
            "hospital_id": stable_id("hospital", self.source_name, osm_type, osm_id),
            "name": name,
            "name_en": tag("name:en") or name,
            "name_hi": tag("name:hi"),
            "official_name": tag("official_name"),
            "short_name": tag("short_name", "operator:short"),
            "alt_name": tag("alt_name", "old_name"),
            "names_by_language": self._names(tags),
            "reference_code": tag("ref", "hospital_type_id"),
            "hospital_type": facility,
            "type": facility,
            "hospital_subtype": tag("hospital:type", "health_facility:type"),
            "medical_system": tag("medical_system"),
            "operational_status": tag("operational_status", "operational_status:date"),
            "description": tag("description", "note"),
            "address": address,
            "address_line1": tag("addr:full", "addr:street") or address,
            "address_line2": tag("addr:housenumber"),
            "locality": tag("addr:suburb", "addr:neighbourhood", "addr:block", "locality"),
            "landmark": tag("addr:landmark", "addr:place"),
            "city": city or district or "",
            "source_city": city,
            "district": district,
            "subdistrict": tag("addr:subdistrict"),
            "state": state,
            "source_state": source_state,
            "pincode": pincode,
            "country": tag("addr:country") or location.country,
            "phone": phones[0][1] if phones else None,
            "phone_1": phones[0][1] if phones else None,
            "phone_2": phones[1][1] if len(phones) > 1 else None,
            "all_phones": [number for _, number in phones],
            "country_code_1": phones[0][0] if phones else None,
            "country_code_2": phones[1][0] if len(phones) > 1 else None,
            "emergency_phone": emergency_phone,
            "emergency_country_code": emergency_code,
            "fax": tag("fax", "contact:fax"),
            "email": normalize_email(tag("email", "contact:email", "contact:nodal_officer_email")),
            "website": normalize_url(tag("website", "contact:website", "url")),
            "emergency_available": self._boolean(tags.get("emergency")),
            "operator": tag("operator"),
            "operator_type": tag("operator:type"),
            "ownership": self._ownership(tag("operator:type")),
            "specialties": "; ".join(specialities) if specialities else None,
            "departments": specialities,
            "facilities": self._facilities(tags),
            "beds": tag("beds", "capacity:beds", "health_facility:bed"),
            "personnel_count": tag("personnel:count", "staff_count"),
            "building_levels": tag("building:levels"),
            "opening_hours": tag("opening_hours"),
            "wheelchair": tag("wheelchair"),
            "internet_access": tag("internet_access"),
            "payment_methods": self._payments(tags),
            "latitude": latitude,
            "longitude": longitude,
            "osm_type": osm_type,
            "osm_id": osm_id,
            "profile_url": profile_url,
            "wikidata": tag("wikidata"),
            "wikipedia": tag("wikipedia"),
            "operator_wikidata": tag("operator:wikidata"),
            "osm_source": tag("source"),
            "last_checked": tag("check_date", "survey:date"),
            "established": tag("start_date", "opening_date"),
            # The complete upstream tag set, so no collected value is ever lost
            # to a mapping gap; the fields above are conveniences over this.
            "osm_tags": dict(tags),
            "source": self.source_name,
            "source_url": profile_url or self.source_url,
            "source_record_id": f"{osm_type}/{osm_id}",
            "license": LICENSE,
            "attribution": ATTRIBUTION,
            "verification_status": "needs_review",
            "source_usage": "ingestion",
        }

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _names(tags: dict[str, str]) -> dict[str, str]:
        """Collect every name:<lang> variant, which India tags heavily."""
        names: dict[str, str] = {}
        for key, value in tags.items():
            if not key.startswith(NAME_PREFIX):
                continue
            language = key[len(NAME_PREFIX):]
            # name:etymology:wikidata and friends are not language variants.
            if ":" in language or not language:
                continue
            cleaned = clean_text(value)
            if cleaned:
                names[language] = cleaned
        return names

    @staticmethod
    def _facilities(tags: dict[str, str]) -> dict[str, Any]:
        """Map OSM facility flags to a stable set of capability fields."""
        found: dict[str, Any] = {}
        for name, keys in FACILITY_TAGS.items():
            for key in keys:
                if key not in tags:
                    continue
                raw = str(tags[key]).strip()
                lowered = raw.casefold()
                if lowered in {"yes", "true", "1"}:
                    found[name] = True
                elif lowered in {"no", "false", "0"}:
                    found[name] = False
                elif lowered not in {"", "unknown"}:
                    # Values such as counts or "designated" carry real detail.
                    found[name] = raw
                break
        return found

    @staticmethod
    def _payments(tags: dict[str, str]) -> list[str]:
        accepted = []
        for key, value in tags.items():
            if key.startswith(PAYMENT_PREFIX) and str(value).strip().casefold() in {"yes", "true", "1"}:
                method = key[len(PAYMENT_PREFIX):].replace("_", " ")
                if method:
                    accepted.append(method)
        return sorted(accepted)

    @staticmethod
    def _phones(value: str | None) -> list[tuple[str | None, str]]:
        if not value:
            return []
        found: list[tuple[str | None, str]] = []
        for part in str(value).replace(",", ";").split(";"):
            code, number = normalize_phone(part)
            if number and all(number != existing for _, existing in found):
                found.append((code, number))
        return found

    @staticmethod
    def _address(tags: dict[str, str]) -> str | None:
        full = clean_text(tags.get("addr:full"))
        if full:
            return full
        parts = [
            clean_text(tags.get(key))
            for key in (
                "addr:housenumber",
                "addr:street",
                "addr:neighbourhood",
                "addr:suburb",
                "addr:village",
                "addr:town",
                "addr:city",
                "addr:district",
                "addr:state",
                "addr:postcode",
            )
        ]
        joined = ", ".join(part for part in parts if part)
        return joined or None

    @staticmethod
    def _specialities(tags: dict[str, str]) -> list[str]:
        raw = tags.get("healthcare:speciality") or tags.get("speciality") or ""
        values = [clean_text(item.replace("_", " ")) for item in str(raw).split(";")]
        return [value.title() for value in values if value]

    @staticmethod
    def _boolean(value: str | None) -> bool | None:
        if value is None:
            return None
        lowered = str(value).strip().casefold()
        if lowered in {"yes", "true", "1"}:
            return True
        if lowered in {"no", "false", "0"}:
            return False
        return None

    @staticmethod
    def _ownership(operator_type: str | None) -> str | None:
        """Fold the many free-text operator:type spellings into stable buckets.

        Values arrive as "private", "Private", "private_for_profit",
        "public/government", "government_facility-public" and similar, so
        matching is done on normalized substrings rather than exact equality.
        """
        if not operator_type:
            return None
        lowered = operator_type.casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
        if "non_profit" in lowered or "not_for_profit" in lowered or "nonprofit" in lowered:
            return "private_not_for_profit"
        if any(token in lowered for token in ("ngo", "charit", "religious", "trust", "mission")):
            return "charitable"
        if any(token in lowered for token in ("government", "public", "municipal", "state", "military")):
            return "government"
        if any(token in lowered for token in ("private", "business", "company", "corporate", "consortium")):
            return "private"
        if any(token in lowered for token in ("community", "cooperative", "co_operative")):
            return "community"
        return operator_type

    # ---- location filtering ---------------------------------------------

    def filter_location(self, record: dict[str, Any], location: Location) -> bool:
        """Keep a record only when it plausibly sits in the requested target."""
        if not record.get("name"):
            return False
        if location.statewide:
            return True
        target = location.city.casefold()
        for field in ("source_city", "district", "locality"):
            if (record.get(field) or "").casefold() == target:
                return True
        pincode = record.get("pincode") or ""
        if location.pincode_prefixes and any(pincode.startswith(p) for p in location.pincode_prefixes):
            return True
        address = (record.get("address") or "").casefold()
        return bool(address) and target in address

    # ---- planning --------------------------------------------------------

    def plan(self, location: Location, states: Iterable[str] | None = None) -> Iterator[tuple[str, str]]:
        """Yield the (state_code, state_name) chunks a run should fetch.

        An explicit `states` list lets one process cover several states behind a
        single readiness probe; a process per state would re-probe each time and
        burn the endpoint's small slot allowance on setup rather than data.
        """
        if states:
            for name in states:
                code = resolve_state_code(name)
                if not code:
                    raise ValueError(f"Unknown Indian state: {name}")
                yield code, STATE_BY_CODE[code]
            return
        if (location.state or "").casefold() in {"", "all", "india"}:
            yield from INDIA_STATES
            return
        code = resolve_state_code(location.state)
        if not code:
            raise ValueError(
                f"Unknown Indian state: {location.state}. "
                f"Use one of: {', '.join(name for _, name in INDIA_STATES)}"
            )
        yield code, STATE_BY_CODE[code]

    def discover(self, location: Location, states: Iterable[str] | None = None) -> list[tuple[str, str]]:
        return list(self.plan(location, states))
