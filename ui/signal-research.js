"use strict";

// Read-only presentation of exact saved relationships. No preparation or Submit calls.
(() => {
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  const numeric = value => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  const format = (value, digits = 3, signed = false) => {
    if (!numeric(value)) return "—";
    const n = Number(value);
    if (n !== 0 && Math.abs(n) < 0.001) return `${signed && n > 0 ? "+" : ""}${n.toExponential(2)}`;
    return n.toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay: signed ? "exceptZero" : "auto"});
  };
  const integer = value => numeric(value) ? Number(value).toLocaleString() : "—";
  const words = value => String(value || "Unavailable").replaceAll("_", " ").toLowerCase().replace(/^./, c => c.toUpperCase());
  const fullMode = mode => mode === "CS" ? "Cross-sectional" : "Time-series";
  const targetName = value => value === "price_return" ? "Price Return" : words(value);
  const exact = (a, b) => a && b && a.id === b.id && a.version === b.version && a.content_sha256 === b.content_sha256;
  const tone = value => ["pass", "validated", "admitted"].includes(String(value).toLowerCase()) ? "positive" :
    ["fail", "failed", "rejected"].includes(String(value).toLowerCase()) ? "negative" : "neutral";
  const status = value => ({not_admitted: "Not admitted", not_run: "Not run", VALIDATED: "Validated", FAILED: "Failed", UNRESOLVED: "Unresolved"})[value] || words(value);
  const contextKey = r => JSON.stringify([r.scope, r.mode, r.target_family, r.expected_direction,
    r.results.find(t => t.stage === "P1")?.research_spec || r.results[0]?.research_spec || r.validations?.[0]?.research_spec]);
  let cancelCurrent = () => {};
  function button(label, onClick, cls = "research-button") {
    const b = node("button", label, cls); b.type = "button"; b.addEventListener("click", onClick); return b;
  }
  function panel(title, cls = "") { const p = node("section", undefined, `research-panel ${cls}`); p.append(node("h3", title)); return p; }
  function note(text, cls = "") { return node("p", text, `research-caption ${cls}`); }
  function kv(parent, rows) {
    const list = node("dl", undefined, "research-values");
    for (const [label, value, color] of rows) {
      const row = node("div"); row.append(node("dt", label), node("dd", value, color ? `ink-${color}` : undefined)); list.append(row);
    }
    parent.append(list);
  }
  function metric(label, value, caption, color = "", dark = false) {
    const p = panel(label, `headline-metric ${dark ? "dark-panel" : ""}`);
    p.append(node("div", value, `metric-value ${color ? `ink-${color}` : ""}`), note(caption)); return p;
  }
  function jsonDetails(label, value) {
    const d = node("details", undefined, "research-provenance");
    d.append(node("summary", label), node("pre", JSON.stringify(value, null, 2))); return d;
  }
  function bar(parent, label, value, max, caption, color) {
    const b = node("div", undefined, "research-bar");
    const heading = node("div"); heading.append(node("span", label), node("strong", format(value, 3, true), `ink-${color}`));
    const meter = svg("svg", {viewBox:"0 0 200 12",role:"img","aria-label":`${label}: ${format(value,3,true)}; zero at centre`,class:`signed-bar bar-${color}`});
    const width=numeric(value) ? 98*Math.abs(Number(value))/(max||1) : 0;
    meter.append(svg("line",{x1:100,x2:100,y1:0,y2:12,stroke:"currentColor"}));
    if(numeric(value))meter.append(svg("rect",{x:Number(value)<0 ? 100-width : 100,y:3,width,height:6,fill:"currentColor"}));
    b.append(heading, meter, note(caption)); parent.append(b);
  }
  function checklist(evidence, stage) {
    const p = panel(stage === "P1" ? "Admission checklist" : "Validation evidence");
    const names = {execution_completed: "Execution sufficiency", absolute_hac_t: "Absolute HAC t-statistic", sign_stability: "Sign stability",
      absolute_mean_ic: "Absolute mean IC", discovery_direction: "Discovery direction", sample_sufficiency: "Sample sufficiency",
      direction: "Validation direction", magnitude: "Magnitude retention", inference: "Inference", stability: "Stability"};
    if (!evidence || !Object.keys(evidence).length) p.append(note("Evidence was not recorded for this stage."));
    else for (const [key, e] of Object.entries(evidence)) {
      kv(p, [[names[key] || words(key), words(e.status), tone(e.status)]]);
      if (e.minimum !== undefined && e.minimum !== null) p.append(note(`Required minimum: ${format(e.minimum, Number.isInteger(Number(e.minimum)) ? 0 : 3)}`, "criterion-minimum"));
    }
    return p;
  }
  function svg(tag, attrs = {}, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function plot(chart, result, blocks) {
    const isCS = chart.kind === "cumulative_rank_ic";
    const p = panel(isCS ? "Cumulative rank IC over time" : "Forward return vs predictor", "research-chart-panel");
    if (!chart.available || !chart.points.length) { p.append(note("No verified chart observations are available for this trial.")); return p; }
    const points = chart.points.map(row => ({x: isCS ? Date.parse(row.x) : Number(row.x), y: Number(row.y), date: row.date}));
    const xs = points.map(row => row.x), ys = points.map(row => row.y);
    let xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(0, ...ys), ymax = Math.max(0, ...ys);
    const m = result.metrics;
    const regression = !isCS && numeric(m.alpha) && numeric(m.predictive_coefficient ?? m.primary_effect);
    const beta = Number(m.predictive_coefficient ?? m.primary_effect), alpha = Number(m.alpha);
    if (regression) { ymin = Math.min(ymin, alpha + beta*xmin, alpha + beta*xmax); ymax = Math.max(ymax, alpha + beta*xmin, alpha + beta*xmax); }
    if (xmin === xmax) { xmin -= 1; xmax += 1; } if (ymin === ymax) { ymin -= 1; ymax += 1; }
    const padding = (ymax-ymin)*0.09; ymin -= padding; ymax += padding;
    const x = value => 64 + 650*(value-xmin)/(xmax-xmin), y = value => 244-212*(value-ymin)/(ymax-ymin);
    const graphic = svg("svg", {viewBox: "0 0 740 295", role: "img", "aria-label": isCS ? "Cumulative sum of stored daily rank IC, on actual dates" : "Stored Feature and future return observations with the saved regression"});
    graphic.append(svg("title", {}, isCS ? "Cumulative rank IC; not portfolio returns" : "Forward return versus Feature value"));
    if (isCS) for (const [i, block] of blocks.entries()) {
      if (i % 2 === 0 && block.start && block.end) graphic.append(svg("rect", {x:x(Date.parse(block.start)),y:24,width:Math.max(0,x(Date.parse(block.end))-x(Date.parse(block.start))),height:220,fill:"var(--g-quiet)"}));
    }
    for (const v of [ymin + padding, 0, ymax-padding]) {
      graphic.append(svg("line", {x1:64,x2:714,y1:y(v),y2:y(v),stroke:"var(--g-border)"}), svg("text", {x:55,y:y(v)+4,"text-anchor":"end",class:"chart-label"},format(v, 2)));
    }
    if (isCS) graphic.append(svg("polyline", {points:points.map(p => `${x(p.x)},${y(p.y)}`).join(" "),fill:"none",stroke:"var(--g-link)","stroke-width":2.5}));
    else {
      for (const p of points) graphic.append(svg("circle", {cx:x(p.x),cy:y(p.y),r:2.3,fill:"var(--g-muted)","fill-opacity":0.32}));
      if (regression) graphic.append(svg("line", {x1:x(xmin),x2:x(xmax),y1:y(alpha+beta*xmin),y2:y(alpha+beta*xmax),stroke:"var(--g-ink)","stroke-width":2.5}));
    }
    graphic.append(svg("text", {x:64,y:268,class:"chart-label"},isCS ? chart.points[0].date : format(xmin)),
      svg("text", {x:714,y:268,"text-anchor":"end",class:"chart-label"},isCS ? chart.points[chart.points.length-1].date : format(xmax)),
      svg("text", {x:390,y:290,"text-anchor":"middle",class:"chart-label"},isCS ? "Date · cumulative sum of raw rank IC" : "Feature value"));
    p.append(graphic, note(isCS ? `Every usable IC contributes to the cumulative sum. ${integer(chart.display_count)} of ${integer(chart.total_count)} points displayed${chart.display_count < chart.total_count ? " (deterministic thinning)" : ""}. Shading follows saved blocks. This is not an investment return curve.` :
      `${integer(chart.display_count)} of ${integer(chart.total_count)} usable observations shown${chart.display_count < chart.total_count ? " (deterministic display sample)" : ""}. The line uses the saved full-sample regression.`));
    return p;
  }

  function mount(host, entry, source = null) {
    cancelCurrent();
    const controller = new AbortController(); let alive = true, version = 0, relationships = [], issues = [], selectedContext = null, horizon = 1, stage = "P1", branch = 0;
    const cache = new Map();
    cancelCurrent = () => { alive = false; controller.abort(); };
    const root = node("div", undefined, "feature-research"); host.append(root);
    const recipe = entry.recipe || entry.signal?.feature;
    async function request(url) {
      const child = new AbortController(), abort = () => child.abort();
      controller.signal.addEventListener("abort", abort, {once:true});
      const timer = window.setTimeout(abort, 5000);
      try {
        const response = await fetch(url, {method:"GET",mode:"same-origin",credentials:"same-origin",cache:"no-store",signal:child.signal});
        if (!response.ok) throw new Error("Unavailable"); return await response.json();
      } finally { window.clearTimeout(timer); controller.signal.removeEventListener("abort", abort); }
    }
    function selector(label, options, value, change) {
      const wrap = node("div", undefined, "research-control"); const select = node("select");
      select.setAttribute("aria-label",label);
      for (const [v,t] of options) { const o=node("option",t);o.value=v;select.append(o); } select.value=value;
      select.addEventListener("change", () => change(select.value));wrap.append(node("span",label,"research-label"),select);return wrap;
    }
    function evidenceTable(parent, result, role) {
      const area = node("div",undefined,"research-evidence-table"); parent.replaceChildren(area);
      let pageVersion=0;
      async function page(offset) {
        const current=++pageVersion; area.replaceChildren(note("Verifying stored evidence…"));
        try {
          const data=await request(`/api/trial-evidence/${result.authority.id}?role=${role}&offset=${offset}`);
          if (!alive || current!==pageVersion) return;
          if (!exact(data.authority,result.authority) || data.role!==role || data.offset!==offset || !Array.isArray(data.rows)) throw new Error("Evidence mismatch");
          const keys=role==="cross_sectional_ic_history" ? ["date","rank_ic","instrument_count"] : ["date","instrument","feature","target","target_entry","target_end","exclusion_reason"];
          const wrap=node("div",undefined,"table-scroll"), table=node("table",undefined,"signal-table");
          const header=node("tr");for(const key of keys) header.append(node("th",words(key)));header.append(node("th","Record"));const head=node("thead");head.append(header);
          const body=node("tbody");for(const row of data.rows) {const tr=node("tr");for(const key of keys) tr.append(node("td",String(row[key] ?? (key==="date" ? row.anchor_date : null) ?? "—")));
            const td=node("td");td.append(jsonDetails("Lineage & full row",row));tr.append(td);body.append(tr);}
          table.append(head,body);wrap.append(table);
          const actions=node("div",undefined,"research-actions");const prev=button("Previous",()=>page(Math.max(0,offset-100))),next=button("Next",()=>page(offset+100));
          prev.disabled=offset===0;next.disabled=offset+data.rows.length>=data.total;actions.append(prev,note(data.available ? `${integer(offset + (data.rows.length ? 1 : 0))}–${integer(offset+data.rows.length)} of ${integer(data.total)} saved rows` : "Evidence was not recorded"),next);
          area.replaceChildren(actions,wrap);
        } catch(error) { if(alive && current===pageVersion) area.replaceChildren(note("Evidence could not be verified."),button("Retry evidence",()=>page(offset))); }
      }
      page(0);
    }
    function render() {
      const token=++version;root.replaceChildren();
      if (issues.length) {
        const warning=panel("Some research records are unavailable", "research-warning");
        warning.append(note("Some saved records could not be verified. Verified results are shown; unavailable records have not been changed."),
          button("Retry research",load),jsonDetails("Unavailable record references",issues));
        root.append(warning);
      }
      const contexts=[...new Map(relationships.map(r=>[contextKey(r),r])).entries()];
      if (!contexts.length) {
        const empty=panel(issues.length ? "Research verification incomplete" : "No saved research", "research-empty");
        empty.append(node("h4",issues.length ? "No verified results available" : "No research results yet"),
          note(issues.length ? "Saved records could not be verified. Retry to check them again; this does not mean that no research was performed." :
            "No verified research records are available for this Signal. Preparing observations alone does not count as a test."));root.append(empty);return;
      }
      if (!contexts.some(([key])=>key===selectedContext)) selectedContext=contexts[0][0];
      const family=relationships.filter(r=>contextKey(r)===selectedContext);
      if (!family.some(r=>r.horizon===horizon)) horizon=family[0].horizon;
      const candidates=family.filter(r=>r.horizon===horizon);branch=Math.min(branch,candidates.length-1);const relationship=candidates[branch];
      const result=relationship.results.find(r=>r.stage===stage);
      const controls=node("div",undefined,"research-controls");
      if(!source) controls.append(selector("Scope · hypothesis",contexts.map(([key,r])=>[key,`${r.scope_label || r.scope.id} · ${fullMode(r.mode)} · ${words(r.expected_direction)} · ${targetName(r.target_family)} · Spec v${r.results[0]?.research_spec?.version || "—"}`]),selectedContext,value=>{selectedContext=value;branch=0;render();}));
      const horizons=node("div",undefined,"research-control");horizons.append(node("span","Forecast horizon · scheduled weekdays","research-label"));const hbuttons=node("div",undefined,"research-segments");
      for(const value of [1,7,21,63,252]) {const b=button(String(value),()=>{horizon=value;branch=0;render();});b.disabled=!family.some(r=>r.horizon===value);b.setAttribute("aria-pressed",String(horizon===value));b.title=b.disabled ? "No saved research for this horizon" : `${value}-day forecast horizon (scheduled weekdays)`;hbuttons.append(b);}horizons.append(hbuttons);
      const periods=node("div",undefined,"research-control");periods.append(node("span","Research period","research-label"));const pbuttons=node("div",undefined,"research-segments");
      for(const [value,label] of [["P1","P1 Discovery"],["P2","P2 Validation"]]) {const b=button(label,()=>{stage=value;render();});b.setAttribute("aria-pressed",String(stage===value));pbuttons.append(b);}periods.append(pbuttons);if(!source)controls.append(horizons);controls.append(periods);root.append(controls);
      if(candidates.length>1) root.append(selector("Saved research result",candidates.map((r,i)=>[String(i),`Saved result ${i + 1} · ${r.results[0]?.period?.start_inclusive || "—"} – ${r.results[0]?.period?.end_exclusive || "—"}`]),String(branch),v=>{branch=Number(v);render();}));
      const badges=node("div",undefined,"research-context");
      badges.append(node("span",`P1 ${status(relationship.p1_status)}`,`research-badge ${tone(relationship.p1_status)}`),node("span",`P2 ${status(relationship.p2_status)}`,`research-badge ${tone(relationship.p2_status)}`),
        note(`${fullMode(relationship.mode)} · ${targetName(relationship.target_family)} · ${horizon}-day forecast horizon · Expected relationship: ${words(relationship.expected_direction)}`));root.append(badges);
      const hypothesis=(relationship.mode === "CS" ? "Across instruments within each date: " : "Over time for this instrument: ") + (relationship.expected_direction==="NEGATIVE" ? "Higher Feature values are hypothesized to correspond to lower Target returns." : "Higher Feature values are hypothesized to correspond to higher Target returns.");
      root.append(note(hypothesis));
      if(!result) {
        const validation=relationship.validations?.find(v=>v.evaluation_trial===null);
        const empty=panel(stage === "P2" && validation ? `P2 ${status(validation.decision)} · before validation evaluation` : `${stage} has no saved evaluation`);
        empty.append(note(stage === "P2" && validation ? "The discovery precheck stopped this relationship before a P2 evaluation trial was run. No validation-period statistics are available." : relationship.p1_status === "rejected" ? "P1 did not admit this relationship to P2." : "No authoritative trial statistics are stored for this stage."));
        if(validation?.reason_codes?.length) empty.append(note(validation.reason_codes.map(words).join(" · ")));
        empty.append(jsonDetails("Authoritative relationship and decisions",relationship));root.append(empty);return;
      }
      root.append(note(`${stage} · ${result.period?.start_inclusive || "Not recorded"} – ${result.period?.end_exclusive || "Not recorded"} (end exclusive) · Research Spec v${result.research_spec?.version || "—"} · Execution: ${status(result.execution_status)}`,"research-period"));
      const m=result.metrics||{},s=result.sample||{},e=result.evidence||{},isCS=relationship.mode==="CS",isP2=stage==="P2";
      const required=Object.values(e).filter(row=>row.status!=="diagnostic"),passes=required.filter(row=>row.status==="pass").length;
      const headlines=node("div",undefined,"research-headlines");
      headlines.append(metric(isCS ? `${isP2 ? "Validation " : ""}mean rank IC` : `${isP2 ? "Validation " : ""}predictive coefficient β`,format(m.primary_effect,3,true),
        isP2 ? `Discovery effect ${format(m.raw_discovery_effect,3,true)}` : isCS ? `Median ${format(m.median_rank_ic,3,true)} across usable dates` : `α ${format(m.alpha,3,true)} · Spearman IC ${format(m.time_series_spearman_ic,3,true)}`,isP2 ? tone(e.direction?.status) : ""),
        metric(isP2 ? "Directional HAC t" : "HAC t-statistic",format(isP2 ? m.directional_hac_t_statistic : m.hac_t_statistic,2),isP2 ? `One-sided p ${format(m.directional_p_value)}` : `SE ${format(m.hac_standard_error)} · ${integer(m.hac_maxlags)} lags`,tone((isP2 ? e.inference : e.absolute_hac_t)?.status)),
        metric(isP2 ? "Effect retention" : "Sign stability",isP2 ? format(m.effect_retention_ratio,2) : `${integer(e.sign_stability?.observed)} matching`,isP2 ? "Oriented P2 ÷ oriented P1" : "Blocks matching the full-sample sign",tone((isP2 ? e.magnitude : e.sign_stability)?.status)),
        metric(isP2 ? "Validation outcome" : "Admission evidence",isP2 ? status(relationship.p2_status) : required.length ? `${passes} of ${required.length} met` : "—",isP2 ? `${passes} of ${required.length} required evidence checks met` : "P1 admission retains a candidate. It is not validation.","",true));root.append(headlines);
      const chartRow=node("div",undefined,"research-chart-row");chartRow.append(panel("Loading verified chart and block evidence…"));root.append(chartRow);
      const middle=node("div",undefined,"research-three-column");
      if(isP2) {
        const robust=panel("Leave-one-block-out");robust.dataset.role="robustness";middle.append(robust);
        const effective=panel("Effective sample size");effective.append(node("div",integer(s.effective_observation_count),"metric-value"),note(`${integer(s.minimum_effective_observations)} required · maximum non-overlapping Target intervals`));
        effective.append(note(`Validation data accessed: ${s.validation_data_accessed === true ? "Yes" : s.validation_data_accessed === false ? "No" : "Not recorded"}`));middle.append(effective);
      } else if(isCS) {
        const frequency=panel("Daily IC direction");kv(frequency,[["Positive dates",numeric(m.positive_ic_frequency) ? `${format(Number(m.positive_ic_frequency)*100,1)}%` : "—"],["Negative dates",numeric(m.negative_ic_frequency) ? `${format(Number(m.negative_ic_frequency)*100,1)}%` : "—"]]);
        frequency.append(note("Share of usable dates. Zero IC dates can make these shares total less than 100%."));middle.append(frequency);
      } else {const regression=panel("Regression");kv(regression,[["Predictive coefficient β",format(m.predictive_coefficient,3,true)],["Intercept α",format(m.alpha,3,true)],["Spearman IC",format(m.time_series_spearman_ic,3,true)]]);middle.append(regression);}
      if(!isP2) {const inference=panel("Inference");kv(inference,[["HAC standard error",format(m.hac_standard_error)],["HAC t-statistic",format(m.hac_t_statistic,2)],["HAC lag count",integer(m.hac_maxlags)],["Statistical clock",m.hac_clock||"Not recorded"]]);middle.append(inference);}
      middle.append(checklist(e,stage));root.append(middle);
      if(isP2) {
        const comparison=panel("Discovery to validation","research-comparison");const max=Math.max(Math.abs(Number(m.oriented_discovery_effect)||0),Math.abs(Number(m.oriented_validation_effect)||0));
        bar(comparison,"P1 effect, oriented",m.oriented_discovery_effect,max,"", "neutral");bar(comparison,"P2 effect, oriented",m.oriented_validation_effect,max,"",tone(e.direction?.status));
        kv(comparison,[["Retention",format(m.effect_retention_ratio,2)],["Directional p",format(m.directional_p_value)],["HAC standard error",format(m.hac_standard_error)]]);
        if(result.reason_codes?.length) comparison.append(note(result.reason_codes.map(words).join(" · "),"research-warning"));
        if(result.confidence_flags?.length) comparison.append(note(result.confidence_flags.map(words).join(" · "),"research-warning"));
        const fdr=result.fdr_diagnostics;
        if(fdr) comparison.append(note(fdr.family_size===1 ? `Benjamini–Hochberg diagnostic: one relationship in this family. Adjusted p ${format(fdr.adjusted_p_value)} equals the raw p-value. This is not a correction across all tested Features.` : `Multiple-testing diagnostic: family size ${integer(fdr.family_size)}; adjusted p ${format(fdr.adjusted_p_value)}.`,"research-warning"));
        root.append(comparison);
      }
      const sample=panel("Sample & supporting records","research-sample");
      kv(sample,[["Usable dates",integer(s.usable_date_count)],["Instrument-date rows",integer(s.usable_pair_count)],["Incomplete dates",integer(Array.isArray(s.incomplete_dates)?s.incomplete_dates.length:s.incomplete_dates)],["Exclusions",integer(s.excluded_pair_count)]]);
      const scheduled=note("Missing scheduled periods: verifying…");sample.append(scheduled);
      const rowsHost=node("div"),actions=node("div",undefined,"research-actions");
      for(const [role,label] of (source ? [] : [["aligned_sample","Aligned observations"],["observation_exclusions","Excluded observations"],...(isCS ? [["cross_sectional_ic_history","IC history"]] : [])])) actions.append(button(label,()=>evidenceTable(rowsHost,result,role)));
      if(source) sample.append(note("Charts are prepared separately from saved evidence. Numerical observation downloads are not loaded by these pages."));
      sample.append(actions,rowsHost,jsonDetails("Sample coverage & members",s),jsonDetails("Exact trial, relationship & lineage references",{recipe,relationship:relationship.relationship,scope:relationship.scope,projection:relationship.projection,trial:result.authority,research_spec:result.research_spec,period:result.period,artifacts:result.artifact_manifests,validations:relationship.validations}));root.append(sample);
      root.append(note(isP2 ? "Outcomes apply only to this Scope, Target, horizon, hypothesis and saved result. Unavailable values are shown as —, never zero." : "P1 applies no multiple-testing adjustment and stores no p-value. Unavailable values are shown as —, never zero.","research-footnote"));
      async function loadEvidence() {
        try {
          let data=cache.get(result.authority.id);
          if(!data) {data=source ? await source.evidence(result.authority,controller.signal) : await request(`/api/trial-evidence/${result.authority.id}`);if(!exact(data.authority,result.authority)||!data.chart||!data.artifacts)throw new Error("Evidence mismatch");cache.set(result.authority.id,data);}
          if(!alive||token!==version)return;
          const a=data.artifacts,blocks=isP2 ? a.blocks||[] : a.stability?.subperiods||[], effects=panel("Effect by block");
          const values=blocks.map(b=>isP2 ? b.oriented_effect : b.primary_statistic),max=Math.max(...values.map(v=>Math.abs(Number(v)||0)),0);
          for(const [i,b] of blocks.entries()) {
            const match=isP2 ? b.expected_sign : b.statistic_sign && b.statistic_sign===a.stability?.full_sample_sign;
            bar(effects,`Block ${i+1}`,values[i],max,`${b.start||"—"} – ${b.end||"—"} · ${integer(b.observation_count)} rows · ${isP2 ? "oriented effect" : "raw effect"} · ${numeric(values[i]) ? match ? isP2 ? "matches hypothesis" : "matches full-sample sign" : isP2 ? "does not match hypothesis" : "differs from full-sample sign" : "unavailable"}`,numeric(values[i]) ? match ? "positive" : "negative" : "neutral");
          }
          if(!blocks.length)effects.append(note("Block evidence was not recorded."));
          const chartPanel=plot(data.chart,result,blocks);
          if(source)chartPanel.append(note(`Chart evidence verified ${data.verified_at || "at an unavailable time"}. Referenced chart roles only.`));
          chartRow.replaceChildren(chartPanel,effects);
          if(!isP2 && a.stability?.subperiods && numeric(a.stability.same_sign_subperiod_count)) {
            const value=headlines.children[2].querySelector(".metric-value");
            if(value)value.textContent=`${integer(a.stability.same_sign_subperiod_count)} / ${integer(a.stability.subperiods.length)}`;
          }
          scheduled.textContent=`Missing scheduled periods: ${integer((a.scheduled_hac||m.scheduled_hac)?.missing_scheduled_period_count)} · gaps retain their scheduled time distance.`;
          if(isP2) {
            const robust=middle.querySelector('[data-role="robustness"]');
            for(const [key,title] of [["leaveouts",""],["robustness_slices","Chronological halves"]]) {
              if(title)robust.append(node("h3",title));
              const rows=a[key]||[],max=Math.max(...rows.map(b=>Math.abs(Number(b.oriented_effect)||0)),0);
              for(const [i,b] of rows.entries())bar(robust,key==="leaveouts" ? `Without block ${b.omitted_block}` : i===0 ? "First half" : "Second half",b.oriented_effect,max,"Oriented estimate",numeric(b.oriented_effect) ? Number(b.oriented_effect)>0 ? "positive" : "negative" : "neutral");
              if(!rows.length)robust.append(note("Not recorded."));
            }
          }
        } catch(error) {
          if(alive&&token===version){chartRow.replaceChildren(note("Chart and block evidence could not be verified."),button("Retry chart evidence",loadEvidence));scheduled.textContent="Missing scheduled periods: unavailable";}
        }
      }
      loadEvidence();
    }
    async function load() {
      root.replaceChildren(note("Verifying saved research for this Feature…"));
      try {
        const data=source ? await source.load(controller.signal) : await request(`/api/feature-research/${recipe.id}`);
        if(!alive)return;
        if(data.recipe_id!==recipe.id||!Array.isArray(data.relationships)||data.relationships.some(r=>!r.scope||!["TS","CS"].includes(r.mode)||!Array.isArray(r.results)))throw new Error("Invalid research");
        if(data.issues !== undefined && (!Array.isArray(data.issues) || data.issues.some(issue=>!issue || typeof issue.code!=="string" || typeof issue.message!=="string")))throw new Error("Invalid research issues");
        relationships=data.relationships;issues=data.issues || [];render();
      } catch(error) {if(alive)root.replaceChildren(note("Saved research could not be verified. No results have been changed."),button("Retry research",load));}
    }
    load();
  }
  window.SignalResearch = {mount, cancel:()=>cancelCurrent()};
})();
