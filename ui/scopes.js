(() => {
  "use strict";
  const select = document.getElementById("scope");
  const status = document.getElementById("scope-status");
  const retry = document.getElementById("scope-retry");
  if (!select || !status || !retry) return;

  let entries = [];
  let generation = 0;
  let controller = null;
  let retrySelection = false;
  let refreshSelection = null;
  const bindingKeys = ["scopeReference", "membershipSnapshot", "resolvedMembers", "experimentScope", "scopeDependency", "scopeResolution"];
  const catalogKeys = ["catalogCount", "universeCount", "instrumentCount"];
  const readinessCounts = ["stored_price_member_count", "retrospective_ready_member_count",
    "historical_replay_ready_member_count", "live_ready_member_count"];
  const text = value => typeof value === "string" && value.trim().length > 0;
  const count = value => Number.isSafeInteger(value) && value >= 0;
  const reference = value => value && text(value.id) && text(value.version) && /^[0-9a-f]{64}$/.test(value.content_sha256);
  const sameReference = (a, b) => reference(a) && reference(b) &&
    a.id === b.id && a.version === b.version && a.content_sha256 === b.content_sha256;
  const choice = item => JSON.stringify({id: item.id, version: item.version});
  const selected = () => entries.find(item => choice(item) === select.value);
  const catalogNote = () => entries.length
    ? `${entries.filter(item => item.kind === "universe").length} universes · ` +
      `${entries.filter(item => item.kind === "instrument").length} individual pairs. Choose a registered Scope.`
    : "No registered scopes are available.";

  function notifySelectionChanged() {
    // Other selectors may depend on Scope. Programmatic resets do not emit a
    // native change event, so disclose them without changing Scope resolution.
    if (typeof window.dispatchEvent === "function" && typeof CustomEvent === "function") {
      window.dispatchEvent(new CustomEvent("scope-state-change"));
    }
  }

  function option(label, value = "", disabled = false) {
    const node = document.createElement("option");
    node.textContent = label;
    node.value = value;
    node.disabled = disabled;
    return node;
  }
  function clearBinding(message) {
    for (const key of bindingKeys) delete select.dataset[key];
    select.setCustomValidity(message);
    notifySelectionChanged();
  }
  function begin(message) {
    const request = ++generation;
    if (controller) controller.abort();
    controller = new AbortController();
    clearBinding(message);
    select.setAttribute("aria-busy", "true");
    retry.hidden = true;
    return {request, active: controller};
  }
  async function fetchValue(path, active) {
    const timeout = window.setTimeout(() => active.abort(), 90000);
    try {
      const response = await fetch(path, {method: "GET", mode: "same-origin", credentials: "same-origin",
        cache: "no-store", signal: active.signal});
      if (!response.ok) throw new Error("Unavailable");
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }
  function validEntry(item) {
    return item && text(item.id) && text(item.version) && ["instrument", "universe"].includes(item.kind) &&
      text(item.display_name) && reference(item.reference) && item.reference.id === item.id &&
      item.reference.version === item.version && reference(item.membership_snapshot) &&
      count(item.member_count) && item.member_count > 0 && Array.isArray(item.members) &&
      item.member_count === item.members.length && item.members.every(text) &&
      new Set(item.members).size === item.member_count && (item.kind !== "instrument" || item.member_count === 1) &&
      item.readiness && item.readiness.registered_member_count === item.member_count &&
      readinessCounts.every(key => count(item.readiness[key]) && item.readiness[key] <= item.member_count);
  }
  function readCatalog(value) {
    if (!value || value.schema_version !== "1.0.0" || !Array.isArray(value.scopes) ||
        value.scope_count !== value.scopes.length || !Array.isArray(value.issues) ||
        !value.scopes.every(validEntry) || new Set(value.scopes.map(choice)).size !== value.scope_count) {
      throw new Error("Invalid scope catalog");
    }
    return value;
  }
  function readResolution(value, item) {
    if (!validEntry(value) || value.id !== item.id || value.version !== item.version || value.kind !== item.kind ||
        !sameReference(value.reference, item.reference) || !sameReference(value.definition_binding, item.reference) ||
        !sameReference(value.membership_snapshot, item.membership_snapshot) ||
        value.member_count !== item.member_count || !value.members.every(id => item.members.includes(id)) ||
        !value.experiment_scope || value.experiment_scope.id !== item.id || value.experiment_scope.version !== item.version ||
        !value.dependency || value.dependency.requirement !== "required" || !Array.isArray(value.dependency.bindings) ||
        !value.dependency.bindings.every(binding => text(binding.role) && reference(binding.artifact)) ||
        new Set(value.dependency.bindings.map(binding => binding.role)).size !== value.dependency.bindings.length) {
      throw new Error("Invalid scope resolution");
    }
    const membership = value.dependency.bindings.filter(binding => binding.role === "membership");
    if (membership.length !== 1 || !sameReference(membership[0].artifact, value.membership_snapshot)) {
      throw new Error("Unpinned scope membership");
    }
    return value;
  }
  function readinessNote(item) {
    // Counts and decisions are supplied by the registry API, never inferred
    // from group membership or used to remove members from the selection.
    const ready = item.readiness;
    const coverage = `${ready.stored_price_member_count} of ${item.member_count} members have stored prices. ` +
      `Provisional retrospective research: ${ready.retrospective_ready_member_count}/${item.member_count} · ` +
      `Historical replay: ${ready.historical_replay_ready_member_count}/${item.member_count} · ` +
      `Live: ${ready.live_ready_member_count}/${item.member_count}.`;
    return coverage + (item.kind === "universe" ? " Fixed research group; broker eligibility is unverified." : "");
  }
  function populate(previous) {
    const placeholder = option(entries.length ? "Select a scope" : "No registered scopes", "", true);
    placeholder.selected = true;
    select.replaceChildren(placeholder);
    select.value = "";
    for (const [kind, label] of [["instrument", "Instruments"], ["universe", "Universes"]]) {
      const items = entries.filter(item => item.kind === kind);
      if (!items.length) continue;
      const group = document.createElement("optgroup");
      group.label = label;
      for (const item of items) {
        const label = item.reference_currency ? `${item.display_name} · ${item.member_count} currencies vs ${item.reference_currency}` : item.kind === "universe" ? `${item.display_name} · ${item.member_count} pairs` : item.display_name;
        group.append(option(label, choice(item)));
      }
      select.append(group);
    }
    select.disabled = entries.length === 0;
    select.dataset.catalogCount = String(entries.length);
    select.dataset.universeCount = String(entries.filter(item => item.kind === "universe").length);
    select.dataset.instrumentCount = String(entries.filter(item => item.kind === "instrument").length);
    // Reuse a choice only when both immutable definition and frozen membership
    // remain exact. Current labels or a reused id/version alone are insufficient.
    const retained = previous && entries.find(item => sameReference(item.reference, previous.reference) &&
      sameReference(item.membership_snapshot, previous.membership_snapshot));
    if (retained) select.value = choice(retained);
    status.textContent = catalogNote();
    notifySelectionChanged();
  }
  async function resolveSelection() {
    const item = selected();
    const {request, active} = begin(item ? "Resolving selected scope…" : "Choose a registered scope.");
    retrySelection = Boolean(item);
    if (!item) {
      status.textContent = catalogNote();
      select.setAttribute("aria-busy", "false");
      return;
    }
    status.textContent = `Resolving ${item.display_name}…`;
    try {
      const path = `/api/scope-library/${encodeURIComponent(item.id)}?version=${encodeURIComponent(item.version)}`;
      const value = readResolution(await fetchValue(path, active), item);
      if (request !== generation || selected() !== item) return;
      select.dataset.scopeReference = JSON.stringify(value.definition_binding);
      select.dataset.membershipSnapshot = JSON.stringify(value.membership_snapshot);
      select.dataset.resolvedMembers = JSON.stringify(value.members);
      select.dataset.experimentScope = JSON.stringify(value.experiment_scope);
      select.dataset.scopeDependency = JSON.stringify(value.dependency);
      select.dataset.scopeResolution = JSON.stringify(value);
      select.setCustomValidity("");
      status.textContent = readinessNote(value);
    } catch (error) {
      if (request !== generation) return;
      clearBinding("The selected scope could not be resolved. Retry or choose another scope.");
      status.textContent = "Could not resolve the stored scope membership. Retry or choose another scope.";
      retry.textContent = "Retry selected scope";
      retry.hidden = false;
    } finally {
      if (request === generation) { select.setAttribute("aria-busy", "false"); notifySelectionChanged(); }
    }
  }
  async function load() {
    const previous = selected() || refreshSelection;
    refreshSelection = previous;
    const {request, active} = begin("Loading registered scopes…");
    for (const key of catalogKeys) delete select.dataset[key];
    entries = [];
    retrySelection = false;
    select.disabled = true;
    select.replaceChildren(option("Loading scopes…", "", true));
    select.value = "";
    notifySelectionChanged();
    status.textContent = "Loading registered scopes…";
    try {
      const value = readCatalog(await fetchValue("/api/scope-library", active));
      if (request !== generation) return;
      entries = value.scopes;
      refreshSelection = null;
      populate(previous);
      clearBinding("Choose a registered scope.");
      if (selected()) {
        const resolving = resolveSelection(), resolutionRequest = generation;
        await resolving;
        if (resolutionRequest !== generation) return;
      }
      if (value.issues.length) {
        status.textContent += " Some registry records are unavailable.";
        retry.textContent = "Retry loading scopes";
        retry.hidden = false;
        retrySelection = false;
      }
    } catch (error) {
      if (request !== generation) return;
      entries = [];
      refreshSelection = null;
      select.replaceChildren(option("Scopes unavailable", "", true));
      select.disabled = true;
      clearBinding("Registered scopes are unavailable.");
      status.textContent = "Could not load registered scopes. Retry to load the library.";
      retry.textContent = "Retry loading scopes";
      retry.hidden = false;
    } finally {
      if (request === generation) { select.setAttribute("aria-busy", "false"); notifySelectionChanged(); }
    }
  }
  select.addEventListener("change", resolveSelection);
  retry.addEventListener("click", () => retrySelection && selected() ? resolveSelection() : load());
  window.addEventListener("experiment-catalog-refresh", event => {
    if (typeof event?.detail?.enqueue === "function") event.detail.enqueue("scope", load);
    else load();
  });
  // The contract coordinator starts this read only when its page is visible.
})();
