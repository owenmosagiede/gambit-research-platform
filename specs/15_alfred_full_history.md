# 15 — ALFRED full-history onboarding and PIT store

> Current storage update: the redundant 2018 sample has been physically removed. References below to preserving the pilot describe the original implementation. Full-history reads/replays now stand alone; [removal details](../docs/alfred_sample_removal.md).

Status: implementation specification for the full available **CES0500000003** archive
at one frozen capture. Verified acquisition facts are stated below. Successful publication
identifiers and executed test results belong in the separate completion report; this document
does not assert that publication or the final test suite has completed.

The source-specific [publisher](../src/data/alfred_full_history.py) and
[acquisition module](../src/data/alfred_full_acquisition.py) are exposed through
[onboard_alfred_full_history.py](../tools/onboard_alfred_full_history.py). They extend the
[2018 pilot](14_alfred_pit_store.md) with new definitions, raw/PIT snapshots and a separate
SQLite index. The prior immutable pilot evidence remains preserved. Explicit fetch performs
official API requests; offline build, query and index rebuild use local platform evidence.
No legacy data is migrated or rewritten, and no scientific engine, feature transformation,
scheduler or UI data integration is introduced.

## 1. Inputs and exact scope

The series is Average Hourly Earnings of All Employees, Total Private. Full history means
all available archived information returned for this series at the frozen provider cutoff,
not every value ever released by the original publisher or a promise of complete intraday
history. The validated capture has:

| Coverage dimension | Verified value |
| --- | --- |
| Reference months | 247, from 2006-03-01 through 2026-09-01 |
| Stored vintage values/events | 1,587: 60 initial archived values plus 1,527 new/revised entries |
| Explicit missing events | 36, retained as null/missing |
| Distinct archived vintage dates | 187 |
| First / last archived vintage | 2011-03-04 / 2026-10-02 |
| Provider real-time cutoff | 2026-10-02 |
| Acquisition UTC interval | 2026-10-09T04:39:08.702697Z through 2026-10-09T04:39:12.634612Z |
| Requests in the completed acquisition bundle | 16 successful HTTP 200 responses |

The dataset `DS_FRED_ALFRED_CES0500000003`, SourceView
`SVIEW_ALFRED_CES0500000003_VINTAGE_DATE` and seven `POL_ALFRED_DATE_*` policies receive
explicit versions `2.0.0`. The revised provider contract has a new content-derived ID at
version 1.0.0. All references bind exact id/version/content_sha256. Version1 records retain
their original meanings; they are not overwritten or renamed as full-history evidence.

Build takes a complete acquisition directory containing `bundle.json`, exact named response
files and sanitized receipt files. It also resolves the existing platform onboarding package
to retain its dataset conventions and compare all 77 preserved 2018 vintage values with the
new archive. This comparison reads platform copies, not legacy data locations.

## 2. Permitted information and historical boundaries

The first reference month, first archived vintage and current capture time are different
facts. March 2006 observations first appear in this retained archive in the actual
2011-03-04 baseline. They must not be inserted into earlier information sets using their
reference month as an availability date. First archived vintage is not necessarily first
economic release. Before 2011-03-04, an empty query means archive coverage is unavailable;
it does not establish that the economic data did not exist.

`observation_date` and `vintage_date` remain source-calendar labels with date precision.
No release hour, timezone mapping, historical local receipt or UTC availability timestamp
is inferred. The manifest reference period is `[2006-03-01, 2026-10-01)`, encoded using the
platform's period format; its midnight notation does not describe release instants.

The provider's `realtime_cutoff` is 2026-10-02, independently returned in metadata and checked
against the unbounded vintage catalog. The acquisition's UTC date is 2026-10-09. The code
preserves both facts instead of converting or equating them. Raw and PIT `information_cutoff`
record the acquisition finish timestamp. The run's `as_of_date` pins the provider's vintage
cutoff; queries after it fail.

Acquisition uses several requests with metadata/vintage stability checks, not an atomic
provider transaction. A query at the final vintage date reconstructs captured archive state;
no completed source-calendar-day or intraday guarantee follows. This extension certifies
neither live generation nor a trading decision clock.

## 3. Acquisition, normalization and selection

