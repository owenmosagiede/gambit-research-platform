"use strict";

(() => {
  const $ = id => document.getElementById(id), panel = $("queue-summary");
  if (!panel) return;
  const waiting = $("queue-waiting-count"), completed = $("queue-completed-count"), status = $("queue-status");
  let controller = null, timer = null, serial = 0, pageActive = true;
  const visible = () => pageActive && !document.hidden &&
    !["#ledger", "#ledger-page", "#signals", "#signal-page"].includes(window.location.hash);
  function schedule() {
    window.clearTimeout(timer);
    if (visible()) timer = window.setTimeout(load, 30000);
  }
  async function load() {
    if (!visible()) return;
    controller?.abort(); const requestController = new AbortController(); controller = requestController; const current = ++serial;
    const timeout = window.setTimeout(() => requestController.abort(), 5000);
    panel.setAttribute("aria-busy", "true");
    try {
      const response = await fetch("/api/research-metrics", {method: "GET", credentials: "same-origin", mode: "same-origin", cache: "no-store", signal: requestController.signal});
      if (!response.ok) throw new Error("Counts unavailable");
      const data = await response.json();
      const stamp = Date.parse(data.observed_at), age = Date.now() - stamp;
      if (data.schema_version !== "research_metrics_v1" || data.counting_unit !== "canonical_research_jobs" ||
          !Number.isSafeInteger(data.queued) || data.queued < 0 ||
          !Number.isSafeInteger(data.completed_last_hour) || data.completed_last_hour < 0 ||
          !Number.isFinite(stamp) || age < -5000 || age > 60000) throw new Error("Unverified counts");
      if (current !== serial || !visible()) return;
      waiting.textContent = String(data.queued); completed.textContent = String(data.completed_last_hour);
      status.textContent = `Checked ${new Date(stamp).toLocaleString()}. Refreshes every 30 seconds.`;
    } catch (_) {
      if (current !== serial || !visible()) return;
      waiting.textContent = "—"; completed.textContent = "—";
      status.textContent = "Research counts are unavailable. Refresh to retry; this does not stop research.";
    } finally {
      window.clearTimeout(timeout);
      if (current === serial) {panel.setAttribute("aria-busy", "false"); schedule();}
    }
  }
  function activate() {
    controller?.abort(); serial++; window.clearTimeout(timer);
    if (visible()) load();
  }
  $("queue-refresh").addEventListener("click", load);
  window.addEventListener("hashchange", activate);
  window.addEventListener("focus", activate);
  document.addEventListener("visibilitychange", activate);
  window.addEventListener("pagehide", () => {pageActive = false; activate();});
  window.addEventListener("pageshow", () => {pageActive = true; activate();});
  load();
})();
