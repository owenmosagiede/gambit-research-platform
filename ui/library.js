"use strict";

(() => {
  const items = document.getElementById("library-items");
  const status = document.getElementById("library-status");
  const issues = document.getElementById("library-issues");
  const retry = document.getElementById("library-retry");
  const title = document.getElementById("details-title");
  const description = document.getElementById("details-description");
  const body = document.getElementById("details-body");
  const monthFormat = new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
  const dayFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const timeFormat = new Intl.DateTimeFormat(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC"
  });
  const numberFormat = new Intl.NumberFormat();
  const panel = document.getElementById("dataset-details");
  const home = document.getElementById("dataset-detail-home");
  const controls = Object.fromEntries(["search", "provider", "frequency", "from", "to"].map(key => [key, document.getElementById(`pit-${key}`)]));
  let catalogData = null;
  let selectedId = null;
  let requestNumber = 0;
  let activeRequest = null;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function validText(value) {
    return typeof value === "string" && value.trim().length > 0;
  }

  function validDate(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }

  function validCount(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function readCatalog(value) {
    if (!value || value.schema_version !== "1.0.0" || !Array.isArray(value.datasets) || !Array.isArray(value.issues)) {
      throw new Error("Invalid library response");
    }
    const datasets = new Set();
    const snapshots = new Set();
    for (const dataset of value.datasets) {
      if (!dataset || ![dataset.id, dataset.series_id, dataset.name, dataset.provider, dataset.frequency, dataset.units].every(validText) ||
          datasets.has(dataset.id) || !Array.isArray(dataset.snapshots) || dataset.snapshots.length === 0) {
        throw new Error("Invalid dataset entry");
      }
      datasets.add(dataset.id);
      for (const snapshot of dataset.snapshots) {
        if (!snapshot || !/^SNAPSHOT_[0-9a-f]{64}$/.test(snapshot.id) || snapshots.has(snapshot.id) ||
            ![snapshot.label, snapshot.source_view_version].every(validText) ||
            ![snapshot.observation_start, snapshot.observation_end].every(validDate) ||
            (snapshot.scope === "retrospective_snapshot" ? (snapshot.vintage_start !== null || snapshot.vintage_end !== null || snapshot.vintage_count !== 0) :
              ![snapshot.vintage_start,snapshot.vintage_end].every(validDate)) ||
            snapshot.observation_start > snapshot.observation_end || snapshot.vintage_start > snapshot.vintage_end ||
            !validCount(snapshot.observation_count) || !validCount(snapshot.event_count) || snapshot.timing_precision !== "date" ||
            !["full_history", "bounded_sample", "retrospective_snapshot"].includes(snapshot.scope) ||
            !validText(snapshot.captured_at) || !snapshot.captured_at.endsWith("Z") || !Number.isFinite(Date.parse(snapshot.captured_at))) {
          throw new Error("Invalid snapshot entry");
        }
        for (const key of ["vintage_count", "missing_event_count"]) {
          if (key in snapshot && !validCount(snapshot[key])) throw new Error("Invalid snapshot count");
        }
        snapshots.add(snapshot.id);
      }
    }
    if (value.dataset_count !== datasets.size || value.snapshot_count !== snapshots.size) throw new Error("Invalid library counts");
    return value;
  }

  function dateRange(start, end, format) {
    const first = format.format(new Date(`${start}T00:00:00Z`));
    const last = format.format(new Date(`${end}T00:00:00Z`));
    return first === last ? first : `${first} – ${last}`;
  }

  function providerName(value) {
    return value === "FRED_ALFRED" ? "FRED / ALFRED" : value;
  }

  function clearDetails(message) {
    home.append(panel); panel.hidden = true;
    title.textContent = "Explore your saved data";
    description.textContent = message;
    body.replaceChildren();
    body.hidden = true;
  }

  function showDetails(dataset, snapshot, moveFocus = true) {
    selectedId = snapshot.id;
    for (const button of items.querySelectorAll("button[data-snapshot-id]")) {
      const selected = button.dataset.snapshotId === selectedId;
      button.setAttribute("aria-expanded", String(selected));
      if (selected) button.parentElement.append(panel);
    }
    panel.hidden = false;
    title.textContent = dataset.name;
    description.textContent = `${dataset.series_id} · ${providerName(dataset.provider)}`;
    const retrospective = snapshot.scope === "retrospective_snapshot";
    const fields = [
      ["Observation period", dateRange(snapshot.observation_start, snapshot.observation_end, dataset.frequency === "daily" ? dayFormat : monthFormat)],
      ["Observations", `${numberFormat.format(snapshot.observation_count)} · ${dataset.frequency}`],
      ["Units", dataset.units],
      [retrospective ? "Stored close records" : "Vintage records", numberFormat.format(snapshot.event_count)],
      [retrospective ? "Historical vintage evidence" : "Archived vintage dates", retrospective ? "Unavailable · captured snapshot only" : dateRange(snapshot.vintage_start, snapshot.vintage_end, dayFormat)],
      ["Time precision", "Calendar date"],
      [retrospective ? "Last original ingestion" : "Captured", `${timeFormat.format(new Date(snapshot.captured_at))} UTC`]
    ];
    if (retrospective) fields.push(["Price basis", snapshot.price_basis || "Unknown"], ["Historical replay", snapshot.readiness && snapshot.readiness.historical_replay || "Uncertified"], ["Live API capability", snapshot.readiness && snapshot.readiness.live_api_daily_pull || "Unresolved"], ["Snapshot identity", snapshot.id]);
    if (!retrospective && snapshot.vintage_count !== undefined) fields.push(["Distinct vintage dates", numberFormat.format(snapshot.vintage_count)]);
    if (snapshot.missing_event_count !== undefined) fields.push(["Missing records", numberFormat.format(snapshot.missing_event_count)]);
    if (snapshot.verification_state === "catalog_metadata_only") fields.push(["Catalog information", "Saved counts and coverage. Observation integrity is checked when data is used for research."]);
    const list = element("dl", undefined, "detail-grid");
    for (const [label, value] of fields) {
      const field = element("div");
      field.append(element("dt", label), element("dd", value));
      list.append(field);
    }
    const note = element("p", retrospective ? "Retrospective provider history stored in the PIT infrastructure. Original ingestion times are preserved; historical publication times and revision history are unknown. Source close, timezone, exact synchronization and live readiness remain unverified. Observation dates are not availability timestamps." : "Vintage dates identify archived versions of the data. They do not establish an exact release time. ", "precision-note");
    body.replaceChildren(list, note);
    body.hidden = false;
    if (moveFocus) title.focus();
  }

  function preferredSnapshot(dataset) {
    return [...dataset.snapshots].sort((a, b) => Number(b.scope === "full_history") - Number(a.scope === "full_history") ||
      b.captured_at.localeCompare(a.captured_at) || a.id.localeCompare(b.id))[0];
  }
  function filterOptions(key, values, label) {
    const select = controls[key], previous = select.value;
    const all = element("option", label); all.value = "";
    select.replaceChildren(all, ...[...new Set(values)].sort().map(value => {
      const option = element("option", key === "provider" ? providerName(value) : value); option.value = value; return option;
    }));
    select.value = values.includes(previous) ? previous : "";
  }
  function showCatalog(catalog) {
    catalogData = catalog;
    filterOptions("provider", catalog.datasets.map(d => d.provider), "All providers");
    filterOptions("frequency", catalog.datasets.map(d => d.frequency), "All frequencies");
    renderCatalog();
    if (catalog.issues.length > 0) {
      issues.textContent = "Some saved entries could not be loaded. You can retry to check the library again.";
      issues.hidden = false; retry.hidden = false;
    }
  }
  function renderCatalog() {
    if (!catalogData) return;
    home.append(panel); panel.hidden = true;
    const query = controls.search.value.trim().toLowerCase(), from = controls.from.value, to = controls.to.value;
    const invalidRange = from && to && from > to;
    const visible = catalogData.datasets.filter(dataset => {
      const snapshot = preferredSnapshot(dataset);
      return !invalidRange && (!controls.provider.value || dataset.provider === controls.provider.value) &&
        (!controls.frequency.value || dataset.frequency === controls.frequency.value) &&
        (!from || snapshot.observation_end >= from) && (!to || snapshot.observation_start <= to) &&
        (!query || [dataset.name, dataset.id, dataset.series_id, providerName(dataset.provider), dataset.frequency, dataset.units,
          snapshot.scope, snapshot.observation_start, snapshot.observation_end].join(" ").toLowerCase().includes(query));
    });
    const buttons = new Map();
    const list = element("ul", undefined, "dataset-list card-list");
    let restored = null;
    for (const dataset of visible) {
      const snapshot = preferredSnapshot(dataset);
      const item = element("li", undefined, "library-card");
      const button = element("button", undefined, "card-toggle");
      button.type = "button"; button.dataset.snapshotId = snapshot.id;
      button.setAttribute("aria-controls", "dataset-details");
      button.setAttribute("aria-expanded", String(snapshot.id === selectedId));
      button.append(element("span", dataset.name, "dataset-name"), element("span", dataset.series_id, "dataset-id"),
        element("span", providerName(dataset.provider), "dataset-source"));
      button.append(element("span", `${dateRange(snapshot.observation_start, snapshot.observation_end, dataset.frequency === "daily" ? dayFormat : monthFormat)} · ${dataset.frequency}`, "snapshot-coverage"));
      button.append(element("span", `${numberFormat.format(snapshot.observation_count)} observations`, "snapshot-count"));
      button.append(element("span", snapshot.id === selectedId ? "Collapse details −" : "Explore dataset +", "card-action"));
      button.addEventListener("click", () => {
        if (selectedId === snapshot.id) { selectedId = null; clearDetails(""); renderCatalog().get(snapshot.id)?.focus(); }
        else { selectedId = snapshot.id; renderCatalog(); showDetails(dataset, snapshot); }
      });
      item.append(button); list.append(item); buttons.set(snapshot.id, button);
      if (snapshot.id === selectedId) restored = [dataset, snapshot];
    }
    items.replaceChildren(list);
    status.textContent = invalidRange ? "Coverage from must be on or before Coverage to." :
      `${visible.length} of ${catalogData.dataset_count} ${catalogData.dataset_count === 1 ? "dataset" : "datasets"}`;
    if (!visible.length) items.append(element("p", catalogData.datasets.length ? "No datasets match these filters. Try a different search or clear the filters." : "No PIT datasets are available yet.", "empty-table"));
    if (restored) showDetails(...restored, false);
    else { selectedId = null; clearDetails(""); }
    return buttons;
  }

  async function loadCatalog() {
    if (activeRequest) return;
    const currentRequest = ++requestNumber;
    if (activeRequest) activeRequest.abort();
    const controller = new AbortController();
    activeRequest = controller;
    const focusRetryOnFailure = document.activeElement === retry;
    home.append(panel); panel.hidden = true; catalogData = null;
    items.replaceChildren();
    items.setAttribute("aria-busy", "true");
    status.textContent = "Loading saved datasets…";
    issues.hidden = true;
    retry.hidden = true;
    clearDetails("Loading the saved data library…");
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      if (window.location.protocol === "file:") throw new Error("Local platform required");
      const response = await fetch("/api/pit-library", {
        method: "GET", mode: "same-origin", credentials: "same-origin", cache: "no-store", signal: controller.signal
      });
      if (!response.ok) throw new Error("Library unavailable");
      const catalog = readCatalog(await response.json());
      if (currentRequest !== requestNumber) return;
      showCatalog(catalog);
      if (focusRetryOnFailure && !retry.hidden) retry.focus();
    } catch (_error) {
      if (currentRequest !== requestNumber) return;
      status.textContent = window.location.protocol === "file:"
        ? "Open this page through the local platform to load the library."
        : "The data library could not be loaded. Please try again.";
      clearDetails("Dataset details will appear once the library is available.");
      retry.textContent = "Retry";
      retry.hidden = false;
      if (focusRetryOnFailure) retry.focus();
    } finally {
      window.clearTimeout(timeout);
      if (currentRequest === requestNumber) {
        activeRequest = null;
        items.setAttribute("aria-busy", "false");
      }
    }
  }

  for (const control of Object.values(controls)) control.addEventListener("input", renderCatalog);
  document.getElementById("pit-clear").addEventListener("click", () => {
    for (const control of Object.values(controls)) control.value = "";
    renderCatalog();
  });
  document.getElementById("target-details-link").addEventListener("click", () => { document.getElementById("selection-details").open = true; });
  retry.addEventListener("click", loadCatalog);
  function loadWhenVisible() {
    if (["#pit", "#pit-page"].includes(window.location.hash) && !catalogData && !activeRequest) loadCatalog();
  }
  window.addEventListener("hashchange", loadWhenVisible);
  loadWhenVisible();
})();
