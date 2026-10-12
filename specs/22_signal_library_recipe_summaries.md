# 22 — Signal Library reusable recipe summaries

The Signal Library presents every registered selectable Feature, including
unmaterialized and untested definitions. This supersedes the earlier stored-output
inclusion boundary at the user's request on 2026-10-10. Reusable FX recipes have one
summary per configuration. Existing non-FX entries, including CES, retain their
source-bound presentation and historical identity.

## Read-only projection and identity

`GET /api/signal-library-summaries` returns grouped presentation entries. It joins
historical Feature records through the existing immutable reusable-recipe mapping
and verifies their exact references and canonical recipe projection. Different
parameter configurations remain separate even when readable titles coincide.
No new Signal identity, recipe definition, observation or research record is saved.

FX summaries use a readable recipe title, the required input type from the recipe
contract (`Closing prices` for the current close-price recipes), and the actual
ordered operators and parameters resolved from the reusable registry. The title
and the `Skip Recent Difference` caption are presentation aliases; canonical
operator names, IDs, versions, parameters and existing dropdown labels are intact.
The momentum configuration k=63, s=5 displays:

| Field | Value |
| --- | --- |
| Signal | Log Skip Recent Momentum |
| Source | Closing prices |
| Transformation | Log Level → Skip Recent Difference (k=63, s=5) |
| Observations | N/A |
| Research status | Untested when no research exists; otherwise the recorded research status |

N/A means observation count is not a property of a reusable definition; it does
not mean outputs are missing. Counts and library cards reflect grouped entries,
with transformation parameters available to distinguish configurations.

## Expanded stored outputs

Selecting a recipe opens its grouped output details. Individual instruments,
providers, exact observation/status counts, date coverage, readiness, original
Signal/Feature/materialization IDs and lineage remain attached to their specific
outputs. Existing 64-row samples do not establish coverage for another instrument
or the full history. Selecting an output reads its exact materialization.

`GET /api/signal-library-outputs/<SIGNAL_ID>?materialization_id=<MATERIALIZATION_ID>`
uses the existing strict materialization reader and verifies immutable published
Signal/Feature/materialization links. The original Signal endpoints remain
available. Existing Feature coverage links retain exact historical IDs and are
routed to the corresponding grouped entry and output.

## Research outcomes

Preparing observations is not research. Empty relationship links display
Untested. Nonempty links are retained by original Signal, exact projection and
relationship, with trial/admission/validation references and attempt IDs intact.
They display `Research results linked`, never a recipe-wide success status.
Metrics are not copied, averaged or inferred. Scope, Target, horizon, direction,
Research Spec and period remain owned by their authoritative relationship/trial
records. The list reads authoritative relationship/link envelopes without loading metric
artifacts. Opening a definition with research retrieves and verifies authoritative
results through the existing research-results API. Preparation never becomes a
research result, and a linked outcome is not universal recipe validation. If
research metadata cannot be checked, show an explicit unavailable status.

## Responsive loading and verification boundary

The UI first loads the Feature registry, then enriches those cards with stored
output metadata and research references. Registration alone is enough to display
a Signal. Until enrichment finishes, coverage and research are explicitly pending.
A failed enrichment leaves registered definitions visible with a retry message;
requests time out after 20 seconds instead of waiting ten minutes.

The summary API verifies catalog references and reads manifest-declared counts and
coverage without reading all observation/lineage payloads. It marks output metadata
as `catalog_metadata_only`. Opening an output verifies that exact materialization
through the strict reader. A corrupt payload therefore does not hide its registered
recipe, but cannot be presented as verified observations.

With no filters, empty-output definitions remain visible. Provider/date filters
refer to actual stored outputs and require both conditions on the same output;
definitions with no matching stored coverage do not match those filters. Search and
research status filters remain available for registered definitions.


## Preserved boundaries

Experiment inputs and their Feature/Target/Scope resolution are unchanged. This
change performs no migration, materialization, provider acquisition, research,
P1/P2 execution or scientific policy alteration. It writes code, tests and this
specification only; all existing scientific records and payloads are preserved.
