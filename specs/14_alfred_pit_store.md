# 14 — Bounded ALFRED PIT store

> Current storage update: the redundant 2018 sample has been physically removed. References below to preserving the pilot describe the original implementation. Full-history reads/replays now stand alone; [removal details](../docs/alfred_sample_removal.md).

Status: implementation specification for the fixed **CES0500000003 / 2018** PIT
materializer and date-level as-of query. This document describes implemented behavior
and required acceptance checks; publication identifiers and executed test results belong
in the separate completion report. It does not certify a completed run by itself.

The implementation is [alfred_pit.py](../src/data/alfred_pit.py), exposed through
[materialize_alfred_pit.py](../tools/materialize_alfred_pit.py). It consumes the frozen
[onboarding package](13_provider_onboarding.md), adds a canonical `layer=pit` snapshot,
and builds a disposable SQLite query index. It performs no network requests, credential
reads, legacy reads or writes, raw replacement, feature transformations or research trials.

## 1. Inputs and exact scope

The input completion marker is
`storage/catalog/onboarding/runs/ONBOARDING_124af5ecbbd0cc30b35459763b2a254b2b3bdba2c1887770e8673539aec5b67e.json`.
Its `bounded_vintages` raw snapshot is
`SNAPSHOT_45eebfb35a87396f45242a7361238437ed9e7506701ca3f0bf02213237cf50ed`.
The exact SourceView is `SVIEW_ALFRED_CES0500000003_VINTAGE_DATE@1.0.0`, resolving
`DS_FRED_ALFRED_CES0500000003@1.0.0` and its registered date-level policies.
References bind `id`, `version` and `content_sha256` throughout.

Verified source facts: the selected observation window is `[2018-01-01, 2019-01-01)`;
there are 12 monthly reference dates and 77 native vintage changes. Their vintage dates
span 2018-02-02 through 2025-02-07. Every change is retained, including later revisions
to the 2018 observations. The actual sample has no missing markers; missingness remains
part of the contract and requires synthetic boundary checks. Values are seasonally
adjusted dollars per hour, for economic entity `US`.

The loader verifies the entire frozen onboarding record/payload closure, completion
marker hash, raw/SourceView relationship and exact historical-readiness assessment.
It reads only files already inside `research_platform`. The latest-five live probe in
that package is evidence of earlier onboarding; it is not the materializer's data source.

## 2. Permitted information and time semantics

`observation_date` is the economic reference month. `vintage_date` is an ALFRED archive
change-date label. Both use canonical `YYYY-MM-DD` and remain source-calendar dates.
Neither becomes an exact historical publication timestamp or local receipt timestamp.

The frozen raw archive was captured at **2026-10-09T03:59:46.083674Z**. The PIT snapshot
inherits that exact `information_cutoff`; it is the capture bound for the stored archive,
not an invented availability time for each historical value. The manifest's inherited
UTC-formatted `period` bounds encode the selected reference window; they do not describe
release instants.

The query requires an explicit date-only `--as-of`. Dates after the UTC date component
of the frozen capture timestamp are rejected. This is a conservative operational guard
against querying beyond the captured archive, not a mapping between source-calendar dates
and UTC, and not a guarantee of a completed source-calendar day. In particular, a query
for the capture date reflects the archive as captured; later changes that day are unknown.
Earlier as-of queries reconstruct the source's archived vintage-date state, not measured
intraday availability. No date-to-UTC conversion, end-of-day convention or live-generation
certification is introduced.

## 3. Normalization and selection

The existing bounded parser accepts a complete initial native-unit `output_type=3` page,
rejects duplicate reference periods, unexpected series/vintage columns, invalid dates and
nonfinite values, and retains every change event. Decimal text is normalized exactly;
binary floating-point rounding is not used. A source `.` becomes `value=null` and
`status=missing`. Sorting is by `(observation_date, vintage_date)` for the fixed series.
Equal consecutive source values are not collapsed.

For each observation date, `next_vintage_date` is the following change's date, or null
for its final event in this archive. Intervals are half-open:
`[vintage_date, next_vintage_date)`. The selection predicate is:

```text
vintage_date <= as_of
and (next_vintage_date is null or as_of < next_vintage_date)
```

At an exact revision date, the new event replaces the prior event. Before an observation's
first vintage there is no selected row. An explicit missing event remains a selected
null/missing row until replaced; selection never falls back to an older nonmissing value.
A null successor means no later recorded change in this frozen archive, not permanent
validity or evidence of future freshness.

