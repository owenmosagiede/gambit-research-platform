"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const select = $("feature"), scope = $("scope"), status = $("feature-status");
  const panel = $("feature-coverage"), coverageStatus = $("feature-coverage-status");
  if (!select || !scope || !status || !panel) return;
  let entries = [], catalogGeneration = 0, resolutionGeneration = 0;
  let catalogController = null, resolutionController = null;
  let lastScopeBinding = null, refreshSelection = null, catalogPending = false;
  const text = value => typeof value === "string" && value.trim().length > 0;
  const count = value => Number.isSafeInteger(value) && value >= 0;
  const reference = value => value && text(value.id) && text(value.version) && /^[0-9a-f]{64}$/.test(value.content_sha256);
  const sameReference = (a, b) => reference(a) && reference(b) && a.id === b.id &&
    a.version === b.version && a.content_sha256 === b.content_sha256;
  const choice = item => JSON.stringify({id: item.id, version: item.version});
  const selected = () => entries.find(item => choice(item) === select.value);
  const catalogNote = () => entries.length ? `${entries.length} registered Features. Choose a registered Feature recipe.` :
    "No registered Features are available.";
  const scopeBinding = () => JSON.stringify([scope.value, scope.dataset.scopeReference || "",
    scope.dataset.membershipSnapshot || "", scope.dataset.scopeResolution || ""]);
  const signalPattern = /^SIGNAL_[0-9a-f]{64}$/;
  const materializationPattern = /^MATERIALIZATION_[0-9a-f]{64}$/;
  const readinessKeys = ["retrospective_research", "historical_replay", "live_use"];
  function el(tag, label, className) {
    const node = document.createElement(tag);
    if (label !== undefined) node.textContent = label;
    if (className) node.className = className;
    return node;
  }
  function option(label, value = "", disabled = false) {
    const node = el("option", label);
    node.value = value; node.disabled = disabled;
    return node;
  }
  function scopeSelection() {
    try {
      const value = JSON.parse(scope.value);
      const binding = JSON.parse(scope.dataset.scopeResolution);
      const definition = JSON.parse(scope.dataset.scopeReference);
      const membership = JSON.parse(scope.dataset.membershipSnapshot);
      if (value && text(value.id) && text(value.version) && binding.id === value.id && binding.version === value.version &&
          definition.id === value.id && definition.version === value.version &&
          sameReference(binding.reference, definition) && sameReference(binding.definition_binding, definition) &&
          sameReference(binding.membership_snapshot, membership)) {
        return {...value, reference: definition, membership_snapshot: membership};
      }
    } catch (_error) { /* No Scope selected. */ }
    return null;
  }
  function operatorText(item) {
    return item.transformations.map(step => {
      const params = step.parameters.map(p => `${p.name}=${p.value.value}`).join(", ");
      return step.label + (params ? ` (${params})` : "");
    }).join(" → ");
  }
  function validEntry(item) {
    return item && text(item.id) && text(item.version) && text(item.name) &&
      ["reusable_fx_recipe", "stored_feature"].includes(item.kind) && item.registration_state === "registered" &&
      reference(item.reference) && item.reference.id === item.id && item.reference.version === item.version &&
      (item.signal_id === null || signalPattern.test(item.signal_id)) && Array.isArray(item.transformations) &&
      item.transformations.length > 0 && item.transformations.every(step => reference(step.operator) &&
        text(step.label) && Array.isArray(step.parameters) && step.parameters.every(p => text(p.name) &&
          p.value && p.value.value !== undefined));
  }
  function readCatalog(value) {
    if (!value || value.schema_version !== "1.0.0" || !Array.isArray(value.features) ||
        value.feature_count !== value.features.length || !Array.isArray(value.issues) ||
        !value.features.every(validEntry) || new Set(value.features.map(choice)).size !== value.feature_count) {
      throw new Error("Invalid Feature catalog");
    }
    return value;
  }
  const decision = value => typeof value === "string" ? value : value && value.decision;
  function validReadiness(value) {
    return value && readinessKeys.every(key => text(decision(value[key])));
  }
  function validMaterialization(item, sourceOnly = false) {
    return item && reference(item.reference) && materializationPattern.test(item.reference.id) &&
      reference(item.legacy_feature) && signalPattern.test(item.signal_id) && count(item.row_count) &&
      item.status_counts && ["valid", "missing", "invalid"].every(key => count(item.status_counts[key])) &&
      item.row_count === item.status_counts.valid + item.status_counts.missing + item.status_counts.invalid &&
      item.coverage && ["reference_start", "reference_end", "cutoff_start", "cutoff_end"].every(key =>
        item.coverage[key] === null || text(item.coverage[key])) &&
      (validReadiness(item.readiness_capabilities) || (sourceOnly && item.readiness_capabilities &&
        Object.keys(item.readiness_capabilities).length === 0));
  }
  function readResolution(value, feature, chosenScope) {
    if (!value || value.schema_version !== "1.0.0" || value.selection_read_only !== true ||
        value.registration_state !== "registered" || !value.recipe || !sameReference(value.recipe.reference, feature.reference) ||
        value.recipe.kind !== feature.kind || !value.scope || value.scope.id !== chosenScope.id ||
        value.scope.version !== chosenScope.version || !reference(value.scope.reference) ||
        value.scope.reference.id !== chosenScope.id || value.scope.reference.version !== chosenScope.version ||
        !sameReference(value.scope.reference, chosenScope.reference) ||
        !sameReference(value.scope.membership_snapshot, chosenScope.membership_snapshot) ||
        !reference(value.scope.membership_snapshot) || !text(value.scope.display_name) ||
        !count(value.member_count) || !Array.isArray(value.members) || value.members.length !== value.member_count ||
        new Set(value.members.map(item => item.instrument_id)).size !== value.member_count ||
        !Array.isArray(value.issues) || !value.summary || !value.members.every(item => item && text(item.instrument_id) &&
          ["materialized", "missing", "blocked"].includes(item.state) && (item.reason === null || text(item.reason)) &&
          Array.isArray(item.materializations) && item.materializations.every(m => validMaterialization(m)) &&
          (item.state === "materialized" ? item.materializations.length > 0 : item.materializations.length === 0) &&
          validReadiness(item.readiness)) || !["materialized", "missing", "blocked"].every(state =>
          value.summary[`${state}_member_count`] === value.members.filter(item => item.state === state).length)) {
      throw new Error("Invalid Feature and Scope resolution");
    }
    if (value.source_materializations !== undefined && (feature.kind !== "stored_feature" ||
        !Array.isArray(value.source_materializations) || !text(value.source_application_note) ||
        !value.source_materializations.every(item => validMaterialization(item, true)))) {
      throw new Error("Invalid source coverage");
    }
    return value;
  }
  async function fetchValue(url, controller) {
    const timeout = window.setTimeout(() => controller.abort(), 600000);
    try {
      const response = await fetch(url, {method: "GET", mode: "same-origin", credentials: "same-origin",
        cache: "no-store", signal: controller.signal});
      if (!response.ok) throw new Error("Unavailable");
      return await response.json();
    } finally { window.clearTimeout(timeout); }
  }
  function clearResolution() {
    ++resolutionGeneration;
    if (resolutionController) resolutionController.abort();
    delete select.dataset.featureResolution;
    window.dispatchEvent(new CustomEvent("feature-state-change"));
    $("feature-coverage-body").replaceChildren();
    $("feature-coverage-retry").hidden = true;
    panel.setAttribute("aria-busy", "false");
  }
  function openSignal(id, materializationId = null) {
    if (!signalPattern.test(id) || (materializationId && !materializationPattern.test(materializationId))) return;
    const detail = {signal_id: id};
    if (materializationId) detail.materialization_id = materializationId;
    window.dispatchEvent(new CustomEvent("open-signal", {detail}));
  }
  function renderReadiness(value) {
    const node = el("div");
    for (const [key, label] of [["retrospective_research", "Retrospective"], ["historical_replay", "Historical replay"], ["live_use", "Live use"]]) {
      const state = decision(value[key]);
      const item = el("span", `${label}: ${state.replaceAll("_", " ")}`, "cell-secondary");
      if (value[key] && text(value[key].reason)) item.title = value[key].reason;
      node.append(item);
    }
    return node;
  }
  function renderResolution(value) {
    const total = value.member_count, summary = value.summary;
    $("feature-coverage-title").textContent = `Stored coverage · ${value.scope.display_name}`;
    coverageStatus.textContent = `${summary.materialized_member_count} of ${total} members have matching stored outputs. ` +
      `${summary.missing_member_count} missing · ${summary.blocked_member_count} blocked. ` +
      "Readiness applies only to the stored periods shown.";
    const wrap = el("div", undefined, "table-scroll");
    wrap.tabIndex = 0; wrap.setAttribute("role", "region"); wrap.setAttribute("aria-label", "Feature coverage by Scope member");
    const table = el("table", undefined, "signal-table feature-coverage-table");
    const head = el("thead"), header = el("tr"), body = el("tbody");
    for (const label of ["Instrument", "Stored coverage", "Readiness"]) {
      const cell = el("th", label); cell.scope = "col"; header.append(cell);
    }
    head.append(header);
    for (const member of value.members) {
      const row = el("tr");
      const coverage = el("td", undefined, "coverage-cell");
      const state = {materialized: "Stored outputs", missing: "Not materialized", blocked: "Blocked"}[member.state];
      coverage.append(el("span", state, "status-pill"));
      for (const materialization of member.materializations) {
        const period = materialization.coverage;
        coverage.append(el("span", `${period.reference_start || "Unknown start"} – ${period.reference_end || "Unknown end"}`, "cell-secondary"));
        coverage.append(el("span", `${materialization.row_count} scheduled observations · ${materialization.status_counts.valid} valid · ` +
          `${materialization.status_counts.missing} missing · ${materialization.status_counts.invalid} invalid`, "cell-secondary"));
        const button = el("button", "View stored Signal ↗", "text-button"); button.type = "button";
        button.addEventListener("click", () => openSignal(materialization.signal_id, materialization.reference.id)); coverage.append(button);
      }
      if (member.reason) coverage.append(el("span", member.reason.replaceAll("_", " "), "cell-secondary"));
      const readiness = el("td", undefined, "readiness-cell"); readiness.append(renderReadiness(member.readiness));
      row.append(el("td", member.instrument_id), coverage, readiness); body.append(row);
    }
    table.append(head, body); wrap.append(table);
    const content = $("feature-coverage-body"); content.replaceChildren();
    if (value.source_materializations && value.source_materializations.length) {
      const source = el("div", undefined, "research-note");
      source.append(el("strong", "Existing source observations"));
      for (const item of value.source_materializations) {
        source.append(el("span", `${item.coverage.reference_start || "Unknown start"} – ${item.coverage.reference_end || "Unknown end"} · ` +
          `${item.row_count} observations`, "cell-secondary"));
        const button = el("button", "View stored Signal ↗", "text-button"); button.type = "button";
        button.addEventListener("click", () => openSignal(item.signal_id, item.reference.id)); source.append(button);
      }
      source.append(el("p", value.source_application_note, "field-note")); content.append(source);
    }
    content.append(wrap);
    if (value.issues.length) coverageStatus.textContent += " Unusable records are excluded from coverage and readiness. See member statuses.";
  }
  async function resolveSelection() {
    clearResolution();
    lastScopeBinding = scopeBinding();
    const item = selected(), chosenScope = scopeSelection();
    $("feature-details-link").hidden = !item || !item.signal_id;
    if (!item) {
      delete select.dataset.featureReference; delete select.dataset.experimentFeature; delete select.dataset.featureKind;
      select.title = "";
      select.setCustomValidity(catalogPending ? "Loading registered Features." : "Choose a registered Feature.");
      status.textContent = catalogPending ? "Loading registered Features…" : catalogNote(); panel.hidden = true;
      window.dispatchEvent(new CustomEvent("feature-state-change")); return;
    }
    select.dataset.featureReference = JSON.stringify(item.reference);
    select.dataset.featureKind = item.kind;
    select.dataset.experimentFeature = choice(item);
    select.setCustomValidity(item.kind === "stored_feature" ? "Check external Feature compatibility with Scope." : "");
    select.title = item.name;
    const registered = item.kind === "reusable_fx_recipe" ? "Registered recipe" : "Registered stored Feature";
    status.textContent = `${registered}. ` + (chosenScope ? "Checking selected Scope coverage…" : "Choose Scope to check stored coverage.");
    panel.hidden = !chosenScope;
    if (!chosenScope) { window.dispatchEvent(new CustomEvent("feature-state-change")); return; }
    const generation = resolutionGeneration;
    const selection = select.value, binding = scopeBinding();
    resolutionController = new AbortController(); const active = resolutionController;
    panel.setAttribute("aria-busy", "true");
    $("feature-coverage-title").textContent = "Stored coverage";
    coverageStatus.textContent = "Checking existing outputs for the selected Feature and Scope…";
    try {
      const query = `feature_id=${encodeURIComponent(item.id)}&feature_version=${encodeURIComponent(item.version)}` +
        `&scope_id=${encodeURIComponent(chosenScope.id)}&scope_version=${encodeURIComponent(chosenScope.version)}`;
      const value = readResolution(await fetchValue(`/api/feature-resolution?${query}`, active), item, chosenScope);
      if (generation !== resolutionGeneration || select.value !== selection || scopeBinding() !== binding) return;
      select.dataset.featureResolution = JSON.stringify(value);
      status.textContent = `${registered}. ${value.summary.materialized_member_count}/${value.member_count} Scope members have matching stored outputs.`;
      // During an idle-server upgrade, an older backend may still serve native
      // coverage without capability fields. Preserve its existing native rule.
      // The new backend always returns application and submission_compatible,
      // including explicit false/null for missing or unsupported contracts.
      const legacyNative = item.kind === "reusable_fx_recipe" && !("application" in value) && !("submission_compatible" in value);
      select.setCustomValidity(value.submission_compatible === true || legacyNative ? "" : (value.source_application_note || "Feature application compatibility is unavailable."));
      if (value.submission_compatible !== true && !legacyNative && item.kind !== "stored_feature") status.textContent += ` ${value.source_application_note || "Application compatibility is unavailable."}`;
      if (item.kind === "stored_feature") {
        const compatible = value.submission_compatible === true;
        select.setCustomValidity(compatible ? "" : (value.source_application_note || "External Feature alignment is unavailable."));
        status.textContent = `${registered}. ${value.source_application_note}`;
        if (value.alignment_policy) status.textContent += ` Policy: ${value.alignment_policy.id} v${value.alignment_policy.version}.`;
      }
      renderResolution(value);
      window.dispatchEvent(new CustomEvent("feature-state-change"));
    } catch (_error) {
      if (generation !== resolutionGeneration) return;
      delete select.dataset.featureResolution;
      select.setCustomValidity("Coverage for this Feature and Scope could not be verified.");
      status.textContent = `${registered}. Scope coverage could not be verified.`;
      coverageStatus.textContent = "Stored coverage could not be checked. Retry or choose another Feature or Scope.";
      $("feature-coverage-retry").hidden = false;
    } finally {
      if (generation === resolutionGeneration) { panel.setAttribute("aria-busy", "false"); window.dispatchEvent(new CustomEvent("feature-state-change")); }
    }
  }
  async function load() {
    const previous = selected() || refreshSelection;
    refreshSelection = previous;
    catalogPending = true;
    const generation = ++catalogGeneration;
    if (catalogController) catalogController.abort();
    catalogController = new AbortController(); const active = catalogController;
    entries = []; select.disabled = true; select.value = ""; select.title = "";
    delete select.dataset.featureReference; delete select.dataset.experimentFeature; delete select.dataset.featureKind;
    delete select.dataset.catalogCount;
    clearResolution(); panel.hidden = true;
    select.setCustomValidity("Loading registered Features."); select.setAttribute("aria-busy", "true");
    select.replaceChildren(option("Loading features…", "", true));
    status.textContent = "Loading registered Features…";
    $("feature-retry").hidden = true; $("feature-details-link").hidden = true;
    try {
      const value = readCatalog(await fetchValue("/api/feature-library", active));
      if (generation !== catalogGeneration) return;
      entries = value.features;
      catalogPending = false;
      refreshSelection = null;
      select.dataset.catalogCount = String(entries.length);
      const placeholder = option(entries.length ? "Select a feature" : "No registered Features", "", true);
      placeholder.selected = true; select.replaceChildren(placeholder);
      for (const item of entries) {
        const label = item.kind === "reusable_fx_recipe" ? `${item.name} · ${operatorText(item)}` : item.name;
        const node = option(label, choice(item)); node.title = item.name;
        node.dataset.registrationState = item.registration_state; select.append(node);
      }
      select.disabled = entries.length === 0;
      const retained = previous && entries.find(item => sameReference(item.reference, previous.reference));
      if (retained) select.value = choice(retained);
      await resolveSelection();
      if (generation !== catalogGeneration) return;
      if (!entries.length) status.textContent = "No registered Features are available.";
      if (value.issues.length) {
        status.textContent += " Some registry records are unavailable."; $("feature-retry").hidden = false;
      }
    } catch (_error) {
      if (generation !== catalogGeneration) return;
      entries = []; refreshSelection = null; catalogPending = false; select.disabled = true;
      select.replaceChildren(option("Features unavailable", "", true));
      status.textContent = "Registered Features could not be loaded. Retry to load the library.";
      select.setCustomValidity("Registered Features are unavailable."); $("feature-retry").hidden = false;
    } finally {
      if (generation === catalogGeneration) { select.setAttribute("aria-busy", "false"); window.dispatchEvent(new CustomEvent("feature-state-change")); }
    }
  }
  select.addEventListener("change", resolveSelection);
  const scopeChanged = () => { if (scopeBinding() !== lastScopeBinding) resolveSelection(); };
  scope.addEventListener("change", scopeChanged);
  window.addEventListener("scope-state-change", scopeChanged);
  window.addEventListener("experiment-catalog-refresh", load);
  $("feature-retry").addEventListener("click", load);
  $("feature-coverage-retry").addEventListener("click", resolveSelection);
  $("feature-details-link").addEventListener("click", () => { const item = selected(); if (item) openSignal(item.signal_id); });
  load();
})();
