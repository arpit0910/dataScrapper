# Arogio Local Healthcare Scraper

A local, provenance-first Python toolkit for hospitals, doctors, and doctor/hospital relationships. It stores data in SQLite, preserves evidence, validates values, and exports import-shaped CSV/XLSX files.

## Current status

The shared pipeline is implemented: configuration, canonical Pydantic models, SQLite persistence, stable IDs, normalization, validation, deduplication helpers, rate-limited public HTTP fetching, template-aware exporters, and local logging.

One live source is enabled and working end to end:

- **`osm_overpass_health_facilities`** — OpenStreetMap healthcare facilities via the
  public Overpass API. Open data under **ODbL 1.0**, reusable with attribution,
  and queried through the endpoint OpenStreetMap publishes for programmatic use.
  India holds roughly 82,000 healthcare facilities, of which `amenity=hospital`
  alone exceeds the ten-thousand target.

Every other adapter remains fail-closed: no approved URL or parser contract was
supplied, so the application will not silently choose or scrape a website. The
owner-provided CSV templates are also not present in this workspace; copy them
into `templates/` before using `--template`.

### Collecting hospitals

```bash
python -m arogio scrape hospitals --state all --city all          # all of India
python -m arogio scrape hospitals --state Rajasthan --city all    # one state
python -m arogio scrape hospitals --state Rajasthan --city Jaipur # one city
python -m arogio scrape hospitals --state all --kinds hospital,clinic,doctors
```

The run is chunked by state, rate limited, and bounded by `--max-minutes` and
`--limit`. A failing chunk is reported and skipped rather than ending the run,
and requests rotate across public Overpass mirrors so one busy host does not
stall collection. Every raw response is persisted under `data/raw/`.

### Capturing everything a source returned

Each hospital record keeps the mapped fields *and* `osm_tags`, the complete
upstream tag set, so a mapping gap never silently loses a value. Beyond name and
location this includes facility capabilities (`facilities`: OPD, IPD, ICU,
ambulance, blood bank, operating theatre, pathology/radiology labs, ventilator,
delivery), regional-language names (`names_by_language`), staff counts, medical
system, operational status, payment methods, fax, and Wikidata/Wikipedia links.

An improved parser can be re-applied to past runs offline, because raw responses
are kept as evidence:

```bash
python -m arogio source reprocess-raw          # rebuild entities, no HTTP
```

### Optional enrichment

```bash
python -m arogio enrich wikidata               # free, no API key
```

Hospitals carrying a `wikidata` tag gain founding date, bed count, official
website, postal address and parent organisation. Enriched values live under
`wikidata_enrichment` with their own source URL, and only ever fill fields the
primary source left blank — a filled field is listed in `enriched_fields`.

### Collecting several named states in one run

```bash
python -m arogio scrape hospitals --states "Haryana,Punjab,Delhi"
```

Prefer this over one process per state: the endpoint allows only a couple of
concurrent slots, and a process per state re-runs the readiness probe each time,
spending that allowance on setup instead of data.

### Exporting

`--schema canonical` writes all 43 stored fields; `--schema import` (the default)
writes the narrow import-template shape.

```bash
python -m arogio export hospitals --city Rajasthan --schema canonical --format csv
python -m arogio report completeness --entity hospitals

# Everything, every field, one JSON file (nested values kept intact)
python -m arogio export dataset --output data/exports/hospitals_full.json
```

`export dataset` writes a single document with a `metadata` header (record
count, sources, licences, states covered, field list) and the full records. It
keeps nested values such as `facilities`, `names_by_language`, `osm_tags` and
`wikidata_enrichment`, which the flat column exports cannot represent.

Records collected from OpenStreetMap must keep the attribution
"© OpenStreetMap contributors" and the ODbL licence when redistributed; both are
stored on every row.

### Sources that need a key or permission

`data.gov.in`'s National Hospital Directory is free but its direct CSV link now
returns **HTTP 403**; it requires a registered (free) OGD API key. The remaining
catalogue entries stay disabled pending access review.

## Setup (Windows)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m arogio init
pytest -q
```

Unix/macOS: use `python3 -m venv .venv` and `source .venv/bin/activate`.

## Configuration

- `config/locations.yaml` contains location defaults. City and state can also be supplied on the CLI; Jaipur is not hard-coded in application logic.
- `config/sources.yaml` must contain an explicitly approved public source, its URL, supported entity types, timeout, retries, and rate limit. Keep `enabled: false` until approval and a parser are available.
- `config/validation.yaml` contains required fields and verification policy.
- `config/app.yaml` contains local database, raw-data, export, scraping, and logging paths.

Templates are the export contract. Their headers are compared exactly; missing or mismatched templates are errors and are never silently repaired.

## Optional local AI extraction

Ollama is supported as a local extraction aid. Configure its endpoint/model in `config/app.yaml`, then check it with:

```powershell
python -m arogio model-status
```

The model only extracts explicit page values into structured JSON. Deterministic validation, source evidence, location checks, and verification still decide what can be exported.

## Multiple sources

List source readiness with:

```powershell
python -m arogio source-list
```

The application is intentionally not an unrestricted crawler. Add each insurer, government directory, hospital network, or approved healthcare directory as its own adapter after confirming normal public access and terms. A source may contribute partial evidence, but missing fields stay blank and disagreements go to review. This allows many sources to be combined without treating low-quality or stale data as verified.

For a new source, add its configuration under `config/sources.yaml`, implement a separate adapter, preserve the raw response, add local fixtures/tests, run a 10–25 record trial, and only then enable it.

## Commands

```powershell
python -m arogio init
python -m arogio scrape hospitals --city Jaipur --state Rajasthan --source approved_source
python -m arogio scrape doctors --city Jaipur --state Rajasthan --source approved_source
python -m arogio export hospitals --city Jaipur --format xlsx --template templates/sample_hospitals_template.csv
python -m arogio export doctors --city Jaipur --format csv --template templates/sample_doctors_template.csv
```

Exports read stored canonical records from SQLite and preserve exact import columns. Supported formats are `xlsx`, `csv`, and `json`. A successful fetch is never treated as verification.

## Accuracy and compliance

Blank is preferred to an unproven value. Important values need field-level evidence, timestamps, and validation. Conflicts remain reviewable; `is_verified` is not blindly set. The HTTP helper only performs ordinary public requests with bounded retries and a rate limiter. It does not bypass authentication, CAPTCHA, robots restrictions, paywalls, or anti-bot controls. No cloud database, hosted AI, proxy, or scraping service is used.

Runtime data is kept under `data/` and logs under `logs/`; these paths are ignored by Git. Run `pytest` for the local test suite. Do not add another source until the first approved source and its controlled 10–25 record trial have been reviewed.
