# Feature application foundation, version 1.0.0

Implemented 2026-10-10. This is an additive application capability layer. It does not modify Feature recipes, source observations, scientific thresholds, or the meaning of Expected Direction.

## Verified executable applications

| Application | Feature input | Individual Scope | Universe Scope |
| --- | --- | --- | --- |
| `per_instrument_input` | Reusable FX recipe with the existing strict FX input contract | Own instrument inputs; TS | Each member's own inputs; CS only |
| `selected_single_series` | One explicitly selected stored source series | Existing availability-aware TS alignment | Rejected; no broadcast or TS fan-out |
| `entity_mapped_series` | Future explicitly mapped source entities/operands | Disabled | Disabled |

“External” is not a scientific data type or an assertion that a provider's data cannot support CS. The enabled single-series adapter describes the current selected series' application. Entity-specific provider data requires a separate approved application contract and adapter.

These capabilities do not certify all hypotheses as economically meaningful. Current adapters preserve the existing Feature and raw Target orientations. They do not invert FX quotes, flip Expected Direction, infer countries from currency codes, or apply base-minus-quote arithmetic. Expected Direction remains the prespecified Feature–Target relationship. Existing alignment, missing-value, scheduled-horizon, phase-isolation, and P1/P2 rules remain authoritative.

## Exact storage and identity

- Application contracts: `definitions/feature_applications/contracts/<application-id>/<version>.json`.
- Exact Feature bindings: `definitions/feature_applications/bindings/<feature-id>/<feature-version>.json`.
- Each binding contains schema version `1.0.0`, the exact canonical Feature reference, and the application contract's ID, version and SHA-256. Exactly one application binding exists per selected Feature version in this initial foundation. Changing one requires an explicit versioned evolution, not overwrite.
- Contract fields: `schema_version`, `id`, `version`, `kind`, `adapter`, `definition_type`, `scope_modes`, `input_binding`, `orientation`, `comparability`, `alignment`. Unknown or changed contract contents cannot execute merely because a JSON file claims approval.
- Bindings are outside recipe identities. Existing 180 reusable recipes, instrument-bound records, observations and historical references are retained.
- `tools/install_feature_applications.py` explicitly installs bindings for the verified existing selectable catalog. It is idempotent. Neither selection nor execution installs missing bindings.

## Resolution and execution

`research.feature_applications.resolve` verifies the exact definition and binding, installed contract bytes, available implementation, explicit Scope kind, and nonempty unique membership. No ID prefix determines application semantics. Missing contracts fail closed with a structured blocker.

`api.feature_library.get_feature_resolution` uses this resolver alongside existing stored coverage. Its `application` field contains the resolved contract and binding; `submission_compatible` communicates application compatibility. A native application still passes full source, Target and policy validation during Submit. Registration, existing output coverage, retrospective eligibility, historical certification and live readiness remain separate.

`runtime.research_jobs.ResearchJobs.submit` selects the existing Research Spec through the registered application and freezes application semantics before accepting a new production request. Native FX retains deferred full input planning in the worker so submission does not synchronously scan all Target coverage. The existing single-series path retains its full metadata preflight. The worker verifies that its resolved application exactly matches the submitted contract before preparing data. `research.inputs.resolve_plan` uses the same application resolver, then the existing preparation adapters and policy checks. No preparation is triggered by selecting a Feature or Scope.

New plans include `feature_application` (binding, contract, mode, Scope kind, null entity mapping). The existing plan already freezes Scope/membership, source and Target snapshots, profile, alignment policy, cutoff and periods. Application semantics participate in the plan and relationship identities; trial reuse remains tied to exact scientific inputs. Observation reuse remains governed by existing source/recipe/policy checks. No source-specific Feature definition is added by this layer.

Historical plans lacking this additive field remain readable under their existing contracts. Records are not rewritten. Existing runtime implementation-fingerprint safeguards remain in force: resuming an older submission after a code change may be blocked rather than silently changing its implementation.

## UI and service upgrade

Feature, Target, Scope and Expected Direction remain the existing inputs. The selector consumes application compatibility separately from materialization counts. A compatible unmaterialized FX recipe remains selectable. Unsupported stored-series/universe combinations remain disabled.

The current server may continue running the previous backend while research is active. For that transition only, the UI accepts the old native coverage response, which lacks both capability fields and identifies its verified recipe kind as `reusable_fx_recipe`. The new API always includes both fields; missing/unsupported bindings return false/null and cannot enter this fallback. Stored-series selections always require affirmative compatibility. Restart the server when its queue is idle to activate the new backend; do not interrupt active research to roll out this foundation.

## Deferred provider decisions

No BIS data or entity mapping is installed. A later provider onboarding must establish source entity type and identity, measure/dimensions/units, availability/revision/freshness rules, exact entity-to-instrument operand mappings, orientation and comparability, and missing/ambiguous-member rejection rules. Source snapshots and mapping/policy versions must be frozen in execution and reuse identities. Mapping supplies operands; any arithmetic belongs in a versioned recipe. This reserved application cannot execute until those decisions and an adapter are implemented and tested. The foundation grants no provider-specific scientific approval.
