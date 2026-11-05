// Session handling is shared by the landing and live reader; exported HTML stays independent.
(() => {
  'use strict';
  let state = { enabled: false, authenticated: false };
  const originalFetch = window.fetch.bind(window);
  let redirecting = false;
  function login() {
    if (redirecting) return;
    redirecting = true;
    location.replace(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
  }
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    const input = args[0];
    const url = new URL(typeof input === 'string' || input instanceof URL ? String(input) : input.url, location.href);
    if (response.status === 401 && url.origin === location.origin && url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/auth/')) login();
    return response;
  };
  function render(root = document) {
    root.querySelectorAll('[data-logout]').forEach((button) => {
      button.hidden = !(state.enabled && state.authenticated);
      const label = button.querySelector('[data-logout-label]');
      const caption = document.documentElement.lang.startsWith('zh') ? '登出' : 'Sign out';
      if (label) label.textContent = caption;
      button.setAttribute('aria-label', caption);
      button.title = caption;
      button.onclick = async () => {
        button.disabled = true;
        try {
          const response = await originalFetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
          if (!response.ok) throw new Error();
          location.replace('/login');
        } catch {
          button.disabled = false;
          const failure = document.documentElement.lang.startsWith('zh') ? '登出失败，点击重试' : 'Retry sign out';
          if (label) label.textContent = failure;
          button.title = failure;
          button.setAttribute('aria-label', failure);
        }
      };
    });
  }
  window.TFSession = { render };
  originalFetch('/api/auth/session', { cache: 'no-store' }).then((r) => {
    if (!r.ok) throw new Error();
    return r.json();
  }).then((value) => { state = value; if (state.enabled && !state.authenticated) login(); else render(); }).catch(() => {});
  addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });
})();
