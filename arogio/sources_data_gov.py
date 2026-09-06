import csv
from pathlib import Path
from typing import Any

from .dedupe import stable_id
from .normalization import clean_text, normalize_coordinate, normalize_email, normalize_phone, normalize_pincode, normalize_url
from .sources import Location


class DataGovHospitalAdapter:
    source_name = "data_gov_in_hospital_directory"
    source_url = "https://www.data.gov.in/resource/national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month"

    def parse_file(self, path: str | Path) -> list[dict[str, Any]]:
        with Path(path).open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            return list(csv.DictReader(handle))

    def normalize_source_record(self, record: dict[str, Any], location: Location) -> dict[str, Any]:
        def first(*names: str) -> str | None:
            for name in names:
                value = clean_text(record.get(name))
                if value and value.casefold() not in {"0", "na", "n/a", "-", "null"}:
                    return value
            return None

        name = first("Hospital_Name", "Hospital Name", "hospital_name", "Name")
        address = first("Address_Original_First_Line", "Address", "address")
        phone_code, phone = normalize_phone(first("Telephone", "Mobile_Number", "Phone"))
        lat = normalize_coordinate(first("Latitude", "latitude"), -90, 90)
        lon = normalize_coordinate(first("Longitude", "longitude"), -180, 180)
        source_city = first("Town", "City", "city")
        return {
            "hospital_id": stable_id("hospital", self.source_name, name, address, first("Pincode", "pincode")),
            "name": name,
            "name_en": name,
            "hospital_type": first("Hospital_Category", "Hospital Category", "Category"),
            "type": first("Hospital_Category", "Hospital Category", "Category"),
            "address": address,
            # Keep the source's city separate from its district.  The import
            # command assigns the requested target city only after the row has
            # passed the district+pincode fallback rule.
            "city": source_city or "",
            "source_city": source_city,
            "district": first("District"),
            "state": first("State", "state") or location.state,
            "country": location.country,
            "pincode": normalize_pincode(first("Pincode", "pincode", "PIN")),
            "phone": phone,
            "phone_1": phone,
            "country_code_1": phone_code,
            "email": normalize_email(first("Hospital_Primary_Email_Id", "Email", "email")),
            "website": normalize_url(first("Website", "website")),
            "latitude": lat,
            "longitude": lon,
            "specialties": first("Specialties", "specialties"),
            "source": self.source_name,
            "source_url": self.source_url,
            "source_record_id": first("Sr_No", "Sr No", "ID") or stable_id("record", name, address),
            "verification_status": "needs_review",
            "source_usage": "discovery",
        }

    def filter_location(self, record: dict[str, Any], location: Location) -> bool:
        city = clean_text(record.get("source_city") or record.get("city")) or ""
        state = clean_text(record.get("state")) or ""
        if state.casefold() != location.state.casefold():
            return False
        if location.statewide:
            return True
        if city.casefold() == location.city.casefold():
            return True
        district = clean_text(record.get("district")) or ""
        pincode = clean_text(record.get("pincode")) or ""
        return district.casefold() == location.city.casefold() and any(pincode.startswith(prefix) for prefix in location.pincode_prefixes)
