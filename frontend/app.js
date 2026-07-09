/* ============================================================
   CapturadorM3 — Panel Frontend (vanilla JS)
   ============================================================ */
'use strict';

const API = '';  // same origin

const $ = (id) => document.getElementById(id);

const state = {
  files: [],
  jobId: null,
  records: [],
  filter: 'all',
  search: '',
  pollHandle: null,
  lastJobStatus: null,
};

const ACCEPTED_EXT = ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.tiff', '.tif'];
const MAX_FILES = 100;

const fmtCLP = (n) => (n === null || n === undefined)
  ? '—'
  : '$' + Number(n).toLocaleString('es-CL');
const fmtDate = (s) => s ? s : '—';
const fmtShort = (s, n = 40) => (s && s.length > n ? s.slice(0, n - 1) + '…' : (s || '—'));
const escapeHTML = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#039;');


/* ============================================================
   TOASTS
   ============================================================ */
function toast(msg, type = 'info', ttl = 4000) {
  const wrap = $('toasts');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icon = type === 'ok' ? '✅' : type === 'warn' ? '⚠️' : type === 'err' ? '❌' : 'ℹ️';
  el.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-msg">${escapeHTML(msg)}</span>
    <button class="toast-close" aria-label="Cerrar">✕</button>
  `;
  el.querySelector('.toast-close').addEventListener('click', () => el.remove());
  wrap.appendChild(el);
  if (ttl > 0) setTimeout(() => el.remove(), ttl);
}


/* ============================================================
   API HELPERS
   ============================================================ */
async function api(path, opts = {}) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j); } catch (_) {}
    throw new Error(`${r.status} · ${detail}`);
  }
  return r.json();
}


/* ============================================================
   HEALTH
   ============================================================ */
async function checkHealth() {
  const pill = $('api-status');
  const text = $('api-status-text');
  try {
    const j = await api('/api/v1/health');
    pill.classList.remove('err');
    pill.classList.add('ok');
    text.textContent = '● API OK';
    $('redis-status').textContent = `redis: ${j.redis ? '✓' : '✗'}`;
    $('db-status').textContent = `db: ${j.db ? '✓' : '✗'}`;
    $('version-info').textContent = `v${j.version}`;
  } catch (e) {
    pill.classList.remove('ok');
    pill.classList.add('err');
    text.textContent = '● API caída';
    $('redis-status').textContent = 'redis: ?';
    $('db-status').textContent = 'db: ?';
  }
}


/* ============================================================
   STEPPER NAVIGATION
   ============================================================ */
const STEP_NAMES = { 1: 'Cargar', 2: 'Procesar', 3: 'Revisar', 4: 'Entregar' };

function goToStep(n) {
  document.querySelectorAll('.step-card').forEach((el) => el.classList.remove('active'));
  const card = $(`step-${n}`);
  if (card) card.classList.add('active');

  document.querySelectorAll('.stepper .step').forEach((el) => {
    const s = parseInt(el.dataset.step, 10);
    el.classList.toggle('active', s === n);
    el.classList.toggle('done', s < n);
  });

  // Scroll suave al paso
  card?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function markStepDone(n) {
  const el = document.querySelector(`.stepper .step[data-step="${n}"]`);
  if (el) el.classList.add('done');
}


/* ============================================================
   DROPZONE & FILE LIST
   ============================================================ */
function setupDropzone() {
  const dz = $('dropzone');
  const input = $('file-input');

  dz.addEventListener('click', () => input.click());
  dz.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });

  ['dragenter', 'dragover'].forEach((evt) => {
    dz.addEventListener(evt, (e) => {
      e.preventDefault(); e.stopPropagation();
      dz.classList.add('dragover');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    dz.addEventListener(evt, (e) => {
      e.preventDefault(); e.stopPropagation();
      if (evt === 'dragleave' && e.target !== dz) return;
      dz.classList.remove('dragover');
    });
  });
  dz.addEventListener('drop', (e) => {
    handleFiles(e.dataTransfer.files);
  });

  input.addEventListener('change', (e) => {
    handleFiles(e.target.files);
    e.target.value = '';  // permitir re-selección
  });

  $('btn-clear').addEventListener('click', () => {
    state.files = [];
    renderFileList();
    toast('Lista limpiada', 'info', 2000);
  });

  $('btn-process').addEventListener('click', startProcess);
  $('btn-new-batch').addEventListener('click', () => {
    state.files = [];
    state.records = [];
    state.jobId = null;
    renderFileList();
    $('progress-fill').style.width = '0%';
    $('progress-fill').classList.remove('done', 'err');
    $('log-stream').innerHTML = '';
    $('quarantine-list').innerHTML = '';
    $('quarantine-section').hidden = true;
    goToStep(1);
  });
}

function handleFiles(fileList) {
  const arr = Array.from(fileList || []);
  let added = 0;
  for (const f of arr) {
    if (state.files.length >= MAX_FILES) {
      toast(`Máximo ${MAX_FILES} archivos por lote`, 'warn');
      break;
    }
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
    if (!ACCEPTED_EXT.includes(ext)) {
      toast(`Formato no soportado: ${f.name}`, 'warn');
      continue;
    }
    if (state.files.some((x) => x.name === f.name && x.size === f.size)) continue;
    state.files.push(f);
    added++;
  }
  if (added > 0) toast(`${added} archivo${added > 1 ? 's' : ''} agregado${added > 1 ? 's' : ''}`, 'ok', 2000);
  renderFileList();
}

function renderFileList() {
  const wrap = $('file-list-wrap');
  const list = $('file-list');
  const btn = $('btn-process');
  const btnClear = $('btn-clear');

  if (state.files.length === 0) {
    wrap.hidden = true;
    list.innerHTML = '';
    btn.disabled = true;
    btnClear.disabled = true;
    return;
  }

  wrap.hidden = false;
  btn.disabled = false;
  btnClear.disabled = false;

  $('file-count-label').textContent = `${state.files.length} archivo${state.files.length > 1 ? 's' : ''}`;
  const totalSize = state.files.reduce((s, f) => s + f.size, 0);
  $('file-list-meta').textContent = `· ${(totalSize / 1024 / 1024).toFixed(2)} MB total`;

  list.innerHTML = state.files.map((f, i) => {
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    const isPdf = ext === 'pdf';
    const size = f.size < 1024 * 1024
      ? `${(f.size / 1024).toFixed(1)} KB`
      : `${(f.size / 1024 / 1024).toFixed(2)} MB`;
    return `
      <li data-idx="${i}">
        <div class="file-icon ${isPdf ? 'pdf' : 'img'}">${isPdf ? 'PDF' : 'IMG'}</div>
        <div class="file-info">
          <div class="file-name" title="${escapeHTML(f.name)}">${escapeHTML(f.name)}</div>
          <div class="file-meta">${size} · ${ext.toUpperCase()}</div>
        </div>
        <button class="file-remove" data-remove="${i}" title="Quitar">✕</button>
      </li>
    `;
  }).join('');

  list.querySelectorAll('[data-remove]').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const i = parseInt(b.dataset.remove, 10);
      state.files.splice(i, 1);
      renderFileList();
    });
  });
}


/* ============================================================
   PROCESSING
   ============================================================ */
function setProgress(pct, text, sub) {
  $('progress-fill').style.width = `${Math.max(0, Math.min(100, pct))}%`;
  $('progress-pct').textContent = `${Math.round(pct)}%`;
  if (text) $('processing-main').textContent = text;
  if (sub !== undefined) $('processing-sub').textContent = sub;
}

function logLine(text, kind = '') {
  const stream = $('log-stream');
  const ts = new Date().toLocaleTimeString('es-CL', { hour12: false });
  const line = document.createElement('span');
  line.className = `log-line ${kind}`;
  line.innerHTML = `<span class="ts">${ts}</span>${escapeHTML(text)}`;
  stream.appendChild(line);
  stream.scrollTop = stream.scrollHeight;
}

async function startProcess() {
  if (state.files.length === 0) return;

  const useAsync = $('mode-async').checked;
  const formData = new FormData();
  for (const f of state.files) formData.append('files', f);

  // Reset estado visual
  $('progress-fill').classList.remove('done', 'err');
  $('log-stream').innerHTML = '';
  $('btn-download-excel').disabled = true;

  goToStep(2);
  setProgress(2, 'Subiendo archivos…', `Job: pendiente · ${state.files.length} archivos`);
  logLine(`Subiendo ${state.files.length} archivo(s)…`);

  try {
    if (useAsync) {
      await processAsync(formData);
    } else {
      await processSync(formData);
    }
  } catch (e) {
    setProgress(100, `Error: ${e.message}`, '');
    $('progress-fill').classList.add('err');
    logLine(`ERROR: ${e.message}`, 'err');
    toast(`Error: ${e.message}`, 'err', 6000);
  }
}

async function processSync(formData) {
  setProgress(30, 'Procesando OCR (modo síncrono)…', `Esto puede tardar unos segundos por archivo`);
  logLine('Llamando a /api/v1/ocr/upload-batch (síncrono)…');

  const t0 = performance.now();
  const j = await api('/api/v1/ocr/upload-batch', { method: 'POST', body: formData });
  const dt = ((performance.now() - t0) / 1000).toFixed(1);

  state.jobId = j.job_id;
  state.records = j.records || [];

  setProgress(100, `¡Listo! ${state.records.length} documentos procesados`, `Job ${j.job_id} · ${dt}s`);
  $('progress-fill').classList.add('done');
  logLine(`✓ Job ${j.job_id} completado en ${dt}s (processed=${j.processed}, failed=${j.failed})`, 'ok');
  logLine(`→ ${state.records.length} registros extraídos`, 'ok');

  finishJob();
}

async function processAsync(formData) {
  setProgress(15, 'Encolando en Redis…', 'Subiendo archivos al servidor');
  logLine('Llamando a /api/v1/ocr/queue (asíncrono vía arq/Redis)…');

  const j = await api('/api/v1/ocr/queue', { method: 'POST', body: formData });
  state.jobId = j.job_id;
  setProgress(25, 'Encolado. Procesando en background…', `Job ${j.job_id}`);
  logLine(`✓ Job ${j.job_id} encolado (${j.total_files} archivos)`, 'ok');
  toast(`Job ${j.job_id} encolado`, 'ok');

  // Polling
  startPolling(j.job_id);
}

function startPolling(jobId) {
  stopPolling();
  let attempts = 0;
  const tick = async () => {
    attempts++;
    try {
      const j = await api(`/api/v1/jobs/${jobId}`);
      state.lastJobStatus = j;
      const total = j.total_files || 1;
      const done = (j.processed || 0) + (j.failed || 0);
      const pct = Math.min(95, (done / total) * 100);
      setProgress(pct, `Procesando ${done} / ${total}…`, `Job ${jobId} · status: ${j.status}`);
      logLine(`Polling #${attempts}: ${done}/${total} (status=${j.status})`);

      if (j.status === 'done') {
        stopPolling();
        // Cargar registros finales
        const records = await api(`/api/v1/jobs/${jobId}`);
        state.records = records.records || [];
        setProgress(100, `¡Listo! ${state.records.length} documentos procesados`, `Job ${jobId} · Excel generado`);
        $('progress-fill').classList.add('done');
        logLine(`✓ Job completado: processed=${j.processed}, failed=${j.failed}`, 'ok');
        if (j.output_path) logLine(`📄 Excel: ${j.output_path}`, 'ok');
        finishJob();
      } else if (j.status === 'failed') {
        stopPolling();
        setProgress(100, `Job falló: ${j.error || 'error desconocido'}`, `Job ${jobId}`);
        $('progress-fill').classList.add('err');
        logLine(`✗ Job falló: ${j.error}`, 'err');
        toast(`Job ${jobId} falló`, 'err', 6000);
      }
    } catch (e) {
      logLine(`Polling error: ${e.message}`, 'warn');
      if (attempts > 120) { stopPolling(); toast('Polling agotado tras 2 min', 'err'); }
    }
  };
  tick();
  state.pollHandle = setInterval(tick, 1500);
}

