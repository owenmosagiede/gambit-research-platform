# ALFRED PIT materialization — completed

> Subsequent update: the redundant 2018 raw/PIT sample package was physically removed at the user’s request. The full-history dataset remains intact. See [the removal report](alfred_sample_removal.md). The results below describe the earlier task.

The onboarded **CES0500000003** sample (Average Hourly Earnings, Total Private, seasonally
adjusted USD/hour) now has a separate materialized **PIT snapshot and SQLite query database**.
The bounded scope is unchanged: all **12 reference months of 2018**, preserving **77 native
vintage events**, including subsequent revisions through **2025-02-07**.

This is source-vintage **date-level** PIT reconstruction. No exact intraday availability
timestamps, live-generation approval or research fitness were inferred.

## Actual storage

All paths below are inside `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.

- [Queryable PIT database](../storage/catalog/pit_store/index.sqlite):
  `storage/catalog/pit_store/index.sqlite`. It is a rebuildable index over verified immutable records.
- [Authoritative PIT snapshot](../storage/catalog/snapshots/SNAPSHOT_928c333a67fcdcb0510ee856c5544fabe9220facfd4623b2edffec698992893e/manifest.json):
  `SNAPSHOT_928c333a67fcdcb0510ee856c5544fabe9220facfd4623b2edffec698992893e` at version `1.0.0`, with `layer=pit`.
- [Canonical revision history](../storage/payloads/sha256/f1/f15532d2edd69898989c8167f3f79051dfaea3dc4913e215edf853a9020948c4.jsonl):
  **53,489 bytes**, 77 canonical JSONL rows. SHA-256
  `f15532d2edd69898989c8167f3f79051dfaea3dc4913e215edf853a9020948c4`.
- [Successful completion record](../storage/catalog/pit_store/completions/SNAPSHOT_928c333a67fcdcb0510ee856c5544fabe9220facfd4623b2edffec698992893e.json):
  pins raw/PIT/view/schema references, observed counts and historical acceptance probes.
- [Implementation manifest](../storage/catalog/implementations/IMPLEMENTATION_41845620cc68e7d819594620a401ed1db1e569f46b5b9a15833519d9de0b77a8/manifest.json)
  and [lineage manifest](../storage/catalog/lineage/LINEAGE_4436841639cffdbd80a606d2f8fd30e9dd285353aee6c19bc169871e56e3fd83/manifest.json)
  pin the code, environment, policies, source snapshot and schema evidence.

The raw and PIT layers have distinct snapshots and distinct payloads; their immutable files
share the checksum-addressed payload root. SQLite is the separate convenient query location,
not the only retained copy. Deleting/corrupting the index in an isolated test and rebuilding
it preserved identical historical query results.

The conversion added **5 new immutable payloads**, **4 typed records**, **5 locator records**
and **1 completion record**: **89,436 bytes** in total. The separate SQLite file is
**131,072 bytes**, bringing new stored data and index bytes to **220,508** (excluding source
code/documentation). Existing shared code/environment payloads were reused where identical.

## Actual historical results

These queries select the January 2018 observation from the published snapshot:

| As-of vintage date | Selected value | Meaning |
| --- | --- | --- |
| 2018-02-01 | No row | The first archived value had not appeared |
| 2018-02-02 | 26.74 | Initial archived value |
| 2018-03-08 | 26.74 | The later revision is excluded |
| 2018-03-09 | 26.71 | The revision applies from this date |

Both release-date values agree with the independent official historical responses saved
during onboarding. The stored history retains all revisions. Query results omit later
successor dates so they do not expose a future revision schedule. An explicit missing event
would remain missing rather than silently falling back to an older value; synthetic tests
verify this boundary.

## Implementation files

- [PIT materializer and verified reader](../src/data/alfred_pit.py).
- [Build/query/rebuild command](../tools/materialize_alfred_pit.py).
- [Source-specific PIT row schema](../specs/schemas/alfred_pit_rows.schema.json).
- [12 PIT store tests](../tests/test_alfred_pit_store.py) and [8 row-schema tests](../tests/test_alfred_pit_schema.py).
- [PIT implementation contract](../specs/14_alfred_pit_store.md) and [runtime dependency](../requirements-data.txt).
- Current root/storage/source/schema READMEs, the specification index and portable storage
  layout now distinguish this implemented pilot from remaining proposed stores.

The existing experiment, platform and onboarding schemas are unchanged. The new row contract
is additive and its exact bytes are pinned as immutable evidence for this snapshot.

## Verification performed

Python **3.14.0**, jsonschema **4.25.1**; SQLite supplied by Python. From the platform root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 -m unittest discover -s tests/specifications -v
```

**62 tests passed in 1.829s + 24 tests passed in 0.150s = 86 passed, no skips.**
The 20 new cases cover source-specific schema rules, first-release/revision boundaries,
missing and equal-value events, invalid/future/uncovered dates, canonical-payload/index
corruption, index recovery, identical repeat builds, pinned-schema independence and missing
evidence rejection. Integration writes occur only in temporary copies of the bounded package.

After tests, the real platform build completed successfully. A separate read of the actual
published store reverified its parent package, exact immutable lineage, pinned schema,
canonical row bytes/counts, source equivalence and historical query values. The database
integrity check passed with one snapshot and 77 indexed events. All **53 original onboarding
files** were checksum-compared against the pre-build inventory and are **byte-identical**.

No legacy reads/writes, new API requests, credential reads, migration, deletion, new scientific
trials, feature/target materializations or schedules were performed by this PIT conversion.

## Using this snapshot

The temporary dependency path used above must exist. For a durable environment, install the
pinned [requirements-data.txt](../requirements-data.txt) in a project virtual environment;
then the same command needs only `PYTHONPATH=src`. Installation was not needed for this run.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/private/tmp/research_platform_schema_check_v02:src python3 tools/materialize_alfred_pit.py query --snapshot-id SNAPSHOT_928c333a67fcdcb0510ee856c5544fabe9220facfd4623b2edffec698992893e --as-of 2018-03-09 --observation-date 2018-01-01
```

Omit `--observation-date` to select all visible reference months. `rebuild-index` reconstructs
the disposable database; `build` repeats the same frozen conversion without pulling data.
The command never chooses an implicit latest snapshot.

## Limits and next bounded task

The captured archive cutoff is **2026-10-09T03:59:46.083674Z**. It describes the actual stored
archive, not the release time of individual historical observations. Queries beyond its UTC
capture date are rejected; a query on that date still means the archive as captured, not a
completed source-calendar day. This is not the provider's full history and is not a refreshed
live feed. Source-vintage replay does not establish historical receipt into this computer,
intraday trading eligibility or permission to use previously exposed research periods.

The next bounded task is to specify and verify **one retained transformation** on this pinned
PIT view, then materialize one Feature after resolving its availability/alignment policy.
Parameters, units, missingness and decision-time semantics must be explicit. No particular
transformation, lag, release hour or trading clock is selected by this conversion.
