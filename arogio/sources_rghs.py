import re
from pathlib import Path
from typing import Any

import pdfplumber

from .dedupe import stable_id
from .normalization import clean_text
from .sources import Location


class RghsHospitalAdapter:
    """Parse the official RGHS empanelled-hospital PDF supplied by the user."""

    source_name = "rajasthan_rghs_empanelled_hospitals"
    source_url = "https://rghs.rajasthan.gov.in/OPDLISTHOSPITAL.pdf"
    _date = re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}\b")
    _row = re.compile(r"^\s*(\d+)\s+(.+)$")

    def parse_file(self, path: str | Path) -> list[dict[str, Any]]:
        with pdfplumber.open(path) as document:
            text = "\n".join(page.extract_text() or "" for page in document.pages)
        lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
        try:
            start = next(i for i, line in enumerate(lines) if line.casefold() == "jaipur")
        except StopIteration:
            return []
        rows: list[dict[str, Any]] = []
        current: list[str] = []
        for line in lines[start + 1:]:
            match = self._row.match(line)
            if match:
                if current:
                    rows.append(self._parse_block(current))
                current = [match.group(2)]
            elif current:
                # The PDF wraps long hospital names/specialties onto lines.
                current.append(line)
        if current:
            rows.append(self._parse_block(current))
        return [row for row in rows if row.get("name")]

    def _parse_block(self, lines: list[str]) -> dict[str, Any]:
        joined = " ".join(lines)
        dates = self._date.findall(joined)
        without_dates = self._date.sub("", joined)
        without_dates = re.sub(r"\b(?:Empanelled under RGHS|F\.6\([^)]*\)[^ ]*)\b", "", without_dates, flags=re.I)
        name = clean_text(without_dates).strip(" .,-")
        return {
            "name": name,
            "specialties": None,
            "empanelment_valid_from": dates[-2] if len(dates) >= 2 else None,
            "empanelment_valid_upto": dates[-1] if dates else None,
            "source_text": joined,
        }

    def normalize_source_record(self, record: dict[str, Any], location: Location) -> dict[str, Any]:
        name = record["name"]
        return {
            "hospital_id": stable_id("hospital", self.source_name, name),
            "name": name,
            "name_en": name,
            "type": "RGHS empanelled hospital",
            "hospital_type": "RGHS empanelled hospital",
            "address": name if location.city.casefold() in name.casefold() else None,
            "city": location.city,
            "state": location.state,
            "country": location.country,
            "specialties": record.get("specialties"),
            "empanelment_valid_from": record.get("empanelment_valid_from"),
            "empanelment_valid_upto": record.get("empanelment_valid_upto"),
            "source": self.source_name,
            "source_url": self.source_url,
            "source_record_id": stable_id("rghs", name),
            "verification_status": "needs_review",
            "source_usage": "discovery",
            "source_text": record.get("source_text"),
        }

    def filter_location(self, record: dict[str, Any], location: Location) -> bool:
        if location.statewide:
            return True
        return location.city.casefold() in (record.get("name") or "").casefold()
