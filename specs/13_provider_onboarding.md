# 13 — Bounded provider onboarding

> Current storage update: the redundant 2018 sample has been physically removed. References below to preserving the pilot describe the original implementation. Full-history reads/replays now stand alone; [removal details](../docs/alfred_sample_removal.md).

Status: implemented for **one fixed ALFRED CES0500000003 / 2018 pilot**, not a general
provider framework. The user selected any existing ALFRED series and defined live capability
as an API that can be queried daily, without a trading decision-clock requirement.
[Actual results](../docs/alfred_onboarding_report.md) distinguish these completed capabilities
from future pipeline work.

## Additive contract and exact locations

The closed [onboarding schema](schemas/onboarding.schema.json) adds four record types with
its own profile 0.1.0; existing experiment0.1 and platform0.2 schemas remain unchanged.
Each record has schema_version, record_type, id, version and body. References use exact
id/version/content_sha256. These records hash canonical sorted-key compact ASCII JSON;
the record content digest covers the full record. Their IDs are prefix + SHA-256 of the
canonical envelope without id. Definition/display and snapshot projection rules for
platform0.2 continue to follow [01](01_canonical_objects.md).

| Record | Location | Required meaning |
| --- | --- | --- |
| provider_contract | `definitions/providers/<id>/<version>.json` | Native series identity, official endpoints/docs, units/frequency/seasonality, availability policy and explicit vintage/live limitations |
| ingestion_receipt | `storage/catalog/ingestions/records/<id>.json` | Sanitized request, retrieval times, status/headers, payload hash/count, original source provenance, completeness and errors |
| onboarding_evidence | `storage/catalog/onboarding/evidence/<id>.json` | Typed immutable reference to a content-addressed JSON evidence document |
| capability_assessment | `storage/catalog/readiness/records/<id>.json` | Exact dataset/provider/snapshot/policy/code/evidence bindings, scope, mandatory checks, decision and limitations |

The full run's completion marker is `storage/catalog/onboarding/runs/ONBOARDING_<hash>.json`.
It is an operational index of the validated package, not a new scientific identity or editable
certificate. Its name hashes its canonical entire content. Standard dataset/source-view/policy
registrations, raw snapshots, lineage, implementation and locator records use platform0.2 paths.
Exact original bytes, JSON evidence and code/environment artifacts use the existing payload
store. These pilot raw observations retain native JSON, not feature/target Parquet encoding.

## Scope, acceptance and failure

Historical replay means reconstructing the ALFRED archive's information state using native
vintage-date labels for the selected 2018 reference months. Observation date, vintage date,
retrieval time and import time remain separate. No exact UTC availability is manufactured.
The old plus-one-day-at-12-UTC convention remains provenance, not a measured release time.
The source contract makes this date precision explicit even though the dataset schema names
the availability column `vintage_date`. It is a date token, not a UTC timestamp; a later
feature materializer must resolve an approved time-availability policy before accepting it.

Live capability is `live_api_daily_pull`; it is intentionally distinct from full
`live_generation`. Its evidence is official API documentation plus authenticated metadata
and latest-observation pulls. A monthly dataset can be queried daily without changing daily.
No uptime or deadline guarantee is implied. An assessment is scoped to its captured evidence;
there is no blanket or permanent provider approval and no automatic schedule.

The bounded parser requires output_type3 native units, a complete initial page, unique
reference periods, valid series/date columns and finite decimal-or-missing values. It preserves
every revision and deletion. The command checks all 12 requested months, archived/current
value parity and two independent historical as-of responses. A latest-five probe is marked
partial, not silently treated as complete history. Missing legacy status/start time stays null.

Raw/source changes, incomplete pages, reference conflicts, failed network requests or integrity
errors cannot produce a completed ready package. Network failures retain sanitized acquisition
receipts without credential-bearing exception URLs; incomplete runs may leave immutable orphan
artifacts and temporary evidence, but no completion marker. Recovery/manual review is required;
no automatic cleanup is implemented. A failed required check cannot be represented by `ready`.

Payloads are installed completely with fsync and no-clobber publication before their records.
Identical bytes are reused; different bytes at an immutable path conflict. Before the completion
marker, the command rereads every record and payload, validates schemas, checks the full exact
reference closure and confirms the selected legacy inputs still have their original hashes.
This is bounded local publication, not a tested multiwriter database or production backup service.
Policy `approved` here is initial acceptance of these specific technical onboarding rules under
the user's instruction; it conveys no independent scientific, legal or trading approval.

## Running the bounded pilot

The helper needs the optional schema engine `jsonschema==4.25.1` already used by specification
checks. It currently resides in `/private/tmp/research_platform_schema_check_v02`; no global
Python environment was changed. The command is intentionally fixed to CES0500000003 and the
2018 window; expanding it requires reviewing the provider/series assumptions.

From the platform root, using a fresh temporary acquisition directory:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/onboard_alfred.py --fetch --acquisition-dir /private/tmp/alfred-onboarding-new-capture
```

`--fetch` makes five official GETs and reads only `FRED_API_KEY` from the existing local legacy
configuration. It never persists that key. Omitting `--fetch` replays a previously captured
acquisition directory and does not claim to refresh live connectivity. The receipts preserve
the actual capture timestamps. A repeated replay creates another audit record while reusing
identical immutable payloads/definitions. No legacy job or legacy writer is invoked.

Tests and the exact issued assessments are documented in the completion report. UI selections
remain mock; no research trial, feature/target store or downstream engine is populated here.
