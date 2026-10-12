# Authoritative scientific definitions

Review-draft definition documents follow the closed schemas in
[platform.schema.json](../specs/schemas/platform.schema.json) and the exact path templates in
[storage specification](../specs/12_data_pipeline_and_storage.md). The original specification task registered only synthetic examples. The subsequent
[full-history ALFRED package](../docs/alfred_full_history_report.md) supplies a real provider, dataset, source view and
seven scoped technical policies at the current versions. The obsolete pilot-only definitions
were removed with the [redundant sample package](../docs/alfred_sample_removal.md); subsequent transformation and Feature registrations are documented in their own implementation reports. Research definitions remain separate work.

- providers: pinned provider/series API and vintage-capability contracts.
- datasets: source-series meaning, economic units, dimensions and availability/vintage semantics.
- source_views: exact source definitions/selections and registered PIT view rules.
- interactions: approved typed combinations, ordered operands and alignment/validity policies.
- transformations: namespaced, versioned transformations and exact allowed parameter contracts.
- features: the single authoritative predictor recipe. Its derived Signal ID groups all tested
  target/asset/horizon relationships without duplicating the recipe in another editable registry.
- targets: executable 0.4 continuous investment return definitions under [specification 18](../specs/18_return_targets.md), with exact source economics, representation/comparison, schedule, horizon and availability. The production registry remains empty until a certified market source is admitted.
- scopes: instruments/universes and effective membership/exclusion/eligibility rules.
- research_specs: TS/CS evaluation and versioned period, test, admission and validation policies.
- policies: reusable versioned rule definitions referenced by the other contracts.
- mandates and venue_profiles: downstream portfolio/execution contexts, never hidden research inputs.

Feature/Target definitions are not their observation histories. Observations live in the
payload store, with materialization manifests and catalog indexes. Library metrics resolve to
authoritative trial/validation results. Catalog indexes are rebuildable references, not a
second source of definitions. Raw/PIT legacy stores stay external and read-only for this task.

Registered operator specifications are declarative references to reviewed behavior. Submissions
and parameters never contain executable Python/SQL or an unreviewed formula. An empty folder
or synthetic fixture is not a registration, readiness certificate or scientific result.

Target policies and definitions are constructed and validated by `data.targets.contracts`.
Actual source records, finite anchors, resolved intervals and outcomes belong to immutable
materializations in the existing shared store. Historical 0.2 Target schemas are preserved
and are not production registrations. See [Target library](../docs/target_library.md).
