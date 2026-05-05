/* Operator AI Scoped — bug report library
   Captura console.error + window.onerror, expone botón copy-log
   que arma payload (mockup_id, data_attrs, console errors, step fields)
   y lo copia al clipboard.

   Cada mockup puede definir window.__stepSpecificFields = () => ({...})
   para incluir contexto del paso (ej: chips seleccionados, valores form).
*/
(function () {
  'use strict';

  const errors = [];
  const MAX_ERRORS = 50;

  // Capture runtime errors
  window.addEventListener('error', (ev) => {
    if (errors.length >= MAX_ERRORS) return;
    errors.push({
      type: 'error',
      message: ev.message || String(ev.error || ''),
      source: ev.filename || '',
      line: ev.lineno || 0,
      col: ev.colno || 0,
      stack: ev.error && ev.error.stack ? ev.error.stack : '',
      ts: new Date().toISOString(),
    });
  });

  // Capture unhandled promise rejections
  window.addEventListener('unhandledrejection', (ev) => {
    if (errors.length >= MAX_ERRORS) return;
    errors.push({
      type: 'unhandledrejection',
      message: String(ev.reason && ev.reason.message ? ev.reason.message : ev.reason),
      stack: ev.reason && ev.reason.stack ? ev.reason.stack : '',
      ts: new Date().toISOString(),
    });
  });

  // Wrap console.error (without losing console output)
  const origError = console.error.bind(console);
  console.error = function (...args) {
    if (errors.length < MAX_ERRORS) {
      errors.push({
        type: 'console.error',
        message: args.map(a => {
          try { return typeof a === 'string' ? a : JSON.stringify(a); }
          catch (_) { return String(a); }
        }).join(' '),
        ts: new Date().toISOString(),
      });
    }
    return origError(...args);
  };

  function getMockupId () {
    // Prefer file basename
    const path = (location.pathname || '').split('/').pop() || '';
    return path.replace(/\.html$/, '').replace(/-standalone$/, '') || 'unknown';
  }

  function getDataAttrs () {
    const ds = document.body.dataset;
    const out = {};
    for (const key of Object.keys(ds)) out[key] = ds[key];
    return out;
  }

  function getStepFields () {
    if (typeof window.__stepSpecificFields === 'function') {
      try { return window.__stepSpecificFields() || {}; }
      catch (e) { return { __step_fields_error: String(e) }; }
    }
    return {};
  }

  function buildBugReport () {
    return {
      timestamp: new Date().toISOString(),
      mockup_id: getMockupId(),
      url: location.href,
      title: document.title,
      viewport: { w: window.innerWidth, h: window.innerHeight },
      ua: navigator.userAgent,
      data_attrs: getDataAttrs(),
      step_fields: getStepFields(),
      console_errors: errors.slice(),
    };
  }

  function formatBugReport (report) {
    const r = report || buildBugReport();
    const lines = [];
    lines.push('# Bug Report — Operator AI Scoped');
    lines.push('');
    lines.push(`**Mockup:** ${r.mockup_id}`);
    lines.push(`**Timestamp:** ${r.timestamp}`);
    lines.push(`**URL:** ${r.url}`);
    lines.push(`**Title:** ${r.title}`);
    lines.push(`**Viewport:** ${r.viewport.w}×${r.viewport.h}`);
    lines.push(`**UA:** ${r.ua}`);
    lines.push('');
    lines.push('## data-attrs');
    lines.push('```json');
    lines.push(JSON.stringify(r.data_attrs, null, 2));
    lines.push('```');
    lines.push('');
    lines.push('## step_fields');
    lines.push('```json');
    lines.push(JSON.stringify(r.step_fields, null, 2));
    lines.push('```');
    lines.push('');
    lines.push(`## console_errors (${r.console_errors.length})`);
    if (r.console_errors.length === 0) {
      lines.push('_none_');
    } else {
      lines.push('```json');
      lines.push(JSON.stringify(r.console_errors, null, 2));
      lines.push('```');
    }
    return lines.join('\n');
  }

  async function copyLog (btn) {
    const report = buildBugReport();
    const text = formatBugReport(report);
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        // Fallback: textarea + execCommand
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setBtnState(btn, 'copied');
      return { ok: true, text };
    } catch (e) {
      console.error('[bug-report] copy failed', e);
      setBtnState(btn, 'error');
      return { ok: false, error: e };
    }
  }

  function setBtnState (btn, state) {
    if (!btn) return;
    btn.classList.remove('is-copied', 'is-error');
    const originalLabel = btn.dataset.idleLabel || btn.textContent;
    if (!btn.dataset.idleLabel) btn.dataset.idleLabel = originalLabel;
    if (state === 'copied') {
      btn.classList.add('is-copied');
      btn.textContent = '✓ Copiado';
    } else if (state === 'error') {
      btn.classList.add('is-error');
      btn.textContent = '⚠ Error';
    } else {
      btn.textContent = btn.dataset.idleLabel;
    }
    if (state === 'copied' || state === 'error') {
      clearTimeout(btn.__resetTimer);
      btn.__resetTimer = setTimeout(() => setBtnState(btn, 'idle'), 1800);
    }
  }

  // Auto-bind: any element with [data-bug-report] is a copy-log trigger
  function bindButtons () {
    document.querySelectorAll('[data-bug-report]').forEach((el) => {
      if (el.__bugBound) return;
      el.__bugBound = true;
      el.addEventListener('click', (ev) => {
        ev.preventDefault();
        copyLog(el);
      });
    });
  }

  // Run on DOM ready + after chrome.js injects (chrome.js runs sync at end of body)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindButtons);
  } else {
    bindButtons();
  }
  // Re-scan after a tick in case chrome.js injected the button
  setTimeout(bindButtons, 0);
  setTimeout(bindButtons, 100);

  // Expose API
  window.bugReport = {
    build: buildBugReport,
    format: formatBugReport,
    copy: copyLog,
    bind: bindButtons,
    _errors: errors,
  };
})();
