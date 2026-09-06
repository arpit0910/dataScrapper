from pathlib import Path
from datetime import datetime, timezone

import typer

from .config import load_yaml, location, source as get_source
from .exporters import DOCTOR_COLUMNS, HOSPITAL_COLUMNS, assert_template_columns, export_rows
from .sources import Location, build_source
from .storage import Database
from .reports import DOCTOR_REPORT_FIELDS, HOSPITAL_REPORT_FIELDS, completeness
from .local_ai import OllamaExtractor
from .linking import link_payload, match_hospital
from .sources_icici import ICICILombardSource
from .sources_data_gov import DataGovHospitalAdapter
from .sources_rghs import RghsHospitalAdapter
from .sources_doctors import OfficialDoctorFileAdapter
import json

app = typer.Typer(no_args_is_help=True)
scrape_app = typer.Typer()
export_app = typer.Typer()
ingest_app = typer.Typer()
report_app = typer.Typer()
app.add_typer(scrape_app, name="scrape")
app.add_typer(export_app, name="export")
app.add_typer(report_app, name="report")
app.add_typer(ingest_app, name="ingest")
source_app = typer.Typer()
app.add_typer(source_app, name="source")


@app.command("source-list")
def source_list() -> None:
    """Show configured sources and whether their adapter is ready."""
    configured = load_yaml("sources.yaml").get("sources", {})
    for name, value in configured.items():
        enabled = bool(value.get("enabled", False))
        adapter_ready = name in {"approved_source", "icici_lombard_network"}
        configured_status = value.get("source_status", "access_review_pending")
        state = configured_status + "+payload" if name == "icici_lombard_network" and enabled else configured_status if configured_status != "access_review_pending" or not enabled else "adapter_pending"
        typer.echo(f"{name}: {state} ({', '.join(value.get('entity_types', []))})")


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


@scrape_app.command("hospitals")
def scrape_hospitals(city: str = typer.Option(...), state: str = typer.Option(...), source: str = typer.Option(...)) -> None:
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
    columns = HOSPITAL_COLUMNS if entity == "hospitals" else DOCTOR_COLUMNS
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
    output = Path(app_config.get("export", {}).get("path", "data/exports")) / city / f"{entity}_{city.casefold()}.{format.casefold()}"
    export_rows(records, columns, output, format)
    typer.echo(f"Exported {len(records)} {entity} row(s) to {output}.")


@export_app.command("hospitals")
def export_hospitals(city: str = typer.Option(...), format: str = typer.Option("xlsx"), template: Path | None = typer.Option(None), schema: str = typer.Option("import")) -> None:
    _export("hospitals", city, format, template, schema)


@export_app.command("doctors")
def export_doctors(city: str = typer.Option(...), format: str = typer.Option("xlsx"), template: Path | None = typer.Option(None), schema: str = typer.Option("import")) -> None:
    _export("doctors", city, format, template, schema)


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