The acquisition directory must be empty. Fetch reads the existing provider credential only
when explicitly requested, saves exact successful response bytes, and excludes the key from
saved request parameters and error text. It preserves failed-request receipts without a
completed bundle. Offline replay verifies hashes, response/request scope, date/order/output
semantics and capture intervals before accepting the bundle.

Two responses are authoritative raw value sources: the native `output_type=2` state at the
first archived vintage, and one complete `output_type=3` new/revised response. In this capture,
type 3 supplies 1,527 entries but omits 60 initial archived values. The actual type 2 response
supplies those 60 native cells. The combined 1,587-event history contains no synthetic baseline
or invented pre-archive vintage. Initial and revised observation/vintage keys must be disjoint;
an overlap requires investigation rather than silent deduplication.

The type 3 response with limit=100000 returns 247 wide monthly rows and count=247. Separate
100-row verification pages return 100, 100, 47 rows while reporting count=1587. The implementation
treats the latter count as opaque provider evidence, not an inferred month or event count.
It compares each page with the exact corresponding slice of the complete response, requires
an empty terminal page at offset=247, and retains all reported counts. Initial and full-history
responses must each fit one complete supported page. The vintage catalog is requested through
9999-12-31 and checked again; every retained event's vintage must occur in it, the complete set
must match, and none may exceed the provider cutoff.

The capture also verifies unchanged series metadata, all 247 monthly anchors, native units
and seasonal adjustment, and full reconstructed states against separate type 1 requests at
first, middle and last archived vintages. Its three official comparisons contain respectively
60 rows at 2011-03-04, 153 at 2018-12-07 and 247 at 2026-10-02. The empty state on 2011-03-03 is
a reconstruction-boundary check, not a fourth official API comparison.

Normalization uses exact decimal text, preserves separate equal-valued events, and converts
source `.` to null/missing. For each observation, rows sort by vintage date and form
`[vintage_date, next_vintage_date)` intervals. Null successor means no later event in this
frozen archive, not permanent validity. An exact revision boundary selects the new event.
Explicit missing replaces the prior value until another event replaces it; no fallback to
an older nonmissing value is permitted. Successor dates are retrospective metadata and are
omitted from as-of result rows so queries do not reveal future revision timing.

## 4. Output units, row contract and query shape

Units remain seasonally adjusted dollars per hour for entity `US`. The existing closed
[ALFRED row schema](schemas/alfred_pit_rows.schema.json), profile 0.1.0, is reused and its exact
bytes are pinned in evidence. Platform 0.2 snapshot, lineage and implementation envelopes are
unchanged. Each PIT row carries:

| Fields | Meaning |
| --- | --- |
| `series_id`, `entity_id` | `CES0500000003`, `US` |
| `observation_date`, `vintage_date` | Native reference and archive dates |
| `next_vintage_date` | Exclusive successor boundary or null |
| `value`, `status` | Canonical finite decimal text with valid, or null with missing |
| `timing_precision` | Fixed date |
| `raw_snapshot`, `source_view` | Exact full-history raw and version 2 view references |
| `source_raw_blob_sha256`, `source_field` | Actual authoritative source response and original `CES0500000003_YYYYMMDD` column |

Raw blob/column plus observation date identifies the original cell. Baseline rows point to
the type 2 bytes; later entries point to type 3 bytes. The raw snapshot therefore has two native
arrays with 60 + 247 = 307 serialized source rows over 247 unique months. Its record_count=307 is
not the PIT count: the PIT snapshot has 1,587 normalized event rows.

Query requires `--snapshot-id` and date-only `--as-of`. Optional `--observation-date` must
equal an actual captured monthly anchor; omission selects all anchors available at that
as-of date. Unsupported anchors or dates after the provider cutoff fail. There is no implicit
latest snapshot, arbitrary range selector, resampling, aggregation or filling.

Output contains `snapshot`, `as_of_vintage_date`, `archive_captured_at`, `timing_precision`,
`reference_period`, `earliest_archived_vintage`, `archive_coverage_status`, `selected_count`,
`observations` and `limitations`. Coverage status is `before_archive_coverage` before the first
retained vintage and `within_captured_archive` otherwise. The latter does not promise that
every later reference month is already available. Rows are ordered by observation date and
omit `next_vintage_date`; exact raw lineage remains retrospective audit context.