function stopPolling() {
  if (state.pollHandle) {
    clearInterval(state.pollHandle);
    state.pollHandle = null;
  }
}

function finishJob() {
  markStepDone(2);
  renderResults();
  renderDelivery();
  loadJobs();  // refrescar sidebar

  // Auto-avanzar al paso 3 después de una breve pausa
  setTimeout(() => goToStep(3), 800);
}


/* ============================================================
   RESULTS (Paso 3)
   ============================================================ */
function renderResults() {
  const tbody = $('results-tbody');
  const counts = { all: state.records.length, OK: 0, QUARANTINE: 0, REJECTED: 0 };

  state.records.forEach((r) => {
    counts[r.estado] = (counts[r.estado] || 0) + 1;
  });

  $('count-all').textContent = counts.all;
  $('count-ok').textContent = counts.OK || 0;
  $('count-q').textContent = counts.QUARANTINE || 0;
  $('count-rj').textContent = counts.REJECTED || 0;

  const visible = getFilteredRecords();
  if (visible.length === 0) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="9">${
      state.records.length === 0 ? 'Aún no hay resultados.' : 'Sin resultados para el filtro actual.'
    }</td></tr>`;
    return;
  }

  tbody.innerHTML = visible.map((r, i) => {
    const estado = r.estado || 'QUARANTINE';
    const cls = estado === 'OK' ? 'row-ok' : estado === 'REJECTED' ? 'row-rj' : 'row-q';
    const badgeCls = estado === 'OK' ? 'ok' : estado === 'REJECTED' ? 'rj' : 'q';
    return `
      <tr class="${cls}" data-idx="${state.records.indexOf(r)}">
        <td title="${escapeHTML(r.archivo || '')}">${escapeHTML(fmtShort(r.archivo || '—', 36))}</td>
        <td>${escapeHTML((r.doc_type || '—').toString())}</td>
        <td>${escapeHTML(fmtDate(r.fecha_emision))}</td>
        <td class="num">${escapeHTML(r.folio ?? '—')}</td>
        <td class="mono">${escapeHTML(fmtShort(r.rut_emisor || '—', 18))}</td>
        <td title="${escapeHTML(r.razon_social || '')}">${escapeHTML(fmtShort(r.razon_social || '—', 30))}</td>
        <td class="num">${escapeHTML(fmtCLP(r.total))}</td>
        <td><span class="badge ${badgeCls}">${estado}</span></td>
        <td><button class="btn-ghost btn-xs" data-detail="${state.records.indexOf(r)}">Ver →</button></td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('tr[data-idx]').forEach((tr) => {
    tr.addEventListener('click', () => {
      openDetail(state.records[parseInt(tr.dataset.idx, 10)]);
    });
  });
}