Successor dates are retrospective interval metadata derived from later events. They are
stored for archive reconstruction and indexing but **omitted from every as-of result row**,
so historical queries do not expose the future revision schedule. Returned raw references
are audit provenance, not evidence that the full later archive was available historically.

## 4. Output units, rows and query shape

The closed [ALFRED PIT row schema](schemas/alfred_pit_rows.schema.json), profile 0.1.0,
is source-specific. The platform0.2 snapshot schema is reused unchanged. Stored rows have:

| Field | Contract |
| --- | --- |
| `series_id`, `entity_id` | Fixed `CES0500000003`, `US` |
| `observation_date`, `vintage_date` | Actual canonical calendar dates |
| `next_vintage_date` | Exclusive successor boundary, or null for the final recorded event |
| `value`, `status` | Canonical decimal text in USD/hour with `valid`, or null with `missing` |
| `timing_precision` | Fixed `date` |
| `raw_snapshot`, `source_view` | Exact immutable input references |
| `source_raw_blob_sha256` | Original raw response byte hash |
| `source_field` | Exact original column, `CES0500000003_YYYYMMDD` |

The combination of raw snapshot/blob, observation date and original column identifies the
source cell. The schema and semantic checks reject inconsistent status/value pairs,
duplicate or unsorted keys, incorrect lineage, incorrect successor intervals and incomplete
12-month reference coverage. Every normalized row is also compared against a fresh
normalization of the pinned raw payload during reads.

A query returns `snapshot`, `as_of_vintage_date`, `archive_captured_at`, `reference_period`,
`timing_precision`, `selected_count`, `limitations` and `observations`. Selected rows retain
the fields above except `next_vintage_date`, ordered by observation date. Without an
observation filter, the query returns all selected months in the bounded window. Optional
`--observation-date` selects one actual reference date; dates outside the 12 stored monthly
anchors are rejected. Arbitrary reference ranges, aggregation, filling and transformations
are not implemented.

## 5. Validity and completion

Build verifies the pinned parent package, all normalized rows, original vintage count,
row schema, output bytes, manifests and full immutable-reference closure. It rereads the
original onboarding records and payloads to confirm they are unchanged. The implementation
manifest binds code, Python/SQLite/jsonschema environment evidence and the registered
determinism policy. Lineage binds the raw snapshot, SourceView, pinned row-schema evidence,
selection operation, availability, revision and quality policies.

Read verifies the PIT snapshot identity, inherited period/cutoff, exact SourceView/upstream
raw binding, policies, implementation and lineage. The row schema is resolved from its
immutable evidence payload, so editing a current schema file cannot silently redefine an
existing snapshot. Reads verify canonical JSONL bytes, byte count/hash, semantic digest,
row count and equality to normalized raw evidence.

A successful build then rebuilds the index, runs its historical acceptance probes, compares
two retained official historical responses and installs the completion record. That record
reports `live_generation_certified=false`. It certifies this bounded materialization and
query operation only; feature readiness and research approval remain separate.

## 6. Failure and recovery

Missing, changed or conflicting immutable inputs; invalid dates; malformed rows; mismatched
lineage/policies; incorrect counts/hashes; and disagreement with raw evidence fail the
operation. Missing, stale or altered index contents cause a query error with rebuild guidance.
Queries verify the selected snapshot's entire indexed rows against immutable observations
before using the SQL result, then compare that result with the direct selection algorithm.
There is no silent best-effort result or fallback to a different snapshot.

Immutable files use complete temporary writes, fsync and no-clobber installation. A failure
may leave individually valid immutable artifacts, but does not create a new successful
completion record. Snapshot existence alone does not assert that all later build checks
finished. Existing artifacts are not cleaned up or rewritten automatically.

Index rebuild uses a local file lock, creates a fresh temporary database, checks SQLite
integrity, fsyncs and atomically replaces the derived index. Rebuilding does not change
canonical PIT/raw snapshots. This is a bounded local implementation, not a general
multiwriter service, backup system or network refresh process.

## 7. Reuse and invalidation

Identical canonical payloads and immutable records are reused. The snapshot identity hashes
its semantic manifest projection without `id` or physical `members`; its semantic content
digest binds the complete normalized ordered row array. Exact reference hashing follows
[01](01_canonical_objects.md). The JSONL byte checksum independently binds the stored encoding.
Changed input snapshots, policies, code/environment, schema lineage or normalized contents
cannot silently reuse the same immutable snapshot identity.

