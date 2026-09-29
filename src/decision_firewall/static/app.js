document.querySelectorAll('[data-clear-search]').forEach(button => {
  const input = document.getElementById('q');
  input.addEventListener('input', () => { button.hidden = !input.value; });
  button.addEventListener('click', event => { event.preventDefault(); input.value = ''; button.hidden = true; input.focus(); input.form.requestSubmit(); });
});
document.querySelectorAll('[data-review-form]').forEach(form => {
  const reason = form.querySelector('textarea');
  const status = form.querySelector('.form-status');
  let dirty = false;
  reason.addEventListener('input', () => { dirty = true; reason.style.height = 'auto'; reason.style.height = `${reason.scrollHeight}px`; });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  form.addEventListener('submit', event => {
    if (form.dataset.busy) { event.preventDefault(); return; }
    if (reason.value.trim().length < 3) {
      event.preventDefault(); reason.setAttribute('aria-invalid','true');
      status.textContent = 'Enter a reason with at least three characters.'; reason.focus(); return;
    }
    dirty = false; form.dataset.busy = 'true'; form.setAttribute('aria-busy','true');
    status.textContent = 'Saving review and checking policy…';
    // Preserve the clicked submitter's value before disabling duplicate submissions.
    const decision = document.createElement('input'); decision.type='hidden'; decision.name='decision'; decision.value=event.submitter.value; form.append(decision);
    form.querySelectorAll('button').forEach(button => { button.disabled=true; });
  });
});
document.getElementById('form-error')?.focus();

