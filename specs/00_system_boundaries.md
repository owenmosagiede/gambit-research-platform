# 00 — System boundaries

Status: **review draft; no engines or UI implemented**. Interfaces below are design requirements, not a claim that the referenced objects or services already exist. [01](01_canonical_objects.md) owns canonical identities and [03](03_features_targets_scopes.md) owns recipe/definition semantics.

## Authority and decisions

**User decisions, 2026-10-08:** retain verified legacy P1/P2 methods as explicit versioned policies after compatibility checks; P4 constructs trading sleeves and P5 allocates shared capital. The actual P4/P5 capital-feedback and aggregate-feasibility algorithm remains open. These decisions supersede the original foundation's unresolved ownership note without changing the preserved P3/P4 source.

**Source requirements:** preserve [P3/P4 intended design](references/p3_p4_design_reference.txt), separate research from capital and execution, consume canonical objects, and keep all legacy locations read only. **Proposals:** the interface/readiness rules below complete a reviewable design, not a new implementation authorization. **Verified facts:** legacy [Signal Repository](../../Data/docs/signal-repository.md) identities are target/scope/horizon-specific and derive direction from observed results; [legacy P2](../../Data/docs/process2-signal-validation.md) uses an independently sourced ex ante direction and calls old P3 “system admission.” Neither convention is silently renamed into a new parent Signal or the new forecasting P3.

## Identity and ownership

A parent `SIGNAL_X` represents the predictor recipe: source dataset identity, source-view/slice, and the ordered optional interactions and transformations with exact parameters and versions. Tested assets, Target/horizon, research Scope, Expected Direction, Research Spec and research period do not enter that parent identity. A source-side slice describes what the predictor is; it is not a tested target asset or research Scope. `definitions/features/` holds the one authoritative recipe. The existing Feature input resolves to that parent; there is no sixth scientific input or second editable Signal recipe.

Each tested relationship links that parent to the exact Target/horizon, Scope/assets, frozen direction, Research Spec and periods through canonical experiment/trial identities. A library view includes **all tested relationships**, including failures, rejections and unresolved work. Its displayed statistics dereference authoritative trial and validation evidence. It cannot promote the parent as a whole or treat one passing horizon as approval of another. P3 consumes only the exact currently valid P2-certified SignalHorizon relationship. Historical mappings preserve original identities and evidence; missing ex ante direction remains unresolved rather than being inferred from an observed coefficient.

## Data and process flow

```text
external raw evidence → normalized PIT store
                            ├→ bound source view/slice → optional interactions
                            │   → ordered transformations → feature store
                            └→ explicit Target construction → ex-post target store
feature + target + Scope + frozen direction + Research Spec
  → resolved experiment/trials → P1 evidence + admission → P2 evidence/decision
  → eligible SignalHorizon → P3 InstrumentHorizonForecast
  → P4 trading-sleeve construction ↔ P5 shared-capital allocation
  → feasible, authorized execution intent → execution/reconciliation
```

The Target branch is typed as ex-post realized outcomes and becomes available only when its required endpoint/dependencies are available. It must never be consumed as an as-of predictor. Interactions are optional registered calculations, never guessed economic pairings. Scope binds before any operation whose meaning depends on scope; a parent recipe may be shared while its scoped materializations differ. After normalization, science cannot branch on provider name; provenance remains in lineage.

| Owner | Consumes | Produces | Boundary |
| --- | --- | --- | --- |
| Data/definitions | Raw/PIT evidence, registered policies and recipes | Canonical observations, scoped features, separate targets, readiness evidence | No research statistics or implied live certification |
| P1 | Resolved trial and compatible method/admission policies | Trial evidence and immutable candidate decision | Discovery admission is not validation |
| P2 | Frozen relationship and evidence, exposure-aware window/policy | Validation evidence/decision; eligible SignalHorizon when valid | No retuning or portfolio approval |
| P3 | Exact validated relationships and PIT histories | Individual forecasts and InstrumentHorizonForecast | No positions; family metadata never replaces constituents |
| P4 | Forecasts, risk/cost/venue/mandate and allocated-capital context | Sleeve TargetPosition and RequiredTrade | No authority to allocate the shared pool |
| P5 | Sleeve contexts/proposals, shared pool and aggregate constraints | Versioned capital allocation and aggregate feasibility context | Cannot retroactively change research or silently rescale infeasible trades |
| Execution | Exact final proposal plus explicit authorization and current reconciliation state | Orders/fills/reconciled state | RequiredTrade alone is not permission to send orders |

## Universal transformation contract

Every stage specification must define these nine dimensions. A missing scientific choice blocks that affected stage, not unrelated documentation or existing evidence.

| Dimension | Cross-system invariant |
| --- | --- |
| Inputs | Immutable typed canonical references and explicitly applicable policies; paths are locators. |
| Permitted information set | Declare as-of time, availability, mature labels, scope membership and exposure restrictions. |
| Calculations | Pin recipe order, policy/implementation versions and randomness; no implicit defaults or executable form text. |
| Output units and shape | Type economic units, horizon clock, instrument/scope axes and evidence status; no ambiguous `D` or uncertainty scalar. |
| Validity/readiness | Certify the exact dependency state and policy; distinguish historical replay from live generation. |
| Failure behavior | Keep invalid contract, unresolved dependency, operational failure and scientific rejection distinct. |
| Reuse/invalidation | Reuse unchanged valid dependencies; changed semantics invalidate affected descendants only. |
| Persistence | Preserve compact evidence, exposure, failures and lineage; payloads once; library/catalog are projections. |
| Acceptance tests | Verify temporal isolation, identity boundaries, typed handoffs, invalidation and truthful statuses before production. |

## Acceptance scenarios and remaining gates

Changing only tested asset or horizon leaves the parent identity unchanged but creates a different relationship; changing recipe order changes the parent. A scoped rank transform under two universes has distinct scoped materializations. A validated 63-observation relationship never creates a 7-observation forecast. A legacy observed-positive record without ex ante evidence remains historical-only. P4 cannot commit a proposal under a changed P5 allocation without rechecking feasibility. A recorded request with no executor is never displayed as running.

Remaining gates: exact P3/P4 return clock, forecast-error versus expected-return-estimation uncertainty, estimation timelines, P4/P5 feedback/feasibility protocol, complete production registries and readiness evidence. This review draft neither migrates legacy evidence nor certifies the new pipeline.
