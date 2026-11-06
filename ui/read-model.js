"use strict";

(() => {
  if (document.querySelector('meta[name="gambit-read-model"]')?.content !== "enabled") return;
  const $ = id => document.getElementById(id);
  const prefix = "/api/read-model/v1/";
  const state = new Map();
  let visible = null, timer = null, selected = null;
  const node = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  };
  const button = (text, action) => {
    const n = node("button", text, "text-button"); n.type = "button";
    n.addEventListener("click", action); return n;
  };
  const freshness = data => {
    const f = data.freshness;
    const age = f.state === "current" ? "Verified snapshot" : f.state === "delayed" ? "Update delayed" : "Historical snapshot — current activity unknown";
    return `${age} · observed ${f.observed_at.slice(0,19).replace("T"," ")} UTC. ` +
      (data.issue_count ? `${data.issue_count} records are unavailable. ` : "");
  };
  async function request(url, controller) {
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(url, {method:"GET",credentials:"same-origin",mode:"same-origin",cache:"no-store",signal:controller.signal});
      if (!response.ok) {
        const error = new Error(response.status === 410 ? "This page expired. Refresh to see the latest records." : response.status === 401 ? "Your session expired. Sign in again." : "Research views are temporarily unavailable. Existing experiments continue independently.");
        error.status = response.status; throw error;
      }
      const data = await response.json();
      if (data.schema_version !== "read_model_v1" || !data.freshness?.generation) throw new Error("The saved view could not be verified.");
      return data;
    } finally { window.clearTimeout(timeout); }
  }
  const targets = {
    queue: ["queue-board","queue-status"], ledger:["ledger-items","ledger-status"], recipes:["signal-table-container","signal-library-status"]
  };
  function params(kind) {
    const q = new URLSearchParams({limit:"50"});
    if (kind === "ledger") for (const [id,key] of [["ledger-search","search"],["ledger-state","status"],["ledger-from","from"],["ledger-to","to"]]) {
      const value = $(id)?.value?.trim(); if (value) q.set(key,value);
    }
    return q;
  }
  function references(parent, value) {
    const d=node("details",undefined,"definition-panel"); d.append(node("summary","Exact saved references"),node("pre",JSON.stringify(value,null,2))); parent.append(d);
  }
  function trialCard(item) {
    const job=item.job, card=node("details",undefined,"ledger-card");
    const heading=node("summary");
    heading.append(node("strong",item.presentation?.title || "Saved experiment"),node("span",item.presentation?.subtitle || item.intent?.scope?.id || job.request_id),node("span",`${job.status} · ${job.updated_at.slice(0,19).replace("T"," ")} UTC`));
    card.append(heading,node("p",job.message));
    if (item.queue_position) card.append(node("p",`Waiting position ${item.queue_position}`));
    const table=node("table",undefined,"research-table"), head=node("tr");
    for (const title of ["Horizon · weekdays","P1","P2"]) head.append(node("th",title));
    table.append(head);
    for (const h of job.horizons || []) { const tr=node("tr"); for (const value of [h.horizon,h.p1_status,h.p2_status]) tr.append(node("td",String(value))); table.append(tr); }
    card.append(table);
    references(card,{request_id:job.request_id,intent:item.intent,provenance:item.provenance,event_sha256:job.event_sha256,results:job.results});
    return card;
  }
  function recipeCard(item, generation) {
    const card=node("article",undefined,"signal-card");
    card.append(node("h3",item.name),node("p",`${item.research.relationship_count} researched relationships · ${item.research.research_stage_pass_count} research-stage passes`),node("p",item.research.description,"field-note"),button("View researched relationships",()=>showBranches(item,generation)));
    return card;
  }
  function pager(kind, container, data) {
    const s=state.get(kind), nav=node("div",undefined,"queue-heading");
    if (s.index>0) nav.append(button("Previous page",()=>load(kind,s.index-1)));
    if (data.next_cursor) nav.append(button("Next page",()=> { s.cursors[s.index+1]=data.next_cursor; load(kind,s.index+1); }));
    nav.append(button("Refresh latest",()=>load(kind,0,true))); container.append(nav);
  }
  async function load(kind,index=0,reset=false) {
    let s=state.get(kind);
    if (!s) { s={cursors:[null],index:0,serial:0};state.set(kind,s); }
    s.controller?.abort(); s.controller=new AbortController(); const serial=++s.serial;
    if (reset) {s.cursors=[null];s.generation=null;} s.index=index;
    const [containerId,statusId]=targets[kind], container=$(containerId), status=$(statusId);
    if (!container || !status) return;
    const q=params(kind); if (s.cursors[index]) q.set("cursor",s.cursors[index]);
    else if (s.generation) q.set("generation",s.generation);
    container.setAttribute("aria-busy","true");
    try {
      const data=await request(prefix+kind+"?"+q,s.controller);
      if (serial!==s.serial) return;
      if (!Array.isArray(data.items) || !Number.isInteger(data.total)) throw new Error("Invalid saved view.");
      status.textContent=freshness(data)+`${data.items.length} shown of ${data.total}. `+(kind==="queue" ? "Recorded queue activity; worker liveness is not checked by this page." : "");
      container.replaceChildren();
      for (const item of data.items) container.append(kind==="recipes" ? recipeCard(item,data.freshness.generation) : trialCard(item));
      if (!data.items.length) container.append(node("p",data.issue_count ? "No verified records in this view. Some records are unavailable." : "No saved records in this view.","field-note"));
      pager(kind,container,data); s.data=data;s.generation=data.freshness.generation;
    } catch (error) {
      if (serial!==s.serial || error.name==="AbortError" && visible!==kind) return;
      status.textContent=(s.data ? "Showing the previous snapshot; current activity is unknown. " : "")+(error.name==="AbortError" ? "The view timed out. Please retry." : error.message);
      const retry=button("Refresh latest",()=>load(kind,0,true));
      if (!s.data) container.replaceChildren(retry);
      else if (error.status===410) container.append(retry);
    } finally {
      if (serial===s.serial) container.setAttribute("aria-busy","false");
      window.dispatchEvent(new CustomEvent("research-queue-settled",{detail:{verified:Boolean(s.data)}}));
    }
  }
  async function showBranches(recipe,generation,cursor=null) {
    selected?.controller.abort(); const controller=new AbortController();
    selected={recipe,generation,controller}; const identity=selected;
    const panel=$("signal-detail"), body=$("signal-detail-body"), status=$("signal-detail-status");
    panel.hidden=false; $("signal-detail-home").hidden=false; $("signal-detail-title").textContent=recipe.name;
    $("signal-catalog-view").hidden=true; status.textContent="Loading recorded relationships…";
    const q=new URLSearchParams({limit:"50"});
    if (generation && !cursor) q.set("generation",generation);
    if (cursor) q.set("cursor",cursor);
    try {
      const data=await request(prefix+"recipes/"+recipe.id+"/branches?"+q,controller);
      if (identity!==selected) return;
      status.textContent=freshness(data)+`${data.items.length} shown of ${data.total} evidence branches. Research-stage passes do not establish trading readiness.`;
      body.replaceChildren();
      for (const row of data.items) {
        const card=node("article",undefined,"queue-card");
        card.append(node("h3",`${row.scope.reference_currency || row.scope.id} · ${row.horizon} weekdays · ${row.expected_direction.toLowerCase()} hypothesis`),node("p",`P1: ${row.p1_status} · P2: ${row.p2_status}`),node("p",row.p2_evaluation_ran ? "P2 numerical evaluation completed." : "No completed P2 numerical evaluation is recorded for this branch."));
        if (row.p2_reason_codes.length) card.append(node("p",row.p2_reason_codes.join(" · ")));
        if (row.research_stage_pass) card.append(node("strong","Research-stage pass"));
        for (const trial of row.trial_results) card.append(button("View saved trial metadata",()=>showTrial(card,trial.id,data.freshness.generation)));
        references(card,row);body.append(card);
      }
      if (data.next_cursor) body.append(button("Next relationships",()=>showBranches(recipe,data.freshness.generation,data.next_cursor)));
      body.append(button("Refresh relationships",()=>showBranches(recipe,null)));
    } catch (error) { if (identity===selected) {status.textContent=error.message;body.replaceChildren(button("Retry",()=>showBranches(recipe,null)));} }
  }
  async function showTrial(card,id,generation) {
    const panel=node("div");card.append(panel);panel.textContent="Loading saved metadata…";
    try {
      const data=await request(prefix+"trial/"+id+"?generation="+generation,new AbortController());
      panel.replaceChildren(node("p",freshness(data)+"Stored metrics and decisions. Numerical evidence payloads are not loaded by this view."));
      references(panel,data.record);
    } catch (error) { panel.textContent=error.message; }
  }
  function navigate() {
    window.clearTimeout(timer);
    selected?.controller.abort();selected=null;
    $("signal-detail").hidden=true;$("signal-catalog-view").hidden=false;
    const hash=window.location.hash;
    visible=["#ledger","#ledger-page"].includes(hash) ? "ledger" : ["#signals","#signal-page"].includes(hash) ? "recipes" : "queue";
    for (const [kind,id] of [["queue","experiment-inputs"],["ledger","ledger-page"],["recipes","signal-page"]]) $(id).hidden=kind!==visible;
    for (const link of document.querySelectorAll("[data-page]")) {
      const active=link.dataset.page===(visible==="queue" ? "experiment" : visible==="recipes" ? "signals" : "ledger");
      if (active) link.setAttribute("aria-current","page"); else link.removeAttribute("aria-current");
    }
    const skip=document.querySelector(".skip-link"); if (skip) { skip.href=visible==="queue" ? "#experiment-inputs" : visible==="recipes" ? "#signal-page" : "#ledger-page"; skip.textContent="Skip to current research page"; }
    for (const [kind,s] of state) if (kind!==visible) s.controller?.abort();
    load(visible,0,true);
    if (visible==="queue") timer=window.setTimeout(poll,30000);
  }
  function poll() {
    if (!document.hidden && visible==="queue" && (state.get("queue")?.index || 0)===0) load("queue",0,true);
    timer=window.setTimeout(poll,30000);
  }
  $("queue-refresh").addEventListener("click",()=>load("queue",0,true));
  $("signal-library-retry").hidden=false;
  $("signal-library-retry").addEventListener("click",()=>load("recipes",0,true));
  $("signal-back").addEventListener("click",()=>{ selected?.controller.abort();selected=null;$("signal-detail").hidden=true;$("signal-catalog-view").hidden=false; });
  let searchTimer=null;
  for (const id of ["ledger-search","ledger-state","ledger-from","ledger-to"]) $(id).addEventListener("input",()=>{window.clearTimeout(searchTimer);searchTimer=window.setTimeout(()=>load("ledger",0,true),250);});
  $("ledger-clear").addEventListener("click",()=> { for (const id of ["ledger-search","ledger-state","ledger-from","ledger-to"]) $(id).value="";load("ledger",0,true); });
  window.addEventListener("hashchange",navigate);
  window.addEventListener("pagehide",()=>{window.clearTimeout(timer);window.clearTimeout(searchTimer);selected?.controller.abort();for(const s of state.values())s.controller?.abort();});
  window.addEventListener("pageshow",event=>{if(event.persisted)navigate();});
  navigate();
})();
