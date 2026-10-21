"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const select = $("batch-select"), status = $("batch-status"), detail = $("batch-detail"), refresh = $("batch-refresh");
  if (!select || !status || !detail || !refresh) return;
  const labels = {previewing:"Checking selections", ready:"Preview ready · awaiting approval", dispatching:"Submitting approved experiments",
    paused:"Paused", completed:"Batch execution complete", needs_attention:"Needs attention", queued:"Queued", resolving:"Checking inputs",
    preparing:"Preparing observations", p1:"In P1", p2:"In P2", succeeded:"Execution complete", failed:"Execution failed", blocked:"Blocked", cancelled:"Cancelled"};
  let timer, controller, generation = 0, active = true, last = null, page = 0, reviewed = null, busy = false, fresh = false;
  const feedback = nodeFeedback();
  function nodeFeedback() {
    const n = document.createElement("p"); n.role = "status"; n.ariaLive = "polite"; n.className = "field-note";
    detail.before(n); return n;
  }
  const node = (tag, text, cls) => {
    const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n;
  };
  const date = text => {
    const d = new Date(text); return text && Number.isFinite(d.getTime()) ? d.toLocaleString() + " (your time)" : "Not recorded";
  };
  function name(id, ref) {
    for (const option of Array.from($(id)?.options || [])) {
      try { const value = JSON.parse(option.value); if (value.id === ref.id && value.version === ref.version) return option.textContent; } catch (_) { /* placeholder */ }
    }
    return ref.id;
  }
  function actions(value) {
    if (value.read_only) {
      detail.append(node("p", "Historical batch: its time-series research is retained. Retired cross-sectional research was removed. This batch cannot be relaunched.", "field-note"));
      return;
    }
    const controls = node("div", undefined, "queue-heading"), state = value.state.state;
    const button = (id, title, disabled, fn) => {
      const b = node("button", title); b.id = id; b.type = "button"; b.disabled = disabled || busy || !fresh;
      b.addEventListener("click", fn); controls.append(b);
    };
    const eligible = !value.approved && state === "ready" && value.preview_complete && value.preview_sha256 &&
      value.previewed === value.unique_experiments && !(value.preview_counts.blocked > 0);
    if (!value.approved) {
      button("batch-review", "Review batch", !eligible, () => { reviewed = value.preview_sha256; render(last); });
      if (reviewed && reviewed === value.preview_sha256 && eligible) {
        detail.append(node("p", `You are reviewing ${value.unique_experiments} experiments: ${value.preview_counts.new || 0} new and ${value.preview_counts.reuse || 0} reused. Review the Features, Scopes and directions below. Launch queues P1 and, only for admitted candidates, P2.`, "field-note"));
        button("batch-launch", "Launch reviewed batch", false, () => mutate(value, "approve", {preview_sha256: reviewed, exclude_blocked: false}));
      }
      if (value.preview_counts.blocked > 0) detail.append(node("p", "Resolve the blocked selections before launching this batch.", "card-reasons"));
    }
    if (["previewing", "ready", "approved", "dispatching"].includes(state))
      button("batch-pause", "Pause batch", false, () => mutate(value, "pause", {}));
    if (state === "paused") button("batch-resume", value.approved ? "Resume approved batch" : "Resume checks", false, () => mutate(value, "resume", {}));
    detail.append(controls, node("p", "Pausing stops further batch submissions. Experiments already queued or running continue. Preparation runs on the server through the existing research queue.", "field-note"));
  }
  async function mutate(value, action, payload) {
    if (busy || !fresh || last?.batch_id !== value.batch_id) return;
    if (action === "approve" && (reviewed !== last.preview_sha256 || value.preview_sha256 !== last.preview_sha256)) return;
    busy = true; generation++; controller?.abort(); window.clearTimeout(timer);
    select.disabled = refresh.disabled = true; render(last);
    feedback.textContent = "Saving your request…";
    const request = new AbortController(), deadline = window.setTimeout(() => request.abort(), 20000);
    try {
      const response = await fetch("/api/batches/" + encodeURIComponent(value.batch_id) + "/" + action,
        {method:"POST", mode:"same-origin", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload), signal:request.signal});
      if (!response.ok) {
        const messages = {401:"Sign in again, then refresh the batch.", 403:"Your session could not authorize this action. Sign in again and refresh.",
          409:"The batch changed or cannot accept this action. Refresh and review its current status.", 503:"Batch submission is temporarily unavailable. Refresh before trying again."};
        throw Error(messages[response.status] || "The server did not confirm the request. Check the refreshed batch status before trying again.");
      }
      feedback.textContent = action === "approve" ? "Launch approved. The server will process this batch through the research queue." : action === "pause" ? "Batch paused. Previously queued experiments continue." : "Batch resumed.";
    } catch (error) {
      feedback.textContent = error.name === "AbortError" || error instanceof TypeError ? "Request outcome unconfirmed. Checking saved status; do not submit again until it is confirmed." : error.message;
    } finally {
      window.clearTimeout(deadline); busy = false; reviewed = null; fresh = false;
      select.disabled = refresh.disabled = false; if (last) render(last); await load();
    }
  }
  function render(value) {
    detail.replaceChildren();
    const count = value.job_counts, n = key => count[key] || 0;
    const running = ["resolving", "preparing", "p1", "p2"].reduce((sum, key) => sum + n(key), 0);
    detail.append(node("h3", value.name), node("p", labels[value.state.state] || value.state.state),
      node("p", `${n("succeeded")} of ${value.unique_experiments} experiments completed · ${running} running · ${n("queued")} queued · ${n("failed") + n("blocked") + n("cancelled")} need review · ${n("excluded")} excluded`),
      node("p", `${value.previewed} selections checked · ${value.read_only ? "Retained historical batch" : value.approved ? "Launch approved" : "Launch not approved"}. Completed execution does not mean statistical validation.`, "field-note"));
    const timestamps = [value.created_at, value.state.updated_at, ...value.items.flatMap(item => [item.job?.updated_at, item.job?.preparation_progress?.updated_at])]
      .filter(t => t && Number.isFinite(Date.parse(t))).sort((a,b) => Date.parse(b) - Date.parse(a));
    detail.append(node("p", `Last saved update: ${date(timestamps[0])}. Counts come from saved submissions and survive worker restarts.`, "field-note"));
    if (timestamps[0] && Date.now() - Date.parse(timestamps[0]) > 15 * 60 * 1000 && value.approved && value.state.state === "dispatching") {
      detail.append(node("p", "No saved checkpoint in the last 15 minutes. A long step may still be running; this timestamp alone does not confirm a stall.", "field-note"));
    }
    if (value.state.error) detail.append(node("p", value.state.error, "card-reasons"));
    detail.append(node("p", `Preview: ${value.preview_counts.new || 0} new · ${value.preview_counts.reuse || 0} reusable · ${value.preview_counts.blocked || 0} blocked. Existing matching experiments are reused.`, "field-note"));
    const estimates = value.estimates || {};
    const range = (v, unit, scale) => Array.isArray(v) && v.length === 2 ? v.map(x => (x / scale).toFixed(1)).join("–") + " " + unit : "Not yet calibrated";
    detail.append(node("p", `Estimated runtime: ${range(estimates.sequential_seconds_range, "hours", 3600)} · Additional storage: ${range(estimates.additional_bytes_range, "GiB", 1073741824)}. Estimates are not guarantees.`, "field-note"));
    if (estimates.p1_horizon_evaluations !== undefined) detail.append(node("p", `P1: ${estimates.p1_horizon_evaluations} horizon evaluations · P2: up to ${estimates.p2_horizon_evaluations_upper_bound}.`, "field-note"));
    for (const limitation of estimates.limitations || []) detail.append(node("p", limitation, "field-note"));
    actions(value);
    const table = node("table", undefined, "signal-table"), head = node("thead"), heading = node("tr"), body = node("tbody");
    for (const title of ["Feature / Scope", "Progress", "Last update"]) { const th = node("th", title); th.scope = "col"; heading.append(th); }
    head.append(heading);
    page = Math.min(page, Math.max(0, Math.ceil(value.items.length / 25) - 1));
    for (const item of value.items.slice(page * 25, page * 25 + 25)) {
      const row = node("tr"), selection = node("td"), progress = node("td"), job = item.job, prep = job?.preparation_progress;
      selection.append(node("strong", name("feature", item.intent.feature)), node("p", name("scope", item.intent.scope)),
        node("p", `${item.intent.expected_direction === "POSITIVE" ? "Positive" : "Negative"} · Price Return · five horizons`, "field-note"));
      progress.append(node("p", job ? labels[job.status] || job.status : item.dispatch?.state === "excluded" ? "Excluded from launch" : item.disposition === "blocked" ? "Blocked in preview" : "Awaiting submission"));
      if (job?.stage) progress.append(node("p", job.stage));
      if (job?.message) progress.append(node("p", job.message, "field-note"));
      for (const blocker of item.blockers || []) progress.append(node("p", blocker.message, "card-reasons"));
      if (prep && job.status === "preparing") progress.append(node("p", `${prep.members_completed}/${prep.members_total} instruments processed · ${prep.batches_completed} preparation windows processed${prep.instrument ? " · " + prep.instrument : ""}`, "field-note"));
      if (job?.horizons) for (const h of job.horizons) progress.append(node("p", `${h.horizon} days · P1: ${h.p1_status} · P2: ${h.p2_status}`, "field-note"));
      if (job) { const link = node("a", "View Trial Ledger", "text-button"); link.href = "#ledger"; progress.append(link, node("p", job.request_id, "queue-id")); }
      row.append(selection, progress, node("td", date(prep?.updated_at || job?.updated_at || item.dispatch?.at))); body.append(row);
    }
    table.append(head, body); const scroll = node("div", undefined, "table-scroll"); scroll.append(table); detail.append(scroll);
    if (value.items.length > 25) {
      const controls = node("div", undefined, "queue-heading");
      for (const [title, delta, disabled] of [["Previous", -1, page === 0], ["Next", 1, (page + 1) * 25 >= value.items.length]]) {
        const b = node("button", title, "text-button"); b.type = "button"; b.disabled = disabled;
        b.addEventListener("click", () => { page += delta; render(last); }); controls.append(b);
      }
      controls.append(node("span", `Page ${page + 1} of ${Math.ceil(value.items.length / 25)}`)); detail.append(controls);
    }
  }
  async function load() {
    if (!active || busy) return;
    const current = ++generation; window.clearTimeout(timer); controller?.abort(); controller = new AbortController();
    const request = controller, signal = request.signal, deadline = window.setTimeout(() => request.abort(), 20000);
    const get = async url => {
      const r = await fetch(url, {method:"GET", mode:"same-origin", credentials:"same-origin", cache:"no-store", signal});
      if (!r.ok) throw Error("Unavailable"); return r.json();
    };
    try {
      const list = await get("/api/batches"); if (current !== generation) return;
      if (!Array.isArray(list.batches)) throw Error("Invalid batches");
      const selected = select.value, options = list.batches.map(b => { const o = node("option", b.name); o.value = b.batch_id; return o; });
      select.replaceChildren(...options);
      if (!options.length) { select.append(node("option", "No saved batches")); select.value = ""; detail.replaceChildren(); last = null; status.textContent = "No batch has been created. Historical input preparation is a separate operation."; return; }
      select.value = list.batches.some(b => b.batch_id === selected) ? selected : list.batches[list.batches.length - 1].batch_id;
      const bid = select.value, value = await get("/api/batches/" + encodeURIComponent(bid)); if (current !== generation) return;
      if (value.batch_id !== bid || !Array.isArray(value.items) || !value.job_counts || !value.state) throw Error("Invalid batch");
      if (last?.batch_id !== value.batch_id || last?.preview_sha256 !== value.preview_sha256) reviewed = null;
      fresh = true; last = value; render(value); status.textContent = `Status checked ${new Date().toLocaleTimeString()}. Updates every 15 seconds. Research starts only after you launch a batch.`;
    } catch (_) {
      fresh = false; reviewed = null; if (last) render(last);
      if (current === generation) status.textContent = last ? "Connection unavailable. Showing the last retrieved status; current progress is unconfirmed. Retry with Refresh batches." : "Batch status unavailable. Retry with Refresh batches.";
    } finally {
      window.clearTimeout(deadline); if (current === generation && active) timer = window.setTimeout(load, 15000);
    }
  }
  select.addEventListener("change", () => { page = 0; last = null; reviewed = null; fresh = false; feedback.textContent = ""; detail.replaceChildren(); load(); });
  refresh.addEventListener("click", load);
  window.addEventListener("pagehide", () => { active = false; generation++; controller?.abort(); window.clearTimeout(timer); });
  window.addEventListener("pageshow", () => { if (!active) { active = true; load(); } });
  load();
})();
