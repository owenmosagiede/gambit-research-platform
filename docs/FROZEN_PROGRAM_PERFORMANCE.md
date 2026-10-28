# Verified input reuse for a frozen research program

This release adds request-local verified input reuse and an explicit execution
compatibility boundary. It does not change research policies, prices, recipes,
membership, statistical arithmetic, admission thresholds, or horizon selection.
The ordinary release command still refuses queued or running research.

## Cache lifecycle and measurements

One `VerifiedInputs` context belongs to one submission attempt. Phase entry binds
the frozen plan, phase, period and actual implementation. Entering another phase
clears retained objects. P2 entry still requires the normal admission token and
admitted horizon. Cancellation, failure, completion and process exit discard the
context. There is no persistent verification flag or cross-request cache.

The total retained-object bound remains **128 MiB**, including identity keys and
dependency witnesses. Compact immutable objects may occupy at most half that
bound. Large intermediate values use the remaining shared budget and cannot
evict the protected compact tier. An oversized value is computed normally and
not retained. This is a bound on retained cache objects, not total worker RSS.

The compact Feature lookup is keyed by the exact member, Feature, source,
ordered materialization references, batch policy, cutoff and phase. Independent
materialization verification and complete overlap checks happen before rows are
reduced to the fields used by alignment. Each horizon still performs its own
Target validation, eligibility, missing-data handling and aligned sample build.
Returned rows have fresh lineage dictionaries; retained lookup containers are
recursively immutable.

Target source reuse first runs the existing independent source verifier. It
retains the phase-safe endpoint fields and the original full source schedule
needed for horizon construction, under exact source/policy/phase identity.
Each horizon independently reconstructs and compares its Target values and
lineage. It does not reuse a Target decision from another horizon or recipe.

Cache publication records the exact source, manifest, payload and definition
reads, including negative definition lookups and lineage-catalog generations.
File witnesses include device/inode, size, mode, nanosecond modification/change
times and resolved path. A read set is checked again before publication; every
warm hit checks its witnesses. Changed/missing files or newly conflicting
definitions invalidate the entry and require full verification again. Nested
hits propagate their witnesses to the enclosing object. The same-capture
resolved-record memo is private to one verifier and cannot outlive that capture.
Packed lineage catalog changes conservatively invalidate dependent entries.
This operates under the existing immutable-publication/filesystem contract;
it is not a substitute for operating-system access control or protection from a
privileged actor that can alter the filesystem and its metadata arbitrarily.

Operational profiling records inclusive wall/thread-CPU intervals, process
lifetime peak RSS, cache hits/misses/evictions/retained bytes, and witness checks.
Labels distinguish preparation, independent verification, source prices,
Target reconstruction, loading/copying/alignment/hashing, catalog/event work,
P1/P2 calculation, publication and lock waiting. Nested interval totals must not
be added together. Performance diagnostics contain no observations and do not
enter trial identities or scientific outcomes. Diagnostic-write failure cannot
change the outcome of a research attempt.

## Frozen execution compatibility

Performance code changes the real implementation fingerprint. Pending envelopes
are never rewritten and their old fingerprints are never impersonated.
`runtime.execution_compatibility` accepts only an explicit immutable approval
covering **both intake and pending execution**, with exact pins for:

* Original manifest and intake-operator hashes, old/new full implementations and
  Python environments, source/target release archives, and test/equivalence files.
* Every manifest request UUID and canonical UUID, scientific identity and intent,
  accepted envelope hash or explicit not-yet-accepted state, and committed trials.
* Human approval identity, time and decision reference.

An `EXECPROPOSAL` is inert. No production approval is shipped in this release.
The old release-reuse registry is not treated as execution permission. Ambiguous
or overlapping approvals fail closed. A completed request remains terminal.

Approved continuation validates the full committed historical closure, including
trials published before a result-link crash. Exact old trial references are used
before input loading or calculation. Unfinished trials record the actual new
executor. Before a new calculation, an immutable operational intent pins its
exact trial key; after a crash, a committed trial can be found without depending
on a newly reconstructed materialization inventory. A missing recovery intent,
changed artifact, ambiguous committed trial or incompatible discovery chain
blocks continuation. This is safe retry, not an exactly-once computation claim.

`tools/frozen_program_intake.py` verifies the original operator bytes and uses
its finite workflow, guards, metadata/resource checks and receipts. Only the
implementation gate is replaced by the scoped approval. An ephemeral view used
for that gate is never serialized as a replacement manifest or used to regenerate
program identities. Verification is the default; `--submit` is explicit.
The recommended initial cutover waits for original intake to finish, so it does
not need to replace or restart that running helper.

## Subsequent equivalent-execution releases

