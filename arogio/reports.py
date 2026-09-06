from collections.abc import Iterable
from typing import Any


def completeness(records: Iterable[dict[str, Any]], fields: list[str]) -> dict[str, dict[str, float | int]]:
    rows = list(records)
    total = len(rows)
    result: dict[str, dict[str, float | int]] = {}
    for field in fields:
        populated = sum(1 for row in rows if row.get(field) not in (None, "", [], {}))
        result[field] = {"populated": populated, "total": total, "percent": round(populated * 100 / total, 1) if total else 0.0}
    return result


HOSPITAL_REPORT_FIELDS = ["phone", "emergency_phone", "address", "pincode", "website", "email", "latitude", "longitude", "departments"]
DOCTOR_REPORT_FIELDS = ["registration_number", "medical_council", "phone_1", "email", "qualification", "experience_years", "department_name_en", "organization_name", "address_line1", "pincode", "latitude", "longitude", "consultation_fee"]
