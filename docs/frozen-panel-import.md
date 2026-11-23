# Frozen panel import, version 1

This is a separate data migration after a controlled application release. Normal
deployment does not install its policy, source snapshots, Features or data.
The explicit importer requires closed research admissions, an idle reset-era job
catalog, an exact plan hash and matching source fingerprints. It never submits
research. Re-running the same plan reuses identical immutable records.

Four source package schemas are supported: seven currency macro panels, ten
common-factor panels, ETF market/flow vectors, and the four market extensions.
These still represent 18 logical families; market blocks and ETF flows extend
families rather than creating a separate family for each engineered field.

## Storage and identity

Record profile `0.11.0` registers a source-backed field projection, not a ratio
transformation or a newly calculated signal. Every Feature pins its database,
original ZIP, package instructions/quality metadata, selector, field, unit, layer,
policy and operator. The importer streams each database into one immutable
content-addressed SQLite payload, shared by its projections. Original operands,
candidate values, missing/quality flags and package lineage remain in that file.
No observation or previous Feature is overwritten. Signal entries link completed
materializations and contain no research outcomes.

Only fields with at least one nonmissing, unblocked source state are registered.
An all-held field remains in the frozen source package; it is not promoted into a
selectable valid Feature. In otherwise usable histories, every missing/held
update remains and supersedes the previous state. The importer does not fill gaps.
Common series bound to several families are imported once, retaining all family
labels. Export JSONL files are alternative representations and are not imported
again. Source field units and native observation lags are retained, including
differences between common and market feature windows.

Common-source unit/cadence regimes are separate field identities. An update in
another regime emits an unavailable value for the old regime, including when
an earlier regime later returns. There is no implicit unit conversion or
carry-forward across such boundaries. Original unit labels remain in row evidence.

Metadata lists do not decode histories. Detail and research reads stream-verify
the pinned database hash and resolve the exact source row/field. Execution-local
reuse obeys the existing file-witness rules. No process-global verification cache
or new PIT certification is introduced.

## Timing and application

`archive`, `capture`, and `retrospective` are separate Feature identities. Macro
archive daily states retain their actual 12 UTC materialization cutoffs. Archived
provider dates remain conservative date-based evidence, not verified intraday
release timestamps. Retrospective ETF/market histories retain their assumed
availability and latest-vintage warnings. Unverified monthly market release times
and N-PORT-dependent ETF vectors remain held/capture-only as supplied.

The new alignment policy `POL_FROZEN_PANEL_UTC_STATE` does not alter the older
date-only external policy. A target anchor is conservatively interpreted as
00 UTC on its scheduled weekday. Availability must be strictly earlier than
that instant. Original exclusive validity intervals, null updates, query-time
market freshness (14 daily/150 monthly calendar days), and each package's frozen
capture ceiling apply. Source values after a phase's exclusive endpoint are not
decoded; at most one prevailing preperiod state is retained. A frozen package
cannot serve future anchors without an explicit refreshed publication.

Capture is one current context state per selector, not a history assigned an
earlier availability date. Capture Features remain stored/visible but are blocked
from historical TS planning. Their existence does not imply discovery coverage.

The explicit application contract is individual-instrument TS only. A canonical
macro pair field may be used only for the same two currencies; it is negated when
the target quotation is reversed, with that decision frozen in the plan and row
evidence. A common factor or country source stays unchanged when selected for a
pair. No exposure-weight mapping, 19-way duplication, CS broadcast, normalization,
learned response, trial, or performance claim is created by ingestion.

## Operations

Run `tools/import_panel_packages.py plan --batch BATCH --plan PLAN` on the server
and retain the exact plan. Inspect its eligible field counts, source hashes,
layer split and frozen dates. After controlled code deployment, apply that exact
plan with `apply --batch BATCH --plan PLAN --plan-sha256 HASH`. Both use the
canonical cloud store; never copy a legacy/Mac registry over production.

The apply command installs the new additive policy and an inherited Research
Spec under `config/frozen_panel_alignment.json`, separately from application
deployment. Existing policies and prospective scheduling remain unchanged.
Admissions remain closed. Verify source hashes, sample native reads, read-only
TS plans, library health and the absence of jobs before reporting completion.
