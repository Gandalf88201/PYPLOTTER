"""Exports beyond Matplotlib images: interactive Plotly HTML and a reproducible Python bundle."""
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from . import plotting
from .catalog import PALETTES

HERE = Path(__file__).resolve().parent

MAKE_FIGURE = '''"""Re-creates the figure exported from PyPlotter.

Needs Python 3.10+ with numpy, pandas and matplotlib (pip install numpy pandas matplotlib).
Run:  python make_figure.py            -> figure.pdf, figure.png (and the other formats listed below)
Edit spec.json to change colours, labels, fonts or size, then run it again.
"""
import json
from pathlib import Path

import pandas as pd

from plotting import render

HERE = Path(__file__).resolve().parent
spec = json.loads((HERE / 'spec.json').read_text(encoding='utf-8'))
df = pd.read_csv(HERE / 'data.csv', parse_dates={dates!r})
# analysis results drawn over the data (fits with confidence bands, smoothing, …)
overlays = {{o['id']: pd.read_csv(HERE / o['file']) for o in spec.get('overlays', []) if o.get('file')}}
# other data files drawn in the same figure
extras = {{e['id']: pd.read_csv(HERE / e['file']) for e in spec.get('extra', []) if e.get('file')}}

for fmt in {formats!r}:
    out = HERE / f'figure.{{fmt}}'
    out.write_bytes(render(df, spec, fmt, overlay_data=overlays, extra_data=extras))
    print('wrote', out.name)
'''


def used_columns(spec):
    cols = [spec.get('x'), spec.get('hue'), spec.get('z'), spec.get('xerr'), spec.get('yerr'),
            *(spec.get('y') or []), *(spec.get('y2') or [])]
    return [c for c in dict.fromkeys(cols) if c]


def references_text(modules, spec, extra=()):
    """Plain-text software references for a figure: core modules plus the optional ones it used."""
    from .catalog import requirements_for
    used = {'numpy', 'pandas', 'matplotlib'} | set(requirements_for(spec.get('kind'), spec.get('style', {}).get('base'),
                                                                 spec.get('style', {}).get('cmap')))
    lines = ['Figure made with PyPlotter (MIT licence). Please cite the software it relies on:', '']
    for m in modules:
        if m['id'] in used and m.get('cite'):
            lines.append(f'- {m["pip"]} ({m.get("license", "")}): {m["cite"]}')
    palette = spec.get('style', {}).get('palette', '')
    if palette == 'okabe-ito':
        lines.append('- Colour palette: Okabe, M. & Ito, K. Color Universal Design (CUD): how to make figures and '
                     'presentations that are friendly to colorblind people (2008). https://jfly.uni-koeln.de/color/')
    elif palette.startswith('tol-'):
        lines.append('- Colour palette: Tol, P. Colour Schemes. SRON Technical Note SRON/EPS/TN/09-002, issue 3.2 (2021). '
                     'https://personal.sron.nl/~pault/')
    extra = [r for r in dict.fromkeys(extra) if r]
    if extra:
        lines += ['', 'Analyses applied to the data:']
        lines += [f'- {r}' for r in extra]
    return '\n'.join(lines) + '\n'


