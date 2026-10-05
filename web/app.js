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
  $('#updatesBadge').hidden = !updates;
  $('#updatesBadge').textContent = updates;
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

async function runInstall(ids, upgrade, onUpdate) {
  let job = await api('/api/modules/install', { ids, upgrade });
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

function updatePalettePreview() {
  const pal = state.meta.palettes[state.spec.style.palette] || [];
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

function buildChecklist(box, selected, key) {
  box.innerHTML = '';
  (state.dataset?.columns || []).forEach(c => {
    const lab = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = c.name;
    cb.checked = selected.includes(c.name);
    cb.onchange = () => {
      const list = $$('input', box).filter(i => i.checked).map(i => i.value);
      state.spec[key] = list;
      buildSeries();
      refreshRecommend();
      scheduleRender(0);
    };
    const name = document.createElement('span');
    name.textContent = c.name;
    const tag = document.createElement('span');
    tag.className = 'kind-tag';
    tag.textContent = KIND_TAG[c.kind] || c.kind;
    lab.append(cb, name, tag);
    box.append(lab);
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
  if (rebuildLists || !$('#mapY').children.length) {
    buildChecklist($('#mapY'), s.y, 'y');
    buildChecklist($('#mapY2'), s.y2, 'y2');
  } else {
    $$('#mapY input').forEach(i => { i.checked = s.y.includes(i.value); });
  }
}

// ------------------------------------------------------------------ series styling
function buildOverlays() {
  const list = state.spec.overlays || [];
  $('#overlayCard').hidden = !list.length;
  $('#overlayCount').textContent = list.length || '';
  const box = $('#overlayList');
  box.innerHTML = '';
  const pal = state.meta.palettes[state.spec.style.palette] || [];
  list.forEach((o, i) => {
    o.style = o.style || {};
    const row = document.createElement('div');
    row.className = 'overlay-row' + (o.hidden ? ' hidden-layer' : '');
    row.innerHTML = `<div class="src"></div><input type="color"><input type="text"><button class="reset" type="button">✕</button>
      <div class="opts"><select class="ls"></select><label class="check"><input type="checkbox" class="band"><span></span></label>
      <label class="check"><input type="checkbox" class="show"><span></span></label></div>`;
    row.querySelector('.src').textContent = o.source_name || '';
    const color = row.querySelector('input[type=color]');
    color.value = o.style.color || pal[(state.spec.y.length + i) % (pal.length || 1)] || '#000000';
    const label = row.querySelector('input[type=text]');
    label.value = o.label || '';
    const ls = row.querySelector('.ls');
    fillSelect(ls, [...LINESTYLES.map(v => [v, t('ls.' + v)]), ['none', t('ov.markers')]], o.style.linestyle || '-');
    const band = row.querySelector('.band');
    band.checked = o.band !== false && !!(o.lo && o.hi);
    band.disabled = !(o.lo && o.hi);
    band.nextElementSibling.textContent = o.band_label ? `${t('ov.band')} (${o.band_label})` : t('ov.band');
    const show = row.querySelector('.show');
    show.checked = !o.hidden;
    show.nextElementSibling.textContent = t('ov.visible');
    color.oninput = () => { o.style.color = color.value; scheduleRender(250); };
    label.oninput = () => { o.label = label.value; scheduleRender(400); };
    ls.onchange = () => { o.style.linestyle = ls.value; if (ls.value === 'none' && !o.style.marker) o.style.marker = 'o'; scheduleRender(0); };
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

function buildSeries() {
  buildOverlays();
  const box = $('#seriesList');
  box.innerHTML = '';
  const s = state.spec;
  const cols = [...s.y, ...(state.meta.twin_kinds.includes(s.kind) ? s.y2 : [])];
  const extraRows = (window.Files && (s.layout || {}).mode !== 'panels') ? Files.extraSpec().flatMap(e =>
    e.y.map(c => ({ key: `${e.id}:${c}`, title: `${e.name} · ${c}` }))) : [];
  if ((!cols.length && !extraRows.length) || s.hue) {
    box.innerHTML = `<p class="small muted">${t('series.empty')}</p>`;
    return;
  }
  const pal = state.meta.palettes[s.style.palette] || [];
  const rows = [...cols.map(c => ({ key: c, title: c })), ...extraRows];
  rows.forEach(({ key: col, title }, i) => {
    const over = s.series[col] || {};
    const row = document.createElement('div');
    row.className = 'series';
    row.innerHTML = `<div class="name"><span></span><button class="reset" type="button"></button></div>
      <input type="color"><input type="text">
      <div class="opts"><select class="ls"></select><select class="mk"></select><input type="number" class="lw" step="0.1" min="0"></div>`;
    row.querySelector('.name span').textContent = title;
    row.querySelector('.reset').textContent = t('series.reset');
    const color = row.querySelector('input[type=color]');
    color.value = over.color || pal[i % (pal.length || 1)] || '#000000';
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
    row.querySelector('.reset').onclick = () => { delete s.series[col]; buildSeries(); scheduleRender(0); };
    box.append(row);
  });
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
  s.extra = window.Files ? Files.extraSpec() : [];
  return s;
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
    const url = URL.createObjectURL(blob);
    img.onload = () => URL.revokeObjectURL(url);
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
      $('#errorBox').textContent = e.message;
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
function resetDataSpec(mapping) {
  const s = state.spec;
  Object.assign(s, { kind: mapping.kind || 'line', x: mapping.x, y: mapping.y || [], y2: [], hue: null, z: mapping.z || null,
    xerr: mapping.xerr || null, yerr: mapping.yerr || null, series: {}, overlays: [] });
  ['title', 'xlabel', 'ylabel', 'y2label', 'zlabel'].forEach(k => { s.text[k] = ''; });
  ['xmin', 'xmax', 'ymin', 'ymax', 'y2min', 'y2max'].forEach(k => { s.axes[k] = null; });
  s.style.vmin = null;
  s.style.vmax = null;
}

function applyDataset(ds, keepSpec = false) {
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
  ds.columns.forEach(c => {
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
  note.textContent = `${t('data.loaded', { rows: ds.rows.toLocaleString(LOCALE()), cols: ds.columns.length })}` +
    (ds.rows > ds.preview.length ? ` — 1–${ds.preview.length}` : '');
  box.append(note, table);
}

function setTab(tab) {
  state.tab = tab;
  $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  const hasData = !!state.dataset;
  $('#tableBox').hidden = tab !== 'table' || !hasData;
  $('#figureBox').hidden = tab !== 'figure' || !hasData;
  $('#emptyState').hidden = hasData;
  if (tab !== 'figure') $('#errorBox').hidden = true;
  if (tab === 'figure') scheduleRender(0);
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
      const status = document.createElement('span');
      status.className = 'status';
      if (!m.installed) { status.classList.add('no'); status.textContent = t('modules.missing'); }
      else if (m.update) { status.classList.add('upd'); status.textContent = `${t('modules.installed', { v: m.installed })} → ${t('modules.newer', { v: m.latest })}`; }
      else { status.classList.add('ok'); status.textContent = t('modules.installed', { v: m.installed }); }
      if (m.restart) status.textContent += ` · ${t('modules.restart')}`;
      const actions = document.createElement('span');
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

async function installFromManager(ids, upgrade) {
  if (state.busyJob) { toast(t('modules.busy'), true); return; }
  $$('#modulesTable button, #btnUpdateAll, #btnRefresh').forEach(b => { b.disabled = true; });
  const bar = $('#modulesProgress');
  try {
    const job = await runInstall(ids, upgrade, j => { setBar(bar, j.progress); $('#modulesPhase').textContent = `${j.title}: ${phaseText(j)}`; });
    if (job.state === 'error') toast(phaseText(job), true);
  } catch (e) {
    handleError(e);
  }
  setTimeout(() => { bar.hidden = true; }, 800);
  renderModules();
  if (state.meta) { buildStaticSelects(); buildKindGallery(); }
}

async function openModules() {
  await refreshStatus();
  renderModules();
  $('#modulesDialog').showModal();
  if (state.status.refresh?.state === 'running') pollRefresh();
}

async function pollRefresh() {
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 700));
    await refreshStatus();
    if ($('#modulesDialog').open) renderModules();
  if (window.Analysis) { window.Analysis.relabel(); window.Analysis.updateDerived(); }
  if (window.Files) Files.render();
    if (state.status.refresh?.state !== 'running') break;
  }
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
  $$('.tab').forEach(b => { b.onclick = () => setTab(b.dataset.tab); });
  let resizeTimer = null;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => scheduleRender(0), 250); });
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
  refreshStatus().then(() => {
    if (state.status.refresh?.state === 'running') {
      setTimeout(() => refreshStatus().catch(() => {}), 6000);
    }
  });
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
