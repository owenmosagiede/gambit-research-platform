# Research batch submission is retired

The batch creation, preview, approval, pause, resume and automatic dispatch
workflow has been removed. Use one explicit experiment request at a time through
`POST /api/experiments`. The independent worker still prepares that experiment
and evaluates its five forecast horizons. Ordinary queue recovery and duplicate
experiment checks remain in place.

`/api/batches` and its descendants return HTTP 410 `BATCH_RETIRED` without
recording work. Authentication, CSRF and origin checks still apply. The former
`tools/research_batch.py` command exits with a retirement message and performs no
reads or writes. Its old browser script is inert and is no longer served.

Old batch manifests, approvals, rows and dispatch references are historical
operational evidence. They are not scheduled, advanced or rewritten by the
worker. Read-only compatibility readers remain for legacy migration audits and
for previously installed release controllers. They cannot create or dispatch
experiments. Existing trials, results and request IDs remain authoritative.

A release still refuses unfinished or unverifiable historical batch evidence;
removing scheduling is not permission to silently drop frozen work. Inspect any
such records and resolve their disposition explicitly before deployment. A
completed manifest cannot conceal an active ordinary experiment: the release
controller checks the normal queue independently.

This retirement does not remove the numerical preparation chunks sometimes
called “batches,” source-price construction, or any Feature/Target data. It does
not modify the seven currency universes or the 43 single-pair Scopes.

See [the retirement release review](../docs/batch-retirement-release.md) for the
implementation compatibility and deployment checks.