def script_bundle(df, spec, name='figure', modules=(), extra_refs=(), source=None, overlay_data=None,
                  extra_data=None):
    """ZIP with data.csv, spec.json, plotting.py, catalog.py, make_figure.py and REFERENCES.txt."""
    spec = plotting.normalize_spec(spec)
    cols = used_columns(spec)
    if spec['kind'] in ('corr', 'pairplot', 'heatmap') and not spec['y']:
        cols = list(df.columns)
    data = df[cols] if cols else df
    dates = [c for c in data.columns if pd.api.types.is_datetime64_any_dtype(data[c])]
    overlay_files = {}
    clean = []
    for k, o in enumerate(spec.get('overlays') or []):
        o = {key: v for key, v in o.items() if key not in ('source', 'dataset', 'dataset_id', 'references')}
        frame = (overlay_data or {}).get(o.get('id'))
        if frame is not None:
            fname = f'overlay_{k + 1}.csv'
            cols = [c for c in dict.fromkeys([o.get('x'), o.get('y'), o.get('lo'), o.get('hi')]) if c]
            overlay_files[fname] = frame[cols].to_csv(index=False)
            o['file'] = fname
        clean.append(o)
    extras = []
    for k, e in enumerate(spec.get('extra') or []):
        e = {key: v for key, v in e.items() if key not in ('source', 'dataset_id')}
        frame = (extra_data or {}).get(e.get('id'))
        if frame is not None:
            fname = f'extra_{k + 1}.csv'
            cols = [c for c in dict.fromkeys([e.get('x'), *(e.get('y') or []), e.get('yerr')]) if c]
            overlay_files[fname] = frame[cols].to_csv(index=False)
            e['file'] = fname
            extras.append(e)
    spec = dict(spec, overlays=clean, extra=extras)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'{name}/data.csv', data.to_csv(index=False))
        for fname, text in overlay_files.items():
            zf.writestr(f'{name}/{fname}', text)
        zf.writestr(f'{name}/spec.json', json.dumps(spec, indent=2, ensure_ascii=False))
        zf.writestr(f'{name}/plotting.py', (HERE / 'plotting.py').read_text(encoding='utf-8'))
        zf.writestr(f'{name}/catalog.py', (HERE / 'catalog.py').read_text(encoding='utf-8'))
        zf.writestr(f'{name}/make_figure.py', MAKE_FIGURE.format(dates=dates, formats=['pdf', 'png', 'svg']))
        zf.writestr(f'{name}/REFERENCES.txt', references_text(modules, spec, extra_refs))
        if source:
            zf.writestr(f'{name}/provenance.json', json.dumps(_provenance(source), indent=2, ensure_ascii=False, default=str))
        zf.writestr(f'{name}/LICENSE.txt', (HERE.parent / 'LICENSE').read_text(encoding='utf-8'))
    return buf.getvalue()


# ------------------------------------------------------------------ Plotly (interactive HTML)
PLOTLY_KINDS = {'line', 'scatter', 'step', 'area', 'errorbar', 'regression', 'bar', 'barh', 'hist', 'box',
                'violin', 'heatmap', 'corr', 'contour', 'pie', 'kde', 'ecdf', 'stem', 'polar', 'hexbin', 'hist2d'}


