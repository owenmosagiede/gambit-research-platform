"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const api = "/api/forecast-models";
  const pagePath = "/forecast-models/";
  const svgNS = "http://www.w3.org/2000/svg";
  const number = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : "Unavailable";
  const signed = (value, digits = 2) => Number.isFinite(value) ? (value > 0 ? "+" : "") + value.toFixed(digits) : "—";
  const integer = new Intl.NumberFormat("en-US");
  const periods = [...document.querySelectorAll("[data-period]")];
  let catalog = null, activeTask = null, selected = null, controller, observer, fromLibrary = null;
  let loadSequence = 0;

  function el(tag, value, className) {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (className) node.className = className;
    return node;
  }
  function viewLabel(view) {
    return ({CS:"Cross sectional",TS:"Time series",COMBINED:"Combined"})[view] || view;
  }
  function linkFor(task, candidate, period) {
    return pagePath + "#" + new URLSearchParams({task, ...(candidate && {model:candidate}), ...(period && {period})});
  }
  function route(task, candidate, period, replace = false) {
    const href = task ? linkFor(task,candidate,period) : pagePath;
    window.history[replace ? "replaceState" : "pushState"](task && fromLibrary ? {forecastFromLibrary:true} : null,"",href);
    navigate();
  }
  function plainClick(event) {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey;
  }
  async function get(url, signal) {
    const response = await fetch(url,{credentials:"same-origin",cache:"no-store",signal});
    if (!response.ok) throw new Error("Unavailable");
    const data = await response.json();
    if (data.schema !== "gambit_forecast_models_readout_v1") throw new Error("Unknown readout");
    return data;
  }
  function counts(pairs) {
    const list = el("dl");
    for (const [label,value] of pairs) {
      const item = el("div");
      item.append(el("dt",label),el("dd",integer.format(value)));
      list.append(item);
    }
    return list;
  }
  function renderCatalog() {
    const list = $("forecast-tasks");
    list.replaceChildren();
    const status = $("forecast-catalog-status");
    status.textContent = catalog.tasks.length
      ? `${catalog.tasks.length} saved prediction tasks`
      : "No saved prediction tasks are available.";
    if (catalog.archived_through) {
      $("forecast-catalog-notice").textContent = `Frozen P3 records · Evaluation archive through ${catalog.archived_through}`;
      $("forecast-catalog-notice").hidden = false;
    }
    for (const task of catalog.tasks) {
      const card = el("a",undefined,"forecast-task");
      card.id = "task-" + task.id;
      card.href = linkFor(task.id);
      card.append(el("p","Prediction task","section-label"),el("h2",task.title),
        el("p",`${viewLabel(task.view)} · ${task.target_label} · ${task.unit}`,"forecast-meta"),
        counts([["Fitted methods",task.methods.filter(method=>method.status==="fitted").length],
                ["Saved instruments",task.instruments]]),
        el("span","View forecast models","forecast-task-action"));
      card.addEventListener("click",event=>{
        if (!plainClick(event)) return;
        event.preventDefault();
        fromLibrary = {task:task.id,scroll:window.scrollY};
        route(task.id);
        $("forecast-title").focus();
      });
      list.append(card);
    }
  }
  async function loadCatalog() {
    $("forecast-catalog-retry").hidden = true;
    $("forecast-catalog-status").textContent = "Loading saved prediction tasks…";
    try {
      catalog = await get(api,AbortSignal.timeout(10000));
      if (!Array.isArray(catalog.tasks)) throw new Error("Invalid index");
      renderCatalog();
      navigate();
    } catch (_) {
      catalog = null;
      $("forecast-catalog-status").textContent = "Saved prediction tasks could not be loaded.";
      $("forecast-catalog-retry").hidden = false;
    }
  }
  function clearSnapshot() {
    controller?.abort();
    observer?.disconnect();
    $("forecast-snapshot").replaceChildren();
    $("forecast-snapshot").setAttribute("aria-busy","false");
    $("forecast-detail-retry").hidden = true;
    ++loadSequence;
  }
  function navigate() {
    if (!catalog) return;
    const params = new URLSearchParams(window.location.hash.slice(1));
    const id = params.get("task");
    $("forecast-library").hidden = Boolean(id);
    $("forecast-detail").hidden = !id;
    if (!id) {
      if (activeTask) {
        clearSnapshot();
        selected = null;
        activeTask = null;
        if (fromLibrary) {
          document.getElementById("task-"+fromLibrary.task)?.focus({preventScroll:true});
          window.scrollTo(0,fromLibrary.scroll);
          fromLibrary = null;
        }
      }
      return;
    }
    const task = catalog.tasks.find(item=>item.id===id);
    const controls = $("forecast-method").closest(".forecast-controls");
    controls.hidden = !task;
    if (!task) {
      clearSnapshot();
      $("forecast-title").textContent = "Prediction task unavailable";
      $("forecast-context").textContent = "";
      $("forecast-detail-status").textContent = "This link does not identify a saved prediction task.";
      return;
    }
    const defaultModel = task.methods.find(item=>item.method==="equal_weight"&&item.status==="fitted")
      || task.methods.find(item=>item.status==="fitted") || task.methods[0];
    const chosenId = params.has("model") ? params.get("model") : defaultModel?.id;
    const candidate = task.methods.find(item=>item.id===chosenId);
    const period = params.has("period") ? params.get("period") : (candidate?.has_evaluation ? "evaluation" : "training");
    const methodControl = $("forecast-method");
    if (activeTask?.id !== task.id) {
      methodControl.replaceChildren(el("option","Select a saved method"));
      methodControl.firstElementChild.value = "";
      methodControl.firstElementChild.disabled = true;
      for (const item of task.methods) {
        const option = el("option",item.label+(item.status==="fitted"?"":" · unavailable"));
        option.value = item.id;
        methodControl.append(option);
      }
    }
    activeTask = task;
    $("forecast-title").textContent = task.title;
    methodControl.value = candidate?.id || "";
    $("forecast-context").textContent = `${task.target_label} · ${viewLabel(task.view)} · ${task.unit} · ${task.calendar}`;
    for (const button of periods) button.setAttribute("aria-pressed",String(button.dataset.period===period));
    clearSnapshot();
    if (!candidate || !["training","evaluation"].includes(period)) {
      $("forecast-detail-status").textContent = "Choose a saved method and supported period for this task.";
      return;
    }
    if (!params.has("model") || !params.has("period")) {
      window.history.replaceState(window.history.state,"",linkFor(task.id,candidate.id,period));
    }
    loadModel(task,candidate,period,loadSequence);
  }

  async function loadModel(task,candidate,period,sequence) {
    const pane = $("forecast-snapshot");
    pane.setAttribute("aria-busy","true");
    $("forecast-detail-status").textContent = "Loading the selected saved model…";
    controller = new AbortController();
    const controllerForRequest = controller;
    const timeout = setTimeout(()=>controllerForRequest.abort(),12000);
    try {
      const snapshot = selected?.model_id === candidate.id ? selected
        : await get(api+"/"+encodeURIComponent(candidate.id),controllerForRequest.signal);
      if (sequence !== loadSequence) return;
      if (snapshot.model_id !== candidate.id || snapshot.task_id !== task.id || snapshot.method !== candidate.method) {
        throw new Error("Mismatched readout");
      }
      renderSnapshot(pane,snapshot,task,candidate,period);
      selected = snapshot;
      $("forecast-detail-status").textContent = `${candidate.label} · ${period === "training" ? "Training" : "Evaluation"} loaded.`;
    } catch (_) {
      if (sequence !== loadSequence) return;
      pane.replaceChildren();
      $("forecast-detail-status").textContent = "Saved evidence could not be loaded for this selection.";
      $("forecast-detail-retry").hidden = false;
    } finally {
      clearTimeout(timeout);
      if (sequence === loadSequence) pane.setAttribute("aria-busy","false");
    }
  }

  function panel(title, note) {
    const region = el("section",undefined,"forecast-panel");
    region.append(el("h2",title));
    if (note) region.append(el("p",note,"field-note"));
    return region;
  }
  function disclosure(label,value) {
    const details = el("details");
    details.append(el("summary",label),el("pre",JSON.stringify(value,null,2)));
    return details;
  }
  function table(columns, rows, caption) {
    const element = el("table",undefined,"forecast-data");
    if (caption) {
      const title = el("caption",caption,"field-note");
      element.append(title);
    }
    const header = element.createTHead().insertRow();
    for (const column of columns) {
      const cell = el("th",column);
      cell.scope = "col";
      header.append(cell);
    }
    const body = element.createTBody();
    for (const cells of rows) {
      const row = body.insertRow();
      for (const content of cells) {
        const cell = row.insertCell();
        if (typeof content==="string") cell.textContent=content;
        else cell.append(content);
      }
    }
    const wrap=el("div",undefined,"table-scroll");
    wrap.tabIndex=0;
    wrap.setAttribute("role","region");
    wrap.setAttribute("aria-label",caption||"Forecast evidence table");
    wrap.append(element);
    return wrap;
  }

  function metricCards(metrics) {
    const grid = el("div",undefined,"forecast-stats");
    for (const metric of metrics) {
      const block = el("div",undefined,"forecast-stat"), list = el("dl");
      const value = el("dd",number(metric.value,metric.digits ?? (metric.label.includes("IC")?3:2)));
      if (metric.unit && Number.isFinite(metric.value)) value.append(el("small",metric.unit));
      list.append(el("dt",metric.label),value);
      block.append(list,el("p",metric.note,"field-note"));
      grid.append(block);
    }
    return grid;
  }
  function numer(value) { return el("span",value,"forecast-num"); }
  function svg(tag,attrs,text) {
    const node = document.createElementNS(svgNS,tag);
    for (const [key,val] of Object.entries(attrs)) node.setAttribute(key,val);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function renderChart(container, points, kind, label) {
    const width = Math.max(215,Math.floor(container.clientWidth)), height=220;
    const left=49, right=width-15, top=17, bottom=179;
    let minX, maxX, minY, maxY;
    if (kind === "rolling") {
      minX=0;maxX=Math.max(1,points.length-1);
      const values=points.map(item=>item.value);
      minY=Math.min(0,...values);maxY=Math.max(0,...values);
    } else if (kind === "calibration") {
      minX=minY=Math.min(0,...points.flatMap(p=>[p.forecast,p.realized]));
      maxX=maxY=Math.max(0,...points.flatMap(p=>[p.forecast,p.realized]));
    } else {
      minX=points[0].low;maxX=points.at(-1).high;
      minY=0;maxY=Math.max(...points.map(p=>p.count));
    }
    if (minX === maxX) {minX-=1;maxX+=1;}
    if (minY === maxY) {minY-=1;maxY+=1;}
    const X=x=>left + (x-minX)/(maxX-minX)*(right-left);
    const Y=y=>bottom - (y-minY)/(maxY-minY)*(bottom-top);
    const art=svg("svg",{viewBox:`0 0 ${width} ${height}`,role:"img","aria-label":label});
    for (let index=0;index<=3;index++) {
      const value=minY+(maxY-minY)*index/3, y=Y(value);
      art.append(svg("line",{x1:left,x2:right,y1:y,y2:y,class:"forecast-chart-grid"}),
                 svg("text",{x:left-7,y:y+4,"text-anchor":"end"},kind==="histogram" ? Math.round(value) : value.toFixed(2)));
    }
    const labels = kind === "rolling"
      ? [[left,points[0].origin.slice(5)],[right,points.at(-1).origin.slice(5)]]
      : [[left,minX.toFixed(1)],[right,maxX.toFixed(1)]];
    for (const [x,text] of labels) art.append(svg("text",{x,y:201,"text-anchor":x===left?"start":"end"},text));
    if (kind === "calibration") {
      art.append(svg("line",{x1:X(minX),x2:X(maxX),y1:Y(minX),y2:Y(maxX),class:"forecast-chart-reference"}));
    } else if (kind === "rolling" && minY<0) {
      art.append(svg("line",{x1:left,x2:right,y1:Y(0),y2:Y(0),class:"forecast-chart-reference"}));
    }
    if (kind === "histogram") {
      const step=(right-left)/points.length;
      points.forEach((bin,i)=>art.append(svg("rect",{x:left+i*step+1,y:Y(bin.count),width:Math.max(1,step-2),
        height:bottom-Y(bin.count),class:"forecast-chart-mark"})));
    } else {
      const coordinates=points.map((p,i)=>kind==="rolling"?[X(i),Y(p.value)]:[X(p.forecast),Y(p.realized)]);
      art.append(svg("polyline",{points:coordinates.map(pair=>pair.join(",")).join(" "),class:"forecast-chart-path"}));
      if (kind==="calibration" || coordinates.length===1) {
        for (const [x,y] of coordinates) art.append(svg("circle",{cx:x,cy:y,r:3,class:"forecast-chart-mark"}));
      }
    }
    container.replaceChildren(art);
  }
  function showChart(region, points, kind, label, empty, charts) {
    if (!points.length) {
      region.append(el("p",empty,"field-note"));
      return;
    }
    const container = el("div",undefined,"forecast-chart");
    region.append(container);
    charts.set(container,{points,kind,label});
  }
  function chartsFor(diag, charts) {
    const row = el("div",undefined,"forecast-panels");
    const rolling = panel(diag.rolling.label,"21 valid forecast dates per window. Origins with missing or undefined ranks are omitted.");
    showChart(rolling,diag.rolling.points,"rolling",diag.rolling.label,"Requires 21 dates with valid observations.",charts);
    const calibration = panel("Forecast calibration","Mean realized vs. mean forecast in up to six equal-count bins. Ties stay together. Gray line is perfect calibration.");
    showChart(calibration,diag.calibration,"calibration","Calibration, forecast and realized returns in basis points",
      "Requires at least six matched rows and distinct forecast values.",charts);
    if (diag.calibration.length) {
      const details=el("details");details.append(el("summary","Calibration bin counts"),table(
        ["Forecast · bps","Realized · bps","Count"],diag.calibration.map(b=>[number(b.forecast),number(b.realized),integer.format(b.count)]),"Calibration bins"));
      calibration.append(details);
    }
    row.append(rolling,calibration);
    return row;
  }
  function errorPanel(diag,charts) {
    const error = panel("Forecast error distribution","Realized minus forecast. Nine equal-width bins symmetric around zero when errors vary.");
    showChart(error,diag.histogram,"histogram","Forecast errors in basis points","No completed forecast errors.",charts);
    if (diag.histogram.length) {
      error.append(el("p",`Mean error ${signed(diag.mean_error)} bps · ${integer.format(diag.counts.matched)} matched forecasts`,"forecast-meta"));
      const detail=el("details");detail.append(el("summary","Error bin counts"),table(["Lower · bps","Upper · bps","Count"],
        diag.histogram.map(b=>[number(b.low),number(b.high),integer.format(b.count)]),"Forecast error bins"));
      error.append(detail);
    }
    return error;
  }
  function inputsPanel(snapshot) {
    const ridge=snapshot.method==="ridge_reg_weight";
    const note=ridge ? "The archived Ridge fit applies signed coefficients to individually calibrated return forecasts."
      : "Saved weights apply to individually calibrated return forecasts in matching target units.";
    const input=panel("Model components",note+" Component errors and mean absolute contributions are unavailable in this archive.");
    const rows=snapshot.inputs.map(row=>{
      const ref=disclosure(row.label===row.recipe.id ? "Recipe "+row.recipe.id.slice(-12) : row.label,{
        recipe:row.recipe,relationship:row.relationship,validation:row.validation,trial:row.trial,
        feature_references:row.feature_refs,calibration:row.calibration,alignment:row.alignment_policy,
      });
      const val=Number.isFinite(row.influence)?(ridge?signed(row.influence,4):number(row.influence*100,2)+"%"):"—";
      return [ref,numer(val),"—","—"];
    });
    input.append(table(["Calibrated component",ridge?"Coefficient":"Weight","Error RMSE · bps","Mean absolute contribution · bps"],rows,"Saved model components"));
    if (Number.isFinite(snapshot.intercept_bps)) input.append(el("p","Saved intercept "+signed(snapshot.intercept_bps)+" bps","forecast-meta"));
    return input;
  }
  function ledgerPanel(snapshot) {
    const rows=snapshot.evaluation.rows;
    const names={matched:"Matched",pending_outcome:"Pending outcome",missing_outcome:"Missing outcome",
      unavailable_forecast:"Unavailable forecast",excluded_incomplete_scope:"Excluded · incomplete scope"};
    const ledger=panel("Forecast ledger","Archived close-to-close predictions and outcomes. Forecasts remain linked to their original fit and target.");
    if (!rows.length) {
      ledger.append(el("p","No saved forecast rows for this selection.","field-note"));
      return ledger;
    }
    const dates=[...new Set(rows.map(row=>row.origin))];
    const filter=el("select"), label=el("label","Forecast origin");
    filter.id="forecast-origin";label.htmlFor=filter.id;
    filter.append(el("option","All saved dates"));filter.firstChild.value="";
    for (const day of dates) { const option=el("option",day);option.value=day;filter.append(option); }
    const contents=el("div"), controls=el("div",undefined,"forecast-page-nav");
    const previous=el("button","Previous page","research-button"),next=el("button","Next page","research-button");
    const status=el("span",undefined,"field-note");status.setAttribute("aria-live","polite");
    previous.type=next.type="button"; controls.append(previous,next,status);
    let page=0;
    const pageSize=36;
    function draw() {
      const scoped=filter.value?rows.filter(row=>row.origin===filter.value):rows;
      const start=page*pageSize;
      const cells=scoped.slice(start,start+pageSize).map(row=>[
        disclosure(row.instrument,{model_id:snapshot.model_id,fit_id:snapshot.fit_id,
          target:snapshot.lineage.targets_by_instrument[row.instrument],
          forecast_stream_sha256:snapshot.lineage.forecast_stream_sha256,
          archived_evaluation:snapshot.lineage.evaluation_archive_sha256,
          forecast_available_at:null}),
        numer(row.origin),numer(row.target_end),numer(signed(row.forecast_bps)),
        numer(signed(row.realized_bps)),numer(signed(row.error_bps)),names[row.status]||row.status,
      ]);
      contents.replaceChildren(table(["Instrument","Forecast origin","Target close","Forecast · bps",
        "Realized · bps","Error · bps","Status"],cells,"Saved forecast ledger"));
      previous.disabled=page===0;next.disabled=start+pageSize>=scoped.length;
      status.textContent=`${start+1}–${Math.min(start+pageSize,scoped.length)} of ${scoped.length} rows`;
    }
    previous.addEventListener("click",()=>{page--;draw();});
    next.addEventListener("click",()=>{page++;draw();});
    filter.addEventListener("change",()=>{page=0;draw();});
    ledger.append(label,filter,contents,controls);draw();
    return ledger;
  }
  function lineagePanel(snapshot, task, candidate) {
    const lineage=panel("Supporting evidence","The archive did not retain distinct model-version, forecast-run, or point-in-time availability fields.");
    lineage.append(disclosure("Lineage and fit context",{
      task_id:task.id,model_id:snapshot.model_id,method:candidate.method,policy:snapshot.saved_policy,
      fit_id:snapshot.fit_id,fit_period:snapshot.training.bounds,fit_evidence:snapshot.training.fit_evidence,
      scope:task.scope,calendar:task.calendar,...snapshot.lineage,
    }),el("p","No canonical Model Comparison Record is attached to this archive.","field-note"));
    return lineage;
  }
  function renderSnapshot(pane,snapshot,task,candidate,period) {
    const fragment=document.createDocumentFragment(), charts=new Map();
    const evaluation=snapshot.evaluation, diag=evaluation.diagnostics;
    const header=el("div",undefined,"forecast-period-line");
    const bounds=snapshot.training.bounds;
    header.append(el("p",period==="training"
      ? `Fit window ${bounds.start_inclusive} to ${bounds.end_exclusive} (end excluded)`
      : evaluation.bounds ? `Archived evaluation ${evaluation.bounds[0]} to ${evaluation.bounds[1]}` : "Evaluation unavailable","forecast-meta"),
      el("p",`Saved fit · ${snapshot.fit_id.slice(-12)}`,"forecast-meta"));
    fragment.append(header);
    if (snapshot.fit_reason) fragment.append(el("p","Saved fit unavailable · "+snapshot.fit_reason.replaceAll("_"," ").toLowerCase(),"forecast-notice"));
    if (period==="training") {
      const saved=snapshot.training.fit_evidence;
      fragment.append(el("p",snapshot.training.availability,"forecast-notice"));
      const evidence=panel("Saved fit support","Chronological development sample used for this saved combination when recorded.");
      evidence.append(metricCards([["Matched dates",saved.matched_dates],["Matched rows",saved.matched_rows],
        ["Non-overlapping windows",saved.non_overlapping_intervals]].map(([label,value])=>(
          {label,value,unit:null,digits:0,note:Number.isFinite(value)?"Recorded in the archived fit":"Unavailable in this fit record."}))));
      fragment.append(evidence,inputsPanel(snapshot));
    } else {
      if (evaluation.availability) fragment.append(el("p",evaluation.availability,"forecast-notice"));
      else {
        const c=diag.counts, coverage=diag.breadth.length
          ? (diag.breadth[0]===diag.breadth[1] ? String(diag.breadth[0]) : diag.breadth.join("–")) : "—";
        fragment.append(metricCards(diag.metric_values),
          el("p",`${integer.format(c.matched||0)} matched · ${diag.dates} evaluated dates · ${diag.quality_dates} valid ranks · ${integer.format(c.pending_outcome||0)} pending · ${integer.format(c.missing_outcome||0)} missing outcomes · ${integer.format(c.unavailable_forecast||0)} unavailable forecasts · ${integer.format(c.excluded_incomplete_scope||0)} excluded · ${coverage} instruments per evaluated date`,"field-note"));
        fragment.append(chartsFor(diag,charts));
      }
      const row=el("div",undefined,"forecast-panels");
      if (!evaluation.availability) row.append(errorPanel(diag,charts),inputsPanel(snapshot));
      if (row.children.length) fragment.append(row); else fragment.append(inputsPanel(snapshot));
      fragment.append(ledgerPanel(snapshot));
    }
    fragment.append(lineagePanel(snapshot,task,candidate));
    pane.replaceChildren(fragment);
    if (charts.size) {
      observer=new ResizeObserver(entries=>{
        for (const entry of entries) { const chart=charts.get(entry.target);renderChart(entry.target,chart.points,chart.kind,chart.label); }
      });
      for (const [container,chart] of charts) {
        renderChart(container,chart.points,chart.kind,chart.label);
        observer.observe(container);
      }
    }
  }

  $("forecast-catalog-retry").addEventListener("click",loadCatalog);
  $("forecast-detail-retry").addEventListener("click",navigate);
  $("forecast-method").addEventListener("change",event=>{
    const period=new URLSearchParams(window.location.hash.slice(1)).get("period")||"evaluation";
    route(activeTask.id,event.target.value,period,true);
  });
  for (const button of periods) button.addEventListener("click",()=>{
    if (activeTask) route(activeTask.id,$("forecast-method").value,button.dataset.period,true);
  });
  $("forecast-back").addEventListener("click",event=>{
    if (!plainClick(event)) return;
    event.preventDefault();
    if (window.history.state?.forecastFromLibrary && fromLibrary) window.history.back();
    else route(null,null,null,true);
  });
  document.querySelector(".skip-link")?.addEventListener("click",event=>{
    event.preventDefault();
    $("forecast-models").focus();
  });
  window.addEventListener("popstate",navigate);
  window.addEventListener("hashchange",navigate);
  window.addEventListener("pagehide",clearSnapshot);
  window.addEventListener("pageshow",event=>{if (event.persisted) navigate();});
  loadCatalog();
})();
