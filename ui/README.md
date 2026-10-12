# Research UI: experiments, Signals and PIT data

Start the local server from the `research_platform` root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/serve_research_platform.py
```

Open `http://127.0.0.1:8765/#experiment` for New Experiment, `/#pit` for PIT Data
Library, `/#signals` for Signal Library, or `/#ledger` for Trial Ledger. The sidebar contains only those navigation tabs. There is no frontend build step or external asset host. Use the local server
rather than opening the HTML file directly.

## The four inputs

The form contains **Feature**, **Target**, **Scope** and **Expected Direction**, followed
by **Submit**. Research Spec is a frozen backend contract, not another dropdown.

Feature options come from `GET /api/feature-library`: 180 reusable FX configurations
plus the existing non-FX Features, according to the registered catalog. Scope chooses
the instrument or universe receiving that calculation. Registration does not require
prior observations. Changing either selector only reads existing per-member coverage
and missing outputs through `/api/feature-resolution`; it never launches preparation.
Historical instrument-bound Feature IDs remain on the stored outputs and lineage.

Target presents **Price Return**, **Total Return** and **Excess Return**. Price Return
is enabled when populated; the other categories stay visible and disabled until
implemented/populated. Each category represents all five horizons: 1, 7, 21, 63 and
252 scheduled weekdays. The dropdown never selects an instrument or horizon.

Scope is API-backed and preserves exact registered membership. Individual instrument
means TS research; universe means CS only. For a universe, per-member Feature histories
feed one cross-sectional relationship per horizon. They do not create separate TS
trials. Expected Direction is frozen before research and is not inferred from results.

## Submit and readiness

The installed P1/P2 pathway uses approved Research Spec `RSPEC_FX_SCOPE_ROUTED_SUBMIT`
**2.0.0**. `config/research_execution.json` references its exact ID, version and content
hash at `definitions/research_specs/RSPEC_FX_SCOPE_ROUTED_SUBMIT/2.0.0.json`. The UI
reads `GET /api/research-readiness` and enables Submit when this profile verifies and
readiness is satisfied. Any remaining blocker or unavailable readiness response keeps
Submit disabled. Refreshing readiness is a read action.

Pressing Submit records a request with the selected identities and approved profile.
The worker resolves exact inputs,
prepares only missing coverage, runs five P1 evaluations, and runs P2 only for admitted
horizons passing prechecks. Each trial card shows the frozen choices, request ID,
preparation/stage, all five horizon outcomes and concrete blockers/errors. Operational
completion is separate from scientific admission or validation.

The displayed **Validation period** is 1 January 2022 through 31 August 2026.
Discovery includes all eligible history through 31 December 2021; the selected Scope's
latest member structural start is frozen in its plan. The five horizons use scheduled
Monday–Friday dates with no holiday exclusions, and inference preserves missing weekday
gaps. Unavailable required P2 evidence is unresolved; available failed criteria are failed.
The 252-day t/p evidence remains diagnostic under its existing rule.

The registered profile pins 43 source snapshots and 215 completed Targets, resolving ten
display-snapshot mismatches and two AUDUSD Target ambiguities for research without changing
library data. Research is retrospective date-label analysis. Prior period-level legacy
exposure is disclosed, specific-recipe exposure remains unknown, and the UI does not
present the Validation period as an untouched holdout. Historical availability and live
readiness remain uncertified.

A request ID is preserved across duplicate clicks and uncertain responses. Retry uses
the same recorded request; it does not create another experiment. Session storage can
restore a pending request so the UI checks its status instead of reposting it on load.
Polling is bounded and can be continued with the status control. Cancellation stops at
safe checkpoints and preserves committed data. Resume retains the original profile,
inputs and plan; changing backend configuration does not rewrite an old request.

Opening the UI, changing inputs, installing code or loading the Signal Library never
creates a new research submission. The local worker may recover active work previously
submitted by the user. The current input adapter supports reusable FX recipes; CES and
other non-FX entries remain available but an unsupported research binding is reported
as blocked, without inventing broadcast/alignment rules.

## Signal Library

The expandable recipe cards use `GET /api/signal-library-summaries`. FX entries are grouped
reusable recipe configurations represented by stored outputs. The library does not
expand to all registered recipes merely to match the Feature dropdown count.

For example, the existing momentum summary displays:

| Field | Display |
| --- | --- |
| Signal | Log Skip Recent Momentum |
| Source | Closing prices |
| Transformation | Log Level → Skip Recent Difference (k=63, s=5) |
| Observations | N/A |
| Research Status | Untested until an authoritative research result exists |

`N/A` describes the reusable recipe, not missing observations. Expanded details retain
AUDUSD and its 64-row sample, actual coverage, provider, readiness and exact lineage;
that sample does not establish universe coverage. Cards use generic recipe titles and
the actual transformations/parameters. Existing non-FX identities and details are retained.

