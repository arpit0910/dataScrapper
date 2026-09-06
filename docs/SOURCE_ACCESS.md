# Source access and approval

Public visibility does not automatically grant permission for bulk retrieval, local storage, or redistribution. Arogio therefore separates source discovery, verification, and ingestion.

## Required lifecycle

1. Record the official owner and landing page in `config/sources.yaml` and `config/source_catalog.yaml`.
2. Complete the access request in `docs/SOURCE_ACCESS_REQUEST_TEMPLATE.md`.
3. Confirm the normal public machine-readable method, rate policy, retention, attribution, and reuse terms.
4. Keep `source_status` as `access_review_pending` or `permission_pending` until documented.
5. Implement a source-specific adapter and sanitized local fixtures.
6. Run parser tests and a 10–25 record review batch.
7. Set `source_status: approved`, `machine_access.automation_permitted: true`, and the relevant `approved_usage` flag only after review.
8. Suspend the source when access rules, schema, or data quality changes.

Production HTTP retrieval requires all three conditions:

```text
source_status == approved
automation_permitted == true
approved_usage.ingestion == true
```

Missing or unknown permissions fail closed. A source can remain available for fixture parsing or manual verification without being enabled for bulk ingestion.

## Prohibited

No login automation, CAPTCHA or anti-bot bypass, proxy/IP rotation, private or reverse-engineered APIs, token/cookie extraction, rate-limit bypass, patient records, claims, prescriptions, appointments, or other patient-level health data.

## Data pipeline

```text
raw response -> parsed record -> normalized record -> location check
-> source validation -> stable-ID matching -> deduplication
-> conflict detection -> field provenance -> review/acceptance -> export
```

Insurer lists establish network/empanelment evidence; they do not automatically prove current phone numbers, coordinates, specialties, doctors, or emergency availability.
