"""Parser for the ICICI Lombard network-hospital JSON shape supplied by the owner."""

from html import unescape
from typing import Any

from .dedupe import stable_id
from .normalization import clean_text, normalize_coordinate, normalize_phone, normalize_pincode
from .sources import BaseSource, Location
from .source_governance import assert_source_can_run
from .models import SourceUsage


class ICICILombardSource(BaseSource):
    source_name = "icici_lombard_network"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def supports(self, entity_type: str) -> bool:
        return entity_type == "hospital"

    def discover(self, location: Location) -> list[dict[str, Any]]:
        assert_source_can_run(self.config, SourceUsage.INGESTION)
        raise RuntimeError("ICICI discovery requires the owner-supplied JSON payload; the live page blocks direct requests")

    def fetch(self, item: Any) -> Any:
        return item

    def parse(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        return list(response.get("data", {}).get("lstHosptalList", []))

    def normalize_source_record(self, record: dict[str, Any], location: Location) -> dict[str, Any]:
        phone_code, phone = normalize_phone(record.get("Contact_number"))
        latitude = normalize_coordinate(record.get("latitude"), -90, 90)
        longitude = normalize_coordinate(record.get("longitude"), -180, 180)
        if latitude == 0 and longitude == 0:
            latitude = longitude = None
        name = clean_text(record.get("HospitalName"))
        address = clean_text(unescape(record.get("address", "")))
        pincode = normalize_pincode(record.get("pincode"))
        return {
            "hospital_id": stable_id("hospital", self.source_name, name, address, pincode),
            "name": name,
            "name_en": name,
            "hospital_type": clean_text(record.get("Type")),
            "type": clean_text(record.get("Type")),
            "address": address,
            "city": location.city,
            "state": location.state,
            "country": location.country,
            "pincode": pincode,
            "phone": phone,
            "phone_1": phone,
            "latitude": latitude,
            "longitude": longitude,
            "source": self.source_name,
            "source_url": "https://www.icicilombard.com/cashless-hospitals",
            "source_record_id": stable_id("icici", name, address, pincode),
            "country_code_1": phone_code,
            "verification_status": "needs_review",
            "is_within_target_location": bool(pincode and any(pincode.startswith(prefix) for prefix in location.pincode_prefixes)),
        }