A recipe's scoped research details read authoritative trial/admission/validation
records. Scope, Target/horizon, Research Spec and evaluation period stay separate.
Partial and complete branches are reconciled without editing historical records.
Preparing observations is not testing, and no successful relationship universally
validates a recipe. The page refreshes research links when a submitted job publishes
results. Descriptive observation statistics remain separate from predictive metrics.

Output details select exact historical Signal/materialization IDs via
`/api/signal-library-outputs/`; non-FX details retain their existing route. Counts and
statistics refer to the selected materialization. Decimal values, null reasons,
source/policy references and observation lineage remain inspectable.

## Library pages and filters

Each library is a separate page with expandable cards. Only one card's details are
expanded at a time. Closing a card or filtering it out hides its details; stale
Signal detail requests cannot reappear after the selection is cleared.

PIT Data Library uses `GET /api/pit-library`. Search matches name, ID, series, provider,
frequency, units and coverage metadata. Provider, frequency and inclusive observation
coverage dates filter its current displayed dataset snapshots. The existing preferred
snapshot selection and one-card-per-dataset inclusion rule remain unchanged.

Signal Library searches recipe names/IDs, transformations, parameters and stored output
identities/providers. It filters by provider, research status and inclusive observation
coverage dates. Provider and date criteria must match the same stored materialization;
a generic recipe is not given invented global coverage. Expanded details retain all
its outputs and their exact lineage even when only one output matches the filter.
Date filters match overlapping coverage, not retrieval/capture dates or a promise that
every date within the range has observations. Clear filters restores the full library.
Filters operate locally on verified API metadata and trigger no preparation or research.

ALFRED archive dates and FX retrospective snapshots retain their distinct limitations;
neither storage nor a source capture date establishes intraday availability or live
readiness. Loading, empty, partial and failed states retain retry paths. No mock library
entry replaces a failed catalog.

## Trial cards and history

The Experiment page has the four inputs, Submit and a live API-backed queue.
There is no separate Experiment progress section or Open progress link. Cards show
stage, frozen intent, mode, horizon outcomes, blocker reasons and relevant Cancel
or Resume actions. Completed and cancelled submissions remain in Trial Ledger.
Resolved attention cards can be removed from this browser's queue without deleting
research; Trial Ledger retains a Show in queue action.

An unconfirmed submission appears as a card even before the queue API records it.
Check receipt uses GET only. Check and retry first uses GET by the original request
ID, and only a 404 permits resending the exact original body with the same ID.
Network failures, malformed responses and unavailable status never permit a new
identity or an automatic research run. Reload restores the previous session's
request and checks status without submitting it. Queue polling can reconcile a
late acknowledgment. Errors include available HTTP/server details.

Selection coverage and Target inspection stay in the collapsed Selection details
and stored coverage disclosure. Research contracts and numerical execution remain
unchanged. Trial Ledger keeps per-horizon outcomes and links to Signal Library.

See [API instructions](../src/api/README.md),
[Feature/Scope specification](../specs/21_reusable_features_and_scope.md),
[Signal presentation](../specs/22_signal_library_recipe_summaries.md) and
[P1/P2 execution](../specs/23_p1_p2_submit_execution.md).

### Unconfirmed submission receipts

Submit displays its disabled reason immediately below the form. A request with an
unknown receipt pauses new submissions until a read-only status check resolves it;
checks also run with the regular health refresh, without resending work. A verified
404 releases that pause. If the inputs are unchanged, Submit reuses the original
request ID and frozen intent; changed inputs get a new request ID. A later status
failure restores the safeguard. The form's Check previous submission status control
never sends a POST. Only Submit or the card's explicit Check and retry action can
send the request. These controls do not certify a selection's scientific eligibility.

### Safari submission compatibility and dismissed notices

The application serves `Referrer-Policy: same-origin`. Safari sends `Origin: null`
for same-origin POST requests under the previous `no-referrer` policy. The server
still requires the exact local Host/Origin for mutations and still rejects null,
missing, mismatched and foreign origins; no CORS allowance was added. Referrers
remain withheld from other origins.

Explicit INVALID_ORIGIN/INVALID_HOST 403 submission responses are labelled
Submission rejected, not Receipt unconfirmed. Their local notices have a dismiss
button. Unknown receipt notices also have a dismiss button, which checks the
server first: only not-found responses clear them, while accepted jobs retain their
normal queue tracking and unavailable responses retain the recovery handle.
Dismissing a local notice never cancels a job or deletes stored research records.

### Submit follows selector compatibility

Submit is disabled for incomplete/unavailable selections, unresolved identity
bindings, and existing selector validation errors. External stored Features also
require an affirmative compatibility response for the exact selected Feature and
Scope versions. Async Feature, Scope and Target state updates refresh the button
and its explanation immediately; changing Scope cannot reuse a prior external
compatibility decision. Backend validation remains authoritative.

Readiness of the service is labelled separately from compatibility of the selected
inputs. Zero stored Feature outputs or unverified live readiness do not by
themselves disable an otherwise supported retrospective selection. Selection
changes perform read-only checks and never launch materialization or research.
