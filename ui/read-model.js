"use strict";

(() => {
  if (document.querySelector('meta[name="gambit-read-model"]')?.content !== "enabled") return;
  const $ = id => document.getElementById(id);
  const prefix = "/api/read-model/v1/";
  const state = new Map();
  let visible = null, timer = null, selected = null, activityController = null;
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
  async function request(url, controller, schema = "read_model_v1") {
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(url, {method:"GET",credentials:"same-origin",mode:"same-origin",cache:"no-store",signal:controller.signal});
      if (!response.ok) {
        const error = new Error(response.status === 410 ? "This page expired. Refresh to see the latest records." : response.status === 401 ? "Your session expired. Sign in again." : "Research views are temporarily unavailable. Existing experiments continue independently.");
        error.status = response.status; throw error;
      }
      const data = await response.json();
      if (data.schema_version !== schema || schema === "read_model_v1" && !data.freshness?.generation) throw new Error("The saved view could not be verified.");
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
  const words = value => ({succeeded:"Completed",p1:"P1",p2:"P2"})[value] || String(value || "Not recorded").replaceAll("_"," ").toLowerCase().replace(/^./,c=>c.toUpperCase());
  const badge = (value, scientific=false) => node("span",words(value),"research-badge " +
    (scientific && ["VALIDATED","admitted"].includes(value) ? "positive" : scientific && ["FAILED","rejected"].includes(value) ? "negative" : "neutral"));
  const stamp = value => value ? value.slice(0,19).replace("T"," ")+" UTC" : "not recorded";
  function trialCard(item) {
    const job=item.job, card=node("details",undefined,"ledger-card");
    const heading=node("summary");
    heading.append(node("strong",item.presentation?.title || "Saved experiment"),node("span",item.presentation?.subtitle || item.intent?.scope?.id || job.request_id),node("span",`${item.queue_position ? "Waiting #"+item.queue_position+" · " : ""}Execution: ${words(job.status)} · updated ${stamp(job.updated_at)}`));
    card.append(heading,node("p",job.message),node("p","Execution status describes the job. P1 and P2 below are its stored scientific outcomes.","field-note"));
    if (item.queue_position) card.append(node("p",`Waiting position ${item.queue_position}`));
    const table=node("table",undefined,"research-table"), head=node("tr");
    for (const title of ["Horizon · weekdays","P1","P2"]) head.append(node("th",title));
    table.append(head);
    for (const h of job.horizons || []) { const tr=node("tr"); tr.append(node("td",String(h.horizon))); for (const value of [h.p1_status,h.p2_status]) { const td=node("td");td.append(badge(value,true));tr.append(td); } table.append(tr); }
    card.append(table);
    references(card,{request_id:job.request_id,intent:item.intent,provenance:item.provenance,event_sha256:job.event_sha256,results:job.results});
    return card;
  }
  function recipeCard(item, generation) {
    const card=node("article",undefined,"signal-card");
    card.append(node("p","RESEARCHED RECIPE","research-label"),node("h3",item.name));
    const counts=node("div",undefined,"recipe-counts");
    for(const [label,value] of [["Researched relationships",item.research.relationship_count],["Research-stage passes",item.research.research_stage_pass_count]]) {
      const cell=node("div");cell.append(node("strong",String(value)),node("span",label));counts.append(cell);
    }
    card.append(counts,node("p",`P1 admitted: ${item.research.p1_counts?.admitted ?? 0} saved results · P2 failed: ${item.research.p2_counts?.FAILED ?? 0} saved results`,"field-note"),node("p",item.research.description,"field-note"),button("View researched relationships",()=>showBranches(item,generation)));
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
      status.textContent=freshness(data)+`${data.items.length} shown of ${data.total}. `+(kind==="queue" ? "Queue counts and order belong to this snapshot; live activity is shown separately." : "");
      container.replaceChildren();
      container.className=kind==="recipes" ? "read-model-recipes" : "read-model-records";
      if(kind==="queue") {
        const activity=node("section",undefined,"research-panel live-activity");container.append(activity);
        loadActivity(activity,data);
        const counts=data.status_counts||{};
        container.append(node("h3",`${counts.queued ?? "—"} waiting · saved queue`),node("p",data.status_counts ? `Recorded stages: preparation ${(counts.preparing||0)+(counts.resolving||0)} · P1 ${counts.p1||0} · P2 ${counts.p2||0}. Ordered by the stored queue; snapshot states may lag the current worker.` : "Recorded stage counts unavailable.","field-note"));
      }
      for (const item of data.items) container.append(kind==="recipes" ? recipeCard(item,data.freshness.generation) : trialCard(item));
      if (!data.items.length) container.append(node("p",data.issue_count ? "No verified records in this view. Some records are unavailable." : "No saved records in this view.","field-note"));
      pager(kind,container,data); s.data=data;s.generation=data.freshness.generation;
    } catch (error) {
      if (serial!==s.serial || error.name==="AbortError" && visible!==kind) return;
      status.textContent=(s.data ? "Showing the previous snapshot; current activity is unknown. " : "")+(error.name==="AbortError" ? "The view timed out. Please retry." : error.message);
      const retry=button("Refresh latest",()=>load(kind,0,true));
      if (!s.data) container.replaceChildren(retry);
      else if (error.status===410) container.append(retry);
      if(kind==="queue") {
        let activity=container.querySelector?.(".live-activity");
        if(!activity) {activity=node("section",undefined,"research-panel live-activity");container.append(activity);}
        loadActivity(activity,s.data||{items:[]});
      }
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
      const picker=node("select");picker.setAttribute("aria-label","Exact saved result");
      const contextKey=row=>JSON.stringify([row.scope,row.mode,row.expected_direction,row.target_family]);
      const contexts=[...new Map(data.items.map(row=>[contextKey(row),row])).entries()];
      const context=node("select");context.setAttribute("aria-label","Scope · hypothesis · target");
      for(const [key,row] of contexts) {const opt=node("option",`${row.scope_label || row.scope.id} · ${words(row.expected_direction)} · ${words(row.target_family)}`);opt.value=key;context.append(opt);}
      context.value=contexts[0]?.[0]||"";
      const contextLabel=node("label","Scope · hypothesis · target","research-control");contextLabel.append(context);
      const horizonButtons=node("div",undefined,"research-segments");
      const horizonLabel=node("div",undefined,"research-control");horizonLabel.append(node("span","Forecast horizon · scheduled weekdays","research-label"),horizonButtons);
      const controls=node("div",undefined,"research-controls");controls.append(contextLabel,horizonLabel);body.append(controls);
      const resultLabel=node("label","Exact saved result","research-control");resultLabel.append(picker);body.append(resultLabel);
      const evidence=node("div");body.append(evidence);let selection=0,chosenHorizon=null;
      function selectContext() {
        const family=data.items.filter(row=>contextKey(row)===context.value);
        if(!family.some(row=>row.horizon===chosenHorizon))chosenHorizon=family[0]?.horizon;
        horizonButtons.replaceChildren();
        for(const h of [1,7,21,63,252]) {const b=button(String(h),()=>{chosenHorizon=h;selectContext();});b.className="research-button";b.disabled=!family.some(row=>row.horizon===h);b.setAttribute("aria-pressed",String(h===chosenHorizon));horizonButtons.append(b);}
        const choices=data.items.map((row,index)=>({row,index})).filter(x=>contextKey(x.row)===context.value&&x.row.horizon===chosenHorizon);
        picker.replaceChildren();
        choices.forEach(({row,index},position)=>{const opt=node("option",`Saved result ${position+1} · P1 ${words(row.p1_status)} / P2 ${words(row.p2_status)} · ${(row.projection?.id||row.relationship?.id||"").slice(-10)}`);opt.value=String(index);picker.append(opt);});
        picker.value=String(choices[0]?.index ?? "");resultLabel.hidden=choices.length<2;
        choose();
      }
      async function choose() {
        const choice=++selection,row=data.items[Number(picker.value)||0];
        window.SignalResearch?.cancel();evidence.replaceChildren();if(!row)return;
        evidence.append(node("p",row.p2_evaluation_ran ? "P2 numerical evaluation completed." : "No completed P2 numerical evaluation is recorded for this branch.","field-note"));
        if(row.research_stage_pass)evidence.append(badge("Research-stage pass"));
        if(!window.SignalResearch) {references(evidence,row);return;}
        const source={
          load:async signal=>{
            const linked=new AbortController();signal.addEventListener("abort",()=>linked.abort(),{once:true});
            controller.signal.addEventListener("abort",()=>linked.abort(),{once:true});
            if(signal.aborted||controller.signal.aborted)linked.abort();
            const refs=[...(row.trial_results||[]).map(r=>["trial",r]),...(row.validation_results||[]).map(r=>["decision",r])];
            if(refs.length>8)throw new Error("Too many result references");
            const records=await Promise.all(refs.map(async([kind,ref])=>{
              const d=await request(prefix+kind+"/"+ref.id+"?generation="+data.freshness.generation,linked);
              // The server verifies the reference closure in this pinned generation.
              if(d.record.id!==ref.id || d.record.version!==ref.version || d.authority?.content_sha256!==ref.content_sha256)throw new Error("Reference mismatch");
              return [kind,ref,d.record];
            }));
            if(choice!==selection||identity!==selected)throw new Error("Selection changed");
            const results=records.filter(([kind])=>kind==="trial").map(([,authority,t])=>({authority,...t.body,period:t.scientific_key.period,research_spec:t.scientific_key.research_spec}));
            const validations=records.filter(([kind])=>kind==="decision").map(([,authority,t])=>({authority,...t.body}));
            return {recipe_id:recipe.id,relationships:[{...row,results,validations}],issues:[]};
          },
          evidence:async(authority,signal)=>{
            const linked=new AbortController();signal.addEventListener("abort",()=>linked.abort(),{once:true});
            controller.signal.addEventListener("abort",()=>linked.abort(),{once:true});
            if(signal.aborted||controller.signal.aborted)linked.abort();
            return request(prefix+"evidence/"+authority.id+"?generation="+data.freshness.generation,linked);
          }
        };
        window.SignalResearch.mount(evidence,{recipe:{id:recipe.id}},source);
      }
      picker.addEventListener("change",choose);context.addEventListener("change",()=>{chosenHorizon=null;selectContext();});selectContext();
      if (data.next_cursor) body.append(button("Next relationships",()=>showBranches(recipe,data.freshness.generation,data.next_cursor)));
      body.append(button("Refresh relationships",()=>showBranches(recipe,null)));
    } catch (error) { if (identity===selected) {status.textContent=error.message;body.replaceChildren(button("Retry",()=>showBranches(recipe,null)));} }
  }
  async function loadActivity(panel,snapshot) {
    activityController?.abort();const controller=new AbortController();activityController=controller;
    panel.replaceChildren(node("h3","Current research"),node("p","Checking the worker…"));
    try {
      const data=await request(prefix+"activity",controller,"live_activity_v1");
      if(controller!==activityController||visible!=="queue")return;
      panel.replaceChildren(node("h3","Current research"),node("p",`Worker: ${words(data.worker.state)} · checked ${stamp(data.observed_at)}`));
      if(!data.active) {
        panel.append(node("p",data.activity_unavailable || data.worker.state==="unknown" ? "Current experiment cannot be verified. The queue below is a saved snapshot." : "No active experiment was observed at this checkpoint."));return;
      }
      const active=data.active;
      const saved=snapshot.items.find(x=>x.job.request_id===active.request_id);
      let item=saved;
      if(!item && snapshot.freshness?.generation)try{item=(await request(prefix+"experiment/"+active.request_id+"?generation="+snapshot.freshness.generation,controller)).record;}catch(_){}
      if(controller!==activityController||visible!=="queue")return;
      panel.append(node("h4",item?.presentation?.title || "Active experiment"),node("p",item?.presentation?.subtitle || active.request_id),badge(active.status),node("p",active.message),node("p",`Stage updated ${stamp(active.updated_at)}`,"field-note"));
      const prep=active.preparation;
      if(prep && prep.state!=="complete") panel.append(node("p",`${prep.phase || ""} preparation · ${prep.members_completed ?? "—"} of ${prep.members_total ?? "—"} members · ${prep.batches_completed ?? "—"} batches completed`));
      references(panel,{request_id:active.request_id,attempt_id:active.attempt_id,event_sha256:active.event_sha256,observed_at:data.observed_at});
    } catch(_) {if(controller===activityController)panel.replaceChildren(node("h3","Current research"),node("p","Live worker activity is unavailable. Saved queue records below do not establish current activity."));}
  }
  function navigate() {
    window.clearTimeout(timer);
    selected?.controller.abort();selected=null;window.SignalResearch?.cancel();activityController?.abort();
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
    if (!document.hidden && visible==="queue") {
      const saved=state.get("queue");
      if((saved?.index||0)===0)load("queue",0,true);
      else {const activity=$("queue-board").querySelector?.(".live-activity");if(activity)loadActivity(activity,saved.data||{items:[]});}
    }
    timer=window.setTimeout(poll,30000);
  }
  $("queue-refresh").addEventListener("click",()=>load("queue",0,true));
  $("signal-library-retry").hidden=false;
  $("signal-library-retry").addEventListener("click",()=>load("recipes",0,true));
  $("signal-back").addEventListener("click",()=>{ selected?.controller.abort();selected=null;window.SignalResearch?.cancel();$("signal-detail").hidden=true;$("signal-catalog-view").hidden=false; });
  let searchTimer=null;
  for (const id of ["ledger-search","ledger-state","ledger-from","ledger-to"]) $(id).addEventListener("input",()=>{window.clearTimeout(searchTimer);searchTimer=window.setTimeout(()=>load("ledger",0,true),250);});
  $("ledger-clear").addEventListener("click",()=> { for (const id of ["ledger-search","ledger-state","ledger-from","ledger-to"]) $(id).value="";load("ledger",0,true); });
  window.addEventListener("hashchange",navigate);
  window.addEventListener("pagehide",()=>{window.clearTimeout(timer);window.clearTimeout(searchTimer);activityController?.abort();window.SignalResearch?.cancel();selected?.controller.abort();for(const s of state.values())s.controller?.abort();});
  window.addEventListener("pageshow",event=>{if(event.persisted)navigate();});
  // Put observation first while retaining the existing contract reference below.
  const activityPage=$("experiment-inputs"),queueSection=$("trial-queue");
  if(activityPage?.prepend && queueSection) {activityPage.prepend(queueSection);queueSection.className+=" read-model-activity-top";}
  const queueLink=document.querySelector('[data-page="experiment"]');if(queueLink)queueLink.textContent="Trial queue";
  navigate();
})();
