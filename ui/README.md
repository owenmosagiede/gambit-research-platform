# Research UI: experiment reference, Signals and history

Start the local server from the `research_platform` root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tools/serve_research_platform.py
```

Open `http://127.0.0.1:8765/#experiment` for the Experiment contract,
`/#signals` for Signal Library, or `/#ledger` for Trial Ledger. The sidebar
contains these three pages. There is no frontend build step or external asset
host. Serve the UI through the platform rather than opening the HTML directly.

## Experiment contract

The four selectors describe **Feature**, **Target**, **Scope** and **Expected
Direction**. They provide a read-only example for authenticated research tooling;
there is no Submit button or experiment mutation path in this page. Research Spec
is a frozen backend contract, not another dropdown. Service availability and the
compatibility of a particular selection are reported separately.

Feature and Scope choices come from the current registered catalogs. Returning to
this page or refreshing the inputs reloads them; an exact selection is preserved
only while it still exists. The Feature selector includes registered calculations,
including those with no research yet. Changing Feature or Scope reads existing
coverage and compatibility through `/api/feature-resolution`; it never launches
preparation. Selection details retain exact identities and stored coverage.

Target presents Price Return, Total Return and Excess Return. Unimplemented or
unpopulated categories remain disabled. Price Return covers all five scheduled
weekday horizons: 1, 7, 21, 63 and 252. The selector does not choose an instrument
or an individual horizon. An individual-pair Scope means TS research; a currency
universe means CS research using its common quote reference and frozen membership.
Expected Direction is selected before research and is not inferred from results.

The service selects the applicable Research Spec from the exact Feature/Scope
binding. P1 is discovery; admitted relationships proceed to P2 when its prechecks
pass. Queue acceptance and operational completion do not establish validation.
The numerical research contracts and the normal experiment API remain unchanged.

## Signal Library

Signals appear after verified research records have been saved. Preparation alone
does not count as research. Rejected, precheck and unresolved outcomes remain
visible; research does not imply validation. The page has no search/filter bar.
An empty library states that no researched Signals are available, rather than
filling the page with registered or prepared-only Features.

The library reads the Signal summary and research presentation APIs. Each entry
shows its readable calculation name and recorded experiments. Scope, expected
direction, discovery/validation state and forecast horizons remain distinct.
A calculation's lookback is not its forecast horizon: for example, 63-day log
momentum can be tested against each of the five return horizons.

Opening an entry reads its saved evidence and outcomes. Failed or unavailable
responses remain explicit and retryable. No sample result is substituted for
missing evidence. The page does not prepare observations, submit experiments or
change research records. Research updates can refresh the library without
reloading the workspace.

## Trial queue and Trial Ledger

The Experiment contract includes a live queue for experiments submitted through
research tooling. It is a monitor: it cannot start, cancel or resume research.
Each card retains the request's saved choices, stage, preparation progress, five
horizon outcomes and any concrete blockers or errors. Numerical preparation
windows are distinct from the retired Research batches panel.

Trial Ledger retains saved submission history and per-horizon outcomes. Its
search, status and date filters remain available. Hiding a resolved queue card
only changes this browser's view; the underlying trial stays in the ledger.
Opening or refreshing any page does not create a research request.

## Removed interface surfaces

PIT Data Library and the Research batches panel are no longer part of the shipped
workspace navigation or markup. The dormant PIT script is not loaded. The former `batches.js` asset is inert
and is no longer served; it performs no browsing or polling. The underlying PIT data,
source prices, Features, Targets and read APIs remain intact. Research batch APIs return an explicit retirement response, the old operator CLI
is disabled, and the worker no longer dispatches batches. Individual experiment
submission and execution remain available. Historical operational evidence is
retained through read-only readers.

Authenticated sessions add Sign out beneath the navigation. Its layout keeps the
label on one line. Logout still uses the existing CSRF-protected POST form.

See [Experiment contract reference](../docs/read-only-experiment-contract.md),
[API instructions](../src/api/README.md) and
[P1/P2 execution](../specs/23_p1_p2_submit_execution.md).
