# 06 — P2 relationship validation

Status: **review draft; retained policy inventory, no new validator or certification**. Dependencies: [01–05](README.md). **User decision, 2026-10-08:** retain verified P1/P2 methods as versioned policies after compatibility checks.

## Source evidence and identity boundary

Verified by reading [P2 documentation](../../Data/docs/process2-signal-validation.md), [registry](../../Data/src/signal_validation/registry.py), [engine](../../Data/src/signal_validation/engine.py), [gate](../../Data/src/signal_validation/gate.py) and [version constants](../../Data/src/signal_validation/model.py). Source evidence describes actual old behavior; no production results were replayed here.

P2 validates the exact tested relationship, never an entire parent `SIGNAL_X`. The parent recipe is shared through Feature, while Target/horizon, tested assets/Scope, declared direction, Research Spec and period remain relationship/trial context. Old target-specific signal IDs and observed predictive direction retain their historical meaning. Missing frozen ex ante direction cannot be reconstructed from the signed discovery effect.

## 1. Inputs

Bind the exact relationship and parent recipe, P1 Trial Result and Admission Decision, discovery effect and units, ex ante direction with immutable provenance, feature/source-view/interaction/transformation/alignment versions, Target basis/horizon, Scope and membership/exclusion evidence, validation policy/window, approved exposure history, implementation and applicable data/readiness bindings. A valid P1 admission is insufficient without those bindings.

The validation specification freezes all of them before data access. A feature, interaction, parameter, direction, Scope, Target, horizon or alignment change is a new relationship/research decision, not a repair of the existing validation. For CS, preserve the discovery sampling semantics and exact membership policy; a [dynamic CS adapter](../../Data/src/signal_validation/dynamic_cross_sectional.py) is a separately identified input contract, not permission to treat every panel as fixed-universe.

## 2. Permitted information set

The retained `VWINDOW` policy starts at `2022-01-01T00:00:00Z` with an explicitly frozen exclusive end. Predictor availability, target start and target endpoint must fall in the window; no silent end extension. Rolling warm-up may require earlier predictor history but cannot introduce validation labels into predictor construction. Supplied out-of-window rows are rejected by the legacy validation engine; the production resolver may construct only the permitted inputs.

This source window is a retained policy fact, **not a claim that all dates since 2022 are untouched**. Record prior validation access and actual exposure before classifying a proposed use. A new interval/policy requires an explicit versioned decision. No validation end is invented here.

Before validation inputs are opened, compare frozen direction with discovery effect. Known conflict follows the retained failure rule. Missing direction provenance remains unresolved and cannot be cured using observed sign.

## 3. Retained calculations and policy inventory

Validation policy registry and both policies are `1.0.0`; the current inspected architecture/engine/specification/result/run path is `1.1.0`, with Gate/Ledger `1.0.0`. Historical Engine `1.0.0` remains a distinct replay path and must not be relabeled as the corrected implementation.

| Item | Verified retained calculation/rule |
| --- | --- |
| Standard policy | `VPOL_STANDARD_VALIDATION_POLICY@1.0.0` for 1, 7, 21, 63 valid-observation horizons. |
| Standard direction/magnitude | Strictly positive expected-direction-oriented validation effect; at least 0.25 retained discovery effect. |
| Standard inference | Directional HAC t at least 1.645, inclusive. |
| Standard stability | At least 2 of 3 chronological blocks have expected sign; every leave-one-block-out effect has expected sign; no block has directional t at or below -1.645. |
| Standard sufficiency | At least 15 effective observations. |
| Long-horizon policy | `VPOL_252D_LONG_HORIZON_VALIDATION_POLICY@1.0.0`, horizon 252; expected direction, retention at least 0.25, effective observations at least 4. |
| Long-horizon stability | All three segments, every leave-one-period-out estimate and every predefined robustness slice have expected sign. HAC/p values are diagnostic, not a hard gate. Always retain `LONG_HORIZON_LOW_SAMPLE_CONFIDENCE`. |
| Effective N in Engine 1.1.0 | Maximum cardinality of non-overlapping actual target-return intervals. Sort by endpoint, start and observation ID; greedily take next start >= previous selected end. Shared boundary price is allowed. |
| Historical Engine 1.0.0 N | `floor(n / ceil(horizon/spacing))`; retain for old replay only. The correction does not retroactively mutate historical results. |
| HAC | Newey–West/Bartlett, lag `ceil(horizon/spacing_valid_observations)-1`; effective-N correction does not change this lag. |
| Raw/oriented statistics | TS regression effect or CS mean rank IC; orient with the frozen expected direction. Retention is oriented validation effect / oriented discovery effect. Directional p value uses the retained normal-tail calculation. |
| Diagnostic blocks/slices | Inspected engine uses three chronological blocks, each block and leave-out estimate with `maxlags=0`; robustness slices are two chronological halves. Preserve these precise semantics rather than describing every diagnostic as full-sample HAC. |
| FDR | Benjamini–Hochberg is diagnostic only. Pin the cohort of p values used; never display a batch-wide adjustment if only a singleton cohort was supplied. |

