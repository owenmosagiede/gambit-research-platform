# 03 — Registered definitions and the data-to-research boundary

> Target update: [specification 18](18_return_targets.md) supersedes this document’s
> draft Target construction/observation clauses with executable 0.4 return-only contracts.
> Legacy valid-observation horizons below remain historical evidence and are not silently
> reused as the new scheduled-session/bar horizons. Other definitions retain their authority.

Status: **reviewable implementation specification**. Depends on [01](01_canonical_objects.md),
[02](02_data_and_readiness.md), [04](04_experiment_submission.md), [12](12_data_pipeline_and_storage.md)
and the [machine schemas](schemas/platform.schema.json). Definition documents are source
assets; registering them, calculating values and certifying readiness are later implementations.

## Required flow and typed branches

The user requested `raw → PIT → optional interactions → transformations → feature/target stores`.
Operationally this is a directed, typed pipeline:

```text
External raw sources → canonical PIT snapshots and source views
                         ├─ optional causal interactions → registered transforms → Feature Store
                         └─ registered exact future-outcome construction           → Target Store
Feature Store + Target Store + Scope + declared direction + Research Spec
                         → P1 trials/admission → P2 validation
                         → Trial/Validation ledgers + linked Artifact Store
                         → parent Signal library with every tested relationship
```

The shared transformation library supplies registered operations where the construction
contract allows them. Targets are deliberately ex-post outcomes, not generic predictor
transformations or observations that may be read as features. Target maturity, basis and
horizon are enforced by their own definition and constructor. Keeping their values in a
separate store prevents future labels leaking into causal predictor computation.

## Definition contracts

All definitions have an exact version, immutable scientific content digest and closed schema.
Authoritative locations are specified in [12](12_data_pipeline_and_storage.md). No raw Python,
SQL or user-supplied executable expressions are permitted in scientific submissions or recipe
parameters. Calculation behavior is resolved through reviewed registered operator/policy IDs.

| Definition | Required meaning | Explicit exclusion |
| --- | --- | --- |
| Dataset | Economic variable, source-series identity, entity/dimensions, units, frequency and availability/vintage semantics | A folder or provider endpoint is not its scientific identity |
| Source View | Exact Dataset bindings and selection, PIT vintage policy, source cutoffs and series/collection geometry | No mutable newest-vintage selector applied retroactively |
| Interaction | Typed arity, ordered operands, alignment, units, mathematical validity, versioned implementation contract | No arbitrary combination grid or unregistered operand substitution |
| Transformation | Library namespace, operation/version, parameter contract, causal input geometry, output units, warm-up/failure policy | Same short name is insufficient to equate distinct legacy catalogs |
| Feature / Signal recipe | Dataset/source-view bindings and ordered registered operations with exact parameters and scope requirements | No target asset/horizon, observed IC, evaluation direction or period in parent identity |
| Target | Exact outcome construction, economic return basis, units, horizon clock/count, orientation, maturity and admissible source roles | No conversion between calendar days and observation counts by label alone |
| Scope | Instrument or universe, membership/exclusion/eligibility semantics and versioned policies | Evaluated scope is not an after-the-fact filter for scoped calculations |
| Research Spec | TS/CS mode, selected evaluation period, alignment, sampling, tests, inference, admission and validation policy bindings, applicability and approved implementation | No hidden trading mandate, capital, venue or direction inferred from results |

One Feature definition is authoritative for one parent Signal. A signal's readable name may
include dataset and transformation labels; its stable ID comes from the complete recipe.
Separate labels never become independently editable scientific definitions.

## Legacy reuse decisions

The user selected retained verified P1/P2 methods under explicit versioned policies. Reuse is
conditional on a recorded compatibility/parity check, not copying every old behavior. The
[capability map](../docs/legacy_capability_map.md) lists observed catalogs, schemas and source
implementations and assigns RETAIN, ADAPT, REPLACE or DEFER with reasons.

The 68-operation univariate core, binary combination, grid extensions, price-technical
operators and release-coherent transformations must keep their distinct versioned identities.
A display name collision never merges their semantics. Optional interactions are supported
only to the extent an exact existing or newly reviewed definition permits them; there is no
assumption that an exhaustive general Interaction Library already exists.

Legacy targets retain their historical meanings: spot Target 0.2.0 uses 1/7/21/63/252 subsequent
valid observations and simple price returns; the additive 0.3.0 registry includes separate
excess-return definitions. A historical carry-readiness claim is not a fresh certification.
No default return basis is silently selected. Exact target versions can coexist in the new
registry when admissibility, maturity and source capability have been verified.

Legacy transformation grids define admissible parameters; they do not by themselves authorize
running every combination or expand a single five-input submission into an undisclosed search.

## Transformation contract and acceptance requirements

| Dimension | Implementation requirement |
| --- | --- |
| Inputs | Registered definitions + immutable source snapshot/view + approved parameters + applicable Scope binding; no path-based scientific inputs |
| Permitted information | Feature inputs known by their anchor/cutoff; target labels usable only after maturity; each historical vintage chosen at its own as-of cutoff |
| Calculations | Dispatch only a compatible versioned registered operator; preserve exact legacy formulas/parameters where retained, including operand order and warm-up/failure behavior |
| Output units/shape | One schema-defined causal feature or ex-post target observation per declared entity/time slot, value or explicit failure; no substituted zero |
| Validity | Verify operator arity, parameter rules, source alignment, units, geometry, scope membership and input completeness before accepting a materialization |
| Failure | Retain explicit null/failure reason, missing readiness or unsupported operator; do not shorten windows, fill gaps or switch policies silently |
| Reuse/invalidation | Recipe may be reused; actual values require matching data/code/availability/scope/randomness state and coverage; definition or dependency changes invalidate affected outputs only |
| Persistence | Definitions once; observations once in content-addressed payloads; store manifests and catalog links preserve exact source lineage; separate target payloads |
| Acceptance | Test recipe identity across targets, parameter-induced identity changes, known operator vectors, PIT revision/as-of cases, ordered binary operands, scope-before-rank, target endpoints and no-lookahead joins |

## Unresolved scientific choices that block affected calculations

P3 calibration basis and P4 common return clock are not decided by reusing legacy target labels.
Exact parameterizations of new interactions or operators require review; no methods beyond
verified retained definitions are authorized. Target-source readiness must be established for
each selected asset/outcome. The [decision register](../docs/specification_decisions.md) lists
remaining gates and who must resolve them. These open gates do not prevent building closed
storage schemas and a truthful submission intake.


## Implemented transformation foundation update

[Specification16](16_transformation_execution.md) now implements the scoped single-series
operators, canonical execution envelopes, recipe identities and fixture-only computation.
Existing0.2 definition/Feature/Signal conventions are reused. Date-aware transient results
have an explicitly tagged execution identity profile; they are not published production
materialization manifests. Definition registrations remain separate from observation stores.
No Feature observations or Signal registrations were produced by this foundation task.
