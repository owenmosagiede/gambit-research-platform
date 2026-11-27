# 27 — P3 incremental signal value and Signal Library ranking

Design contract **P3_INCREMENTAL_VALUE@1.0.0**, 27 November 2026.
The user requires P3 to measure how much incremental value each signal produces
for the model containing it, preserve this as metadata, and supply a Signal
Library ranked from greatest to least incremental contribution.
**Specification only: no ablation engine, contribution scores, ranking API/UI,
production model selection or historical certificates are installed here.**

This extends the responsibilities and metadata in [07](07_p3_forecasting.md),
all seven architectures in [26](26_p3_combination_architectures.md), and the
read-only library in [22](22_signal_library_recipe_summaries.md). It does not
change existing P1/P2 outcomes or Feature/Signal identities. Calibration and
basket semantics remain those of [25](25_p3_ts_cs_calibration.md).

## 1. Purpose and measurement unit

P3 has two explicit responsibilities: produce comparable expected-return
forecasts with typed uncertainty, and evaluate the incremental **predictive**
value of each signal in its model. Numerical contribution to a current forecast
(`weight * forecast`) remains useful attribution but is not incremental value.
Neither a large weight, standalone IC, P2 pass, p-value nor standalone Sharpe is
the library ranking score. P4/P5 trading P&L, costs and capital effects are separate
economic evaluation, not silently substituted for P3 forecast accuracy.
Evaluation is a required P3 capability, but an outcome-based contribution score
is not a prerequisite for issuing the first shadow forecast. Pending ranking
metadata does not itself change P2 validation or the independent forecast/data
readiness rules; do not create a circular first-forecast requirement.

The elementary context is one frozen model/architecture/policy/family-mapping
version, instrument/member, exact Target basis and horizon, evaluation campaign,
issue-cutoff schedule, and full constituent/dependency roster. Scores belong to
that context, not permanently to a recipe in every possible model.

Default removal unit is a canonical parent SIGNAL/Feature: remove all its
relationship forecasts used by this model, not merely one convenient duplicate
or one zero-weight branch. Retain per-relationship diagnostics underneath it.
Different Targets/horizons are different contexts, never multiple votes in a
single comparison. All selected parents are evaluated, including those with
zero current weights. A signal can help one model and hurt another.

For a library entry grouping several verified canonical parents, pin an immutable
RankingEntityMapping from library entry/group identity to its exact parent refs
and grouping semantics. Do not merge by readable name or manual family label.
Evaluate removal of that whole recipe group in each applicable model. Label it
`LIBRARY_RECIPE_GROUP` rather than pretending the joint effect is the sum of the
individual-parent effects. Keep the original per-parent records accessible.

## 2. Primary contribution measure: causal refit ablation

For each evaluation issue time t, produce the full model forecast and its
counterfactual excluding the removal unit. Both forecast the same realised
Target `y_t` on exactly the same anchor and actual endpoint interval. Denote:

`L_full = mean_t (y_t - forecast_full,t)^2`

`L_without_s = mean_t (y_t - forecast_without_s,t)^2`

`incremental_MSE_gain_s = L_without_s - L_full`

`incremental_accuracy_gain_pct_s = 100 * (L_without_s - L_full) / L_without_s`

The percentage is the primary ranking score. Positive means including the
signal reduced forecast MSE; zero means no measured gain; negative means the
model forecast better without it. It is a percentage improvement in prediction
loss, not expected asset return, a probability of skill or a profit contribution.
Raw MSE gain has unit `U^2`; the percentage is dimensionless. Keep both losses,
the raw gain and the denominator, not just the formatted percentage.

If `L_without_s = 0`, the normalised score is unavailable with
`ZERO_REFERENCE_LOSS`; preserve raw loss/gain diagnostics. Do not divide by an
invented epsilon or rank an infinity. Negative scores are retained without
clipping; undocumented floors, winsorisation or return-selected transformations
are forbidden. Any alternative score requires a new versioned evaluation policy.

Refit the model without the signal using the **same** architecture, available
training labels, fitting/refit schedule, permissible hyperparameter grids/folds,
constraints, random-seed policy and evaluation issue cutoffs. Error weights,
ridge coefficients/lambda choices and covariance-dependent weights can change
as a causal consequence of removal, but may use only training information.
Independent calibrations of unaffected parents are reused by reference; they
are not retuned on the comparison window. Do not set one final coefficient to
zero and call that a refitted model. A fixed-fit removal diagnostic, if provided,
has a distinct method ID and cannot supply the headline refit-ablation score.

## 3. Hierarchies, dependencies and the no-signal reference

