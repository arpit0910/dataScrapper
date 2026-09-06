# Source adapter status

| Source | Adapter | Mode | Hospitals | Doctors | Automated | File import | Verification | Blocker |
|---|---|---|---:|---:|---|---|---|---|
| ICICI Lombard network | `ICICILombardSource` | official payload import | Yes | No | No | Yes | No | live automation permission/endpoint pending |
| data.gov.in hospital directory | `DataGovHospitalAdapter` | official CSV import | Yes | No | No | Yes | Discovery only | shell download returned 403; use official downloaded CSV |
| RGHS | Not yet implemented | official PDF/web candidate | No | No | No | No | Pending | source contract/file needed |
| PM-JAY | Not yet implemented | official web/file candidate | No | No | No | No | Pending | source contract/file needed |
| ESIC | Not yet implemented | official PDF/web candidate | No | No | No | No | Pending | source contract/file needed |
| ABDM HFR/HPR | Prepared in catalog only | permission required | No | No | No | Planned | Planned | authorized export/API not configured |
| NMC / Rajasthan Medical Council / NABH | Verification candidates | verification only | No | No | No | No | Planned | permitted lookup/bulk-access contract needed |

Counts are capability/status indicators, not fabricated production record counts. Run `python -m arogio source status` for the current registry state.
