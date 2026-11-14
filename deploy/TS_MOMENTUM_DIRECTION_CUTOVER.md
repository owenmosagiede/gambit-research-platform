# TS momentum direction cutover

The `DISCOVERY_SIGN_V1` request policy applies the existing P1 strength and
stability gates to either sign. The P2 trial binds to the selected sign,
original P1 trial and admission before the validation data are read. Fixed
direction requests retain their prior behavior. The profile, Feature formulas,
Target definitions and horizon-specific periods stay the same.

The cutover keeps the accepted science and the original roster. Unstarted
queued requests get deterministic successors that reuse their frozen inputs.
The originals retain their submission and event history and link to their
successors. The remaining staged rows and eligible P2-only follow-ups go to a
new paced manifest. A follow-up must reference the exact prior direction
precheck and original P1 result. The exposure ledger is checked at review and
again before evaluation. These follow-ups are retrospective because earlier
related research used the validation history.

1. Prepare the clean merged release with passing isolated checks. Verify the
   off-host backup and original installed archive. Stage the reviewed operator
   separately from application code.
2. Pause intake at its checkpoint. Drain the worker using its normal service
   stop so the current request finishes. Pause web intake for the reviewed
   cutover. Run `deploy/ts_momentum_direction_release.py review` against the
   verified staged artifact. Compare the current, replaced, staged, and
   P2-only counts and record the exact approved proposal hash before applying.
3. Run `apply` with that hash. The code transaction verifies checksums and
   saves before-images. Queue replacement uses the existing research intake
   and event journals with the worker stopped. Check the release receipt,
   running services, and new queue. Confirm the first follow-up references
   the original P1 trial and has no P1 sample access.
4. Before any queue change, a failed source installation restores its
   before-images. After source installation and queue mutation, recover
   forward using the same approved proposal and deterministic request IDs.
   The `resume` command only completes service startup for a verified
   `queue_ready` receipt.
