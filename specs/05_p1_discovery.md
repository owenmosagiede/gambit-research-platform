# 05 — P1 discovery and candidate admission

Status: **review draft; retained legacy method inventory, no P1 engine implemented**. Dependencies: [01](01_canonical_objects.md), [02](02_data_and_readiness.md), [03](03_features_targets_scopes.md), [04](04_experiment_submission.md). Policy facts below are verified by reading source and documentation, not by replaying scientific jobs.

## Decision and evidence

**User decision, 2026-10-08:** retain verified legacy P1/P2 methods as versioned policies after compatibility checks. This approves retention, not silent use of “latest,” new thresholds, new datasets or a claim that old results have been newly certified. Every run must pin the method, admission policy, implementation and sample policy actually used.

Evidence: [method documentation](../../Data/docs/empirical-signal-research.md), [Research Spec registry source](../../Data/src/research_specification_registry/registry.py), [admission registry source](../../Data/src/candidate_admission/registry.py), [admission documentation](../../Data/docs/candidate-admission-gate.md), [fixed sample design](../../Data/docs/process1-fixed-sample-compact-lineage-design.md), [generic predictor design](../../Data/docs/generalized-predictor-research.md). Registry source shows later versions beyond the older documentation headings; the explicit matrix below avoids treating those headings as active-version resolution.

## 1. Inputs

One resolved experiment supplies the parent Signal/Feature recipe, exact Target, Scope, frozen Expected Direction and Research Spec. The compiled atomic trial additionally binds scoped feature and target materializations, target-market alignment, actual eligible membership, data snapshots, exposure/period policy, method and admission policy fingerprints, code/environment manifest and required readiness evidence. An optional interaction must already be a registered ordered recipe step; P1 does not invent or execute formulas received from the UI.

Trial identity distinguishes tested asset/scope, Target/horizon, direction, Research Spec and period. These do not alter the parent predictor identity. A deterministic expansion may create explicit trials only when prescribed by a pinned Research Spec; there is no undocumented grid. Fixed/dynamic CS sampling and predictor-to-target mapping are part of compatibility, not inferred from labels.

## 2. Permitted information set

The retained locked-discovery policies require both feature decision time and complete target endpoint strictly before `2022-01-01T00:00:00Z`. Targets remain ex-post labels; their future returns cannot enter predictor computation. Features satisfy `input_available_at_max <= decision_time`; exact target and feature alignment rules are below. The generic alignment policy selects the first valid target-market observation at or after predictor availability, preserving the original source event and policy lineage.

Any different research partition requires a new explicit policy/version and exposure review. The old statement “2022–2026 locked validation” is not proof those dates remain untouched: later legacy validation was performed. Existing exposure must be carried forward. No period end is selected by this draft.

## 3. Retained calculations and exact policy compatibility

| Retained policy path | Research Spec ID/version | Admission Policy ID/version | Engine / Trial Result | Compatibility boundary |
| --- | --- | --- | --- | --- |
| FX TS locked discovery | `RSPEC_FX_TIME_SERIES_DISCOVERY_DEFAULT@1.1.0` | `APOL_FX_TIME_SERIES_DISCOVERY_DEFAULT@1.1.0` | `1.3.0` | One target instrument, exact supplied-time alignment |
| FX fixed CS | `RSPEC_FX_CROSS_SECTIONAL_DISCOVERY_DEFAULT@1.2.0` | `APOL_FX_CROSS_SECTIONAL_DISCOVERY_DEFAULT@1.2.0` | `1.4.0` | `XSAMPLE_FX_FIXED_UNIVERSE_COMMON_HISTORY@1.0.0`, complete frozen membership and verified compact dependencies |
| Generic predictor TS | `RSPEC_GENERIC_TIME_SERIES_DISCOVERY_DEFAULT@1.2.0` | `APOL_GENERIC_TIME_SERIES_DISCOVERY_DEFAULT@1.2.0` | `1.5.0` | Registered source view and predictor-target mapping/alignment; Registry snapshots `1.3.0` |
| Historical dynamic CS / prior versions | Exact original frozen references only | Exact original compatible policy | Original frozen version | Preserve/replay historical meaning; never relabel as fixed-CS or new certification |

The fixed-CS path requires the entire frozen required member set, structural common start equal to the latest member's first structurally usable date, and exclusion of an entire timestamp if any required member lacks a valid feature/target. Warm-up and target maturity apply separately after that start. A changing eligible subset must not silently use this policy.

| Method or gate | Verified retained rule |
| --- | --- |
| TS statistic | OLS with intercept `Y = alpha + beta X + epsilon`; signed beta, intercept, HAC standard error/t and Spearman IC; deterministic average ranks for ties. No implicit feature preprocessing. |
| CS statistic | Spearman rank IC at each exact decision timestamp; signed mean/median IC, HAC standard error/t of mean IC, positive/negative frequencies and section sizes. No normalization before ranking. |
| Alignment | Join anchor date and target instrument; feature `as_of` equals target `observation_time`; valid status, finite values, exact Target/horizon and no feature availability after decision time. No resampling, filling, interpolation or imputation. |
| HAC | Uncorrected Newey–West with Bartlett kernel. `maxlags = ceil(target_horizon / spacing_valid_observations) - 1`; supplied registry defaults have spacing 1. TS minimum is `max(3, maxlags+3)`; CS timestamp minimum is `max(3, maxlags+2)`. |
| Breadth | Historical dynamic CS minimum 2; fixed-CS compiler binds the complete required member count instead. |
| Stability | Three contiguous chronological approximately equal-count blocks; remainder allocated to earliest blocks. TS recomputes beta, CS averages timestamp IC. |
| TS admission | Inclusive `abs(HAC t) >= 2.0`; full-sample effect sign matches at least 2 of 3 block signs. |
| CS admission | Inclusive `abs(mean rank IC) >= 0.03`, `abs(HAC t) >= 2.0`; at least 2 of 3 block signs match the full-sample sign. |
| Deliberate limits | Discovery multiple-testing correction is not applied; OOS, walk-forward and cross-validation are not implemented by these policies. Do not label them otherwise. |

