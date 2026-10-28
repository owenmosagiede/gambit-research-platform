(() => {
  "use strict";
  const select = document.getElementById("target");
  const status = document.getElementById("target-status");
  const retry = document.getElementById("target-retry");
  const targetPattern = /^TARGET_[0-9a-f]{64}$/;
  const materializationPattern = /^MATERIALIZATION_[0-9a-f]{64}$/;
  // UI categories map to existing registry return_basis values. A selection
  // includes the whole five-horizon family, never one instrument or horizon.
  const familyHorizons = [1, 7, 21, 63, 252];
  const returnCategories = [
    {value: "price", label: "Price Return"},
    {value: "total_return", label: "Total Return"},
    {value: "benchmark_excess", label: "Excess Return"},
  ];
  let requestGeneration = 0;
  let currentController = null;
  let refreshSelection = "";
  let entries = [];
  let instrumentEntries = [];
  let detailGeneration = 0;
  let detailController = null;
  const details = document.getElementById("target-details");
  const detailsLink = document.getElementById("target-details-link");

  function element(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = String(text);
    if (className) item.className = className;
    return item;
  }
  function readable(value) { return typeof value === "string" ? value.replaceAll("_", " ") : "Unspecified"; }
  function scheduledWeekdays(target) {
    const schedule = target.schedule;
    return target.horizon.unit === "scheduled_bars" && schedule &&
      schedule.calendar_id === "RESEARCH_WEEKDAYS" && schedule.calendar_version === "1.0.0" &&
      schedule.holiday_exclusions === false;
  }
  function horizonText(target) {
    const amount = target.horizon.amount;
    return `${amount} ${scheduledWeekdays(target) ? (amount === 1 ? "scheduled weekday" : "scheduled weekdays") : readable(target.horizon.unit)}`;
  }
  function coverage(value) { return value && value.start && value.end ? `${value.start} – ${value.end}` : "No verified coverage"; }
  function exactPolicy(value) {
    return value && typeof value.id === "string" && typeof value.version === "string" && /^[0-9a-f]{64}$/.test(value.content_sha256);
  }
  function retrospective(saved) {
    const capability = saved.readiness_capabilities && saved.readiness_capabilities.retrospective_research;
    return capability && capability.decision === "ready" && exactPolicy(capability.policy);
  }
  function readinessText(saved) {
    return saved.research_readiness === "historically_certified" ? "stored labels available" :
      retrospective(saved) ? "provisional retrospective research" : "not research ready";
  }
  function capabilityText(value, fallback = "unresolved") {
    if (!value) return readable(fallback);
    return `${readable(value.decision)}${value.reason ? ` · ${value.reason}` : ""}`;
  }
  function table(headers, rows) {
    const wrap = element("div", undefined, "table-scroll");
    wrap.tabIndex = 0;
    const item = element("table", undefined, "signal-table observations-table");
    const head = element("thead"), headRow = element("tr"), body = element("tbody");
    for (const label of headers) headRow.append(element("th", label));
    head.append(headRow);
    for (const values of rows) {
      const row = element("tr");
      for (const value of values) row.append(element("td", value == null ? "Unknown" : value));
      body.append(row);
    }
    item.append(head, body); wrap.append(item); return wrap;
  }
  function renderInstruments() {
    const panel = document.getElementById("target-instruments");
    if (!panel) return;
    panel.hidden = instrumentEntries.length === 0;
    const holder = document.getElementById("target-instrument-table");
    holder.replaceChildren();
    document.getElementById("target-instruments-heading").textContent = `${instrumentEntries.length} registered ${instrumentEntries.length === 1 ? "instrument" : "instruments"}`;
    if (!instrumentEntries.length) return;
    holder.append(table(["Instrument", "Construction", "PIT inputs", "Price coverage", "Stored prices", "Return Targets / stored labels", "Readiness / blockers"], instrumentEntries.map(item => {
      const caps = item.readiness_capabilities || {};
      const dependencies = (item.dependencies || []).map(value => typeof value === "string" ? value : value.id || value.instrument_id || "Referenced input").join(", ");
      const blockers = Array.isArray(item.blockers) ? item.blockers.map(value => readable(value).toLowerCase()).join("; ") : "";
      const referencedTargets = entries.filter(target => (item.target_ids || []).includes(target.target_id));
      const labelCount = referencedTargets.reduce((total, target) => {
        const stored = target.materializations.filter(saved => saved.state === "ready").sort((a,b) => a.id.localeCompare(b.id)).at(-1);
        return total + (stored ? stored.row_count || 0 : 0);
      },0);
      return [item.display_name || item.instrument_id,
        `${item.construction && item.construction.method === "usd_triangulation" ? "USD cross" : readable(item.construction && item.construction.method)}${dependencies ? ` · ${dependencies}` : ""}`,
        caps.pit_inputs && caps.pit_inputs.decision === "ready" ? "Stored snapshot" : capabilityText(caps.pit_inputs), coverage(item.price_coverage), item.price_row_count ?? 0, `${(item.target_ids || []).length} definitions / ${labelCount} labels across variants`,
        `Research: ${retrospective({readiness_capabilities:caps}) ? "provisional retrospective" : readable(caps.retrospective_research && caps.retrospective_research.decision)}. Historical PIT: ${readable(caps.historical_replay && caps.historical_replay.decision)}. Live: ${readable(caps.live_use && caps.live_use.decision)}.${blockers ? ` ${blockers}.` : ""}`];
    })));
  }


  function option(text, value = "", disabled = false) {
    const element = document.createElement("option");
    element.textContent = text;
    element.value = value;
    element.disabled = disabled;
    return element;
  }

  function catalog(value) {
    if (!value || value.schema_version !== "1.0.0" || !Array.isArray(value.targets) ||
        !Array.isArray(value.issues) || value.target_count !== value.targets.length) throw new Error("Invalid catalog");
    const ids = new Set();
    for (const target of value.targets) {
      if (!target || !targetPattern.test(target.target_id) || ids.has(target.target_id) ||
          typeof target.investment_series !== "string" || typeof target.return_basis !== "string" ||
          typeof target.representation !== "string" || !target.horizon ||
          !Number.isInteger(target.horizon.amount) || target.horizon.amount <= 0 ||
          typeof target.horizon.unit !== "string" || !Array.isArray(target.materializations)) throw new Error("Invalid Target");
      ids.add(target.target_id);
      const materializationIds = new Set();
      for (const saved of target.materializations) {
        if (!saved || !materializationPattern.test(saved.id) || materializationIds.has(saved.id) ||
            typeof saved.state !== "string" || typeof saved.research_readiness !== "string" ||
            !Number.isInteger(saved.valid_count) || saved.valid_count < 0) throw new Error("Invalid materialization");
        materializationIds.add(saved.id);
      }
    }
    if (value.instruments !== undefined) {
      if (!Array.isArray(value.instruments) || value.instrument_count !== value.instruments.length) throw new Error("Invalid instrument registry");
      const instrumentIds = new Set();
      for (const item of value.instruments) {
        if (!item || typeof item.instrument_id !== "string" || instrumentIds.has(item.instrument_id) ||
            !Array.isArray(item.target_ids) || !item.target_ids.every(id => targetPattern.test(id))) throw new Error("Invalid instrument");
        instrumentIds.add(item.instrument_id);
      }
    }
    return value;
  }

  function chosenMaterialization(target) {
    // Deterministic presentation preference only. Observation retrieval remains
    // explicitly pinned; this ID is never described as the latest outcome.
    return target.materializations.filter(saved => saved.state === "ready" &&
      (saved.research_readiness === "historically_certified" || retrospective(saved)) && saved.valid_count > 0)
      .sort((a, b) => a.id.localeCompare(b.id)).at(-1);
  }

  function clearBinding() {
    delete select.dataset.materializationId;
    delete select.dataset.returnBasis;
    delete select.dataset.horizons;
    delete select.dataset.horizonUnit;
    delete select.dataset.targetBindings;
  }

  function priceFamily() {
    const members = entries.filter(target => target.return_basis === "price" && target.comparison === "none" &&
      target.source_eligibility === "eligible" && target.definition_state === "valid" &&
      typeof target.definition_version === "string" && target.definition_version.length > 0 &&
      scheduledWeekdays(target) && familyHorizons.includes(target.horizon.amount))
      .map(target => ({target, saved: chosenMaterialization(target)})).filter(member => member.saved);
    // An incomplete set must not silently turn the category into a horizon choice.
    return familyHorizons.every(amount => members.some(({target}) => target.horizon.amount === amount)) ? members : [];
  }

  function notifyTargetState() {
    if (typeof window.dispatchEvent === "function" && typeof CustomEvent === "function") window.dispatchEvent(new CustomEvent("target-state-change"));
  }

  function renderCategories(available, prompt = "Select a target") {
    select.replaceChildren();
    clearBinding();
    if (detailsLink) detailsLink.hidden = true;
    select.append(option(prompt, "", true));
    for (const category of returnCategories) {
      // Total and Excess Return stay visible until their implementation and
      // populated observations are explicitly supported by this interface.
      select.append(option(category.label, category.value, category.value !== "price" || !available));
    }
    select.disabled = !available;
    select.value = "";
    notifyTargetState();
  }

  function updateNote() {
    clearBinding();
    // A category has no single Target detail record. Do not choose an arbitrary
    // instrument/horizon for the existing individual-record inspection link.
    if (detailsLink) detailsLink.hidden = true;
    if (details) {
      ++detailGeneration;
      if (detailController) detailController.abort();
      details.hidden = true;
    }
    const members = select.value === "price" && !select.disabled ? priceFamily() : [];
    if (!members.length) { select.value = ""; notifyTargetState(); return; }
    select.dataset.returnBasis = select.value;
    select.dataset.horizons = JSON.stringify(familyHorizons);
    select.dataset.horizonUnit = "scheduled_weekdays";
    select.dataset.targetBindings = JSON.stringify(members.map(({target, saved}) => ({
      target_id: target.target_id, definition_version: target.definition_version,
      materialization_id: saved.id, horizon: target.horizon,
    })));
    notifyTargetState();
    const provisional = members.some(({saved}) => saved.research_readiness !== "historically_certified");
    status.textContent = "Includes all five horizons: 1, 7, 21, 63 and 252 scheduled weekdays. " + (provisional ?
      "Provisional retrospective research; not certified historical replay. Historical timing and live use remain unverified." :
      "Stored labels available. Historical training must still check each label against its training cutoff.");
  }

  function populate(previous) {
    const available = priceFamily().length > 0;
    renderCategories(available);
    status.textContent = available ?
      "Select a return category. Includes all five horizons: 1, 7, 21, 63 and 252 scheduled weekdays." :
      "Price Return is not ready: verified stored observations are required for all five horizons (1, 7, 21, 63 and 252 scheduled weekdays).";
    if (available && previous === "price") { select.value = previous; updateNote(); }
  }

  async function load() {
    const previous = select.value || refreshSelection;
    refreshSelection = previous;
    const generation = ++requestGeneration;
    if (currentController) currentController.abort();
    currentController = new AbortController();
    const controller = currentController;
    const timeout = window.setTimeout(() => controller.abort(), 300000);
    entries = []; instrumentEntries = []; renderInstruments();
    renderCategories(false, "Loading targets…");
    status.textContent = "Verifying stored Targets… This can take longer while research is preparing data.";
    retry.hidden = true;
    if (detailsLink) detailsLink.hidden = true;
    if (details) {
      ++detailGeneration;
      if (detailController) detailController.abort();
      details.hidden = true;
      document.getElementById("target-details-body").replaceChildren();
    }
    try {
      const response = await fetch("/api/target-library", {method: "GET", cache: "no-store", signal: controller.signal});
      if (!response.ok) throw new Error("Target catalog unavailable");
      const value = catalog(await response.json());
      if (generation !== requestGeneration) return;
      entries = [...value.targets].sort((a, b) =>
        String(a.instrument_id || a.investment_series).localeCompare(String(b.instrument_id || b.investment_series)) ||
        a.horizon.unit.localeCompare(b.horizon.unit) || a.horizon.amount - b.horizon.amount ||
        a.representation.localeCompare(b.representation) || a.target_id.localeCompare(b.target_id));
      instrumentEntries = value.instruments || [];
      refreshSelection = "";
      renderInstruments(); populate(previous);
      if (value.issues.length) {
        status.textContent += " Some Target records could not be verified and are unavailable.";
        retry.hidden = false;
      }
    } catch (_error) {
      if (generation !== requestGeneration) return;
      entries = []; instrumentEntries = []; refreshSelection = ""; renderInstruments();
      renderCategories(false, "Targets unavailable");
      status.textContent = controller.signal.aborted
        ? "Target verification timed out. Stored data has not been changed. Retry when the server is less busy."
        : "Stored Targets could not be verified or loaded. Please retry.";
      retry.hidden = false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function loadDetail() {
    if (!details) return;
    const target = entries.find(entry => entry.target_id === select.value);
    const saved = target && chosenMaterialization(target);
    if (!saved) return;
    const generation = ++detailGeneration;
    if (detailController) detailController.abort();
    const controller = new AbortController(); detailController = controller;
    const timeout = window.setTimeout(() => controller.abort(), 60000);
    const title = document.getElementById("target-details-title");
    const note = document.getElementById("target-details-status");
    const body = document.getElementById("target-details-body");
    const again = document.getElementById("target-detail-retry");
    details.hidden = false; details.setAttribute("aria-busy", "true");
    title.textContent = `${target.instrument_id || target.investment_series} · ${horizonText(target)} · ${target.representation}`;
    note.textContent = "Loading the selected stored materialization…";
    body.replaceChildren(); again.hidden = true;
    try {
      const url = `/api/target-library/${encodeURIComponent(target.target_id)}?materialization_id=${encodeURIComponent(saved.id)}`;
      const response = await fetch(url, {method:"GET", cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error("Target unavailable");
      const data = await response.json();
      if (generation !== detailGeneration) return;
      if (!data || !data.definition || data.definition.id !== target.target_id || !data.manifest ||
          data.manifest.id !== saved.id || !Array.isArray(data.observations)) throw new Error("Unverified Target response");
      const caps = saved.readiness_capabilities || target.readiness_capabilities || {};
      note.textContent = `${readable(readinessText(saved))}. Economic coverage: ${readable(data.definition.body && data.definition.body.economic_coverage)}.${target.construction ? " FX spot returns exclude carry, financing, transaction costs, leverage, position sizing and account currency conversion." : ""}`;
      const facts = element("dl", undefined, "detail-grid");
      const construction = target.construction || {};
      const horizons = [...new Set(entries.filter(entry => (entry.instrument_id || entry.investment_series) === (target.instrument_id || target.investment_series))
        .map(entry => `${horizonText(entry)} / ${entry.representation}`))].join(", ");
      const values = [
        ["Target identity", target.target_id], ["Construction", readable(construction.method)],
        ["Price basis / alignment", `${readable(construction.price_basis)} / ${readable(construction.alignment)}`],
        ["Available Target variants", horizons], ["Valid anchor coverage", coverage(saved.coverage || target.coverage)],
        ["Stored labels", `${data.manifest.row_count} rows · ${JSON.stringify(data.manifest.status_counts || {})}`],
        ["Retrospective research", retrospective(saved) ? "Eligible for provisional retrospective research only" : capabilityText(caps.retrospective_research)],
        ["Historical PIT / timing", capabilityText(caps.historical_replay, saved.research_readiness === "historically_certified" ? "ready" : "unresolved")],
        ["Live use", capabilityText(caps.live_use)], ["Research policy", caps.retrospective_research && caps.retrospective_research.policy ? caps.retrospective_research.policy.id : "No retrospective authorization"],
      ];
      if (data.manifest.coverage) values.push(["Scheduled anchor coverage", coverage(data.manifest.coverage)]);
      if (scheduledWeekdays(target)) {
        values.push(["Schedule", "Monday–Friday, no holiday exclusions. Advance exactly the declared number of scheduled weekdays; do not count the anchor date."],
          ["Return anchoring", "Entry is the anchor date’s assigned close; zero delay does not certify an achievable trade at that close. Feature, label and training-cutoff checks remain separate."]);
      }
      values.push(["Return units", target.representation === "simple" ? "Decimal fractions: 0.01 represents 1%. No annualization." : readable(data.definition.body && data.definition.body.unit)]);
      for (const [name, value] of values) { const pair = element("div"); pair.append(element("dt", name),element("dd",value)); facts.append(pair); }
      body.append(facts);
      const examples = data.observations.filter(row => row.status === "valid").slice(0,3);
      if (examples.length) {
        body.append(element("h3", "First available returns"));
        body.append(table(["Prediction anchor", "Entry", "Exit", "Return"], examples.map(row =>
          [row.prediction_anchor, row.entry_time, row.exit_time, row.value])));
      }
      const rows = data.observations.slice(0,100);
      body.append(element("p", `Showing ${rows.length} of ${data.observations.length} stored observation rows. Unknown label availability remains unknown. The API supports explicit date-range retrieval.`, "field-note"));
      body.append(table(["Prediction anchor", "Entry", "Exit", "Return", "State", "Label availability", "Reason"],rows.map(row =>
        [row.prediction_anchor,row.entry_time,row.exit_time,row.value,row.status,row.label_available_at,row.reason_code || "—"])));
      const provenance = element("details",undefined,"definition-panel");
      provenance.append(element("summary","Definition, construction and lineage"));
      provenance.append(element("pre",JSON.stringify({definition:data.definition,manifest:data.manifest,
        construction:target.construction || null,readiness_capabilities:caps,
        source_metadata:data.source_metadata || null,
        lineage:Array.isArray(data.operand_lineage) ? data.operand_lineage.slice(0,3) : data.operand_lineage || null,
        observation_operand_sample:rows.slice(0,3).map(row => ({observation_id:row.id,operands:row.operands || row.selected_sources || []}))},null,2)));
      body.append(provenance);
    } catch (_error) {
      if (generation !== detailGeneration) return;
      note.textContent = "This stored Target could not be verified or loaded. Retry to read the same pinned materialization.";
      again.hidden = false;
    } finally {
      window.clearTimeout(timeout);
      if (generation === detailGeneration) details.setAttribute("aria-busy","false");
    }
  }
  select.addEventListener("change", () => { updateNote(); if (details && !details.hidden) loadDetail(); });
  if (detailsLink) detailsLink.addEventListener("click", loadDetail);
  const detailRetry = document.getElementById("target-detail-retry");
  if (detailRetry) detailRetry.addEventListener("click", loadDetail);
  retry.addEventListener("click", load);
  window.addEventListener("experiment-catalog-refresh", event => {
    if (typeof event?.detail?.enqueue === "function") event.detail.enqueue("target", load);
    else load();
  });
  // The contract coordinator starts this read only when its page is visible.
})();
