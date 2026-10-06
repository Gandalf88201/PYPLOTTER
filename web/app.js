// PyPlotter interface. Talks only to the local Python service (same origin, session token).
'use strict';

const TOKEN = document.querySelector('meta[name="pp-token"]').content;
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};

const state = {
  lang: store.get('pp-lang') || ((navigator.language || 'en').toLowerCase().startsWith('it') ? 'it' : 'en'),
  meta: null, status: null, defaults: null, spec: null,
  file: null, dataset: null, source: null, recommend: [], history: [],
  renderSeq: 0, renderCtrl: null, renderTimer: null, fitDpi: 96, tab: 'figure', busyJob: null,
  axesGeom: [],                                     // where the axes lie in the figure drawn last (X-Axes)
  views: [], view: null, mainSpec: null, mainDataset: null, mainRecommend: null,   // see "figure copies"
};

// Number formatting follows the interface language (1.161 in Italian, 1,161 in English).
const LOCALE = () => (state.lang === 'it' ? 'it-IT' : 'en-US');

const LINESTYLES = ['-', '--', ':', '-.'];
const MARKERS = ['', 'o', 's', '^', 'v', 'D', 'x', '+', '*', '.'];
const SCALES = ['linear', 'log', 'symlog', 'logit'];
const LEGEND_LOCS = ['best', 'upper right', 'upper left', 'lower left', 'lower right', 'center left', 'center right',
  'upper center', 'lower center', 'outside right', 'outside top', 'outside bottom'];
const PREFERRED_FONTS = ['Arial', 'Helvetica', 'Helvetica Neue', 'Times New Roman', 'Times', 'Calibri', 'Cambria',
  'Garamond', 'Georgia', 'Palatino', 'Liberation Sans', 'Liberation Serif', 'DejaVu Sans', 'DejaVu Serif', 'STIXGeneral', 'CMU Serif'];
const KIND_OPTS = {
  scatter: ['colorbar', 'vmin', 'vmax'], area: ['stacked'], errorbar: ['error_style', 'capsize'],
  regression: ['fit', 'fit_degree'], polar: ['polar_degrees'], bar: ['stacked', 'bar_width', 'agg', 'capsize'],
  barh: ['stacked', 'bar_width', 'agg', 'capsize'], box: ['show_fliers'], pie: ['agg'], hist: ['bins', 'density', 'stacked'],
  kde: ['fill'], heatmap: ['annotate', 'agg', 'colorbar', 'vmin', 'vmax'], contour: ['levels', 'contour_lines', 'colorbar', 'vmin', 'vmax'],
  hexbin: ['gridsize', 'colorbar'], hist2d: ['bins', 'density', 'colorbar'],
};
const OPT_DEF = {
  bins: { type: 'number', min: 2, step: 1 }, density: { type: 'check' }, stacked: { type: 'check' }, fill: { type: 'check' },
  levels: { type: 'number', min: 2, step: 1 }, contour_lines: { type: 'check' }, gridsize: { type: 'number', min: 5, step: 5 },
  fit: { type: 'select', options: ['linear', 'poly', 'exp', 'log', 'power'], prefix: 'fit.' },
  fit_degree: { type: 'number', min: 1, max: 9, step: 1 }, annotate: { type: 'check' }, capsize: { type: 'number', min: 0, step: 0.5 },
  error_style: { type: 'select', options: ['bars', 'band'], prefix: 'err.' }, colorbar: { type: 'check' },
  vmin: { type: 'nullable' }, vmax: { type: 'nullable' }, polar_degrees: { type: 'check' }, bar_width: { type: 'number', min: 0.1, max: 1, step: 0.05 },
  agg: { type: 'select', options: ['mean', 'median', 'sum', 'count', 'max', 'min'], prefix: 'agg.' }, show_fliers: { type: 'check' },
};
const UNIT_MM = { mm: 1, cm: 10, in: 25.4 };
const KIND_GROUPS = ['xy', 'cat', 'dist', 'map', 'multi'];

// ------------------------------------------------------------------ i18n
function t(key, vars) {
  const dict = window.I18N[state.lang] || window.I18N.en;
  let s = dict[key] ?? window.I18N.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m));
  return s;
}
// A figure that cannot be drawn: the server's message, in the interface language when it has a key.
function specMessage(e) {
  const key = e.data && e.data.key && 'error.' + e.data.key;
  if (!key || !(key in window.I18N.en)) return e.message;
  const vars = Object.fromEntries(Object.entries(e.data.values || {})
    .map(([k, v]) => [k, typeof v === 'number' ? v.toLocaleString(LOCALE()) : v]));
  return t(key, vars);
}
function applyI18n(root = document) {
  document.documentElement.lang = state.lang;
  $$('[data-i18n]', root).forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-title]', root).forEach(el => { el.title = t(el.dataset.i18nTitle); });
  $$('[data-i18n-placeholder]', root).forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $$('.seg [data-lang]').forEach(b => b.classList.toggle('active', b.dataset.lang === state.lang));
}
function setLang(lang) {
  state.lang = lang;
  store.set('pp-lang', lang);
  applyI18n();
  if (state.meta) { buildStaticSelects(); buildKindGallery(); buildKindOptions(); buildMapping(false); buildSeries(); updateHints(); updateFigInfo(); }
  if ($('#modulesDialog').open) renderModules();
  if (window.Analysis) { window.Analysis.relabel(); window.Analysis.updateDerived(); }
  if (window.Files) Files.render();
  renderViewTabs();
  if (state.dataset) scheduleRender();
}

// ------------------------------------------------------------------ theme
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('pp-theme', theme); } catch (e) { /* ignore */ }
}

// ------------------------------------------------------------------ API
class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.code = data.code; this.data = data; }
}
async function api(path, body, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body), signal: opts.signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(t('error.network'), 0, { code: 'network' });
  }
  if (!res.ok) {
    let data = {};
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (data.code === 'token') reloadForNewSession();
    throw new ApiError(data.error || res.statusText, res.status, data);
  }
  if (opts.raw) return res;
  return res.json();
}

// The service was restarted with another token: reload once to pick up the new page.
function reloadForNewSession() {
  let last = 0;
  try { last = Number(sessionStorage.getItem('pp-reload') || 0); } catch (e) { /* ignore */ }
  if (Date.now() - last < 10000) return;          // avoid a reload loop
  try { sessionStorage.setItem('pp-reload', String(Date.now())); } catch (e) { /* ignore */ }
  location.reload();
}

// ------------------------------------------------------------------ toasts
function toast(msg, err = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), err ? 7000 : 3500);
}