Compatibility must establish Target/horizon units, mode, frozen sampling, actual intervals, availability, direction, policy/implementation fingerprints and sufficient usable evidence. The verified inventory does not imply every newer dynamic-panel path is compatible or every scientific edge case is resolved. New horizon units or unsupported horizons require a policy, not nearest-horizon substitution.

## 4. Output units and shape

Persist a Validation Result with relationship/trial/parent references, original legacy references if applicable, policy/window/implementation identities, raw and oriented effects, retention ratio, HAC evidence, directional p, effective N, blocks/leave-outs/robustness, FDR cohort/evidence, confidence flags, exact input fingerprint and lineage. Effect units follow P1/Target; retention, IC, t and probabilities are dimensionless; N is integer. No position or cost-adjusted profitability assertion is produced.

A separate immutable decision states `VALIDATED`, `FAILED` or `UNRESOLVED` with criterion evidence and reason codes. Only an exact currently valid validated relationship may be represented as an eligible SignalHorizon for P3. Its Target, horizon and Scope remain unchanged. A parent with one pass and several failures continues to display every relationship; it never receives blanket validation.

## 5. Validity and readiness

Verify identity consistency among candidate, original trial, policies and actual inputs. Check ex ante direction independently, validation-period exposure, complete sample/lineage, Target maturity, window bounds, certificate dependencies and implementation compatibility. P2 validation is predictive evidence, not live-data generation certification, tradability or execution approval. A historical pass may be preserved and displayed, but new P3 eligibility requires an explicit compatible relationship mapping and valid new eligibility/certification evidence.

## 6. Failure behavior

Retained Gate precedence: discovery-direction conflict → `FAILED` with `DISCOVERY_EFFECT_CONTRADICTS_EXPECTED_DIRECTION`; otherwise insufficient effective sample → `UNRESOLVED`; otherwise missing required evidence → `UNRESOLVED`; otherwise substantive direction/magnitude/stability/inference failures → `FAILED`; otherwise `VALIDATED`. Known conflict is checked before loading validation data. Missing ex ante provenance blocks resolution rather than being silently converted to a sign.

Invalid contracts, conflicting fingerprints, unsupported input geometry or out-of-window records are operational/integrity failures with preserved attempt evidence, not a completed validation decision. Do not use absent metrics as zero, erase a failed attempt or retry an exposed period as “untouched.”

## 7. Reuse and invalidation

Reuse requires the identical frozen relationship, data/sample, policy, window, implementation and still-valid readiness/exposure evidence. Changing the validation end, policy or corrected effective-N implementation creates new immutable result identity and evidence; original results remain accessible. A retry adds an attempt but never retunes the relationship. Invalidated data or certificates withdraw downstream eligibility under an explicit evidence record; unaffected relationships are not rerun automatically.

## 8. Persistence

The draft [`validation_record`](schemas/platform.schema.json) uses lower-case wire values
`validated`, `failed`, `unresolved` for the decisions above. Its `trial` references the
originating P1 trial; `evaluation_trial` references an actual P2 trial or is null when a
precheck prevented calculation. Required `research_spec`, `evaluation_period` and
`implementation` freeze the planned P2 context in either case. A validated decision requires
a P2 evaluation trial; no evaluation means no P2 metrics. Calculated effects, counts and
diagnostics belong to the P2 trial and artifacts; a validation record owns only additional
prescribed gate-derived metrics and the decision. Its evidence resolves original metrics
by reference. P1 [`admission_record`](schemas/platform.schema.json) is a separate type with
`admitted`, `rejected`, `unresolved`, and does not establish P3 eligibility.

Store exact frozen specifications, compact results and decisions as authoritative scientific memory. Reference aligned samples, block/robustness details and compact lineage stored once. Append attempt and exposure history; retain historical identities and every failed/unresolved result. Library metrics and P3 eligibility are derived views with source references, not independent editable copies. Publish evidence before a decision points to it; transaction/recovery mechanics follow [10](10_runtime_recovery_storage.md).

## 9. Acceptance scenarios

- Known declared-positive/observed-negative discovery fails before the validation resolver reads inputs, even when P1's absolute-value gate admitted it. Missing declared sign is unresolved, never inferred.
- At 14 effective intervals the standard policy is unresolved; at 15, other gates may be evaluated. Intervals sharing only one boundary count separately; overlapping returns do not.
- Standard retention exactly 0.25 and directional t exactly 1.645 meet their inclusive thresholds. A block directional t exactly -1.645 violates the no-opposite-significance rule.
- A 252-observation relationship carries the low-sample flag even when validated; its HAC result remains diagnostic.
- An endpoint equal to the exclusive window end is rejected; retries cannot extend the window.
- A 63-observation pass yields only that SignalHorizon. The library retains the same parent's 21-observation failure and its authoritative metrics.
- Compatibility fixtures must reproduce retained samples, interval count, effects, diagnostic block rules and gate outcomes before a new engine is approved. No such scientific equivalence run is claimed in this documentation task.

Remaining review gates: exposed-period inventory, exact eligible policy/input combinations, FDR cohort provenance, legacy-to-new relationship mappings, certificate/invalidation approval and bounded equivalence evidence. No automatic historical certification or engine migration occurs.
