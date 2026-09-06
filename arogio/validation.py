import re
from collections.abc import Mapping


def validate_pincode(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"\d{6}", value))


def validate_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return latitude is not None and longitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180


def validate_record(record: Mapping[str, object], required_fields: list[str]) -> list[str]:
    errors = [field for field in required_fields if not record.get(field)]
    if "pincode" in record and record.get("pincode") and not validate_pincode(str(record["pincode"])):
        errors.append("pincode")
    if "latitude" in record or "longitude" in record:
        if (record.get("latitude") is not None or record.get("longitude") is not None) and not validate_coordinates(record.get("latitude"), record.get("longitude")):
            errors.append("coordinates")
    if record.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(record["email"])):
        errors.append("email")
    for phone_field in ("phone", "phone_1", "phone_2", "emergency_phone"):
        if record.get(phone_field):
            digits = re.sub(r"\D", "", str(record[phone_field]))
            if len(digits) not in {7, 8, 10, 11, 12}:
                errors.append(phone_field)
    if "experience_years" in record and record.get("experience_years") is not None:
        try:
            if int(record["experience_years"]) < 0:
                errors.append("experience_years")
        except (TypeError, ValueError):
            errors.append("experience_years")
    return errors


def is_within_target_location(record: Mapping[str, object], location: Mapping[str, str]) -> bool:
    return (
        str(record.get("city", "")).strip().casefold() == location["city"].strip().casefold()
        and str(record.get("state", "")).strip().casefold() == location["state"].strip().casefold()
    )
