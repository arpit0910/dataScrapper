import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


class Database:
    def __init__(self, path: str | Path = "data/arogio_scraper.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS scrape_runs (run_id TEXT PRIMARY KEY, entity_type TEXT, source TEXT, city TEXT, state TEXT, started_at TEXT, completed_at TEXT, summary TEXT);
        CREATE TABLE IF NOT EXISTS source_observations (observation_id INTEGER PRIMARY KEY, entity_type TEXT, source TEXT, source_url TEXT, fetched_at TEXT, http_status INTEGER, content_hash TEXT, raw_json TEXT);
        CREATE TABLE IF NOT EXISTS entities (entity_type TEXT, entity_id TEXT PRIMARY KEY, city TEXT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS field_evidence (entity_type TEXT, entity_id TEXT, field_name TEXT, value TEXT, source TEXT, source_url TEXT, observed_at TEXT, confidence REAL);
        CREATE TABLE IF NOT EXISTS conflicts (entity_type TEXT, entity_id TEXT, field_name TEXT, existing_value TEXT, candidate_value TEXT, existing_source TEXT, candidate_source TEXT, resolution TEXT, requires_review INTEGER);
        CREATE TABLE IF NOT EXISTS doctor_hospital_links (link_id TEXT PRIMARY KEY, doctor_id TEXT, hospital_id TEXT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_records (source_key TEXT, source_record_id TEXT, retrieved_at TEXT, raw_reference TEXT, payload TEXT NOT NULL, PRIMARY KEY(source_key, source_record_id));
        CREATE TABLE IF NOT EXISTS verification_events (event_id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT, field_name TEXT, source_key TEXT, status TEXT, verified_at TEXT, notes TEXT);
        CREATE TABLE IF NOT EXISTS source_run_logs (run_id TEXT PRIMARY KEY, source_key TEXT, started_at TEXT, completed_at TEXT, summary TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS review_batches (batch_id TEXT PRIMARY KEY, source_key TEXT, created_at TEXT, status TEXT, payload TEXT NOT NULL);
        """)
        self.connection.commit()

    def save_entity(self, entity_type: str, entity_id: str, city: str, payload: dict[str, Any]) -> None:
        self.connection.execute("INSERT OR REPLACE INTO entities VALUES (?, ?, ?, ?)", (entity_type, entity_id, city, json.dumps(payload, default=str)))
        self.connection.commit()

    def save_observation(self, entity_type: str, source: str, source_url: str, fetched_at: str, status: int, raw: str) -> None:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.connection.execute("INSERT INTO source_observations(entity_type, source, source_url, fetched_at, http_status, content_hash, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)", (entity_type, source, source_url, fetched_at, status, digest, raw))
        self.connection.commit()

    def save_raw_snapshot(self, source_key: str, run_id: str, raw: str, extension: str = "json", root: str | Path = "data/raw") -> Path:
        now = datetime.now(timezone.utc)
        directory = Path(root) / source_key / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}" / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"response_001.{extension.lstrip('.') }"
        path.write_text(raw, encoding="utf-8")
        return path

    def save_source_record(self, source_key: str, source_record_id: str, retrieved_at: str, raw_reference: str, payload: dict[str, Any]) -> None:
        self.connection.execute("INSERT OR REPLACE INTO source_records VALUES (?, ?, ?, ?, ?)", (source_key, source_record_id, retrieved_at, raw_reference, json.dumps(payload, default=str)))
        self.connection.commit()

    def save_run(self, run_id: str, source_key: str, started_at: str, completed_at: str, summary: dict[str, Any]) -> None:
        self.connection.execute("INSERT OR REPLACE INTO source_run_logs VALUES (?, ?, ?, ?, ?)", (run_id, source_key, started_at, completed_at, json.dumps(summary, default=str)))
        self.connection.commit()

    def save_evidence(self, entity_type: str, entity_id: str, field_name: str, value: Any, source: str, source_url: str, observed_at: str, confidence: float) -> None:
        self.connection.execute(
            "INSERT INTO field_evidence(entity_type, entity_id, field_name, value, source, source_url, observed_at, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, field_name, json.dumps(value, default=str), source, source_url, observed_at, confidence),
        )
        self.connection.commit()

    def save_conflict(self, entity_type: str, entity_id: str, field_name: str, existing_value: Any, candidate_value: Any, existing_source: str, candidate_source: str, resolution: str | None = None, requires_review: bool = True) -> None:
        self.connection.execute(
            "INSERT INTO conflicts(entity_type, entity_id, field_name, existing_value, candidate_value, existing_source, candidate_source, resolution, requires_review) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, field_name, json.dumps(existing_value, default=str), json.dumps(candidate_value, default=str), existing_source, candidate_source, resolution, int(requires_review)),
        )
        self.connection.commit()

    def entities(self, entity_type: str, city: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        query = "SELECT payload FROM entities WHERE entity_type = ?"
        params: list[Any] = [entity_type]
        if city:
            query += " AND lower(city) = lower(?)"
            params.append(city)
        rows = self.connection.execute(query, params).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_link(self, link_id: str, doctor_id: str, hospital_id: str | None, payload: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO doctor_hospital_links(link_id, doctor_id, hospital_id, payload) VALUES (?, ?, ?, ?)",
            (link_id, doctor_id, hospital_id, json.dumps(payload, default=str)),
        )
        self.connection.commit()

    def links(self, doctor_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT payload FROM doctor_hospital_links"
        params: list[Any] = []
        if doctor_id:
            query += " WHERE doctor_id = ?"
            params.append(doctor_id)
        return [json.loads(row["payload"]) for row in self.connection.execute(query, params).fetchall()]

    def close(self) -> None:
        self.connection.close()