Removal is a new counterfactual model identity, not corruption of the production
model's frozen strict roster. Within the counterfactual only, re-form affected
family forecasts and refit affected inner and outer nodes under 26's original
method. Keep the user's assignments for all remaining parents. If a family
becomes empty because its last signal was explicitly ablated, remove that family
from the counterfactual tree and record the intervention. An empty family caused
by missing data in the ordinary model remains a blocker. No arbitrary reassignment
or switch from ridge to equal weighting is permitted.

Retain nested causal family vintages. An outer ablation fit cannot train on
today-refitted historical family forecasts or on labels unavailable at the
historical issue cutoff. The measured gain includes the original architecture's
reallocation/family-prior effects, not a claim to isolate a universal economic
causal effect of the signal.

Traverse **P3 forecast dependencies** as well as direct leaves. If the removed
parent feeds a conditional basket provider, remove it from that provider and
causally refit the remaining provider inputs. It must not continue to enter the
counterfactual indirectly through a shared baseline or cached family forecast.
Do not remove raw source data from independent parents merely because their
Features share economic operands: the intervention removes this signal's model
outputs, not the world's underlying data.

The default evaluation policy explicitly defines two structural absence cases:

- If an ablated conditional basket provider has no remaining validated input,
  reconstruct surviving relative CS leaves with 25's historical basket-mean
  provider using only its eligible matured training labels. Record this null
  provider substitution and new counterfactual calibration-context identity.
- If no full-return leaves remain in the final model, the counterfactual is
  `NO_SIGNAL_TARGET_MEAN_V1`: the mean of the instrument's exact Target labels
  under 25's mature-only calibration window/refit and minimum-history rules,
  omitting score-dispersion checks that do not apply to a null model.

These are declared **ablation-only** null references for measuring the last
signal/basket input. They do not authorise automatic production fallback,
new predictive certificates or a live zero forecast. A fitted null mean may
genuinely equal zero; missing null history is unavailable. If the specified
reference cannot be produced, mark the ablation unmeasurable rather than changing
the reference. Pin every substitution, dependency and null-fit version.

## 4. Evaluation information set and common samples

Freeze evaluation policy, parent/group-removal roster and full/counterfactual
recipes before evaluation labels are accessed. The default is paired forward
shadow issuance: at each t persist both forecasts using only then-available
decisions, scores, family metadata, calibration/combination fits and matured
training labels. Evaluate the pair only after its own Target endpoint and label
availability mature. Each side has an independent model/fit identity and lineage.

Past-only numerical replay using a later-selected roster, mapping, ablation
definition or architecture is `SELECTION_CONDITIONAL_REPLAY`. It must not appear
as unseen or prospectively issued evidence merely because its fits exclude
future labels. Profile changes or selecting/removing signals after seeing the
leaderboard create selection exposure; a fresh frozen forward evaluation is
required for a new unseen-performance claim. Ranking is descriptive evidence,
not automatic admission, pruning, revalidation, retraining or trade permission. A
research ranking profile may explicitly select selection-conditional replay
evidence, labelled as such. It must remain separate from the prospective-shadow
profile; mixing evidence classes or calling replay unseen performance is invalid.

Within a model ranking comparison, use one frozen common anchor schedule for
the full model and every requested ablation. Do not let removing a signal
expand the reduced model's scored dates, use its better-covered period, or give
each signal its most favourable slice. Preserve requested, forecastable,
paired-evaluable and excluded counts/reasons separately. A scheduled forecast
failure makes that context's ranking incomplete, rather than silently improving
the score by dropping the difficult dates. Pending immature labels remain
explicitly pending until the campaign's recorded evidence cutoff.

The bounded version-1 display requires at least 20 maximum-cardinality
non-overlapping **paired** Target intervals and the frozen evaluation coverage
requirements. Reuse the actual-interval sufficiency convention in 25; overlapping
daily returns do not become independent evidence. A CS universe's member count
does not multiply temporal N. For universe-level diagnostics, average loss
differences within an anchor under pinned weights before measuring time evidence.
Keep the elementary instrument/Target contexts for library aggregation.

Persist uncertainty/stability evidence on the paired differences of losses,
including effective N, subperiod gain, exposure and inference-method references.
Any standard error/interval must respect temporal/overlap dependence through an
explicit validated HAC or blocked-resampling policy; no IID standard errors,
member-times-date counts or imported conformal coverage guarantee is inferred.
Ratio-score intervals require an actual ratio-aware estimator. Unavailable
uncertainty is labelled unavailable; a measured point rank is not a significant
ordering or confidence that the signal is useful. Inference numerical details
remain an implementation policy gate, not fabricated metadata.

## 5. Ranked Signal Library

