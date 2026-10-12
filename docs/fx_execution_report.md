# FX execution report — completed retrospective Target build

**Completed: all 43 requested instruments × 5 approved horizons = 215 unique logical Targets.**

The actual store contains **1,928,440 scheduled Target observations**, including **1,562,485 numerical simple returns**. Every combination has valid stored outcomes. The remaining rows preserve missing, invalid or immature endpoint diagnostics; no unavailable return was filled with zero. All 25 additional reusable cross histories are persisted. The existing 18 source registrations, 43-instrument manifest, 18 direct/inverse price histories and existing Signal were preserved.

This report supersedes the earlier pending-approval execution status. The immutable earlier evidence and historical source audit remain intact. Outputs are **provisional retrospective research Targets**. Successful storage and retrospective eligibility do not establish historical PIT, tradable close entry, live readiness or FTMO eligibility.

## Approved and recorded scope

- Family: FX gross spot price returns only. Formula `(exit / entry) - 1`, stored as decimal fractions; `0.01` means one percent.
- Exactly **1, 7, 21, 63 and 252 scheduled weekdays**, Monday–Friday with **no holiday exclusions**. Calendar `RESEARCH_WEEKDAYS@1.0.0`; the underlying generic clock is `scheduled_bars`, explicitly bound to this calendar. UI and coverage exports label the economic unit as scheduled weekdays.
- Entry is the native provider-date anchor close; exit advances exactly h weekdays, excluding the anchor from the count. Monday +1 → Tuesday; Friday +1 → Monday; Monday +7 → the following Wednesday.
- Resolve endpoint dates before observing prices. Both endpoints are required; missing interior prices do not invalidate a pure endpoint return. No next-observation substitution, carry-forward, interpolation or silent holiday exclusion.
- Zero delay describes return anchoring only, not an achievable order fill after calculating a Feature.
- Crosses match native stored date labels: normalize `U_X = USD per X`, then `P_A/B = U_A / U_B`. Construct endpoint prices before calculating returns; do not subtract simple leg returns.
- Unknown timing is allowed provisionally. Demonstrated session, bar, valuation, currency, quotation, domain or conflicting-observation defects remain blockers. Different timezone names alone are not proof of incompatible sessions. No numeric wall-clock tolerance was invented.
- Gross spot outcomes exclude carry, financing, spreads, fees, slippage, leverage, sizing and account-currency conversion. No unrelated Target-family defaults were introduced.

The exact user instruction is retained in approval `EVIDENCE_63a162f8a975a25fda80701febe60896047eaf299903c3bcc8d83081f26b818c@1.0.0`. The provisional retrospective policy is `POLICY_2ba9539c29b93277e30ee4c2b0752c3e54cbcf9a101ec19b2628dc5fb43ec14b@1.0.0`. The reviewable execution bundle is `config/fx_retrospective_completion.json`, with cutoff `2026-10-09` at date precision. The approval record's decision time records receipt of the instruction, not a source release time.

## Actual stored coverage

| Horizon: scheduled weekdays | Instruments | Scheduled rows | Valid returns | Missing | Invalid | Pending |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 43 | 385688 | 315561 | 70127 | 0 | 0 |
| 7 | 43 | 385688 | 315190 | 70498 | 0 | 0 |
| 21 | 43 | 385688 | 314453 | 71235 | 0 | 0 |
| 63 | 43 | 385688 | 312670 | 71341 | 0 | 1677 |
| 252 | 43 | 385688 | 304611 | 71273 | 0 | 9804 |

The exhaustive [215-combination coverage matrix](fx_target_coverage.csv) contains counts, both scheduled and valid date coverage, null reasons, readiness, Target IDs, exact materialization IDs and absolute storage paths. [Instrument coverage](fx_instrument_coverage.csv) reports the independent price ranges and dependencies; [source coverage](fx_source_coverage.csv) retains all 18 original inputs. No combination is unpopulated. No common-date truncation was applied across instruments.

Across all 43 reusable price histories there are **390,282 rows**: **321,258 valid** and **69,024 null** for missing required leg observations. Original direct/inverse histories contain 145,236 rows. Cross histories preserve the union of their required input dates, including explicit missing-leg rows before both histories overlap.

| Target null reason | Rows |
| --- | --- |
| FUTURE_ENDPOINT | 11481 |
| MISSING_ENDPOINT | 13778 |
| SOURCE_MISSING | 340696 |

Missing endpoint counts include dates which may be holidays and dates missing for other reasons. No independently verified holiday/session calendar is available to split those causes reliably, so holiday attribution remains unknown. The coverage CSV also reports overlapping diagnostic counts for absent endpoints and missing underlying legs; these overlapping counts should not be summed as disjoint categories.

