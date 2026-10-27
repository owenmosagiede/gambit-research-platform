# Frozen-program cutover after the reviewed reset

The earlier momentum reset intentionally retired 5,717 definition files. Those
files remain in source archives for review, but must remain absent from the live
registry. The ordinary code-release planner correctly reports them as registry
migration blockers. `program_cutover.py` can acknowledge only this exact,
previously reviewed retirement when supplied its protected evidence. Every other
registry, configuration, dependency, service and code-removal blocker remains.

This is release control only. It does not restore or remove definitions, change
research calculations, replay trials, change queue order, install dependencies,
or start or stop services. `release_server.py` remains unchanged and refuses
queued research. The separate program cutover still requires complete intake,
a drained and stopped worker, stopped web intake, a recent successful backup,
the existing maintenance locks, and an exact human-approved proposal and plan.

## Exact historical evidence

The optional exception is fixed to these historical anchors; the CLI cannot
select a different retirement or increase its scope:

| Evidence | Required value |
| --- | --- |
| Source commit | `9654b7de0b90d7f9a85718638effc271f6d6c6e1` |
| Source archive SHA-256 | `225910f261192e6c2d92c3733d61da4a1ccd2b5ded9c7558b0dff3f04240b118` |
| Reset plan identity | `4f3cfd3140376ee892d50bf6322752d77fc6fc7c84331c2ddc5501ee77da7ee0` |
| Reset plan raw-file SHA-256 | `933990b62b28ca4d208eed9b296dd486f4b34c00127906e0cb439ca3666562b4` |
| Reset status raw-file SHA-256 | `0cbda495d156fa7b68b92b4911eb82e683a57c5886465e67f32d64163137586c` |
| Prior successful release ID | `9654b7de0b90d7f9a85718638effc271f6d6c6e1-c5f149eefa65` |
| Prior server receipt raw-file SHA-256 | `b8821b141a89b484ab6ec52089dbf52171c84d882803054cbc75b23060d6a580` |
| Omitted-definition map | Exactly 5,717 paths; SHA-256 `ce5c2904edea98fc97f7f4a865f8e0ffedb39fe2cd32a55dc5946f7c50686c5f` |

The map is derived from the completed reset and must equal the prior release
receipt's acknowledged map. Only `definitions/features/`,
`definitions/feature_recipes/` and `definitions/feature_applications/bindings/`
are eligible. Every recognized definition must have identical bytes in both
verified archives and remain absent from the live store, including absence of
redirecting symlinks. A restored file, changed archived definition, different
evidence, additional omission or remaining blocker prevents the cutover.

The prior receipt's pretty-printed local export has SHA-256 `85449794…`.
Its parsed content is identical, but it is not the original server file. The
server uses compact canonical JSON plus a final newline, whose raw SHA-256 is
`b8821b14…`. Use the exact server bytes, not a reformatted export. Likewise,
preserve the reset files and both release archives byte for byte.

The evidence files, archives and their ancestors must be regular, root-owned,
protected paths with no symlink redirection or group/other write permission.
Keep them outside the application and repository. Do not commit reset
inventories, deployment receipts, data or private operator mappings.

## Prepare the evidence index without granting approval

Use the corrected official archive and its passing checks for the exact clean
main commit. Stage its reviewed control code separately from the application,
retaining the project layout (`deploy/`, `tools/`, `src/`, `specs/`). Use the
existing production Python and dependencies. An earlier release receipt does
not test this additional control code.

Keep the original scientific equivalence reports, raw benchmark results and
receipts unchanged. Produce a separate carry-forward report that demonstrates
the reviewed performance candidate and corrected release have identical
scientific/runtime source, benchmark harness dependencies and dependency lock.
The new control files, tests and operator documentation must be identified as a
separately reviewed change.

The external index has schema `frozen_program_release_evidence_v1`. Its
`retirement_context` must equal the validated context's complete `binding`.
The existing proposal field `evidence.equivalence_sha256` pins the entire raw
index. `evidence.tests_sha256` separately pins the corrected exact-main checks.
No scientific approval schema changes are needed.

For example, in a protected local staging area containing the exact retained
evidence and archives, obtain the binding with the reviewed helper:

```python
from pathlib import Path
import sys

control = Path("/protected/control")  # Separately staged reviewed project layout.
sys.path[:0] = [str(control / "deploy"), str(control / "tools")]
from retired_definitions import load_context

context = load_context(
    {
        "plan": Path("/protected/reset-plan.json"),
        "status": Path("/protected/reset-status.json"),
        "receipt": Path("/protected/prior-receipt.json"),
    },
    Path("/protected/source.tar.gz"),
    "225910f261192e6c2d92c3733d61da4a1ccd2b5ded9c7558b0dff3f04240b118",
    Path("/protected/corrected-main.tar.gz"),
    corrected_archive_sha256,  # Read from the verified official artifact.
)
binding = context.binding
```