function getFilteredRecords() {
  let arr = state.records.slice();
  if (state.filter !== 'all') {
    arr = arr.filter((r) => (r.estado || 'QUARANTINE') === state.filter);
  }
  if (state.search) {
    const q = state.search.toLowerCase();
    arr = arr.filter((r) =>
      (r.archivo || '').toLowerCase().includes(q) ||
      (r.rut_emisor || '').toLowerCase().includes(q) ||
      (r.razon_social || '').toLowerCase().includes(q) ||
      (r.folio || '').toString().includes(q)
    );
  }
  return arr;
}

function setupFilters() {
  document.querySelectorAll('.filter-chips .chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chips .chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      state.filter = chip.dataset.filter;
      renderResults();
    });
  });

  $('search-input').addEventListener('input', (e) => {
    state.search = e.target.value.trim();
    renderResults();
  });
}


/* ============================================================
   DETAIL MODAL
   ============================================================ */
function openDetail(rec) {
  if (!rec) return;
  $('modal-title').textContent = rec.archivo || 'Documento';

  const fields = [
    ['Tipo de documento', rec.doc_type, false],
    ['RUT emisor', rec.rut_emisor, true],
    ['Razón social', rec.razon_social, false],
    ['Giro', rec.giro, false],
    ['Folio', rec.folio, true],
    ['Fecha emisión', rec.fecha_emision, false],
    ['RUT receptor', rec.rut_receptor, true],
    ['Neto', rec.neto, true],
    ['IVA', rec.iva, true],
    ['Exento', rec.exento, true],
    ['Total', rec.total, true],
    ['Estado', rec.estado, false],
    ['Motivo revisión', rec.motivo_revision, false],
  ];

  const completeness = typeof rec.completeness === 'number'
    ? Math.round(rec.completeness * 100)
    : (rec.estado === 'OK' ? 100 : (rec.estado === 'REJECTED' ? 0 : 50));

  const fieldsHTML = fields.map(([label, value, mono]) => {
    const empty = value === null || value === undefined || value === '';
    return `
      <div class="detail-field">
        <div class="detail-label">${escapeHTML(label)}</div>
        <div class="detail-value ${mono ? 'mono' : ''} ${empty ? 'empty' : ''}">${
          empty ? '— no detectado —' : escapeHTML(typeof value === 'number' && label.match(/Total|Neto|IVA|Exento/) ? fmtCLP(value) : value)
        }</div>
      </div>
    `;
  }).join('');

  const meta = [
    rec.ocr_engine ? `engine: ${rec.ocr_engine}` : null,
    typeof rec.ocr_avg_score === 'number' ? `score: ${rec.ocr_avg_score.toFixed(3)}` : null,
    Array.isArray(rec.missing) && rec.missing.length ? `missing: ${rec.missing.join(', ')}` : null,
  ].filter(Boolean);

  $('modal-body').innerHTML = `
    <div class="detail-completeness">
      <div class="completeness-head">
        <span>Completitud de extracción</span>
        <span><strong>${completeness}%</strong></span>
      </div>
      <div class="completeness-bar">
        <div class="completeness-fill" style="width:${completeness}%"></div>
      </div>
    </div>
    <div class="detail-grid">${fieldsHTML}</div>
    ${meta.length ? `<div class="detail-meta">${meta.map((m) => `<span class="meta-chip">${escapeHTML(m)}</span>`).join('')}</div>` : ''}
  `;

  $('modal-backdrop').hidden = false;
}

