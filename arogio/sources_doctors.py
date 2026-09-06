import csv
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .dedupe import stable_id
from .normalization import clean_text, normalize_email, normalize_phone, normalize_pincode, normalize_url
from .sources import Location


class OfficialDoctorFileAdapter:
    """Import an authorized doctor registry/export without guessing its schema."""

    def __init__(self, source_name: str, source_url: str) -> None:
        self.source_name = source_name
        self.source_url = source_url

    def parse_file(self, path: str | Path) -> list[dict[str, Any]]:
        path = Path(path)
        if path.suffix.casefold() in {".xlsx", ".xlsm"}:
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook.active
            rows = sheet.iter_rows(values_only=True)
            headers = [str(value or "").strip() for value in next(rows)]
            return [dict(zip(headers, row)) for row in rows if any(value not in (None, "") for value in row)]
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            return list(csv.DictReader(handle))

    def normalize_source_record(self, record: dict[str, Any], location: Location) -> dict[str, Any]:
        def first(*names: str) -> str | None:
            lowered = {str(key).casefold().replace(" ", "_"): value for key, value in record.items()}
            for name in names:
                value = clean_text(lowered.get(name.casefold().replace(" ", "_")))
                if value and value.casefold() not in {"0", "na", "n/a", "-", "null"}:
                    return value
            return None

        full_name = first("full_name", "doctor_full_name", "doctor_name", "name", "physician_name")
        registration = first("registration_number", "registration_no", "reg_no", "imr_number")
        phone_code, phone = normalize_phone(first("phone", "mobile", "mobile_number", "telephone"))
        state = first("state", "registered_state", "address_state") or location.state
        city = first("city", "town", "district", "address_city") or ""
        return {
            "doctor_id": stable_id("doctor", self.source_name, registration or full_name, city),
            "full_name": full_name or "Unknown",
            "registration_number": registration,
            "specialization": first("specialization", "speciality", "department", "specialty"),
            "qualification": first("qualification", "qualifications", "degree", "education"),
            "medical_council": first("medical_council", "council", "registered_council"),
            "phone_1": phone,
            "country_code_1": phone_code,
            "email": normalize_email(first("email", "email_id")),
            "website": normalize_url(first("website", "profile_url")),
            "profile_url": normalize_url(first("source_url", "profile_url")),
            "city": city,
            "state": state,
            "pincode": normalize_pincode(first("pincode", "pin", "postal_code")),
            "address_line1": first("address", "address_line1", "clinic_address", "hospital_address"),
            "organization_name": first("hospital", "hospital_name", "organization", "clinic"),
            "source": self.source_name,
            "source_url": self.source_url,
            "source_record_id": registration or stable_id("record", full_name, city),
            "verification_status": "needs_review",
            "source_usage": "discovery",
        }

    def filter_location(self, record: dict[str, Any], location: Location) -> bool:
        if (record.get("state") or "").casefold() != location.state.casefold():
            return False
        if location.statewide:
            return True
        return (record.get("city") or "").casefold() == location.city.casefold()
