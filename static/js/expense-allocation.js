/* Progressive enhancement only: Python owns every financial calculation. */
(() => {
  const form = document.querySelector('[data-allocation-form]');
  if (!form || !form.querySelector('[data-allocation-panel]')) return;
  let revision = 0;
  let timer;
  let controller;
  let navigating = false;

  function invalidate() {
    revision += 1;
    clearTimeout(timer);
    controller?.abort();
  }
  async function preview(expected) {
    controller = new AbortController();
    const data = new FormData(form);
    data.set('action', 'calculate');
    try {
      // Buttons named "action" shadow HTMLFormElement.action through named access.
      const response = await fetch(form.getAttribute('action') || window.location.href, {
        method: 'POST', body: data, signal: controller.signal,
        credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}
      });
      if (!response.ok) throw new Error('Calculation unavailable');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (expected !== revision || navigating) return;
      const panel = page.querySelector('[data-allocation-panel]');
      if (!panel) throw new Error('Calculation unavailable');
      const focus = document.activeElement;
      const id = focus?.id;
      const start = focus?.selectionStart;
      const end = focus?.selectionEnd;
      form.querySelector('[data-allocation-panel]').replaceWith(panel);
      const restored = id && document.getElementById(id);
      restored?.focus({preventScroll: true});
      if (restored && start != null && restored.type === 'text') {
        restored.setSelectionRange(start, end);
      }
    } catch (error) {
      if (error.name === 'AbortError' || expected !== revision || navigating) return;
      const status = form.querySelector('[data-allocation-status]');
      if (status) status.textContent = 'Live calculation is unavailable. Use Update calculation or Review allocation. Your entries have not been saved.';
    }
  }
  form.addEventListener('input', event => {
    const basis = event.target.dataset.allocationInput;
    if (!basis) {
      // Do not let an in-flight response replace a note being edited.
      invalidate();
      const expected = revision;
      timer = setTimeout(() => preview(expected), 400);
      return;
    }
    event.target.closest('[data-allocation-row]').querySelector('[data-allocation-basis]').value = basis;
    invalidate();
    const expected = revision;
    timer = setTimeout(() => preview(expected), 400);
  });
  form.addEventListener('change', event => {
    if (event.target.name !== 'remainder' && !event.target.hasAttribute('data-allocation-basis')) return;
    invalidate();
    preview(revision);
  });
  form.addEventListener('submit', () => {
    navigating = true;
    invalidate();
  });
})();
