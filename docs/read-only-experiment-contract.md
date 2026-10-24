## Read-only experiment contract

The Experiment Contract page explains the four required inputs: **Feature**,
**Target**, **Scope** and **Expected Direction**. The selectors browse the current
registered catalog and produce a JSON example with a UUID placeholder. There is
no form submission, browser request persistence, or browser research control.
Agent/operator research tooling submits the exact contract to `POST /api/experiments`;
the authenticated backend API and its validation remain unchanged.

Feature options come from `GET /api/feature-library`, preserving catalog names so
single-pair and currency-oriented recipes remain distinguishable. Scope choices
come from `GET /api/scope-library`. Counts and options are discovered, not hardcoded.
Catalogs refresh when returning to the visible page after 30 seconds, and via
**Refresh inputs**. Exact selections survive only if their registered definition
and membership hashes still match. Retired or changed selections are cleared.
Late responses cannot restore an obsolete selection. Changing inputs only reads
coverage and compatibility through `GET /api/feature-resolution`.

Price Return represents all five horizons: 1, 7, 21, 63 and 252 scheduled weekdays.
Other return categories remain disabled until supported. Individual instrument
Scopes mean TS; currency universes mean CS against their common quote/funding
reference, with matching oriented Feature and Target prices. Expected Direction
is supplied before research and is not inferred from results.

Research Spec is selected and frozen by the backend; it is not a request field.
The generic readiness profile describes the single-pair route and must never be
presented as the currency CS profile. Exact external Feature profiles are shown
only after compatibility resolves. Currency CS uses its active currency release.
The service rechecks compatibility, freezes dependencies, prepares missing inputs,
runs P1 across five horizons and runs P2 for admitted candidates.

`GET /api/research-readiness` is informational. Failed readiness does not hide the
contract or claim research is available. This page, queue and batch views issue
GET requests only. They cannot create, retry, approve, launch, pause, cancel or
resume research. Browser-only queue dismissal does not alter stored research.

