# CES0500000003 full-history onboarding and PIT — completed

> Subsequent update: the redundant 2018 raw/PIT sample package was physically removed at the user’s request. The full-history dataset remains intact. See [the removal report](alfred_sample_removal.md). The results below describe the earlier task.

The entire **available ALFRED archive** for Average Hourly Earnings of All Employees,
Total Private is now onboarded and materialized as a separate PIT store. Coverage was
verified against official metadata, the unbounded vintage-date catalog, exact native
responses and independently requested historical states.

| Verified coverage | Result |
| --- | --- |
| Economic reference months | **March 2006 through September 2026 — 247 months** |
| Available archived vintage dates | **2011-03-04 through 2026-10-02 — 187 dates** |
| Stored PIT events | **1,587** |
| Composition | 60 initial archived observations + 1,527 new/revised events |
| Explicit missing events preserved | **36** |
| UTC acquisition interval | 2026-10-09T04:39:08.702697Z through 2026-10-09T04:39:12.634612Z |
| Provider-evidenced vintage cutoff | **2026-10-02**, separately recorded from download time |
| Successful requests in published acquisition bundle | **16**, all HTTP 200 |

Older economic observations first appear in the available archive on **2011-03-04**.
They are retained, but their original release-time vintages are not invented. A query
before that date explicitly reports `before_archive_coverage`; it does not assert that
the economic data did not exist. Timing remains source-calendar **date-level**, with no
fabricated intraday availability or historical receipt into this computer.

## Storage and authoritative records

Platform root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.

- [Full-history query database](../storage/catalog/pit_store/full_history/index.sqlite):
  `storage/catalog/pit_store/full_history/index.sqlite`.
- [Raw snapshot](../storage/catalog/snapshots/SNAPSHOT_0fc2d1ab5d72a9830a9b5af5a99ec5d40753468f7706db88538ab0fad9c369e7/manifest.json):
  `SNAPSHOT_0fc2d1ab5d72a9830a9b5af5a99ec5d40753468f7706db88538ab0fad9c369e7`.
- [PIT snapshot](../storage/catalog/snapshots/SNAPSHOT_0ad3598870753cc4bba55777aaf087d057b5d967a7333f7d530b664f366f9892/manifest.json):
  `SNAPSHOT_0ad3598870753cc4bba55777aaf087d057b5d967a7333f7d530b664f366f9892`.
- [Canonical PIT events](../storage/payloads/sha256/1b/1be820be75e62c4ef7572364fed27827a5c2e12b1afa2e48ed1f2bc6a1c06270.jsonl):
  **1,102,327 bytes** of immutable canonical JSONL, SHA-256 `1be820be75e62c4ef7572364fed27827a5c2e12b1afa2e48ed1f2bc6a1c06270`.
- [Full package manifest](../storage/catalog/onboarding/runs/ONBOARDING_8e6512e01635192b710e8585ce0aa848ea90b6eb5820fc821f5301d0a6278785.json) enumerates the complete record/payload
  closure and pins the source definition, policies, evidence, implementation and assessments.
- [Successful completion record](../storage/catalog/pit_store/full_history/completions/SNAPSHOT_0ad3598870753cc4bba55777aaf087d057b5d967a7333f7d530b664f366f9892.json) records the published
  raw/PIT references, verified coverage and index location.

The raw snapshot has **two authoritative source members**: an actual native type-2 response
for the earliest archived vintage (60 reference rows), and an actual native type-3 response
for subsequent changes (247 reference rows). Its `record_count` is therefore **307 serialized
source rows**, across **247 distinct reference months**; PIT `record_count` is **1,587 events**.
Every PIT event identifies its original raw blob and actual source column. The separately
retained verification responses are evidence, not duplicate authoritative observations.

SQLite is a verified, rebuildable query index. The immutable manifests, raw responses and
PIT event payload remain authoritative. The previous 2018 pilot keeps its separate database
at `storage/catalog/pit_store/index.sqlite`; it was not replaced or expanded in place.

## Completeness checks and source behavior

A changes-only download was insufficient: it omitted the first archived state. The materializer
now combines the separately fetched type-2 initial vintage with the type-3 change history,
then checks that their union covers every date in the complete official vintage catalog.
The first archived state is directly observed source data, not synthetic backward filling.

The provider's three small type-3 pages contain **100 + 100 + 47** reference rows but each
reports `count=1587`. The independent full response reports **247 rows** and contains the
same exact wide-row values. Rather than interpret the inconsistent page count as a row total,
the adapter requires exact agreement with the full response, contiguous page offsets,
metadata-complete monthly coverage and an empty terminal page. Original response bytes and
counts are preserved. The full response, rather than the diagnostic pages, is authoritative.

