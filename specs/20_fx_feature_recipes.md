# 20 — FX log recipes and bounded Feature preparation

## Authority and verified scope

The user requested the 23 log-first and seven internal-log-basis variants in the
FX log recipe review, then explicitly approved every existing daily parameter
combination across the 43 registered pairs. The review was compared with all 98
executable operator definitions, exact file hashes, formulas, kernels, input/output
semantics, temporal contracts and grids. No discrepancy was found. No operator
implementation or approved grid was changed.

The approved grids yield 180 shared configurations and 7,740 instrument bindings.
A configuration is a catalog grouping, not a new canonical predictor identity.
Each binding reuses the existing Feature/Signal identity calculation: exact source
view, instrument selection, transformations, typed parameters and policy versions.
Consequently there are 7,740 canonical source-bound recipe definitions. Equivalent
existing definitions are reused; presentation labels never cause duplicates.

Only the 23 requested operators receive Log as a first step. The seven operators
with a basis parameter receive raw positive prices and basis=log in a single step.
The 14 optional variants, excluded ratios and TR_PRICE operators are untouched.
Operators that already difference input levels do not receive an extra difference.
Composed output units and semantics follow the executable contracts without
relabeling a generic log-level difference as a percent return.

## Existing stores and interfaces

| Item | Location relative to research_platform |
| --- | --- |
| Canonical recipes | definitions/features/FEATURE_<digest>/1.0.0.json |
| Versioned evaluation policy | definitions/policies/POL_TRANSFORM_EVALUATION_FX_SNAPSHOT/2.0.0.json |
| Approval and registration index | storage/catalog/onboarding/evidence/EVIDENCE_<digest>.json |
| Feature manifests | storage/catalog/feature_store/MATERIALIZATION_<digest>/manifest.json |
| Observation/code/evidence payloads | storage/payloads/sha256/<prefix>/<digest>.<format> |
| Input and per-observation lineage | storage/catalog/lineage/LINEAGE_<digest>/manifest.json |
| Verified materialized Signal projections | storage/catalog/signal_library/ |

`tools/fx_features.py register --review <review.txt> --request <request.txt>`
verifies contracts, rejects conflicts before publication, registers definitions and
publishes the completion catalog last. It never computes observations.

`tools/fx_features.py list --instrument AUDUSD --limit 100 --offset 0` and
`GET /api/feature-recipes?instrument_id=AUDUSD&limit=100&offset=0` expose registered
bindings with explicit registered_unmaterialized/materialized states. Paging is
required; only verified persisted Features are selectable.

`tools/fx_features.py prepare --instrument AUDUSD --operator
TR_BASE_momentum_skip_diff --parameters '{"k":63,"s":5}' --start 2024-01-02
--end 2024-03-29` resolves one exact registered binding and prepares that bounded
interval. The default actual knowledge cutoff comes from the existing approved FX
completion configuration. No bulk materializer is introduced.

The existing Signal API and Feature dropdown discover successfully published
samples automatically. The UI displays the full transformation chain and truthful
FX timing/source metadata. Registration alone creates neither a selectable Feature
nor trial/validation statistics.

## Explicit snapshot-retrospective profile

The generic PIT executor requires known availability and a different daily-gap
contract. Stored FX histories have unknown historical availability. A separate,
strict 0.6 record profile therefore extends the existing Feature Store dispatch
without changing the CES 0.3 path or weakening the generic executor.

- Pin the exact existing FX price snapshot and approved retrospective alignment.
- Preserve available_at=null and historical_eligibility_certified=false.
- Resolve one captured state at a fixed actual knowledge cutoff; this is not
  historical decision-time replay. Reject any source captured after that cutoff.
- Reuse RESEARCH_WEEKDAYS version 1.0.0: Monday–Friday, no holiday exclusions.
- Retain missing scheduled weekdays as nulls; exclude weekends from operands.
- Use existing approved daily grids on this explicit weekday observation clock.
- Warm up from preceding stored scheduled history, but persist only the requested
  output interval (at most 366 calendar days inclusive per verification sample).
- Keep interval, cutoff, exact snapshot and code manifest in materialization
  identity, never as permanent limits on the logical Feature or Signal.
- Pin the approved existing numeric kernels. Do not double log or insert differences.

The strict executable record contract is `src/data/fx_feature_contracts.py`.
A scheduled-input record stores exact source row IDs/hashes and missing slots.
Each output points to that record and its causal prefix. This is explicitly an
audit superset, not a claim that every preceding row was numerically necessary.
The full snapshot, code, policies and output hashes are also pinned. Retrieval
verifies source construction, closure, schedule, arithmetic, lineage and metadata.
Only a validated completed materialization receives a Signal Library projection;
all-null preparation leaves the recipe registered only. Retries reuse immutable
identities and do not rewrite prior results.

## Remaining limits

The samples are eligible for the currently approved retrospective data preparation
profile only. Historical source timestamps, price basis, synchronized valuation
clocks and live use remain unresolved. P1/P2 engines and executable Research Spec
policies are not implemented in this workspace. This addition does not create or
run research trials, claim historical tradability, or confer statistical validation.

The next bounded research task is to specify and implement one retrospective
P1→P2 execution path using these stored Features and existing Price Return Targets,
with explicit admission, alignment and validation policies and authoritative trial
records. Exhaustive materialization requires a separate task.
