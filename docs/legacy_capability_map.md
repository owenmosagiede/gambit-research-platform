# Legacy capability map — inspected evidence and proposed reuse

Status: **review draft, 2026-10-08**. No legacy file has been changed, imported or executed by this task. This map reads targeted documentation, compact registries and source metadata; it is not a runtime audit or certification of every historical dataset. The [CSV](legacy_capability_map.csv) enumerates every inspected operator plus store/contract decisions, with the source-file SHA-256 at inspection. Hashes cover those small evidence files, not legacy datasets.

## Transformation library findings

The [complete explanatory catalogue](transformation_library_catalogue.md) now documents every
entry below with formulas, parameters, observed implementation behavior and remaining gates.

The earlier “68 transformations” figure describes the **base univariate catalog**, not every transformation elsewhere in the old system. Static inspection of `Data/src/point_in_time_data/transformation_catalog.py` confirms 68 definitions across 15 families at library 0.1.0, matching [the legacy documentation](../../Data/docs/transformation-library.md). The catalog supplies deterministic frequency grids and pair constraints; the source metadata is canonical for this catalog.

Additional inspected capabilities:

- [Price technical source](../../Data/src/point_in_time_data/price_technical_transformations.py): 16 price-specific definitions at 1.0.0, including 13 names shared with the base catalog and three `price.*` names (`vol_normalized_log_return`, `log_return_shape`, `oriented_new_low`). A repeated name does not establish identical semantics, parameters or implementation.
- [Release-coherent registry](../../Data/derived/alfred-release-coherent/v1.0.0/transformation-registry.json): six `release.*` definitions at 1.0.0. They pin a specific release-state source view and vintage-selection meaning; applying similarly named base transforms to a final-vintage series is not equivalent.
- [Binary source](../../Data/src/point_in_time_data/binary_transformations.py): one `combine.difference` definition at 1.0.0 with ordered operands and strict same-dataset/entity/reference-period/availability/vintage/ingestion/provider-row-group matching. This is a reusable interaction candidate with limited alignment scope, not an exhaustive generic interaction library.
- The same binary source supplies one explicit additive grid extension: weekly `standard.zscore` 0.1.0 may use `w=156`, bound by an extension fingerprint. It does not alter every grid automatically.

The CSV contains **92 operator/extension rows**: 68 base + 16 price + 6 release + 1 binary + 1 extension. These are versioned catalog entries, not 92 distinct formulas. The count does not assert that no other operation exists anywhere in the legacy system. Reuse exact implementations and original IDs/versions/fingerprints through a namespaced adapter after compatibility checks; do not rewrite formulas to fit the new catalog.

## Retain / adapt / replace

| Component | Verified source evidence | Proposed treatment |
| --- | --- | --- |
| Raw/PIT | [Data README](../../Data/README.md); existing inventory | **Retain in place.** Read-only verified snapshot/locator adapters. Preserve vintages and availability precision/method, not only observation dates. |
| Transformations | Base, price and release catalogs above | **Retain semantics, adapt envelopes.** Pin library namespaces/versions, grids, parameters, code and source views. CSV has individual entries. |
| Interactions | Binary source plus base library exclusions | **Adapt the observed difference operator; specify missing general operators separately.** No claim that ratios, residuals, correlations or arbitrary composites are already reusable. |
| Feature Store | [Derived Feature Store](../../Data/docs/derived-feature-store.md) | **Retain content/lineage, adapt version-specific readers.** 1.0 single-source, 1.1 panels, 1.2 compact lineage and 1.4 partitioned panels coexist; no rewrite. Other variants require their own compatibility checks. |
| Target Store | [Target system](../../Data/docs/target-system.md), [FX excess targets](../../Data/docs/fx-excess-targets.md) | **Retain exact definitions and observations.** Historical calendar target 0.1 is not valid-observation target 0.2. Registry 0.3 adds five excess definitions to five spot definitions. Carry readiness is unverified now; preserve unavailable outcomes. |
| Trial Ledger | [Global ledger](../../Data/docs/global-trial-ledger.md) | **Retain compact authority and all results/failures; adapt references/index.** Preserve original result IDs/fingerprints and nested evidence. |
| Trial Artifact Store | [Compact artifacts](../../Data/docs/compact-trial-artifacts.md) | **Retain evidence; adapt references.** v1 detailed and v2 compact replay formats remain readable. New artifacts share histories and retain unique evidence. No compaction/deletion now. |
| Signal Library | [Signal repository](../../Data/docs/signal-repository.md) | **Replace parent identity/grouping, retain evidence.** Old signal binds target/horizon/scope/direction and admits only passed candidates. New parent binds predictor recipe; relationship records and all trials, including rejected/unresolved, sit beneath it. Never infer new expected direction from observed effect. |
| P1/P2 | [Empirical research](../../Data/docs/empirical-signal-research.md), [validation](../../Data/docs/process2-signal-validation.md) | **Retain verified methods as versioned policies after compatibility checks**, per current user decision. Preserve distinct validation effective-N versions and historical period exposure. No recalculation or blanket certification. |
| Runtime/indexing | Immutable JSON, SQLite and artifact-first behavior in ledger docs | **Adapt protocol.** New single-writer publication, recovery and query rules in [10](../specs/10_runtime_recovery_storage.md). Indexes do not become editable scientific authority. |

## Compatibility checklist and remaining limits

An adapter must resolve source dataset and source view/slice, input information-time semantics, full causal recipe and parameters, precise numerical implementation, units, scope/membership, target convention, direction provenance, Research Spec/method/admission policy, periods/exposure and evidence hashes. Each successful mapping preserves legacy namespace, ID, version and original fingerprint plus the new identity. A mismatch or absent fact remains a recorded unresolved mapping; it is never guessed from a filename or positive IC.

No old `SIGNAL_*`, `FEATURE_*` or cutoff `FEAT_*` prefix alone proves compatibility with a new object. In particular legacy `FEAT_*` can identify a logical entity/cutoff slot without hashing selected vintage bytes; exact content requires the run/lineage fingerprints and checksums. Multiple old signals can share a new parent only if their mechanical recipes match completely, while their target/scope/direction relationships remain distinct.

The storage inventory remains unchanged: Data was measured at 75.36007 GiB allocated with overlapping nested measurements and 117 multiply linked file-path entries. Writer activity was unknown. No new space/reclaimability measurement, source quiescence guarantee or full payload verification is made here.

Next bounded storage work: implement one read-only legacy adapter against one selected source/feature/target pair, with schema/reference checks and synthetic publication/recovery fixtures. Compare a bounded approved historical slice and document differences before enabling any real research execution. Broader catalog admission, migration and cleanup are separate tasks.