function setupModals() {
  $('modal-close').addEventListener('click', () => { $('modal-backdrop').hidden = true; });
  $('modal-backdrop').addEventListener('click', (e) => {
    if (e.target.id === 'modal-backdrop') $('modal-backdrop').hidden = true;
  });

  // RUT modal
  const rutModal = $('rut-modal');
  $('btn-validate-rut').addEventListener('click', () => {
    rutModal.hidden = false;
    setTimeout(() => $('rut-input').focus(), 50);
  });
  $('rut-modal-close').addEventListener('click', () => { rutModal.hidden = true; });
  rutModal.addEventListener('click', (e) => {
    if (e.target.id === 'rut-modal') rutModal.hidden = true;
  });

  $('btn-validate').addEventListener('click', validateRut);
  $('rut-input').addEventListener('keypress', (e) => { if (e.key === 'Enter') validateRut(); });
}

async function validateRut() {
  const rut = $('rut-input').value.trim();
  const out = $('rut-result');
  if (!rut) { out.innerHTML = ''; return; }
  out.innerHTML = '<span class="muted">Validando…</span>';
  try {
    const j = await api('/api/v1/validate/rut', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rut }),
    });
    if (j.valido) {
      out.innerHTML = `<div class="ok">✓ <strong>Válido</strong> · Canónico: <code>${escapeHTML(j.canonico)}</code> · DV calculado: <code>${escapeHTML(j.dv_calculado || '—')}</code></div>`;
    } else {
      out.innerHTML = `<div class="bad">✗ <strong>Inválido</strong> · Input: <code>${escapeHTML(j.rut_input)}</code> · DV esperado: <code>${escapeHTML(j.dv_calculado || '—')}</code></div>`;
    }
  } catch (e) {
    out.innerHTML = `<div class="bad">Error: ${escapeHTML(e.message)}</div>`;
  }
}


