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
Authoritative P1/P2 metrics are not copied, averaged or inferred. The separately specified P3 incremental-contribution aggregation below never averages P1/P2 outcomes or replaces their evidence. Scope, Target, horizon, direction,
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


## P3 incremental-contribution ranking — specified future extension

The user requests the Signal Library to become a ranked view from the greatest
incremental contributor down to the worst measured signal. [27](27_p3_incremental_value_and_library_ranking.md)
is the contract for that extension. P3 owns full-versus-without-signal evaluation
and publishes the results as derived Signal metadata; the library projects them.
This section specifies future behavior, not an already deployed ranking API/UI.

The signal name in each ranked or unranked row remains a clickable link to its
existing complete research page. That page retains every original definition,
pair/Scope, horizon/Target/direction/period, saved P1/P2 outcome and evidence,
including failures and unresolved results. P3 memberships, per-model ranks and
contribution evidence are added alongside that research. Selecting a model in the
library does not silently restrict the research page to that model's results.
Separate model links open model details; they do not replace the signal link.
Existing deep links remain valid and Back returns to the selected model, filters,
sort and ranking page/snapshot where available. Navigation reads saved evidence
and never starts research, refits or ablations.


The headline score is incremental out-of-sample forecast accuracy gained (%),
computed from paired full and causally refitted ablated model MSE. It is not a
current forecast weight, additive return contribution, standalone IC, P2 pass or
trading P&L. Rank descending under a visible versioned model/architecture,
Target/horizon and evaluation-period profile; show model applicability/coverage,
uncertainty and links to exact evaluations. Retain zero/negative measured scores.
Unmeasured, pending, insufficient or unavailable evidence is visible without a
numeric rank. A recipe grouping uses its verified canonical-parent mapping and
joint group ablation, not a sum of non-additive child importances.

The default page ranking is **within the selected model**, with a model/version
selector and visible Target/horizon/evaluation window. A signal can belong to
many models and has a separate incremental score and rank in each. Expanding it
shows a Models using this signal table with model links, per-model scores/ranks,
ranked/member counts, coverage, current/historical membership and evidence status.
Choosing a model filters to its members and orders signals by contribution to
that model. Nonmembers are not assigned zero or last place; zero-weight members
remain visible. Display sorting can change without rewriting contribution ranks.

An aggregate across models is an explicitly selected, clearly labelled summary
profile, not the default rank and not a replacement for per-model results. It
uses the equal-context mean across all applicable frozen contexts with coverage
shown; missing required evidence keeps that summary incomplete. The page never
selects the best model/window separately for each signal. Original definitions,
pairs and P1/P2 results remain accessible beneath the ranked entries.

RankingSnapshot publication follows label maturity and records its availability.
As-of queries cannot see later scores. Metadata readers project compact records
into a generation-pinned ranking index; GET requests never run model refits or
ablations and do not create a separately editable score authority. Stable ranks,
ties and pagination follow 27. Without P3 evaluations, keep the existing catalog
and an honest unmeasured ranking state rather than manufacture a #1 signal.

## Preserved boundaries

Experiment inputs and their Feature/Target/Scope resolution are unchanged. This
change performs no migration, materialization, provider acquisition, research,
P1/P2 execution or scientific policy alteration. It writes code, tests and this
specification only; all existing scientific records and payloads are preserved.
