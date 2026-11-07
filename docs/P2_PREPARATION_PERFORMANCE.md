# P2 preparation reuse

The research arithmetic, statistical policies, expected directions, admission,
periods, horizons, identities and existing records are unchanged. Execution code
changes require a separately pinned compatibility approval for queued work.

Small verified catalog records and the active request's verified event chain now
use private JSON values backed by immutable compact bytes. They share the existing
128 MiB total / 64 MiB compact limits with other input caches. An event-history
entry witnesses every scanned event and listing level. Appends, deletions, new
attempts, changed files and unreadable unrelated events invalidate reuse; the
ordinary full replay then checks the chain. This deliberately does not trust a
mutable job projection or assume that an unchanged directory means unchanged
file contents. Cache pressure may fall back to full replay.

Witness validation resolves a shared parent path once per validation pass while
still checking every file with both `lstat` and `stat`. It rechecks every shared
parent resolution and ancestor identity before accepting the pass. Replacing a
symlink, including changing it back during the pass, rejects reuse. This temporary
path traversal state never survives a validation pass.

An exact, bounded index of the eight definition directories avoids repeating
negative file lookups for every lineage record. Directory identities witness
membership, so a newly added identifier invalidates the index. Existing identifiers
still use the ordinary version lookup, full record validation and ambiguity checks.
Standalone readers retain their existing lookup path.
Repeated directory lookups within the very same enclosing verification read may
reuse its already captured directory witnesses. The enclosing verifier checks
every witness before publishing a cached result; a directory changed during that
read rejects publication. Independent loads still check the directories afresh.
Cancellation/event checks never use this same-read shortcut.

Feature publication checks its complete reference closure inside one fresh
read-only capture. Every file and directory in that closure is checked again
before the call returns and before the caller can publish a manifest. The capture
retains no result between closures. If nested inside another verifier, its full
read set propagates outward and is checked again there. This lets repeated
lookups share evidence within a closure without treating an earlier closure as
permanently verified.

Packed row-lineage reads also reuse the already checked locator and bounded
pack within one enclosing verification read. The first lookup captures the
index, catalog generation, exact pack catalog and payload. The enclosing verifier
rechecks that complete read set before publication. A changed payload, index or
catalog membership rejects the result. A separate read or phase performs the
ordinary checks again; the existing two-pack bound remains unchanged.
The Feature resolver accepts that pack reader's complete row validation instead
of repeating the identical schema and reference checks on its private copy.
Canonical path checks and independent validation of any loose record remain.

A verified FX Feature retains canonical bytes in the ordinary cache. Its full
independent source, arithmetic and lineage verification remains required on a
miss. The complete dependency witnesses are checked on every hit and before
publication. It does not retain a second proof in the compact tier: the stored
input benchmark showed that duplicate witness sets displaced shared prices,
lookups and Target endpoints and increased total P2 time. Eviction, a changed
dependency, a new phase and standalone inspection all require full verification.

All reuse is local to one execution and phase. P2 still needs the exact admission
token and admitted horizon before access. Cancellation, failed publication,
restart and completed/partial-trial recovery retain their existing behavior.

## Offline acceptance

`tools/benchmark_p2_preparation.py` compares the deployed baseline
`4eaba323d2de21034fb302edfddd61efcd9d2b80` against the candidate using copies of one
synthetic persisted source fixture. It accepts no production store. Two recipe
families exercise 18 CHF currency members, five P1 horizons, actual P1 admissions,
and a P2 period from January 2022 through August 2026. The ordinary preparation,
source provenance, Feature publication/replay, Target alignment and P2 kernels
run unchanged. 12,500 synthetic historical events exercise progress checks.
Fresh and previously published Feature cases run twice in reversed order.

Full inputs, null/exclusion decisions, output values, statistical decisions and
lineage must agree. Fresh output comparisons translate only explicitly verified
producer-code references and their proven derived identities. Existing output
references must match exactly. The gate requires at least 30% lower P2 preparation
time, lower complete P2 time, no more than 10% P1 total regression and the existing
cache bound. Timings are local synthetic evidence, not a production ETA.

## Existing negative follow-up queue

The follow-up manifest has its own original byte identity and immutable envelope
bindings. `deploy/followup_manifest.py` reads its pinned parent manifest to derive
an in-memory binding view for the existing cutover checks. It verifies completed
parent submissions, negative direction, all horizons, original child executor,
scientific identity and the unchanged scientific plan. Each child's own optional
output inventory remains frozen in its original checksummed envelope, including
the early follow-ups that accepted a newer cache inventory than the parent.
Neither manifest is rewritten. An unknown, changed or missing parent blocks the
release. Existing cutover checks still preserve all research authority, including
completed parent results, and reject unrelated active requests.

Deploy only after the exact candidate's benchmark gate and required release checks
pass. Gracefully drain the single worker, capture bounded preservation evidence,
review the inert compatibility proposal, and apply the exact official archive.
Verify research records, queue order and real website data before resuming the
next existing queued request. Rollback restores code only and must never replace
newer research with an older snapshot.

Witness checks retain separate lstat/stat calls for every file. Within one check,
absolute paths whose ancestors are all ordinary directories use their already
known spelling instead of resolving each sibling directory repeatedly. All
ancestor identities are checked again before acceptance. Symlinks, relative
paths and dot-dot paths retain full resolution and its final recheck.

Small immutable Feature definitions can reuse witnesses already captured by the
same enclosing verifier, which rechecks the full read set before publication.
Returned records remain private copies. Independent reads still check witnesses;
operational event and cancellation reads do not enable this shortcut.
