/* Progressive enhancement only. Money calculations run in the existing Python service. */
(() => {
  const menu = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('#sidebar');
  const mobile = matchMedia('(max-width:900px)');
  document.body.classList.add('enhanced');
  document.querySelectorAll('.entity-image img').forEach(img => {
    const failed = () => { img.hidden = true; img.parentElement.classList.add('image-missing'); img.parentElement.setAttribute('aria-label', img.parentElement.getAttribute('aria-label').replace(' · synthetic sample photo', '')); };
    img.addEventListener('error', failed);
    if (img.complete && img.naturalWidth === 0) failed();
  });
  document.querySelectorAll('[data-auto-filter]').forEach(filter => {
    filter.querySelectorAll('select').forEach(select => select.addEventListener('change', () => filter.requestSubmit()));
  });
  const locationPicker = document.querySelector('.location-picker');
  const phone = matchMedia('(max-width:800px)');
  const syncLocation = () => { if (locationPicker) locationPicker.open = !phone.matches; };
  syncLocation(); phone.addEventListener('change', syncLocation);
  // Full-page GET navigation avoids out-of-order fragment responses. Keep scroll per URL.
  const scrollKey = () => 'rhp-prototype:scroll:' + location.pathname + location.search;
  try {
    const y = sessionStorage.getItem(scrollKey());
    if (y && !location.hash) requestAnimationFrame(() => scrollTo(0, Number(y)));
    addEventListener('pagehide', () => sessionStorage.setItem(scrollKey(), String(scrollY)));
  } catch { /* Browser history and plain links remain usable without storage. */ }
  const syncMenu = () => { if (sidebar) { sidebar.inert = mobile.matches && !sidebar.classList.contains('open'); sidebar.setAttribute('aria-hidden', String(sidebar.inert)); } };
  const closeMenu = () => { sidebar?.classList.remove('open'); menu?.setAttribute('aria-expanded', 'false'); syncMenu(); };
  syncMenu(); mobile.addEventListener('change', closeMenu);
  menu?.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open'); menu.setAttribute('aria-expanded', String(open)); syncMenu();
    if (open) sidebar.querySelector('a')?.focus();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && sidebar?.classList.contains('open')) { closeMenu(); menu.focus(); } });
  sidebar?.addEventListener('keydown', e => {
    if (e.key !== 'Tab' || !mobile.matches || !sidebar.classList.contains('open')) return;
    const links = [...sidebar.querySelectorAll('a[href], button')];
    const first = links[0], last = links[links.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  document.addEventListener('click', e => { if (sidebar?.classList.contains('open') && !sidebar.contains(e.target) && !menu?.contains(e.target)) closeMenu(); });
  const selectUnit = target => {
    const id = target.closest('[data-unit]')?.dataset.unit;
    if (!id) return;
    document.querySelectorAll('[data-allocation-row]').forEach(r => r.classList.toggle('highlight', r.dataset.allocationRow === id));
    const row = document.querySelector(`[data-allocation-row="${id}"]`);
    row?.querySelector('input')?.focus({preventScroll:true});
    row?.scrollIntoView({block:'nearest', behavior:'auto'});
  };
  document.addEventListener('click', e => selectUnit(e.target));
  document.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('svg [data-unit]')) { e.preventDefault(); selectUnit(e.target); } });
  document.querySelector('[data-reset]')?.addEventListener('click', () => {
    Object.keys(sessionStorage).filter(k => k.startsWith('rhp-prototype:')).forEach(k => sessionStorage.removeItem(k));
  });
  const form = document.querySelector('#allocation-form');
  if (!form) return;
  const storage = 'rhp-prototype:' + form.dataset.draft;
  let serial = 0, controller, timer;
  const syncRecipient = () => {
    const recipient = form.elements.namedItem('remainder').value;
    form.querySelectorAll('[data-allocation-row]').forEach(row => {
      const calculated = row.dataset.allocationRow === recipient;
      row.querySelectorAll('input').forEach(input => { input.readOnly = calculated; });
      row.querySelector('.field-note').textContent = calculated
        ? 'Calculated remainder recipient. Choose another recipient before editing this unit directly.'
        : 'The field you edit controls its paired value. Rounded percentages never replace exact dollars.';
    });
  };
  const remember = () => { try { sessionStorage.setItem(storage, JSON.stringify(Object.fromEntries([...new FormData(form)].filter(([k]) => k !== 'csrfmiddlewaretoken')))); } catch { /* Storage can be disabled; plain forms still work. */ } };
  const preview = async () => {
    const current = ++serial;
    controller?.abort(); controller = new AbortController();
    try {
      const response = await fetch(form.dataset.preview, {method:'POST',body:new FormData(form),signal:controller.signal,credentials:'same-origin'});
      const data = await response.json();
      if (current !== serial) return;
      if (!response.ok) { document.querySelector('#allocation-summary').textContent = data.error || 'Preview unavailable. Use Update calculation.'; return; }
      document.querySelector('#allocation-summary').innerHTML = data.summary;
      const method = form.elements.namedItem('method').value;
      const remainder = form.elements.namedItem('remainder').value;
      for (const row of data.values) {
        const basis = form.elements.namedItem(`basis_${row.id}`).value;
        for (const field of ['amount','percent']) {
          const input = form.elements.namedItem(`${field}_${row.id}`);
          if (input !== document.activeElement && (method !== 'custom' || remainder === String(row.id) || basis !== field)) input.value = row[field];
        }
      }
      remember();
    } catch (e) { if (e.name !== 'AbortError' && current === serial) document.querySelector('#allocation-summary').textContent = 'Live preview unavailable. Use Update calculation; your input has been kept.'; }
  };
  try {
    const saved = JSON.parse(sessionStorage.getItem(storage) || 'null');
    if (saved) { for (const [k,v] of Object.entries(saved)) { const input = form.elements.namedItem(k); if (input && k !== 'csrfmiddlewaretoken') input.value = v; } preview(); }
  } catch { /* No persistent draft required. */ }
  syncRecipient();
  form.addEventListener('input', e => {
    ++serial; controller?.abort();
    const match = e.target.name?.match(/^(amount|percent)_(\d+)$/);
    if (match) { form.elements.namedItem(`basis_${match[2]}`).value = match[1]; form.elements.namedItem('method').value = 'custom'; }
    remember(); clearTimeout(timer); timer = setTimeout(preview, 180);
  });
  form.addEventListener('change', e => { ++serial; controller?.abort(); syncRecipient(); remember(); if (e.target.tagName === 'SELECT') { clearTimeout(timer); preview(); } });
  form.addEventListener('submit', () => { clearTimeout(timer); ++serial; controller?.abort(); remember(); });
})();