A second performance release uses proposal schema
`frozen_program_execution_proposal_v2`. Supply `--predecessor-approval` to
`program_cutover.py review` with a file containing the exact installed approval
reference. The source archive is the currently installed release; the immutable
manifest's original implementation pins are retained. The command verifies the
predecessor authorizes that installed executor and the same manifest/operator.
It reads the exact accepted receipts and original journals, validates historical
and intermediate trials through the predecessor metadata reader, and pins every
committed trial to its actual implementation reference. Missing intents, attempts,
events, omitted historical references or unknown intermediate trials block review.

The successor embeds the exact predecessor approval, preserves the same cohort,
original scientific identities and accepted envelope hashes, and may only add
committed trial references. A further successor must retain all prior trial-to-
implementation bindings. Chains are bounded to 16 proposals; reverse execution
migration is not inferred. `plan` and `apply` derive this predecessor from the
explicit approval and check it again against the live immutable store. Numerical
execution, result decisions and original request identities are unchanged.

Successor approvals are append-only under `successor_approvals`, separate from
the original `approvals` namespace. This lets code-only recovery restore an older
reader without deleting new approval records. New code resolves and validates
both namespaces, rejects duplicate/wrong-namespace publications, and requires
the predecessor record to remain installed. Recovery refuses once new research
or execution provenance has been written. It never restores research snapshots.

Stage the matching status reader before cutover. It recursively rechecks previous
trial intents and observed execution attempts even when those trials are now
pinned historical results. Activate the new exact approval/executor/reader pins
only after preservation and website checks pass; carry forward the last successful
checkpoint and known pass identities. An old-reader mismatch is not zero passes.

## Reviewed cutover procedure — not authorized by this document

The target program is manifest
`9eb5aa189a70b4ef22db9e5cdb4ac1c7e695d7ce5f763ff7b47f547796b85459`:
371 experiments (one historical reuse), 53 recipes, seven currency universes,
and 1,855 horizon relationships. The audited executor fingerprint is
`0828f436efee8d04e78e8931942da4ad02ff79637d7750589b64137d977f0ac3`.
The active resume-003 intake operator observed during implementation has SHA256
`61cf7649743d1c704c65e1ec5f4e2bf9abff3bae9fe6493379469e25a28e9ffd`.
Recheck these identities at the actual cutover; these are not permission to act.

1. Complete review and merge only with authorization. Build the official source
   archive and passing release-check receipt from that exact main commit. Retain
   the original deployed archive, new archive, equivalence report and checks.
   Recheck that the service Python and every installed package still match the
   observed environment and unchanged `requirements-cloud.lock`; a dependency
   change requires separate review. Use the service interpreter for cutover.
   Stage the reviewed release-control script and its dependencies outside the
   installed application, from that verified artifact. This is an explicit
   operator-control update, not an implicit service/configuration installation.
2. Let the current finite intake finish. Reconcile **all 371** manifest entries
   against durable journals and canonical requests, including the exact reused
   historical request and result references. Require no unrelated backlog,
   integrity incidents or pending retired batch. Confirm the intake process and
   descendants have exited. A stopped/failed helper is a blocker, not completion.
3. With a separately approved maintenance window, request the existing worker's
   SIGTERM drain. Its systemd stop timeout is infinite: allow the active request
   to finish, never force-kill it or cancel queued work. The web application may
   remain available during this wait. Once the worker has exited, stop the web
   service before snapshotting so no new submissions can enter. Confirm all
   workers/children are gone and service/executor/writer locks are free.
4. Require a successful verified backup within 36 hours. Run the separate
   `deploy/program_cutover.py review` command with the exact manifest, original
   operator, both verified source archives, checks and equivalence files.
   It verifies full frozen bindings, records queued/terminal/partial states,
   inventories bounded research metadata, includes orphan committed trials, and saves
   an **inert** proposal, snapshot, code plan and before-images outside the app.
   Capture runs once under the maintenance locks; retrieve the durable review
   package after a connection loss instead of starting another capture. It never starts/stops services or grants approval.
5. Review that concrete proposal and its complete cohort, fingerprints, archive
   hashes and committed references. Only an explicit authorized decision may
   produce the separate append-only approval. If the proposal or cohort changes,
   refresh review; do not silently broaden approval or delete an older approval.
6. Run `program_cutover.py plan` with that approval, both archives, the original
   operator and exact evidence. Review the resulting plan hash. Run `apply` with
   that exact hash only after approval. The command rechecks quiescence, backup,
   release-control/backup locks, worker/executor/writer locks, and Feature/Target/lineage
   publication locks, in their established order. It verifies all pins again,
   publishes approval with access for the existing `gambit` service identity,
   saves before-images and a durable receipt, and installs only allowed code.
   Definition, policy, configuration, dependency, service and removal changes
   remain blocked. Research authority must be byte-identical before/after.