## 5. Validity and completion

Build validates the acquisition again, compares the preserved pilot overlap, pins the row
schema and code/environment, and publishes exact definitions, receipts, evidence, raw and
PIT snapshots. The raw snapshot binds both authoritative responses; its lineage also resolves
all acquisition evidence. PIT lineage binds raw snapshot, SourceView, row schema and coverage
audit, plus selection/availability/revision/quality policies and implementation.

Every read resolves the full package and its exact references, validates the saved acquisition
again, checks snapshot identities and temporal bindings, and validates rows against the pinned
schema. It verifies canonical JSONL bytes, byte and semantic digests, counts, intervals,
lineage and equality to a fresh normalization of authoritative raw evidence. It also verifies
the historical assessment for that exact PIT snapshot. Engineering policy approval and
historical readiness do not grant research-exposure permission or trading approval.

The package record uses status `VERIFIED_FULL_HISTORY_PACKAGE`; it is installed before index
rebuild and final query checks. The final completion marker uses
`COMPLETE_FULL_HISTORY_RAW_AND_PIT` and binds the package path/hash and both snapshots.
These are distinct stages. A valid package or snapshot may exist before the later completion
checks finish. Both report `live_generation_certified=false`; neither is a refresh service.

## 6. Failure and recovery

Failed requests, unstable metadata/vintage catalog, inconsistent scopes/pages, missing baseline,
overlapping initial/revised keys, invalid dates/decimals, absent vintage coverage, historical
state disagreement, pilot overlap conflict and checksum/reference errors fail closed. No
incomplete bundle is represented as complete. Current implementation limits include at most
2,000 vintage dates, a complete single 100,000-row response for each authoritative value source,
and a 25,000,000-byte response bound. Exceeding a bound fails rather than truncating history.

Immutable publication reuses identical bytes and rejects conflicting content at an existing
path. A failure may leave valid orphan artifacts, but does not create a new successful final
marker. No cleanup or migration is automatic. Existing pilot source data remains read only.

Missing, stale or altered SQLite data fails query verification. Rebuild reads verified
canonical packages, writes a fresh database under a local lock, checks SQLite integrity,
fsyncs and atomically replaces only the derived full-history index. A query opens it read-only,
compares all indexed rows for the requested snapshot against immutable observations, then
compares SQL selection with the direct selection algorithm. The database cannot override a
canonical value or supply an alternative snapshot silently.

## 7. Reuse, identity and compatibility

Exact payloads are shared by byte hash. Definitions retain explicit versions and snapshot
identity follows [01](01_canonical_objects.md): semantic manifest projection excludes physical
members, while row/response semantic digests and all other dependencies remain bound. JSONL
byte checksums independently verify its selected encoding. Code, environment, schema evidence,
source capture and policy changes remain visible in immutable provenance.

The full-history index is separate from the pilot index. The pilot rebuild scan is tightened
to its version 1 SourceView; the full-history reader requires version 2. This compatibility fix
changes the current helper without altering its previously published immutable code artifacts.
The old pilot definitions, raw/PIT snapshots, row payloads and completion evidence retain
their original identities and remain readable.

Offline replay of the same bundle can reuse identical artifacts. Version2 policies pin this
capture's compatibility audit. A later capture that changes that audit or another definition's
content cannot overwrite the same id/version; it may require new explicit policy/definition
versions. General unattended refresh/version management is outside this one-capture extension.

## 8. Persistence and interfaces

| Artifact | Location |
| --- | --- |
| Dataset / SourceView / policies | Existing logical IDs in definitions, new `2.0.0.json` files |
| New provider contract | `definitions/providers/<provider_id>/1.0.0.json` |
| Raw / PIT snapshots | `storage/catalog/snapshots/<snapshot_id>/manifest.json` |
| Raw responses, evidence, schema, code and JSONL rows | `storage/payloads/sha256/<first-two-hex>/<full-sha256>.<format>` |
| Ingestion receipts / evidence | `storage/catalog/ingestions/records/<id>.json`, `storage/catalog/onboarding/evidence/<id>.json` |
| Implementation / lineage | `storage/catalog/implementations/<id>/manifest.json`, `storage/catalog/lineage/<id>/manifest.json` |
| Historical assessment | `storage/catalog/readiness/records/<id>.json` |
| Package index | `storage/catalog/onboarding/runs/ONBOARDING_<hash>.json` |
| Final completion | `storage/catalog/pit_store/full_history/completions/<pit_snapshot_id>.json` |
| Derived database | `storage/catalog/pit_store/full_history/index.sqlite` |
| Local rebuild lock | `storage/temporary/alfred-full-history-index.lock` |

