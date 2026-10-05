// PyPlotter analysis panel (right sidebar): runs built-in and user plugins on the current data,
// draws their curves and error bands over the open figure, shows the numbers, and can turn a
// result into a figure of its own. Plugin editor included.
'use strict';

window.Analysis = (() => {
  const A = { list: null, current: null, params: {}, results: {}, editing: null };
  const CATS = ['fit', 'timeseries', 'stats', 'signal', 'custom'];
  const L = obj => (obj && typeof obj === 'object') ? (obj[state.lang] || obj.en || '') : (obj ?? '');

  // ---------------------------------------------------------------- list
  async function load(force = false) {
    if (A.list && !force) return A.list;
    A.list = await api('/api/analyses', {});
    return A.list;
  }

  async function show() {
    const has = !!state.dataset;
    $('#anEmpty').hidden = has;
    $('#anBody').hidden = !has;
    if (!has) return;
    try {
      await load();
    } catch (e) {
      return handleError(e, show);
    }
    renderList();
    if (!A.current || !A.list.plugins.some(p => p.id === A.current)) {
      A.current = (A.list.plugins.find(p => p.id === 'fit_curve') || A.list.plugins[0] || {}).id || null;
    }
    if (A.current) renderMain(A.current);
  }

  function renderList() {
    const box = $('#anList');
    box.innerHTML = '';
    CATS.forEach(cat => {
      const items = A.list.plugins.filter(p => p.category === cat);
      if (!items.length) return;
      const h = document.createElement('div');
      h.className = 'an-cat';
      h.textContent = t('an.cat.' + cat);
      box.append(h);
      items.forEach(p => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'an-item' + (p.id === A.current ? ' active' : '');
        b.dataset.id = p.id;
        const name = document.createElement('span');
        name.textContent = L(p.name);
        b.append(name);
        const tag = document.createElement('span');
        tag.className = 'tag';
        if (p.missing.length) { tag.classList.add('need'); tag.textContent = '↓ ' + p.missing.join(', '); }
        else if (p.source === 'user') { tag.classList.add('user'); tag.textContent = p.overrides ? t('an.custom') : t('an.user'); }
        b.append(tag);
        b.title = L(p.description);
        b.onclick = () => renderMain(p.id);
        box.append(b);
      });
    });
    const err = $('#anErrors');
    err.innerHTML = '';
    if (A.list.errors.length) {
      const d = document.createElement('div');
      d.className = 'an-errors';
      d.textContent = t('an.load_errors') + '\n' + A.list.errors.map(e => `• ${e.file}: ${e.error}`).join('\n');
      err.append(d);
      A.list.errors.forEach(e => {
        if (e.source !== 'user') return;
        const b = document.createElement('button');
        b.className = 'btn small';
        b.textContent = t('an.edit') + ' ' + e.file;
        b.onclick = () => openEditor({ file: e.file });
        err.append(b);
      });
    }
  }

  // ---------------------------------------------------------------- form
  function roleValue(role) {
    const s = state.spec;
    const cols = state.dataset.columns.map(c => c.name);
    const has = c => c && cols.includes(c);
    const numeric = state.dataset.columns.filter(c => c.kind === 'numeric').map(c => c.name);
    const ys = s.y.filter(has).length ? s.y.filter(has) : numeric.filter(c => c !== s.x).slice(0, 1);
    switch (role) {
      case 'x': return has(s.x) ? s.x : '';
      case 'y': return ys[0] || '';
      case 'y2': return ys[1] || (s.y2 || []).find(has) || numeric.find(c => c !== ys[0] && c !== s.x) || '';
      case 'ys': return ys;
      case 'xs': return has(s.x) ? [s.x] : [];
      case 'xerr': case 'yerr': case 'hue': case 'z': return has(s[role]) ? s[role] : '';
      default: return null;
    }
  }

  function defaultValue(prm) {
    const d = prm.default;
    if (prm.type === 'column' || prm.type === 'columns') {
      const v = typeof d === 'string' ? roleValue(d) : null;
      if (v !== null) return v;
      return d ?? (prm.type === 'columns' ? [] : '');
    }
    return d ?? (prm.type === 'bool' ? false : '');
  }

  function renderMain(id) {
    A.current = id;
    $$('#anList .an-item').forEach(b => b.classList.toggle('active', b.dataset.id === id));
    const p = plugin();
    const main = $('#anMain');
    main.innerHTML = '';
    const head = document.createElement('div');
    head.className = 'an-head';
    const desc = document.createElement('p');
    desc.className = 'an-desc';
    desc.textContent = L(p.description);
    desc.title = p.file + (p.source === 'user' ? ` (${t('an.user')})` : '');
    const edit = document.createElement('button');
    edit.className = 'btn small';
    edit.textContent = p.source === 'user' ? t('an.edit') : t('an.customize');
    edit.title = p.source === 'user' ? p.file : t('an.customize_hint');
    edit.onclick = () => (p.source === 'user' ? openEditor({ file: p.file }) : customize(p.id));
    head.append(desc, edit);
    main.append(head);

    const values = A.params[paramKey(id)] || {};
    const form = document.createElement('div');
    form.className = 'an-form';
    p.params.forEach(prm => form.append(field(prm, values[prm.id] !== undefined ? values[prm.id] : defaultValue(prm))));
    main.append(form);
    // Parameters with show_if: {other: [values]} appear only when the other parameter has one of those values.
    const applyShowIf = () => {
      const now = readForm();
      p.params.forEach(prm => {
        if (!prm.show_if) return;
        const el = $(`#anMain [data-param="${CSS.escape(prm.id)}"]`);
        if (el) el.hidden = !Object.entries(prm.show_if).every(([k, vals]) => [].concat(vals).includes(now[k]));
      });
    };
    form.addEventListener('change', applyShowIf);
    applyShowIf();

    const actions = document.createElement('div');
    actions.className = 'an-actions';
    const run = document.createElement('button');
    run.className = 'btn primary';
    run.textContent = t('an.run');
    run.onclick = () => runAnalysis(run);
    const rst = document.createElement('button');
    rst.className = 'btn';
    rst.textContent = t('an.reset');
    rst.title = t('an.reset_hint');
    rst.onclick = () => { forget(id); delete A.params[paramKey(id)]; renderMain(id); };
    actions.append(run, rst);
    if (p.missing.length) {
      const note = document.createElement('span');
      note.className = 'small muted';
      note.textContent = t('an.needs', { mods: p.missing.join(', ') });
      actions.append(note);
    }
    main.append(actions);
    const res = document.createElement('div');
    res.className = 'an-results';
    res.id = 'anResults';
    main.append(res);
    const kept = resultFor(id);
    if (kept) renderResult(kept);
  }

  // Results are kept per analysis and per data set, so they stay on screen after drawing them on a
  // copy of the figure, after plotting a result and coming back, or after looking at another analysis.
  const resultKey = (id, dsId) => `${id}|${dsId}`;
  function resultFor(id) {
    const ids = [state.dataset, ...state.history.map(h => h.dataset)].filter(Boolean).map(d => d.dataset_id);
    for (const dsId of ids) if (A.results[resultKey(id, dsId)]) return A.results[resultKey(id, dsId)];
    return null;
  }
  function forget(id) {
    Object.keys(A.results).forEach(k => { if (k.startsWith(id + '|')) delete A.results[k]; });
  }

  function plugin() { return A.list.plugins.find(p => p.id === A.current); }
  // Remembered parameters apply only to data with the same columns.
  function paramKey(id) { return id + '|' + state.dataset.columns.map(c => c.name).join('\u0001'); }

  function field(prm, value) {
    const f = document.createElement('div');
    f.className = 'field' + (prm.type === 'text' || prm.type === 'columns' ? ' wide' : '');
    f.dataset.param = prm.id;
    f.dataset.type = prm.type;
    const label = document.createElement('label');
    label.textContent = L(prm.label);
    let input;
    const cols = state.dataset.columns;
    if (prm.type === 'column') {
      input = document.createElement('select');
      fillSelect(input, [...(prm.optional ? [['', t('map.none')]] : []), ...cols.map(c => [c.name, c.name])], value || '');
    } else if (prm.type === 'columns') {
      input = document.createElement('div');
      input.className = 'checklist';
      cols.forEach(c => {
        const lab = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = c.name;
        cb.checked = (value || []).includes(c.name);
        const sp = document.createElement('span');
        sp.textContent = c.name;
        lab.append(cb, sp);
        input.append(lab);
      });
    } else if (prm.type === 'choice') {
      input = document.createElement('select');
      fillSelect(input, prm.choices.map(c => [c.value, L(c.label)]), value);
    } else if (prm.type === 'bool') {
      const lab = document.createElement('label');
      lab.className = 'check';
      input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = !!value;
      const sp = document.createElement('span');
      sp.textContent = L(prm.label);
      lab.append(input, sp);
      f.append(lab);
      return f;
    } else {
      input = document.createElement('input');
      input.type = prm.type === 'text' ? 'text' : 'number';
      if (prm.type === 'int') input.step = '1';
      if (prm.type === 'float') input.step = 'any';
      if (prm.min !== undefined && prm.min !== null) input.min = prm.min;
      if (prm.max !== undefined && prm.max !== null) input.max = prm.max;
      if (prm.optional) input.placeholder = 'auto';
      input.value = value ?? '';
    }
    f.append(label, input);
    if (prm.help) {
      const h = document.createElement('span');
      h.className = 'help';
      h.textContent = L(prm.help);
      f.append(h);
    }
    return f;
  }

  function readForm() {
    const out = {};
    $$('#anMain .an-form [data-param]').forEach(f => {
      const type = f.dataset.type;
      if (type === 'columns') out[f.dataset.param] = $$('input', f).filter(i => i.checked).map(i => i.value);
      else if (type === 'bool') out[f.dataset.param] = $('input', f).checked;
      else {
        const el = $('select, input', f);
        out[f.dataset.param] = (type === 'int' || type === 'float') ? (el.value === '' ? null : Number(el.value)) : el.value;
      }
    });
    return out;
  }

  // ---------------------------------------------------------------- run & results
  async function runAnalysis(btn) {
    const p = plugin();
    if (p.missing.length) {
      if (!(await ensureModules(p.missing))) return;
      await load(true);
      renderList();
    }
    const params = readForm();
    A.params[paramKey(p.id)] = params;
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = t('an.running');
    try {
      const res = await api('/api/analyses/run', { dataset_id: state.dataset.dataset_id, id: p.id, params,
        spec: specForServer(), lang: state.lang });
      A.results[resultKey(p.id, res.analysed_dataset)] = res;
      renderResult(res);
      if (res.overlays.length) showOnCopy(res);
    } catch (e) {
      if (e.code === 'missing_modules') {
        if (await ensureModules(e.data.modules)) { await load(true); renderList(); return runAnalysis(btn); }
      } else if (e.code === 'dataset_gone') {
        await reopenSource();
      } else {
        const box = $('#anResults');
        box.innerHTML = '';
        const err = document.createElement('div');
        err.className = 'error-box';
        err.style.position = 'static';
        err.textContent = e.message;
        box.append(err);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = old;
    }
  }

  function fmt(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
      if (Number.isInteger(v)) return v.toLocaleString(state.lang === 'it' ? 'it-IT' : 'en-US');
      const a = Math.abs(v);
      return (a !== 0 && (a < 1e-3 || a >= 1e6)) ? v.toExponential(4) : String(+v.toPrecision(6));
    }
    if (typeof v === 'boolean') return v ? '✓' : '✗';
    return String(v);
  }

  function htmlTable(columns, rows) {
    const table = document.createElement('table');
    const tr = document.createElement('tr');
    columns.forEach(c => { const th = document.createElement('th'); th.textContent = c; tr.append(th); });
    const thead = document.createElement('thead');
    thead.append(tr);
    const tbody = document.createElement('tbody');
    rows.forEach(r => {
      const row = document.createElement('tr');
      r.forEach(v => {
        const td = document.createElement('td');
        td.textContent = fmt(v);
        if (typeof v === 'number') td.className = 'num';
        row.append(td);
      });
      tbody.append(row);
    });
    table.append(thead, tbody);
    return table;
  }

  function toCSV(columns, rows) {
    const esc = v => { const s = v === null || v === undefined ? '' : String(v); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    return [columns.map(esc).join(','), ...rows.map(r => r.map(esc).join(','))].join('\n') + '\n';
  }

  function tableBlock(box, title, columns, rows, open = false) {
    const det = document.createElement('details');
    det.open = open;
    const sum = document.createElement('summary');
    sum.textContent = title + (rows.length > 1 ? `  (${rows.length})` : '');
    const wrap = document.createElement('div');
    wrap.className = 'tbl';
    wrap.append(htmlTable(columns, rows));
    const bar = document.createElement('div');
    bar.className = 'mini';
    const copy = document.createElement('button');
    copy.className = 'btn small';
    copy.textContent = t('an.copy');
    copy.onclick = async () => {
      const tsv = [columns.join('\t'), ...rows.map(r => r.map(v => v ?? '').join('\t'))].join('\n');
      try { await navigator.clipboard.writeText(tsv); toast(t('an.copied')); } catch (e) { toast(e.message, true); }
    };
    const csv = document.createElement('button');
    csv.className = 'btn small';
    csv.textContent = 'CSV';
    csv.onclick = () => download(new Blob([toCSV(columns, rows)], { type: 'text/csv' }), `${title.replace(/[^\w.-]+/g, '_')}.csv`);
    bar.append(copy, csv);
    det.append(sum, wrap, bar);
    box.append(det);
  }

  // The copy of the figure that shows this result, if one is open.
  const copyOf = res => state.views.find(v => v.runs.some(r => r.run === res.run_id));

  function renderResult(res) {
    const box = $('#anResults');
    if (!box) return;
    box.innerHTML = '';
    const bar = document.createElement('div');
    bar.className = 'an-actions';
    if (res.overlays.length) {
      const v = copyOf(res);
      const ov = document.createElement('button');
      ov.className = 'btn small primary';
      ov.textContent = v ? t('an.goto_copy') : t('an.overlay');
      ov.title = t('an.overlay_hint');
      ov.onclick = () => (v && state.views.includes(v) ? showView(v.id) : showOnCopy(res));
      bar.append(ov);
    }
    if (res.dataset) {
      const plot = document.createElement('button');
      plot.className = res.overlays.length ? 'btn small' : 'btn small primary';
      plot.textContent = t('an.plot');
      plot.title = t('an.plot_hint', { rows: res.dataset.rows.toLocaleString(LOCALE()), cols: res.dataset.columns.length });
      plot.onclick = () => plotResult(res);
      bar.append(plot);
    }
    if (bar.children.length) box.append(bar);
    res.texts.forEach(text => {
      const p = document.createElement('p');
      p.className = /^[a-zA-Z]+ ?=|^y =|^k =/.test(text) || /~/.test(text) ? 'eq' : 'small';
      p.textContent = text;
      box.append(p);
    });
    if (res.summary.length) {
      const rows = res.summary.map(s => [s.label, [fmt(s.value), s.error !== null && s.error !== undefined ? '± ' + fmt(s.error) : '',
        s.unit || ''].filter(Boolean).join(' ')]);
      tableBlock(box, t('an.summary'), [t('an.quantity'), t('an.value')], rows, true);
    }
    res.tables.forEach((tb, i) => tableBlock(box, tb.title, tb.columns, tb.rows, i === 0));
    if (res.references.length) {
      const det = document.createElement('details');
      const sum = document.createElement('summary');
      sum.textContent = t('an.refs');
      const ul = document.createElement('ul');
      ul.className = 'refs';
      res.references.forEach(r => { const li = document.createElement('li'); li.textContent = r; ul.append(li); });
      det.append(sum, ul);
      box.append(det);
    }
  }

  // Overlay descriptor for a figure spec; gets a fixed colour so the panel shows the real one.
  const stripOverlay = (o, res, spec, index) => {
    const { dataset, ...rest } = o;
    const out = { ...clone(rest), id: Math.random().toString(16).slice(2, 12), analysis_run: res.plugin.id,
      source_name: `${L(res.plugin.name)} · ${state.dataset ? state.dataset.name : ''}` };
    out.style = out.style || {};
    const pal = state.meta.palettes[spec.style.palette] || [];
    if (!out.style.color && pal.length) out.style.color = pal[(spec.y.length + index) % pal.length];
    return out;
  };

  // Draw the result's curves and bands on a copy of the figure (the original stays as it is).
  // The copy on screen gets the layers; otherwise the copy already showing this analysis, otherwise a
  // new copy. Running the same analysis again replaces its layers.
  function showOnCopy(res) {
    if (!state.dataset || state.dataset.dataset_id !== res.analysed_dataset) {
      toast(t('ov.other_data'), true);
      return;
    }
    if (!res.run_id) res.run_id = Math.random().toString(16).slice(2, 10);
    const v = state.views.find(x => x.id === state.view)
      || [...state.views].reverse().find(x => x.runs.some(r => r.id === res.plugin.id))
      || newView();
    const s = v.spec;
    s.overlays = (s.overlays || []).filter(o => o.analysis_run !== res.plugin.id);
    res.overlays.forEach(o => s.overlays.push(stripOverlay(o, res, s, s.overlays.length)));
    v.runs = v.runs.filter(r => r.id !== res.plugin.id);
    v.runs.push({ id: res.plugin.id, name: res.plugin.name, run: res.run_id });
    // A fit weighted by an error column: show the data with those error bars (on the copy only).
    const sigma = res.params && (res.params.sigma || res.params.yerr);
    if (sigma && !s.yerr && ['line', 'scatter', 'errorbar'].includes(s.kind)) {
      s.kind = 'errorbar';
      s.yerr = sigma;
      s.series = s.series || {};
      s.y.forEach(c => { s.series[c] = { ...(s.series[c] || {}), linestyle: 'none', marker: (s.series[c] || {}).marker || 'o' }; });
      toast(t('ov.errors_used', { col: sigma }));
    }
    if (state.view === v.id) { refreshSpecUI(); setTab('figure'); } else showView(v.id);
    viewsChanged();
  }

  // Keep the result buttons ("Show on a copy" / "Go to the copy") in step with the open copies.
  function viewsChanged() {
    const res = A.current && state.dataset ? resultFor(A.current) : null;
    if (res && $('#anResults')) renderResult(res);
  }

  function reset() {
    A.results = {};
    if (A.current && state.dataset) delete A.params[paramKey(A.current)];
    const m = $('#anMain');
    if (m) m.innerHTML = '';
    show();
  }

  function plotResult(res) {
    const views = stashViews();
    state.history.push({ dataset: state.dataset, spec: clone(state.spec), file: state.file, views });
    applyDataset(res.dataset);
    const pl = res.plot || {};
    const s = state.spec;
    ['kind', 'x', 'y', 'y2', 'hue', 'z', 'xerr', 'yerr'].forEach(k => { if (pl[k] !== undefined) s[k] = clone(pl[k]); });
    s.series = clone(pl.series || {});
    s.overlays = (pl.overlays || []).map((o, i) => stripOverlay(o, res, s, i));
    ['text', 'axes', 'style', 'legend'].forEach(k => { if (pl[k]) s[k] = merge(s[k], pl[k]); });
    syncControls();
    buildKindGallery();
    buildKindOptions();
    buildMapping(true);
    buildSeries();
    updateFigInfo();
    setTab('figure');
  }

  function back() {
    const prev = state.history.pop();
    if (!prev) return;
    const stack = state.history.slice();
    stashViews();
    applyDataset(prev.dataset, true);
    state.history = stack;
    state.spec = prev.spec;
    state.file = prev.file;
    state.views = prev.views || [];
    renderViewTabs();
    syncControls();
    buildKindGallery();
    buildKindOptions();
    buildMapping(true);
    buildSeries();
    updateDerived();
    scheduleRender(0);
  }

  function updateDerived() {
    const derived = !!(state.dataset && state.dataset.source && state.dataset.source.analysis);
    $('#derivedBox').hidden = !derived;
    if (derived) $('#derivedName').textContent = t('an.derived', { name: state.dataset.name });
    $('#btnBack').hidden = !state.history.length;
  }

  // ---------------------------------------------------------------- plugin files
  async function customize(id) {
    try {
      const r = await api('/api/plugins/customize', { id });
      await load(true);
      renderList();
      openEditor({ file: r.file });
    } catch (e) { handleError(e); }
  }

  async function newPlugin() {
    const name = prompt(t('an.new_name'), state.lang === 'it' ? 'la mia analisi' : 'my analysis');
    if (!name) return;
    try {
      const r = await api('/api/plugins/new', { name });
      await load(true);
      const created = A.list.plugins.find(p => p.file === r.file);
      if (created) A.current = created.id;
      show();
      openEditor({ file: r.file });
    } catch (e) { handleError(e); }
  }

  async function openEditor(ref) {
    try {
      const r = await api('/api/plugins/read', ref);
      A.editing = r.file;
      $('#pluginFile').textContent = r.file;
      $('#pluginPath').textContent = t('an.editor_hint', { dir: A.list ? A.list.user_dir : '' });
      $('#pluginCode').value = r.code;
      $('#pluginErrors').hidden = true;
      $('#pluginDialog').showModal();
    } catch (e) { handleError(e); }
  }

  async function save() {
    try {
      const r = await api('/api/plugins/save', { file: A.editing, code: $('#pluginCode').value });
      await load(true);
      renderList();
      if (r.errors.length) {
        $('#pluginErrors').textContent = r.errors.map(e => e.error).join('\n');
        $('#pluginErrors').hidden = false;
        return;
      }
      $('#pluginErrors').hidden = true;
      toast(t('an.saved'));
      const p = A.list.plugins.find(q => q.file === A.editing && q.source === 'user');
      if (p) { A.current = p.id; renderList(); renderMain(p.id); }
    } catch (e) {
      $('#pluginErrors').textContent = e.message;
      $('#pluginErrors').hidden = false;
    }
  }

  async function disable() {
    if (!A.editing || !confirm(t('an.disable_confirm', { file: A.editing }))) return;
    try {
      await api('/api/plugins/disable', { file: A.editing });
      $('#pluginDialog').close();
      await load(true);
      if (!A.list.plugins.some(p => p.id === A.current)) A.current = null;
      show();
    } catch (e) { handleError(e); }
  }

  function bind() {
    $('#btnNewPlugin').onclick = newPlugin;
    $('#btnPluginFolder').onclick = () => api('/api/plugins/folder', {}).then(r => toast(r.path)).catch(handleError);
    $('#btnReloadPlugins').onclick = async () => { await api('/api/plugins/reload', {}).catch(handleError); await load(true); show(); toast(t('an.reloaded')); };
    $('#btnSavePlugin').onclick = save;
    $('#btnDisablePlugin').onclick = disable;
    $('#btnBack').onclick = back;
    const code = $('#pluginCode');
    code.addEventListener('keydown', e => {
      if (e.key === 'Tab') {
        e.preventDefault();
        const { selectionStart: a, selectionEnd: b, value } = code;
        code.value = value.slice(0, a) + '    ' + value.slice(b);
        code.selectionStart = code.selectionEnd = a + 4;
      } else if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        save();
      }
    });
  }
  bind();

  return { show, updateDerived, load, renderList, reset, viewsChanged, relabel: () => { if (A.list) show(); } };
})();
