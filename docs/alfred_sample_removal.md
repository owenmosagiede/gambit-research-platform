# Redundant ALFRED 2018 sample — physically removed

The user explicitly requested deletion of the redundant sample data, extending the prior
UI-only change. The deletion was completed inside `research_platform`; legacy `Data/` and
`FX/` locations were not modified.

## Actual result

- Removed **62 files**: 32 sample-only definition/catalog records, 13 exclusive payloads,
  13 payload locators, the sample completion, sample SQLite database, pilot onboarding run
  and superseded full-history package inventory.
- Removed bytes totaled **385,215**; publishing the smaller replacement full-history inventory
  produced a net logical storage reduction of **371,575 bytes**. Filesystem allocated-space
  savings were not measured. No archive or backup copy of the removed sample payloads was made.
- Full history still contains **247 observation months, March 2006–September 2026**, and
  **1,587 vintage records**. The 2018 observations remain part of this complete dataset.
- The API now reports **one dataset, one snapshot and no issues**. The local UI server
  was restarted at `http://127.0.0.1:8765`.

## Why deletion required a package update

The original full-history run listed every earlier pilot file even though its scientific
references did not depend on those records. Two independent reference audits found the actual
full-history closure: **36 records and 25 payloads**, rather than 64 records and 35 payloads.
A new content-addressed package inventory now lists only those dependencies. The active
completion points to that new inventory. The prior over-inclusive inventory was removed.

Full-history raw/PIT payload bytes, scientific snapshot IDs, definitions, lineage and SQLite
index are unchanged. Shared code, environment and schema evidence was retained. The two
snapshots remain identified historically as:

- Deleted sample: `SNAPSHOT_928c333a67fcdcb0510ee856c5544fabe9220facfd4623b2edffec698992893e`.
- Retained full history: `SNAPSHOT_0ad3598870753cc4bba55777aaf087d057b5d967a7333f7d530b664f366f9892`.

Current package inventory:
`storage/catalog/onboarding/runs/ONBOARDING_12654e3f5dc5d68ba38ef330623593d110b4806fb5008d372001e25e6cf502de.json`.

Current query database:
`storage/catalog/pit_store/full_history/index.sqlite`.

## Verification actually performed

Before deletion, all **77** sample scientific records were matched exactly to full-history
records. Historical as-of states matched across all **19** sample vintage dates. An isolated
staging package containing only the retained full-history dependencies passed the existing
verified reader, library API and historical queries before production removal.

After deletion, every planned removed path was absent and every retained package/index file
was byte-identical. The live API returned the single expected full-history snapshot. January
2018 historical queries still returned 26.74 on 2018-02-02 and 26.71 on 2018-03-09; the final
stored vintage query returned all 247 reference months.

**121 tests passed, with no failures, errors or skips, in 10.333 seconds.** Bounded-store tests
now build temporary synthetic data; full-history/API tests use the surviving package.
No duplicate real sample was retained as a test fixture.

## Runtime and documentation

Identical acquisition replay verifies and reuses the standalone full-history package, without
requiring the deleted pilot. New acquisition publication still requires a versioned refresh
implementation; no refresh service or new scientific processing was added. Tests reject a
corrupt completion and changed capture provenance without recreating the sample.

Current UI/API/storage documentation and path configuration now describe the full-history
package. Earlier completion reports carry a retirement notice so their historical statements
about retaining the pilot are not mistaken for current storage status.
