// Several data files: the list of loaded files, combining them in one figure (same axes or one
// panel per file), and a health check of the local service (connection lost, newer version).
'use strict';

window.Files = (() => {
  const F = { list: [], settings: {} };       // list: {id, ds, info, name}; settings[id]: {enabled, x, y, yerr}

  const active = () => (state.dataset ? state.dataset.dataset_id : null);
  const layout = () => {
    state.spec.layout = Object.assign({ mode: 'single', ncols: 2, share: true, letters: true, titles: true },
      state.spec.layout || {});
    return state.spec.layout;
  };

  function uniqueName(name) {
    const names = new Set(F.list.map(e => e.name));
    if (!names.has(name)) return name;
    let k = 2;
    while (names.has(`${name} (${k})`)) k++;
    return `${name} (${k})`;
  }

  function add(ds, info, enabled) {
    F.list.push({ id: ds.dataset_id, ds, info, name: uniqueName(ds.name) });
    F.settings[ds.dataset_id] = { enabled: !!enabled };
  }

  function replace(oldId, ds, info) {
    const e = F.list.find(x => x.id === oldId);
    if (!e) return add(ds, info, false);
    const st = F.settings[oldId] || { enabled: false };
    delete F.settings[oldId];
    F.settings[ds.dataset_id] = st;
    Object.assign(e, { id: ds.dataset_id, ds, info });
  }

  function clear() {
    F.list = [];
    F.settings = {};
    render();
  }

  function activate(id) {
    const e = F.list.find(x => x.id === id);
    if (!e || id === active()) return;
    const prev = active();
    const combined = F.list.some(x => x.id !== prev && F.settings[x.id] && F.settings[x.id].enabled);
    if (prev && F.settings[prev] && combined) F.settings[prev].enabled = true;   // keep the same set of files
    showFileControls(e.info);
    applyDataset(e.ds);
    setTab('figure');
  }

  function remove(id) {
    const i = F.list.findIndex(x => x.id === id);
    if (i < 0) return;
    F.list.splice(i, 1);
    delete F.settings[id];
    if (id === active()) {
      const next = F.list[0];
      if (next) {
        showFileControls(next.info);
        applyDataset(next.ds);
      } else {
        clearDataset();
      }
    } else {
      render();
      scheduleRender(0);
    }
  }

  // Columns used for another file: the user's choice, else the same names as the current figure, else its defaults.
  function resolved(e) {
    const st = F.settings[e.id] || {};
    const cols = new Set(e.ds.columns.map(c => c.name));
    const has = c => c && cols.has(c);
    const s = state.spec;
    const x = st.x !== undefined ? st.x : (has(s.x) ? s.x : e.ds.mapping.x);
    let y = st.y;
    if (!y) {
      y = s.y.filter(has);
      if (!y.length) y = (e.ds.mapping.y || []).slice(0, Math.max(1, s.y.length));
    }
    const yerr = st.yerr !== undefined ? st.yerr : (has(s.yerr) ? s.yerr : null);
    return { x: x || null, y: y.filter(has), yerr: has(yerr) ? yerr : null };
  }

  function extraSpec() {
    if (!state.dataset || !F.list.some(e => e.id === active())) return [];
    return F.list.filter(e => e.id !== active() && F.settings[e.id] && F.settings[e.id].enabled).map(e => {
      const r = resolved(e);
      return { id: e.id, dataset_id: e.id, source: e.ds.source, name: e.name, enabled: true, ...r };
    });
  }

  // ---------------------------------------------------------------- UI
  function render() {
    renderList();
    renderCombine();
  }

  function renderList() {
    const box = $('#loadedList');
    box.innerHTML = '';
    $('#loadedBox').hidden = !F.list.length;
    F.list.forEach(e => {
      const row = document.createElement('div');
      row.className = 'file-row' + (e.id === active() ? ' active' : '');
      row.title = t('files.activate');
      const name = document.createElement('span');
      name.className = 'fname';
      name.textContent = e.name;
      const meta = document.createElement('span');
      meta.className = 'meta';
      meta.textContent = `${e.ds.rows.toLocaleString(LOCALE())}×${e.ds.columns.length}`;
      const x = document.createElement('button');
      x.className = 'x';
      x.type = 'button';
      x.textContent = '✕';
      x.title = t('files.remove');
      x.onclick = ev => { ev.stopPropagation(); remove(e.id); };
      row.append(name, meta, x);
      row.onclick = () => activate(e.id);
      box.append(row);
    });
  }

  function renderCombine() {
    const box = $('#combineBox');
    const others = F.list.filter(e => e.id !== active());
    const show = !!state.dataset && F.list.some(e => e.id === active()) && others.length > 0;
    box.hidden = !show;
    if (!show) return;
    const lay = layout();
    $$('#layoutSeg [data-layout]').forEach(b => {
      b.classList.toggle('active', b.dataset.layout === lay.mode);
      b.onclick = () => { lay.mode = b.dataset.layout; renderCombine(); buildSeries(); scheduleRender(0); };
    });
    $('#panelOpts').hidden = lay.mode !== 'panels';
    const bindOpt = (id, key, type) => {
      const el = $('#' + id);
      if (type === 'check') el.checked = !!lay[key]; else el.value = lay[key];
      el.onchange = () => { lay[key] = type === 'check' ? el.checked : Math.max(1, Number(el.value) || 1); scheduleRender(0); };
    };
    bindOpt('panelCols', 'ncols', 'num');
    bindOpt('panelShare', 'share', 'check');
    bindOpt('panelLetters', 'letters', 'check');
    bindOpt('panelTitles', 'titles', 'check');

    const list = $('#combineList');
    list.innerHTML = '';
    others.forEach(e => {
      const st = F.settings[e.id] = F.settings[e.id] || { enabled: false };
      const r = resolved(e);
      const card = document.createElement('div');
      card.className = 'combine-file' + (st.enabled ? '' : ' off');
      const head = document.createElement('label');
      head.className = 'head';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!st.enabled;
      const nm = document.createElement('span');
      nm.textContent = e.name;
      head.append(cb, nm);
      cb.onchange = () => { st.enabled = cb.checked; renderCombine(); buildSeries(); scheduleRender(0); };
      const body = document.createElement('div');
      body.className = 'body';
      const cols = e.ds.columns.map(c => [c.name, c.name]);
      const fx = document.createElement('div');
      fx.className = 'field';
      fx.innerHTML = `<label>${t('map.x')}</label>`;
      const sx = document.createElement('select');
      fillSelect(sx, [['', t('map.index')], ...cols], r.x || '');
      sx.onchange = () => { st.x = sx.value || null; scheduleRender(0); };
      fx.append(sx);
      const fy = document.createElement('div');
      fy.className = 'field';
      fy.innerHTML = `<label>${t('map.y')}</label>`;
      const cl = document.createElement('div');
      columnPicker(cl, {
        columns: e.ds.columns, selected: r.y, tags: false,
        pickable: c => c.kind === 'numeric' && c.name !== resolved(e).x,
        onChange: list => { st.y = list; buildSeries(); scheduleRender(0); },
      });
      fy.append(cl);
      const fe = document.createElement('div');
      fe.className = 'field';
      fe.innerHTML = `<label>${t('map.yerr')}</label>`;
      const se = document.createElement('select');
      fillSelect(se, [['', t('map.none')], ...cols], r.yerr || '');
      se.onchange = () => { st.yerr = se.value || null; scheduleRender(0); };
      fe.append(se);
      body.append(fx, fy, fe);
      card.append(head, body);
      list.append(card);
    });
  }

  // ---------------------------------------------------------------- health of the local service
  const BUILD = (document.querySelector('meta[name="pp-build"]') || {}).content || '';
  let healthBusy = false;

  function banner(kind) {
    const b = $('#healthBanner');
    b.hidden = !kind;
    $('#app').classList.toggle('with-banner', !b.hidden || !$('#restartBanner').hidden);
    if (!kind) return;
    $('#healthText').textContent = t(kind === 'down' ? 'health.down' : 'health.stale');
    const btn = $('#btnHealth');
    btn.textContent = t(kind === 'down' ? 'health.retry' : 'health.reload');
    btn.onclick = () => (kind === 'down' ? health() : location.reload());
  }

  async function health() {
    if (healthBusy) return;
    healthBusy = true;
    try {
      const st = await api('/api/status');
      banner(st.build && BUILD && !BUILD.startsWith('{{') && st.build !== BUILD ? 'stale' : null);
    } catch (e) {
      if (e.code === 'network') banner('down');
    } finally {
      healthBusy = false;
    }
  }

  setInterval(health, 15000);
  window.addEventListener('focus', health);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) health(); });

  return { add, replace, clear, activate, remove, render, extraSpec, health, list: () => F.list };
})();