The raw member roles are `initial_vintage` and `observations_full`; the PIT member role is
`alfred_full_history_pit_changes`. New locators use the existing
`storage/catalog/locators/<blob_sha256>/PLATFORM_LOCAL/<path_sha256>.json` layout.

SQLite `snapshots` contains snapshot_id (primary key), content_sha256, rows_sha256, row_count
and information_cutoff. `observations` contains snapshot_id, series_id, observation_date,
vintage_date, next_vintage_date and canonical row_json; its primary key is the first four
columns. `as_of_lookup` indexes snapshot_id, observation_date, vintage_date and next_vintage_date.
Rebuild scans full-history package records and validates every selected version 2 snapshot.
SQLite remains a reproducible projection, never the only retained scientific evidence.

## 9. Acceptance scenarios

These requirements complement the measured acquisition facts above. They do not assert that
the final publication or complete regression suite has already passed.

| Scenario | Required result |
| --- | --- |
| Complete native capture | 247 reference months, 60 baseline values plus 1,527 change entries, 187 vintage dates and 36 retained missing events |
| Type 3-only materialization | Rejected as incomplete without the required actual first-vintage state |
| Query 2011-03-03 | Empty, with before_archive_coverage; no claim that economic data did not exist |
| Queries at 2011-03-04, 2018-12-07 and 2026-10-02 | Full states equal retained official type 1 evidence: 60, 153, 247 selected rows respectively |
| Exact revision date | New event selected; no future successor date exposed |
| Explicit missing event | Null/missing selected, without prior-value fallback |
| Truncated or changed verification page, altered native boundary or baseline overlap | Explicit failure |
| Missing/stale/altered index | Query fails; verified rebuild restores identical values |
| Repeated identical offline build | Reuses unchanged canonical artifacts appropriately |
| Pilot after full-history addition | Version1 query/rebuild remains isolated from version 2; old immutable evidence remains unchanged |

## Running the implementation

Use a Python environment with the pinned [requirements-data.txt](../requirements-data.txt),
including jsonschema==4.25.1. Standard-library SQLite and local locking are used. Run from
the `research_platform` root with `PYTHONPATH=src`. In this workspace the existing temporary
schema installation can instead be used with
`PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src` while that directory exists.

Offline publication from a completed capture, query and index rebuild:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 tools/onboard_alfred_full_history.py build --acquisition-dir '<completed_capture_dir>'

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 tools/onboard_alfred_full_history.py query --snapshot-id '<snapshot_id>' --as-of 2011-03-03

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 tools/onboard_alfred_full_history.py query --snapshot-id '<snapshot_id>' --as-of 2011-03-04 --observation-date 2006-03-01

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 tools/onboard_alfred_full_history.py rebuild-index
```

Replace placeholders with the saved acquisition directory and the exact snapshot ID returned
by build. `build --fetch --acquisition-dir '<new_empty_capture_dir>'` performs fresh requests
first, reading only the existing `FRED_API_KEY` from `../Data/.env.local`; it does not modify
that file. Fetch can also be separated from publication:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m data.alfred_full_acquisition --output '<new_empty_capture_dir>' --credential-file '<credential_file>'
```

The CLI has build/query/rebuild-index commands; fetch is a build flag or a separate acquisition
module, not a fourth CLI subcommand. New capture does not authorize a conflicting immutable
version overwrite. No command schedules future work.

## Remaining scientific boundary

The next bounded integration is one feature transformation with an approved availability and
alignment policy, exact source/recipe/policy/implementation pins, and calculation scope bound
before scoped computation. The policy must state how date-level archive evidence satisfies the
feature's decision-time contract, including unresolved timing. More history does not supply
missing intraday evidence. No release hour, synthetic availability timestamp, signal direction,
forecast methodology or trading cutoff is chosen by this extension.