The library's ranking view is ordered greatest to least by incremental predictive
contribution, showing **#1 through the worst measured signal**. Its headline
column is `Incremental accuracy gained (%)`, backed by the primary score above.
Negative and zero contributions remain in that ordered list. Entries with no
valid contribution evidence are visible as `Not yet measured`, `Pending`,
`Insufficient evidence`, `Unmeasurable reference` or `Unavailable`, with no numeric
rank. A P2 failure or absence of P3 evaluation is not a measured worst score.
Keep the existing recipe details, pairs and exact P1/P2 results accessible.

A visible, versioned RankingProfile defines which models the page means:
one selected architecture and configuration policy, exact return family/basis,
horizon/clock, common campaign/window/availability and evidence class, plus an
ordered model roster with fixed aggregation rules. One model per selected
instrument/Target context prevents attempts, duplicate vintages or extra models
for a popular pair from buying additional votes. The user can select another
profile; the page never picks whichever architecture gives each signal its best
score. A cross-architecture summary is a separately named profile with explicit
weights, not the default same-architecture view.

For each library entry, its applicable model set is fixed from that profile's
full-model usage/dependency manifests, before evaluation outcomes. The default
aggregate is the equal-context mean of the entry's measured percentage scores
over **all applicable** models. Count a parent/group once per model context;
do not sum non-additive effects of its grouped parents or relationship branches.
An entry absent from a model is structurally not applicable, not a measured zero.
If any applicable context is pending or unavailable, the entry's aggregate is
incomplete and unranked; do not average only its successful/positive contexts.

Show applicable/measured model counts and evaluated coverage next to the score.
Different entries may be used in different models; the default overall score
therefore means **average incremental gain in the selected models that use this
entry**, not a model-independent universal quality. A matched-model filter can
restrict comparisons to entries evaluated on the same explicit model panel.
No significance claim or IID error bar is obtained by averaging correlated
models, architectures, currency pairs or overlapping horizons.

Sort by the unrounded aggregate score descending. Equal exact scores share
competition rank (`1,1,3`); stable entry ID orders tied display rows without
claiming different merit. Display rounding must not alter scoring/ranking.
Persist the profile, complete candidate roster, aggregation weights, scores,
ties, evidence cutoff and source contribution refs as a RankingSnapshot.
A different model roster/window/metric creates a different snapshot, retaining
the old view. A family name or recipe display rename changes no score or rank.

The UI is a bounded read-only projection of saved P3 records. It never runs
ablations, refits, numerical artifact scans or model selection on GET. Background
evaluation publishes compact results, and the existing metadata reader projects
them into a generation-pinned ranked index with stable pagination. Requests
filter on an explicit profile and generation so refreshes cannot silently move
rows between pages. Persist no separately editable duplicate score in the library.
Without P3 evidence, show an honest empty ranking with the existing catalog
available; never infer incremental ranks from today's P2 passes.

## 6. Required metadata and ownership

| Record | Required fields |
| --- | --- |
| IncrementalEvaluationPolicy | Method/version/hash, removal unit and dependency semantics, loss/score/sign, full and reduced fit rules, null references, exact evaluation schedule/window, maturity/coverage/effective-N requirements, inference, exposure and implementation. |
| ModelSignalUsage | Model/architecture/policy/version, original parent/relationship/leaf roster, FamilyMapping and tree, calibration/basket dependencies, applicable instrument/Target/horizon and issue cutoffs. |
| SignalIncrementalContribution | Parent or verified library group refs, model context, full/counterfactual model/fit/forecast refs, removal/intervention manifest, matching Target/interval/sample, both losses, raw MSE gain, normalised score or blocker, counts, uncertainty/subperiod/exposure evidence and computation time/cutoff. |
| RankingEntityMapping | Stable library group/entry and grouping-policy version, exact constituent canonical parents and verified projection refs, hash/provenance; display aliases excluded from numerical identity. |
| RankingProfile | Exact model roster and configuration, return basis/horizon/clock, campaign/evidence class/window, candidate/removal entities, applicability, coverage and equal-context aggregation policy, tie/inference rules and user selection/availability. |
| RankingSnapshot | Profile/hash and generation, ranked and explicitly unranked entries, source contribution refs, aggregate scores and full denominator/model coverage, rank/ties, evidence cutoff, computation and implementation refs. |

These are logical immutable evidence contracts pending closed schema/engine
implementation. Large paired forecast/error histories live once in referenced
payloads; compact metrics/lineage are published before projections point to them.
P3 computes the measures, original Signal/Feature relationships retain the
references as derived metadata, and the library projects/sorts those measures.
Publish evaluation records after label maturity with separate `evidence_cutoff`,
`computed_at` and `available_at`. Do not rewrite immutable Feature definitions or
original issued forecasts with later scores. Historical as-of library/model
queries use only contributions and snapshots published by their query cutoff;
a later evaluation may reference an old forecast without making its rank known
at that old issue time. Keep these links in derived/evidence records, not in a
second editable signal definition or a future-aware forecast metadata overwrite.
Manual family membership remains user-owned and cannot be overwritten by the
ranking evaluator. Family-group ablations may be additional declared diagnostics;
they are not individual signal scores.

