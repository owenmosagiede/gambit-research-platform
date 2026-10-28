"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const board = $("queue-board"), status = $("queue-status"), refresh = $("queue-refresh");
  if (!board || !status || !refresh) return;
  const groups = [
    ["waiting", "In Queue", ["queued", "submitting"]],
    ["running", "Preparing / In P1 / In P2", ["resolving", "preparing", "p1", "p2"]],
    ["attention", "Needs attention", ["blocked", "failed", "unconfirmed", "rejected"]]
  ];
  const labels = {rejected:"Submission rejected", submitting:"Saving submission", unconfirmed:"Receipt unconfirmed", queued: "Queued", resolving: "Checking inputs", preparing: "Preparing observations",
    p1: "In P1", p2: "In P2", blocked: "Blocked", failed: "Execution failed", succeeded: "Completed", cancelled: "Cancelled"};
  let timer = null, loading = false, active = true, last = null, stale = false, rendered = null, ledgerRendered = null;
  let initialReadSettled = false;
  let focusedRequest = null;
  const publishedResults = new Map();
  const dismissalKey = "research-platform.queue-dismissals.v1";
  const attention = new Set(["blocked", "failed"]);
  let dismissed = {};
  function readDismissals() {
    try {
      const value = JSON.parse(window.localStorage.getItem(dismissalKey) || "{}");
      if (value && typeof value === "object" && !Array.isArray(value)) dismissed = value;
    } catch (_error) { /* Show records if saved preferences cannot be read. */ }
  }
  function isDismissed(item) {
    const j = item.job, saved = dismissed[j.request_id];
    return attention.has(j.status) && saved && saved.attempt_id === j.attempt_id && saved.status === j.status;
  }
  readDismissals();
  const finished = new Set(["succeeded", "cancelled", "blocked", "failed"]);
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  function selection(item) {
    const p = item.presentation;
    if (p?.state === "verified" && [p.title, p.subtitle, p.feature_label, p.scope_label, p.target_label].every(v => typeof v === "string" && v.length)) {
      return {Feature: p.feature_label, Scope: p.scope_label, Title: p.title, Subtitle: p.subtitle, Target: p.target_label};
    }
    return {Feature: "Saved experiment", Scope: item.intent?.scope.id || "Scope unavailable", Title: "Saved experiment",
      Subtitle: "Saved input labels could not be verified. Expand the record for its exact selections.",
      Target: "Forward price return · five forecast horizons"};
  }
  function references(card, item) {
    const details = node("details", undefined, "definition-panel");
    details.append(node("summary", "Exact selections and record IDs"));
    details.append(node("p", `Request: ${item.job.request_id}`, "queue-id"));
    if (item.intent) {
      for (const [label, key] of [["Feature", "feature"], ["Scope", "scope"]]) {
        const reference = item.intent[key];
        details.append(node("p", `${label}: ${reference.id} · version ${reference.version}`, "queue-id"));
      }
      details.append(node("p", `Expected direction: ${item.intent.expected_direction}`, "field-note"));
    }
    if (item.presentation?.state === "verified") {
      for (const [label, key] of [["Feature definition", "feature_reference"], ["Scope definition", "scope_reference"], ["Frozen membership", "membership_snapshot"]]) {
        const value = item.presentation[key];
        if (value) details.append(node("p", `${label}: ${JSON.stringify(value)}`, "queue-id"));
      }
    }
    card.append(details);
  }
  const outcome = value => ({pending:"Pending", admitted:"Admitted", rejected:"Rejected", unresolved:"Inconclusive", not_admitted:"Not admitted", not_run:"Not run", VALIDATED:"Validated", FAILED:"Failed", UNRESOLVED:"Inconclusive"}[value] || value);
  function addDetails(card, item) {
    const j = item.job;
    card.id = `trial-${j.request_id}`;
    const prep = j.preparation_progress;
    if (j.status === "preparing" && prep && j.stage === `${prep.phase} preparation`) {
      const n = value => Number.isInteger(value) && value >= 0;
      if (n(prep.members_completed) && n(prep.members_total) && n(prep.batches_completed)) {
        card.append(node("p", `${prep.phase} preparation · ${prep.members_completed}/${prep.members_total} instruments processed · ${prep.batches_completed} batches processed`, "card-preparation"));
        if (prep.instrument) card.append(node("p", `Current instrument: ${prep.instrument}${prep.start && prep.end ? " · " + prep.start + " – " + prep.end : ""}`));
        if (prep.updated_at) card.append(node("p", `Last preparation checkpoint: ${prep.updated_at} · updates at batch boundaries`, "field-note"));
        card.append(node("p", "Processed batches may include unavailable observations. This is preparation progress, not P1/P2 results.", "field-note"));
      }
    }
    if (j.mode) card.append(node("p", `${j.mode === "TS" ? "Time series" : "Cross sectional"} research · 1, 7, 21, 63, 252 scheduled weekdays`));
    const reasons = [...j.blockers, ...(j.resume_blocker ? [j.resume_blocker] : [])];
    if (reasons.length) { const list = node("ul", undefined, "card-reasons"); for (const b of reasons) list.append(node("li", b.message)); card.append(list); }
    if (j.horizons.length) {
      const list = node("ul", undefined, "card-horizons");
      for (const h of [...j.horizons].sort((a,b) => a.horizon-b.horizon)) list.append(node("li", `${h.horizon}-day forecast · P1: ${outcome(h.p1_status)} · P2: ${outcome(h.p2_status)}`));
      card.append(list);
    }
    if (j.operational_failure) card.append(node("p", "Operational failure; this is not a statistical rejection. Saved evidence is preserved."));
    if (j.results.length) { const link=node("a", `${j.results.length} saved result links · View Signal Library`, "text-button"); link.href="#signals"; card.append(link); }
  }
  function renderUnavailable(failed = false) {
    const message = failed ? "Saved submissions could not be loaded. Refresh to try again." : "Loading saved submissions…";
    board.replaceChildren(node("p", message, "field-note"));
    $("ledger-items")?.replaceChildren(node("p", message, "field-note"));
    status.textContent = failed ? "Queue status is unavailable. No saved job status has been verified yet." : "Loading queue status…";
    if ($("ledger-status")) $("ledger-status").textContent = failed ? "Trial history is unavailable. No saved history has been verified yet." : "Loading trial history…";
  }
  function render(value) {
    board.replaceChildren();
    for (const [key, title, states] of groups) {
      const rows = value.items.filter(item => states.includes(item.job.status) && !isDismissed(item));
      const column = node("section", undefined, "queue-column"), heading = node("h3", title);
      heading.append(node("span", String(rows.length), "queue-count")); column.append(heading);
      for (const item of rows) {
        const job = item.job, names = item.intent ? selection(item) : null;
        const card = node("article", undefined, "queue-card"); card.dataset.requestId = job.request_id;
        if (key === "attention" && job.attempt_id) {
          const remove = node("button", "×", "queue-remove"); remove.type = "button";
          remove.setAttribute("aria-label", `Remove resolved submission ${job.request_id} from queue`);
          remove.title = "Remove from queue · saved records stay in Trial Ledger";
          remove.addEventListener("click", () => dismiss(item)); card.append(remove);
        }
        card.append(node("h4", names ? names.Title : "Submission evidence unavailable"));
        if (names) card.append(node("p", names.Subtitle), node("p", names.Target, "field-note"));
        card.append(node("p", `${labels[job.status]}${item.queue_position ? ` · Waiting position ${item.queue_position}` : ""}`),
          node("p", `${job.progress.completed} of ${job.progress.total} work items completed`), node("p", job.message));
        if (job.status === "succeeded") card.append(node("p", "Execution complete. Scientific outcomes are listed separately for each horizon."));
        addDetails(card, item);
        references(card, item);
        column.append(card);
      }
      if (!rows.length) column.append(node("p", value.issues.length ? "No verified submissions. Some records are unavailable." : "No submissions", "field-note"));
      board.append(column);
    }
  }
  function dismiss(item) {
    const notice = $("queue-action-status");
    const current = last?.items.find(row => row.job.request_id === item.job.request_id);
    if (!current || !attention.has(current.job.status) || current.job.attempt_id !== item.job.attempt_id) {
      notice.textContent = "This item changed. Refresh the queue before removing it."; return;
    }
    // A browser preference only. Never submit, cancel, resume or delete research.
    readDismissals();
    const next = {...dismissed, [item.job.request_id]: {attempt_id: item.job.attempt_id, status: item.job.status}};
    try { window.localStorage.setItem(dismissalKey, JSON.stringify(next)); }
    catch (_error) { notice.textContent = "This browser could not save the removal. The item remains in the queue."; return; }
    dismissed = next; rendered = null; ledgerRendered = null; render(last); renderLedger(); updateStatus();
    notice.textContent = "Removed from this browser’s queue. Saved records remain in Trial Ledger.";
  }
  function updateStatus() {
    const visible = last.items.filter(item => !["succeeded", "cancelled"].includes(item.job.status) && !isDismissed(item)).length;
    status.textContent = (stale ? "Queue status could not be refreshed. Showing the last verified status; it may be out of date. " : "") +
      `${visible} queue item${visible === 1 ? "" : "s"}. Completed submissions are in Trial Ledger. ` +
      (stale ? "Last verified worker status: " : "") +
      (last.worker.healthy ? "Worker available. " : "Worker unavailable; saved jobs are retained. ") +
      (last.issues.length ? `${last.issues.length} record(s) could not be verified: ${last.issues.map(i => i.request_id).join(", ")}.` : stale ? "Refresh will retry automatically." : "Updates automatically.");
  }
  function renderLedger() {
    const list = $("ledger-items"), note = $("ledger-status");
    if (!list || !note || !last) return;
    const search = $("ledger-search").value.trim().toLowerCase(), state = $("ledger-state").value;
    const from = $("ledger-from").value, to = $("ledger-to").value;
    const all = last.items.filter(item => finished.has(item.job.status));
    const rows = all.filter(item => {
      const names = item.intent ? selection(item) : {};
      const day = item.job.updated_at.slice(0, 10);
      return (!state || item.job.status === state) && (!from || day >= from) && (!to || day <= to) &&
        (!search || JSON.stringify([names, item.intent, item.job.request_id]).toLowerCase().includes(search));
    }).sort((a,b) => b.job.updated_at.localeCompare(a.job.updated_at) || a.job.request_id.localeCompare(b.job.request_id));
    const signature = JSON.stringify([rows.map(item => [item, item.intent ? selection(item) : null]), dismissed, search, state, from, to, stale]);
    if (signature === ledgerRendered) return;
    ledgerRendered = signature;
    const expanded = new Set(Array.from(list.children).filter(card => card.open).map(card => card.dataset.requestId));
    list.replaceChildren();
    const freshness = stale ? "History could not be refreshed. Showing the last verified records; they may be out of date. " : "";
    if (from && to && from > to) { note.textContent = freshness + "Finished from must be on or before Finished through."; return; }
    note.textContent = freshness + `${rows.length} of ${all.length} saved submissions. ${last.issues.length ? "Some records could not be verified; see queue status." : "Each entry preserves its original selections and horizon outcomes."}`;
    for (const item of rows) {
      const j = item.job, names = item.intent ? selection(item) : null;
      const card = node("details", undefined, "ledger-card"); card.dataset.requestId = j.request_id; card.open = expanded.has(j.request_id) || focusedRequest === j.request_id;
      const summary = node("summary");
      summary.append(node("strong", names ? names.Title : "Submission evidence unavailable"),
        node("span", names ? names.Subtitle : j.request_id),
        node("span", `${labels[j.status]} · ${j.updated_at.slice(0, 19).replace("T", " ")} UTC${isDismissed(item) ? " · Removed from queue" : ""}`));
      card.append(summary, node("p", names ? names.Target : "", "field-note"), node("p", j.message, "field-note"));
      if (item.presentation?.schedule_note) card.append(node("p", item.presentation.schedule_note, "field-note"));
      if (j.blockers.length) card.append(node("p", j.blockers.map(b => b.message).join(" "), "field-note"));
      const scroll = node("div", undefined, "table-scroll"), table = node("table", undefined, "signal-table");
      const head = node("thead"), heading = node("tr");
      for (const title of ["Forecast horizon · scheduled weekdays", "P1 · discovery", "P2 · validation"]) { const cell = node("th", title); cell.scope = "col"; heading.append(cell); }
      head.append(heading); const body = node("tbody");
      for (const h of [...j.horizons].sort((a,b) => a.horizon - b.horizon)) {
        const row = node("tr"); row.append(node("td", String(h.horizon)), node("td", outcome(h.p1_status)), node("td", outcome(h.p2_status))); body.append(row);
      }
      table.append(head, body); scroll.append(table); card.append(scroll);
      card.append(node("p", `${j.results.length} stored research result links. Completed execution does not mean a validated relationship.`, "field-note"));
      // History is self-contained; there is no separate progress panel.
      addDetails(card, {...item,job:{...j,horizons:[],blockers:[]}});
      references(card, item);
      if (isDismissed(item)) {
        const restore = node("button", "Show in queue", "text-button ledger-restore"); restore.type = "button";
        restore.addEventListener("click", () => {
          readDismissals(); const next = {...dismissed}; delete next[j.request_id];
          try { window.localStorage.setItem(dismissalKey, JSON.stringify(next)); }
          catch (_error) { note.textContent = "This browser could not save the change. Please try again."; return; }
          dismissed = next; rendered = null; ledgerRendered = null; render(last); renderLedger(); updateStatus();
        }); card.append(restore);
      }
      list.append(card);
    }
    if (!rows.length) list.append(node("p", last.issues.length ? "No verified saved submissions match these filters. Some records are unavailable." : "No saved submissions match these filters.", "field-note"));
  }
  function validate(value) {
    if (!value || !Array.isArray(value.items) || !Array.isArray(value.issues) ||
        !value.issues.every(issue => issue && typeof issue.request_id === "string") ||
        !value.worker || typeof value.worker.healthy !== "boolean") throw Error("Invalid queue");
    const seen = new Set();
    for (const item of value.items) {
      const j = item.job;
      if (!j || typeof j.request_id !== "string" || seen.has(j.request_id) || !Object.hasOwn(labels, j.status) ||
          !j.progress || !Number.isSafeInteger(j.progress.completed) || !Number.isSafeInteger(j.progress.total) ||
          !Array.isArray(j.horizons) || !Array.isArray(j.blockers) || !Array.isArray(j.results) ||
          typeof j.updated_at !== "string" || !j.horizons.every(h => h && Number.isSafeInteger(h.horizon)) ||
          !j.blockers.every(blocker => blocker && typeof blocker.message === "string") ||
          typeof j.message !== "string" || (item.intent && (!item.intent.feature || !item.intent.scope))) throw Error("Invalid queue entry");
      seen.add(j.request_id);
    }
    return value;
  }
  async function load() {
    if (loading || !active) return;
    if (timer !== null) window.clearTimeout(timer);
    loading = true; refresh.disabled = true;
    if (!last) renderUnavailable();
    board.setAttribute("aria-busy", "true"); $("ledger-items")?.setAttribute("aria-busy", "true");
    // Give the first verified history read time to warm its cache. Later
    // refreshes can time out sooner while the last verified records stay visible.
    const controller = new AbortController(), deadline = window.setTimeout(() => controller.abort(), last ? 20000 : 60000);
    try {
      const response = await fetch("/api/experiments", {method: "GET", credentials: "same-origin", mode: "same-origin", cache: "no-store", signal: controller.signal});
      if (!response.ok) throw Error("Queue unavailable");
      last = validate(await response.json());
      stale = false;
      window.dispatchEvent(new CustomEvent("research-queue-state",{detail:last}));
      for (const item of last.items) {
        const refs = item.job.results;
        const signature = JSON.stringify(refs);
        if (refs.length && publishedResults.get(item.job.request_id) !== signature) {
          publishedResults.set(item.job.request_id,signature);
          window.dispatchEvent(new CustomEvent("research-results-updated",{detail:{request_id:item.job.request_id,results:refs}}));
        }
      }
      // Keep buttons and scroll positions stable when the saved queue is unchanged.
      const signature = JSON.stringify([dismissed, last.items.map(item => [item, item.intent ? selection(item) : null])]);
      if (signature !== rendered) { render(last); rendered = signature; }
      renderLedger();
      updateStatus();
    } catch (_error) {
      stale = true;
      if (last) { renderLedger(); updateStatus(); }
      else renderUnavailable(true);
    } finally {
      window.clearTimeout(deadline); loading = false; refresh.disabled = false;
      board.setAttribute("aria-busy", "false"); $("ledger-items")?.setAttribute("aria-busy", "false");
      if (!initialReadSettled) {
        initialReadSettled = true;
        window.dispatchEvent(new CustomEvent("research-queue-settled", {detail: {verified: Boolean(last && !stale)}}));
      }
      if (active) timer = window.setTimeout(load, 5000);
    }
  }
  for (const name of ["ledger-search", "ledger-state", "ledger-from", "ledger-to"]) {
    $(name)?.addEventListener("input", renderLedger);
  }
  $("ledger-clear")?.addEventListener("click", () => {
    for (const name of ["ledger-search", "ledger-state", "ledger-from", "ledger-to"]) $(name).value = "";
    renderLedger();
  });
  window.addEventListener("storage", event => {
    if (event.key !== dismissalKey && event.key !== null) return;
    dismissed = {}; readDismissals(); rendered = null; ledgerRendered = null;
    if (last) { render(last); renderLedger(); updateStatus(); }
  });
  window.addEventListener("research-ledger-focus", event => {
    focusedRequest = event.detail?.request_id;
    if (!focusedRequest || !$("ledger-search")) return;
    $("ledger-search").value = focusedRequest;
    for (const name of ["ledger-state", "ledger-from", "ledger-to"]) $(name).value = "";
    ledgerRendered = null; renderLedger();
  });
  window.addEventListener("research-queue-refresh", load);
  refresh.addEventListener("click", load);
  window.addEventListener("pagehide", () => { active = false; window.clearTimeout(timer); });
  window.addEventListener("pageshow", () => { active = true; load(); });
  load();
})();