The legacy P1 gate uses observed sign and absolute statistics. **It does not establish that the effect agrees with the ex ante hypothesis.** Preserve its exact decision and separately record declared and observed direction. A statistically admitted opposite-sign result remains that historical/statistical decision; [P2](06_p2_validation.md) fails the known discovery-direction conflict before opening validation inputs. Do not rewrite Expected Direction to make it agree, and do not silently add a new threshold to the retained P1 policy.

## 4. Output units and shape

Each immutable Trial Result links parent, relationship/trial, exact inputs and all policy identities; stores sample/exclusion counts, full-sample metrics, three-block evidence, input/implementation fingerprints and execution outcome; and references detailed aligned samples, exclusions and IC history. Beta has Target-unit per Feature-unit, alpha has Target-unit, IC/t/sign frequencies are dimensionless, and counts are integers. Target return basis/horizon unit is taken from its exact definition; there is no global spot-return default.

The separate Admission Decision references a Trial Result and policy, with per-criterion observed value, operator, threshold, source field, reason and `admitted/rejected/unresolved`. A candidate relationship is never a global validated-parent state. The library exposes all attempts/results, including failed or rejected relationships, through references to these authoritative records.

## 5. Validity, readiness and compatibility gates

Before data access, verify immutability and all version combinations above; recipe/source-view/alignment equivalence; precise Target economic basis and horizon; Scope membership/exclusions before any scope-dependent transformation; period and known exposure; sample requirements; applicable certificates; and ex ante direction provenance. No old target-specific `SIGNAL_*` ID can stand in for the parent recipe ID. Historical observed direction without an independent frozen source stays unresolved historical evidence.

Compatibility review must record the selected source versions/hashes, documented divergences, and bounded equivalence fixtures before a new implementation claims retained methodology. A mismatch blocks that path; it does not authorize changing old data, thresholds or identities. Unsupported assets, Target basis, interaction recipes or dynamic-CS variants need explicit compatible policies rather than assumed extension of the FX matrix.

## 6. Failure behavior

Invalid contracts, digest conflicts and incompatible policies fail before computation. Missing data/eligibility/certificates produce explicit unresolved or blocked operational resolution. Insufficient samples, constant series, zero HAC variance, duplicate/misaligned records and invalid values retain controlled exclusions or failed calculation evidence as defined by the pinned policy. A completed statistical rejection is not a software crash. Retained gate precedence is structural failure, structural uncertainty, statistical uncertainty, statistical failure, otherwise admission; missing metrics never become zero.

## 7. Reuse and invalidation

Reuse only the exact immutable calculation inputs, scoped materializations and still-valid evidence under the same policy/implementation. Changing Target, Scope, mode or direction changes create a new relationship and trial; period or Research Spec changes create a new trial under the unchanged relationship but may reuse an unchanged scope-independent feature. Scoped transformations require matching Scope bindings. Changed data, methods or materialization dependencies create new evidence and invalidate affected descendants. Retry preserves the trial's science and adds an attempt; location changes do not alter science.

## 8. Persistence

The compact computation is a `trial_record`; its separate P1 gate decision is an
[`admission_record`](schemas/platform.schema.json), with lower-case wire values
`admitted`, `rejected`, `unresolved`. The library keeps exact links to both. Admission
is not a P2 validation decision and cannot grant P3 eligibility.

Keep compact Trial Results and Admission Decisions as authoritative immutable scientific memory; payloads and exact lineage are stored once and referenced. The library/catalog indexes parent-to-relationship-to-evidence links and never edits copied metric values. Preserve every attempt, negative result, period exposure, policy/code reference and historical identity. No migration or replay is performed in this task.

## 9. Acceptance scenarios

- TS t exactly 2.0 and two matching blocks passes the retained numeric screen; 1.999 fails it. CS additionally requires absolute IC at least 0.03. Negative relationships are treated symmetrically.
- Declared POSITIVE with observed negative beta can retain the exact legacy admission decision, but P2 reports its direction failure before validation data access; declared direction never changes.
- A missing third-block statistic remains unresolved where the gate requires evidence; it is not a zero-valued rejection.
- A 2021 feature with a target endpoint in 2022 contributes neither discovery statistics nor exposed-row diagnostics under the locked policy.
- A missing member excludes the whole fixed-CS timestamp; a dynamic subset is not silently accepted under that policy.
- Changing only the tested asset/horizon leaves parent identity unchanged, changes the relationship/trial and does not rewrite prior rows.
- Numeric equivalence, exact sample/lineage equivalence and expected failure cases must be established against frozen retained policies before engine implementation approval. These are specified tests, not tests run in this documentation task.

Remaining review: actual policy registrations/adapters, complete exposure history, bounded equivalence evidence and which new asset/basis/membership combinations pass compatibility. Numerical thresholds above are retained facts, not newly invented defaults.