This only validates local inputs. It does not create an approval or touch
research. A protected server-side read can export the same binding for local
assembly when the original inputs are held on the server; do not weaken the
file-ownership checks to make workstation copies appear authoritative.

Assemble the index locally from that validated binding and actual evidence
files. The following illustrates the data structure; use the real paths and
hash each retained file's raw bytes:

```python
import hashlib
import json
from pathlib import Path

def reference(path):
    path = Path(path)
    return {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

index = {
    "schema": "frozen_program_release_evidence_v1",
    "retirement_context": binding,
    "scientific_evidence": [reference(path) for path in original_evidence_paths],
    "carry_forward": reference(carry_forward_report),
    "control_review": reference(control_review_report),
}
raw = (json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode()
with Path("release-evidence.json").open("xb") as output:
    output.write(raw)
```

The index records evidence references, not a new scientific result or permission
to deploy. Retain every referenced file beside the review package. Review their
contents and hashes; the cutover validates the context and pinned index bytes,
not the scientific adequacy of a newly written report.

## Proposal, approval and application

The three optional flags must be supplied together to `propose`, `review`, `plan` and
`apply` when using this exception. Omitting them leaves ordinary blockers in
place. `snapshot` is unchanged; `recover` uses the saved release evidence and
does not accept replacement retirement files.

After the separately authorized safe drain and backup checks, prepare the inert
proposal using the separately staged corrected control tool:

```sh
/opt/gambit/venv/bin/python -B /protected/control/deploy/program_cutover.py review \
  --root /srv/gambit/research_platform \
  --manifest /protected/program-manifest.json \
  --source-archive /protected/source.tar.gz \
  --source-sha256 SOURCE_ARCHIVE_SHA256 \
  --archive /protected/corrected-main.tar.gz \
  --sha256 CORRECTED_ARCHIVE_SHA256 \
  --operator /protected/original-operator.py \
  --operator-sha256 ORIGINAL_OPERATOR_SHA256 \
  --checks /protected/release-checks.json \
  --equivalence /protected/release-evidence.json \
  --retirement-plan /var/lib/gambit-clean-reset/plan-10c9e968f7b4/plan.json \
  --retirement-status /var/lib/gambit-clean-reset/execute-2f7ac080/status.json \
  --retirement-receipt /var/lib/gambit-releases/9654b7de0b90d7f9a85718638effc271f6d6c6e1-c5f149eefa65/receipt.json
```

Replace uppercase placeholders with verified hashes. The `review` action takes
one bounded research-metadata snapshot under maintenance locks and saves the
proposal, snapshot, code plan, before-images and receipt outside the application.
Retain that complete review package; retrieve it after a connection loss instead
of repeating the scan. It does not scan numerical data or row-lineage catalogs. Stop for the user's explicit approval of this concrete
proposal. The proposal is inert; do not synthesize an approval from a prior PR
approval, a successful test run or this documentation.

Only after that human decision has been recorded as the existing immutable
execution-approval document, run `plan` with the same arguments and
`--approval /protected/approved-proposal.json`. `--operator-sha256` is not needed
for `plan` or `apply`; the approved proposal already pins the original operator.
Inspect and retain the resulting plan, including its retirement context,
acknowledgement, complete authority snapshot and `plan_sha256`.

Run `apply` with those same inputs, the actual approval, and
`--plan-sha256 REVIEWED_PLAN_SHA256` only within the approved release procedure.
Application reacquires the existing locks, revalidates all evidence and both
archives, checks the unchanged original code, and recreates the exact plan
before any installation. It rechecks research authority and the retired
definitions' absence afterward. A changed cohort or evidence requires a fresh
review; it is not permission to force the old plan through.

The tool leaves services stopped. The approved release procedure separately
verifies installation and health, resumes the single worker, and activates the
appropriate read-only monitoring. Do not deploy unrelated PRs or modify frozen
research definitions during this operation.

## Retained evidence and recovery

The release state keeps a protected copy of both exact archives, the three
historical evidence files, their bound context, and the exact release-evidence
index. Do not delete those inputs after installation. Recovery must remain
possible without relying on a mutable incoming directory or workstation.

```sh
/opt/gambit/venv/bin/python -B /protected/control/deploy/program_cutover.py recover \
  --root /srv/gambit/research_platform \
  --manifest /protected/program-manifest.json \
  --release-id program-COMMIT-ATTEMPT
```

Recovery requires the same quiescent services, recent backup and maintenance
locks. It verifies saved evidence and absences, then restores code only. It
refuses after any authoritative research change, including new execution
intents or trial records, and refuses changed retirement evidence. It never
recreates the retired definitions, erases new research or discards approval
history. Investigate a blocked recovery and prepare an explicitly reviewed
forward repair or reverse-compatibility route.
