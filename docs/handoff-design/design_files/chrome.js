/* Operator AI Scoped — chrome injector
   Cada página declara <body data-step="contexto" data-state="A" data-audit="off">.
   Este script inyecta sidebar + topbar + (audit) + quote-header + stepper.
   Mantiene cada HTML compacto y standalone (al cargar lo necesario inline).
*/

(function () {
  const body = document.body;
  const ds = body.dataset;
  const step = ds.step || 'contexto';     // brief | contexto | despiece | paso4 | pdf | dashboard | detail
  const state = (ds.state || 'A').toUpperCase();
  const audit = ds.audit === 'on';
  const showChrome = ds.chrome !== 'off';

  if (!showChrome) return;

  // Steps fuera del flujo de creación (dashboard, detail) NO renderizan stepper ni qhead
  const isFlowStep = ['brief','contexto','despiece','paso4','pdf'].includes(step);

  // Quote identity (lee data-attrs del body, fallback a genérico)
  const hasQuoteAttrs = ('quoteId' in ds) || ('quoteClient' in ds) || ('quoteProject' in ds);
  const quoteId      = ds.quoteId      || '';
  const quoteClient  = ds.quoteClient  || '';
  const quoteProject = ds.quoteProject || '';
  const hasContent = quoteId || quoteClient || quoteProject;

  function crumbLabel () {
    if (hasContent) {
      const parts = [quoteId, quoteClient, quoteProject].filter(Boolean);
      return parts.join(' · ');
    }
    return 'Nuevo';
  }

  function qheadTitle () {
    if (hasContent) {
      if (quoteProject && quoteClient) return `${quoteProject} — ${quoteClient}`;
      if (quoteProject) return quoteProject;
      if (quoteClient)  return quoteClient;
    }
    return 'Presupuesto sin guardar';
  }

  function qheadSub () {
    if (hasContent && quoteId) return `${quoteId} · creado hoy · borrador`;
    if (hasContent && !quoteId) return 'borrador · sin asignar';
    return 'borrador · sin asignar';
  }

  const STEPS = [
    { id: 'brief',    n: 1, label: 'Brief',     done: step !== 'brief' && ['contexto','despiece','paso4','pdf'].includes(step), current: step === 'brief' },
    { id: 'contexto', n: 2, label: 'Contexto',  done: ['despiece','paso4','pdf'].includes(step), current: step === 'contexto' },
    { id: 'despiece', n: 3, label: 'Despiece',  done: ['paso4','pdf'].includes(step), current: step === 'despiece' },
    { id: 'paso4',    n: 4, label: 'Cálculo',   done: step === 'pdf', current: step === 'paso4' },
    { id: 'pdf',      n: 5, label: 'PDF',       done: false, current: step === 'pdf' },
  ];

  const stepperHtml = `
    <nav class="stepper">
      ${STEPS.map(s => `
        <div class="step ${s.done ? 'done' : ''} ${s.current ? 'now' : ''}">
          <span class="n">${s.done ? '' : s.n}</span>
          <span>${s.label}</span>
        </div>
      `).join('')}
    </nav>
  `;

  const sidebarHtml = `
    <aside class="sidebar">
      <div class="brand"><span class="dot"></span>D'Angelo Operator</div>

      <div class="nav-h">Principal</div>
      <div class="nav-i on">
        <span>Presupuestos</span>
        <span class="badge">18</span>
      </div>
      <div class="nav-i">
        <span>Clientes</span>
        <span class="badge">42</span>
      </div>

      <div class="nav-h">Sistema</div>
      <div class="nav-i"><span>Catálogo</span></div>
      <div class="nav-i"><span>Configuración</span></div>

      <div style="flex:1"></div>

      <div class="nav-i" style="border:1px dashed var(--line-strong); justify-content:center; color:var(--accent);">
        + Nuevo presupuesto
      </div>
      <div style="display:flex; align-items:center; gap:10px; padding:10px; margin-top:6px;">
        <div style="width:28px; height:28px; border-radius:999px; background:var(--surface-2); display:grid; place-items:center; font-family:var(--mono); font-size:11px; color:var(--ink-soft);">M</div>
        <div style="font-size:12px; color:var(--ink-soft);">Marina · operadora</div>
      </div>
    </aside>
  `;

  const auditHtml = audit ? `
    <div class="audit">
      <span class="pulse"></span>
      <span><strong>DEBUG · auditoría activa</strong></span>
      <span style="opacity:0.7;">model: claude-sonnet-4 · tokens: 1.842 · latency: 4.2s · trace_id: q_8f2a</span>
      <a href="#" style="margin-left:auto;">ver auditoría completa →</a>
    </div>
  ` : '';

  // Topbar crumbs varían: dashboard mostraba "Presupuestos" como current
  const crumbsHtml = isFlowStep
    ? `<span>Presupuestos</span><span class="sep">/</span><span class="now">${crumbLabel()}</span>`
    : (step === 'detail'
        ? `<span>Presupuestos</span><span class="sep">/</span><span class="now">Detalle</span>`
        : `<span class="now">Presupuestos</span>`);

  const topbarHtml = `
    ${auditHtml}
    <div class="topbar">
      <div class="crumbs">
        ${crumbsHtml}
      </div>
      <div class="right">
        <button class="ico-btn" title="Notificaciones">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9zM10 21a2 2 0 004 0"/></svg>
        </button>
        <button class="ico-btn" title="Ajustes">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 00-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 00-2-1.2L14 3h-4l-.5 2.6a7 7 0 00-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 005 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 002 1.2L10 21h4l.5-2.6a7 7 0 002-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z"/></svg>
        </button>
      </div>
    </div>
  `;

  const qheadHtml = `
    <header class="qhead">
      <div class="meta">
        <div class="eyebrow">Presupuesto</div>
        <h1>${qheadTitle()}</h1>
        <div class="sub">${qheadSub()}</div>
      </div>
      <div class="actions">
        <button class="btn ghost sm">Auditoría</button>
        <button class="btn ghost sm">Compartir</button>
        <button class="btn-copy-log" data-bug-report title="Copia un reporte técnico de este mockup al clipboard">⧉ copy log</button>
      </div>
    </header>
  `;

  const main = body.querySelector('.main');
  if (!main) return;
  const page = main.parentElement; // .page

  const sidebar = document.createElement('div');
  sidebar.innerHTML = sidebarHtml;
  page.insertBefore(sidebar.firstElementChild, main);

  // Solo flow steps inyectan qhead (header de quote) + stepper
  // Dashboard / detail tienen su propio header inline en el HTML
  const headerHtml = isFlowStep ? (qheadHtml + stepperHtml) : '';
  main.insertAdjacentHTML('afterbegin', topbarHtml + headerHtml);
})();