## 7. Interpretation, failure and invalidation

Refit ablation measures conditional incremental value under a model, roster,
architecture, replacement/null policy and finite evaluation sample. Correlated
substitutes may each score near zero even when removing both is damaging. Scores
need not add to total model skill, sum to 100%, or equal Shapley allocations.
Interaction/complementarity and hierarchical reallocation can affect results.
Do not claim a causal economic mechanism or universal lack of usefulness from
one low score. Retain original forecast weights and additive return contributions
under their own fields, never relabel them as measured incremental accuracy.

Missing or mismatched Target labels, different paired dates, impossible refits,
missing null references, leaking provider dependencies, invalid family mappings,
unregistered policy/solver settings, inadequate evidence or corrupt artifacts
produce typed blocked/unranked records, not zeros or guessed ranks. Invalidate
affected contribution/ranking descendants when model/parent/Target/provider,
mapping, policy, evaluation labels, data readiness or implementation changes;
retain old records and historical ranks. Unrelated P1/P2 results remain intact.

Evaluation is a separately bounded background workload with pinned model and
removal rosters, resource limits, cancellation/reuse and checkpoint manifests.
Changing this specification does not trigger N+1 fits or new research now.

## 8. Bounded acceptance cases

1. Full MSE 0.008, without-signal MSE 0.010 gives raw gain 0.002 U^2 and score
   **+20%**. Full 0.011 versus without 0.010 gives **-10%**, retained below zero.
2. Equal losses give score zero; zero reference loss gives an unavailable
   normalised score, not infinity or rank last. Missing evidence is not zero.
3. A model's only signal is compared to its declared mature-only Target-mean
   null forecast; removing the last family is valid only in the intervention.
4. Removing a library group removes every included parent/relationship path once.
   A conditional basket cannot leak the removed parent's forecast back into the
   reduced model; null-provider substitution is recorded and never a live fallback.
5. Ridge/error hierarchy removal refits both affected levels with training-only
   histories/folds. Merely zeroing a fitted coefficient fails the primary method.
6. Identical substitutable forecasts may each have zero refit-ablation gain.
   Their joint-removal gain can be positive; no sum-to-total or independent-alpha
   assertion follows. Current weight zero does not exempt a signal from evaluation.
7. Full and reduced scores use exactly matching anchors/labels. Extra reduced-model
   coverage cannot improve its comparison; a required failed/pending context keeps
   the aggregate unranked rather than selecting a favourable slice.
8. Context scores +20% and -10% aggregate to +5% under equal-context weights.
   An entry absent from one model is marked not applicable, not assigned zero.
9. Equal measured scores share ranks `1,1,3` with stable ID tie ordering. A negative
   measured score ranks below zero; an unmeasured P2-failed entry has no rank.
10. Spot/TR, different horizons or selected-best architectures cannot enter the
    default same-profile mean. A ranking profile or evaluated model change creates
    new metadata identity; a display/family label rename does not change ranks.
11. Twenty paired non-overlapping intervals count as twenty temporal observations,
    regardless of member/model count. Ratio/inference metadata cannot claim IID or
    finite-sample guarantees imported from unrelated assumptions.
12. Saved contributions project into a stable-generation ranked list. Reading
    page two cannot launch ablations or switch generations silently. With no P3
    contribution records, the page displays no invented #1 signal.

These are contract requirements and synthetic identities, not implemented
evaluation, empirical scores for current signals, a deployed ranking page or
evidence that any P2 survivor already has positive P3 incremental value.

## 9. Method evidence and remaining work

The refit-without-input predictive-importance concept is supported by
[Lei et al., section 6](https://www.stat.berkeley.edu/~ryantibs/papers/conformal-jasa.pdf).
The MSE/percentage metric, time-dependent paired evaluation, grouped recipe
interventions, model aggregation and ranking rules here are explicit Gambit
design choices. That paper's IID/conformal inference guarantees are not claimed
for these currency time series. The user owns the ranking requirement; P3 owns
the derived evidence, not a new editable scientific signal definition.

Remaining implementation work: closed policy/metadata validators, bounded
full/reduced causal refit jobs and null-provider handling, concrete temporal
inference settings, durable publication/reuse and ranking projections/API/UI,
isolated numerical/leakage/pagination tests and controlled release. Existing
models, research jobs, ranking-free library views and the PR52 release gate
are unchanged by this specification revision.
