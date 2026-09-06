import csv
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook


HOSPITAL_COLUMNS = ["name_en", "name_hi", "type", "address", "city", "emergency_phone", "latitude", "longitude"]
DOCTOR_COLUMNS = ["doctor_hospital_link_id", "doctor_id", "hospital_id", "registration_number", "first_name", "last_name", "department_name_en", "department_name_hi", "medical_council", "country_code_1", "country_code_2", "phone_1", "phone_2", "consultation_fee", "experience_years", "education_degrees", "about_en", "about_hi", "email", "website", "city", "state", "pincode", "address_line1", "address_line2", "landmark", "languages_spoken", "gender", "is_verified", "latitude", "longitude", "hospital_name", "hospital_city", "doctor_hospital_role", "consultation_mode", "availability", "days_of_week", "start_time", "end_time", "hospital_consultation_fee"]


def template_columns(path: str | Path) -> list[str]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return next(csv.reader(handle))


def assert_template_columns(path: str | Path, columns: list[str]) -> None:
    actual = template_columns(path)
    if actual != columns:
        raise ValueError(f"Template headers do not match. Expected {columns}; found {actual}")


def export_rows(rows: list[dict[str, Any]], columns: list[str], output: str | Path, fmt: str = "xlsx") -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.casefold()
    if fmt not in {"xlsx", "csv", "json"}:
        raise ValueError(f"Unsupported export format: {fmt}. Choose xlsx, csv, or json.")
    if fmt == "json":
        output.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    elif fmt == "csv":
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(columns)
        for row in rows:
            sheet.append([row.get(column) for column in columns])
        workbook.save(output)
    return output