/* ============================================================
   DELIVERY (Paso 4)
   ============================================================ */
function renderDelivery() {
  const counts = { OK: 0, QUARANTINE: 0, REJECTED: 0 };
  const sums = { OK: 0, QUARANTINE: 0, REJECTED: 0 };

  state.records.forEach((r) => {
    const e = r.estado || 'QUARANTINE';
    counts[e] = (counts[e] || 0) + 1;
    if (typeof r.total === 'number') sums[e] = (sums[e] || 0) + r.total;
  });

  $('metric-ok').textContent = counts.OK;
  $('metric-q').textContent = counts.QUARANTINE;
  $('metric-rj').textContent = counts.REJECTED;
  $('metric-total').textContent = state.records.length;

  $('metric-ok-sum').textContent = `Suma: ${fmtCLP(sums.OK)}`;
  $('metric-q-sum').textContent = `Suma: ${fmtCLP(sums.QUARANTINE)}`;
  $('metric-total-sum').textContent = `Σ ${fmtCLP(sums.OK + sums.QUARANTINE + sums.REJECTED)}`;

  // Quarantine list
  const qRecords = state.records.filter((r) => (r.estado || 'QUARANTINE') === 'QUARANTINE');
  if (qRecords.length > 0) {
    $('quarantine-section').hidden = false;
    $('quarantine-list').innerHTML = qRecords.map((r) => `
      <li>
        <span class="qfile" title="${escapeHTML(r.archivo)}">${escapeHTML(r.archivo)}</span>
        <span class="muted">${escapeHTML(r.motivo_revision || 'revisión manual')}</span>
      </li>
    `).join('');
  } else {
    $('quarantine-section').hidden = true;
  }

  // Download button: solo si el job tiene output_path (modo async)
  const btnDl = $('btn-download-excel');
  if (state.jobId && state.lastJobStatus && state.lastJobStatus.output_path) {
    btnDl.disabled = false;
    btnDl.dataset.jobId = state.jobId;
  } else if (state.jobId) {
    // Modo sync: igual descargar (job_detail tiene records)
    btnDl.disabled = false;
    btnDl.dataset.jobId = state.jobId;
  } else {
    btnDl.disabled = true;
  }

  markStepDone(3);
}