// ------------------------------------------------------------------ object path helpers
const getPath = (obj, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
function setPath(obj, path, value) {
  const keys = path.split('.');
  let o = obj;
  keys.slice(0, -1).forEach(k => { if (typeof o[k] !== 'object' || o[k] === null) o[k] = {}; o = o[k]; });
  o[keys[keys.length - 1]] = value;
}
const clone = o => JSON.parse(JSON.stringify(o));
function merge(base, over) {
  const out = clone(base);
  for (const [k, v] of Object.entries(over || {})) {
    if (v && typeof v === 'object' && !Array.isArray(v) && out[k] && typeof out[k] === 'object' && !Array.isArray(out[k])) out[k] = merge(out[k], v);
    else out[k] = v;
  }
  return out;
}

// ------------------------------------------------------------------ modules / installs
const installedMap = () => Object.fromEntries((state.status?.modules || []).map(m => [m.id, m]));
const missingOf = ids => { const m = installedMap(); return [...new Set(ids)].filter(id => m[id] && !m[id].installed); };
const kindNeeds = kind => missingOf(state.meta.kinds[kind]?.requires || []);

async function refreshStatus() {
  state.status = await api('/api/status');
  const updates = state.status.modules.filter(m => m.update && m.installed).length;
  const broken = state.status.modules.filter(m => m.installed && m.works === false).length;
  $('#updatesBadge').hidden = !(updates || broken);
  $('#updatesBadge').textContent = broken || updates;
  $('#updatesBadge').classList.toggle('danger', !!broken);
  const restart = state.status.restart_required;
  $('#restartBanner').hidden = !restart;
  $('#app').classList.toggle('with-banner', restart);
  return state.status;
}

function phaseText(job) {
  if (job.state === 'error') return t('phase.error', { error: job.error });
  if (job.state === 'cancelled') return t('phase.cancelled');
  return t('phase.' + job.phase, { detail: job.detail || '' });
}

function setBar(box, frac) {
  box.hidden = false;
  box.querySelector('.bar').style.width = Math.round(frac * 100) + '%';
}

async function runInstall(ids, upgrade, onUpdate, reinstall = false) {
  let job = await api('/api/modules/install', { ids, upgrade, reinstall });
  state.busyJob = job.id;
  while (job.state === 'running') {
    onUpdate(job);
    await new Promise(r => setTimeout(r, 400));
    job = await api('/api/jobs/' + job.id);
  }
  onUpdate(job);
  state.busyJob = null;
  await refreshStatus();
  return job;
}

// Ask to install missing modules; resolves true when they are installed.
function ensureModules(ids, reasonKey = 'install.reason.feature', vars = {}) {
  const need = missingOf(ids);
  if (!need.length) return Promise.resolve(true);
  const dlg = $('#installDialog');
  const mods = installedMap();
  $('#installReason').textContent = t(reasonKey, vars);
  $('#installList').innerHTML = '';
  need.forEach(id => {
    const m = mods[id];
    const li = document.createElement('li');
    li.innerHTML = `<b></b> <span class="lic"></span><small></small>`;
    li.querySelector('b').textContent = m.pip;
    li.querySelector('.lic').textContent = m.license;
    li.querySelector('small').textContent = (m.description[state.lang] || m.description.en || '') + ' ' + t('install.size');
    $('#installList').append(li);
  });
  const bar = $('#installProgress');
  bar.hidden = true;
  $('#installPhase').textContent = '';
  $('#installLogBox').hidden = true;
  const go = $('#installGo');
  go.disabled = false;
  go.textContent = t('install.button');
  return new Promise(resolve => {
    let running = false;
    let done = false;
    const finish = ok => { if (done) return; done = true; dlg.close(); resolve(ok); };
    go.onclick = async ev => {
      ev.preventDefault();
      if (running) return;
      running = true;
      go.disabled = true;
      try {
        const job = await runInstall(need, false, j => {
          setBar(bar, j.progress);
          $('#installPhase').textContent = phaseText(j);
        });
        if (job.state === 'done') { setBar(bar, 1); setTimeout(() => finish(true), 450); return; }
        $('#installLog').textContent = (job.log || []).join('\n');
        $('#installLogBox').hidden = !(job.log || []).length;
        go.disabled = false;
        go.textContent = t('setup.retry');
      } catch (e) {
        $('#installPhase').textContent = e.message;
        go.disabled = false;
      }
      running = false;
    };
    $('#installCancel').onclick = async ev => {
      ev.preventDefault();
      if (running && state.busyJob) { await api(`/api/jobs/${state.busyJob}/cancel`, {}).catch(() => {}); }
      finish(false);
    };
    dlg.onclose = () => finish(false);
    dlg.showModal();
  });
}

// ------------------------------------------------------------------ first start
async function showSetup() {
  $('#setup').hidden = false;
  $('#app').hidden = true;
  $('#setupPython').textContent = t('setup.python', { version: state.status.python, path: state.status.executable });
  const btn = $('#btnSetup');
  btn.onclick = async () => {
    btn.disabled = true;
    const bar = $('#setupProgress');
    setBar(bar, 0);
    try {
      const core = state.status.modules.filter(m => m.core && (!m.installed || m.outdated)).map(m => m.id);
      const job = await runInstall(core, state.status.modules.some(m => m.core && m.outdated), j => {
        setBar(bar, j.progress);
        $('#setupPhase').textContent = phaseText(j);
      });
      if (job.state === 'done' && state.status.core_ready) {
        $('#setup').hidden = true;
        return start();
      }
      $('#setupPhase').textContent = phaseText(job);
    } catch (e) {
      $('#setupPhase').textContent = e.message;
    }
    btn.disabled = false;
    btn.textContent = t('setup.retry');
  };
}

// ------------------------------------------------------------------ static selects
function fillSelect(sel, items, current) {
  sel.innerHTML = '';
  items.forEach(([value, label, group]) => {
    let parent = sel;
    if (group) {
      parent = sel.querySelector(`optgroup[data-g="${group}"]`);
      if (!parent) { parent = document.createElement('optgroup'); parent.label = t('cmapgrp.' + group); parent.dataset.g = group; sel.append(parent); }
    }
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    parent.append(o);
  });
  if (current !== undefined) sel.value = current;
}

function buildStaticSelects() {
  const m = state.meta;
  fillSelect($('#styleSelect'), Object.keys(m.styles).map(k => [k, t('style.' + k) + (missingOf(m.styles[k].requires).length ? ' ↓' : '')]));
  fillSelect($('#paletteSelect'), [...Object.keys(m.palettes), 'style'].map(k => [k, t('pal.' + k)]));
  const cm = [];
  Object.entries(m.colormaps).forEach(([g, names]) => names.forEach(n => cm.push([n, n.replace('cmc.', ''), g])));
  fillSelect($('#cmapSelect'), cm);
  $$('.ls-select').forEach(s => fillSelect(s, LINESTYLES.map(v => [v, t('ls.' + v)])));
  $$('.marker-select').forEach(s => fillSelect(s, MARKERS.map(v => [v, t('mk.' + v)])));
  $$('.scale-select').forEach(s => fillSelect(s, SCALES.map(v => [v, t('scale.' + v)])));
  fillSelect($('#legendLoc'), LEGEND_LOCS.map(v => [v, t('loc.' + v)]));
  const fonts = m.fonts || [];
  const pref = PREFERRED_FONTS.filter(f => fonts.includes(f));
  fillSelect($('#fontSelect'), [['', t('text.font_default')], ...pref.map(f => [f, f]), ...fonts.filter(f => !pref.includes(f)).map(f => [f, f])]);
  fillSelect($('#sizePreset'), [['', t('fig.custom')], ...Object.entries(m.size_presets).map(([k, [w]]) => [k, `${t('preset.' + k)} · ${w} mm`])]);
  fillSelect($('#exportFormat'), Object.keys(m.export_formats).map(k => [k, t('fmt.' + k) + (missingOf(m.export_formats[k].requires).length ? ' ↓' : '')]),
    store.get('pp-export-format', 'pdf'));
  syncControls();
  updatePalettePreview();
}

function paletteColors(palette = state.spec.style.palette) {
  const fixed = state.meta.palettes[palette];
  if (fixed && fixed.length) return fixed;
  const pv = state.meta.palette_previews || {};
  return (palette === 'style' ? (pv.style || {})[state.spec.style.base] : pv[palette]) || [];
}

function updatePalettePreview() {
  const pal = paletteColors();
  $('#paletteSwatches').innerHTML = pal.slice(0, 10).map(c => `<span style="background:${c}"></span>`).join('');
}

// ------------------------------------------------------------------ spec <-> controls
function readControl(el) {
  const type = el.dataset.type;
  if (el.type === 'checkbox') return el.checked;
  const v = el.value;
  if (type === 'number') return v === '' ? null : Number(v);
  if (type === 'nullable') return v.trim() === '' ? null : (isNaN(Number(v)) ? v.trim() : Number(v));
  return v;
}
function writeControl(el, value) {
  if (el.type === 'checkbox') el.checked = !!value;
  else el.value = value ?? '';
}
function syncControls() {
  $$('[data-path]').forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  const f = state.spec.figure;
  const preset = Object.entries(state.meta.size_presets).find(([, [w, h]]) =>
    Math.abs(w - f.width * UNIT_MM[f.units]) < 0.05 && Math.abs(h - f.height * UNIT_MM[f.units]) < 0.05);
  $('#sizePreset').value = preset ? preset[0] : '';
}

function onControlChange(ev) {
  const el = ev.target;
  if (!el.dataset || !el.dataset.path) return;
  const path = el.dataset.path;
  const value = readControl(el);
  const old = getPath(state.spec, path);
  if (path === 'figure.units') return changeUnits(old, value);
  setPath(state.spec, path, value);
  if (path === 'style.palette') { updatePalettePreview(); buildSeries(); }
  if (path === 'style.base') updatePalettePreview();
  if (path === 'figure.width' || path === 'figure.height') syncControls();
  if (path === 'style.base' || path === 'style.cmap') {
    const need = path === 'style.base' ? state.meta.styles[value]?.requires || [] : (String(value).startsWith('cmc.') ? ['cmcrameri'] : []);
    if (missingOf(need).length) {
      ensureModules(need).then(ok => {
        if (!ok) { setPath(state.spec, path, old); writeControl(el, old); }
        buildStaticSelects();
        scheduleRender();
      });
      return;
    }
  }
  saveStyle();
  updateFigInfo();
  scheduleRender(ev.type === 'input' && el.type === 'text' ? 450 : 200);
}

function changeUnits(from, to) {
  const f = state.spec.figure;
  const k = UNIT_MM[from] / UNIT_MM[to];
  f.width = +(f.width * k).toFixed(to === 'in' ? 3 : 2);
  f.height = +(f.height * k).toFixed(to === 'in' ? 3 : 2);
  f.units = to;
  syncControls();
  saveStyle();
  updateFigInfo();
}

const STYLE_KEYS = ['figure', 'style', 'axes', 'legend', 'text'];
function styleSnapshot() {
  const s = {};
  STYLE_KEYS.forEach(k => { s[k] = clone(state.spec[k]); });
  ['title', 'xlabel', 'ylabel', 'y2label', 'zlabel'].forEach(k => delete s.text[k]);
  ['xmin', 'xmax', 'ymin', 'ymax', 'y2min', 'y2max'].forEach(k => delete s.axes[k]);
  delete s.style.vmin; delete s.style.vmax;
  return s;
}
function saveStyle() { store.set('pp-style', styleSnapshot()); }

// ------------------------------------------------------------------ kinds gallery
function buildKindGallery() {
  const box = $('#kindGallery');
  box.innerHTML = '';
  const recTop = new Set(state.recommend.slice(0, 3).map(r => r.kind));
  KIND_GROUPS.forEach((g, gi) => {
    if (gi) box.append(Object.assign(document.createElement('span'), { className: 'kind-sep' }));
    Object.entries(state.meta.kinds).filter(([, k]) => k.group === g).forEach(([name]) => {
      const b = document.createElement('button');
      b.className = 'kind';
      b.dataset.kind = name;
      b.classList.toggle('active', state.spec.kind === name);
      b.classList.toggle('rec', recTop.has(name));
      b.classList.toggle('needs', kindNeeds(name).length > 0);
      b.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${window.KIND_ICONS[name] || ''}</svg><span></span>`;
      b.querySelector('span').textContent = t('kind.' + name);
      const rec = state.recommend.find(r => r.kind === name);
      b.title = t('kind.' + name) + (rec ? ` — ${t('rec.reason.' + rec.reason)}` : '');
      b.onclick = () => setKind(name);
      box.append(b);
    });
  });
  const active = box.querySelector('.kind.active');
  if (active) box.scrollLeft = Math.max(0, active.offsetLeft - box.clientWidth / 2 + active.offsetWidth / 2);
}

async function setKind(kind) {
  const need = kindNeeds(kind);
  if (need.length && !(await ensureModules(need))) return;
  state.spec.kind = kind;
  if (['corr', 'pairplot'].includes(kind) && state.spec.y.length < 2 && state.dataset) {
    state.spec.y = state.dataset.columns.filter(c => c.kind === 'numeric').slice(0, 5).map(c => c.name);
  }
  buildKindGallery();
  buildKindOptions();
  buildMapping(false);
  updateHints();
  scheduleRender(0);
}

function buildKindOptions() {
  const box = $('#kindOptions');
  box.innerHTML = '';
  const opts = KIND_OPTS[state.spec.kind] || [];
  const wrap = document.createElement('div');
  wrap.className = 'grid2';
  opts.forEach(name => {
    const def = OPT_DEF[name];
    const path = 'style.' + name;
    if (def.type === 'check') {
      const lab = document.createElement('label');
      lab.className = 'check';
      lab.style.gridColumn = '1 / -1';
      lab.innerHTML = `<input type="checkbox" data-path="${path}"><span></span>`;
      lab.querySelector('span').textContent = t('opt.' + name);
      box.append(lab);
      return;
    }
    const f = document.createElement('div');
    f.className = 'field';
    const label = document.createElement('label');
    label.textContent = t('opt.' + name);
    f.append(label);
    let input;
    if (def.type === 'select') {
      input = document.createElement('select');
      fillSelect(input, def.options.map(o => [o, t(def.prefix + o)]));
    } else {
      input = document.createElement('input');
      input.type = def.type === 'nullable' ? 'text' : 'number';
      input.placeholder = 'auto';
      ['min', 'max', 'step'].forEach(a => { if (def[a] !== undefined) input[a] = def[a]; });
      input.dataset.type = def.type === 'nullable' ? 'nullable' : 'number';
    }
    input.dataset.path = path;
    f.append(input);
    wrap.append(f);
  });
  if (wrap.children.length) box.prepend(wrap);
  $$('[data-path]', box).forEach(el => writeControl(el, getPath(state.spec, el.dataset.path)));
  const usesCmap = ['heatmap', 'contour', 'hexbin', 'hist2d'].includes(state.spec.kind) || (state.spec.kind === 'scatter' && state.spec.z);
  $('[data-for="cmap"]').classList.toggle('disabled', !usesCmap);
}

// ------------------------------------------------------------------ mapping
function columnOptions(includeNone, noneLabel) {
  const cols = state.dataset ? state.dataset.columns : [];
  const items = includeNone ? [['', noneLabel || t('map.none')]] : [];
  return items.concat(cols.map(c => [c.name, c.name]));
}
const KIND_TAG = { numeric: '123', category: 'abc', datetime: 'date' };

// Choice of several columns, quick with tens of thousands of them: the rows are drawn a page at a
// time as the list scrolls. "All" and "None" act on the columns the filter shows; Shift+click ticks
// or clears a whole block; the filter also takes a range of numeric names (19600-19840) or of
// positions (#1-500). Returns {get, set}; onChange gets the chosen names in column order.
const PICK_PAGE = 200;
const PICK_TOOLS_FROM = 8;          // fewer columns: just the list

function columnPicker(box, { columns, selected, onChange, tags = true, pickable = c => c.kind === 'numeric' }) {
  box.innerHTML = '';
  box.classList.add('col-pick');
  const names = columns.map(c => c.name);
  const known = new Set(names);
  const sel = new Set(selected.filter(n => known.has(n)));
  let shown = names.map((_, i) => i);
  let drawn = 0;
  let anchor = null;                // position in `shown` of the last row ticked
  let shift = false;

  const list = document.createElement('div');
  list.className = 'checklist';
  list.title = t('pick.shift');
  const tools = document.createElement('div');
  tools.className = 'pick-tools';
  tools.innerHTML = '<input type="search" class="pick-filter" spellcheck="false"><button type="button" class="btn small pick-all"></button><button type="button" class="btn small pick-none"></button><span class="pick-count"></span>';
  const filter = tools.querySelector('.pick-filter');
  filter.placeholder = t('pick.filter');
  filter.title = t('pick.filter_help');
  tools.querySelector('.pick-all').textContent = t('pick.all');
  tools.querySelector('.pick-all').title = t('pick.all_help');
  tools.querySelector('.pick-none').textContent = t('pick.none');
  const count = tools.querySelector('.pick-count');
  if (names.length >= PICK_TOOLS_FROM) box.append(tools);
  box.append(list);

  const row = k => {
    const c = columns[shown[k]];
    const lab = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = c.name;
    cb.dataset.k = k;
    cb.checked = sel.has(c.name);
    const name = document.createElement('span');
    name.textContent = c.name;
    lab.append(cb, name);
    if (tags) {
      const tag = document.createElement('span');
      tag.className = 'kind-tag';
      tag.textContent = KIND_TAG[c.kind] || c.kind;
      lab.append(tag);
    }
    return lab;
  };
  const more = () => {
    const page = document.createDocumentFragment();
    const end = Math.min(shown.length, drawn + PICK_PAGE);
    for (let k = drawn; k < end; k++) page.append(row(k));
    drawn = end;
    list.append(page);
  };
  const redraw = () => {
    list.innerHTML = '';
    drawn = 0;
    anchor = null;
    if (!shown.length && names.length) list.innerHTML = `<p class="small muted">${t('pick.nomatch')}</p>`;
    more();
  };
  const showCount = () => {
    let n = 0;
    names.forEach(x => { if (sel.has(x)) n++; });
    count.textContent = t('pick.count', { n: n.toLocaleString(LOCALE()), total: names.length.toLocaleString(LOCALE()) }) +
      (shown.length < names.length ? ` · ${t('pick.shown', { n: shown.length.toLocaleString(LOCALE()) })}` : '');
  };
  const tickDrawn = () => $$('input', list).forEach(i => { i.checked = sel.has(i.value); });
  const changed = () => { showCount(); onChange(names.filter(n => sel.has(n))); };

  list.addEventListener('scroll', () => {
    if (drawn < shown.length && list.scrollTop + list.clientHeight > list.scrollHeight - 300) more();
  });
  list.addEventListener('pointerdown', e => { shift = e.shiftKey; }, true);
  list.addEventListener('keydown', e => { shift = e.shiftKey; }, true);
  list.addEventListener('change', e => {
    const k = Number(e.target.dataset.k);
    const on = e.target.checked;
    const [lo, hi] = shift && anchor !== null ? [Math.min(anchor, k), Math.max(anchor, k)] : [k, k];
    for (let j = lo; j <= hi; j++) on ? sel.add(names[shown[j]]) : sel.delete(names[shown[j]]);
    if (hi > lo) tickDrawn();
    anchor = k;
    shift = false;
    changed();
  });
  tools.querySelector('.pick-all').onclick = () => {
    shown.forEach(i => { if (pickable(columns[i])) sel.add(names[i]); });
    tickDrawn();
    changed();
  };
  tools.querySelector('.pick-none').onclick = () => {
    shown.forEach(i => sel.delete(names[i]));
    tickDrawn();
    changed();
  };
  let timer = null;
  filter.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      shown = matchColumns(names, filter.value);
      redraw();
      showCount();
    }, 120);
  };

  redraw();
  showCount();
  return {
    get: () => names.filter(n => sel.has(n)),
    set(list) { sel.clear(); list.forEach(n => { if (known.has(n)) sel.add(n); }); tickDrawn(); showCount(); },
  };
}

// Positions of the columns that match a filter: text in the name, or a range "a-b" (also a..b, a:b)
// of numeric names, or "#a-b" of positions counted from 1.
function matchColumns(names, query) {
  const q = query.trim();
  const all = names.map((_, i) => i);
  if (!q) return all;
  const low = q.toLocaleLowerCase();
  const text = i => names[i].toLocaleLowerCase().includes(low);
  const m = q.match(/^(#)?\s*(-?\d+(?:[.,]\d+)?)\s*(?:\.\.|[-–:])\s*(-?\d+(?:[.,]\d+)?)$/);
  if (!m) return all.filter(text);
  const [a, b] = [m[2], m[3]].map(v => Number(v.replace(',', '.')));
  const [lo, hi] = [Math.min(a, b), Math.max(a, b)];
  const inRange = m[1]
    ? i => i + 1 >= lo && i + 1 <= hi
    : i => { const s = names[i].trim(); const v = Number(s.replace(',', '.')); return s !== '' && Number.isFinite(v) && v >= lo && v <= hi; };
  return all.filter(i => inRange(i) || text(i));
}

function buildChecklist(box, selected, key) {
  box.picker = columnPicker(box, {
    columns: state.dataset?.columns || [],
    selected,
    pickable: c => c.kind === 'numeric' && c.name !== state.spec.x,
    onChange: list => {
      state.spec[key] = list;
      buildSeries();
      refreshRecommend();
      scheduleRender(0);
    },
  });
}

function buildMapping(rebuildLists = true) {
  if (!state.dataset) return;
  const s = state.spec;
  const inputs = state.meta.kinds[s.kind].inputs;
  const cat = ['box', 'violin', 'strip', 'swarm'].includes(s.kind);
  const dist = state.meta.kinds[s.kind].group === 'dist';
  $$('#mappingCard [data-role]').forEach(el => { el.hidden = !inputs.includes(el.dataset.role); });
  $('[data-role="y2"]').hidden = !state.meta.twin_kinds.includes(s.kind);
  $('[data-role="x"] label').textContent = cat ? t('map.groups') : t('map.x');
  $('[data-role="y"] label').textContent = (cat || dist) ? t('map.values') : t('map.y');
  const selects = { mapX: ['x', true, t('map.index')], mapHue: ['hue', true], mapZ: ['z', true], mapXerr: ['xerr', true], mapYerr: ['yerr', true] };
  Object.entries(selects).forEach(([id, [key, none, noneLabel]]) => {
    const sel = $('#' + id);
    fillSelect(sel, columnOptions(none, noneLabel), s[key] || '');
    sel.onchange = () => {
      s[key] = sel.value || null;
      if (key === 'z') buildKindOptions();
      if (key === 'hue') buildSeries();
      refreshRecommend();
      scheduleRender(0);
    };
  });
  if (rebuildLists || !$('#mapY').picker) {
    buildChecklist($('#mapY'), s.y, 'y');
    buildChecklist($('#mapY2'), s.y2, 'y2');
  } else {
    $('#mapY').picker.set(s.y);
  }
}

// ------------------------------------------------------------------ series styling
// Colour of a layer as the last figure drew it (null before the first render of this figure).
const drawnOverlayColor = o => (state.drawnOverlays && state.drawnOverlays.spec === state.spec && state.drawnOverlays.color[o.id]) || null;

// After a render: show in the Overlays panel the colours the layers really got.
function syncOverlayColors() {
  $$('#overlayList .overlay-row').forEach(row => {
    const o = (state.spec.overlays || []).find(x => x.id === row.dataset.id);
    const input = row.querySelector('input[type=color]');
    const real = o && drawnOverlayColor(o);
    if (real && document.activeElement !== input) input.value = real;
  });
}

function buildOverlays() {
  const list = state.spec.overlays || [];
  $('#overlayCard').hidden = !list.length;
  $('#overlayCount').textContent = list.length || '';
  const box = $('#overlayList');
  box.innerHTML = '';
  const pal = paletteColors();
  list.forEach((o, i) => {
    o.style = o.style || {};
    const row = document.createElement('div');
    row.className = 'overlay-row' + (o.hidden ? ' hidden-layer' : '');
    row.dataset.id = o.id;
    row.innerHTML = `<div class="src"></div><input type="color"><input type="text"><button class="reset" type="button">✕</button>
      <div class="opts"><select class="ls"></select><div class="mk-row"><select class="mk"></select><input type="number" class="ms" step="0.5" min="0"></div>
      <label class="check"><input type="checkbox" class="band"><span></span></label>
      <label class="check"><input type="checkbox" class="show"><span></span></label></div>`;
    row.querySelector('.src').textContent = o.source_name || '';
    const color = row.querySelector('input[type=color]');
    const fixed = /^#[0-9a-f]{6}$/i.test(o.style.color || '') ? o.style.color : null;
    color.value = fixed || drawnOverlayColor(o) || pal[(state.spec.y.length + i) % (pal.length || 1)] || '#000000';
    const label = row.querySelector('input[type=text]');
    label.value = o.label || '';
    const ls = row.querySelector('.ls');
    fillSelect(ls, [...LINESTYLES.map(v => [v, t('ls.' + v)]), ['none', t('ov.markers')]], o.style.linestyle || '-');
    // The layer's own markers (e.g. peak markers): shape and size, independent of the series' markers.
    const mk = row.querySelector('.mk');
    fillSelect(mk, MARKERS.map(v => [v, `${t('ov.marker')}: ${t('mk.' + v)}`]), o.style.marker || '');
    const ms = row.querySelector('.ms');
    ms.value = o.style.markersize ?? '';
    ms.placeholder = 'auto';
    ms.title = t('ov.marker_size');
    const band = row.querySelector('.band');
    band.checked = o.band !== false && !!(o.lo && o.hi);
    band.disabled = !(o.lo && o.hi);
    band.nextElementSibling.textContent = o.band_label ? `${t('ov.band')} (${o.band_label})` : t('ov.band');
    const show = row.querySelector('.show');
    show.checked = !o.hidden;
    show.nextElementSibling.textContent = t('ov.visible');
    color.oninput = () => { o.style.color = color.value; scheduleRender(250); };
    label.oninput = () => { o.label = label.value; scheduleRender(400); };
    ls.onchange = () => {
      o.style.linestyle = ls.value;
      if (ls.value === 'none' && !o.style.marker) { o.style.marker = 'o'; mk.value = 'o'; }   // something must show
      scheduleRender(0);
    };
    mk.onchange = () => {
      o.style.marker = mk.value || null;
      if (!mk.value && o.style.linestyle === 'none') { o.style.linestyle = '-'; ls.value = '-'; }
      scheduleRender(0);
    };
    ms.oninput = () => {
      if (ms.value === '' || !(Number(ms.value) >= 0)) delete o.style.markersize; else o.style.markersize = Number(ms.value);
      scheduleRender(300);
    };
    band.onchange = () => { o.band = band.checked; scheduleRender(0); };
    show.onchange = () => { o.hidden = !show.checked; row.classList.toggle('hidden-layer', o.hidden); scheduleRender(0); };
    const rm = row.querySelector('.reset');
    rm.title = t('ov.remove');
    rm.onclick = () => { state.spec.overlays.splice(i, 1); buildOverlays(); scheduleRender(0); };
    box.append(row);
  });
}

function newSession() {
  if (state.dataset && !confirm(t('new.confirm'))) return;
  clearDataset();
  state.spec = merge(state.defaults, store.get('pp-style', {}));
  state.spec.overlays = [];
  if (window.Analysis) window.Analysis.reset();
  Files.clear();
  setDataError('');
  $('#fileInput').value = '';
  $('#tableSelect').innerHTML = '';
  $('#seriesList').innerHTML = '';
  syncControls();
  buildKindGallery();
  buildKindOptions();
  buildOverlays();
  updateFigInfo();
  setTab('figure');
  toast(t('new.done'));
}

// The series the last figure really drew, in drawing order: [{key, label, color}] (sent by the server
// with each render). The Series panel shows exactly these rows and colours, so panel = figure.
function seriesDrawn(header) {
  let list = null;
  try { list = header ? JSON.parse(decodeURIComponent(header)) : null; } catch (e) { list = null; }
  if (!Array.isArray(list)) return;
  // Analysis layers: their real colours go to the Overlays panel.
  state.drawnOverlays = { spec: state.spec, color: Object.fromEntries(list.filter(e => e.overlay).map(e => [e.overlay, e.color])) };
  syncOverlayColors();
  list = list.filter(e => !e.overlay);
  state.drawn = { list, spec: state.spec };
  const box = $('#seriesList');
  // Other rows than the figure's series (categories, groups, another view): rebuild the panel,
  // unless the user is typing in it. In every case the swatches take the colours really drawn,
  // also when the panel was built (with a guess) before this render.
  const shown = $$('.series', box).map(r => r.dataset.key).join('\u0002');
  if (shown !== list.map(e => e.key).join('\u0002') && !box.contains(document.activeElement)) {
    buildSeriesRows();
    return;
  }
  const color = Object.fromEntries(list.map(e => [e.key, e.color]));
  $$('.series', box).forEach(row => {
    const input = row.querySelector('input[type=color]');
    if (color[row.dataset.key] && document.activeElement !== input) input.value = color[row.dataset.key];
  });
}

function buildSeries() {
  buildOverlays();
  buildSeriesRows();
}

// One row per series, as many as the figure reports colours for (plotting.ColorLog.MAX_SERIES).
const MAX_SERIES_ROWS = 200;

function buildSeriesRows() {
  const box = $('#seriesList');
  box.innerHTML = '';
  const s = state.spec;
  const cols = [...s.y, ...(state.meta.twin_kinds.includes(s.kind) ? s.y2 : [])];
  const extraAll = (window.Files && !viewDataset()) ? Files.extraSpec().flatMap(e =>
    e.y.map(c => ({ key: `${e.id}:${c}`, title: `${e.name} · ${c}` }))) : [];
  const extraRows = (s.layout || {}).mode !== 'panels' ? extraAll : [];
  const base = [...cols.map(c => ({ key: c, title: c })), ...extraRows];
  const titles = Object.fromEntries([...base, ...extraAll].map(r => [r.key, r.title]));
  const titleOf = key => titles[key] || (key.includes('::') ? key.split('::').map((k, i) => (i ? k : titles[k] || k)).join(' · ') : key);
  // After a render of this figure: its real series (groups and categories included) and colours.
  const drawn = state.drawn && state.drawn.spec === s ? state.drawn.list : null;
  if (drawn && !drawn.length) {        // drawn, but this kind of figure has no colour per series
    box.innerHTML = `<p class="small muted">${t('series.none')}</p>`;
    return;
  }
  const rows = drawn ? drawn.map(e => ({ key: e.key, title: titleOf(e.key), color: e.color })) : (s.hue ? [] : base);
  if (!rows.length) {
    box.innerHTML = `<p class="small muted">${t('series.empty')}</p>`;
    return;
  }
  const pal = paletteColors(s.style.palette);
  rows.slice(0, MAX_SERIES_ROWS).forEach(({ key: col, title, color: real }, i) => {
    const over = s.series[col] || {};
    const row = document.createElement('div');
    row.className = 'series';
    row.dataset.key = col;
    row.innerHTML = `<div class="name"><span></span><button class="reset" type="button"></button></div>
      <input type="color"><input type="text">
      <div class="opts"><select class="ls"></select><select class="mk"></select><input type="number" class="lw" step="0.1" min="0"></div>`;
    row.querySelector('.name span').textContent = title;
    row.querySelector('.reset').textContent = t('series.reset');
    const color = row.querySelector('input[type=color]');
    color.value = over.color || real || pal[i % (pal.length || 1)] || '#000000';
    const label = row.querySelector('input[type=text]');
    label.placeholder = title;
    label.title = t('series.label');
    label.value = over.label || '';
    const ls = row.querySelector('.ls');
    fillSelect(ls, [['', '—'], ...LINESTYLES.map(v => [v, t('ls.' + v)])], over.linestyle || '');
    const mk = row.querySelector('.mk');
    fillSelect(mk, [['__', '—'], ...MARKERS.map(v => [v, t('mk.' + v)])], over.marker === undefined ? '__' : over.marker);
    const lw = row.querySelector('.lw');
    lw.placeholder = String(s.style.linewidth);
    lw.value = over.linewidth ?? '';
    const update = () => {
      const o = {};
      if (color.dataset.touched || over.color) o.color = color.value;
      if (label.value) o.label = label.value;
      if (ls.value) o.linestyle = ls.value;
      if (mk.value !== '__') o.marker = mk.value;
      if (lw.value !== '') o.linewidth = Number(lw.value);
      if (Object.keys(o).length) s.series[col] = o; else delete s.series[col];
      scheduleRender(250);
    };
    color.oninput = () => { color.dataset.touched = '1'; update(); };
    [label, lw].forEach(el => { el.oninput = update; });
    [ls, mk].forEach(el => { el.onchange = update; });
    row.querySelector('.reset').onclick = () => { delete s.series[col]; buildSeriesRows(); scheduleRender(0); };
    box.append(row);
  });
  if (rows.length > MAX_SERIES_ROWS) {
    const p = document.createElement('p');
    p.className = 'small muted';
    p.textContent = t('series.more', { n: (rows.length - MAX_SERIES_ROWS).toLocaleString(LOCALE()) });
    box.append(p);
  }
}

// ------------------------------------------------------------------ recommendations & hints
let recTimer = null;
function refreshRecommend() {
  clearTimeout(recTimer);
  recTimer = setTimeout(async () => {
    if (!state.dataset) return;
    try {
      const s = state.spec;
      const r = await api('/api/recommend', { dataset_id: state.dataset.dataset_id, kind: s.kind,
        mapping: { x: s.x, y: s.y, z: s.z, hue: s.hue, xerr: s.xerr, yerr: s.yerr } });
      state.recommend = r.recommend;
      state.warnings = r.warnings;
      buildKindGallery();
      updateHints();
    } catch (e) { /* recommendations are optional */ }
  }, 150);
}

function updateHints() {
  const box = $('#hints');
  box.innerHTML = '';
  if (!state.dataset) return;
  const top = state.recommend.slice(0, 4);
  if (top.length) {
    const span = document.createElement('span');
    span.className = 'hint';
    span.append(t('rec.title') + ' ');
    top.forEach((r, i) => {
      const chip = document.createElement('button');
      chip.className = 'chip';
      chip.textContent = `${t('kind.' + r.kind)} · ${t('rec.reason.' + r.reason)}`;
      chip.onclick = () => setKind(r.kind);
      if (r.kind === state.spec.kind) chip.style.borderColor = 'var(--accent)';
      span.append(chip, i < top.length - 1 ? ' ' : '');
    });
    box.append(span);
  }
  (state.warnings || []).forEach(w => {
    const span = document.createElement('span');
    span.className = 'hint';
    span.innerHTML = '<span class="warn">⚠</span> ';
    span.append(t('warn.' + w));
    box.append(span);
  });
}

// ------------------------------------------------------------------ rendering
function figInches() {
  const f = state.spec.figure;
  const k = UNIT_MM[f.units] / 25.4;
  return { w: Math.max(0.2, (f.width || 1) * k), h: Math.max(0.2, (f.height || 1) * k) };
}
function updateFigInfo() {
  const f = state.spec.figure;
  const fmt = $('#exportFormat').value;
  const { w, h } = figInches();
  $('#figInfo').textContent = state.dataset ? `${f.width} × ${f.height} ${f.units} · ${state.dataset.rows.toLocaleString(LOCALE())} × ${state.dataset.columns.length}` : '';
  const info = state.meta.export_formats[fmt] || {};
  let hint;
  if (fmt === 'html') hint = t('export.hint.html');
  else if (fmt === 'py') hint = t('export.hint.py');
  else if (info.raster) hint = t('export.hint.raster', { w: Math.round(w * f.dpi), h: Math.round(h * f.dpi), dpi: f.dpi });
  else hint = t('export.hint.vector');
  $('#exportHint').textContent = hint;
  $('[data-path="figure.dpi"]').closest('.field').classList.toggle('disabled', !info.raster);
}

function specForServer() {
  const s = clone(state.spec);
  s.lang = state.lang;
  s.name = state.dataset ? state.dataset.name : '';
  s.extra = (window.Files && !viewDataset()) ? Files.extraSpec() : [];
  return s;
}

// ------------------------------------------------------------------ points clicked on the figure
// The server says where each set of axes lies in the image (X-Axes), so a click becomes data x, y.
// An analysis field (e.g. baseline anchor points) starts a session with startPick and gets each point.
const Pick = { session: null };

function figureAxes(header) {
  try { return JSON.parse(decodeURIComponent(header || '[]')).filter(g => [g.xscale, g.yscale].every(v => v === 'linear' || v === 'log')); }
  catch (e) { return []; }
}

// Position along one axis: fraction f of the image → data value (linear or log axis), and back.
const axisValue = (f, lo, hi, lim, scale) => {
  const u = (f - lo) / (hi - lo);
  if (scale === 'log') return 10 ** (Math.log10(lim[0]) + u * (Math.log10(lim[1]) - Math.log10(lim[0])));
  return lim[0] + u * (lim[1] - lim[0]);
};
const axisFraction = (v, lo, hi, lim, scale) => {
  const t = scale === 'log' ? (Math.log10(v) - Math.log10(lim[0])) / (Math.log10(lim[1]) - Math.log10(lim[0]))
    : (v - lim[0]) / (lim[1] - lim[0]);
  return lo + t * (hi - lo);
};

// Data coordinates under a point of the screen, or null outside the axes.
function figureToData(clientX, clientY) {
  const r = $('#figure').getBoundingClientRect();
  if (!r.width || !r.height) return null;
  const fx = (clientX - r.left) / r.width, fy = 1 - (clientY - r.top) / r.height;
  const g = (state.axesGeom || []).find(a => fx >= a.box[0] && fx <= a.box[2] && fy >= a.box[1] && fy <= a.box[3]);
  if (!g) return null;
  return { x: axisValue(fx, g.box[0], g.box[2], g.xlim, g.xscale), y: axisValue(fy, g.box[1], g.box[3], g.ylim, g.yscale), g };
}

// A coordinate written with the precision the axis can show (≈ 1/2000 of its span).
function axisText(v, lim, scale) {
  if (scale === 'log' || !Number.isFinite(v)) return String(+v.toPrecision(4));
  const step = Math.abs(lim[1] - lim[0]) / 2000 || 1;
  return String(+v.toFixed(Math.min(12, Math.max(0, Math.ceil(-Math.log10(step))))));
}

function startPick(session) {
  stopPick();
  if (state.tab !== 'figure') setTab('figure');
  if (!(state.axesGeom || []).length) { toast(t('pick.unavailable'), true); return false; }
  Pick.session = session;
  const box = $('#figureBox');
  box.classList.add('picking');
  const hint = document.createElement('div');
  hint.className = 'pick-hint';
  hint.id = 'pickHint';
  hint.textContent = t('pick.hint');
  box.append(hint);
  drawPickMarks();
  $('#stage').scrollIntoView({ block: 'nearest', behavior: 'smooth' });   // narrow screens: the figure is above
  return true;
}

function stopPick() {
  const s = Pick.session;
  Pick.session = null;
  $('#figureBox').classList.remove('picking');
  ['#pickHint', '#pickLayer', '#pickReadout'].forEach(id => { const el = $(id); if (el) el.remove(); });
  if (s && s.onStop) s.onStop();
}

// The session's points over the image: a dot where the height is given, a vertical line where the
// height will be read from the signal.
function drawPickMarks() {
  const old = $('#pickLayer');
  if (old) old.remove();
  if (!Pick.session || !(state.axesGeom || []).length) return;
  const box = $('#figureBox');
  const img = $('#figure').getBoundingClientRect();
  const outer = box.getBoundingClientRect();
  const g = state.axesGeom[0];
  const layer = document.createElement('div');
  layer.className = 'pick-layer';
  layer.id = 'pickLayer';
  const left = v => img.left - outer.left + img.width * axisFraction(v, g.box[0], g.box[2], g.xlim, g.xscale);
  const top = v => img.top - outer.top + img.height * (1 - axisFraction(v, g.box[1], g.box[3], g.ylim, g.yscale));
  (Pick.session.marks() || []).forEach(({ x, y }) => {
    const m = document.createElement('div');
    if (y === null || y === undefined) {
      m.className = 'pick-vline';
      m.style.left = left(x) + 'px';
      m.style.top = top(g.ylim[1]) + 'px';
      m.style.height = (top(g.ylim[0]) - top(g.ylim[1])) + 'px';
    } else {
      m.className = 'pick-dot';
      m.style.left = left(x) + 'px';
      m.style.top = top(y) + 'px';
    }
    layer.append(m);
  });
  box.append(layer);
}

function initPick() {
  const img = $('#figure');
  img.addEventListener('click', e => {
    if (!Pick.session) return;
    const p = figureToData(e.clientX, e.clientY);
    if (!p) { toast(t('pick.outside')); return; }
    Pick.session.onPoint({ x: axisText(p.x, p.g.xlim, p.g.xscale), y: axisText(p.y, p.g.ylim, p.g.yscale) });
    drawPickMarks();
  });
  img.addEventListener('mousemove', e => {
    if (!Pick.session) return;
    let tip = $('#pickReadout');
    const p = figureToData(e.clientX, e.clientY);
    if (!p) { if (tip) tip.remove(); return; }
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'pick-readout';
      tip.id = 'pickReadout';
      $('#figureBox').append(tip);
    }
    const outer = $('#figureBox').getBoundingClientRect();
    tip.textContent = `x ${axisText(p.x, p.g.xlim, p.g.xscale)}   y ${axisText(p.y, p.g.ylim, p.g.yscale)}`;
    tip.style.left = (e.clientX - outer.left + 14) + 'px';
    tip.style.top = (e.clientY - outer.top + 14) + 'px';
  });
  img.addEventListener('mouseleave', () => { const tip = $('#pickReadout'); if (tip) tip.remove(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && Pick.session) stopPick(); });
}

function scheduleRender(delay = 200) {
  clearTimeout(state.renderTimer);
  state.renderTimer = setTimeout(renderNow, delay);
}

async function renderNow() {
  if (!state.dataset || state.tab !== 'figure') return;
  const seq = ++state.renderSeq;
  if (state.renderCtrl) state.renderCtrl.abort();
  const ctrl = new AbortController();
  state.renderCtrl = ctrl;
  const stage = $('#stage');
  const img = $('#figure');
  const { w, h } = figInches();
  const fit = Math.max(20, Math.min((stage.clientWidth - 56) / w, (stage.clientHeight - 56) / h));
  const dpi = Math.round(Math.min(Math.max(fit * (window.devicePixelRatio || 1), 50), 450));
  $('#spinner').hidden = false;
  img.classList.add('loading');
  try {
    const res = await api('/api/render', { dataset_id: state.dataset.dataset_id, spec: specForServer(), dpi }, { raw: true, signal: ctrl.signal });
    const blob = await res.blob();
    if (seq !== state.renderSeq) return;
    seriesDrawn(res.headers.get('X-Series'));
    state.axesGeom = figureAxes(res.headers.get('X-Axes'));
    const url = URL.createObjectURL(blob);
    img.onload = () => { URL.revokeObjectURL(url); drawPickMarks(); };
    img.src = url;
    img.style.width = Math.round(w * fit) + 'px';
    img.style.height = Math.round(h * fit) + 'px';
    $('#figureBox').hidden = false;
    $('#errorBox').hidden = true;
    $('#btnExport').disabled = false;
  } catch (e) {
    if (e.name === 'AbortError' || seq !== state.renderSeq) return;
    if (e.code === 'missing_modules') {
      if (await ensureModules(e.data.modules)) { buildKindGallery(); scheduleRender(0); }
    } else if (e.code === 'dataset_gone') {
      await reopenSource();
    } else {
      $('#errorBox').textContent = specMessage(e);
      $('#errorBox').hidden = false;
    }
  } finally {
    if (seq === state.renderSeq) {
      $('#spinner').hidden = true;
      img.classList.remove('loading');
    }
  }
}

// ------------------------------------------------------------------ data loading
function resetDataSpec(mapping, s = state.spec) {
  Object.assign(s, { kind: mapping.kind || 'line', x: mapping.x, y: mapping.y || [], y2: [], hue: null, z: mapping.z || null,
    xerr: mapping.xerr || null, yerr: mapping.yerr || null, series: {}, overlays: [] });
  ['title', 'xlabel', 'ylabel', 'y2label', 'zlabel'].forEach(k => { s.text[k] = ''; });
  ['xmin', 'xmax', 'ymin', 'ymax', 'y2min', 'y2max'].forEach(k => { s.axes[k] = null; });
  s.style.vmin = null;
  s.style.vmax = null;
}

function applyDataset(ds, keepSpec = false) {
  if (!keepSpec) stashViews();   // copies belong to the data they were made from
  state.dataset = ds;
  state.source = ds.source;
  if (!ds.source || !ds.source.analysis) state.history = [];
  if (window.Analysis) window.Analysis.updateDerived();
  if (window.Files) Files.render();
  state.recommend = ds.recommend || [];
  state.warnings = [];
  if (!keepSpec) resetDataSpec(ds.mapping);
  $('#datasetName').textContent = ds.name;
  $('#mappingCard').hidden = false;
  $('#emptyState').hidden = true;
  const base = (ds.name || 'figure').split(/[\\/›]/).pop().trim().replace(/\.[^.]+$/, '').replace(/[^\w.-]+/g, '_')
    .replace(/^_+|_+$/g, '').slice(0, 60);
  $('#exportName').value = base || 'figure';
  syncControls();
  buildKindGallery();
  buildKindOptions();
  buildMapping(true);
  buildSeries();
  buildTable();
  updateHints();
  updateFigInfo();
  if (state.tab === 'table') setTab('figure');
  if (window.Analysis) window.Analysis.show();
  scheduleRender(0);
}

function setUpload(show, frac, text) {
  $('#uploadBox').hidden = !show;
  if (show) {
    $('#uploadBar').style.width = Math.round(frac * 100) + '%';
    $('#uploadText').textContent = text;
  }
}

function uploadFile(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('X-Token', TOKEN);
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) setUpload(true, e.loaded / e.total, t('data.uploading', { name: file.name, pct: Math.round(100 * e.loaded / e.total) }));
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      if (data.code === 'token') reloadForNewSession();
      if (xhr.status >= 400) reject(new ApiError(data.error || xhr.statusText, xhr.status, data));
      else resolve(data);
    };
    xhr.onerror = () => reject(new ApiError(t('error.network'), 0, { code: 'network' }));
    xhr.send(file);
  });
}

// Upload one file and read its first table; returns {ds, info} without showing it.
async function loadFile(file) {
  setUpload(true, 0, t('data.uploading', { name: file.name, pct: 0 }));
  let info = await uploadFile(file);
  setUpload(true, 1, t('data.reading', { name: file.name }));
  if (info.missing.length) {
    const ok = await ensureModules(info.missing, 'install.reason.file', { name: file.name });
    if (!ok) return null;
    info = await api('/api/file', { file_id: info.file_id });
  }
  let ds = await api('/api/open', { file_id: info.file_id, table: info.tables[0], options: {} });
  setUpload(false);
  ds = await askConversion(ds, info, {});
  return { ds, info };
}

// Columns written like "1,003.3": ask before turning them into numbers; returns the data set to use.
async function askConversion(ds, info, baseOptions) {
  const sug = ((ds.options || {}).suggestions || []);
  if (!sug.length || !info) return ds;
  const dlg = $('#convertDialog');
  $('#convertText').textContent = t('conv.text', { file: info.name });
  const list = $('#convertList');
  list.innerHTML = '';
  sug.forEach(sg => {
    const li = document.createElement('li');
    const lab = document.createElement('label');
    lab.className = 'check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.dataset.col = sg.column;
    cb.dataset.style = sg.style;
    const b = document.createElement('b');
    b.textContent = sg.column;
    lab.append(cb, b);
    const small = document.createElement('small');
    small.textContent = t('conv.item', { example: sg.example, value: sg.value, count: sg.count.toLocaleString(LOCALE()),
      rows: sg.rows.toLocaleString(LOCALE()), style: t('conv.style.' + sg.style) });
    li.append(lab, small);
    list.append(li);
  });
  const answer = await new Promise(resolve => {
    dlg.onclose = () => resolve(dlg.returnValue || 'no');
    dlg.returnValue = '';
    dlg.showModal();
  });
  const convert = {};
  $$('input[type=checkbox]', list).forEach(cb => {
    convert[cb.dataset.col] = answer === 'yes' && cb.checked ? cb.dataset.style : 'none';
  });
  info.convert = convert;                  // remembered for this file (import options, reloads)
  if (!Object.values(convert).some(v => v !== 'none')) {
    ds.source = { ...ds.source, options: { ...(ds.source.options || {}), convert } };
    return ds;
  }
  const table = (ds.source && ds.source.table) || info.tables[0];
  const fresh = await api('/api/open', { file_id: info.file_id, table, options: { ...baseOptions, convert } });
  toast(t('conv.done'));
  return fresh;
}

function showFileControls(info) {
  state.file = info || null;
  const sel = $('#tableSelect');
  if (!info) {
    $('#tableField').hidden = true;
    $('#importOptions').hidden = true;
    return;
  }
  fillSelect(sel, info.tables.map(n => [n, n]));
  $('#tableField').hidden = info.tables.length < 2;
  sel.onchange = () => openTable(sel.value);
  const textual = info.format === 'text';
  const sheet = ['excel', 'xls', 'ods'].includes(info.format);
  $('#importOptions').hidden = !(textual || sheet);
  $$('[data-import="sep"], [data-import="decimal"]').forEach(el => { el.closest('.field').hidden = !textual; });
  $$('[data-import]').forEach(el => { el.value = el.tagName === 'SELECT' ? 'auto' : ''; });
}

// Open one or more files. The first becomes the figure; files opened together are combined in it.
async function openFiles(files) {
  files = Array.from(files || []).filter(Boolean);
  if (!files.length) return;
  setDataError('');
  const loaded = [];
  for (const file of files) {
    try {
      const r = await loadFile(file);
      if (r) loaded.push(r);
    } catch (e) {
      setDataError(`${file.name}: ${e.message}`);
      if (e.code === 'missing_modules') handleError(e);
    }
  }
  setUpload(false);
  if (!loaded.length) return;
  loaded.forEach((r, i) => {
    const same = Files.list().find(e => e.ds.name === r.ds.name);
    if (same) Files.replace(same.id, r.ds, r.info);        // the same file again: refresh it
    else Files.add(r.ds, r.info, files.length > 1 && i > 0);
  });
  const first = loaded[0];
  showFileControls(first.info);
  applyDataset(first.ds);
  setTab('figure');
  toast(loaded.length > 1 ? t('files.opened', { n: loaded.length })
    : t('data.loaded', { rows: first.ds.rows.toLocaleString(LOCALE()), cols: first.ds.columns.length }));
}

const openFile = file => openFiles([file]);

function setDataError(message) {
  const box = $('#dataError');
  box.textContent = message || '';
  box.hidden = !message;
}

function importOptions() {
  const o = {};
  $$('[data-import]').forEach(el => {
    let v = el.value;
    if (v === '' || v === 'auto') return;
    if (el.dataset.import === 'sep' && v === '\t') v = '\t';
    o[el.dataset.import] = el.dataset.import === 'skiprows' ? Number(v) : v;
  });
  if (state.file && state.file.convert) o.convert = state.file.convert;
  return o;
}

async function openTable(table) {
  if (!state.file) return;
  try {
    const old = state.dataset && state.dataset.dataset_id;
    let ds = await api('/api/open', { file_id: state.file.file_id, table, options: importOptions() });
    ds = await askConversion(ds, state.file, importOptions());
    Files.replace(old, ds, state.file);
    applyDataset(ds);
    setTab('figure');
    setDataError('');
    const o = ds.options || {};
    if (o.sep !== undefined) {
      const sepSel = $('[data-import="sep"]');
      sepSel.dataset.detected = o.sep;
    }
    toast(t('data.loaded', { rows: ds.rows.toLocaleString(LOCALE()), cols: ds.columns.length }));
  } catch (e) {
    handleError(e, () => openTable(table));
  }
}

async function openSample(name) {
  try {
    showFileControls(null);
    const ds = await api('/api/sample', { name });
    Files.add(ds, null, false);
    applyDataset(ds);
    setTab('figure');
    setDataError('');
  } catch (e) {
    handleError(e, () => openSample(name));
  }
}

async function reopenSource() {
  // After a restart result figures point to data the service no longer has: close them.
  if (viewDataset()) showView(null);
  state.views = state.views.filter(v => !v.dataset);
  renderViewTabs();
  const src = state.source;
  if (!src) return;
  try {
    const ds = await api('/api/reopen', { source: src });
    applyDataset(ds, true);
  } catch (e) {
    if (e.code === 'file_gone' || e.code === 'dataset_gone') return clearDataset(t('data.gone'));
    handleError(e);
  }
}

function clearDataset(message) {
  stashViews();
  state.dataset = null;
  state.source = null;
  state.file = null;
  state.history = [];
  $('#datasetName').textContent = '';
  $('#mappingCard').hidden = true;
  $('#tableField').hidden = true;
  $('#importOptions').hidden = true;
  $('#figureBox').hidden = true;
  $('#errorBox').hidden = true;
  $('#emptyState').hidden = false;
  $('#btnExport').disabled = true;
  $('#hints').innerHTML = '';
  if (window.Files) Files.render();
  if (window.Analysis) window.Analysis.show();
  if (message) { toast(message, true); setDataError(message); }
}

function handleError(e, retry) {
  if (e && e.code === 'missing_modules') {
    ensureModules(e.data.modules).then(ok => { if (ok && retry) retry(); });
    return;
  }
  console.error(e);
  const msg = e.code === 'unsupported' ? `${t('error.unsupported')} ${e.message}` : (e.message || String(e));
  toast(msg, true);
  if (['unsupported', 'read_error', 'import_error', 'file_gone', 'token', 'network'].includes(e.code)) setDataError(msg);
}

// ------------------------------------------------------------------ data table
function buildTable() {
  const ds = state.dataset;
  const box = $('#tableBox');
  if (!ds) { box.innerHTML = ''; return; }
  const table = document.createElement('table');
  const head = document.createElement('tr');
  head.append(document.createElement('th'));
  const width = ds.preview_cols ?? ds.columns.length;      // a wide table: its first columns
  ds.columns.slice(0, width).forEach(c => {
    const th = document.createElement('th');
    th.textContent = c.name;
    const sm = document.createElement('small');
    sm.textContent = c.dtype + (c.missing ? ` · ${c.missing} NaN` : '');
    th.append(sm);
    head.append(th);
  });
  const thead = document.createElement('thead');
  thead.append(head);
  const tbody = document.createElement('tbody');
  ds.preview.forEach((row, i) => {
    const tr = document.createElement('tr');
    const idx = document.createElement('td');
    idx.className = 'idx';
    idx.textContent = i + 1;
    tr.append(idx);
    row.forEach(v => {
      const td = document.createElement('td');
      td.textContent = v === null ? '' : (typeof v === 'number' ? +v.toPrecision(8) : v);
      tr.append(td);
    });
    tbody.append(tr);
  });
  table.append(thead, tbody);
  box.innerHTML = '';
  const note = document.createElement('div');
  note.className = 'table-note';
  note.textContent = `${t('data.loaded', { rows: ds.rows.toLocaleString(LOCALE()), cols: ds.columns.length.toLocaleString(LOCALE()) })}` +
    (ds.rows > ds.preview.length ? ` — 1–${ds.preview.length}` : '') +
    (width < ds.columns.length ? ` · ${t('data.first_cols', { n: width })}` : '');
  box.append(note, table);
}

function setTab(tab) {
  state.tab = tab;
  $$('.tab[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab && (tab !== 'figure' || !state.view)));
  renderViewTabs();
  const hasData = !!state.dataset;
  $('#tableBox').hidden = tab !== 'table' || !hasData;
  $('#figureBox').hidden = tab !== 'figure' || !hasData;
  $('#emptyState').hidden = hasData;
  if (tab !== 'figure') $('#errorBox').hidden = true;
  if (tab === 'figure') scheduleRender(0);
}

// ------------------------------------------------------------------ figure copies
// Analyses never change the original figure. Curves that share its axes (fits, bands, smoothing…)
// are drawn on a copy of it; results with axes of their own (ACF, spectrum, Q–Q…) open as a figure
// of their own data. Each has its own spec and a tab closed with ×. While one is shown, state.spec
// (and, for a result, state.dataset) are its own; the original ones wait in state.main*.
const localName = obj => (obj && typeof obj === 'object') ? (obj[state.lang] || obj.en || '') : (obj ?? '');

function viewTitle(v) {
  const names = v.runs.map(r => localName(r.name));
  return v.dataset ? [localName(v.result.name), ...names].join(' + ') : `${t('tab.figure')} + ${names.join(' + ')}`;
}

// The data set of the result figure on screen, if any (copies of the figure use the original data).
function viewDataset() {
  const v = state.view && state.views.find(x => x.id === state.view);
  return (v && v.dataset) || null;
}

function renderViewTabs() {
  const box = $('#viewTabs');
  if (!box) return;
  box.innerHTML = '';
  state.views.forEach(v => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tab view-tab' + (state.tab === 'figure' && state.view === v.id ? ' active' : '');
    const label = document.createElement('span');
    label.className = 'view-label';
    label.textContent = viewTitle(v);
    b.title = viewTitle(v);
    const x = document.createElement('span');
    x.className = 'view-close';
    x.textContent = '×';
    x.title = t('view.close');
    x.setAttribute('role', 'button');
    x.setAttribute('aria-label', t('view.close'));
    x.onclick = e => { e.stopPropagation(); closeView(v.id); };
    b.append(label, x);
    b.onclick = () => showView(v.id);
    box.append(b);
  });
}

function refreshSpecUI() {
  syncControls();
  updatePalettePreview();
  buildKindGallery();
  buildKindOptions();
  buildMapping(true);
  buildSeries();
  updateFigInfo();
}

// Show the original figure (id null), one of its copies or a result figure.
function showView(id, force = false) {
  const v = id ? state.views.find(x => x.id === id) : null;
  if (force || (v ? v.id : null) !== state.view) {
    if (!state.view) {
      state.mainSpec = state.spec;
      state.mainDataset = state.dataset;
      state.mainRecommend = state.recommend;
    }
    const before = state.dataset;
    state.view = v ? v.id : null;
    state.spec = v ? v.spec : state.mainSpec;
    state.dataset = (v && v.dataset) || state.mainDataset;
    state.recommend = (v && v.dataset) ? (v.dataset.recommend || []) : state.mainRecommend;
    if (!v) state.mainSpec = state.mainDataset = state.mainRecommend = null;
    refreshSpecUI();
    if (force || state.dataset !== before) {
      buildTable();
      updateHints();
      if (window.Analysis) { window.Analysis.updateDerived(); window.Analysis.show(); }
    }
  }
  setTab('figure');
}

// A new copy of the original figure (not shown yet).
function newView() {
  const v = { id: Math.random().toString(16).slice(2, 10), spec: clone(state.view ? state.mainSpec : state.spec), runs: [] };
  v.spec.overlays = (v.spec.overlays || []).filter(o => !o.analysis_run);
  state.views.push(v);
  return v;
}

function closeView(id) {
  const i = state.views.findIndex(v => v.id === id);
  if (i < 0) return;
  const shown = state.view === id;
  if (shown) showView(null);
  state.views.splice(i, 1);
  renderViewTabs();
  if (window.Analysis) window.Analysis.viewsChanged();
}

// Leave the copies (back to the original spec) and hand them over, e.g. to keep them in the history.
function stashViews() {
  const saved = state.views;
  if (state.view) {
    state.spec = state.mainSpec;
    state.dataset = state.mainDataset;
    state.recommend = state.mainRecommend;
    state.mainSpec = state.mainDataset = state.mainRecommend = null;
    state.view = null;
  }
  state.views = [];
  renderViewTabs();
  return saved;
}

// ------------------------------------------------------------------ export & templates
async function exportFigure() {
  if (!state.dataset) return;
  const format = $('#exportFormat').value;
  store.set('pp-export-format', format);
  const need = missingOf(state.meta.export_formats[format].requires);
  if (need.length && !(await ensureModules(need))) return;
  const btn = $('#btnExport');
  btn.disabled = true;
  const label = btn.querySelector('span');
  label.textContent = t('export.busy');
  try {
    const name = $('#exportName').value.trim() || 'figure';
    const res = await api('/api/export', { dataset_id: state.dataset.dataset_id, spec: specForServer(), format,
      dpi: state.spec.figure.dpi, filename: name }, { raw: true });
    const blob = await res.blob();
    const ext = format === 'py' ? 'zip' : format;
    download(blob, `${name}.${ext}`);
    toast(t('export.done', { name: `${name}.${ext}` }));
  } catch (e) {
    handleError(e, exportFigure);
  } finally {
    btn.disabled = false;
    label.textContent = t('export.button');
  }
}

function download(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function saveTemplate() {
  const tpl = { schema: 'pyplotter-template/1', ...styleSnapshot() };
  download(new Blob([JSON.stringify(tpl, null, 2)], { type: 'application/json' }), 'pyplotter-style.json');
}

async function loadTemplate(file) {
  try {
    const data = JSON.parse(await file.text());
    if (!String(data.schema || '').startsWith('pyplotter-template/')) throw new Error(t('tpl.bad'));
    STYLE_KEYS.forEach(k => { if (data[k]) state.spec[k] = merge(state.spec[k], data[k]); });
    syncControls();
    buildKindOptions();
    updatePalettePreview();
    buildSeries();
    saveStyle();
    updateFigInfo();
    scheduleRender(0);
    toast(t('tpl.loaded'));
  } catch (e) {
    toast(e.message || t('tpl.bad'), true);
  }
}

// ------------------------------------------------------------------ modules dialog
function fmtWhen(ts) {
  if (!ts) return t('modules.never');
  return new Date(ts * 1000).toLocaleString(state.lang === 'it' ? 'it-IT' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

function renderModules() {
  const st = state.status;
  const r = st.refresh || {};
  $('#modulesInfo').textContent = r.state === 'running' ? t('modules.info', { when: t('modules.checking') })
    : (r.state === 'offline' ? t('modules.offline') : t('modules.info', { when: fmtWhen(r.checked_at) }));
  const upd = st.modules.filter(m => m.installed && m.update);
  $('#btnUpdateAll').hidden = !upd.length;
  $('#btnUpdateAll').textContent = t('modules.update_all', { n: upd.length });
  const inst = st.modules.filter(m => m.installed);
  const broken = inst.filter(m => m.works === false);
  const checking = st.checks?.state === 'running' || inst.some(m => m.works === null);
  const line = $('#modulesCheck');
  line.className = 'small check-line' + (broken.length ? ' bad' : (checking ? ' muted' : ' ok'));
  line.textContent = broken.length ? t('modules.check_bad', { n: broken.length })
    : (checking ? t('modules.check_running') : t('modules.check_ok', { n: inst.length }));
  $('#btnVerify').disabled = checking;
  const box = $('#modulesTable');
  box.innerHTML = '';
  const cats = ['core', 'plotting', 'analysis', 'styles', 'science', 'formats'];
  cats.forEach(cat => {
    const mods = st.modules.filter(m => m.category === cat);
    if (!mods.length) return;
    const sec = document.createElement('div');
    sec.className = 'mod-cat';
    const h = document.createElement('h3');
    h.textContent = t('cat.' + cat);
    sec.append(h);
    mods.forEach(m => {
      const row = document.createElement('div');
      row.className = 'mod-row';
      const info = document.createElement('div');
      const name = document.createElement('b');
      name.textContent = m.pip;
      const lic = document.createElement('span');
      lic.className = 'lic';
      lic.textContent = m.license;
      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.textContent = (m.description[state.lang] || m.description.en || '') + ' ';
      if (m.url) {
        const a = document.createElement('a');
        a.href = m.url; a.target = '_blank'; a.rel = 'noopener'; a.textContent = m.url.replace(/^https?:\/\//, '').replace(/\/$/, '');
        meta.append(a);
      }
      info.append(name, lic, meta);
      if (m.installed && m.works === false && m.import_error) {
        const err = document.createElement('div');
        err.className = 'import-error';
        err.textContent = m.import_error;
        info.append(err);
      }
      const status = document.createElement('span');
      status.className = 'status';
      if (!m.installed) { status.classList.add('no'); status.textContent = t('modules.missing'); }
      else if (m.works === false) { status.classList.add('bad'); status.textContent = t('modules.broken', { v: m.installed }); }
      else if (m.update) { status.classList.add('upd'); status.textContent = `${t('modules.installed', { v: m.installed })} → ${t('modules.newer', { v: m.latest })}`; }
      else { status.classList.add('ok'); status.textContent = t('modules.installed', { v: m.installed }); }
      if (m.installed && m.works !== false) status.textContent += ` · ${t(m.works ? 'modules.works' : 'modules.verifying')}`;
      if (m.restart) status.textContent += ` · ${t('modules.restart')}`;
      const actions = document.createElement('span');
      if (m.installed && m.works === false) {
        const b = document.createElement('button');
        b.className = 'btn small primary';
        b.textContent = t('modules.reinstall');
        b.onclick = () => installFromManager([m.id], false, true);
        actions.append(b);
      }
      if (!m.installed || m.update || m.outdated) {
        const b = document.createElement('button');
        b.className = 'btn small' + (m.installed ? '' : ' primary');
        b.textContent = m.installed ? t('modules.update', { v: m.latest || '' }) : t('modules.install');
        b.onclick = () => installFromManager([m.id], !!m.installed);
        actions.append(b);
      }
      row.append(info, status, actions);
      sec.append(row);
    });
    box.append(sec);
  });
}

async function installFromManager(ids, upgrade, reinstall = false) {
  if (state.busyJob) { toast(t('modules.busy'), true); return; }
  $$('#modulesTable button, #btnUpdateAll, #btnRefresh, #btnVerify').forEach(b => { b.disabled = true; });
  const bar = $('#modulesProgress');
  try {
    const job = await runInstall(ids, upgrade, j => { setBar(bar, j.progress); $('#modulesPhase').textContent = `${j.title}: ${phaseText(j)}`; }, reinstall);
    if (job.state === 'error') toast(phaseText(job), true);
  } catch (e) {
    handleError(e);
  }
  setTimeout(() => { bar.hidden = true; }, 800);
  renderModules();
  if (state.meta) { buildStaticSelects(); buildKindGallery(); }
  pollRefresh();       // the import check runs again after every install
}

async function openModules() {
  await refreshStatus();
  renderModules();
  $('#modulesDialog').showModal();
  pollRefresh();
}

const backgroundChecks = () => state.status.refresh?.state === 'running' || state.status.checks?.state === 'running';

// Follow the PyPI check and the import check until both are over (each up to ~5 min).
let polling = false;
async function pollRefresh() {
  if (polling) return;
  polling = true;
  // Only the module dialog and the "needs module ↓" marks depend on these checks: the analysis form,
  // which the user may be filling in, is never rebuilt here.
  const installedSig = () => (state.status?.modules || []).map(m => `${m.id}=${m.installed || ''}`).join(',');
  const before = installedSig();
  try {
    for (let i = 0; i < 400 && backgroundChecks(); i++) {
      await new Promise(r => setTimeout(r, 700));
      await refreshStatus();
      if ($('#modulesDialog').open) renderModules();
    }
  } finally {
    polling = false;
  }
  if (installedSig() !== before && window.Analysis) window.Analysis.modulesChanged();
}

// ------------------------------------------------------------------ about
function openAbout() {
  $('#aboutVersion').textContent = 'v' + (state.meta?.version || '');
  const box = $('#aboutRefs');
  box.innerHTML = '';
  const ul = document.createElement('ul');
  ul.className = 'refs small';
  (state.status?.modules || []).forEach(m => {
    const li = document.createElement('li');
    const b = document.createElement('b');
    b.textContent = m.pip;
    const lic = document.createElement('span');
    lic.className = 'lic';
    lic.textContent = m.license;
    li.append(b, lic, document.createTextNode(m.cite ? ' — ' + m.cite : ''));
    ul.append(li);
  });
  box.append(ul);
  $('#aboutDialog').showModal();
}

// ------------------------------------------------------------------ restart
async function restartService() {
  const btn = $('#btnRestart');
  btn.disabled = true;
  btn.textContent = t('restart.wait');
  try { await api('/api/restart', {}); } catch (e) { /* the connection may drop */ }
  await new Promise(r => setTimeout(r, 1200));
  for (let i = 0; i < 60; i++) {
    try {
      await refreshStatus();
      break;
    } catch (e) {
      await new Promise(r => setTimeout(r, 500));
    }
  }
  btn.disabled = false;
  btn.textContent = t('restart.button');
  state.meta = await api('/api/meta');
  buildStaticSelects();
  buildKindGallery();
  await reopenSource();
  toast(t('restart.done'));
}

// ------------------------------------------------------------------ start
function bindGlobal() {
  $$('.seg [data-lang]').forEach(b => { b.onclick = () => setLang(b.dataset.lang); });
  $('#btnNew').onclick = newSession;
  $('#btnTheme').onclick = () => setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
  $('#btnModules').onclick = () => openModules().catch(handleError);
  $('#btnAbout').onclick = openAbout;
  $('#btnRestart').onclick = restartService;
  $('#btnRefresh').onclick = async () => { await api('/api/modules/refresh', {}); await refreshStatus(); renderModules(); pollRefresh(); };
  $('#btnVerify').onclick = async () => { await api('/api/modules/verify', {}); await refreshStatus(); renderModules(); pollRefresh(); };
  $('#btnUpdateAll').onclick = () => installFromManager(state.status.modules.filter(m => m.installed && m.update).map(m => m.id), true);
  $$('dialog [data-close]').forEach(b => { b.onclick = () => b.closest('dialog').close(); });
}

function bindApp() {
  $('#fileInput').onchange = e => { const files = Array.from(e.target.files); e.target.value = ''; openFiles(files); };
  $$('[data-sample]').forEach(b => { b.onclick = () => openSample(b.dataset.sample); });
  $('#btnReimport').onclick = () => openTable($('#tableSelect').value || (state.file && state.file.tables[0]));
  document.addEventListener('change', onControlChange);
  document.addEventListener('input', e => { if (e.target.dataset && e.target.dataset.path && e.target.tagName === 'INPUT' && e.target.type !== 'checkbox') onControlChange(e); });
  $('#sizePreset').onchange = e => {
    const p = state.meta.size_presets[e.target.value];
    if (!p) return;
    const k = UNIT_MM[state.spec.figure.units];
    state.spec.figure.width = +(p[0] / k).toFixed(3);
    state.spec.figure.height = +(p[1] / k).toFixed(3);
    syncControls();
    saveStyle();
    updateFigInfo();
    scheduleRender(0);
  };
  $('#exportFormat').onchange = () => { store.set('pp-export-format', $('#exportFormat').value); updateFigInfo(); };
  $('#btnExport').onclick = exportFigure;
  $('#btnSaveTpl').onclick = saveTemplate;
  $('#tplInput').onchange = e => { if (e.target.files[0]) loadTemplate(e.target.files[0]); e.target.value = ''; };
  $$('.tab[data-tab]').forEach(b => { b.onclick = () => (b.dataset.tab === 'figure' ? showView(null) : setTab(b.dataset.tab)); });
  let resizeTimer = null;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => scheduleRender(0), 250); });
  initPick();
  // drag & drop anywhere
  let depth = 0;
  const veil = $('#dropVeil');
  window.addEventListener('dragenter', e => { if (e.dataTransfer.types.includes('Files')) { depth++; veil.classList.add('on'); e.preventDefault(); } });
  window.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) veil.classList.remove('on'); });
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => {
    e.preventDefault();
    depth = 0;
    veil.classList.remove('on');
    if (e.dataTransfer.files.length) openFiles(e.dataTransfer.files);
  });
}

async function start() {
  state.meta = await api('/api/meta');
  state.defaults = state.meta.default_spec;
  state.spec = merge(state.defaults, store.get('pp-style', {}));
  $('#app').hidden = false;
  $('#formatList').textContent = 'CSV · TXT · DAT · Excel · ODS · JSON · Parquet · HDF5 · NetCDF · MATLAB · NumPy · FITS · SPSS · Stata · SAS · XML · SQLite · JCAMP-DX · ZIP';
  $('#formatList').title = state.meta.extensions.join('  ');
  buildStaticSelects();
  buildKindGallery();
  buildKindOptions();
  buildSeries();
  updateFigInfo();
  bindApp();
  if (window.Analysis) window.Analysis.show();
  refreshStatus().then(pollRefresh).catch(() => {});   // badge shows updates and broken modules
}

async function boot() {
  applyI18n();
  bindGlobal();
  try {
    await refreshStatus();
  } catch (e) {
    toast(e.message, true);
    return;
  }
  if (!state.status.core_ready) return showSetup();
  await start();
}

boot();