def plotly_html(df, spec, overlay_data=None, extra_data=None):
    import plotly.graph_objects as go

    spec = plotting.normalize_spec(spec)
    kind = spec['kind']
    if kind not in PLOTLY_KINDS:
        raise plotting.SpecError(f'Interactive HTML is not available for “{kind}”; export SVG or PDF instead.')
    d = plotting.Data(df, spec)
    colors = plotting.palette_colors(spec['style']['palette'], 12) if spec['style']['palette'] in PALETTES \
        else plotting.palette_colors('okabe-ito', 12)
    fig = go.Figure()
    st = spec['style']
    counter = [0]

    def color(key):
        over = spec['series'].get(str(key), {})
        c = over.get('color') or colors[counter[0] % len(colors)]
        counter[0] += 1
        return c

    def label(key, default):
        return spec['series'].get(str(key), {}).get('label') or default

    ycols = spec['y']
    cscale = spec['style']['cmap'] if not spec['style']['cmap'].startswith('cmc.') else 'Viridis'
    if kind in ('line', 'scatter', 'step', 'area', 'errorbar', 'regression', 'stem', 'polar'):
        for axis_cols, yaxis in ((ycols, 'y'), (spec['y2'] if kind in ('line', 'scatter', 'step', 'errorbar') else [], 'y2')):
            for ycol in axis_cols:
                for g, sub in d.groups():
                    x, y, ok = d.xy(ycol, sub)
                    key = ycol if g is None else f'{ycol}::{g}'
                    name = label(key, plotting._series_label(ycol, g, len(axis_cols)))
                    c = color(key)
                    if kind == 'polar':
                        fig.add_trace(go.Scatterpolar(theta=x if st['polar_degrees'] else np.rad2deg(x), r=y,
                                                      mode='lines', name=name, line={'color': c}))
                        continue
                    mode = 'markers' if kind in ('scatter', 'regression') else 'lines+markers' if st['marker'] else 'lines'
                    tr = dict(x=x, y=y, name=name, mode=mode, yaxis=yaxis,
                              line={'color': c, 'width': st['linewidth'] * 1.5,
                                    'shape': 'hvh' if kind == 'step' else 'linear'},
                              marker={'color': c, 'size': st['markersize'] * 1.5})
                    if kind == 'area':
                        tr['fill'] = 'tozeroy'
                    if kind == 'scatter' and spec['z']:
                        tr['marker'] = {'color': d.numeric(spec['z'], sub[ok]).to_numpy(), 'colorscale': cscale,
                                        'showscale': True, 'size': st['markersize'] * 1.5,
                                        'colorbar': {'title': spec['z']}}
                    if kind == 'errorbar':
                        if spec['yerr']:
                            tr['error_y'] = {'type': 'data', 'array': d.numeric(spec['yerr'], sub[ok]).to_numpy()}
                        if spec['xerr']:
                            tr['error_x'] = {'type': 'data', 'array': d.numeric(spec['xerr'], sub[ok]).to_numpy()}
                    fig.add_trace(go.Scatter(**tr))
                    if kind == 'regression' and len(x) >= 3:
                        f, eq, r2 = plotting.fit_curve(x.astype(float), y, st['fit'], st['fit_degree'])
                        t = np.linspace(float(np.nanmin(x)), float(np.nanmax(x)), 300)
                        fig.add_trace(go.Scatter(x=t, y=f(t), mode='lines', line={'color': c},
                                                 name=f'{eq} (R² = {r2:.4f})'))
    elif kind in ('bar', 'barh'):
        table, err = plotting._aggregate(d, ycols)
        cats = [str(c) for c in table.index]
        for col in table.columns:
            vals = table[col].to_numpy()
            kw = dict(name=label(col, str(col)), marker_color=color(col))
            fig.add_trace(go.Bar(x=vals, y=cats, orientation='h', **kw) if kind == 'barh' else go.Bar(x=cats, y=vals, **kw))
        fig.update_layout(barmode='stack' if st['stacked'] else 'group')
    elif kind in ('hist', 'box', 'violin', 'kde', 'ecdf'):
        for lab, key, v in plotting._dist_groups(d, ycols):
            c = color(key)
            name = label(key, lab)
            if kind == 'hist':
                fig.add_trace(go.Histogram(x=v, name=name, marker_color=c, nbinsx=int(st['bins']), opacity=0.7,
                                           histnorm='probability density' if st['density'] else ''))
            elif kind == 'box':
                fig.add_trace(go.Box(y=v, name=name, marker_color=c))
            elif kind == 'violin':
                fig.add_trace(go.Violin(y=v, name=name, line_color=c, box_visible=True, meanline_visible=True))
            elif kind == 'kde':
                x, y = plotting.kde_curve(v)
                fig.add_trace(go.Scatter(x=x, y=y, name=name, line={'color': c}, fill='tozeroy' if st['fill'] else None))
            else:
                v = np.sort(np.asarray(v, dtype=float))
                fig.add_trace(go.Scatter(x=v, y=np.arange(1, v.size + 1) / v.size, name=name,
                                         line={'color': c, 'shape': 'hv'}))
        if kind == 'hist':
            fig.update_layout(barmode='stack' if st['stacked'] else 'overlay')
    elif kind in ('heatmap', 'contour', 'corr'):
        if kind == 'corr':
            cols = ycols if len(ycols) >= 2 else [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            mat = df[cols].corr()
            fig.add_trace(go.Heatmap(z=mat.to_numpy(), x=cols, y=cols, colorscale='RdBu', zmin=-1, zmax=1, reversescale=True))
        else:
            grid = plotting._grid_from_xyz(d)
            if grid is None:
                cols = ycols or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
                fig.add_trace(go.Heatmap(z=df[cols].to_numpy(dtype=float), x=cols, colorscale=cscale))
            else:
                trace = go.Contour if kind == 'contour' else go.Heatmap
                fig.add_trace(trace(z=grid.to_numpy(dtype=float), x=list(grid.columns), y=list(grid.index),
                                    colorscale=cscale, colorbar={'title': spec['z']}))
    elif kind in ('hexbin', 'hist2d'):
        x, y, _ = d.xy(ycols[0])
        fig.add_trace(go.Histogram2d(x=x, y=y, colorscale=cscale, nbinsx=int(st['gridsize']), nbinsy=int(st['gridsize'])))
    elif kind == 'pie':
        table, _ = plotting._aggregate(d, ycols[:1])
        fig.add_trace(go.Pie(labels=[str(c) for c in table.index], values=table.iloc[:, 0].to_numpy(),
                             marker={'colors': colors}, sort=False))

    if kind in ('line', 'scatter', 'step', 'errorbar', 'area', 'regression'):
        for e in spec.get('extra') or []:
            frame = (extra_data or {}).get(e.get('id'))
            if frame is None or not e.get('enabled', True) or e.get('x') not in frame:
                continue
            for ycol in [c for c in (e.get('y') or []) if c in frame]:
                key = f'{e.get("id")}:{ycol}'
                sub = frame[[e['x'], ycol] + ([e['yerr']] if e.get('yerr') in frame else [])].dropna()
                tr = dict(x=sub[e['x']], y=sub[ycol], name=label(key, e.get('name') or ycol),
                          mode='markers' if kind in ('scatter', 'regression') else 'lines',
                          line={'color': color(key)})
                if kind == 'errorbar' and e.get('yerr') in sub:
                    tr['error_y'] = {'type': 'data', 'array': sub[e['yerr']]}
                fig.add_trace(go.Scatter(**tr))
    for o in spec.get('overlays') or []:
        frame = (overlay_data or {}).get(o.get('id'))
        if frame is None and not o.get('dataset_id'):
            frame = df
        if frame is None or o.get('hidden') or o.get('x') not in frame or o.get('y') not in frame:
            continue
        sub = frame.sort_values(o['x'])
        st = o.get('style') or {}
        c = st.get('color') or color(f'overlay:{o.get("id")}')
        name = o.get('label') or o['y']
        if o.get('lo') in sub and o.get('hi') in sub and o.get('band', True):
            fig.add_trace(go.Scatter(x=sub[o['x']], y=sub[o['hi']], mode='lines', line={'width': 0}, showlegend=False,
                                     hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=sub[o['x']], y=sub[o['lo']], mode='lines', line={'width': 0}, fill='tonexty',
                                     fillcolor=c, opacity=0.25, name=f'{name} ({o.get("band_label") or "95% CI"})'))
        marker_only = st.get('linestyle') in ('none', '')
        fig.add_trace(go.Scatter(x=sub[o['x']], y=sub[o['y']], name=name, mode='markers' if marker_only else 'lines',
                                 line={'color': c, 'dash': 'dash' if st.get('linestyle') == '--' else None},
                                 marker={'color': c, 'size': 9, 'symbol': 'triangle-down' if st.get('marker') == 'v' else 'circle'}))

    t, a = spec['text'], spec['axes']
    font = t['font'] or 'Arial, Helvetica, sans-serif'
    auto_x = spec['x'] or ''
    auto_y = ycols[0] if len(ycols) == 1 else ''
    if kind in ('hist', 'kde', 'ecdf'):
        auto_x, auto_y = auto_y, ''
    layout = dict(template='simple_white', title=t['title'] or None, font={'family': font, 'size': float(t['size']) * 1.6},
                  xaxis={'title': t['xlabel'] or auto_x, 'type': 'log' if a['xscale'] == 'log' else None,
                         'mirror': a['mirror_ticks'], 'ticks': 'inside' if a['tick_direction'] == 'in' else 'outside',
                         'showgrid': a['grid'] in ('major', 'both')},
                  yaxis={'title': t['ylabel'] or auto_y, 'type': 'log' if a['yscale'] == 'log' else None,
                         'mirror': a['mirror_ticks'], 'ticks': 'inside' if a['tick_direction'] == 'in' else 'outside',
                         'showgrid': a['grid'] in ('major', 'both')},
                  showlegend=spec['legend']['show'] != 'hide')
    if spec['y2'] and kind in ('line', 'scatter', 'step', 'errorbar'):
        layout['yaxis2'] = {'title': t['y2label'] or spec['y2'][0], 'overlaying': 'y', 'side': 'right'}
    if kind == 'barh':
        layout['xaxis']['title'], layout['yaxis']['title'] = layout['yaxis']['title'], layout['xaxis']['title']
    fig.update_layout(**layout)
    for axis, lo, hi in (('xaxis', a['xmin'], a['xmax']), ('yaxis', a['ymin'], a['ymax'])):
        lo, hi = plotting._num(lo), plotting._num(hi)
        if lo is not None and hi is not None:
            fig.update_layout(**{axis: {'range': [lo, hi]}})
    return fig.to_html(include_plotlyjs=True, full_html=True, config={'toImageButtonOptions': {'format': 'svg'}}).encode('utf-8')


def _provenance(source):
    """How the plotted data was obtained: file/table/options, then each analysis with its parameters."""
    steps, node = [], source
    while isinstance(node, dict) and node.get('analysis'):
        steps.append({'analysis': node['analysis'], 'parameters': node.get('params', {})})
        node = node.get('parent')
    origin = {k: v for k, v in (node or {}).items() if k in ('sample', 'table', 'options')}
    return {'schema': 'pyplotter-provenance/1', 'origin': origin, 'analyses': list(reversed(steps))}
