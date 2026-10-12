"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const tableContainer = $("signal-table-container");
  const catalogStatus = $("signal-library-status");
  const detailBody = $("signal-detail-body");
  const detailStatus = $("signal-detail-status");
  const detailTitle = $("signal-detail-title");
  const detailPanel = $("signal-detail"), detailHome = $("signal-detail-home");
  const filters = Object.fromEntries(["search", "provider", "state", "from", "to"].map(key => [key, $(`signal-${key}`)]));
  const signalPattern = /^SIGNAL_[0-9a-f]{64}$/;
  const featurePattern = /^FEATURE_[0-9a-f]{64}$/;
  const recipePattern = /^FEATURE_RECIPE_[0-9a-f]{64}$/;
  const materializationPattern = /^MATERIALIZATION_[0-9a-f]{64}$/;
  const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 8 });
  const month = new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
  const day = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  let signals = [];
  let entries = [];
  let selectedEntryId = null;
  let selectedDetail = null;
  let selectedId = null;
  let selectedMaterialization = null;
  let catalogRequest = 0;
  let catalogLoading = null;
  let detailRequest = 0;
  let detailController = null;
  let researchRefreshRunning = false;
  let researchRefreshPending = false;
  const researchRefreshSignatures = new Map();

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  const text = value => typeof value === "string" && value.trim().length > 0;
  const count = value => Number.isSafeInteger(value) && value >= 0;
  const providerName = value => value === "FRED_ALFRED" ? "FRED / ALFRED" : value;
  const formatNumber = value => value === null || value === undefined ? "—" : number.format(Number(value));
  function formatDate(value, formatter = day) {
    if (!value) return "—";
    const date = new Date(value.length === 10 ? `${value}T00:00:00Z` : value);
    return Number.isFinite(date.getTime()) ? formatter.format(date) : value;
  }
  const range = (a, b, formatter = day) => `${formatDate(a, formatter)} – ${formatDate(b, formatter)}`;
  function parameterText(parameters) {
    return parameters.map(p => `${p.name}=${p.value.value}`).join(", ");
  }
  function operatorText(signal) {
    return signal.transformations.map(t => t.parameters.length ? `${t.label} (${parameterText(t.parameters)})` : t.label).join(" → ");
  }
  function validSummary(item) {
    return item && signalPattern.test(item.signal_id) && text(item.name) &&
      item.feature && featurePattern.test(item.feature.id) && item.source &&
      [item.source.name, item.source.series_id, item.source.provider, item.unit].every(text) &&
      count(item.row_count) && count(item.materialization_count) && item.materialization_count > 0 &&
      materializationPattern.test(item.default_materialization_id) && item.coverage &&
      item.status_counts && ["valid", "missing", "invalid"].every(k => count(item.status_counts[k])) &&
      item.materialization_state === "materialized" && text(item.scientific_state) &&
      Array.isArray(item.transformations) && item.transformations.length > 0 &&
      item.transformations.every(t => text(t.label) && t.operator && text(t.operator.id) &&
        Array.isArray(t.parameters) && t.parameters.every(p => text(p.name) && p.value && p.value.value !== undefined));
  }
  const reference = value => value && text(value.id) && text(value.version) && /^[0-9a-f]{64}$/.test(value.content_sha256);
  const researchLabel = value => value.charAt(0).toUpperCase() + value.slice(1).replaceAll("_", " ");
  function validStructuredResults(item) {
    if (item.results === undefined) return true; // Historical reference-only projections.
    const date = value => text(value) && /^\d{4}-\d{2}-\d{2}$/.test(value);
    return Array.isArray(item.results) && item.scope && text(item.scope.id) && ["TS", "CS"].includes(item.mode) &&
      [1, 7, 21, 63, 252].includes(item.horizon) && item.target_family === "price_return" &&
      ["POSITIVE", "NEGATIVE"].includes(item.expected_direction) && text(item.p1_status) && text(item.p2_status) &&
      item.results.every(result => result && ["P1", "P2"].includes(result.stage) && result.period &&
        date(result.period.start_inclusive) && date(result.period.end_exclusive) &&
        result.period.start_inclusive < result.period.end_exclusive && reference(result.authority) &&
        reference(result.research_spec) && result.metrics && typeof result.metrics === "object" && !Array.isArray(result.metrics) &&
        result.sample && typeof result.sample === "object" && !Array.isArray(result.sample));
  }
  function validResearch(value) {
    return value && ["untested", "results_linked", "unverified"].includes(value.state) && text(value.label) && text(value.description) &&
      count(value.relationship_count) && Array.isArray(value.relationships) &&
      value.relationship_count === new Set(value.relationships.map(item => item && item.relationship &&
        JSON.stringify([item.signal_id, item.relationship.id, item.relationship.version, item.relationship.content_sha256]))).size &&
      (value.state === "results_linked" ? value.relationship_count > 0 : value.relationship_count === 0) &&
      value.relationships.every(item => item && signalPattern.test(item.signal_id) && reference(item.projection) &&
        reference(item.relationship) && ["trial_results", "admission_results", "validation_results"].every(key =>
          Array.isArray(item[key]) && item[key].every(reference)) && Array.isArray(item.attempt_ids) &&
        item.attempt_ids.every(id => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) && validStructuredResults(item));
  }
  function validOutput(item) {
    return validSummary(item) && item.detail_href === `/api/signal-library-outputs/${item.signal_id}` && Array.isArray(item.materializations) &&
      item.materializations.length === item.materialization_count &&
      new Set(item.materializations.map(m => m.id)).size === item.materializations.length &&
      item.materializations.every(m => m && materializationPattern.test(m.id) && reference(m.reference) &&
        m.reference.id === m.id && m.href === `${item.detail_href}?materialization_id=${m.id}` && count(m.row_count) && m.status_counts &&
        ["valid", "missing", "invalid"].every(key => count(m.status_counts[key])) &&
        m.status_counts.valid + m.status_counts.missing + m.status_counts.invalid === m.row_count &&
        m.coverage && m.readiness_capabilities);
  }
  function validEntry(item) {
    if (!item) return false;
    if (item.kind === "stored_signal") return validSummary(item.signal) && item.id === item.signal.signal_id;
    return ["reusable_fx_recipe", "registered_feature"].includes(item.kind) && (recipePattern.test(item.id) || featurePattern.test(item.id)) && reference(item.recipe) &&
      item.recipe.id === item.id && text(item.name) && item.source && text(item.source.label) &&
      item.source.input_contract && item.observation_count === null && validResearch(item.research) &&
      Array.isArray(item.transformations) && item.transformations.length > 0 &&
      item.transformations.every(step => text(step.node) && reference(step.operator) && text(step.label) &&
        Array.isArray(step.parameters) && step.parameters.every(p => text(p.name) && p.value && p.value.value !== undefined)) &&
      Array.isArray(item.outputs) && item.outputs.every(validOutput);
  }
  function readCatalog(data) {
    if (!data || data.schema_version !== "1.0.0" || !Array.isArray(data.entries) ||
        !Array.isArray(data.issues) || data.entry_count !== data.entries.length ||
        !data.entries.every(validEntry) || new Set(data.entries.map(item => item.id)).size !== data.entry_count) {
      throw new Error("Invalid catalog");
    }
    const outputs = data.entries.flatMap(item => item.kind === "stored_signal" ? [item.signal] : item.outputs);
    if (new Set(outputs.map(item => item.signal_id)).size !== outputs.length) throw new Error("Duplicate stored output");
    return data;
  }
  const groupForSignal = id => entries.find(entry => entry.kind !== "stored_signal" &&
    entry.outputs.some(output => output.signal_id === id));
  function readDetail(data, id, mid) {
    if (!data || data.schema_version !== "1.0.0" || !validSummary(data.signal) || data.signal.signal_id !== id ||
        !materializationPattern.test(data.selected_materialization_id) || (mid && data.selected_materialization_id !== mid) ||
        !Array.isArray(data.materializations) || !data.materializations.some(m => m.id === data.selected_materialization_id) ||
        !data.statistics || data.statistics.kind !== "descriptive_observation_statistics" ||
        !["row_count", "valid_count", "missing_count", "invalid_count", "null_count"].every(k => count(data.statistics[k])) ||
        !["min", "max", "mean", "median", "sample_standard_deviation"].every(k => data.statistics[k] === null || Number.isFinite(data.statistics[k])) ||
        !Array.isArray(data.observations) || data.observations.length !== data.statistics.row_count ||
        !data.provenance || !data.timing || !data.source_metadata || !data.recipe || !data.research ||
        !text(data.research.state) || !count(data.research.relationship_count) || !Array.isArray(data.research.metrics)) {
      throw new Error("Invalid detail");
    }
    if (data.research.relationships !== undefined && !validResearch(data.research)) throw new Error("Invalid research links");
    return data;
  }
  async function request(url, controller) {
    // The full catalog can take longer on a cold cloud store. Registered cards
    // are already displayed while coverage and research evidence are loading.
    const deadline = url === "/api/signal-library-summaries" ? 60000 : 20000;
    const timeout = window.setTimeout(() => controller.abort(), deadline);
    try {
      const response = await fetch(url, { method: "GET", mode: "same-origin", credentials: "same-origin", cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Unavailable");
      return await response.json();
    } finally { window.clearTimeout(timeout); }
  }

  function showPage() {
    const hash = window.location.hash;
    const page = ["#ledger", "#ledger-page"].includes(hash) ? "ledger" : ["#signals", "#signal-page"].includes(hash) ? "signals" : ["#pit", "#pit-page"].includes(hash) ? "pit" : "experiment";
    $("experiment-inputs").hidden = page !== "experiment";
    $("signal-page").hidden = page !== "signals";
    $("pit-page").hidden = page !== "pit";
    if ($("ledger-page")) $("ledger-page").hidden = page !== "ledger";
    const target = page === "ledger" ? "ledger-page" : page === "experiment" ? "experiment-inputs" : page === "signals" ? "signal-page" : "pit-page";
    const skip = document.querySelector(".skip-link");
    skip.href = `#${target}`;
    skip.textContent = page === "ledger" ? "Skip to Trial Ledger" : page === "experiment" ? "Skip to experiment inputs" : `Skip to ${page === "signals" ? "Signal" : "PIT Data"} Library`;
    for (const link of document.querySelectorAll("[data-page]")) {
      if (link.dataset.page === page) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    if (page === "signals") {
      if (!catalogLoading) {
        researchRefreshPending = false;
        catalogLoading = loadCatalog();
      } else if (researchRefreshPending) refreshResearchCatalog();
    }
  }
  function openLibrary() {
    if (window.location.hash !== "#signals") window.location.hash = "#signals";
    showPage();
  }
  function table(headers, className = "") {
    const wrap = el("div", undefined, "table-scroll");
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "region");
    const grid = el("table", undefined, `signal-table ${className}`);
    const head = el("thead");
    const row = el("tr");
    for (const label of headers) { const cell = el("th", label); cell.scope = "col"; row.append(cell); }
    head.append(row);
    const body = el("tbody");
    grid.append(head, body);
    wrap.append(grid);
    return { wrap, grid, body };
  }
  function outputList(entry) { return entry.kind === "stored_signal" ? [entry.signal] : entry.outputs; }
  function stateLabel(entry) { return entry.kind === "stored_signal" ? researchLabel(entry.signal.scientific_state) : entry.research.label; }
  function populateFilters() {
    const choices = {provider: entries.flatMap(entry => outputList(entry).map(output => output.source.provider)), state: entries.map(stateLabel)};
    for (const [key, values] of Object.entries(choices)) {
      const control = filters[key], previous = control.value;
      const all = el("option", key === "provider" ? "All providers" : "All statuses"); all.value = "";
      control.replaceChildren(all, ...[...new Set(values)].sort().map(value => {
        const option = el("option", key === "provider" ? providerName(value) : value); option.value = value; return option;
      }));
      control.value = values.includes(previous) ? previous : "";
    }
  }
  function matches(entry) {
    const query = filters.search.value.trim().toLowerCase(), from = filters.from.value, to = filters.to.value;
    if (from && to && from > to) return false;
    if (filters.state.value && filters.state.value !== stateLabel(entry)) return false;
    const grouped = entry.kind !== "stored_signal", item = grouped ? entry : entry.signal;
    const words = [item.name, entry.id, operatorText(item), grouped ? entry.source.label : entry.signal.source.series_id,
      ...outputList(entry).flatMap(output => [output.signal_id, output.source.series_id, providerName(output.source.provider)])].join(" ").toLowerCase();
    if (query && !words.includes(query)) return false;
    if (!filters.provider.value && !from && !to) return true;
    // Provider and coverage must belong to the same actual materialization.
    return outputList(entry).some(output => (!filters.provider.value || output.source.provider === filters.provider.value) &&
      (output.materializations || [{coverage:output.coverage}]).some(({coverage}) =>
        (!from || coverage.reference_end && coverage.reference_end >= from) && (!to || coverage.reference_start && coverage.reference_start <= to)));
  }
  function clearSelection() {
    window.SignalResearch?.cancel();
    ++detailRequest; if (detailController) detailController.abort();
    selectedEntryId = null; selectedId = null; selectedMaterialization = null; selectedDetail = null;
    detailBody.replaceChildren(); detailPanel.hidden = true; detailPanel.setAttribute("aria-busy", "false");
    $("signal-detail-retry").hidden = true;
  }
  function revealSelection() {
    const entry = entries.find(item => item.id === selectedEntryId);
    if (entry && !matches(entry)) for (const control of Object.values(filters)) control.value = "";
  }
  function applyFilters() {
    if (selectedEntryId && !entries.some(entry => entry.id === selectedEntryId && matches(entry))) clearSelection();
    renderTable();
  }
  function renderTable() {
    detailHome.append(detailPanel); detailPanel.hidden = true;
    const visible = entries.filter(matches), buttons = new Map();
    const invalidRange = filters.from.value && filters.to.value && filters.from.value > filters.to.value;
    catalogStatus.textContent = invalidRange ? "Coverage from must be on or before Coverage to." :
      `${visible.length} of ${entries.length} ${entries.length === 1 ? "library entry" : "library entries"}`;
    const list = el("ul", undefined, "card-list");
    let selectedCard = null;
    for (const entry of visible) {
      const grouped = entry.kind !== "stored_signal", signal = entry.signal;
      const card = el("li", undefined, "library-card"); card.dataset.entryId = entry.id;
      card.dataset.expanded = String(entry.id === selectedEntryId);
      const button = el("button", undefined, "card-toggle"); button.type = "button";
      button.setAttribute("aria-controls", "signal-detail"); button.setAttribute("aria-expanded", String(entry.id === selectedEntryId));
      const values = [grouped ? entry.name : signal.name, grouped ? entry.source.label : `${signal.source.series_id} · ${providerName(signal.source.provider)}`,
        operatorText(grouped ? entry : signal), grouped ? "N/A" : `${formatNumber(signal.row_count)} observations`, stateLabel(entry)];
      const summary = el("span", undefined, "card-summary");
      for (const [index, label] of ["Signal", "Source", "Transformation", "Observations", "Research status"].entries()) {
        const field = el("span", undefined, index === 0 ? "card-identity" : "card-field");
        field.append(el("span", label, "card-field-label"), el("span", values[index], index === 0 ? "dataset-name" : "card-value"));
        if (index === 0 && (!grouped || entry.signal_id)) field.append(el("span", grouped ? entry.signal_id : signal.signal_id, "signal-id"));
        summary.append(field);
      }
      button.append(summary, el("span", entry.id === selectedEntryId ? "Close Feature" : "Explore Feature →", "card-action"));
      button.addEventListener("click", () => {
        if (entry.id === selectedEntryId) { clearSelection(); renderTable().get(entry.id)?.focus(); }
        else selectEntry(entry.id);
      });
      card.append(button); list.append(card); buttons.set(entry.id, button);
      if (entry.id === selectedEntryId) selectedCard = card;
    }
    tableContainer.replaceChildren(list);
    if (!visible.length) tableContainer.append(el("p", entries.length ? "No Signals match these filters. Try a different search or clear the filters." : "No registered Signals are available yet.", "empty-table"));
    if (selectedCard) {
      if ($("signal-catalog-view")) { detailHome.append(detailPanel); detailHome.hidden = false; }
      else selectedCard.append(detailPanel);
      detailPanel.hidden = false;
    }
    if ($("signal-catalog-view")) {
      $("signal-catalog-view").hidden = Boolean(selectedCard);
      detailHome.hidden = !selectedCard;
    }
    return buttons;
  }
  function facts(fields) {
    const list = el("dl", undefined, "detail-grid signal-facts");
    for (const [label, value] of fields) {
      const group = el("div");
      group.append(el("dt", label), el("dd", value));
      list.append(group);
    }
    return list;
  }
  function appendJson(parent, label, value) {
    parent.append(el("h3", label), el("pre", JSON.stringify(value, null, 2)));
  }
  function groupContent(entry) {
    const fragment = document.createDocumentFragment();
    if (window.SignalResearch) {
      fragment.append(el("p", operatorText(entry), "recipe-chain"), el("p", `${entry.source.label} · Observations: N/A · Coverage belongs to each stored output`, "field-note"));
      const dashboard = el("div"); fragment.append(dashboard); window.SignalResearch.mount(dashboard, entry);
    } else {
    fragment.append(facts([["Source", entry.source.label], ["Transformation", operatorText(entry)],
      ["Research status", entry.research.label]]));
    const research = el("p", undefined, "research-note");
    research.append(el("strong", entry.research.label), document.createTextNode(entry.research.description));
    fragment.append(research);
    if (entry.research.relationships.length) {
      for (const relationship of entry.research.relationships.filter(r => Array.isArray(r.results))) {
        const section = el('section', undefined, 'research-note');
        section.append(el('h3', `${relationship.mode} · ${relationship.horizon} scheduled weekdays`));
        section.append(facts([['Scope', relationship.scope.id], ['Target', 'Price Return'],
          ['Expected Direction', relationship.expected_direction], ['P1', relationship.p1_status], ['P2', relationship.p2_status]]));
        for (const result of relationship.results) {
          section.append(el('h4', `${result.stage} · ${result.period.start_inclusive} – ${result.period.end_exclusive} (exclusive)`));
          const metrics = Object.entries(result.metrics || {}).filter(([,value]) => value === null || ['string','number','boolean'].includes(typeof value));
          section.append(facts(metrics.map(([name,value]) => [name.replaceAll('_',' '),value === null ? 'Unavailable' : String(value)])));
          const detail = el('details'); detail.append(el('summary', 'Result source and evidence'));
          appendJson(detail, 'Authoritative trial and Research Spec', {trial:result.authority,research_spec:result.research_spec,sample:result.sample});
          section.append(detail);
        }
        fragment.append(section);
      }
      const relationships = el("details", undefined, "definition-panel");
      relationships.append(el("summary", "Tested relationships and authoritative records"), el("p",
        "Scope, Target and horizon belong to each authoritative relationship below. Linked results do not establish a shared validation status.", "field-note"));
      appendJson(relationships, "Research records", entry.research.relationships); fragment.append(relationships);
    }
    }
    const outputDetails = el("details", undefined, "research-output-details");
    outputDetails.append(el("summary", `Stored outputs & recipe · ${entry.outputs.length} instrument${entry.outputs.length === 1 ? "" : "s"}`));
    const outputContent = window.SignalResearch ? outputDetails : fragment;
    if (window.SignalResearch) fragment.append(outputDetails);
    outputContent.append(el("h3", "Stored instrument outputs"), el("p",
      "Observations, coverage and readiness belong to each stored output below. A stored sample does not establish coverage for another instrument or the full history.", "field-note"));
    const outputs = table(["Instrument / provider", "Stored period", "Observations", "Readiness", "Details"], "recipe-outputs-table");
    outputs.wrap.setAttribute("aria-label", "Stored outputs for this recipe");
    for (const output of entry.outputs) {
      for (const materialization of output.materializations) {
        const row = el("tr"), instrument = el("td", output.source.series_id);
        instrument.append(el("span", providerName(output.source.provider), "cell-secondary"));
        const coverage = el("td", range(materialization.coverage.reference_start, materialization.coverage.reference_end));
        coverage.append(el("span", `Snapshot cutoff: ${range(materialization.coverage.cutoff_start, materialization.coverage.cutoff_end)}`, "cell-secondary"));
        const observations = el("td", formatNumber(materialization.row_count));
        observations.append(el("span", `${materialization.status_counts.valid} valid · ${materialization.status_counts.missing} missing · ${materialization.status_counts.invalid} invalid`, "cell-secondary"));
        const readiness = el("td");
        for (const [key, label] of [["retrospective_research", "Retrospective"], ["historical_replay", "Historical replay"], ["live_use", "Live use"]]) {
          const capability = materialization.readiness_capabilities[key];
          const value = typeof capability === "string" ? capability : capability && capability.decision;
          const note = el("span", `${label}: ${value || "Not recorded"}`, "cell-secondary");
          if (capability && text(capability.reason)) note.title = capability.reason;
          readiness.append(note);
        }
        const details = el("td"), button = el("button", "View observations and lineage", "text-button"); button.type = "button";
        button.dataset.signalId = output.signal_id; button.dataset.materializationId = materialization.id;
        button.setAttribute("aria-pressed", String(selectedId === output.signal_id && selectedMaterialization === materialization.id));
        button.addEventListener("click", () => selectSignal(output.signal_id, materialization.id)); details.append(button);
        row.append(instrument, coverage, observations, readiness, details); outputs.body.append(row);
      }
    }
    if (!entry.outputs.length) outputContent.append(el("p", entry.catalog_pending ? "Stored output coverage is still loading. Registration does not imply prepared observations." : "No stored outputs are catalogued for this Signal. The definition remains available for preparation.", "field-note"));
    outputContent.append(outputs.wrap);
    const definition = el("details", undefined, "definition-panel");
    definition.append(el("summary", "Recipe definition"));
    appendJson(definition, "Reusable recipe", entry.recipe);
    appendJson(definition, "Input contract", entry.source.input_contract);
    appendJson(definition, "Ordered transformations", entry.transformations); outputContent.append(definition);
    return fragment;
  }
  async function selectEntry(id) {
    const entry = entries.find(item => item.id === id);
    if (!entry) return;
    if (entry.kind === "stored_signal") {
      if (!window.SignalResearch) { selectSignal(entry.signal.signal_id); return; }
      ++detailRequest; if (detailController) detailController.abort();
      selectedEntryId=entry.id; selectedId=null; selectedMaterialization=null; selectedDetail=null;
      openLibrary(); revealSelection(); renderTable();
      detailTitle.textContent=entry.signal.name;
      detailStatus.textContent=`${entry.signal.source.series_id} · ${providerName(entry.signal.source.provider)}`;
      detailPanel.setAttribute("aria-busy","false"); $("signal-detail-retry").hidden=true;
      const host=el("div"), outputs=el("details",undefined,"research-output-details");
      outputs.append(el("summary","Stored observations & lineage"),el("p",`${formatNumber(entry.signal.row_count)} observations in the default stored version.`,"field-note"));
      const open=el("button","View observations and lineage","research-button");open.type="button";open.addEventListener("click",()=>selectSignal(entry.signal.signal_id));outputs.append(open);
      detailBody.replaceChildren(el("p",operatorText(entry.signal),"recipe-chain"),host,outputs);window.SignalResearch.mount(host,entry);detailTitle.focus({preventScroll:true});return;
    }
    ++detailRequest; if (detailController) detailController.abort();
    selectedEntryId = entry.id; selectedId = null; selectedMaterialization = null; selectedDetail = null;
    openLibrary(); revealSelection(); renderTable();
    $("signal-detail").setAttribute("aria-busy", "false"); $("signal-detail-retry").hidden = true;
    detailTitle.textContent = entry.name;
    detailStatus.textContent = window.SignalResearch ? "One recipe. Separate evidence for every tested relationship." : entry.outputs.length ? `${entry.research.label} · Select a stored output to view its observations and lineage.` : `${entry.research.label} · Registered definition; ${entry.catalog_pending ? "stored coverage is loading" : "no stored outputs are catalogued"}.`;
    detailBody.replaceChildren(groupContent(entry)); detailTitle.focus({preventScroll: true});
    if (!window.SignalResearch && entry.details_deferred && entry.research.state === "results_linked") {
      const generation = detailRequest, controller = new AbortController(); detailController = controller;
      detailStatus.textContent = "Verifying research results for this Signal…";
      try {
        const response = await request(`/api/research-results/${entry.recipe.id}`, controller);
        if (generation !== detailRequest || selectedEntryId !== entry.id) return;
        const research = {...entry.research, relationships: response.relationships,
          relationship_count: new Set(response.relationships.map(r => r.relationship.id)).size};
        if (response.recipe_id !== entry.recipe.id || !validResearch(research)) throw new Error("Invalid research records");
        entry.research = research; detailBody.replaceChildren(groupContent(entry));
        detailStatus.textContent = "Authoritative research results verified. Output observations are verified when opened.";
      } catch (_error) {
        if (generation === detailRequest) detailStatus.textContent = "Research details could not be verified. Collapse and reopen to retry; the registered Signal remains available.";
      }
    }
  }
  function renderDetail(data) {
    const signal = data.signal;
    const current = data.materializations.find(m => m.id === data.selected_materialization_id);
    const stats = data.statistics;
    const rows = data.observations;
    const retrospective = data.timing.retrospective_snapshot === true;
    const valid = rows.filter(r => r.status === "valid");
    const latest = rows[rows.length - 1];
    const group = groupForSignal(signal.signal_id);
    detailTitle.textContent = group ? group.name : signal.name;
    detailStatus.textContent = `${signal.source.series_id} · ${providerName(signal.source.provider)} · Materialized · ${data.research.label || researchLabel(signal.scientific_state)}`;
    if (["unknown_historical_availability", "retrospective_snapshot_unknown"].includes(signal.availability_semantics)) {
      detailStatus.textContent += " · Historical availability unknown";
    }
    const fragment = document.createDocumentFragment();
    if (group) {
      fragment.append(groupContent(group), el("h3", `${signal.source.series_id} · Stored output details`));
    }
    fragment.append(el("p", signal.signal_id, "signal-id"));
    if (data.materializations.length > 1) {
      const group = el("div", undefined, "materialization-selector");
      const label = el("label", "Stored version"); label.htmlFor = "signal-materialization";
      const select = el("select"); select.id = "signal-materialization";
      data.materializations.forEach(m => {
        const option = el("option", `${range(m.coverage.cutoff_start, m.coverage.cutoff_end)} · ${m.row_count} observations · ${m.id.slice(-8)}`);
        option.value = m.id; option.selected = m.id === current.id; select.append(option);
      });
      select.addEventListener("change", () => selectSignal(signal.signal_id, select.value));
      group.append(label, select); fragment.append(group);
    }
    const cards = el("dl", undefined, "stat-grid");
    for (const [label, value, note] of [
      ["Observations", stats.row_count, `${stats.valid_count} valid · ${stats.null_count} null`],
      ["Latest value", latest ? latest.value : null, latest ? formatDate(retrospective ? latest.reference_time : latest.evaluation_cutoff) : ""],
      ["Mean", stats.mean, "Valid observations"],
      ["Minimum", stats.min, "Valid observations"],
      ["Maximum", stats.max, "Valid observations"],
      ["Median", stats.median, "Valid observations"]
    ]) {
      const card = el("div", undefined, "stat-card");
      const valueNode = el("dd", formatNumber(value));
      valueNode.append(el("span", note));
      card.append(el("dt", label), valueNode); cards.append(card);
    }
    fragment.append(cards);
    fragment.append(el("p", signal.value_semantics === "fractional_change"
      ? "Values are dimensionless fractions: 0.01 means 1%. Summary values are rounded for display; stored values appear below."
      : `Output unit: ${signal.unit}. Summary values are rounded for display; stored values appear below.`, "field-note"));
    const provider = data.source_metadata.provider.body;
    fragment.append(facts([
      [data.timing.coverage_label || "Archive coverage", range(current.coverage.cutoff_start, current.coverage.cutoff_end)],
      ["Reference coverage", range(current.coverage.reference_start, current.coverage.reference_end, retrospective ? day : month)],
      ["Transformation", operatorText(signal)],
      ["Source dataset", signal.source.name],
      ["Source frequency / units", `${signal.source.frequency} · ${signal.source.units}`],
      ["Seasonal adjustment", provider.seasonal_adjustment || "Not recorded"],
      ["Entity / measure", `${data.recipe.selection.entity_id} · ${data.recipe.selection.measure}`],
      ["Validity", `${stats.valid_count} valid · ${stats.missing_count} missing · ${stats.invalid_count} invalid`],
      ["Sample standard deviation", formatNumber(stats.sample_standard_deviation)],
      ["Distinct reference periods", String(new Set(rows.map(r => r.reference_time).filter(Boolean)).size)],
      ["First valid value", valid.length ? `${valid[0].value} (${formatDate(retrospective ? valid[0].reference_time : valid[0].evaluation_cutoff)})` : "No valid values"],
      ["Null reasons", Object.entries(stats.reason_counts).map(([reason, total]) => `${reason}: ${total}`).join(" · ") || "None"]
    ]));
    fragment.append(el("p", data.timing.description, "precision-note"));
    const research = el("p", undefined, "research-note");
    research.append(el("strong", data.research.state === "untested" ? "Research results: not tested" : data.research.label || researchLabel(data.research.state)),
      document.createTextNode(data.research.description));
    if (data.research.relationships && data.research.relationships.length) {
      const links = el("details", undefined, "definition-panel"); links.append(el("summary", "This output’s authoritative research records"));
      appendJson(links, "Relationship and result references", data.research.relationships); fragment.append(links);
    }
    fragment.append(research);
    fragment.append(el("h3", "Stored observations"));
    const observationHeaders = [data.timing.evaluation_label || "Archive date", "Reference period", "Stored value", "Validity"];
    if (retrospective) observationHeaders.push("Historical availability");
    observationHeaders.push("Lineage");
    const observations = table(observationHeaders, "observations-table");
    observations.wrap.setAttribute("aria-label", "Scrollable stored observations");
    observations.grid.setAttribute("aria-label", "Signal observations");
    for (const row of rows) {
      const tr = el("tr");
      tr.append(el("td", row.evaluation_cutoff), el("td", row.reference_time || "—"),
        el("td", row.value === null ? "—" : row.value), el("td", row.reason_code || row.status));
      if (retrospective) tr.append(el("td", row.available_at === null ? "Unknown" : row.available_at));
      const td = el("td", undefined, "lineage-cell");
      const details = el("details");
      details.append(el("summary", "View reference"), el("code", row.lineage.id, "signal-id"),
        el("span", `Version ${row.lineage.version}`, "cell-secondary"), el("code", row.lineage.content_sha256, "signal-id"));
      td.append(details); tr.append(td); observations.body.append(tr);
    }
    fragment.append(observations.wrap);
    const definition = el("details", undefined, "definition-panel");
    definition.append(el("summary", "Definition and provenance"));
    appendJson(definition, "Feature and materialization", data.provenance);
    appendJson(definition, "Exact recipe", data.recipe);
    appendJson(definition, "Source metadata", data.source_metadata);
    appendJson(definition, "Historical timing policy", data.timing);
    fragment.append(definition);
    detailBody.replaceChildren(fragment);
  }
  async function selectSignal(id, mid = null) {
    if (!signalPattern.test(id) || (mid && !materializationPattern.test(mid))) return;
    openLibrary();
    selectedId = id; selectedMaterialization = mid; selectedDetail = null;
    selectedEntryId = groupForSignal(id)?.id || id;
    openLibrary(); revealSelection(); renderTable();
    const generation = ++detailRequest;
    if (detailController) detailController.abort();
    detailController = new AbortController();
    $("signal-detail").setAttribute("aria-busy", "true");
    $("signal-detail-retry").hidden = true;
    detailTitle.textContent = groupForSignal(id)?.name || signals.find(s => s.signal_id === id)?.name || "Signal details";
    detailBody.replaceChildren();
    detailStatus.textContent = "Loading verified statistics and observations…";
    detailTitle.focus({ preventScroll: true });
    try {
      if (catalogLoading) await catalogLoading;
      if (generation !== detailRequest) return;
      selectedEntryId = groupForSignal(id)?.id || id;
      revealSelection(); renderTable();
      const output = signals.find(item => item.signal_id === id);
      const base = output && output.detail_href || `/api/signal-library/${encodeURIComponent(id)}`;
      const url = `${base}${mid ? `?materialization_id=${encodeURIComponent(mid)}` : ""}`;
      const data = readDetail(await request(url, detailController), id, mid);
      if (generation !== detailRequest) return;
      selectedMaterialization = data.selected_materialization_id; selectedDetail = data;
      renderDetail(data);
    } catch (_error) {
      if (generation !== detailRequest) return;
      detailStatus.textContent = "This Signal’s details could not be verified or loaded. Please try again.";
      $("signal-detail-retry").hidden = false;
    } finally {
      if (generation === detailRequest) $("signal-detail").setAttribute("aria-busy", "false");
    }
  }
  function registrationCatalog(data) {
    if (!data || !Array.isArray(data.features) || data.feature_count !== data.features.length) throw new Error("Invalid Feature registry");
    return data.features.map(item => {
      if (!reference(item.reference) || !["reusable_fx_recipe", "stored_feature"].includes(item.kind) || !Array.isArray(item.transformations) || !item.transformations.length) throw new Error("Invalid Feature definition");
      const steps = item.transformations.map((step, index) => ({...step, node: `step_${index}`,
        label: step.operator.id === "TR_BASE_momentum_skip_diff" ? "Skip Recent Difference" : step.label}));
      const logFirst = steps[0].operator.id === "TR_BASE_level_log", last = steps[steps.length - 1];
      const internalLog = last.parameters.some(p => p.name === "basis" && p.value.value === "log");
      const fx = item.kind === "reusable_fx_recipe";
      const name = !fx ? item.name : logFirst && last.operator.id === "TR_BASE_momentum_skip_diff" ? "Log Skip Recent Momentum" :
        (logFirst ? "Log " : internalLog ? "Log Return " : "") + last.label;
      return {kind: fx ? "reusable_fx_recipe" : "registered_feature", id: item.id, recipe: item.reference,
        signal_id: item.signal_id || item.id.replace("FEATURE_RECIPE_", "SIGNAL_"), name,
        source: {label: fx ? "Closing prices" : "Registered source series", input_contract: {}},
        transformations: steps, observation_count: null, outputs: [], catalog_pending: true,
        research: {state: "unverified", label: "Checking research status", relationship_count: 0, relationships: [], metrics: [],
          description: "Registered definition. Stored outputs and research status are checked separately."}};
    });
  }

  async function loadCatalog({preserveSelection = false} = {}) {
    const generation = ++catalogRequest;
    if (!preserveSelection) {
      ++detailRequest;
      if (detailController) detailController.abort();
      selectedId = null; selectedMaterialization = null; selectedEntryId = null; selectedDetail = null;
      entries = []; signals = [];
      detailTitle.textContent = "Select a Signal";
      detailStatus.textContent = "Choose a library entry to explore its recipe and stored outputs.";
      detailBody.replaceChildren();
      $("signal-detail-retry").hidden = true;
      $("signal-detail").setAttribute("aria-busy", "false");
      detailHome.append(detailPanel); detailPanel.hidden = true;
      tableContainer.replaceChildren();
      catalogStatus.textContent = "Loading Signal Library…";
    } else {
      catalogStatus.textContent = "Updating research results… Showing the last verified library while checks complete.";
    }
    tableContainer.setAttribute("aria-busy", "true");
    $("signal-library-issues").hidden = true;
    $("signal-library-retry").hidden = true;
    try {
      let registered = [];
      try {
        registered = registrationCatalog(await request("/api/feature-library", new AbortController()));
        if (generation !== catalogRequest) return;
        entries = registered.map(item => entries.find(old => old.id === item.id || old.kind === "stored_signal" && old.signal.feature.id === item.id) || item);
        populateFilters(); renderTable();
        catalogStatus.textContent += " · Loading stored coverage and research status…";
        tableContainer.setAttribute("aria-busy", "false");
      } catch (_error) { /* Older or temporarily unavailable registry: try the summary endpoint. */ }
      const data = readCatalog(await request("/api/signal-library-summaries", new AbortController()));
      if (generation !== catalogRequest) return;
      const represented = new Set(data.entries.map(item => item.kind === "stored_signal" ? item.signal.feature.id : item.id));
      entries = [...data.entries, ...registered.filter(item => !represented.has(item.id))];
      const storedSelection = entries.find(item => item.kind === "stored_signal" && item.signal.feature.id === selectedEntryId);
      if (storedSelection) selectedEntryId = storedSelection.id;
      populateFilters();
      signals = entries.flatMap(entry => entry.kind === "stored_signal" ? [entry.signal] : entry.outputs);
      if (preserveSelection && selectedEntryId && !entries.some(entry => entry.id === selectedEntryId)) {
        ++detailRequest; if (detailController) detailController.abort();
        selectedId = null; selectedMaterialization = null; selectedEntryId = null; selectedDetail = null;
        detailTitle.textContent = "Select a Signal";
        detailStatus.textContent = "The previous selection is not in the current verified library.";
        detailBody.replaceChildren();
      }
      if (selectedId) selectedEntryId = groupForSignal(selectedId)?.id || selectedId;
      renderTable();
      if (selectedDetail) renderDetail(selectedDetail);
      else if (selectedEntryId && !selectedId) {
        const chosen = entries.find(entry => entry.id === selectedEntryId);
        if (chosen?.kind === "stored_signal" && window.SignalResearch) await selectEntry(chosen.id);
        else if (chosen && chosen.kind !== "stored_signal") {
          detailTitle.textContent = chosen.name;
          detailStatus.textContent = window.SignalResearch ? "One recipe. Separate evidence for every tested relationship." : `${chosen.research.label} · Select a stored output to view its observations and lineage.`;
          detailBody.replaceChildren(groupContent(chosen));
        }
      }

      if (data.issues.length) {
        $("signal-library-issues").textContent = "Some library records could not be verified and are unavailable. Verified entries are shown.";
        $("signal-library-issues").hidden = false;
        $("signal-library-retry").hidden = false;
      }
    } catch (_error) {
      if (generation !== catalogRequest) return;
      if (!preserveSelection && !entries.length) { signals = []; entries = []; }
      catalogStatus.textContent = entries.length ? `${entries.length} registered Signals shown from the last verified library. Stored coverage and research status could not finish loading; retry to update them.` : preserveSelection
        ? "The latest research could not be loaded. Showing the last verified library; retry to update it."
        : "The Signal Library could not be loaded. Please try again.";
      $("signal-library-retry").hidden = false;
    } finally {
      if (generation === catalogRequest) {
        tableContainer.setAttribute("aria-busy", "false");
          }
    }
  }

  async function refreshResearchCatalog() {
    researchRefreshPending = true;
    if (researchRefreshRunning || $("signal-page").hidden) return;
    researchRefreshRunning = true;
    try {
      if (catalogLoading) await catalogLoading;
      while (researchRefreshPending && !$("signal-page").hidden) {
        researchRefreshPending = false;
        catalogLoading = loadCatalog({preserveSelection: true});
        await catalogLoading;
      }
    } finally { researchRefreshRunning = false; }
  }

  window.addEventListener("research-results-updated", event => {
    const update = event.detail;
    if (!update || !text(update.request_id) || !Array.isArray(update.results) ||
        !update.results.length || !update.results.every(reference)) return;
    const signature = JSON.stringify(update.results.map(value => [value.id, value.version, value.content_sha256])
      .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))));
    if (researchRefreshSignatures.get(update.request_id) === signature) return;
    researchRefreshSignatures.set(update.request_id, signature);
    refreshResearchCatalog();
  });

  // Keep exact historical output links while the library groups FX outputs by recipe.
  window.addEventListener("open-signal", event => {
    if (event.detail && signalPattern.test(event.detail.signal_id)) {
      selectSignal(event.detail.signal_id, event.detail.materialization_id || null);
    }
  });
  $("signal-library-retry").addEventListener("click", () => { catalogLoading = loadCatalog(); });
  $("signal-detail-retry").addEventListener("click", () => { if (selectedId) selectSignal(selectedId, selectedMaterialization); });
  $("signal-back")?.addEventListener("click", () => { clearSelection(); renderTable(); $("signal-search").focus({preventScroll:true}); });
  for (const control of Object.values(filters)) control.addEventListener("input", applyFilters);
  $("signal-clear").addEventListener("click", () => { for (const control of Object.values(filters)) control.value = ""; applyFilters(); });
  window.addEventListener("hashchange", showPage);
  showPage();
})();