The vintage catalog was requested through its unrestricted maximum end date and checked
again after acquisition. No later available vintage was clipped. Metadata was also unchanged
at the end. Multi-request stability checks do not imply an atomic provider transaction or a
complete source-calendar capture day.

| Historical date | Reconstructed state | Independent verification |
| --- | --- | --- |
| 2011-03-03 | No selected rows; archive coverage unavailable | Reconstruction boundary check |
| 2011-03-04 | 60 reference rows | Exact match to official type-1 historical response |
| 2018-12-07 | 153 reference rows | Exact match to official type-1 historical response |
| 2026-10-02 | 247 reference rows | Exact match to official type-1 historical response |

All 77 archived events from the existing 2018 pilot also match the full archive exactly.
Missing events supersede older valid values; queries do not silently fill them. Later
revision dates are omitted from historical result rows.

## Implemented files and contracts

- [Full acquisition adapter](../src/data/alfred_full_acquisition.py): exact response capture,
  sanitized request receipts, complete coverage and historical comparisons.
- [Full-history publisher and reader](../src/data/alfred_full_history.py): immutable raw/PIT
  publication, provenance verification, historical queries and index rebuilding.
- [Command interface](../tools/onboard_alfred_full_history.py).
- [Acquisition tests](../tests/test_alfred_full_acquisition.py) and
  [8 store integration tests](../tests/test_alfred_full_history.py).
- [Implementation contract](../specs/15_alfred_full_history.md).

Dataset, source-view and seven technical policy definitions now have explicit **2.0.0**
versions for full-history scope, plus a new provider contract and scoped historical assessment.
Existing 1.0.0 definitions remain unchanged. The existing PIT row schema supports the actual
native columns of both source responses and was not changed. The pilot's index scan now
selects its exact source-view version so the two stores can coexist.

## Actual verification

**106 tests passed; 0 failures, 0 errors, 0 skips.**
The suite covers the original contracts and pilot, acquisition completeness and response-time
bounds, source metadata consistency, missingness, the initial vintage, exact page/full-response
agreement, corruption rejection, query cutoffs, repeat-build identity, index recovery and
coexistence with the old pilot. Tests that modify files use isolated temporary copies.

Executed using combined discovery of both suites with Python 3.14.0 and jsonschema 4.25.1.
Equivalent reproduction commands:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests/specifications -v
```

A separate read of the actual published package verified exact payload hashes, row counts,
lineage, source equivalence and SQLite integrity. Historical query results matched the expected
states. The pre-existing storage/definition inventory was checked after publication:
**88 of 88 files were byte-identical**, including the 2018 database.
New immutable storage totals **1,454,914 bytes**; the separate full-history
SQLite database is **2,072,576 bytes**. These figures exclude source code and documentation.

Earlier failed preflight and successful diagnostic attempts remain separate from the 16-request
published bundle. In particular, the initial UTC-day metadata request was rejected; the final
bundle uses the provider-evidenced cutoff with explicit response-bound verification. Credentials
were used only for the official API and are absent from published records and payloads.
No legacy dataset was moved, overwritten or deleted. No scientific engine, feature/target
materialization, trial, UI change or scheduled refresh was implemented.

## Querying this archive

From the platform root, using the same dependency environment as verification:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/onboard_alfred_full_history.py query --snapshot-id SNAPSHOT_0ad3598870753cc4bba55777aaf087d057b5d967a7333f7d530b664f366f9892 --as-of 2018-03-09 --observation-date 2018-01-01
```

The January value is `26.71` at that cutoff (`26.74` before the revision). Omit the observation
filter to retrieve every visible month. `rebuild-index` reconstructs this full-history database
without modifying the pilot database. For a persistent Python environment, install the pinned
[requirements-data.txt](../requirements-data.txt) and use `PYTHONPATH=src` with that interpreter.

## Remaining boundary and next bounded task

This completes full available raw onboarding and archived date-level PIT conversion for this
series at the recorded cutoff. It does not recover unavailable pre-2011 original releases,
certify a trading decision clock, approve research exposure or create a daily refresh service.
The explicit v2 policies bind this verified capture; subsequent captures must preserve the
immutable definitions and resolve any version conflicts rather than overwrite them.

The next bounded task remains one verified legacy-compatible transformation on the pinned
PIT source view, with its parameters, units, missingness and availability/alignment policy
specified before publishing a Feature materialization.

Official API contracts checked during this work:
[observations and output types](https://fred.stlouisfed.org/docs/api/fred/series_observations.html),
[vintage-date catalog](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html),
[archive limitations](https://alfred.stlouisfed.org/help).
