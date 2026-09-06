from pathlib import Path
from datetime import datetime, timezone

import typer

from .config import load_yaml, location, source as get_source
from .exporters import DOCTOR_COLUMNS, HOSPITAL_CANONICAL_COLUMNS, HOSPITAL_COLUMNS, assert_template_columns, export_rows
from .sources import Location, build_source
from .storage import Database
from .reports import DOCTOR_REPORT_FIELDS, HOSPITAL_REPORT_FIELDS, completeness
from .local_ai import OllamaExtractor
from .enrich_wikidata import batched, extract, fetch_entities, referenced_ids, resolve_labels
from .linking import link_payload, match_hospital
from .sources_icici import ICICILombardSource
from .sources_data_gov import DataGovHospitalAdapter
from .sources_rghs import RghsHospitalAdapter
from .sources_doctors import OfficialDoctorFileAdapter
from .sources_osm import KIND_FILTERS, STATE_BY_CODE, OsmOverpassHospitalAdapter
from .scraping import RateLimiter, post_with_failover
from .source_governance import assert_source_can_run
from .models import SourceUsage
import time
import json

app = typer.Typer(no_args_is_help=True)
scrape_app = typer.Typer()
export_app = typer.Typer()
ingest_app = typer.Typer()
report_app = typer.Typer()
enrich_app = typer.Typer()
app.add_typer(scrape_app, name="scrape")
app.add_typer(export_app, name="export")
app.add_typer(report_app, name="report")
app.add_typer(ingest_app, name="ingest")
app.add_typer(enrich_app, name="enrich")
source_app = typer.Typer()
app.add_typer(source_app, name="source")


@app.command("source-list")
def source_list() -> None:
    """Show configured sources and whether their adapter is ready."""
    configured = load_yaml("sources.yaml").get("sources", {})
    for name, value in configured.items():
        enabled = bool(value.get("enabled", False))
        status = value.get("source_status", "access_review_pending")
        try:
            build_source(name, value)
            adapter = "adapter:ready"
        except ValueError:
            adapter = "adapter:none"
        live = "live" if enabled and value.get("access_mode") == "automated_public" else "file-import" if value.get("file_import") else "inactive"
        typer.echo(f"{name}: {status} [{adapter}] [{live}] ({', '.join(value.get('entity_types', []))})")


@source_app.command("status")
def source_status() -> None:
    source_list()


