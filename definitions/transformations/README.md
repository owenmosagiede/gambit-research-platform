# Transformation definitions

This directory contains **98 approved version 2.0.0 operator registrations**: 68 base aliases,
16 distinct price aliases, six generic release aliases and eight new direct-input primitives.
The authoritative record is `definitions/transformations/<id>/2.0.0.json`, using the existing
`transformation_definition` with a closed `body.execution_contract`. The runtime registry reads
these files; no second executable registry exists.

Read the generated [active library and exhaustive explanations](../../docs/transformation_library.md)
for formulas, parameters, examples, units, temporal capabilities, legacy mappings and tests.
The [historical source catalogue](../../docs/transformation_library_catalogue.md) remains unchanged.
It records the earlier audit, not the new numerical certification.

The 98 registrations share 79 numerical kernels plus one generic release-event-history
operation. Repeated price names retain separate applicability and grid policies. Eight new
primitives add causal lag, rolling sum, direct sample SD and five direct-input distribution
statistics. Interaction `combine.difference` is excluded. The weekly156 z-score extension is a
separate versioned parameter permission under `definitions/policies/`, not an operator.

`src/data/transformations/registry.py` resolves exact pinned definitions and policies, validates
parameters and performs explicitly bounded grid enumeration. Mathematical validation does not
implicitly enumerate research recipes. Definitions use canonical decimal strings and preserve
legacy identity/source fingerprints in their mapping. Version2 deliberately allows zero
*descriptive* SD while keeping division by zero deviation undefined.

Ordered recipes retain the existing `predictor_recipe` contract in `definitions/features/`.
Calculated observations belong in the payload store and Feature catalog, following
[the storage contract](../../specs/12_data_pipeline_and_storage.md). No production Feature
or Signal definitions or observations are created by this foundation.

Operator certification is separate from source eligibility. Release operators require explicit
revision history and anchored release-event capabilities from a certified SourceView; a dataset
being numeric or available through an API does not establish those capabilities.