Every source's last completed stored native date is 2026-09-05; the last weekday anchor is 2026-09-04. Weekend source labels remain in reusable prices but are not Target anchors. Future endpoints are pending at the pinned cutoff. Dates beyond stored price coverage but before that cutoff remain missing. The 36 raw source/date records excluded as incomplete at original capture remain excluded.

## Storage and lineage

Actual platform root: `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.

| Artifact | Existing canonical location |
| --- | --- |
| Source, normalized leg and constructed-price manifests | `storage/catalog/snapshots/<snapshot_id>/manifest.json` |
| Target definitions | `definitions/targets/<target_id>/1.0.0.json` |
| Return materialization manifests | `storage/catalog/target_store/<materialization_id>/manifest.json` |
| Policies and exact approval evidence | `definitions/policies/` and `storage/catalog/onboarding/evidence/` |
| Source, price and actual return observations | Shared `storage/payloads/sha256/<prefix>/<hash>.bin`, deterministic compressed yearly JSONL |
| Raw legacy artifacts | Read-only original paths under `../Data/`, with checksummed locators |

Each Target row binds its exact entry and exit price IDs. Price rows bind the required original source rows/vintages. Build manifests pin source snapshots, approved policies, exact schedule/anchors, code/schema/environment artifacts and knowledge cutoff. Dates retain date precision; original captures remain distinct from unknown historical release and label availability.

The store has **215 logical Target IDs and 217 immutable materialization records**. Two completed AUDUSD records (1 and 7 weekdays) from before a diagnostic correction remain as prior implementation revisions. Independent checks prove they contain exactly the same rows and reuse the same partition payloads as their completed counterparts. They are not extra logical Targets or duplicate observation payloads. The correction classifies a known missing leg as `SOURCE_MISSING` rather than `ENDPOINT_NOT_AVAILABLE`; no affected cross Target had been published before the fix.

## Verification

**544 installed platform/integration tests passed** in 120.269 seconds, plus **24 specification tests** in 0.184 seconds. The final **13 focused API/UI tests** and **11 completed-run reuse tests** also passed. No final-suite skips. Focused checks covered the final timing distinction, missing-source diagnostic and UI calendar labels. Regression coverage retains existing Feature, Signal, Target, API, temporal cutoff and persistence behavior.

The independent verifier uses standard-library exact rational arithmetic and its own weekday schedule, importing no production calculation/scheduling kernel. It checked every stored source-derived price and all **1,928,440 final-run Target rows**, including all **1,562,485 numerical returns**, endpoint lineage, null reasons, coverage, schedule marks and byte/content hashes. Maximum relative price error: `4.9763879587735183467641935243512074104148016945320156180689516894098295232498448E-50`; tolerance `1e-48`. Maximum absolute return error: `1.4628076196925475169312243669030074563872953878699869760705627649098196075921650E-49`; tolerance `1e-48 × max(1, |exact return|)`.

All 18 source snapshots and 18 direct/inverse price snapshot references were retained. All 38 selected raw artifacts and 35 canonical legacy pages have unchanged hashes. All **3,621** pre-completion immutable definition/storage files retain content and modification times. The previously stored CES0500000003 Signal and its 187 rows were not recalculated.

Fresh-process public retrieval succeeded for direct EURUSD, inverse USDJPY and cross EURJPY. Strict historical training retrieval returned zero rows for each. The public catalog exposes **215 unique Targets** and **43 instruments**, with separate provisional research/historical/live readiness. Browser inspection confirmed the real API-backed selector and Target detail disclosures; the sole existing Feature remains unchanged.

### Repeat execution

A complete repeat reconstructed the same prices and used the explicit completed-run reuse path to verify the exact Target references, active construction, definition, policy, schedule, cutoff, current code fingerprint and all dependency/payload checksums. It reused all **215 final Target materializations**, the same 43-instrument construction completion and preserved the original 18 price snapshot references. Across **12,841** immutable definition/catalog/payload files: **0 added, 0 removed, 0 content changes and 0 modification-time changes**. Source onboarding was not rerun. Both partial interruption and resumable parallel execution used the existing atomic publication mechanism.

## Persisted public retrieval examples

### EURUSD — direct, 7 scheduled weekdays

- Target: `TARGET_017a7c28477ec8b1b5f8fa165aa6a97c9b144e73899b777ed0ee973a24560d29`.
- Exact retrieved materialization: `MATERIALIZATION_f925bb95fa5342a97003ace9a491e11d1fb3bfbec53ca42f33dd960a0fe09053`.
- Public retrieval returned **5,940 scheduled rows**, including **5,874 valid returns**.
- First valid example: anchor/entry `2003-12-01`, exit `2003-12-10`, decimal return `0.0188884245716673631424989552862515670706226493941`.
- Historical training cutoff `2026-10-09` returned **0 eligible observations**. Availability remains unknown; original capture is retained separately.

### USDJPY — inverse, 7 scheduled weekdays

- Target: `TARGET_6e10efb77d5da28843e88532a0dca2fd2a82bbc1253cd652b8c740faddcaf4f0`.
- Exact retrieved materialization: `MATERIALIZATION_c440ff45221ba6a2b5a8baf0f1b257330db151608d7e86472462aca233d21d93`.
- Public retrieval returned **7,788 scheduled rows**, including **7,703 valid returns**.
- First valid example: anchor/entry `1996-10-30`, exit `1996-11-08`, decimal return `-0.0213697384037011505688884466964672773659860851521`.
- Historical training cutoff `2026-10-09` returned **0 eligible observations**. Availability remains unknown; original capture is retained separately.

### EURJPY — USD cross, 7 scheduled weekdays

- Target: `TARGET_85219be7f9fe23e074e3b10da8893cb96db6fe485c8fc2ed2595d7a7928e78db`.
- Exact retrieved materialization: `MATERIALIZATION_33470d89e119561fc872584ae764cea7ca0c49b62972a8b36c566a2f47194891`.
- Public retrieval returned **7,788 scheduled rows**, including **5,870 valid returns**.
- First valid example: anchor/entry `2003-12-01`, exit `2003-12-10`, decimal return `0.0115152831206206460152781470501357927500187746268`.
- Historical training cutoff `2026-10-09` returned **0 eligible observations**. Availability remains unknown; original capture is retained separately.


The complete row values, endpoint IDs and readiness records for these examples are in [execution evidence](fx_execution_evidence.json).

## Reproduce or inspect

Run from the actual platform root. The approved configuration and exact completion are already stored; these commands do not onboard providers again.

```sh
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python tools/targets.py list --instrument-id EURJPY

PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python tools/fx_batch.py returns \
  --completion storage/catalog/onboarding/evidence/EVIDENCE_ec69d599bf28e089a06395ffb9b129ecbe3eebbc22ec3ea31e39674afaf8dfae.json \
  --approved-policy config/fx_retrospective_completion.json \
  --reuse-completed-run docs/fx_completed_run.json

PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python tools/targets.py get \
  --target-id TARGET_85219be7f9fe23e074e3b10da8893cb96db6fe485c8fc2ed2595d7a7928e78db \
  --materialization-id MATERIALIZATION_33470d89e119561fc872584ae764cea7ca0c49b62972a8b36c566a2f47194891
```

The existing read-only API is `/api/target-library`; observation reads require an exact Target ID and materialization ID. Range filtering does not replace historical availability checks. The UI runs at `http://127.0.0.1:8765/#experiment`.

## Updated implementation and review files

- `src/data/fx_pipeline.py`: preserve the exact original 18 completed prices and normalized legs while constructing the remaining crosses.
- `src/data/transformations/fx.py`: distinguish unknown timing from demonstrated session/valuation incompatibility.
- `src/data/targets/fx.py`: record the family-scoped approval semantics, publish scheduled-weekday catalog metadata and preserve correct missing-source diagnostics.
- `tools/fx_batch.py`: resume from stored prices, bounded independent execution and explicitly verified reuse of completed builds.
- `ui/targets.js`: sorted live Target choices, separate valid/scheduled coverage, stored numerical examples and provisional/historical/live disclosures.
- FX transformation, pipeline, Target, resume and API/UI regression tests.
- `specs/19_fx_sources_and_return_targets.md`, `docs/fx_data_contracts.md`, decision register, specification index and root README; exact approved execution bundle in `config/fx_retrospective_completion.json`.
- This report, exhaustive coverage CSVs, actual verification evidence and test logs.

## Remaining limits and next bounded task

No approval remains pending for this completion. Historical publication/close times, complete original vintages, provider session/DST conventions and price basis remain unverified. Retrospective approval does not resolve them. Historical PIT is blocked; live/executable use remains unresolved; FTMO account eligibility is unchanged. The 15 large source moves remain disclosed audit flags, with no automatic exclusion. The earlier two-date EUR/GBP comparison remains diagnostic only, not a timing or broker certification.

The verified catalog currently traverses stored dependencies on a cold read; the measured full-catalog time was **8.782 seconds** in a fresh process. The UI allows up to 90 seconds for that verification and 60 seconds for a pinned detail read. A verified metadata index is a bounded performance follow-up; no integrity checks were bypassed.

The next scientific task is to specify the first Signal–Target experiment's Scope, Expected Direction, Research Spec, Feature decision timing and alignment to one of these stored Target horizons. That contract must preserve Feature and label availability rules before any experiment is executed. This completion does not run discovery/validation gates or build an execution system.
