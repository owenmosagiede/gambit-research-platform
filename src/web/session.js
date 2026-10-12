"use strict";
// Loaded only in the authenticated cloud UI, before the existing application scripts.
(() => {
  const original = window.fetch.bind(window);
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  let announced = false;
  function sessionNotice() {
    if (announced) return;
    announced = true;
    const notice = document.createElement('div');
    notice.setAttribute('role', 'alert'); notice.className = 'cloud-session-notice';
    const text = document.createElement('p');
    text.textContent = 'Please sign in again. Saved submissions keep their original IDs; signing in does not start or repeat research.';
    const link = document.createElement('a'); link.href = '/login/'; link.textContent = 'Sign in again';
    notice.append(text, link); document.body.prepend(notice);
  }
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) return original(input, options);
    const method = (options.method || input.method || 'GET').toUpperCase();
    const headers = new Headers(options.headers || input.headers);
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-CSRFToken', token || '');
    const response = await original(input, {...options, headers, credentials:'same-origin'});
    if (response.status === 401 || response.status === 403) sessionNotice();
    return response;
  };
  const nav = document.querySelector('nav[aria-label="Workspace"]');
  if (nav) {
    const form = document.createElement('form'); form.method = 'post'; form.action = '/logout/';
    const csrf = document.createElement('input'); csrf.type = 'hidden'; csrf.name = 'csrfmiddlewaretoken'; csrf.value = token;
    const button = document.createElement('button'); button.type = 'submit'; button.className = 'text-button'; button.textContent = 'Sign out';
    form.append(csrf, button); nav.after(form);
  }
})();
