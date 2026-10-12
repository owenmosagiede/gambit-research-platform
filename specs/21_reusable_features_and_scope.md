# 21 — Reusable Feature definitions and Scope resolution

## Current authority

The user explicitly corrected the FX Feature identity boundary: the selectable
Feature is the calculation recipe; Scope chooses the instruments to which it
applies. This specification supersedes the instrument-bound *selectable* Feature
model in specification 20. Existing historical Feature and Signal IDs retain their
original meaning and remain retrievable. No scientific calculation rules change.

The recently registered 180 approved FX configurations are now canonical reusable
Feature recipe definitions. Their input contract, exact ordered operators,
parameters, grid policies, execution/history/evaluation policies and output unit
rules determine identity. Instruments, universes, source snapshots, date ranges,
materialization status and labels do not determine this reusable identity.

The input contract requires the existing positive-or-controlled-null canonical FX
close-price profile, preserving unknown availability and the approved weekday
clock. Currency units are bound from the selected instrument when resolving or
preparing outputs. The 23 log-first operator families retain Log followed by BASE;
the seven internal-log-basis families consume price directly with basis=log. No
operator, grid, parameter, timing policy or numerical calculation is changed.

## Additive registry and historical compatibility

Schema 0.7 adds two strict record kinds to the existing Feature Store:

- `feature_recipe_definition`: `definitions/feature_recipes/FEATURE_RECIPE_<digest>/1.0.0.json`.
- `feature_recipe_registration`: `storage/catalog/feature_recipes/FEATURE_RECIPE_REGISTRATION_<digest>/manifest.json`.

The executable structural and identity contract is
`src/data/reusable_feature_contracts.py`. `src/data/reusable_features.py` additionally
validates exact approved registry semantics and historical source bindings.

The completion record pins all prior registration catalogs and maps each shared
configuration to its reusable definition. The pinned catalogs retain all 7,740
instrument bindings and their original Feature references. Registration verifies
all those references before publishing the new completion record. It adds 180
new shared definitions, never 7,740 replacement instrument definitions. Repeating
registration reuses the same identities. Existing observations, source data,
Signal entries, materializations, trial records and lineage are untouched.

Run `tools/register_reusable_features.py` to install this additive mapping. This
command does not prepare observations or run research.

## Selection, preparation resolution and coverage

`GET /api/feature-library` supplies the Feature dropdown from registered definitions:
180 shared FX recipes, plus existing non-FX Feature definitions. Registration alone
is sufficient for visibility. Historical FX Signal entries remain in the Signal
Library and are not duplicated as currency-prefixed Feature options.

Catalog reads use the completed registration and pinned semantic definitions.
Missing current preparation configuration or unavailable individual source files
do not remove registered recipes from the selector. Such problems are reported
when resolving readiness, with member-specific failures isolated where possible.

`GET /api/feature-resolution` requires exact `feature_id`, `feature_version`,
`scope_id` and `scope_version`. It resolves membership through the existing Scope
registry, binds the reusable recipe to current per-instrument source snapshots,
and verifies any candidate stored materializations through the existing reader.
It reuses matching legacy outputs by reference, without copying observations.

Reuse requires matching canonical recipe semantics, instrument selection, current
source view and snapshot, approved materialization policies and configured actual
knowledge cutoff. Altered, stale, incompatible or corrupt results are not counted
as ready. Every Scope member remains in the response, including missing and
blocked members. Exact stored periods, row/status counts, cutoff and readiness
are reported for each matching materialization. No selected output period is
invented; a 64-row sample means precisely that stored sample, not full history.

The read-only preparation binding identifies the existing source-bound Feature,
source snapshot and policies for the existing preparation pathway. An output
period remains required for any later explicit preparation request. Changing
Feature or Scope calls no registration, materialization, publication or research
writer. There is no new computation endpoint or background preparation job.

Existing non-FX source-bound Features remain selectable with their stored source
coverage and Signal details. Applying such a source (for example CES wages) across
FX members is reported separately as requiring an explicit research application
rule; this task does not invent replication, alignment or eligibility rules.

## Readiness and preserved boundaries

Registration, existing observation coverage, retrospective research readiness,
historical replay eligibility and live eligibility remain separate. Existing FX
samples retain null historical availability, retrospective-only preparation
semantics and untested scientific status. Selecting FTMO_UNIVERSE does not alter
a Feature definition or certify full-universe Feature coverage, broker eligibility,
historical decision-time availability or live operation.

Acceptance checks cover canonical identity, all 180 approved configurations,
7,740 unchanged historical bindings, compatible stored-output reuse, rejection of
stale policy/source bindings, per-member missing coverage, individual/universe
identity parity, safe UI request races and zero writes on selection. P1/P2 and
bulk Feature materialization are outside this task.
