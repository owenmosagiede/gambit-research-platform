# First stored Signal trial — completed

One real Feature recipe, one logical Signal and one historical materialization were published, retrieved in a fresh process and reused by an identical rerun. **187 scheduled rows: 187 valid, 0 missing, 0 invalid; no null reasons.** The result is `materialized` and scientifically `untested`.

This is successful feature engineering and persistence. It is not evidence of predictive value, an evaluated research relationship or certification for live trading.

## Actual identities

- Signal: `SIGNAL_6d5467959a5e3f4a51d50e202d8ff6f15449f994ce8f08418de41b21ce2dcb0a`.
- Feature recipe: `FEATURE_6d5467959a5e3f4a51d50e202d8ff6f15449f994ce8f08418de41b21ce2dcb0a` version `1.0.0`.
- Materialization: `MATERIALIZATION_efe8c807ec15ba0f162c0e109c9a2ae147bbcc60d372b8e82bfdd15d75a3d636` version `1.0.0`.
- Dataset: `DS_FRED_ALFRED_CES0500000003@2.0.0` — Average Hourly Earnings of All Employees, Total Private; FRED / ALFRED.
- SourceView: `SVIEW_ALFRED_CES0500000003_VINTAGE_DATE@2.0.0`.
- PIT snapshot: `SNAPSHOT_0ad3598870753cc4bba55777aaf087d057b5d967a7333f7d530b664f366f9892@1.0.0`.
- Operator: `TR_BASE_change_pct@2.0.0`, `k=1`; generic `change.pct`, not a price-restricted alias.
- Evaluation policy: `POL_TRANSFORM_EVALUATION_NATIVE_VINTAGES@2.0.0`.

Exact reference hashes, source metadata, all 187 dates, output index, storage paths and audit evidence are in [first_signal_trial_evidence.json](first_signal_trial_evidence.json).

## Approved semantics and verified source

The explicitly approved rule emits once per stored vintage date, **2011-03-04 through 2026-10-02**. Each value is the latest available reference month divided by the immediately preceding calendar month, less one; both operands use the same historical state. The output is a **dimensionless fraction**: `0.01` means 1%. No percentage scaling or other transformation was added.

The selected source is measure `value`, entity `US`, dimensions `[]`, monthly and seasonally adjusted, in `USD_per_hour`. Reference labels use the first calendar day of each month. The stored source contains 247 reference months (2006-03 through 2026-09) and 1,587 PIT events, including 36 explicit missing events. Output reference months range from 2011-02 through 2026-09. All 187 actual native cutoffs were used; earlier source months are not fabricated into earlier feature cutoffs.

Precision remains **date**. This is **archive date replay**, not exact release-event replay or evidence of availability before any particular trading decision that day. Actual execution timestamps were recorded in October 2026 and never substituted for historical availability.

The source missing events affect older reference months, not these scheduled pairs, so this actual materialization has no nulls. Fixtures verify retained null rows for missing monthly values, missing calendar months and zero denominators. There is no interpolation, skipping, zero substitution or dropped scheduled failure.

The recipe pins the schedule rule and version. The materialization pins the exact dates, full input evidence and implementation. Its 187-row coverage is not a permanent limit on the logical Signal.

## Independent calculation checks

All **187** outputs were independently recalculated with 50-digit Decimal division from the stored PIT states, without importing the transformation engine. Maximum absolute difference from stored binary64 results: `2.691946072684642438452520515826495E-16`; tolerance: `1e-15`.

| Check / cutoff | Numerator reference: value | Denominator reference: value | Independent expected fraction (rounded here) | Stored fraction |
| --- | --- | --- | --- | --- |
| first / 2011-03-04 | 2011-02-01: 22.87 | 2011-01-01: 22.86 | 0.0004374453193350831 | 0.0004374453193352057 |
| revised denominator / 2018-03-09 | 2018-02-01: 26.75 | 2018-01-01: 26.71 | 0.0014975664545114189 | 0.0014975664545113787 |
| middle / 2018-12-07 | 2018-11-01: 27.35 | 2018-10-01: 27.29 | 0.0021986075485525834 | 0.0021986075485527223 |
| calendar-month boundary / 2025-12-16 | 2025-11-01: 36.86 | 2025-10-01: 36.81 | 0.0013583265417006248 | 0.0013583265417005386 |
| latest / 2026-10-02 | 2026-09-01: 37.81 | 2026-08-01: 37.76 | 0.0013241525423728814 | 0.0013241525423730582 |

The January 2018 denominator was 26.74 at 2018-02-02 and revised to 26.71 at 2018-03-09; the latter cutoff correctly uses 26.71. There is no actual repeated current-reference month among these 187 outputs; preservation of such revised outputs is verified in isolated fixtures.

For 2025-12-16, October 2025 supplies the denominator even though October had no separate emitted feature row. The previous emitted reference month was September; it is not substituted.

Each checked pair has the following exact operand lineage. All listed records use version `1.0.0`; the companion evidence includes content hashes, raw snapshot/blob/cell locators, native-row hashes and full-precision expectations.