$('btn-download-excel').addEventListener('click', async () => {
  const jobId = $('btn-download-excel').dataset.jobId;
  if (!jobId) {
    toast('No hay job para descargar', 'warn');
    return;
  }
  try {
    logLine(`Descargando Excel del job ${jobId}…`);
    const r = await fetch(`${API}/api/v1/jobs/${jobId}/download`);
    if (!r.ok) {
      // Si falla el endpoint /download (modo sync que no escribió Excel), intentar construir uno
      const err = await r.json().catch(() => ({}));
      if (err.detail && err.detail.includes('no encontrado')) {
        toast('Este job no generó Excel. Use /docs para revisar el flujo.', 'warn', 6000);
        return;
      }
      throw new Error(err.detail || r.statusText);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Rendicion_${jobId}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast('Excel descargado', 'ok');
    logLine(`✓ Excel descargado`, 'ok');
  } catch (e) {
    toast(`Error al descargar: ${e.message}`, 'err', 6000);
    logLine(`✗ Error descarga: ${e.message}`, 'err');
  }
});


/* ============================================================
   JOBS HISTORY (sidebar)
   ============================================================ */
async function loadJobs() {
  try {
    const jobs = await api('/api/v1/jobs?limit=20');
    const list = $('jobs-list');
    if (!jobs.length) {
      list.innerHTML = '<li class="jobs-empty">Sin jobs aún.</li>';
      return;
    }
    list.innerHTML = jobs.map((j) => {
      const cls = j.status === 'done' ? 'ok'
        : j.status === 'failed' ? 'err'
        : j.status === 'processing' ? 'warn' : '';
      const date = new Date(j.created_at).toLocaleString('es-CL', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
      });
      const active = j.id === state.jobId ? 'active' : '';
      return `
        <li class="job-item ${active}" data-job="${j.id}">
          <div class="job-item-head">
            <span class="job-id">${escapeHTML(j.id)}</span>
            <span class="badge ${cls === 'ok' ? 'ok' : cls === 'err' ? 'rj' : 'q'}">${j.status}</span>
          </div>
          <div class="job-meta">
            <span>${date}</span>
            <span class="dot-sep">·</span>
            <span>${j.processed || 0}/${j.total_files || 0}</span>
            ${j.failed ? `<span class="dot-sep">·</span><span style="color:var(--c-rj)">${j.failed} ✗</span>` : ''}
          </div>
        </li>
      `;
    }).join('');

    list.querySelectorAll('.job-item').forEach((item) => {
      item.addEventListener('click', () => loadJob(item.dataset.job));
    });
  } catch (e) {
    console.warn('loadJobs error:', e);
  }
}

