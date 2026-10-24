/* Progressive enhancement for the thread. The server remains authoritative for scope and reads. */
(() => {
  const stream = document.querySelector('[data-conversation-stream]');
  if (!stream) return;
  document.documentElement.classList.add('communications-enhanced');
  const status = document.querySelector('[data-update-status]');
  const readForm = document.querySelector('[data-read-form]');
  const composer = document.querySelector('[data-chat-composer]');
  const composerForm = composer?.querySelector('form');
  const input = composer?.querySelector('[data-chat-input]');
  const sendButton = composer?.querySelector('button[type="submit"]');
  const errorBox = composer?.querySelector('[data-composer-errors]');
  const newer = document.querySelector('[data-new-messages]');
  let busy = false;
  let sending = false;
  let stopped = false;

  const setStatus = text => { if (status) status.textContent = text; };
  const scrollToEnd = () => stream.scrollTo({top: stream.scrollHeight, behavior: 'smooth'});
  const nearEnd = () => stream.scrollHeight - stream.scrollTop - stream.clientHeight < 120;
  const showError = message => {
    if (!errorBox) return;
    errorBox.textContent = '';
    const p = document.createElement('p');
    p.className = 'composer-error';
    p.textContent = message;
    errorBox.append(p);
  };
  const clearError = () => { if (errorBox) errorBox.textContent = ''; };

  const readDisplayed = async receipt => {
    if (!readForm || !receipt || document.hidden) return;
    const field = readForm.querySelector('input[name="receipt"]');
    if (!field) return;
    field.value = receipt;
    const data = new FormData(readForm);
    await fetch(readForm.action, {method: 'POST', body: data, credentials: 'same-origin',
      headers: {'X-Requested-With': 'XMLHttpRequest'}});
  };

  let lastDay = stream.querySelector('.chat-day:last-of-type')?.textContent.trim() || '';
  const appendBatch = (batch, {announce = false} = {}) => {
    if (!batch) return 0;
    const stick = nearEnd();
    let added = 0;
    batch.childNodes.forEach(node => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.classList.contains('chat-day')) {
        const label = node.textContent.trim();
        if (label === lastDay) return;
        stream.append(node.cloneNode(true));
        lastDay = label;
        return;
      }
      if (node.matches('article[data-message-id]') && !document.getElementById(node.id)) {
        stream.append(node);
        added += 1;
      }
    });
    stream.dataset.lastId = batch.dataset.lastId || stream.dataset.lastId;
    const state = document.querySelector('[data-conversation-state]');
    if (state && batch.dataset.workState) state.textContent = batch.dataset.workState;
    if (added && stick) scrollToEnd();
    if (added && !stick && newer) newer.hidden = false;
    if (added && announce) setStatus(`${added} new message${added === 1 ? '' : 's'}.`);
    return added;
  };

  const initial = stream.querySelector('[data-message-batch]');
  if (stream.dataset.initialBottom === '1' && !location.hash) {
    requestAnimationFrame(() => { stream.scrollTop = stream.scrollHeight; });
  }
  if (initial) readDisplayed(initial.dataset.readReceipt).catch(() => {});

  const poll = async () => {
    if (busy || stopped || document.hidden || !stream.dataset.pollUrl) return;
    busy = true;
    try {
      const response = await fetch(`${stream.dataset.pollUrl}?after=${stream.dataset.lastId || 0}`,
        {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}});
      if (!response.ok || response.redirected) {
        stopped = true;
        setStatus('Updates paused. Reload to check your access.');
        return;
      }
      const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
      const batch = parsed.querySelector('[data-message-batch]');
      if (!batch || document.hidden) return;
      const added = appendBatch(batch, {announce: true});
      if (added) await readDisplayed(batch.dataset.readReceipt);
    } catch (_) {
      setStatus('Updates are temporarily unavailable. Your unsent message is unchanged.');
    } finally { busy = false; }
  };

  if (newer) newer.querySelector('button')?.addEventListener('click', () => {
    newer.hidden = true;
    scrollToEnd();
  });

  const grow = () => {
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  };
  input?.addEventListener('input', grow);
  grow();

  if (composerForm) {
    composerForm.addEventListener('submit', async event => {
      if (sending || !window.fetch || !window.FormData) return;
      event.preventDefault();
      const body = input?.value.trim() || '';
      const files = composerForm.querySelector('input[type="file"]')?.files;
      if (!body && (!files || !files.length)) return showError('Enter a message or attach a file.');
      clearError();
      sending = true;
      if (sendButton) sendButton.disabled = true;
      const temp = document.createElement('article');
      temp.className = 'chat-message mine chat-optimistic';
      temp.innerHTML = '<div class="chat-bubble"><p class="chat-author">You <span>Sending…</span></p><p class="chat-body"></p></div>';
      temp.querySelector('.chat-body').textContent = body || 'Attachment';
      stream.append(temp);
      scrollToEnd();
      try {
        const response = await fetch(composerForm.action, {
          method: 'POST', body: new FormData(composerForm), credentials: 'same-origin',
          headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        if (!response.ok) {
          const text = await response.text();
          const parsed = new DOMParser().parseFromString(text, 'text/html');
          const errors = [...parsed.querySelectorAll('.composer-error')].map(node => node.textContent.trim()).filter(Boolean);
          temp.remove();
          showError(errors[0] || 'The message was not sent. Check the fields and try again.');
          return;
        }
        const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
        const batch = parsed.querySelector('[data-message-batch]');
        temp.remove();
        appendBatch(batch, {announce: false});
        if (composerForm) {
          composerForm.reset();
          const token = composerForm.querySelector('input[name="token"]');
          if (token && window.crypto?.randomUUID) token.value = crypto.randomUUID();
          grow();
          input?.focus();
        }
        clearError();
        setStatus('Sent.');
        if (batch?.dataset.readReceipt) await readDisplayed(batch.dataset.readReceipt);
      } catch (_) {
        temp.remove();
        showError('The message could not be sent. Your draft is still here; try again.');
      } finally {
        sending = false;
        if (sendButton) sendButton.disabled = false;
      }
    });

    input?.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        composerForm.requestSubmit();
      }
    });
  }

  const quickReply = document.querySelector('[data-quick-reply-select]');
  if (quickReply) {
    quickReply.addEventListener('change', () => {
      const option = quickReply.selectedOptions[0];
      if (!option || !option.dataset.body) return;
      if (input) { input.value = option.dataset.body; grow(); input.focus(); }
      quickReply.value = '';
    });
  }

  setInterval(poll, 4000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
})();
