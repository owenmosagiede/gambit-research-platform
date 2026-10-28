"use strict";

// A read-only contract explorer. Request submission belongs to research tooling.
(() => {
  const $ = id => document.getElementById(id);
  if (!$('contract-example')) return;
  const fields = ['feature', 'target', 'scope', 'expected-direction'].map($);
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const ref = value => value && text(value.id) && text(value.version);
  const equal = (a, b) => ref(a) && ref(b) && a.id === b.id && a.version === b.version;
  const parse = value => { try { return JSON.parse(value || 'null'); } catch (_) { return null; } };
  const exact = value => ref(value) && /^[0-9a-f]{64}$/.test(value.content_sha256);
  const same = (a, b) => exact(a) && exact(b) && equal(a, b) && a.content_sha256 === b.content_sha256;
  const valid = field => !field.disabled && (!field.validity || field.validity.valid !== false);
  let readiness = null, readinessBusy = false, healthTimer = null, pageActive = true;
  let queueSettled = false, readinessStarted = false, catalogStarted = false;
  let catalogRefreshRunning = false, catalogRefreshPending = false, lastCatalogRefresh = 0;

  function selection(id, key) {
    const field = $(id), chosen = parse(field.value), binding = parse(field.dataset[key]);
    return !field.disabled && equal(chosen, binding) && exact(binding) ? {id: chosen.id, version: chosen.version} : null;
  }
  function matchingResolution(feature, scope) {
    const value = parse($('feature').dataset.featureResolution);
    const resolved = scopeResolution(scope);
    return resolved && equal(value?.recipe?.reference, feature) && equal(value?.scope, scope) &&
      same(value.recipe.reference, parse($('feature').dataset.featureReference)) &&
      same(value.scope.reference, resolved.definition_binding) &&
      same(value.scope.membership_snapshot, resolved.membership_snapshot) ? value : null;
  }
  function scopeResolution(scope) {
    const value = parse($('scope').dataset.scopeResolution);
    return equal(value, scope) && exact(value.definition_binding) &&
      same(value.definition_binding, parse($('scope').dataset.scopeReference)) &&
      same(value.membership_snapshot, parse($('scope').dataset.membershipSnapshot)) ? value : null;
  }
  function renderCatalog() {
    const node = $('contract-catalog-status');
    if (fields.some(field => field.getAttribute('aria-busy') === 'true')) {
      node.textContent = 'Refreshing registered inputs…'; return;
    }
    const counts = [$('feature').dataset.catalogCount, $('scope').dataset.universeCount, $('scope').dataset.instrumentCount];
    node.textContent = counts.every(value => /^\d+$/.test(value || ''))
      ? `${counts[0]} registered Features · ${counts[1]} CS universes · ${counts[2]} single-pair TS Scopes. Choices refresh when you return to this page.`
      : 'Inputs are read from the current catalog. Refresh inputs to retry unavailable choices.';
  }
  function render() {
    renderCatalog();
    const feature = selection('feature', 'featureReference'), scope = selection('scope', 'scopeReference');
    const target = valid($('target')) && $('target').value === 'price' && $('target').dataset.returnBasis === 'price';
    const direction = valid($('expected-direction')) && ['POSITIVE', 'NEGATIVE'].includes($('expected-direction').value)
      ? $('expected-direction').value : null;
    const resolution = matchingResolution(feature, scope), resolvedScope = scopeResolution(scope);
    $('contract-example').textContent = JSON.stringify({
      request_id: '<new canonical UUID>',
      feature: feature || {id: '<registered Feature ID>', version: '<exact version>'},
      target_family: target ? 'price_return' : '<available Target family>',
      scope: scope || {id: '<registered Scope ID>', version: '<exact version>'},
      expected_direction: direction || '<POSITIVE or NEGATIVE>'
    }, null, 2);
    const complete = feature && scope && resolvedScope && target && direction && fields.every(valid);
    $('contract-selection-status').textContent = resolution?.submission_compatible === false
      ? `This combination is unsupported. ${resolution.source_application_note || 'Choose compatible registered inputs.'} This page never submits a request.`
      : complete && resolution?.submission_compatible === true
        ? 'Example for the selected inputs. Replace the UUID placeholder in research tooling; the service rechecks and freezes the exact dependencies on submission. This page never submits a request.'
        : 'Choose the four inputs to inspect an example. Unresolved choices remain placeholders; compatibility must be verified before research tooling submits a request.';
    const compatible = resolution?.submission_compatible === true;
    const spec = compatible ? resolution.research_spec : null;
    $('research-specification').textContent = exact(spec)
      ? `Research Spec: ${spec.id} · ${spec.version} (selected and frozen by the service)`
      : compatible && resolution?.application?.contract?.kind === 'currency_quote_input'
        ? 'Currency CS Research Spec: selected from the active currency release and frozen by the service on submission.'
        : compatible && resolution?.application?.contract?.kind === 'per_instrument_input' && resolvedScope?.kind === 'instrument' && exact(readiness?.research_spec)
          ? `Research Spec: ${readiness.research_spec.id} · ${readiness.research_spec.version} (selected and frozen by the service)`
          : 'Research Spec is selected and frozen by the service for the chosen inputs; it is not a request field.';
    $('research-method-summary').textContent = resolvedScope?.kind === 'universe' && text(resolvedScope.reference_currency)
      ? `CS: ${resolvedScope.member_count} currencies against ${resolvedScope.reference_currency}. Feature and Target use the same oriented price. Five horizons: 1, 7, 21, 63 and 252 scheduled weekdays.`
      : resolvedScope?.kind === 'instrument'
        ? `TS: ${resolvedScope.display_name || scope.id}, using its registered quotation. Five horizons: 1, 7, 21, 63 and 252 scheduled weekdays.`
        : 'Individual instrument: TS. Currency universe: CS with a common quote/funding reference. P1 evaluates five horizons; admitted candidates proceed to P2.';
  }
  function rows(node, values) {
    node.replaceChildren(...values.map(value => { const item = document.createElement('li'); item.textContent = value.message; return item; }));
    node.hidden = values.length === 0;
  }
  function reasons(value) {
    if (!Array.isArray(value) || value.some(row => !row || !text(row.message))) throw Error('Invalid service status');
    return value;
  }
  // Match the router, including skip links and exact historical trial links.
  const visible = () => pageActive && document.visibilityState !== 'hidden' &&
    !['#ledger', '#ledger-page', '#signals', '#signal-page'].includes(window.location.hash);
  function schedule() {
    window.clearTimeout(healthTimer);
    if (queueSettled && visible()) healthTimer = window.setTimeout(loadReadiness, 30000);
  }
  async function loadReadiness() {
    if (!queueSettled || !visible() || readinessBusy) return;
    readinessStarted = true;
    readinessBusy = true;
    $('research-readiness-retry').disabled = true;
    const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/research-readiness', {method: 'GET', mode: 'same-origin', credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw Error('Service status unavailable');
      const value = await response.json();
      if (typeof value?.execution_enabled !== 'boolean') throw Error('Invalid service status');
      const blockers = reasons(value.blockers), incidents = reasons(value.submission_incidents || []).map(item => ({message:
        `Operational failure ${item.id || 'unidentified'} · ${item.request_id || item.storage_path || 'request unavailable'}: ${item.message}`}));
      readiness = value;
      rows($('research-readiness-blockers'), blockers); rows($('research-operational-incidents'), incidents);
      $('research-readiness-status').textContent = value.execution_enabled && !blockers.length
        ? 'Research service is available. Requests from research tooling are checked by the service; this page is read-only.'
        : 'Research service has blockers. The contract remains available for reference.';
    } catch (_) {
      readiness = null;
      rows($('research-readiness-blockers'), []); rows($('research-operational-incidents'), []);
      $('research-readiness-status').textContent = 'Service status is unavailable. This read-only contract remains available; availability is not confirmed.';
    } finally {
      window.clearTimeout(timeout); readinessBusy = false; $('research-readiness-retry').disabled = false;
      render(); schedule();
    }
  }
  async function refreshCatalog(force = false) {
    if (!queueSettled || !visible()) return;
    if (catalogRefreshRunning) { if (force) catalogRefreshPending = true; return; }
    if (!force && !catalogRefreshPending && catalogStarted &&
        (Date.now() - lastCatalogRefresh < 30000 || fields.some(field => field.getAttribute('aria-busy') === 'true'))) return;
    catalogRefreshRunning = true; catalogRefreshPending = false;
    lastCatalogRefresh = Date.now();
    const readers = new Map();
    // Give the first queue/history read the available request slots. Once it
    // settles, warm only the visible contract's catalogs, one at a time.
    window.dispatchEvent(new CustomEvent('experiment-catalog-refresh', {detail: {
      enqueue(name, read) { if (['scope', 'feature', 'target'].includes(name) && typeof read === 'function') readers.set(name, read); }
    }}));
    render();
    try {
      for (const name of ['scope', 'feature', 'target']) {
        if (!visible()) { catalogRefreshPending = true; break; }
        if (readers.has(name)) await readers.get(name)();
      }
      catalogStarted = true;
    } finally {
      catalogRefreshRunning = false;
      render();
      if (catalogRefreshPending && visible()) refreshCatalog(true);
    }
  }
  function activate() {
    if (queueSettled && visible()) {
      refreshCatalog();
      if (!readinessStarted) loadReadiness();
    }
    schedule();
  }
  for (const field of fields) field.addEventListener('change', render);
  for (const event of ['feature-state-change', 'scope-state-change', 'target-state-change']) window.addEventListener(event, render);
  $('contract-refresh').addEventListener('click', () => refreshCatalog(true));
  $('research-readiness-retry').addEventListener('click', loadReadiness);
  window.addEventListener('research-queue-settled', () => { queueSettled = true; activate(); });
  window.addEventListener('focus', activate);
  window.addEventListener('hashchange', activate);
  document.addEventListener('visibilitychange', activate);
  window.addEventListener('pagehide', () => { pageActive = false; window.clearTimeout(healthTimer); });
  window.addEventListener('pageshow', () => { pageActive = true; activate(); });
  render();
})();