The SQLite database is a projection. Its bytes do not define scientific identity; it can be
rebuilt from verified matching PIT manifests. It must never become the only retained copy of
a value, interval, schema or lineage record. Expanding the source, observation window or
acquisition requires a separate reviewed change to the fixed pilot assumptions.

## 8. Persistence and index structure

| Artifact | Exact location / meaning |
| --- | --- |
| Canonical PIT snapshot | `storage/catalog/snapshots/<snapshot_id>/manifest.json`; `layer=pit`, SourceView definition, exact raw upstream, one `alfred_pit_changes` JSONL member |
| Normalized rows | `storage/payloads/sha256/<first-two-hex>/<full-sha256>.jsonl`; one compact sorted-key ASCII JSON row plus newline per event |
| Row-schema evidence | `storage/catalog/onboarding/evidence/<EVIDENCE_id>.json`; exact schema bytes in the shared payload store |
| Implementation / lineage | `storage/catalog/implementations/<id>/manifest.json`, `storage/catalog/lineage/<id>/manifest.json` |
| Payload locators | `storage/catalog/locators/<blob_sha256>/PLATFORM_LOCAL/<path_sha256>.json` |
| Derived SQLite index | `storage/catalog/pit_store/index.sqlite` |
| Local rebuild lock | `storage/temporary/pit-index.lock` |
| Successful completion record | `storage/catalog/pit_store/completions/<snapshot_id>.json` |

The SQLite `snapshots` table contains `snapshot_id` (primary key), `content_sha256`,
`rows_sha256`, `row_count` and `information_cutoff`. The `observations` table contains
`snapshot_id`, `series_id`, `observation_date`, `vintage_date`, `next_vintage_date` and
canonical `row_json`; its primary key is the first four columns. `as_of_lookup` indexes
`(snapshot_id, observation_date, vintage_date, next_vintage_date)`. Rebuild scans matching
ALFRED PIT manifests, validates each, and repopulates these tables. Queries open the database
read-only and explicitly pin one snapshot; they do not select an implicit latest version.

## 9. Acceptance scenarios

These are required behaviors, not a report that tests have already executed:

| Scenario | Expected result |
| --- | --- |
| Build the fixed raw window | 77 events, all 12 observation months, including revisions through 2025-02-07 |
| January 2018 as of 2018-02-01 | No selected row |
| January 2018 as of 2018-02-02 or 2018-03-08 | `26.74`, with no future successor date |
| January 2018 as of 2018-03-09 | `26.71`, agreeing with the retained official historical response |
| Synthetic missing revision | Selected null/missing row; no reuse of the prior value |
| Invalid timestamp/date, uncovered observation anchor or as-of after capture date | Explicit failure |
| Missing, stale or corrupted SQLite index | Explicit failure; successful rebuild restores the same query results |
| Altered payload, reference, schema evidence or successor interval | Integrity/semantic failure |
| Repeated build with unchanged inputs and implementation | Same canonical snapshot/payload, unchanged original onboarding bytes |

## Running the bounded implementation

Use Python with `jsonschema==4.25.1`; SQLite and the local locking/filesystem support come
from the standard library. The required runtime schema dependency used for this workspace is in
`/private/tmp/research_platform_schema_check_v02`, which is temporary and must still exist
when using these examples. No global Python installation is changed by these commands.
Run from the `research_platform` root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/materialize_alfred_pit.py build

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/materialize_alfred_pit.py query --snapshot-id '<snapshot_id>' --as-of 2018-03-09 --observation-date 2018-01-01

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/materialize_alfred_pit.py query --snapshot-id '<snapshot_id>' --as-of 2019-02-01

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/materialize_alfred_pit.py rebuild-index
```

For a persistent environment, install the pinned [requirements-data.txt](../requirements-data.txt)
in a virtual environment and use `PYTHONPATH=src` with that interpreter.

Replace `<snapshot_id>` with the exact ID returned by `build`. These commands use only the
frozen onboarded files. They do not pull new data or schedule work.

## Remaining scientific boundary and next bounded task

The next bounded integration is to feed this exact PIT source view into one feature
transformation under an explicit, approved availability/alignment policy. That policy must
state how source-date evidence satisfies the feature's decision-time contract and how to
handle unresolved timing; exact intraday timestamps must not be manufactured. Pin the source
snapshot, recipe, policy and implementation, bind calculation scope before any scoped
computation, and verify revision-boundary behavior before publishing a Feature materialization.
No particular lag, release hour, timezone mapping, decision cutoff or scientific transform is
chosen by this PIT implementation. General providers, fresh ingestion, research engines and
live-generation certification remain outside this bounded store.