@source_app.command("import-file")
def source_import_file(source_name: str, input_file: Path = typer.Argument(..., exists=True, readable=True), city: str = typer.Option(...), state: str = typer.Option(...), limit: int = typer.Option(1000, min=1, max=100000)) -> None:
    """Parse an officially downloaded source file without performing HTTP retrieval."""
    if source_name not in {"data_gov_in_hospital_directory", "rajasthan_rghs_empanelled_hospitals"}:
        raise typer.BadParameter("File adapters are available for data_gov_in_hospital_directory and rajasthan_rghs_empanelled_hospitals")
    target = location(city, state)
    statewide = city.casefold() in {"all", state.casefold()}
    location_value = Location(target["city"], target["state"], target["country"], tuple(target.get("pincode_prefixes", [])), statewide)
    adapter = DataGovHospitalAdapter() if source_name == "data_gov_in_hospital_directory" else RghsHospitalAdapter()
    records = adapter.parse_file(input_file)
    db_config = load_yaml("app.yaml")
    db = Database(db_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    raw = input_file.read_bytes()
    run_id = f"{source_name}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    raw_path = db.save_raw_snapshot(source_name, run_id, raw.decode("utf-8", errors="replace"), input_file.suffix or ".csv")
    accepted = 0
    for record in records:
        normalized = adapter.normalize_source_record(record, location_value)
        if source_name == "data_gov_in_hospital_directory" and not adapter.filter_location(normalized, location_value):
            continue
        if source_name == "rajasthan_rghs_empanelled_hospitals" and not adapter.filter_location(normalized, location_value):
            continue
        # The source may only provide district + pincode.  Once that bounded
        # fallback passes, label the canonical row with the requested target
        # city while retaining the original district and source fields.
        normalized["city"] = target["city"]
        db.save_entity("hospital", normalized["hospital_id"], target["city"], normalized)
        accepted += 1
        if accepted >= limit:
            break
    typer.echo(f"{source_name}: records={len(records)}; {city} matches={accepted}; status=needs_review; raw={raw_path}")


@source_app.command("import-doctors")
def source_import_doctors(source_name: str, input_file: Path = typer.Argument(..., exists=True, readable=True), city: str = typer.Option(...), state: str = typer.Option(...), limit: int = typer.Option(100000, min=1, max=1000000)) -> None:
    """Import an officially supplied doctor CSV/XLSX export."""
    configured = load_yaml("sources.yaml").get("sources", {}).get(source_name)
    if not configured:
        raise typer.BadParameter(f"Unknown source: {source_name}")
    target = location(city, state)
    location_value = Location(target["city"], target["state"], target["country"], tuple(target.get("pincode_prefixes", [])), city.casefold() in {"all", state.casefold()})
    adapter = OfficialDoctorFileAdapter(source_name, configured.get("landing_page_url", configured.get("page_url", "")))
    records = adapter.parse_file(input_file)
    db_config = load_yaml("app.yaml")
    db = Database(db_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    raw = input_file.read_bytes()
    run_id = f"{source_name}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    raw_path = db.save_raw_snapshot(source_name, run_id, raw.decode("utf-8", errors="replace"), input_file.suffix or ".csv")
    accepted = 0
    for record in records:
        normalized = adapter.normalize_source_record(record, location_value)
        if not adapter.filter_location(normalized, location_value):
            continue
        if location_value.statewide:
            normalized["city"] = normalized.get("city") or target["state"]
        db.save_entity("doctor", normalized["doctor_id"], normalized["city"], normalized)
        hospital = match_hospital(normalized, db.entities("hospital"))
        link = link_payload(normalized, hospital)
        db.save_link(link["doctor_hospital_link_id"], normalized["doctor_id"], link["hospital_id"], link)
        accepted += 1
        if accepted >= limit:
            break
    typer.echo(f"{source_name}: records={len(records)}; {city} matches={accepted}; status=needs_review; raw={raw_path}")


@source_app.command("reprocess-raw")
def source_reprocess_raw(
    source_name: str = typer.Option("osm_overpass_health_facilities", "--source"),
    raw_root: Path = typer.Option(Path("data/raw"), "--raw-root"),
) -> None:
    """Rebuild stored entities from saved raw responses, without any HTTP.

    Raw snapshots are the evidence of what a source actually returned, so an
    improved parser can be applied to past runs offline instead of re-fetching
    and re-loading a public API.
    """
    configured = load_yaml("sources.yaml").get("sources", {}).get(source_name)
    if not configured:
        raise typer.BadParameter(f"Unknown source: {source_name}")
    adapter = build_source(source_name, configured)
    if not isinstance(adapter, OsmOverpassHospitalAdapter):
        raise typer.BadParameter(f"Reprocessing is implemented for the Overpass adapter, not {source_name}.")

    snapshots = sorted((raw_root / source_name).rglob("response_001.json"))
    if not snapshots:
        raise typer.BadParameter(f"No raw snapshots found under {raw_root / source_name}")

    app_config = load_yaml("app.yaml")
    db = Database(app_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    seen: set[str] = set()
    total_elements = accepted = 0
    for snapshot in snapshots:
        # The run directory carries the state code the chunk was fetched for.
        code = snapshot.parent.name.rsplit("-", 2)[-2:]
        code = "-".join(code) if len(code) == 2 else ""
        state_name = STATE_BY_CODE.get(code)
        if not state_name:
            typer.echo(f"[skip] {snapshot.parent.name}: no state code in run id")
            continue
        try:
            records = adapter.parse(snapshot.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            typer.echo(f"[skip] {snapshot.parent.name}: unreadable snapshot")
            continue
        chunk_location = Location("all", state_name, "India", (), True)
        batch: list[tuple[str, str, dict]] = []
        for record in records:
            normalized = adapter.normalize_source_record(record, chunk_location)
            if not adapter.filter_location(normalized, chunk_location):
                continue
            if normalized["hospital_id"] in seen:
                continue
            seen.add(normalized["hospital_id"])
            city_value = normalized.get("city") or normalized.get("district") or state_name
            normalized["city"] = city_value
            batch.append((normalized["hospital_id"], city_value, normalized))
        db.save_entities("hospital", batch)
        total_elements += len(records)
        accepted += len(batch)
        typer.echo(f"[{state_name:<38}] elements={len(records):>6} new={len(batch):>6} total={accepted:>6}")
    typer.echo(f"\nReprocessed {len(snapshots)} snapshot(s): elements={total_elements} unique hospitals={accepted}")
    typer.echo(f"Stored hospital rows in database: {db.count('hospital')}")


@source_app.command("link-doctors")
def source_link_doctors(city: str | None = typer.Option(None), state: str | None = typer.Option(None)) -> None:
    """Backfill conservative doctor-to-hospital links for imported records."""
    config = load_yaml("app.yaml")
    db = Database(config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    doctors = db.entities("doctor", city)
    if state:
        doctors = [doctor for doctor in doctors if (doctor.get("state") or "").casefold() == state.casefold()]
    hospitals = db.entities("hospital")
    matched = 0
    for doctor in doctors:
        hospital = match_hospital(doctor, hospitals)
        link = link_payload(doctor, hospital)
        db.save_link(link["doctor_hospital_link_id"], doctor["doctor_id"], link["hospital_id"], link)
        matched += bool(hospital)
    typer.echo(f"Doctor links: processed={len(doctors)}; connected={matched}; unresolved={len(doctors) - matched}")


@enrich_app.command("wikidata")
def enrich_wikidata_command(
    limit: int = typer.Option(5000, min=1, help="Maximum hospitals to enrich"),
    requests_per_minute: int = typer.Option(30, min=1, max=60),
) -> None:
    """Add public Wikidata facts to hospitals that carry a wikidata reference.

    Enriched values are stored under `wikidata_enrichment` with the source
    recorded, so they stay distinguishable from what the primary source said.
    """
    app_config = load_yaml("app.yaml")
    db = Database(app_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    rows = [row for row in db.entities("hospital") if row.get("wikidata")]
    if not rows:
        typer.echo("No hospitals carry a wikidata reference; nothing to enrich.")
        return
    rows = rows[:limit]
    by_qid: dict[str, list[dict]] = {}
    for row in rows:
        by_qid.setdefault(str(row["wikidata"]).strip(), []).append(row)
    qids = sorted(by_qid)
    typer.echo(f"Enriching {len(rows)} hospital(s) across {len(qids)} Wikidata entities...")

    limiter = RateLimiter(requests_per_minute=requests_per_minute)
    enrichments: dict[str, dict] = {}
    failures = 0
    for index, batch in enumerate(batched(qids), start=1):
        try:
            entities = fetch_entities(batch, limiter)
        except Exception as exc:  # noqa: BLE001 - a failed batch must not end the pass
            failures += 1
            typer.echo(f"[batch {index}] failed ({type(exc).__name__})")
            continue
        for qid, entity in entities.items():
            if "missing" in entity:
                continue
            payload = extract(entity)
            if payload:
                enrichments[qid] = payload
        typer.echo(f"[batch {index}] {len(batch)} ids -> {len(enrichments)} enriched so far")

    pending = referenced_ids(enrichments)
    labels: dict[str, str] = {}
    for batch in batched(pending):
        try:
            for qid, entity in fetch_entities(batch, limiter).items():
                label = (entity.get("labels", {}) or {}).get("en", {}).get("value")
                if label:
                    labels[qid] = label
        except Exception:  # noqa: BLE001 - unresolved ids simply stay as Q-ids
            continue
    resolve_labels(enrichments, labels)

    updated = 0
    batch_rows: list[tuple[str, str, dict]] = []
    for qid, payload in enrichments.items():
        for row in by_qid.get(qid, []):
            row["wikidata_enrichment"] = {**payload, "source": "wikidata", "wikidata_id": qid,
                                          "source_url": f"https://www.wikidata.org/wiki/{qid}"}
            # Fill only genuinely empty fields; never overwrite the primary source.
            for field in ("website", "email", "official_name"):
                if not row.get(field) and payload.get(field):
                    value = payload[field]
                    row[field] = value[0] if isinstance(value, list) else value
                    row.setdefault("enriched_fields", []).append(field)
            # A row with no addr:city was grouped under its state as a fallback;
            # Wikidata's administrative area is a better answer when present.
            if not row.get("source_city") and payload.get("administrative_area"):
                area = payload["administrative_area"]
                area = area[0] if isinstance(area, list) else area
                if isinstance(area, str) and not area.startswith("Q"):
                    row["city"] = area
                    row.setdefault("enriched_fields", []).append("city")
            batch_rows.append((row["hospital_id"], row.get("city") or "", row))
            updated += 1
    db.save_entities("hospital", batch_rows)
    typer.echo(f"\nEnriched {updated} hospital row(s) from {len(enrichments)} Wikidata entities "
               f"({len(labels)} referenced labels resolved, {failures} failed batch(es)).")


@app.command("model-status")
def model_status() -> None:
    config = load_yaml("app.yaml").get("local_model", {})
    model = OllamaExtractor(config.get("model", "qwen2.5:3b"), config.get("endpoint", "http://127.0.0.1:11434"))
    typer.echo(f"Ollama endpoint: {model.endpoint}")
    typer.echo(f"Model: {model.model}")
    if not model.is_available():
        typer.echo("Status: unavailable (Ollama is not reachable)")
        raise typer.Exit(code=1)
    if not model.model_available():
        typer.echo("Status: unavailable (configured model is not installed)")
        raise typer.Exit(code=1)
    try:
        result = model.smoke_test()
    except Exception as exc:
        typer.echo(f"Status: unavailable (inference failed: {exc})")
        raise typer.Exit(code=1) from exc
    typer.echo(f"Status: working; smoke test: {result}")


@app.command()
def init() -> None:
    config = load_yaml("app.yaml")
    Database(config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db")).initialize()
    typer.echo("Initialized local SQLite database.")


def _scrape(entity: str, city: str, state: str, source: str) -> None:
    configured = load_yaml("sources.yaml").get("sources", {}).get(source)
    if not configured:
        raise typer.BadParameter(f"Unknown source: {source}")
    target = location(city, state)
    adapter = build_source(source, configured)
    if not adapter.supports("hospital" if entity == "hospitals" else "doctor"):
        raise typer.BadParameter(
            f"Source '{source}' is disabled or does not support {entity}. "
            "Configure an explicitly approved public source in config/sources.yaml."
        )
    adapter.discover(Location(target["city"], target["state"], target["country"], tuple(target.get("pincode_prefixes", []))))


def _run_overpass(
    city: str,
    state: str,
    source: str,
    kinds: tuple[str, ...],
    limit: int,
    max_minutes: float,
    save_raw: bool,
    states: tuple[str, ...] = (),
) -> None:
    """Collect live OpenStreetMap healthcare facilities under a time budget.

    Each state is a separate bounded request.  A failing chunk is reported and
    skipped so that one slow or oversized area cannot abandon the whole run.
    """
    configured = load_yaml("sources.yaml").get("sources", {}).get(source)
    if not configured:
        raise typer.BadParameter(f"Unknown source: {source}")
    assert_source_can_run(configured, SourceUsage.INGESTION)
    adapter = build_source(source, configured)
    if not isinstance(adapter, OsmOverpassHospitalAdapter):
        raise typer.BadParameter(f"Source '{source}' is not a live Overpass adapter.")

    target = location(city, state)
    statewide = city.casefold() in {"all", "", state.casefold(), "india"}
    target_location = Location(
        target["city"], target["state"], target.get("country", "India"),
        tuple(target.get("pincode_prefixes", [])), statewide,
    )

    app_config = load_yaml("app.yaml")
    db = Database(app_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    limiter = RateLimiter(requests_per_minute=int(configured.get("requests_per_minute", 20)))
    timeout = int(configured.get("timeout_seconds", 300))
    retries = int(configured.get("retries", 3))

    # Prove each mirror actually serves this region before trusting a long run
    # to it; a regional instance answers 200 with no elements for foreign areas.
    live_endpoints: list[str] = []
    for endpoint in adapter.endpoints:
        try:
            # A probe is a tiny count query, so it gets a short timeout: a
            # mirror too slow to answer it is too slow to collect from.  One
            # retry still absorbs a transient throttle.
            _, probe_body, _ = post_with_failover([endpoint], adapter.probe_query(20), limiter, 20, 1)
            count = adapter.probe_count(probe_body)
        except Exception as exc:  # noqa: BLE001 - an unusable mirror is simply skipped
            typer.echo(f"[probe] {endpoint} unusable ({type(exc).__name__})")
            continue
        if count > 0:
            live_endpoints.append(endpoint)
            typer.echo(f"[probe] {endpoint} ok (probe returned {count})")
        else:
            typer.echo(f"[probe] {endpoint} skipped: serves no data for this region")
    if not live_endpoints:
        raise typer.BadParameter("No configured Overpass mirror returned data for this region.")
    adapter.endpoints = live_endpoints

    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = f"{source}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    chunks = adapter.discover(target_location, states or None)
    seen: set[str] = set()
    total_elements = accepted = skipped = 0
    failures: list[str] = []

    typer.echo(f"run={run_id} chunks={len(chunks)} kinds={','.join(kinds)} limit={limit} budget={max_minutes:g}min")

    for index, (code, state_name) in enumerate(chunks, start=1):
        elapsed = (time.monotonic() - started) / 60
        if elapsed >= max_minutes:
            typer.echo(f"[budget] stopping after {elapsed:.1f} min ({index - 1}/{len(chunks)} chunks done)")
            break
        if accepted >= limit:
            typer.echo(f"[limit] reached {accepted} records")
            break

        chunk_location = Location(
            target_location.city, state_name if statewide else target_location.state,
            target_location.country, target_location.pincode_prefixes, statewide,
        )
        query = adapter.build_query(code, kinds, timeout)
        chunk_deadline = started + max_minutes * 60
        try:
            status, body, endpoint = post_with_failover(
                adapter.endpoints, query, limiter, timeout, retries, deadline=chunk_deadline
            )
        except Exception as exc:  # noqa: BLE001 - one bad chunk must not end the run
            failures.append(f"{code}: {exc}")
            typer.echo(f"[{index:>2}/{len(chunks)}] {state_name:<38} FAILED ({exc})")
            continue

        try:
            records = adapter.parse(body)
        except json.JSONDecodeError as exc:
            failures.append(f"{code}: invalid JSON")
            typer.echo(f"[{index:>2}/{len(chunks)}] {state_name:<38} FAILED (invalid JSON: {exc})")
            continue

        if save_raw:
            db.save_raw_snapshot(source, f"{run_id}-{code}", body, ".json")
        db.save_observation("hospital", source, endpoint, datetime.now(timezone.utc).isoformat(), status, query)

        batch: list[tuple[str, str, dict]] = []
        for record in records:
            normalized = adapter.normalize_source_record(record, chunk_location)
            if not adapter.filter_location(normalized, chunk_location):
                skipped += 1
                continue
            if normalized["hospital_id"] in seen:
                continue
            seen.add(normalized["hospital_id"])
            city_value = normalized.get("city") or normalized.get("district") or state_name
            normalized["city"] = city_value
            batch.append((normalized["hospital_id"], city_value, normalized))
            if len(batch) + accepted >= limit:
                break
        db.save_entities("hospital", batch)
        total_elements += len(records)
        accepted += len(batch)
        typer.echo(
            f"[{index:>2}/{len(chunks)}] {state_name:<38} fetched={len(records):>6} kept={len(batch):>6} total={accepted:>6}"
        )

    duration = time.monotonic() - started
    summary = {
        "run_id": run_id, "source": source, "kinds": list(kinds), "chunks": len(chunks),
        "elements": total_elements, "accepted": accepted, "skipped": skipped,
        "failures": failures, "duration_seconds": round(duration, 1),
        "license": configured.get("license"), "attribution": configured.get("attribution"),
    }
    db.save_run(run_id, source, started_at, datetime.now(timezone.utc).isoformat(), summary)
    typer.echo(
        f"\nDone in {duration / 60:.1f} min: elements={total_elements} accepted={accepted} "
        f"skipped_out_of_area={skipped} failed_chunks={len(failures)}"
    )
    typer.echo(f"Stored hospital rows in database: {db.count('hospital')}")
    typer.echo(f"Attribution: {configured.get('attribution')} ({configured.get('license')})")


@scrape_app.command("hospitals")
def scrape_hospitals(
    city: str = typer.Option("all", help="City name, or 'all' for the whole state/country"),
    state: str = typer.Option("all", help="State name or ISO code, or 'all' for all of India"),
    source: str = typer.Option("osm_overpass_health_facilities", help="Configured source key"),
    kinds: str = typer.Option("hospital", help="Comma-separated: hospital,clinic,doctors"),
    limit: int = typer.Option(50000, min=1, help="Stop after this many accepted records"),
    max_minutes: float = typer.Option(15.0, help="Wall-clock budget for the run"),
    save_raw: bool = typer.Option(True, help="Persist each raw API response"),
    states: str | None = typer.Option(None, help="Comma-separated states to collect in one run"),
) -> None:
    """Collect hospitals from a live approved source."""
    selected = tuple(kind.strip() for kind in kinds.split(",") if kind.strip())
    unknown = [kind for kind in selected if kind not in KIND_FILTERS]
    if unknown:
        raise typer.BadParameter(f"Unknown kinds: {', '.join(unknown)}. Choose from hospital, clinic, doctors.")
    configured = load_yaml("sources.yaml").get("sources", {}).get(source, {})
    if configured.get("access_mode") == "automated_public":
        chosen = tuple(part.strip() for part in states.split(",") if part.strip()) if states else ()
        _run_overpass(city, state, source, selected, limit, max_minutes, save_raw, chosen)
    else:
        _scrape("hospitals", city, state, source)


@scrape_app.command("doctors")
def scrape_doctors(city: str = typer.Option(...), state: str = typer.Option(...), source: str = typer.Option(...)) -> None:
    _scrape("doctors", city, state, source)


@ingest_app.command("icici-hospitals")
def ingest_icici_hospitals(input_file: Path = typer.Option(..., "--input", "--input-file", exists=True, readable=True), city: str = typer.Option(...), state: str = typer.Option(...), limit: int = typer.Option(25, min=1, max=1000)) -> None:
    """Ingest an owner-supplied ICICI JSON response as a controlled local batch."""
    target = location(city, state)
    try:
        payload = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON: {exc}") from exc
    adapter = ICICILombardSource()
    location_value = Location(target["city"], target["state"], target["country"], tuple(target.get("pincode_prefixes", [])), city.casefold() in {"all", state.casefold()})
    records = adapter.parse(payload)
    db_config = load_yaml("app.yaml")
    db = Database(db_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    db.save_observation("hospital", adapter.source_name, "https://www.icicilombard.com/cashless-hospitals", datetime.now(timezone.utc).isoformat(), 200, input_file.read_text(encoding="utf-8"))
    accepted = 0
    for raw_record in records:
        if accepted >= limit:
            break
        normalized = adapter.normalize_source_record(raw_record, location_value)
        if not normalized["is_within_target_location"]:
            continue
        db.save_entity("hospital", normalized["hospital_id"], target["city"], normalized)
        accepted += 1
    typer.echo(f"ICICI payload records: {len(records)}; accepted Jaipur-area batch: {accepted}; status: needs_review")


def _export(entity: str, city: str, format: str, template: Path | None, schema: str) -> None:
    if schema not in {"import", "canonical"}:
        raise typer.BadParameter("schema must be import or canonical")
    if format.casefold() not in {"xlsx", "csv", "json"}:
        raise typer.BadParameter("format must be xlsx, csv, or json")
    if entity == "hospitals":
        columns = HOSPITAL_CANONICAL_COLUMNS if schema == "canonical" else HOSPITAL_COLUMNS
    else:
        columns = DOCTOR_COLUMNS
    if template:
        try:
            assert_template_columns(template, columns)
        except (FileNotFoundError, ValueError) as exc:
            raise typer.BadParameter(str(exc)) from exc
    app_config = load_yaml("app.yaml")
    db = Database(app_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    entity_type = "hospital" if entity == "hospitals" else "doctor"
    if city.casefold() == "rajasthan":
        records = [row for row in db.entities(entity_type) if (row.get("state") or "").casefold() == "rajasthan"]
    else:
        records = db.entities(entity_type, city)
    if entity == "doctors":
        links = {link.get("doctor_id"): link for link in db.links()}
        records = [{**record, **links.get(record.get("doctor_id"), {})} for record in records]
    output = Path(app_config.get("export", {}).get("path", "data/exports")) / city / f"{entity}_{city.casefold()}_{schema}.{format.casefold()}"
    export_rows(records, columns, output, format)
    typer.echo(f"Exported {len(records)} {entity} row(s) to {output}.")


@export_app.command("hospitals")
def export_hospitals(city: str = typer.Option(...), format: str = typer.Option("xlsx"), template: Path | None = typer.Option(None), schema: str = typer.Option("import")) -> None:
    _export("hospitals", city, format, template, schema)


@export_app.command("doctors")
def export_doctors(city: str = typer.Option(...), format: str = typer.Option("xlsx"), template: Path | None = typer.Option(None), schema: str = typer.Option("import")) -> None:
    _export("doctors", city, format, template, schema)


@export_app.command("dataset")
def export_dataset(
    output: Path = typer.Option(Path("data/exports/hospitals_full.json"), "--output", "-o"),
    entity: str = typer.Option("hospitals", help="hospitals or doctors"),
    city: str | None = typer.Option(None, help="Restrict to one city"),
    state: str | None = typer.Option(None, help="Restrict to one state"),
    indent: int | None = typer.Option(2, help="JSON indent; use 0 for a compact file"),
) -> None:
    """Write every stored field for every record into one JSON file.

    Unlike the column exports, this keeps nested values (facilities, language
    names, the complete upstream tag set, and any enrichment) intact, so the
    file is a faithful dump rather than a flattened view.
    """
    if entity not in {"hospitals", "doctors"}:
        raise typer.BadParameter("entity must be hospitals or doctors")
    entity_type = "hospital" if entity == "hospitals" else "doctor"
    app_config = load_yaml("app.yaml")
    db = Database(app_config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    db.initialize()
    records = db.entities(entity_type, city)
    if state:
        records = [r for r in records if (r.get("state") or "").casefold() == state.casefold()]
    if entity == "doctors":
        links = {link.get("doctor_id"): link for link in db.links()}
        records = [{**r, **links.get(r.get("doctor_id"), {})} for r in records]

    sources = sorted({r.get("source") for r in records if r.get("source")})
    licenses = sorted({r.get("license") for r in records if r.get("license")})
    attributions = sorted({r.get("attribution") for r in records if r.get("attribution")})
    states = sorted({r.get("state") for r in records if r.get("state")})
    field_names = sorted({key for record in records for key in record})
    document = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entity_type": entity_type,
            "record_count": len(records),
            "sources": sources,
            "licenses": licenses,
            "attribution": attributions,
            "states_covered": states,
            "state_count": len(states),
            "fields": field_names,
            "enriched_count": sum(1 for r in records if r.get("wikidata_enrichment")),
            "filters": {"city": city, "state": state},
            "verification_note": "Values are collected evidence, not verified facts; verification_status is per record.",
        },
        entity: records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=indent or None, default=str),
        encoding="utf-8",
    )
    size_mb = output.stat().st_size / (1024 * 1024)
    typer.echo(f"Wrote {len(records):,} {entity} record(s) with {len(field_names)} distinct field(s) to {output} ({size_mb:.1f} MB).")
    if attributions:
        typer.echo(f"Attribution: {'; '.join(attributions)} ({', '.join(licenses)})")


@report_app.command("completeness")
def report_completeness(entity: str = typer.Option(..., help="hospitals or doctors"), city: str | None = typer.Option(None)) -> None:
    if entity not in {"hospitals", "doctors"}:
        raise typer.BadParameter("entity must be hospitals or doctors")
    config = load_yaml("app.yaml")
    db = Database(config.get("storage", {}).get("sqlite_path", "data/arogio_scraper.db"))
    entity_type = "hospital" if entity == "hospitals" else "doctor"
    if city and city.casefold() == "rajasthan":
        records = [row for row in db.entities(entity_type) if (row.get("state") or "").casefold() == "rajasthan"]
    else:
        records = db.entities(entity_type, city)
    fields = HOSPITAL_REPORT_FIELDS if entity == "hospitals" else DOCTOR_REPORT_FIELDS
    for field, values in completeness(records, fields).items():
        typer.echo(f"{field}: {values['percent']}% ({values['populated']}/{values['total']})")
