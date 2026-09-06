# Arogio Local Healthcare Scraper

A local, provenance-first Python toolkit for hospitals, doctors, and doctor/hospital relationships. It stores data in SQLite, preserves evidence, validates values, and exports import-shaped CSV/XLSX files.

## Current status

The shared pipeline is implemented: configuration, canonical Pydantic models, SQLite persistence, stable IDs, normalization, validation, deduplication helpers, rate-limited public HTTP fetching, template-aware exporters, and local logging.

The source adapter is intentionally fail-closed. No approved public source URL or parser contract was supplied, so the application will not silently choose or scrape a website. The owner-provided CSV templates are also not present in this workspace; copy them into `templates/` before using `--template`.

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