7. `apply` leaves services **stopped**. Verify the installed fingerprint and the
   exact queued/terminal IDs, envelope hashes, frozen bindings, historical
   references, and trial-intent/provenance history against the saved snapshot.
   Then start the web service and verify authenticated research pages and actual
   stored records before resuming the existing single worker. Check external worker health, `/healthz`, existing health service,
   immutable attempt provenance and normal progress on the **existing queue**.
   Do not submit a new pilot. The existing hourly reader requires the original
   executor and must not silently accept a changed fingerprint. Stage and test
   the separate approval-aware metadata reader before the window; activate it
   only as part of the approved cutover, retaining the prior verified-pass
   checkpoint and immutable relationship identities. Require it to verify the
   exact approval, unchanged manifest and research results without reading
   numerical payloads. Keep scientific passes distinct from operational
   completion. This release does not modify the active reader or its schedule.

The command's CLI lists the required file arguments. Exact hashes, approval and
reviewed plan are mandatory; it has no `--force` or `--ignore-backlog` option.
The normal `release_server.py` remains idle-only and must not be used to bypass
this separate program migration. Intake and service lifecycle are deliberately
not automated by the cutover tool.

### Staged hourly reader

`tools/frozen_program_status.py` is a separate metadata-only candidate; it does
not connect over SSH, write checkpoints, repair records or change a schedule.
After approved activation, the existing local SSH/health/process wrapper calls
the installed `read_status` with the original manifest, exact resume-003 operator
and exact installed approval reference. It retains worker/service health and
process observations. The reader accepts historical trials only by approved
immutable references, and new trials only with the approved executor, exact
trial intent and request execution provenance. Existing scientific pass gates
remain in force; numerical artifact manifests and payloads are not read.

The wrapper then calls `merge_checkpoint(report, previous_checkpoint)` locally.
Advance the last-successful checkpoint file only when `checkpoint_advanced` is
true; otherwise save an incomplete diagnostic separately and retain that file.
Known pass identities and the last successful observation survive incomplete
reads, so an old pass is never announced again after an access failure. Preserve
the existing heartbeat frequency and notification preferences. Before activating
this wrapper, verify checkpoint continuity and health-field integration during
the approved window; the current reader remains untouched by this PR.

## Recovery

If installation fails before research authority advances, restore the exact
saved code under the same maintenance and publication locks. Leave services
stopped until the restore and snapshot are verified. Preserve the append-only
approval and release receipt; an exact retry is allowed, while a different
overlapping approval requires explicit reconciliation.

If any new research authority appears—including events, trials, links, exposure,
execution intents or execution provenance—automatic old-code recovery is refused.
Keep every new record. Drain again and investigate with read-only metadata. Use
a reviewed forward fix, or a separately reviewed reverse compatibility proposal
that accounts for all old and new trials and pending envelopes. Do not erase
records, reset the queue, remove terminal status or replay finished research to
make a rollback appear clean.

The cache itself needs no rollback or migration: it is bounded, in memory, and
discarded when the process exits. No infrastructure purchase or resize, new
coordinator, changed dispatch order or parallel production worker is part of
this release. Benchmark results and deployment limitations are reported in the
implementation evidence accompanying the PR.


## Bounded release preservation check

The `frozen_program_research_metadata_v1` snapshot inventories definitions,
configuration, immutable submissions/intake reservations, event chains, research
plans, relationships, links, trials, admissions, validations, exposure,
implementation records, artifact manifests, execution intents/provenance,
integrity incidents and legacy batch evidence. It includes unrelated research
metadata so new authority still prevents an unsafe rollback. Complete frozen
Feature/Target/Scope validation and partial/orphan-trial reconciliation remain.

It does **not** walk the catalog root, Feature/Target materialization inventories,
source snapshots, row lineage, packed lineage, numerical payloads or UI caches.
The work scales with research metadata rather than the market-data store. This
is a code-only deployment: those excluded inputs are not written or deleted.
Their exact frozen bindings and the execution readers retain input verification;
the release inventory is no longer a whole-data-store integrity audit.

Use `review` with the same arguments as `propose`. It checks stopped services,
backup and all publication/maintenance locks, captures once, and saves its package
under the release state's `reviews/` directory before returning its receipt.
The receipt is not approval. Do not call `snapshot`, then `propose`, then rescan
the catalog in a wrapper. Approval/plan/apply still recheck fresh state at their
own boundaries; no snapshot is trusted across a service restart or data change.
Old full-inventory receipts differ from this explicitly versioned snapshot and
cannot silently be used for recovery with the narrower tool.
