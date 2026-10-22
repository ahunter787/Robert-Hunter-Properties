/* Optional open-thread refresh. The server remains authoritative for scope and reads. */
(() => {
  const stream = document.querySelector('[data-conversation-stream]');
  if (!stream) return;
  const status = document.querySelector('[data-update-status]');
  const readForm = document.querySelector('[data-read-form]');
  let busy = false;
  let stopped = false;
  const readDisplayed = async (receipt) => {
    if (!readForm || !receipt || document.hidden) return;
    readForm.elements.receipt.value = receipt;
    readForm.querySelector('button').disabled = false;
    const data = new FormData(readForm);
    await fetch(readForm.action, {method: 'POST', body: data, credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest'}});
  };
  const initial = stream.querySelector('[data-message-batch]');
  if (initial) readDisplayed(initial.dataset.readReceipt).catch(() => {});
  const poll = async () => {
    if (busy || stopped || document.hidden || !stream.dataset.pollUrl) return;
    busy = true;
    try {
      const response = await fetch(`${stream.dataset.pollUrl}?after=${stream.dataset.lastId || 0}`,
        {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (!response.ok || response.redirected) {
        stopped = true;
        status.textContent = 'Updates paused. Reload to check your access.';
        return;
      }
      const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
      const batch = parsed.querySelector('[data-message-batch]');
      if (!batch || document.hidden) return;
      const nearEnd = innerHeight + scrollY >= document.documentElement.scrollHeight - 180;
      let added = 0;
      batch.querySelectorAll('article[id]').forEach(article => {
        if (!document.getElementById(article.id)) { stream.append(article); added++; }
      });
      stream.dataset.lastId = batch.dataset.lastId;
      document.querySelector('[data-conversation-state]').textContent = batch.dataset.workState;
      if (added) {
        status.textContent = `${added} new message${added === 1 ? '' : 's'}.`;
        if (nearEnd && !document.activeElement.closest('form')) stream.lastElementChild?.scrollIntoView({block: 'end'});
        await readDisplayed(batch.dataset.readReceipt);
      }
    } catch (_) {
      status.textContent = 'Updates are temporarily unavailable. Your unsent message is unchanged.';
    } finally { busy = false; }
  };
  const quickReply = document.querySelector('[data-quick-reply-select]');
  if (quickReply) {
    quickReply.addEventListener('change', () => {
      const option = quickReply.selectedOptions[0];
      if (!option || !option.dataset.body) return;
      const body = document.querySelector('textarea[name="body"]');
      if (body) { body.value = option.dataset.body; body.focus(); }
      quickReply.value = '';
    });
  }
  setInterval(poll, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();