- **2011-03-04**: numerator available `2011-03-04`, `PIT_OPERAND_f9c50f9edb3da46cab1803bca36a70cc5635465287852483510b00b05bda6592`; denominator available `2011-03-04`, `PIT_OPERAND_3103c83c9a8991a0e012cae36f88b8ab5b8019d5b0f8ebfd3d167dbe606d2d15`.
- **2018-03-09**: numerator available `2018-03-09`, `PIT_OPERAND_d98a9a23cdce43dabe512ca6c3e8bde10da8bd0b05c4fa1166985f65caf2b1e6`; denominator available `2018-03-09`, `PIT_OPERAND_72cd9fef739ae2bfbeba816c73939e572b4c58b35c110f381f1c218e5bca255b`.
- **2018-12-07**: numerator available `2018-12-07`, `PIT_OPERAND_5ba7780af2941ce00112cdeaa022acd4194d0e38b41c8a129401f96c5f349628`; denominator available `2018-12-07`, `PIT_OPERAND_a574290b47ffdeb2317eabb4af5e5356d456684e682c68e56592be52f8ea9da1`.
- **2025-12-16**: numerator available `2025-12-16`, `PIT_OPERAND_0d0215e7d92b2beceb9ddd128bea4e619ac1d4d2777a38957c3c6dca7bd27c09`; denominator available `2025-12-16`, `PIT_OPERAND_93f6a6650837645402e0f53aa6952a43444742feabe008398966eac6c61eb437`.
- **2026-10-02**: numerator available `2026-10-02`, `PIT_OPERAND_a4ad513baa112bb32576b4a775086613245c14a433ceb4b993e6beae72f4e2ca`; denominator available `2026-10-02`, `PIT_OPERAND_1f3edd72f58456b886234ae571b1a85c2743cfaa5e30d0861b600028a53a9d64`.

## Storage and created implementation

All project paths below are relative to `/Users/owenmckinleyosagiede/Desktop/Multi-Asset Model/research_platform`.

- Feature: `definitions/features/FEATURE_6d5467959a5e3f4a51d50e202d8ff6f15449f994ce8f08418de41b21ce2dcb0a/1.0.0.json`.
- Materialization: `storage/catalog/feature_store/MATERIALIZATION_efe8c807ec15ba0f162c0e109c9a2ae147bbcc60d372b8e82bfdd15d75a3d636/manifest.json`.
- Observations: `storage/payloads/sha256/ca/ca2f34fe790a8766148f42f871782f62a4d88eee8dc2918183f2e286849a3927.jsonl`.
- Signal entry: `storage/catalog/signal_library/entries/SIGNAL_6d5467959a5e3f4a51d50e202d8ff6f15449f994ce8f08418de41b21ce2dcb0a/514377e745cb085ed75dde533bcd6c943440b3c022483ae4dccd0dd8bc46a5d1.json`.
- Implementation: `storage/catalog/implementations/IMPLEMENTATION_e850d6df66b3a22a4f34591a0a72e4af1c0f503f7f8c8d6e7cf825944a2be570/manifest.json`.
- Evaluation policy: `definitions/policies/POL_TRANSFORM_EVALUATION_NATIVE_VINTAGES/2.0.0.json`.
- Exact operand/output lineage: `storage/catalog/lineage/<id>/manifest.json` — 339 distinct PIT operand locators and 187 output lineage records. Locators reference existing PIT/raw evidence without copying source values into definitions.
- Two separate operational audit records live under `storage/catalog/attempts/<attempt-id>/events/`; exact paths and UTC timestamps are in the companion evidence.

New reusable modules are `src/data/stored_pit_source.py`, `pit_feature_adapter.py`, `feature_evaluation.py`, `feature_store_contracts.py`, `feature_store.py` and `first_signal_trial.py`; all are under `src/data/`. The entrypoint is `tools/run_first_signal_trial.py`, configured by `config/first_signal_trial.json`. Added `specs/schemas/feature_store.schema.json` and `specs/17_stored_feature_trial.md`, with focused tests for each boundary. Existing identity, recipe schema and generic engine gained an optional pinned evaluation-policy reference; existing identity vectors still pass.

The additive 0.3 stored-record profile preserves native dates and evaluation cutoffs in the existing Feature Store and Signal Library paths. Feature JSONL is stored once by checksum. Definitions hold the recipe, and the Signal Library holds references; it has no research result or editable metric copy. Publication validates dependencies and payloads before exposing a complete materialization and library link.

## Reproduction, retrieval and tests

From the platform root, the following production request was executed twice. The second returned `reused: true` with identical Signal, Feature, materialization and library references. Storage contains exactly one Feature definition, one materialization and one Signal entry; only the execution audit is separate.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/run_first_signal_trial.py run --request config/first_signal_trial.json
```

Fresh-process retrieval succeeded using:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/run_first_signal_trial.py get --signal-id SIGNAL_6d5467959a5e3f4a51d50e202d8ff6f15449f994ce8f08418de41b21ce2dcb0a --materialization-id MATERIALIZATION_efe8c807ec15ba0f162c0e109c9a2ae147bbcc60d372b8e82bfdd15d75a3d636 --include-observations
```

The current source/schema/environment bytes are pinned in the implementation manifest. Changing those dependencies deliberately produces a different materialization; never overwrite the original.

Final test commands and actual results:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/specifications -v
```

- Main suite: **268 passed** in 28.410s, including 72 new source/adapter/evaluation/store acceptance tests and the 196 prior tests.
- Specification suite: **24 passed** in 0.181s.
- Total: **292 passed; no failures or skips**. Checks include future-revision isolation, same-cutoff operands, exact calendar gaps, null handling, incidental provider labels, immutable identity, interrupted publication recovery, corrupt/missing payloads, source-snapshot mismatch, raw-coordinate tampering, exact Feature-reference validation and fresh retrieval.
- Independently verified all 187 production values, exact schedule, source lineage, rerun reuse and one-object storage counts. Byte checks found **0 changed files among 226 pre-existing storage/definition/UI files**.

## Remaining decisions and boundary

No blocker remains for this approved archive-date stored feature. Live decision-clock certification, a Target/outcome and horizon, Scope, expected direction, Research Spec and later P1/P2 validation remain separate decisions. No target, research trial, extra recipe, UI control, provider download, bulk migration or live execution was added. Legacy Data/FX were read only. Work stops at this one persisted, reproducible and retrievable Signal.
