/* Presentation only: authorization and every business mutation remain on the server. */
(() => {
  document.documentElement.classList.add('portal-enhanced');
  // Native summary supplies keyboard/no-script behavior. Expand the hit area without
  // hijacking links, financial actions, form controls, or selecting/copying text.
  document.addEventListener('click', event => {
    const card = event.target.closest('[data-bill-card]');
    if (!card || event.defaultPrevented || event.button !== 0) return;
    if (event.detail !== 0 && getSelection()?.toString()) {
      if (event.target.closest('summary')) event.preventDefault();
      return;
    }
    if (event.target.closest('summary,a,button,input,select,textarea,label,form,[role="button"],[contenteditable]')) return;
    card.open = !card.open;
  });
  const sidebar = document.querySelector('#portal-sidebar');
  const button = document.querySelector('.portal-menu');
  const mobile = matchMedia('(max-width:900px)');
  const sync = () => {
    if (!sidebar) return;
    sidebar.inert = mobile.matches && !sidebar.classList.contains('open');
    if (sidebar.inert) sidebar.setAttribute('aria-hidden', 'true');
    else sidebar.removeAttribute('aria-hidden');
  };
  const close = () => { sidebar?.classList.remove('open'); button?.setAttribute('aria-expanded', 'false'); sync(); };
  button?.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open');
    button.setAttribute('aria-expanded', String(open)); sync();
    if (open) sidebar.querySelector('a')?.focus();
  });
  mobile.addEventListener('change', close); sync();
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && sidebar?.classList.contains('open')) { close(); button?.focus(); }
    if (e.key === 'Tab' && mobile.matches && sidebar?.classList.contains('open')) {
      const focusable = [...sidebar.querySelectorAll('a[href],button')];
      const first = focusable[0], last = focusable.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener('click', e => {
    if (sidebar?.classList.contains('open') && !sidebar.contains(e.target) && !button?.contains(e.target)) close();
  });
  document.querySelectorAll('.location-image img, .person-image img').forEach(img => {
    const failed = () => { img.hidden = true; };
    img.addEventListener('error', failed);
    if (img.complete && img.naturalWidth === 0) failed();
  });
  const picker = document.querySelector('.location-picker');
  // Native navigation cancels older loads; no asynchronous filter fragments can arrive stale.
  document.querySelectorAll('[data-auto-filters]').forEach(form => {
    // Browsers can restore a pre-submit select value onto the previous results page.
    // The HTML defaults represent that page's URL and server-side result set.
    addEventListener('pageshow', () => requestAnimationFrame(() => form.reset()));
    form.addEventListener('change', event => {
      if (event.target.tagName === 'SELECT') form.requestSubmit();
    });
  });
  const phone = matchMedia('(max-width:800px)');
  if (picker) { const resize = () => { picker.open = !phone.matches; }; resize(); phone.addEventListener('change', resize); }
  // Only navigation coordinates, never form contents or tenant data, enter browser storage.
  const key = () => `rhp:scroll:${location.pathname}${location.search}`;
  try {
    const saved = sessionStorage.getItem(key());
    if (saved && !location.hash) requestAnimationFrame(() => scrollTo(0, Number(saved)));
    addEventListener('pagehide', () => sessionStorage.setItem(key(), String(scrollY)));
  } catch { /* Native browser history works when storage is disabled. */ }
})();
