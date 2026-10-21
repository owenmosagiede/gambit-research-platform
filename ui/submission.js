"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const form = document.querySelector('form[aria-label="Experiment inputs"]');
  const submit = $("experiment-submit");
  if (!form || !submit) return;
  const fields = ["feature", "target", "scope", "expected-direction"].map($);
  const activeStates = new Set(["queued", "resolving", "preparing", "p1", "p2"]);
  const labels = {queued:"Queued", resolving:"Checking inputs", preparing:"Preparing observations", p1:"P1", p2:"P2", blocked:"Blocked", failed:"Execution failed", cancelled:"Cancelled", succeeded:"Completed"};
  const storageKey = "research-platform.experiment-request.v1";
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const text = value => typeof value === "string" && value.trim().length > 0;
  const ref = value => value && text(value.id) && text(value.version);
  const count = value => Number.isSafeInteger(value) && value >= 0;
  let readiness = null, readinessBusy = false, busy = false, current = null;
  let healthTimer = null, pageActive = true;
  function el(tag, value) { const n = document.createElement(tag); n.textContent = value; return n; }
  function blockers(node, rows) { node.replaceChildren(...rows.map(row => el("li", row.message))); node.hidden = rows.length === 0; }
  function validPayload(value) {
    return value && uuid.test(value.request_id) && ref(value.feature) && ref(value.scope) &&
      value.target_family === "price_return" && ["POSITIVE", "NEGATIVE"].includes(value.expected_direction);
  }

  function storeRequest() {
    try {
      if (current) window.sessionStorage.setItem(storageKey, JSON.stringify({payload: current.payload, selection: current.selection}));
    } catch (_error) { /* The in-memory request remains usable if browser storage is unavailable. */ }
  }

  function renderSpecification() {
    const node = $("research-specification");
    if (!node) return;
    let chosen = null, resolution = null;
    try { chosen = JSON.parse($("feature").value); resolution = JSON.parse($("feature").dataset.featureResolution || "null"); } catch (_error) { /* No selection. */ }
    const external = chosen && ($("feature").dataset.featureKind === "stored_feature" ||
      (resolution?.recipe?.reference?.id === chosen.id && resolution.recipe.kind === "stored_feature"));
    const spec = external ? resolution && resolution.research_spec : readiness && readiness.research_spec;
    node.textContent = spec ? `Research Spec: ${spec.id} · ${spec.version} (fixed by the backend)`
      : external ? "Research Spec: external alignment compatibility must be verified." : "";
    if (readiness) $("research-method-summary").textContent = external
      ? "External stored Feature: individual instrument TS only. Five horizons: 1, 7, 21, 63, 252 scheduled weekdays."
      : readiness.method_summary;
  }

  function readBlockers(rows) {
    if (!Array.isArray(rows) || rows.some(row => !row || !text(row.code) || !text(row.message))) {
      throw new Error("Invalid readiness reasons");
    }
    return rows;
  }

  function readJob(value) {
    const job = value && value.job;
    const receipt = job?.submission_receipt;
    const linked = current && receipt?.request_id === current.payload.request_id &&
      receipt.canonical_request_id === job.request_id && /^[0-9a-f]{64}$/.test(receipt.scientific_identity) &&
      /^[0-9a-f]{64}$/.test(receipt.journal_sha256);
    if (!job || !current || (job.request_id !== current.payload.request_id && !linked && job.request_id !== current.job?.request_id) || !Object.prototype.hasOwnProperty.call(labels, job.status) ||
        !text(job.stage) || typeof job.message !== "string" || ![null, "TS", "CS"].includes(job.mode) ||
        !job.progress || !count(job.progress.completed) || !count(job.progress.total) ||
        job.progress.completed > job.progress.total || !Array.isArray(job.horizons) ||
        !Array.isArray(job.results) || !job.results.every(value => ref(value) && /^[0-9a-f]{64}$/.test(value.content_sha256)) ||
        !text(job.created_at) || !text(job.updated_at)) throw new Error("Invalid experiment response");
    readBlockers(job.blockers);
    if (job.resume_blocker) readBlockers([job.resume_blocker]);
    const horizons = new Set();
    for (const row of job.horizons) {
      if (!row || ![1, 7, 21, 63, 252].includes(row.horizon) || horizons.has(row.horizon) ||
          !text(row.p1_status) || !text(row.p2_status)) throw new Error("Invalid horizon progress");
      horizons.add(row.horizon);
    }
    return job;
  }

  async function request(url, method = "GET", body) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 20000);
    try {
      const options = {method, mode: "same-origin", credentials: "same-origin", cache: "no-store", signal: controller.signal};
      if (body !== undefined) { options.headers = {"Content-Type": "application/json"}; options.body = JSON.stringify(body); }
      const response = await fetch(url, options);
      if (!response.ok) {
        const error = new Error("Request unavailable"); error.status = response.status;
        if ([400, 403, 404, 409, 422].includes(response.status)) { try { error.rejection = await response.json(); } catch (_error) { /* Unknown response remains uncertain. */ } }
        throw error;
      }
      return await response.json();
    } finally { window.clearTimeout(timer); }
  }

  async function loadReadiness() {
    if (readinessBusy) return;
    if (healthTimer !== null) window.clearTimeout(healthTimer);
    readinessBusy = true; controls();
    try {
      const value = await request("/api/research-readiness");
      if (!value || typeof value.implementation_installed !== "boolean" || typeof value.execution_enabled !== "boolean" ||
          typeof value.method_summary !== "string" || (value.execution_enabled && !value.implementation_installed)) throw new Error("Invalid readiness response");
      readBlockers(value.blockers); readiness = value;
      $("research-readiness-status").textContent = value.execution_enabled
        ? "Research service is ready. A compatible selection enables Submit to queue preparation and P1 across all five horizons. Admitted candidates proceed to P2."
        : value.implementation_installed ? "P1 and P2 are installed. Execution is blocked until the following requirements are resolved."
          : "P1 and P2 execution is not installed.";
      $("research-method-summary").textContent = value.method_summary;
      renderSpecification();
      blockers($("research-readiness-blockers"), value.blockers);
      $("research-readiness-retry").hidden = value.execution_enabled;
      const incidents = $("research-operational-incidents");
      if (incidents) blockers(incidents, (value.submission_incidents || []).map(item => ({message:
        `Operational failure ${item.id} · ${item.request_id || item.storage_path}: ${item.message}`})));
    } catch (_error) {
      readiness = null;
      $("research-readiness-status").textContent = "Research readiness could not be checked. No submission will start until it is verified.";
      $("research-method-summary").textContent = "";
      blockers($("research-readiness-blockers"), []);
      $("research-readiness-retry").hidden = false;
    } finally { readinessBusy = false; controls(); if (pageActive) healthTimer = window.setTimeout(() => { loadReadiness(); if (current?.uncertain && !current.notRecorded) recover(false); }, 15000); }
  }

  function selectedReference(node, bindingKey) {
    const value = JSON.parse(node.value), binding = JSON.parse(node.dataset[bindingKey] || "null");
    if (node.disabled || !ref(value) || !ref(binding) || value.id !== binding.id || value.version !== binding.version) {
      throw new Error("Selection is still resolving");
    }
    return {id: value.id, version: value.version};
  }

  function selectionPayload() {
    if (!form.reportValidity()) return null;
    if ($("target").disabled || $("target").value !== "price" || $("target").dataset.returnBasis !== "price" ||
        !["POSITIVE", "NEGATIVE"].includes($("expected-direction").value)) throw new Error("Select all four inputs");
    return {feature: selectedReference($("feature"), "featureReference"), target_family: "price_return",
      scope: selectedReference($("scope"), "scopeReference"), expected_direction: $("expected-direction").value};
  }

  function selectionNames() {
    const name = node => node.selectedOptions && node.selectedOptions[0] ? node.selectedOptions[0].textContent : node.value;
    return {Feature: name($("feature")), Target: "Price Return · 1, 7, 21, 63 and 252 scheduled weekdays",
      Scope: name($("scope")), "Expected Direction": name($("expected-direction"))};
  }

  function selectionProblem() {
    const names = ["Feature", "Target", "Scope", "Expected Direction"];
    for (const [index, field] of fields.entries()) {
      if (field.disabled) return `${names[index]} is unavailable or still loading. See its status above.`;
      if (!field.value) return "Choose Feature, Target, Scope and Expected Direction before submitting.";
      if (field.validity && field.validity.valid === false) return field.validationMessage || `Choose a valid ${names[index]}.`;
      if (field.selectedOptions?.[0]?.disabled) return `${names[index]} is not available for submission.`;
    }
    if ($("target").value !== "price" || $("target").dataset.returnBasis !== "price") return "Choose an available return Target.";
    if (!["POSITIVE", "NEGATIVE"].includes($("expected-direction").value)) return "Choose Positive or Negative Expected Direction.";
    let feature, scope;
    try { feature = selectedReference($("feature"), "featureReference"); scope = selectedReference($("scope"), "scopeReference"); }
    catch (_error) { return "Wait for the selected Feature and Scope identities to finish loading."; }
    // All Features need affirmative, current Scope compatibility. Stored
    // observation counts and live-readiness counts are not submission gates.
    {
      let resolution;
      try { resolution = JSON.parse($("feature").dataset.featureResolution || "null"); } catch (_error) { /* Remain blocked. */ }
      if (!resolution || resolution.recipe?.reference?.id !== feature.id || resolution.recipe.reference.version !== feature.version ||
          resolution.scope?.id !== scope.id || resolution.scope.version !== scope.version) return "Checking Feature compatibility with the selected Scope…";
      const legacyNative = resolution.recipe.kind === "reusable_fx_recipe" && !("application" in resolution) && !("submission_compatible" in resolution);
      if (resolution.submission_compatible !== true && !legacyNative) return resolution.source_application_note || "This Feature and Scope combination is unsupported.";
    }
    return "";
  }

  function controls() {
    renderSpecification();
    const selectionIssue = selectionProblem();
    submit.disabled = Boolean(selectionIssue) || busy || !readiness?.execution_enabled || Boolean(current?.uncertain && !current.notRecorded);
    submit.textContent = busy ? "Checking submission…" : "Submit";
    const reason = busy ? "Submit is paused while the previous request is checked."
      : current?.uncertain && !current.notRecorded
        ? "Submit is paused because a previous submission has an unconfirmed receipt. Check its status below; changing inputs does not clear this safeguard."
      : !readiness?.execution_enabled ? "Submit is unavailable until research readiness is verified. See the readiness details below."
      : selectionIssue ? selectionIssue
      : current?.rejection ? "The previous submission was rejected by the local connection check. Reload this page before trying again. You can dismiss its notice in Needs attention."
      : current?.notRecorded ? "The previous request was not found on the server. Submit is available for your current selections. Unchanged selections reuse its original submission ID."
      : "";
    $("submit-availability").textContent = reason;
    $("submit-availability").hidden = !reason;
    $("submission-check").hidden = !current?.uncertain;
    $("submission-check").disabled = busy;
    submit.title = submit.disabled ? reason : "";
    $("research-readiness-retry").disabled = readinessBusy;
    window.researchSubmissionState = current ? {...current, busy} : null;
    window.dispatchEvent(new CustomEvent("research-submission-state", {detail: window.researchSubmissionState}));
  }
  function notice(message) { $("submission-notice").textContent = message; }
  function accepted(job) {
    current.job = job; current.uncertain = false; current.notRecorded = false; current.rejection = null; current.message = "";
    notice(job.intake_action === "view_results" ? "View existing trial/results — this experiment is already completed."
      : job.intake_action === "recover_existing" ? "An existing trial needs recovery. Use its Resume action when available; no new experiment was queued."
      : job.intake_action === "view_existing" ? "View existing trial/results — this experiment is already recorded."
      : job.status === "succeeded" || job.status === "cancelled"
      ? "Submission finished. Its saved outcomes are in Trial Ledger."
      : "Submission recorded. Follow its trial card below.");
    if (["view_existing", "view_results", "recover_existing"].includes(job.intake_action)) {
      const link = el("a", "View existing trial/results");
      link.href = ["succeeded", "cancelled", "failed", "blocked"].includes(job.status) ? "#ledger" : `#trial-${encodeURIComponent(job.request_id)}`;
      if (["succeeded", "cancelled", "failed", "blocked"].includes(job.status)) link.addEventListener("click", () =>
        window.dispatchEvent(new CustomEvent("research-ledger-focus", {detail:{request_id:job.request_id}})));
      $("submission-notice").append(link);
    }
    window.dispatchEvent(new CustomEvent("research-job-update", {detail:{job, intent: {
      feature: current.payload.feature, scope: current.payload.scope,
      target_family: current.payload.target_family, expected_direction: current.payload.expected_direction
    }, selection: current.selection}}));
  }
  function failure(error) {
    const server = error.rejection?.error;
    return server && text(server.message) ? `${server.message}${text(server.code) ? ` (${server.code})` : ""}`
      : error.name === "AbortError" ? "The server did not respond within 20 seconds."
      : error.status ? `The server returned HTTP ${error.status}.` : "The server could not be reached or its response could not be verified.";
  }
  async function postFrozen() {
    current.notRecorded = false; current.rejection = null;
    current.message = "Saving this request with its frozen selections…"; controls();
    try { accepted(readJob(await request("/api/experiments", "POST", current.payload))); }
    catch (error) {
      if (error.status === 403 && ["INVALID_ORIGIN", "INVALID_HOST"].includes(error.rejection?.error?.code)) {
        // These endpoint guards reject before invoking the job store, including on older servers.
        current.uncertain = false; current.notRecorded = true;
        current.rejection = error.rejection.error;
        current.message = failure(error) + " This request was rejected before research could start. Reload this page before retrying. Dismiss removes only this local notice.";
        storeRequest(); notice("Submission rejected by the local connection check. See its dismissible notice below.");
      } else if (error.status === 422 && error.rejection?.recorded === false && error.rejection.error?.code === "EXTERNAL_ALIGNMENT_BLOCKED") {
        const reasons = readBlockers(error.rejection.blockers);
        notice("Not submitted. No research job was recorded. " + reasons.map(r => r.message).join(" "));
        current = null;
        try { window.sessionStorage.removeItem(storageKey); } catch (_error) { /* Nothing was recorded. */ }
      } else {
        current.uncertain = true;
        current.message = failure(error) + " Receipt is unconfirmed. Check or retry on this card; the same submission ID will be used.";
        notice("Submission needs attention. See its trial card below.");
      }
    }
  }
  async function recover(resend) {
    if (busy || !current) return;
    busy = true; current.notRecorded = false; current.message = "Checking whether the server saved this request…"; controls();
    try { accepted(readJob(await request(`/api/experiments/${encodeURIComponent(current.payload.request_id)}`))); }
    catch (error) {
      current.uncertain = true;
      if (error.status === 404) {
        if (resend && readiness?.execution_enabled) await postFrozen();
        else { current.notRecorded = true; current.message = "This request was not found on the server. Submit is available for the current selections. Check and retry sends these frozen selections with the same ID."; }
      } else current.message = failure(error) + " Nothing was resent. Check again before starting another submission.";
    } finally { busy = false; controls(); }
  }
  async function dismissLocal(requestId) {
    if (busy || !current || current.payload.request_id !== requestId) return;
    // Unknown receipts must be resolved before dropping this browser's recovery handle.
    if (!current.rejection) await recover(false);
    if (!current || current.payload.request_id !== requestId || (!current.notRecorded && !current.rejection)) return;
    try { window.sessionStorage.removeItem(storageKey); }
    catch (_error) { current.message = "This browser could not save the dismissal. The notice remains available."; controls(); return; }
    current = null;
    notice("Local submission notice dismissed. No research records were deleted or cancelled.");
    controls();
  }
  window.addEventListener("research-submission-dismiss", event => dismissLocal(event.detail?.request_id));
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !readiness?.execution_enabled || (current?.uncertain && !current.notRecorded)) return;
    if (selectionProblem()) { controls(); return; }
    let payload;
    try {
      payload = selectionPayload(); if (!payload) return;
      const comparable = v => JSON.stringify([v.feature, v.target_family, v.scope, v.expected_direction]);
      if (current?.job && activeStates.has(current.job.status) && comparable(payload) === comparable(current.payload)) {
        notice("This selection already has an active trial card. Its status is updating below.");
        window.dispatchEvent(new CustomEvent("research-queue-refresh")); return;
      }
      // A missing receipt is not permission to create a duplicate of the same intent.
      payload.request_id = current?.notRecorded && comparable(payload) === comparable(current.payload)
        ? current.payload.request_id : window.crypto.randomUUID();
      if (!validPayload(payload)) throw Error("Invalid request identity");
    } catch (_error) { notice("Choose all four inputs and wait for their identities to finish loading before submitting."); return; }
    current = {payload: JSON.parse(JSON.stringify(payload)), selection: selectionNames(), job:null, uncertain:true, message:"Saving request…"};
    storeRequest(); busy = true; controls();
    try { await postFrozen(); } finally { busy = false; controls(); }
  });
  window.addEventListener("research-submission-recover", event => {
    if (event.detail?.request_id === current?.payload.request_id) recover(event.detail.resend === true);
  });
  window.addEventListener("research-queue-state", event => {
    if (!current || busy) return;
    const found = event.detail?.items?.find(item => item.job.request_id === (current.job?.request_id || current.payload.request_id));
    if (!found) return;
    try {
      const job = readJob({job:found.job});
      const changed = current.uncertain || JSON.stringify(current.job) !== JSON.stringify(job);
      current.job = job; current.uncertain = false; current.notRecorded = false; current.rejection = null; current.message = "";
      if (changed) { notice("Submission recorded. Its status and outcomes are on the trial card or in Trial Ledger."); controls(); }
    } catch (_error) { /* An invalid queue row cannot confirm a submission. */ }
  });
  for (const event of ["feature-state-change", "scope-state-change", "target-state-change"]) window.addEventListener(event, controls);
  $("submission-check").addEventListener("click", () => recover(false));
  $("research-readiness-retry").addEventListener("click", loadReadiness);
  for (const field of fields) field.addEventListener("change", controls);
  window.addEventListener("pagehide", () => { pageActive = false; window.clearTimeout(healthTimer); });
  window.addEventListener("pageshow", () => { pageActive = true; loadReadiness(); if (current?.uncertain) recover(false); });
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(storageKey) || "null");
    if (saved && validPayload(saved.payload)) {
      current = {payload:saved.payload, selection:saved.selection && Object.values(saved.selection).every(text) ? saved.selection : null,
        job:null, uncertain:true, message:"Checking saved submission…"};
    }
  } catch (_error) { /* Invalid saved state cannot launch work. */ }
  loadReadiness();
  if (current) recover(false);
})();