async function loadJob(jobId) {
  try {
    logLine(`Cargando job ${jobId}…`);
    const j = await api(`/api/v1/jobs/${jobId}`);
    state.jobId = j.id;
    state.lastJobStatus = j;
    state.records = j.records || [];

    // Marcar como activo en sidebar
    document.querySelectorAll('.job-item').forEach((el) => {
      el.classList.toggle('active', el.dataset.job === jobId);
    });

    if (state.records.length > 0) {
      setProgress(100, `Job ${jobId} cargado (${state.records.length} registros)`, `status: ${j.status}`);
      $('progress-fill').classList.add('done');
      renderResults();
      renderDelivery();
      markStepDone(2);
      goToStep(3);
      toast(`Job ${jobId} cargado`, 'ok', 2000);
    } else if (j.status === 'processing' || j.status === 'queued') {
      // Reanudar polling si aún está corriendo
      setProgress(((j.processed + j.failed) / Math.max(1, j.total_files)) * 100,
        `Procesando ${j.processed + j.failed}/${j.total_files}…`, `Job ${jobId}`);
      goToStep(2);
      startPolling(jobId);
      toast(`Reanudando seguimiento del job ${jobId}`, 'info');
    } else {
      toast(`Job ${jobId} sin registros extraídos`, 'warn');
    }
  } catch (e) {
    toast(`Error cargando job: ${e.message}`, 'err');
  }
}

$('btn-refresh-jobs').addEventListener('click', () => {
  loadJobs();
  toast('Historial refrescado', 'info', 1500);
});


/* ============================================================
   INIT
   ============================================================ */
function init() {
  setupDropzone();
  setupFilters();
  setupModals();
  checkHealth();
  setInterval(checkHealth, 15000);
  loadJobs();

  // Atajos de teclado
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      $('modal-backdrop').hidden = true;
      $('rut-modal').hidden = true;
    }
  });

  // Click en el stepper para navegar a un paso ya completado
  document.querySelectorAll('.stepper .step').forEach((el) => {
    el.addEventListener('click', () => {
      const n = parseInt(el.dataset.step, 10);
      // Permitir navegar hacia atrás o al paso actual
      const activeStep = parseInt(document.querySelector('.stepper .step.active')?.dataset.step || '1', 10);
      if (n <= activeStep || el.classList.contains('done')) {
        goToStep(n);
      }
    });
    el.style.cursor = 'pointer';
  });

  logLine('Panel CapturadorM3 listo');
  console.log('CapturadorM3 panel inicializado');
}

document.addEventListener('DOMContentLoaded', init);