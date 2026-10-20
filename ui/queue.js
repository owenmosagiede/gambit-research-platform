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
  let timer = null, loading = false, active = true, last = null, rendered = null, ledgerRendered = null;
  let client = window.researchSubmissionState || null, focusedRequest = null;
  const actions = new Map(), publishedResults = new Map();
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
  function selectedName(id, reference) {
    for (const option of Array.from($(id)?.options || [])) {
      try {
        const value = JSON.parse(option.value);
        if (value.id === reference.id && value.version === reference.version) return option.textContent;
      } catch (_error) { /* Placeholder options have no reference. */ }
    }
    return reference.id;
  }
  function selection(intent) {
    return {Feature: selectedName("feature", intent.feature), Target: "Price Return · all five horizons",
      Scope: selectedName("scope", intent.scope), "Expected Direction": intent.expected_direction === "POSITIVE" ? "Positive" : "Negative"};
  }
  function visibleItems(value) {
    const items = [...value.items];
    if ((client?.uncertain || client?.rejection) && !items.some(item => item.job.request_id === client.payload.request_id)) {
      const p = client.payload;
      items.push({client_only:true, selection:client.selection, intent:p, job:{request_id:p.request_id,
        status:client.busy ? "submitting" : client.rejection ? "rejected" : "unconfirmed", message:client.message, progress:{completed:0,total:5},
        horizons:[], results:[], blockers:[], mode:null}});
    }
    return items;
  }
  const outcome = value => ({pending:"Pending", admitted:"Admitted", rejected:"Rejected", not_admitted:"Not admitted", not_run:"Not run", VALIDATED:"Validated", FAILED:"Failed", UNRESOLVED:"Unresolved"}[value] || value);
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
      for (const h of [...j.horizons].sort((a,b) => a.horizon-b.horizon)) list.append(node("li", `${h.horizon} · P1: ${outcome(h.p1_status)} · P2: ${outcome(h.p2_status)}`));
      card.append(list);
    }
    if (j.operational_failure) card.append(node("p", "Operational failure; this is not a statistical rejection. Saved evidence is preserved."));
    if (j.results.length) { const link=node("a", `${j.results.length} saved result links · View Signal Library`, "text-button"); link.href="#signals"; card.append(link); }
    const state = actions.get(j.request_id);
    if (state) card.append(node("p", state.message, "card-action-status"));
    const button = (label, fn, disabled=false) => { const b=node("button",label,"text-button"); b.type="button"; b.disabled=disabled; b.addEventListener("click",fn); card.append(b); };
    if (item.client_only) {
      if (!client.busy) {
        button("Check receipt", () => window.dispatchEvent(new CustomEvent("research-submission-recover",{detail:{request_id:j.request_id,resend:false}})));
        button("Check and retry", () => window.dispatchEvent(new CustomEvent("research-submission-recover",{detail:{request_id:j.request_id,resend:true}})));
      }
    } else if (state?.unknown) button("Check status", () => act(item,"status"),state.busy);
    else {
      if (["queued","resolving","preparing","p1","p2"].includes(j.status)) button("Cancel", () => act(item,"cancel"),state?.busy);
      if (["blocked","failed","cancelled"].includes(j.status) && j.resumable !== false) button("Resume", () => act(item,"resume"),state?.busy || !last?.worker.healthy);
    }
  }
  function redraw() { if (last) { render(last); renderLedger(); updateStatus(); } else render({items:[]}); }
  async function act(item, action) {
    const rid = item.job.request_id;
    if (actions.get(rid)?.busy) return;
    actions.set(rid,{busy:true,unknown:action==="status",message:action === "status" ? "Checking saved status…" : `${action === "cancel" ? "Requesting cancellation" : "Requesting resume"}…`}); redraw();
    const controller = new AbortController(), deadline=window.setTimeout(() => controller.abort(),20000);
    try {
      const response=await fetch(`/api/experiments/${encodeURIComponent(rid)}${action === "status" ? "" : "/"+action}`,{
        method:action === "status" ? "GET" : "POST",mode:"same-origin",credentials:"same-origin",cache:"no-store",signal:controller.signal,
        ...(action === "status" ? {} : {headers:{"Content-Type":"application/json"},body:"{}"})});
      const value=await response.json();
      if (!response.ok) {
        actions.set(rid,{unknown:response.status !== 409,message:value.error?.message || `Server returned HTTP ${response.status}. Check status before trying again.`});
      } else {
        validate({items:[{job:value.job,intent:item.intent}],issues:[],worker:{}});
        if (value.job.request_id !== rid) throw Error("Wrong submission response");
        item.job=value.job;
        const saved=last?.items.find(row=>row.job.request_id===rid); if (saved) saved.job=value.job;
        actions.delete(rid);
        window.dispatchEvent(new CustomEvent("research-queue-state",{detail:last}));
      }
    } catch (_error) { actions.set(rid,{unknown:true,message:"The response could not be confirmed. Check status before repeating the action."}); }
    finally { window.clearTimeout(deadline); rendered=null; ledgerRendered=null; redraw(); }
  }
  function render(value) {
    board.replaceChildren();
    for (const [key, title, states] of groups) {
      const rows = visibleItems(value).filter(item => states.includes(item.job.status) && !isDismissed(item));
      const column = node("section", undefined, "queue-column"), heading = node("h3", title);
      heading.append(node("span", String(rows.length), "queue-count")); column.append(heading);
      for (const item of rows) {
        const job = item.job, names = item.selection || (item.intent ? selection(item.intent) : null);
        const card = node("article", undefined, "queue-card"); card.dataset.requestId = job.request_id;
        if (key === "attention" && item.client_only) {
          const remove = node("button", "×", "queue-remove"); remove.type = "button";
          remove.setAttribute("aria-label", `Dismiss local submission notice ${job.request_id}`);
          remove.title = "Dismiss local notice · checks unknown receipts first; never deletes research";
          remove.disabled = client.busy;
          remove.addEventListener("click", () => window.dispatchEvent(new CustomEvent("research-submission-dismiss", {detail:{request_id:job.request_id}})));
          card.append(remove);
        } else if (key === "attention" && job.attempt_id) {
          const remove = node("button", "×", "queue-remove"); remove.type = "button";
          remove.setAttribute("aria-label", `Remove resolved submission ${job.request_id} from queue`);
          remove.title = "Remove from queue · saved records stay in Trial Ledger";
          remove.addEventListener("click", () => dismiss(item)); card.append(remove);
        }
        card.append(node("span", job.request_id, "queue-id"), node("h4", names ? names.Feature : "Submission evidence unavailable"));
        if (names) card.append(node("p", `${names.Scope} · ${names.Target} · ${names["Expected Direction"]}`));
        card.append(node("p", `${labels[job.status]}${item.queue_position ? ` · Waiting position ${item.queue_position}` : ""}`),
          node("p", item.client_only ? "No execution is confirmed for this request." : `${job.progress.completed} of ${job.progress.total} work items completed`), node("p", job.message));
        if (job.status === "succeeded") card.append(node("p", "Execution complete. Scientific outcomes are listed separately for each horizon."));
        addDetails(card, item);
        column.append(card);
      }
      if (!rows.length) column.append(node("p", "No submissions", "field-note"));
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
    const visible = visibleItems(last).filter(item => !["succeeded", "cancelled"].includes(item.job.status) && !isDismissed(item)).length;
    status.textContent = `${visible} queue item${visible === 1 ? "" : "s"}. Completed submissions are in Trial Ledger. ` +
      (last.worker.healthy ? "Worker available. " : "Worker unavailable; saved jobs are retained. ") +
      (last.issues.length ? `${last.issues.length} record(s) could not be verified: ${last.issues.map(i => i.request_id).join(", ")}.` : "Updates automatically.");
  }
  function renderLedger() {
    const list = $("ledger-items"), note = $("ledger-status");
    if (!list || !note || !last) return;
    const search = $("ledger-search").value.trim().toLowerCase(), state = $("ledger-state").value;
    const from = $("ledger-from").value, to = $("ledger-to").value;
    const all = last.items.filter(item => finished.has(item.job.status));
    const rows = all.filter(item => {
      const names = item.intent ? selection(item.intent) : {};
      const day = item.job.updated_at.slice(0, 10);
      return (!state || item.job.status === state) && (!from || day >= from) && (!to || day <= to) &&
        (!search || JSON.stringify([names, item.intent, item.job.request_id]).toLowerCase().includes(search));
    }).sort((a,b) => b.job.updated_at.localeCompare(a.job.updated_at) || a.job.request_id.localeCompare(b.job.request_id));
    const signature = JSON.stringify([rows.map(item => [item, item.intent ? selection(item.intent) : null]), dismissed, search, state, from, to]);
    if (signature === ledgerRendered) return;
    ledgerRendered = signature;
    const expanded = new Set(Array.from(list.children).filter(card => card.open).map(card => card.dataset.requestId));
    list.replaceChildren();
    if (from && to && from > to) { note.textContent = "Finished from must be on or before Finished through."; return; }
    note.textContent = `${rows.length} of ${all.length} saved submissions. ${last.issues.length ? "Some records could not be verified; see queue status." : "Each entry preserves its original selections and horizon outcomes."}`;
    for (const item of rows) {
      const j = item.job, names = item.intent ? selection(item.intent) : null;
      const card = node("details", undefined, "ledger-card"); card.dataset.requestId = j.request_id; card.open = expanded.has(j.request_id) || focusedRequest === j.request_id;
      const summary = node("summary");
      summary.append(node("strong", names ? names.Feature : "Submission evidence unavailable"),
        node("span", names ? `${names.Scope} · ${names.Target} · ${names["Expected Direction"]}` : j.request_id),
        node("span", `${labels[j.status]} · ${j.updated_at.slice(0, 19).replace("T", " ")} UTC${isDismissed(item) ? " · Removed from queue" : ""}`));
      card.append(summary, node("p", j.request_id, "queue-id"), node("p", j.message, "field-note"));
      if (j.blockers.length) card.append(node("p", j.blockers.map(b => b.message).join(" "), "field-note"));
      const scroll = node("div", undefined, "table-scroll"), table = node("table", undefined, "signal-table");
      const head = node("thead"), heading = node("tr");
      for (const title of ["Horizon · scheduled weekdays", "P1", "P2"]) { const cell = node("th", title); cell.scope = "col"; heading.append(cell); }
      head.append(heading); const body = node("tbody");
      for (const h of [...j.horizons].sort((a,b) => a.horizon - b.horizon)) {
        const row = node("tr"); row.append(node("td", String(h.horizon)), node("td", h.p1_status), node("td", h.p2_status)); body.append(row);
      }
      table.append(head, body); scroll.append(table); card.append(scroll);
      card.append(node("p", `${j.results.length} stored research result links. Completed execution does not mean a validated relationship.`, "field-note"));
      // History is self-contained; there is no separate progress panel.
      addDetails(card, {...item,job:{...j,horizons:[],blockers:[]}});
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
    if (!rows.length) list.append(node("p", "No saved submissions match these filters.", "field-note"));
  }
  function validate(value) {
    if (!value || !Array.isArray(value.items) || !Array.isArray(value.issues) || !value.worker) throw Error("Invalid queue");
    const seen = new Set();
    for (const item of value.items) {
      const j = item.job;
      if (!j || typeof j.request_id !== "string" || seen.has(j.request_id) || !Object.hasOwn(labels, j.status) ||
          !j.progress || !Number.isSafeInteger(j.progress.completed) || !Number.isSafeInteger(j.progress.total) ||
          !Array.isArray(j.horizons) || !Array.isArray(j.blockers) || !Array.isArray(j.results) ||
          typeof j.message !== "string" || (item.intent && (!item.intent.feature || !item.intent.scope))) throw Error("Invalid queue entry");
      seen.add(j.request_id);
    }
    return value;
  }
  async function load() {
    if (loading || !active) return;
    if (timer !== null) window.clearTimeout(timer);
    loading = true; refresh.disabled = true;
    const controller = new AbortController(), deadline = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch("/api/experiments", {method: "GET", credentials: "same-origin", mode: "same-origin", cache: "no-store", signal: controller.signal});
      if (!response.ok) throw Error("Queue unavailable");
      last = validate(await response.json());
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
      const signature = JSON.stringify([client, [...actions], dismissed, last.items.map(item => [item, item.intent ? selection(item.intent) : null])]);
      if (signature !== rendered) { render(last); rendered = signature; }
      renderLedger();
      updateStatus();
    } catch (_error) {
      if ($("ledger-status")) $("ledger-status").textContent = "History could not be refreshed. Previously shown records may be out of date.";
      status.textContent = "Queue status could not be refreshed. " + (last ? "Showing the last verified status; it may be out of date." : "No job status is available yet.");
    } finally {
      window.clearTimeout(deadline); loading = false; refresh.disabled = false;
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
  window.addEventListener("research-submission-state", event => { client=event.detail; rendered=null; redraw(); });
  window.addEventListener("research-job-update", event => {
    const item=event.detail;
    if (!last) last={items:[],issues:[],worker:{healthy:true}};
    const index=last.items.findIndex(row=>row.job.request_id===item.job.request_id);
    if (index<0) last.items.push(item); else last.items[index]={...last.items[index],...item};
    rendered=null; ledgerRendered=null; redraw();
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
  redraw(); load();
})();
