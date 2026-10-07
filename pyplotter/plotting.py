"""PyPlotter figure renderer.

``render(df, spec, fmt)`` turns a DataFrame and a JSON figure specification into PNG, TIFF,
JPEG, PDF, SVG or EPS bytes. It depends only on NumPy, pandas and Matplotlib (seaborn for
strip/swarm plots), so the file can be shipped next to an exported figure and re-run
without PyPlotter: ``python make_figure.py``.
"""
import copy
import io
import math
import logging
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import colors as mcolors, dates as mdates, rc_context, style as mstyle, ticker  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

try:
    from . import catalog
except ImportError:          # standalone copy next to an exported figure
    import catalog

logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

UNITS = {'in': 1.0, 'cm': 1 / 2.54, 'mm': 1 / 25.4, 'pt': 1 / 72}
MAX_PIXELS = 400e6
MAX_CORR_COLUMNS = 2000      # a larger matrix has more cells than a figure has pixels
SMOOTH_MATRIX = 512          # larger matrices are drawn anti-aliased: nearest-neighbour would drop rows
MAX_DRAWN_SERIES = 2000      # one line, box… per column: beyond this a figure takes minutes (a heat map, not)
WHOLE_TABLE_KINDS = {'heatmap', 'corr', 'contour', 'pairplot', 'pie', 'hexbin', 'hist2d', 'surface3d'}   # not one artist per column

DEFAULT_SPEC = {
    'kind': 'line', 'lang': 'en',
    'x': None, 'y': [], 'y2': [], 'hue': None, 'z': None, 'xerr': None, 'yerr': None,
    'series': {},
    'overlays': [],
    'figure': {'width': 89, 'height': 67, 'units': 'mm', 'dpi': 600, 'transparent': False, 'background': '#ffffff'},
    'text': {'title': '', 'xlabel': '', 'ylabel': '', 'y2label': '', 'zlabel': '', 'font': '', 'size': 8,
             'title_size': 9, 'label_size': 8, 'tick_size': 7, 'legend_size': 7, 'mathtext': 'dejavusans',
             'bold_labels': False},
    'axes': {'xscale': 'linear', 'yscale': 'linear', 'xmin': None, 'xmax': None, 'ymin': None, 'ymax': None,
             'zmin': None, 'zmax': None,
             'y2min': None, 'y2max': None, 'grid': 'auto', 'tick_direction': 'in', 'minor_ticks': True,
             'mirror_ticks': True, 'spines': 'box', 'invert_x': False, 'invert_y': False, 'aspect': 'auto',
             'xrotation': 0, 'sci': False, 'linewidth': 0.8},
    'legend': {'show': 'auto', 'loc': 'best', 'frame': False, 'ncol': 1, 'title': '', 'pos': None},
    'style': {'base': 'publication', 'palette': 'okabe-ito', 'cmap': 'viridis', 'cmap_reverse': False,
              'linewidth': 1.2, 'linestyle': '-', 'marker': '', 'markersize': 4, 'alpha': 1.0,
              'bins': 30, 'density': False, 'stacked': False, 'fill': True, 'levels': 12, 'contour_lines': True,
              'gridsize': 40, 'fit': 'linear', 'fit_degree': 2, 'annotate': False, 'capsize': 2,
              'error_style': 'bars', 'colorbar': True, 'vmin': None, 'vmax': None, 'polar_degrees': True,
              'bar_width': 0.8, 'agg': 'mean', 'show_fliers': True,
              'elev': 25, 'azim': -60, 'wireframe': False, 'connect': False},
    # Texts the user dragged on the figure: {id: [dx, dy]} in points from where they are drawn by default
    # (titles, axis labels) or from the point they label (value labels); see movables().
    'moved': {},
    # Texts the user rewrote on the figure that have no field of their own (value labels, slice labels,
    # panel titles…): {id: text}. Titles and axis labels are written in spec['text'] instead.
    'texts': {},
}

LABELS = {
    'en': {'count': 'Count', 'density': 'Density', 'probability': 'Cumulative probability', 'value': 'Value',
           'index': 'Index', 'fit': 'fit', 'frequency': 'Frequency', 'correlation': 'Correlation'},
    'it': {'count': 'Conteggio', 'density': 'Densità', 'probability': 'Probabilità cumulativa', 'value': 'Valore',
           'index': 'Indice', 'fit': 'fit', 'frequency': 'Frequenza', 'correlation': 'Correlazione'},
}


class SpecError(ValueError):
    """The specification does not fit the data (missing column, wrong type…).

    key and vars, when given, let the interface show the message in its own language."""

    def __init__(self, message, key=None, **values):
        super().__init__(message)
        self.key, self.values = key, values


# ------------------------------------------------------------------ spec helpers
def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict) and key != 'series':
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def normalize_spec(spec):
    spec = deep_merge(DEFAULT_SPEC, spec or {})
    if spec['kind'] not in catalog.KINDS:
        raise SpecError(f'Unknown plot type: {spec["kind"]}')
    for key in ('y', 'y2'):
        v = spec.get(key) or []
        spec[key] = [v] if isinstance(v, str) else [c for c in v if c]
    for key in ('x', 'hue', 'z', 'xerr', 'yerr'):
        spec[key] = spec.get(key) or None
    spec['overlays'] = [o for o in (spec.get('overlays') or []) if isinstance(o, dict)]
    moved = spec.get('moved') if isinstance(spec.get('moved'), dict) else {}
    spec['moved'] = {str(k): (float(v[0]), float(v[1])) for k, v in moved.items()
                     if isinstance(v, (list, tuple)) and len(v) == 2 and all(_num(c) is not None for c in v)}
    texts = spec.get('texts') if isinstance(spec.get('texts'), dict) else {}
    spec['texts'] = {str(k): str(v) for k, v in texts.items() if isinstance(v, (str, int, float)) and str(v) != ''}
    pos = spec['legend'].get('pos')
    spec['legend']['pos'] = (tuple(float(c) for c in pos) if isinstance(pos, (list, tuple)) and len(pos) == 2
                             and all(_num(c) is not None for c in pos) else None)
    spec['extra'] = [e for e in (spec.get('extra') or []) if isinstance(e, dict)]
    return spec


def _num(v):
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def figure_size(spec):
    f = spec['figure']
    k = UNITS.get(f.get('units', 'mm'), UNITS['mm'])
    w = max(0.5, float(f['width']) * k)
    h = max(0.5, float(f['height']) * k)
    return w, h


def palette_colors(name, n):
    n = max(1, n)
    if str(name).startswith('cmap:'):
        cmap = matplotlib.colormaps[name[5:]]
        return [mcolors.to_hex(cmap(v)) for v in (np.linspace(0.05, 0.9, n) if n > 1 else [0.3])]
    if name == 'style':
        cyc = matplotlib.rcParams['axes.prop_cycle'].by_key().get('color', ['#000000'])
        return [cyc[i % len(cyc)] for i in range(n)]
    base = catalog.PALETTES.get(name) or catalog.PALETTES['okabe-ito']
    return [base[i % len(base)] for i in range(n)]


def palette_previews(n=8):
    """Colours of the palettes that are not a fixed list, for the page's preview: each colour-map
    palette, and the 'style' palette for every style sheet that can be loaded."""
    out = {name: palette_colors(name, n) for name in catalog.PALETTES if name.startswith('cmap:')}
    styles = {}
    for key in catalog.STYLES:
        try:
            with warnings.catch_warnings():          # third-party style packages may warn on import
                warnings.simplefilter('ignore')
                with style_context({'style': {'base': key}}):
                    styles[key] = [mcolors.to_hex(c) for c in palette_colors('style', n)]
        except Exception:            # style sheet of a module that is not installed
            continue
    out['style'] = styles
    return out


def get_cmap(spec):
    name = spec['style'].get('cmap') or 'viridis'
    if name.startswith('cmc.'):
        import cmcrameri  # noqa: F401  (registers the cmc.* colormaps)
    cmap = matplotlib.colormaps[name]
    return cmap.reversed() if spec['style'].get('cmap_reverse') else cmap


# ------------------------------------------------------------------ data helpers
class Data:
    def __init__(self, df, spec):
        self.df, self.spec = df, spec
        for col in [spec['x'], spec['hue'], spec['z'], spec['xerr'], spec['yerr'], *spec['y'], *spec['y2']]:
            if col is not None and col not in df.columns:
                raise SpecError(f'Column not found: {col}')
        self.lang = LABELS.get(spec.get('lang'), LABELS['en'])
        self.label_prefix = ''      # file name, when several files share a figure
        self.key_prefix = ''        # series-style key prefix of that file

    def col(self, name, frame=None):
        frame = self.df if frame is None else frame
        if name is None:
            return pd.Series(np.arange(len(frame)), index=frame.index, name=self.lang['index'])
        return frame[name]

    def numeric(self, name, frame=None):
        s = self.col(name, frame)
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            return s
        conv = pd.to_numeric(s, errors='coerce')
        if conv.notna().sum() == 0 and s.notna().sum():
            raise SpecError(f'Column "{name}" is not numeric.')
        return conv

    def groups(self, frame=None):
        frame = self.df if frame is None else frame
        hue = self.spec['hue']
        if not hue:
            return [(None, frame)]
        return [(g, sub) for g, sub in frame.groupby(hue, sort=True, observed=True, dropna=True)]

    def xy(self, ycol, frame=None):
        frame = self.df if frame is None else frame
        x = self.numeric(self.spec['x'], frame) if self.spec['x'] else self.col(None, frame)
        y = self.numeric(ycol, frame)
        ok = x.notna() & y.notna()
        return x[ok].to_numpy(), y[ok].to_numpy(), ok

    def values(self, ycol, frame=None):
        v = self.numeric(ycol, frame)
        v = v.to_numpy(dtype=float) if not pd.api.types.is_datetime64_any_dtype(v) else v.dropna().to_numpy()
        return v[np.isfinite(v)] if v.dtype.kind == 'f' else v


class ColorLog:
    """The colour each series and each analysis layer really got, in drawing order, so the page can
    show them in its Series and Overlays panels (panel = figure, whatever the palette).

    Series beyond MAX_SERIES are not logged: the list travels in an HTTP header, and a panel with
    thousands of rows (e.g. colour by a numeric column) would be useless anyway.
    """

    MAX_SERIES = 200

    def __init__(self):
        self.series, self.overlays, self._keys = [], [], set()

    def add_series(self, key, label, color):
        key = str(key)
        if key not in self._keys and len(self.series) < self.MAX_SERIES:
            self._keys.add(key)
            self.series.append({'key': key, 'label': str(label), 'color': mcolors.to_hex(color)})

    def add_overlay(self, oid, label, color):
        key = f'overlay:{oid}'
        if key not in self._keys:
            self._keys.add(key)
            self.overlays.append({'key': key, 'overlay': str(oid), 'label': str(label),
                                  'color': mcolors.to_hex(color)})

    def entries(self):
        return self.series + self.overlays


class Series:
    """Style of one plotted series: palette colour + per-column overrides.

    log: a ColorLog that records the colour each series really got.
    """

    def __init__(self, spec, log=None, n=12):
        self.spec = spec
        self.count = 0
        # A colour-map palette is sampled once per series, end to end; the others keep their full cycle.
        palette = str(spec['style']['palette'])
        self.colors = palette_colors(palette, n if palette.startswith('cmap:') else 12)
        self.log = log

    def next(self, key, label):
        st = self.spec['style']
        over = self.spec['series'].get(str(key), {}) if key is not None else {}
        color = over.get('color') or self.colors[self.count % len(self.colors)]
        self.count += 1
        if self.log is not None and key is not None and not str(key).startswith('overlay:'):
            self.log.add_series(key, label, color)
        return {
            'color': color, 'label': over.get('label') or label,
            'linestyle': over.get('linestyle') or st['linestyle'],
            'marker': over.get('marker', st['marker']) or None,
            'linewidth': float(over.get('linewidth') or st['linewidth']),
            'markersize': float(over.get('markersize') or st['markersize']),
            'alpha': float(over.get('alpha') if over.get('alpha') not in (None, '') else st['alpha']),
        }


def _series_label(ycol, group, n_y):
    if group is None:
        return str(ycol)
    return f'{group}' if n_y == 1 else f'{ycol} · {group}'


# ------------------------------------------------------------------ plot kinds
def _label(d, base, single):
    """Series label; with several files the file name is shown (alone when the file has one series)."""
    if not d.label_prefix:
        return base
    return d.label_prefix if single else f'{d.label_prefix} · {base}'


def _xy_loop(ax, d, ser, ycols, draw):
    for ycol in ycols:
        for g, sub in d.groups():
            x, y, ok = d.xy(ycol, sub)
            if not len(x):
                continue
            key = d.key_prefix + (ycol if g is None else f'{ycol}::{g}')
            st = ser.next(key, _label(d, _series_label(ycol, g, len(ycols)), len(ycols) == 1 and g is None))
            draw(x, y, st, sub[ok])


def plot_line(ax, d, ser, ycols):
    _xy_loop(ax, d, ser, ycols, lambda x, y, st, sub: ax.plot(
        x, y, color=st['color'], ls=st['linestyle'], lw=st['linewidth'], marker=st['marker'],
        ms=st['markersize'], alpha=st['alpha'], label=st['label']))


def plot_step(ax, d, ser, ycols):
    _xy_loop(ax, d, ser, ycols, lambda x, y, st, sub: ax.step(
        x, y, where='mid', color=st['color'], ls=st['linestyle'], lw=st['linewidth'], alpha=st['alpha'],
        label=st['label']))


def plot_scatter(ax, d, ser, ycols):
    spec, out = d.spec, {}
    z = spec['z']

    def draw(x, y, st, sub):
        size = st['markersize'] ** 2
        if z:
            c = d.numeric(z, sub).to_numpy()
            out['mappable'] = ax.scatter(x, y, c=c, cmap=get_cmap(spec), s=size, marker=st['marker'] or 'o',
                                         alpha=st['alpha'], linewidths=0, label=st['label'],
                                         vmin=_num(spec['style']['vmin']), vmax=_num(spec['style']['vmax']))
        else:
            ax.scatter(x, y, color=st['color'], s=size, marker=st['marker'] or 'o', alpha=st['alpha'],
                       linewidths=0, label=st['label'])
    _xy_loop(ax, d, ser, ycols, draw)
    if out.get('mappable') is not None:
        return out['mappable'], z


def plot_area(ax, d, ser, ycols):
    st_all = d.spec['style']
    if st_all['stacked'] and len(ycols) > 1:
        frame = d.df.dropna(subset=ycols)
        x = d.numeric(d.spec['x'], frame).to_numpy() if d.spec['x'] else np.arange(len(frame))
        styles = [ser.next(y, str(y)) for y in ycols]
        ax.stackplot(x, *[d.numeric(y, frame).to_numpy() for y in ycols], labels=[s['label'] for s in styles],
                     colors=[s['color'] for s in styles], alpha=styles[0]['alpha'] * 0.85)
        return

    def draw(x, y, st, sub):
        ax.fill_between(x, y, alpha=0.3 * st['alpha'], color=st['color'], linewidth=0)
        ax.plot(x, y, color=st['color'], lw=st['linewidth'], alpha=st['alpha'], label=st['label'])
    _xy_loop(ax, d, ser, ycols, draw)


def plot_stem(ax, d, ser, ycols):
    def draw(x, y, st, sub):
        markerline, stemlines, baseline = ax.stem(x, y, label=st['label'])
        markerline.set(color=st['color'], markersize=st['markersize'], marker=st['marker'] or 'o')
        stemlines.set(color=st['color'], linewidth=st['linewidth'])
        baseline.set(color='0.4', linewidth=0.6)
    _xy_loop(ax, d, ser, ycols, draw)


def plot_errorbar(ax, d, ser, ycols):
    spec = d.spec
    band = spec['style']['error_style'] == 'band'

    def draw(x, y, st, sub):
        yerr = d.numeric(spec['yerr'], sub).to_numpy() if spec['yerr'] else None
        xerr = d.numeric(spec['xerr'], sub).to_numpy() if spec['xerr'] else None
        if band and yerr is not None:
            ax.fill_between(x, y - yerr, y + yerr, color=st['color'], alpha=0.25 * st['alpha'], linewidth=0)
            ax.plot(x, y, color=st['color'], lw=st['linewidth'], ls=st['linestyle'], marker=st['marker'],
                    ms=st['markersize'], label=st['label'], alpha=st['alpha'])
        else:
            ax.errorbar(x, y, yerr=yerr, xerr=xerr, color=st['color'], ls=st['linestyle'] if st['marker'] else 'none',
                        lw=st['linewidth'], marker=st['marker'] or 'o', ms=st['markersize'],
                        capsize=float(spec['style']['capsize']), elinewidth=max(0.5, st['linewidth'] * 0.7),
                        alpha=st['alpha'], label=st['label'])
    _xy_loop(ax, d, ser, ycols, draw)


def fit_curve(x, y, model, degree=2):
    """Least-squares fit. Returns (callable, equation text, R²)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if model == 'poly':
        deg = int(max(1, min(9, degree)))
        coef = np.polyfit(x, y, deg)
        f = np.poly1d(coef)
        terms = []
        for i, c in enumerate(coef):
            p = deg - i
            terms.append(f'{c:.4g}' + ('' if p == 0 else 'x' if p == 1 else f'x^{p}'))
        eq = 'y = ' + ' + '.join(terms).replace('+ -', '− ')
    elif model == 'exp':
        ok = y > 0
        b, a = np.polyfit(x[ok], np.log(y[ok]), 1)
        f = lambda t: np.exp(a) * np.exp(b * t)  # noqa: E731
        eq = f'y = {np.exp(a):.4g}·e^({b:.4g}x)'
        x, y = x[ok], y[ok]
    elif model == 'log':
        ok = x > 0
        a, b = np.polyfit(np.log(x[ok]), y[ok], 1)
        f = lambda t: a * np.log(t) + b  # noqa: E731
        eq = f'y = {a:.4g}·ln x + {b:.4g}'
        x, y = x[ok], y[ok]
    elif model == 'power':
        ok = (x > 0) & (y > 0)
        b, a = np.polyfit(np.log(x[ok]), np.log(y[ok]), 1)
        f = lambda t: np.exp(a) * t ** b  # noqa: E731
        eq = f'y = {np.exp(a):.4g}·x^{b:.4g}'
        x, y = x[ok], y[ok]
    else:
        m, q = np.polyfit(x, y, 1)
        f = lambda t: m * t + q  # noqa: E731
        eq = f'y = {m:.4g}x + {q:.4g}'.replace('+ -', '− ')
    resid = y - f(x)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - np.sum(resid ** 2) / ss_tot if ss_tot > 0 else float('nan')
    return f, eq, r2


def plot_regression(ax, d, ser, ycols):
    st_all = d.spec['style']

    def draw(x, y, st, sub):
        x = x.astype(float)
        ax.scatter(x, y, color=st['color'], s=st['markersize'] ** 2, marker=st['marker'] or 'o',
                   alpha=0.75 * st['alpha'], linewidths=0, label=st['label'])
        if len(x) < 3:
            return
        f, eq, r2 = fit_curve(x, y, st_all['fit'], st_all['fit_degree'])
        lo, hi = np.nanmin(x), np.nanmax(x)
        if st_all['fit'] in ('log', 'power'):
            lo = max(lo, np.nanmin(x[x > 0]) if np.any(x > 0) else lo)
        t = np.linspace(lo, hi, 300)
        ax.plot(t, f(t), color=st['color'], lw=st['linewidth'], ls='-',
                label=f'{eq}  (R² = {r2:.4f})')
    _xy_loop(ax, d, ser, ycols, draw)


def _aggregate(d, ycols):
    """Bar data: rows = categories of x (aggregated when repeated), columns = series."""
    spec, df = d.spec, d.df
    agg = spec['style']['agg'] or 'mean'
    x = spec['x']
    if not ycols:
        if not x:
            raise SpecError('Choose an X column (categories) or at least one Y column.')
        counts = df[x].value_counts(sort=False)
        try:
            counts = counts.sort_index()
        except TypeError:
            pass
        return counts.to_frame(d.lang['count']), None
    if spec['hue'] and len(ycols) == 1:
        if not x:
            raise SpecError('Grouped bars need an X column.')
        table = df.pivot_table(index=x, columns=spec['hue'], values=ycols[0], aggfunc=agg, observed=True)
        table.columns = [str(c) for c in table.columns]
        return table, None
    if x is None:
        frame = df[ycols].copy()
        frame.index = np.arange(1, len(frame) + 1)
        err = df[[spec['yerr']]].set_index(frame.index) if spec['yerr'] else None
        return frame, err
    if df[x].duplicated().any():
        grouped = df.groupby(x, sort=True, observed=True)[ycols]
        table = grouped.agg(agg)
        err = grouped.std() if agg == 'mean' and not spec['yerr'] else None
        return table, err
    frame = df.set_index(x)[ycols]
    err = df.set_index(x)[[spec['yerr']]] if spec['yerr'] else None
    return frame, err


def plot_bar(ax, d, ser, ycols, horizontal=False):
    table, err = _aggregate(d, ycols)
    cats = [str(c) if not isinstance(c, float) else f'{c:g}' for c in table.index]
    pos = np.arange(len(cats))
    k = table.shape[1]
    stacked = d.spec['style']['stacked'] and k > 1
    width = float(d.spec['style']['bar_width'])
    w = width if stacked else width / k
    base = np.zeros(len(cats))
    for j, col in enumerate(table.columns):
        st = ser.next(col, str(col))
        vals = pd.to_numeric(table[col], errors='coerce').to_numpy(dtype=float)
        offs = pos if stacked else pos - width / 2 + w * (j + 0.5)
        e = None
        if err is not None:
            ecol = col if col in err.columns else err.columns[0]
            e = pd.to_numeric(err[ecol], errors='coerce').to_numpy(dtype=float)
        kw = dict(color=st['color'], alpha=st['alpha'], label=st['label'], edgecolor='black',
                  linewidth=max(0.0, d.spec['axes']['linewidth'] * 0.6),
                  error_kw={'elinewidth': 0.8, 'capsize': float(d.spec['style']['capsize'])})
        if horizontal:
            ax.barh(offs, vals, height=w, left=base if stacked else None, xerr=e, **kw)
        else:
            ax.bar(offs, vals, width=w, bottom=base if stacked else None, yerr=e, **kw)
        if stacked:
            base = base + np.nan_to_num(vals)
    if horizontal:
        ax.set_yticks(pos, cats)
    else:
        ax.set_xticks(pos, cats)
    return None


def _dist_groups(d, ycols):
    """[(label, key, values)] for distribution plots: one per y column, or per hue/x group of one y."""
    out = []
    group_col = d.spec['hue'] or (d.spec['x'] if d.spec['kind'] in ('box', 'violin', 'strip', 'swarm') else None)
    if group_col and len(ycols) == 1:
        for g, sub in d.df.groupby(group_col, sort=True, observed=True):
            out.append((_label(d, str(g), False), d.key_prefix + f'{ycols[0]}::{g}', d.values(ycols[0], sub)))
        return out
    if not ycols and d.spec['x']:
        ycols = [d.spec['x']]
    for y in ycols:
        out.append((_label(d, str(y), len(ycols) == 1), d.key_prefix + y, d.values(y)))
    if not out:
        raise SpecError('Choose at least one Y column.')
    return out


def plot_hist(ax, d, ser, ycols):
    st_all = d.spec['style']
    groups = _dist_groups(d, ycols)
    stacked = st_all['stacked'] and len(groups) > 1
    data = [v for _, _, v in groups]
    styles = [ser.next(k, lab) for lab, k, _ in groups]
    bins = int(st_all['bins']) if str(st_all['bins']).isdigit() else st_all['bins']
    allv = np.concatenate([np.asarray(v, dtype=float) for v in data]) if data else np.array([])
    if allv.size and isinstance(bins, int):
        bins = np.histogram_bin_edges(allv[np.isfinite(allv)], bins=bins)
    if stacked:
        ax.hist(data, bins=bins, density=st_all['density'], stacked=True, histtype='stepfilled',
                color=[s['color'] for s in styles], label=[s['label'] for s in styles], alpha=styles[0]['alpha'],
                edgecolor='black', linewidth=0.4)
    else:
        many = len(groups) > 1
        for v, st in zip(data, styles):
            ax.hist(v, bins=bins, density=st_all['density'], histtype='stepfilled', color=st['color'],
                    alpha=min(st['alpha'], 0.55) if many else st['alpha'], label=st['label'],
                    edgecolor=st['color'] if many else 'black', linewidth=0.6 if many else 0.4)
    return d.lang['density'] if st_all['density'] else d.lang['count']


def kde_curve(v, n=1024):
    """Gaussian KDE on a grid (Silverman bandwidth, binned for speed)."""
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 2:
        raise SpecError('A density curve needs at least two values.')
    sd = v.std(ddof=1)
    iqr = np.subtract(*np.percentile(v, [75, 25]))
    s = min(sd, iqr / 1.34) if iqr > 0 else sd
    bw = 0.9 * s * v.size ** -0.2 if s > 0 else max(abs(v.mean()) * 1e-3, 1e-9)
    lo, hi = v.min() - 3 * bw, v.max() + 3 * bw
    edges = np.linspace(lo, hi, n + 1)
    counts, _ = np.histogram(v, edges)
    centers = 0.5 * (edges[1:] + edges[:-1])
    dx = edges[1] - edges[0]
    m = int(min(n, np.ceil(4 * bw / dx)))
    t = np.arange(-m, m + 1) * dx
    kernel = np.exp(-0.5 * (t / bw) ** 2)
    dens = np.convolve(counts, kernel, mode='same')
    dens /= dens.sum() * dx
    return centers, dens


def plot_kde(ax, d, ser, ycols):
    for label, key, v in _dist_groups(d, ycols):
        st = ser.next(key, label)
        x, y = kde_curve(v)
        if d.spec['style']['fill']:
            ax.fill_between(x, y, color=st['color'], alpha=0.25 * st['alpha'], linewidth=0)
        ax.plot(x, y, color=st['color'], lw=st['linewidth'], ls=st['linestyle'], alpha=st['alpha'], label=st['label'])
    return d.lang['density']


def plot_ecdf(ax, d, ser, ycols):
    for label, key, v in _dist_groups(d, ycols):
        st = ser.next(key, label)
        v = np.sort(np.asarray(v, dtype=float))
        ax.step(v, np.arange(1, v.size + 1) / v.size, where='post', color=st['color'], lw=st['linewidth'],
                ls=st['linestyle'], alpha=st['alpha'], label=st['label'])
    return d.lang['probability']


def _set_category_ticks(ax, labels, positions):
    ax.set_xticks(positions, labels)
    ax.minorticks_off()


def plot_box(ax, d, ser, ycols):
    groups = _dist_groups(d, ycols)
    data = [np.asarray(v, dtype=float) for _, _, v in groups]
    styles = [ser.next(k, lab) for lab, k, _ in groups]
    kw = dict(patch_artist=True, widths=0.6, showfliers=bool(d.spec['style']['show_fliers']),
              medianprops={'color': 'black', 'linewidth': 1.0},
              flierprops={'marker': 'o', 'markersize': 2.5, 'markerfacecolor': 'none', 'markeredgewidth': 0.6})
    bp = ax.boxplot(data, **kw)
    for patch, st in zip(bp['boxes'], styles):
        patch.set(facecolor=mcolors.to_rgba(st['color'], 0.55 * st['alpha']), edgecolor='black', linewidth=0.7)
    _set_category_ticks(ax, [lab for lab, _, _ in groups], np.arange(1, len(groups) + 1))
    return 'nolegend'


def plot_violin(ax, d, ser, ycols):
    groups = _dist_groups(d, ycols)
    data = [np.asarray(v, dtype=float) for _, _, v in groups]
    styles = [ser.next(k, lab) for lab, k, _ in groups]
    parts = ax.violinplot(data, showmedians=True, showextrema=True, widths=0.75)
    for body, st in zip(parts['bodies'], styles):
        body.set(facecolor=st['color'], edgecolor='black', alpha=0.6 * st['alpha'], linewidth=0.6)
    for key in ('cmedians', 'cmins', 'cmaxes', 'cbars'):
        if key in parts:
            parts[key].set(color='black', linewidth=0.8)
    _set_category_ticks(ax, [lab for lab, _, _ in groups], np.arange(1, len(groups) + 1))
    return 'nolegend'


def plot_strip(ax, d, ser, ycols, swarm=False):
    import seaborn as sns
    groups = _dist_groups(d, ycols)
    long = pd.DataFrame({'g': np.concatenate([[lab] * len(v) for lab, _, v in groups]),
                         'v': np.concatenate([np.asarray(v, dtype=float) for _, _, v in groups])})
    styles = [ser.next(k, lab) for lab, k, _ in groups]
    fn = sns.swarmplot if swarm else sns.stripplot
    kw = {} if swarm else {'jitter': 0.25}
    fn(data=long, x='g', y='v', hue='g', ax=ax, palette=[s['color'] for s in styles], legend=False,
       size=d.spec['style']['markersize'], alpha=styles[0]['alpha'], **kw)
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.minorticks_off()
    return 'nolegend'


def plot_pie(ax, d, ser, ycols):
    table, _ = _aggregate(d, ycols[:1])
    vals = pd.to_numeric(table.iloc[:, 0], errors='coerce').fillna(0).to_numpy()
    if np.any(vals < 0):
        raise SpecError('A pie chart needs non-negative values.')
    labels = [str(c) for c in table.index]
    styles = [ser.next(f'{table.columns[0]}::{c}', c) for c in labels]
    _, names, shares = ax.pie(vals, labels=labels, colors=[s['color'] for s in styles], autopct='%1.1f%%', startangle=90,
                              counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 0.8},
                              textprops={'fontsize': d.spec['text']['tick_size']})
    for label, name, share in zip(labels, names, shares):      # each slice's name and share can be dragged
        _move_text(ax.figure, name, f'pie.name:{label}', d.spec)
        _move_text(ax.figure, share, f'pie.share:{label}', d.spec)
    ax.set_aspect('equal')
    return 'nolegend'


def _grid_from_xyz(d):
    spec = d.spec
    if not (spec['x'] and spec['y'] and spec['z']):
        return None
    frame = d.df[[spec['x'], spec['y'][0], spec['z']]].dropna()
    return frame.pivot_table(index=spec['y'][0], columns=spec['x'], values=spec['z'], aggfunc=spec['style']['agg'] or 'mean')


def _annotate(ax, mat, fmt='{:.2g}'):
    finite = mat[np.isfinite(mat)]
    if not finite.size:
        return
    mid = (finite.min() + finite.max()) / 2
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            if np.isfinite(mat[i, j]):
                im_color = 'white' if mat[i, j] < mid else 'black'
                ax.text(j, i, fmt.format(mat[i, j]), ha='center', va='center', fontsize='x-small', color=im_color)


def plot_heatmap(ax, d, ser, ycols):
    spec = d.spec
    vmin, vmax = _num(spec['style']['vmin']), _num(spec['style']['vmax'])
    grid = _grid_from_xyz(d)
    if grid is not None:
        mat = grid.to_numpy(dtype=float)
        xs, ys = grid.columns, grid.index
        numeric_axes = pd.api.types.is_numeric_dtype(xs) and pd.api.types.is_numeric_dtype(ys)
        if numeric_axes:
            m = ax.pcolormesh(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), mat, cmap=get_cmap(spec),
                              shading='nearest', vmin=vmin, vmax=vmax)
            return m, spec['z']
        m = ax.imshow(mat, aspect='auto', cmap=get_cmap(spec), vmin=vmin, vmax=vmax, origin='lower',
                      interpolation=_matrix_interp(mat))
        _label_matrix_axes(ax, [str(c) for c in xs], [str(r) for r in ys])
        if spec['style']['annotate'] and mat.size <= 600:
            _annotate(ax, mat)
        return m, spec['z']
    cols = ycols or [c for c in d.df.columns if pd.api.types.is_numeric_dtype(d.df[c])]
    mat = _float_matrix(d.df[cols])
    m = ax.imshow(mat, aspect='auto', cmap=get_cmap(spec), vmin=vmin, vmax=vmax, interpolation=_matrix_interp(mat))
    rows = d.col(spec['x']).astype(str).tolist() if spec['x'] else None
    _label_matrix_axes(ax, cols, rows)
    if spec['style']['annotate'] and mat.size <= 600:
        _annotate(ax, mat)
    return m, d.lang['value']


def _float_matrix(frame):
    """Columns as a float matrix; text that is not a number becomes NaN."""
    if not all(isinstance(t, np.dtype) and t.kind in 'iuf' for t in frame.dtypes):
        frame = frame.apply(pd.to_numeric, errors='coerce')
    return frame.to_numpy(dtype=float)


def _matrix_interp(mat):
    """Nearest-neighbour cells, unless the matrix has more rows or columns than the figure has pixels."""
    return 'antialiased' if max(mat.shape) > SMOOTH_MATRIX else 'nearest'


def corr_columns(df, ycols):
    """Columns of a correlation matrix: the chosen ones, or else every numeric column."""
    cols = ycols if len(ycols) >= 2 else [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(cols) < 2:
        raise SpecError('A correlation matrix needs at least two numeric columns.')
    if len(cols) > MAX_CORR_COLUMNS:
        raise SpecError(f'A correlation matrix of {len(cols):,} columns has more cells than the figure has '
                        f'pixels: choose at most {MAX_CORR_COLUMNS:,} columns (a block), or draw a heat map.',
                        'corr_too_many', n=len(cols), max=MAX_CORR_COLUMNS)
    return cols


def corr_matrix(frame):
    """Pearson r between the columns, like pandas (pairs of rows where both values are present);
    with nothing missing, NumPy's BLAS version, much faster on thousands of columns."""
    mat = _float_matrix(frame)
    if np.isnan(mat).any():
        return pd.DataFrame(mat).corr().to_numpy()
    with np.errstate(divide='ignore', invalid='ignore'), warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)              # constant columns: r is NaN
        return np.atleast_2d(np.corrcoef(mat, rowvar=False))


def _label_matrix_axes(ax, xlabels, ylabels):
    """Row and column names as tick labels: all of them for a small matrix, else as many as fit."""
    from matplotlib.font_manager import FontProperties
    box = ax.get_position()
    width, height = ax.figure.get_size_inches() * 72 * (box.width, box.height)       # points

    def thin(labels, room, each):
        most = len(labels) if len(labels) <= 15 else max(2, min(25, int(room / each)))
        step = max(1, int(np.ceil(len(labels) / most)))
        return np.arange(0, len(labels), step), [labels[i] for i in range(0, len(labels), step)]
    if xlabels is not None:
        size = FontProperties(size=matplotlib.rcParams['xtick.labelsize']).get_size_in_points()
        slanted = max((len(s) for s in xlabels), default=0) > 3
        p, l = thin(xlabels, width, size * (1.8 if slanted else 0.7 * max((len(s) for s in xlabels), default=1) + 1))
        ax.set_xticks(p, l, rotation=45 if slanted else 0, ha='right' if slanted else 'center')
    if ylabels is not None:
        size = FontProperties(size=matplotlib.rcParams['ytick.labelsize']).get_size_in_points()
        p, l = thin(ylabels, height, size * 1.5)
        ax.set_yticks(p, l)
    ax.minorticks_off()


def plot_corr(ax, d, ser, ycols):
    cols = corr_columns(d.df, ycols)
    c = corr_matrix(d.df[cols])
    cmap = matplotlib.colormaps['RdBu_r' if not d.spec['style']['cmap_reverse'] else 'RdBu']
    m = ax.imshow(c, cmap=cmap, vmin=-1, vmax=1, interpolation=_matrix_interp(c))
    _label_matrix_axes(ax, cols, cols)
    if len(cols) <= 15:
        for i in range(len(cols)):
            for j in range(len(cols)):
                ax.text(j, i, f'{c[i, j]:.2f}', ha='center', va='center', fontsize='x-small',
                        color='white' if abs(c[i, j]) > 0.6 else 'black')
    return m, d.lang['correlation']


def plot_contour(ax, d, ser, ycols):
    spec = d.spec
    if not (spec['x'] and ycols and spec['z']):
        raise SpecError('A contour plot needs X, Y and Z columns.')
    levels = int(spec['style']['levels'])
    cmap = get_cmap(spec)
    vmin, vmax = _num(spec['style']['vmin']), _num(spec['style']['vmax'])
    grid = _grid_from_xyz(d)
    if grid is not None and grid.notna().all().all() and grid.size >= 4 and grid.shape[0] > 1 and grid.shape[1] > 1:
        X, Y = np.meshgrid(np.asarray(grid.columns, dtype=float), np.asarray(grid.index, dtype=float))
        Z = grid.to_numpy(dtype=float)
        m = ax.contourf(X, Y, Z, levels=levels, cmap=cmap, vmin=vmin, vmax=vmax)
        if spec['style']['contour_lines']:
            ax.contour(X, Y, Z, levels=levels, colors='black', linewidths=0.4, alpha=0.6)
    else:
        frame = d.df[[spec['x'], ycols[0], spec['z']]].apply(pd.to_numeric, errors='coerce').dropna()
        if len(frame) < 4:
            raise SpecError('Not enough points for a contour plot.')
        x, y, z = (frame.iloc[:, i].to_numpy() for i in range(3))
        m = ax.tricontourf(x, y, z, levels=levels, cmap=cmap, vmin=vmin, vmax=vmax)
        if spec['style']['contour_lines']:
            ax.tricontour(x, y, z, levels=levels, colors='black', linewidths=0.4, alpha=0.6)
    return m, spec['z']


def plot_hexbin(ax, d, ser, ycols):
    if not ycols:
        raise SpecError('Choose a Y column.')
    x, y, _ = d.xy(ycols[0])
    m = ax.hexbin(x.astype(float), y.astype(float), gridsize=int(d.spec['style']['gridsize']),
                  cmap=get_cmap(d.spec), mincnt=1, linewidths=0.1)
    return m, d.lang['count']


def plot_hist2d(ax, d, ser, ycols):
    if not ycols:
        raise SpecError('Choose a Y column.')
    x, y, _ = d.xy(ycols[0])
    *_, m = ax.hist2d(x.astype(float), y.astype(float), bins=int(d.spec['style']['bins']), cmap=get_cmap(d.spec),
                      cmin=1, density=bool(d.spec['style']['density']))
    return m, d.lang['density'] if d.spec['style']['density'] else d.lang['count']


def plot_polar(ax, d, ser, ycols):
    deg = d.spec['style']['polar_degrees']
    _xy_loop(ax, d, ser, ycols, lambda x, y, st, sub: ax.plot(
        np.deg2rad(x.astype(float)) if deg else x, y, color=st['color'], lw=st['linewidth'], ls=st['linestyle'],
        marker=st['marker'], ms=st['markersize'], alpha=st['alpha'], label=st['label']))


# ------------------------------------------------------------------ 3D
def plot_surface3d(ax, d, ser, ycols):
    """Surface z(x, y): from X, Y, Z columns forming a grid (as for contour), else triangulated."""
    spec = d.spec
    if not (spec['x'] and ycols and spec['z']):
        raise SpecError('A 3D surface needs X, Y and Z columns.')
    cmap = get_cmap(spec)
    vmin, vmax = _num(spec['style']['vmin']), _num(spec['style']['vmax'])
    grid = _grid_from_xyz(d)
    color = ser.next('surface', spec['z'])['color']
    if grid is not None and grid.shape[0] > 1 and grid.shape[1] > 1 and grid.notna().all().all():
        X, Y = np.meshgrid(np.asarray(grid.columns, dtype=float), np.asarray(grid.index, dtype=float))
        Z = grid.to_numpy(dtype=float)
        if spec['style']['wireframe']:
            w = ax.plot_wireframe(X, Y, Z, axlim_clip=True, color=color, linewidth=float(spec['style']['linewidth']) * 0.5)
            w._pp_mesh = ('wire', X, Y, Z)                   # for the rotatable preview (view3d)
            return 'nolegend'
        m = ax.plot_surface(X, Y, Z, axlim_clip=True, cmap=cmap, vmin=vmin, vmax=vmax, linewidth=0, antialiased=True,
                            rcount=min(Z.shape[0], 200), ccount=min(Z.shape[1], 200))
        m._pp_mesh = ('grid', X, Y, Z)
    else:
        frame = d.df[[spec['x'], ycols[0], spec['z']]].apply(pd.to_numeric, errors='coerce').dropna()
        if len(frame) < 4:
            raise SpecError('Not enough points for a 3D surface.')
        x, y, z = (frame.iloc[:, i].to_numpy() for i in range(3))
        if spec['style']['wireframe']:
            w = ax.plot_trisurf(x, y, z, axlim_clip=True, color='none', edgecolor=color, linewidth=float(spec['style']['linewidth']) * 0.4)
            w._pp_mesh = ('triwire', x, y, z)
            return 'nolegend'
        m = ax.plot_trisurf(x, y, z, axlim_clip=True, cmap=cmap, vmin=vmin, vmax=vmax, linewidth=0, antialiased=True)
        m._pp_mesh = ('tri', x, y, z)
    return m, spec['z']


def plot_scatter3d(ax, d, ser, ycols):
    """Points (x, y, z), one colour per Y column and group; 'connect' joins them in order (a 3D line)."""
    spec = d.spec
    z = spec['z']
    if not (spec['x'] and ycols and z):
        raise SpecError('A 3D scatter needs X, Y and Z columns.')
    connect = bool(spec['style']['connect'])

    def draw(x, y, st, sub):
        zz = d.numeric(z, sub).to_numpy(dtype=float)
        if connect:
            ax.plot(x, y, zz, axlim_clip=True, color=st['color'], ls=st['linestyle'], lw=st['linewidth'], marker=st['marker'] or None,
                    ms=st['markersize'], alpha=st['alpha'], label=st['label'])
        else:
            ax.scatter(x, y, zz, axlim_clip=True, color=st['color'], s=st['markersize'] ** 2, marker=st['marker'] or 'o',
                       alpha=st['alpha'], linewidths=0, label=st['label'], depthshade=True)
    _xy_loop(ax, d, ser, ycols, draw)


def plot_waterfall(ax, d, ser, ycols):
    """Each Y column (e.g. a spectrum at one time) as a curve at its own depth: the column's value when
    every name is a number (times, temperatures…), else its position."""
    if not ycols:
        raise SpecError('Choose the Y columns (one curve each).')
    try:
        depth = [float(str(c).replace(',', '.')) for c in ycols]
        numeric = True
    except ValueError:
        depth, numeric = list(range(len(ycols))), False
    for pos, ycol in zip(depth, ycols):
        x, y, _ = d.xy(ycol)
        if not len(x):
            continue
        st = ser.next(d.key_prefix + ycol, _label(d, ycol, False))
        ax.plot(x.astype(float), np.full(len(x), pos, dtype=float), y.astype(float), axlim_clip=True, color=st['color'],
                ls=st['linestyle'], lw=st['linewidth'], alpha=st['alpha'], label=st['label'])
    if not numeric:
        step = max(1, int(np.ceil(len(ycols) / 8)))
        ax.set_yticks(depth[::step], [str(c) for c in ycols[::step]])


def _style_axes3d(ax, spec, kind):
    """3D axes: view angle, grid, tick direction, limits on the three axes."""
    st, a = spec['style'], spec['axes']
    ax.view_init(elev=float(_num(st['elev']) if _num(st['elev']) is not None else 25),
                 azim=float(_num(st['azim']) if _num(st['azim']) is not None else -60))
    ax.grid(a['grid'] != 'none')
    ax.tick_params(which='both', direction=a['tick_direction'], pad=1)
    for get, setter in (('x', ax.set_xlim), ('y', ax.set_ylim), ('z', ax.set_zlim)):
        lo, hi = _num(a.get(f'{get}min')), _num(a.get(f'{get}max'))
        if lo is not None or hi is not None:
            setter(lo, hi)
    if a['invert_x']:
        ax.invert_xaxis()
    if a['invert_y']:
        ax.invert_yaxis()
    ax.set_box_aspect(None, zoom=0.88)                    # room for the tick labels inside the figure


PLOTTERS = {
    'line': plot_line, 'scatter': plot_scatter, 'step': plot_step, 'area': plot_area, 'stem': plot_stem,
    'errorbar': plot_errorbar, 'regression': plot_regression, 'polar': plot_polar,
    'bar': plot_bar, 'barh': lambda ax, d, s, y: plot_bar(ax, d, s, y, horizontal=True),
    'box': plot_box, 'violin': plot_violin, 'strip': plot_strip,
    'swarm': lambda ax, d, s, y: plot_strip(ax, d, s, y, swarm=True), 'pie': plot_pie,
    'hist': plot_hist, 'kde': plot_kde, 'ecdf': plot_ecdf,
    'heatmap': plot_heatmap, 'contour': plot_contour, 'hexbin': plot_hexbin, 'hist2d': plot_hist2d,
    'corr': plot_corr,
    'surface3d': plot_surface3d, 'scatter3d': plot_scatter3d, 'waterfall': plot_waterfall,
}


# ------------------------------------------------------------------ figure assembly
def _rc(spec):
    t, a = spec['text'], spec['axes']
    rc = {
        'font.size': float(t['size']), 'axes.titlesize': float(t['title_size']),
        'axes.labelsize': float(t['label_size']), 'xtick.labelsize': float(t['tick_size']),
        'ytick.labelsize': float(t['tick_size']), 'legend.fontsize': float(t['legend_size']),
        'mathtext.fontset': t['mathtext'] or 'dejavusans', 'mathtext.default': 'regular',
        'axes.linewidth': float(a['linewidth']), 'xtick.major.width': float(a['linewidth']),
        'ytick.major.width': float(a['linewidth']), 'xtick.minor.width': float(a['linewidth']) * 0.75,
        'ytick.minor.width': float(a['linewidth']) * 0.75,
        'xtick.major.size': 3.5, 'ytick.major.size': 3.5, 'xtick.minor.size': 2, 'ytick.minor.size': 2,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',   # editable text in Illustrator/Inkscape
        'axes.unicode_minus': True, 'text.usetex': False,
        'figure.constrained_layout.h_pad': 0.03, 'figure.constrained_layout.w_pad': 0.03,
    }
    if t.get('font'):
        rc['font.family'] = 'sans-serif'
        fam = [t['font'], 'DejaVu Sans']
        serif = any(k in t['font'].lower() for k in ('times', 'serif', 'georgia', 'garamond', 'palatino', 'cambria',
                                                      'computer modern', 'cmu', 'stix'))
        if serif and 'sans' not in t['font'].lower():
            rc['font.family'] = 'serif'
            rc['font.serif'] = [t['font'], 'DejaVu Serif']
        else:
            rc['font.sans-serif'] = fam
    return rc


def style_context(spec):
    info = catalog.STYLES.get(spec['style']['base'], catalog.STYLES['publication'])
    if 'scienceplots' in info['requires']:
        import scienceplots  # noqa: F401  (registers the styles)
    return mstyle.context(info['base'])


def _style_axes(ax, spec, kind, twin=None, category_x=False, category_y=False):
    a = spec['axes']
    if kind in ('pie',):
        return
    direction = a['tick_direction']
    mirror = a['mirror_ticks'] and a['spines'] == 'box'
    ax.tick_params(which='both', direction=direction, top=mirror and kind != 'polar',
                   right=mirror and twin is None and kind != 'polar')
    if a['minor_ticks'] and kind not in ('heatmap', 'corr', 'polar', 'pie'):
        ax.minorticks_on()
        if category_x:
            ax.xaxis.set_minor_locator(ticker.NullLocator())
        if category_y:
            ax.yaxis.set_minor_locator(ticker.NullLocator())
    elif not a['minor_ticks']:
        ax.minorticks_off()
    if kind != 'polar':
        if a['spines'] == 'open':
            ax.spines['top'].set_visible(False)
            if twin is None:
                ax.spines['right'].set_visible(False)
        elif a['spines'] == 'none':
            for s in ax.spines.values():
                s.set_visible(False)
    grid = a['grid']
    if grid in ('major', 'both'):
        ax.grid(True, which='major', linewidth=0.5, alpha=0.5)
        if grid == 'both':
            ax.grid(True, which='minor', linewidth=0.3, alpha=0.25)
    elif grid == 'none':
        ax.grid(False, which='both')


def _apply_limits(ax, spec, xlike, kind):
    a = spec['axes']
    if kind not in ('pie', 'corr', 'polar'):
        for axis, scale in (('x', a['xscale']), ('y', a['yscale'])):
            if scale and scale != 'linear':
                (ax.set_xscale if axis == 'x' else ax.set_yscale)(scale)
    xmin, xmax = a['xmin'], a['xmax']
    if xlike is not None and pd.api.types.is_datetime64_any_dtype(xlike):
        conv = lambda v: pd.Timestamp(v) if v not in (None, '') else None  # noqa: E731
    else:
        conv = _num
    # min and max are the lower and the upper value: an axis the plot itself draws reversed (an image's
    # rows from the top) stays reversed.
    try:
        lo, hi = conv(xmin), conv(xmax)
        if lo is not None or hi is not None:
            flipped = ax.xaxis_inverted()
            ax.set_xlim(left=lo, right=hi)
            if flipped != ax.xaxis_inverted():
                ax.invert_xaxis()
    except (ValueError, TypeError):
        pass
    lo, hi = _num(a['ymin']), _num(a['ymax'])
    if lo is not None or hi is not None:
        flipped = ax.yaxis_inverted()
        ax.set_ylim(bottom=lo, top=hi)
        if flipped != ax.yaxis_inverted():
            ax.invert_yaxis()
    elif (xmin not in (None, '') or xmax not in (None, '')) and kind in Y_FIT_KINDS:
        _fit_y_to_view(ax)
    if a['invert_x']:
        ax.invert_xaxis()
    if a['invert_y']:
        ax.invert_yaxis()
    if a['aspect'] == 'equal' and kind != 'pie':
        ax.set_aspect('equal', adjustable='datalim')
    if a['sci'] and kind not in ('pie', 'heatmap', 'corr'):
        for axis, scale in (('x', a['xscale']), ('y', a['yscale'])):
            if scale == 'linear':
                try:
                    ax.ticklabel_format(axis=axis, style='sci', scilimits=(-3, 3), useMathText=True)
                except AttributeError:
                    pass
    if a['xrotation']:
        for lab in ax.get_xticklabels():
            lab.set_rotation(float(a['xrotation']))
            lab.set_ha('right' if 0 < float(a['xrotation']) < 90 else 'center')


Y_FIT_KINDS = {'line', 'scatter', 'step', 'errorbar', 'stem', 'regression', 'area'}


def _fit_y_to_view(ax):
    """With only the x range fixed (e.g. zoomed on one band of a spectrum), the y axis spans the data in that
    range rather than all of it, with Matplotlib's usual margin."""
    x0, x1 = sorted(ax.get_xlim())
    lo, hi = np.inf, -np.inf
    for line in ax.get_lines():
        xy = np.asarray(line.get_xydata(), dtype=float)
        if not line.get_visible() or not xy.size:
            continue
        y = xy[(xy[:, 0] >= x0) & (xy[:, 0] <= x1), 1]
        y = y[np.isfinite(y)]
        if ax.get_yscale() == 'log':
            y = y[y > 0]
        if y.size:
            lo, hi = min(lo, y.min()), max(hi, y.max())
    from matplotlib.collections import PathCollection
    for col in ax.collections:                    # scatter points
        offs = np.asarray(col.get_offsets(), dtype=float)
        if isinstance(col, PathCollection) and col.get_visible() and offs.ndim == 2 and offs.shape[1] == 2 and len(offs):
            y = offs[(offs[:, 0] >= x0) & (offs[:, 0] <= x1), 1]
            y = y[np.isfinite(y)]
            if y.size:
                lo, hi = min(lo, y.min()), max(hi, y.max())
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return
    m = matplotlib.rcParams['axes.ymargin']
    if ax.get_yscale() == 'log':
        llo, lhi = np.log10(lo), np.log10(hi)
        span = (lhi - llo) or 1.0
        ax.set_ylim(10 ** (llo - m * span), 10 ** (lhi + m * span))
    else:
        span = (hi - lo) or (abs(hi) or 1.0)
        ax.set_ylim(lo - m * span, hi + m * span)


def _tag_legend(leg):
    leg._pp_id, leg._pp_field = 'legend', 'legend.title'


def _legend_fits(fig, ax, spec, n):
    """Whether a legend of n entries fits in the height it has (the axes, or the figure when outside): an
    automatic legend that does not fit is left out, as it would cover the plot or squeeze the axes."""
    lg = spec['legend']
    rows = math.ceil(n / max(1, int(lg['ncol'] or 1)))
    height = fig.get_size_inches()[1] * 72 * (1 if lg['loc'].startswith('outside') else ax.get_position().height)
    return rows * float(spec['text']['legend_size']) * 1.75 <= 0.9 * height


def _legend(fig, ax, spec, handles, labels, kind):
    lg = spec['legend']
    show = lg['show']
    if show == 'hide' or not handles or (show == 'auto' and len(handles) < 2 and kind != 'regression'):
        return
    if show == 'auto' and not _legend_fits(fig, ax, spec, len(handles)):
        return
    kw = dict(frameon=bool(lg['frame']), ncol=max(1, int(lg['ncol'] or 1)), title=lg['title'] or None,
              fontsize=float(spec['text']['legend_size']), title_fontsize=float(spec['text']['legend_size']))
    if lg['frame']:
        kw.update(fancybox=False, edgecolor='black', framealpha=1)
    loc = lg['loc']
    if lg.get('pos'):                      # dragged on the figure: its top left corner, in fractions of the axes
        leg = ax.legend(handles, labels, loc='upper left', bbox_to_anchor=lg['pos'], borderaxespad=0, **kw)
        _tag_legend(leg)
    elif loc.startswith('outside'):
        where = {'outside right': 'outside right upper', 'outside top': 'outside upper center',
                 'outside bottom': 'outside lower center'}.get(loc, 'outside right upper')
        if where != 'outside right upper' and lg['ncol'] in (1, '1', None):
            kw['ncol'] = min(len(handles), 4)
        _tag_legend(fig.legend(handles, labels, loc=where, **kw))
    else:
        _tag_legend(ax.legend(handles, labels, loc=loc, **kw))


OVERLAY_KINDS = {'line', 'scatter', 'step', 'area', 'errorbar', 'regression', 'stem', 'hist', 'kde', 'ecdf',
                 'hexbin', 'hist2d', 'contour', 'heatmap'}


def _draw_overlays(ax, spec, ser, df, overlay_data):
    """Analysis results drawn over the figure: a curve (or markers) and an optional error band.

    Each overlay is {'id', 'x', 'y', 'lo', 'hi', 'label', 'band_label', 'band', 'text', 'style': {...}}; its data comes
    from overlay_data[id] (a DataFrame) or, when it has no data of its own, from the plotted DataFrame.
    """
    for o in spec.get('overlays') or []:
        if not isinstance(o, dict) or o.get('hidden'):
            continue
        frame = (overlay_data or {}).get(o.get('id'))
        if frame is None:
            if o.get('dataset_id'):
                continue                        # its data is not available: skip rather than fail
            frame = df
        cols = [o.get('x'), o.get('y'), o.get('lo'), o.get('hi')]
        if not o.get('x') or not o.get('y') or any(c and c not in frame.columns for c in cols):
            continue
        st = o.get('style') or {}
        label = o.get('label') or o['y']
        color = st.get('color') or ser.next(f'overlay:{o.get("id")}', label)['color']
        shown = st.get('legend', True) is not False          # style legend=False: drawn, but not in the legend
        if color == 'text':                      # the colour of the figure's text (readable on any style)
            color = matplotlib.rcParams['text.color']
        if ser.log is not None and o.get('id') is not None:
            ser.log.add_overlay(o.get('id'), label, color)
        sub = frame[[c for c in dict.fromkeys(cols) if c]].apply(pd.to_numeric, errors='coerce')
        sub = sub.dropna(subset=[o['x'], o['y']]).sort_values(o['x'], kind='stable')
        text = o.get('text') if o.get('text') in frame.columns else None
        x = sub[o['x']].to_numpy(float)
        if o.get('lo') and o.get('hi') and o.get('band', True):
            band = sub[[o['lo'], o['hi']]].notna().all(axis=1).to_numpy()
            ax.fill_between(x[band], sub[o['lo']].to_numpy(float)[band], sub[o['hi']].to_numpy(float)[band],
                            color=color, alpha=float(st.get('band_alpha', 0.22)), linewidth=0,
                            label=f'{label} ({o.get("band_label") or "95% CI"})' if shown else '_nolegend_', zorder=1.5)
        ls = st.get('linestyle', '-')
        marker = st.get('marker') or None
        ax.plot(x, sub[o['y']].to_numpy(float), color=color, ls='none' if ls in ('', 'none') else ls,
                lw=float(st.get('linewidth') or spec['style']['linewidth']), marker=marker,
                ms=float(st.get('markersize') or spec['style']['markersize'] * 1.4), label=label if shown else '_nolegend_',
                zorder=3)
        if text:                                  # value labels above each point (below for minima)
            below = st['text_below'] if 'text_below' in st else marker == '^'   # older layers: from the marker
            labels = ax.__dict__.setdefault('_pp_labels', [])        # placed by _place_labels once drawn
            ms = float(st.get('markersize') or spec['style']['markersize'] * 1.4) if marker else 0.0
            for xv, yv, tv in zip(x, sub[o['y']].to_numpy(float), frame.loc[sub.index, text]):
                labels.append({'id': f'label:{o.get("id")}:{xv:.6g}', 'xy': (xv, yv), 'text': str(tv),
                               'below': bool(below), 'marker': ms})


# ------------------------------------------------------------------ value labels without overlaps
# All distances in points, so the preview and an export at any DPI place the labels alike.
LABEL_GAP = 2.5          # between a label and its marker
LABEL_PAD = 1.2          # free space kept around each label
LABEL_ROOM = 2.5         # the axes grow at most this many times to make room above the points


def _curve_samples(P, step):
    """Points along a polyline (display coordinates, NaN = break) at most `step` apart."""
    P = np.asarray(P, dtype=float)
    ok = np.isfinite(P).all(axis=1)
    if ok.sum() < 2:
        return P[ok]
    seg = ok[:-1] & ok[1:]
    a, b = P[:-1][seg], P[1:][seg]
    n = np.clip(np.ceil(np.hypot(*(b - a).T) / step).astype(int), 1, 400)
    idx = np.repeat(np.arange(a.shape[0]), n)
    frac = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
    return np.vstack([a[idx] + (b - a)[idx] * frac[:, None], P[ok][-1:]])


def _obstacles(ax, pt):
    """What a label should not cover: the curves (as close samples) and the markers ([x, y, radius]), in pixels."""
    view = ax.bbox
    curves, marks = [], []
    for line in ax.get_lines():
        if not line.get_visible() or not len(line.get_xydata()):
            continue
        P = line.get_transform().transform(line.get_xydata())
        if line.get_linestyle() not in ('None', 'none', '', ' '):
            curves.append(_curve_samples(P, 1.2 * pt))
        if line.get_marker() not in (None, 'None', 'none', '', ' '):
            marks.append(np.column_stack([P, np.full(len(P), line.get_markersize() / 2 * pt)]))
    for col in ax.collections:                    # scatter points
        offs = col.get_offsets()
        if col.get_visible() and len(offs) and len(offs) < 200_000 and hasattr(col, 'get_sizes') and len(col.get_sizes()):
            P = col.get_offset_transform().transform(offs)
            marks.append(np.column_stack([P, np.full(len(P), np.sqrt(col.get_sizes()[0]) / 2 * pt)]))
    curves = np.vstack(curves) if curves else np.empty((0, 2))
    marks = np.vstack(marks) if marks else np.empty((0, 3))
    inside = lambda A: A[(A[:, 0] >= view.x0 - 50) & (A[:, 0] <= view.x1 + 50) & (A[:, 1] >= view.y0 - 50)  # noqa: E731
                         & (A[:, 1] <= view.y1 + 50) & np.isfinite(A[:, :2]).all(axis=1)]
    return inside(curves), inside(marks)


def _make_room(fig, ax, spec, items, sizes, pt):
    """Stretch the y axis (above the points, or below them for minima) so each label fits over its point
    inside the axes; not when the user fixed that limit, and never by more than LABEL_ROOM."""
    a = spec['axes']
    if ax.get_yscale() not in ('linear', 'log'):
        return False
    H = ax.bbox.height
    b, t = ax.get_ylim()                          # values at the bottom and at the top of the axes
    tr = ax.yaxis.get_transform()
    sb, st = tr.transform(np.array([[b], [t]], dtype=float)).ravel()
    grown = False
    for below in (False, True):
        fixed = a['ymin'] if (below != bool(a['invert_y'])) else a['ymax']
        if _num(fixed) is not None:
            continue
        need = 1.0
        for it, (w, h) in zip(items, sizes):
            if it['below'] != below or it.get('fixed'):
                continue
            f = ax.transAxes.inverted().transform(ax.transData.transform(it['xy']))[1]
            if not np.isfinite(f) or not 0 <= f <= 1:
                continue
            f = 1 - f if below else f             # distance from the edge the label grows from
            o = (it['marker'] / 2 + LABEL_GAP + 3 * LABEL_PAD) * pt + h     # clear of the frame
            if H - o > 0.3 * H:
                need = max(need, f * H / (H - o))
        if need > 1.0:
            need = min(need, LABEL_ROOM)
            if below:
                sb = st - (st - sb) * need
            else:
                st = sb + (st - sb) * need
            grown = True
    if grown:
        lo, hi = tr.inverted().transform(np.array([[sb], [st]])).ravel()
        if np.isfinite(lo) and np.isfinite(hi) and lo != hi:
            ax.set_ylim(lo, hi)
            return True
    return False


def _place_labels(fig, ax, spec):
    """Value labels of the overlays (peak positions…): each over its point (under it for minima). A label that
    would cover another one, a curve or the legend moves up or aside and is joined to its point by a thin
    leader line. Labels the user dragged (spec['moved']) stay where they were put."""
    from matplotlib.text import Text
    items = ax.__dict__.pop('_pp_labels', None)
    if not items:
        return
    size = float(spec['text']['tick_size']) * 0.9
    color = matplotlib.rcParams['text.color']
    pt = fig.dpi / 72
    renderer = fig._get_renderer()
    sizes = []
    for it in items:
        it['text'] = spec['texts'].get(it['id'], it['text'])
        tb = Text(0, 0, it['text'], fontsize=size, figure=fig).get_window_extent(renderer)
        sizes.append((tb.width, tb.height))
        if it['id'] in spec['moved']:
            it['fixed'] = spec['moved'][it['id']]
    fig.draw_without_rendering()                  # the final layout and limits
    if _make_room(fig, ax, spec, items, sizes, pt):
        fig.draw_without_rendering()
    legend = ax.get_legend()
    if legend is not None and legend.get_visible() and legend._loc == 0:   # 'best': keep the place it chose
        bb = legend.get_window_extent(renderer)
        legend.set_loc(tuple(ax.transAxes.inverted().transform((bb.x0, bb.y0))))
    keep_out = [legend.get_window_extent(renderer)] if legend is not None and legend.get_visible() else []
    curves, marks = _obstacles(ax, pt)
    view = ax.bbox
    pad = LABEL_PAD * pt
    placed = []                                   # [x0, y0, x1, y1] of the labels already placed

    def rect(it, w, h, dx, dy):                   # dx, dy in pixels from the point to the label's near edge
        X, Y = it['_d']
        x0 = X + dx - w / 2
        return (x0, Y - dy - h, x0 + w, Y - dy) if it['below'] else (x0, Y + dy, x0 + w, Y + dy + h)

    def hits(r, P, g=0.0):                        # points of P (grown by g, e.g. marker radii) in r
        if not len(P):
            return 0
        return int(np.count_nonzero((P[:, 0] + g >= r[0] - pad) & (P[:, 0] - g <= r[2] + pad)
                                    & (P[:, 1] + g >= r[1] - pad) & (P[:, 1] - g <= r[3] + pad)))

    def overlaps(r, others):
        return any(r[0] < o[2] + pad and r[2] > o[0] - pad and r[1] < o[3] + pad and r[3] > o[1] - pad for o in others)

    leaders = []                                  # leader lines already drawn: ((x0, y0), (x1, y1))

    def leader_of(it, r):                         # from the point to the middle of the label's near edge
        return (tuple(it['_d']), ((r[0] + r[2]) / 2, r[3] if it['below'] else r[1]))

    def crossings(seg):
        (ax_, ay_), (bx_, by_) = seg
        n = 0
        for (cx_, cy_), (dx_, dy_) in leaders:
            d1 = (bx_ - ax_) * (cy_ - ay_) - (by_ - ay_) * (cx_ - ax_)
            d2 = (bx_ - ax_) * (dy_ - ay_) - (by_ - ay_) * (dx_ - ax_)
            d3 = (dx_ - cx_) * (ay_ - cy_) - (dy_ - cy_) * (ax_ - cx_)
            d4 = (dx_ - cx_) * (by_ - cy_) - (dy_ - cy_) * (bx_ - cx_)
            n += d1 * d2 < 0 and d3 * d4 < 0
        s = np.linspace(0.15, 0.95, 6)[:, None]
        P = np.array(seg[0]) + (np.array(seg[1]) - np.array(seg[0])) * s
        return n + sum(hits(o, P) > 0 for o in placed)

    for it, (w, h) in zip(items, sizes):
        it['_d'] = ax.transData.transform(it['xy'])
        it['_wh'] = (w, h)
        it['_in'] = bool(np.isfinite(it['_d']).all() and view.x0 - 1 <= it['_d'][0] <= view.x1 + 1
                         and view.y0 - 1 <= it['_d'][1] <= view.y1 + 1)
        it['_base'] = (it['marker'] / 2 + LABEL_GAP) * pt
        if it.get('fixed') and it['_in']:
            dx, dy = (c * pt for c in it['fixed'])
            placed.append(rect(it, w, h, dx, -dy if it['below'] else dy))
            leaders.append(leader_of(it, placed[-1]))
    order = sorted((it for it in items if it['_in'] and not it.get('fixed')),
                   key=lambda it: it['_d'][1] if it['below'] else -it['_d'][1])     # the most prominent first
    for it in order:                              # where each label would go by itself: kept free for it
        it['_own'] = rect(it, *it['_wh'], 0, it['_base'])
    for n, it in enumerate(order):
        others = [o['_own'] for o in order[n + 1:]]
        w, h = it['_wh']
        X, Y = it['_d']
        near = (np.abs(curves[:, 0] - X) < 4 * w + 2 * pad) if len(curves) else None
        C = curves[near] if near is not None else curves
        M = marks[np.abs(marks[:, 0] - X) < 4 * w + 2 * pad] if len(marks) else marks
        best = None
        for k in range(14):
            dy = it['_base'] + k * (h + pad)
            for j, dx in enumerate((0, 0.6, -0.6, 1.2, -1.2, 1.8, -1.8, 2.6, -2.6, 3.4, -3.4)):
                r = rect(it, w, h, dx * w, dy)
                outside = r[0] < view.x0 + 1 or r[2] > view.x1 - 1 or r[1] < view.y0 + 1 or r[3] > view.y1 - 1
                cost = (1e6 if overlaps(r, placed) else 0) + (1e4 if outside else 0) + 60 * overlaps(r, others) \
                    + 400 * sum(overlaps(r, [(b.x0, b.y0, b.x1, b.y1)]) for b in keep_out) \
                    + 6 * hits(r, C) + 25 * hits(r, M[:, :2], M[:, 2] if len(M) else 0) \
                    + 1.5 * k + 0.9 * abs(dx) + (2 + 25 * crossings(leader_of(it, r)) if (k or dx) else 0)
                if best is None or cost < best[0]:
                    best = (cost, dx * w, dy, r)
            if best[0] < 1.5 * (k + 1) + 3:       # clean spot: higher rows can only cost more
                break
        it['fixed_px'] = best[1:3]
        placed.append(best[3])
        if best[1] or best[2] > it['_base']:
            leaders.append(leader_of(it, best[3]))

    for it in items:
        if 'fixed_px' in it:
            dx, dy = it['fixed_px'][0] / pt, it['fixed_px'][1] / pt
            dy = -dy if it['below'] else dy
        elif it.get('fixed'):
            dx, dy = it['fixed']
        else:
            dx, dy = 0.0, -(it['_base'] / pt) if it['below'] else it['_base'] / pt
        base = it['_base'] / pt
        leader = abs(dx) > 0.5 or abs(dy) > base + 0.5
        kw = {}
        if leader:
            kw['arrowprops'] = {'arrowstyle': '-', 'color': color, 'lw': 0.5, 'alpha': 0.8,
                                'shrinkA': 0.5, 'shrinkB': it['marker'] / 2 + 0.8}
        ann = ax.annotate(it['text'], it['xy'], xytext=(dx, dy), textcoords='offset points', ha='center',
                          va='top' if it['below'] else 'bottom', zorder=4, color=color, fontsize=size, **kw)
        ann._pp_id, ann._pp_offset, ann._pp_label = it['id'], (round(dx, 2), round(dy, 2)), True


def _tag_texts(fig, ax, spec, pid='', ax2=None, cbar=None):
    """Name the titles and axis labels the user can drag and rewrite, and move those already dragged
    (spec['moved']). field: where the text is kept in the specification (None: in spec['texts'])."""
    single = not pid                                    # one set of axes: its labels are the figure's own
    texts = [('title', ax.title if ax.title.get_text() else ax._left_title, 'text.title' if single else None),
             ('xlabel', ax.xaxis.label, 'text.xlabel'), ('ylabel', ax.yaxis.label, 'text.ylabel')]
    if ax.name == '3d':
        texts.append(('zlabel', ax.zaxis.label, 'text.zlabel'))
    if ax2 is not None:
        texts.append(('y2label', ax2.yaxis.label, 'text.y2label'))
    if cbar is not None:
        texts.append(('cblabel', cbar.ax.yaxis.label if cbar.orientation == 'vertical' else cbar.ax.xaxis.label,
                      'text.zlabel'))
    for name, artist, field in texts:
        _move_text(fig, artist, pid + name, spec, field)


def _move_text(fig, artist, key, spec, field=None):
    """Make a text draggable under the name key: rewritten (spec['texts'], when it has no field of its
    own) and moved by the offset in points the user dragged it (spec['moved'])."""
    from matplotlib.transforms import ScaledTranslation
    if artist is None:
        return
    if field is None and key in spec['texts']:
        artist.set_text(spec['texts'][key])
    if not artist.get_text():
        return
    dx, dy = spec['moved'].get(key, (0.0, 0.0))
    if dx or dy:
        artist.set_transform(artist.get_transform() + ScaledTranslation(dx / 72, dy / 72, fig.dpi_scale_trans))
    artist._pp_id, artist._pp_offset, artist._pp_field = key, (dx, dy), field


EXTRA_KINDS = {'line', 'scatter', 'step', 'errorbar', 'stem', 'regression', 'area', 'hist', 'kde', 'ecdf', 'polar'}


def _file_data(frame, spec, extra, name):
    """Data view of another loaded file, with its own X / Y / error columns."""
    sub = dict(spec, x=extra.get('x') or None, y=[c for c in (extra.get('y') or []) if c],
               xerr=None, yerr=extra.get('yerr') or None, hue=None, z=None, y2=[])
    d = Data(frame, sub)
    d.label_prefix = name
    d.key_prefix = f'{extra.get("id")}:'
    return d


def _layers(df, spec, extra_data):
    """[(name, Data)] for the figure: the main file plus each enabled extra file that has data."""
    main = Data(df, spec)
    extras = [e for e in spec.get('extra') or [] if isinstance(e, dict) and e.get('enabled', True)]
    layers = [(spec.get('name') or '', main)]
    for e in extras:
        frame = (extra_data or {}).get(e.get('id'))
        if frame is None or not (e.get('y') or spec['kind'] in ('hist', 'kde', 'ecdf')):
            continue
        try:
            layers.append((e.get('name') or e.get('id'), _file_data(frame, spec, e, e.get('name') or '')))
        except SpecError:
            continue
    if len(layers) > 1 and spec.get('name'):
        main.label_prefix = spec['name']
    return layers


def _series_count(df, spec, layers):
    """How many coloured series the figure will have (to spread a colour-map palette over them)."""
    if spec['kind'] == 'pie':                   # one colour per slice
        try:
            return max(1, len(_aggregate(Data(df, spec), spec['y'][:1])[0]))
        except (SpecError, KeyError, ValueError, TypeError):
            return 12
    groups = 1
    if spec['hue'] and spec['hue'] in df.columns:
        groups = df[spec['hue']].nunique()
    elif spec['kind'] in ('box', 'violin', 'strip', 'swarm') and spec['x'] in df.columns and len(spec['y']) == 1:
        groups = df[spec['x']].nunique()
    n = (len(spec['y']) + len(spec['y2'] or [])) * max(1, groups)
    n += sum(len(d.spec['y']) for _, d in layers[1:])
    n += sum(1 for o in spec.get('overlays') or [] if isinstance(o, dict) and not (o.get('style') or {}).get('color'))
    return max(1, int(n))


def _projection(kind):
    return 'polar' if kind == 'polar' else '3d' if kind in catalog.THREE_D_KINDS else None


def build_figure(df, spec, overlay_data=None, extra_data=None, series_log=None):
    """Create the Matplotlib Figure. Call inside style_context(spec) and rc_context(_rc(spec)).

    extra_data: {extra id: DataFrame} for spec['extra'] (other files drawn in the same figure).
    series_log: a ColorLog that records the colour given to each series and layer.
    """
    spec = normalize_spec(spec)
    kind = spec['kind']
    w, h = figure_size(spec)
    bg = spec['figure'].get('background') or None
    fig = Figure(figsize=(w, h), layout='constrained', facecolor=bg if spec['style']['base'] != 'dark' else None)
    weight = 'bold' if spec['text']['bold_labels'] else 'normal'

    if kind == 'pairplot':
        return _pairplot(fig, Data(df, spec), Series(spec, series_log, _series_count(df, spec, [None])), spec, weight)

    layers = _layers(df, spec, extra_data)
    if kind not in WHOLE_TABLE_KINDS:
        drawn = len(spec['y']) + len(spec['y2'] or []) + sum(len(d.spec['y']) for _, d in layers[1:])
        if drawn > MAX_DRAWN_SERIES:
            raise SpecError(f'{drawn:,} series are too many to draw one by one (at most {MAX_DRAWN_SERIES:,}): '
                            f'draw a heat map, or choose a block of columns.',
                            'too_many_series', n=drawn, max=MAX_DRAWN_SERIES)
    n_series = _series_count(df, spec, layers)
    layout = spec.get('layout') or {}
    if layout.get('mode') == 'panels' and len(layers) > 1:
        n = len(layers)
        ncols = max(1, min(n, int(layout.get('ncols') or 2)))
        nrows = -(-n // ncols)
        share = bool(layout.get('share', True))
        axes = fig.subplots(nrows, ncols, squeeze=False, sharex=share and kind not in catalog.THREE_D_KINDS,
                            sharey=share and kind not in catalog.THREE_D_KINDS,
                            subplot_kw={'projection': _projection(kind)} if _projection(kind) else None)
        for i, ax in enumerate(axes.flat):
            if i >= n:
                ax.set_visible(False)
                continue
            name, d = layers[i]
            d.label_prefix = ''
            letter = f'({chr(97 + i)})' if layout.get('letters', True) else ''
            title = ' '.join(t for t in (letter, name if layout.get('titles', True) else '') if t)
            _draw_panel(fig, ax, d, Series(spec, series_log, n_series), spec, kind, [], overlay_data, title=title, overlays=i == 0,
                        outer_x=i // ncols == nrows - 1 or i + ncols >= n, outer_y=i % ncols == 0 or not share,
                        pid=f'p{i}.')
        if spec['text']['title']:
            _move_text(fig, fig.suptitle(spec['text']['title'], fontweight=weight), 'suptitle', spec, 'text.title')
        return fig

    ax = fig.add_subplot(projection=_projection(kind))
    extras = [d for _, d in layers[1:]] if kind in EXTRA_KINDS else []
    _draw_panel(fig, ax, layers[0][1], Series(spec, series_log, n_series), spec, kind, extras, overlay_data,
                title=spec['text']['title'])
    return fig


def _draw_panel(fig, ax, d, ser, spec, kind, extras, overlay_data, title='', outer_x=True, outer_y=True,
                overlays=True, pid=''):
    """Draw one set of axes: main data, other files' series (extras), overlays, labels, ticks, limits, legend."""
    t = spec['text']
    weight = 'bold' if t['bold_labels'] else 'normal'
    ycols = d.spec['y']
    if kind in ('line', 'scatter', 'step', 'area', 'errorbar', 'regression', 'stem', 'polar', 'hexbin',
                'hist2d', 'contour', 'surface3d', 'scatter3d', 'waterfall') and not ycols:
        raise SpecError('Choose at least one Y column.')
    result = PLOTTERS[kind](ax, d, ser, ycols)
    for ed in extras or []:
        PLOTTERS[kind](ax, ed, ser, ed.spec['y'])
    if overlays and kind in OVERLAY_KINDS:
        _draw_overlays(ax, spec, ser, d.df, overlay_data)

    xlabel, ylabel = t['xlabel'], t['ylabel']
    auto_x = d.spec['x'] or ''
    auto_y = ycols[0] if len(ycols) == 1 else ''
    if kind in ('hist', 'kde', 'ecdf'):
        auto_x = ycols[0] if len(ycols) == 1 else (d.spec['x'] or '')
        auto_y = result
    elif kind in ('box', 'violin', 'strip', 'swarm'):
        auto_x = d.spec['x'] if (d.spec['x'] and len(ycols) == 1) else ''
        auto_y = ycols[0] if len(ycols) == 1 else ''
    elif kind in ('bar', 'barh') and not ycols:
        auto_y = d.lang['count']
    elif kind == 'heatmap' and not d.spec['z']:
        auto_x, auto_y = '', ''
    elif kind == 'corr' or kind == 'pie':
        auto_x = auto_y = ''
    elif kind == 'waterfall':
        auto_y = ''
    if kind == 'barh':
        auto_x, auto_y = auto_y, auto_x
    if kind != 'pie':
        three_d = kind in catalog.THREE_D_KINDS
        ax.set_xlabel((xlabel or auto_x) if outer_x or three_d else '', fontweight=weight)
        ax.set_ylabel((ylabel or auto_y) if outer_y or three_d else '', fontweight=weight)
    if kind in catalog.THREE_D_KINDS:            # the vertical axis: Z, or the values of the curves
        auto_z = d.spec['z'] or (ycols[0] if kind == 'waterfall' and len(ycols) == 1 else d.lang['value'])
        ax.set_zlabel(t['zlabel'] or auto_z, fontweight=weight)
    if title:
        ax.set_title(title, fontweight=weight, loc='left' if title.startswith('(') else 'center')

    cb = None
    if isinstance(result, tuple) and spec['style']['colorbar']:
        mappable, zlabel = result
        three_d = kind in catalog.THREE_D_KINDS
        cb = fig.colorbar(mappable, ax=ax, pad=0.15 if three_d else 0.02, aspect=25, shrink=0.7 if three_d else 1.0)
        if not three_d:                                   # in 3D the z axis already carries the label
            cb.set_label(t['zlabel'] or zlabel or '', fontweight=weight)
        cb.ax.tick_params(direction=spec['axes']['tick_direction'], labelsize=float(t['tick_size']))
        cb.outline.set_linewidth(float(spec['axes']['linewidth']))

    ax2 = None
    if spec['y2'] and kind in catalog.TWIN_KINDS and d.spec['y2']:
        ax2 = ax.twinx()
        PLOTTERS[kind](ax2, d, ser, d.spec['y2'])
        ax2.set_ylabel(t['y2label'] or (d.spec['y2'][0] if len(d.spec['y2']) == 1 else ''), fontweight=weight)
        _style_axes(ax2, spec, kind, twin=True)
        ax2.tick_params(which='both', left=False, right=True)
        lo, hi = _num(spec['axes']['y2min']), _num(spec['axes']['y2max'])
        if lo is not None or hi is not None:
            ax2.set_ylim(bottom=lo, top=hi)
        if spec['axes']['yscale'] == 'log':
            ax2.set_yscale('log')

    category_x = kind in ('bar', 'box', 'violin', 'strip', 'swarm')
    category_y = kind == 'barh'
    if kind in catalog.THREE_D_KINDS:
        _style_axes3d(ax, spec, kind)
    else:
        _style_axes(ax, spec, kind, twin=ax2, category_x=category_x, category_y=category_y)
        xlike = d.col(d.spec['x']) if d.spec['x'] and kind in catalog.TWIN_KINDS | {'area', 'stem', 'regression'} else None
        _apply_limits(ax, spec, xlike, kind)

    handles, labels = ax.get_legend_handles_labels()
    if ax2 is not None:
        h2, l2 = ax2.get_legend_handles_labels()
        handles, labels = handles + h2, labels + l2
    if result != 'nolegend':
        _legend(fig, ax, spec, handles, labels, kind)
    _tag_texts(fig, ax, spec, pid, ax2, cb)
    _place_labels(fig, ax, spec)


def _pairplot(fig, d, ser, spec, weight):
    cols = spec['y'] or [c for c in d.df.columns if pd.api.types.is_numeric_dtype(d.df[c])][:5]
    if len(cols) < 2:
        raise SpecError('A pair plot needs at least two numeric columns.')
    cols = cols[:8]
    n = len(cols)
    axes = fig.subplots(n, n, squeeze=False)
    groups = d.groups()
    styles = [ser.next(None if g is None else f'{spec["hue"]}::{g}', str(g) if g is not None else '') for g, _ in groups]
    for i, yi in enumerate(cols):
        for j, xj in enumerate(cols):
            ax = axes[i, j]
            for (g, sub), st in zip(groups, styles):
                if i == j:
                    v = d.values(xj, sub)
                    ax.hist(v, bins=min(30, max(5, int(np.sqrt(max(1, len(v)))))), color=st['color'],
                            alpha=0.6 if len(groups) > 1 else 0.85, histtype='stepfilled')
                else:
                    x = d.numeric(xj, sub)
                    y = d.numeric(yi, sub)
                    ok = x.notna() & y.notna()
                    ax.scatter(x[ok], y[ok], s=max(1.0, st['markersize'] ** 2 / 3), color=st['color'], alpha=0.6,
                               linewidths=0, label=st['label'] if (i, j) == (1, 0) else None)
            ax.tick_params(which='both', direction=spec['axes']['tick_direction'], labelsize=float(spec['text']['tick_size']) * 0.85)
            if i < n - 1:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel(xj, fontweight=weight)
                _move_text(fig, ax.xaxis.label, f'pair.x:{xj}', spec)
            if j > 0:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel(yi, fontweight=weight)
                _move_text(fig, ax.yaxis.label, f'pair.y:{yi}', spec)
    if spec['text']['title']:
        _move_text(fig, fig.suptitle(spec['text']['title'], fontweight=weight), 'suptitle', spec, 'text.title')
    if spec['hue'] and spec['legend']['show'] != 'hide':
        handles, labels = axes[1, 0].get_legend_handles_labels()
        if handles:
            _tag_legend(fig.legend(handles, labels, loc='outside right upper', frameon=bool(spec['legend']['frame']),
                                   title=spec['legend']['title'] or spec['hue']))
    return fig


# ------------------------------------------------------------------ output
def series_colors(df, spec, overlay_data=None, extra_data=None):
    """{series key: colour} exactly as the figure draws them (other exports use it to match)."""
    spec = normalize_spec(spec)
    log = ColorLog()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with style_context(spec), rc_context(_rc(spec)):
            build_figure(df, spec, overlay_data, extra_data, log)
    return {e['key']: e['color'] for e in log.series}


def render(df, spec, fmt='png', dpi=None, overlay_data=None, extra_data=None, info=None):
    """Render to bytes. fmt: png, tiff, jpg, pdf, svg or eps.

    overlay_data: {overlay id: DataFrame}; extra_data: {extra id: DataFrame} (other files in the figure).
    info: dict that receives 'series': [{'key', 'label', 'color'} …] — the colours really used (ColorLog).
    """
    spec = normalize_spec(spec)
    fmt = fmt.lower()
    if fmt not in ('png', 'tiff', 'jpg', 'pdf', 'svg', 'eps'):
        raise SpecError(f'Unsupported export format: {fmt}')
    dpi = float(dpi or spec['figure']['dpi'] or 300)
    w, h = figure_size(spec)
    if fmt in ('png', 'tiff', 'jpg') and w * h * dpi * dpi > MAX_PIXELS:
        raise SpecError(f'{w * dpi:.0f} × {h * dpi:.0f} px is too large; lower the DPI or the size.')
    transparent = bool(spec['figure']['transparent']) and fmt not in ('jpg', 'eps')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with style_context(spec), rc_context(_rc(spec)):
            log = ColorLog()
            fig = build_figure(df, spec, overlay_data, extra_data, log)
            if info is not None:
                info['series'] = log.entries()
            buf = io.BytesIO()
            kw = {}
            if fmt == 'tiff':
                kw['pil_kwargs'] = {'compression': 'tiff_lzw'}
            elif fmt == 'jpg':
                kw['pil_kwargs'] = {'quality': 95}
            elif fmt == 'pdf':
                kw['metadata'] = {'Creator': 'PyPlotter'}
            fig.savefig(buf, format='jpeg' if fmt == 'jpg' else fmt, dpi=dpi, transparent=transparent,
                        facecolor='auto' if not transparent else 'none', **kw)
            if info is not None:
                # Measure the figure as it was saved: savefig puts the DPI back, and axis labels keep a
                # position in pixels from the last drawing, which would no longer match the image.
                fig.set_dpi(dpi)
                fig.draw_without_rendering()
                info['axes'] = axes_geometry(fig)
                info['movables'] = movables(fig)
                info['zoom'] = zoom_axes(fig)
                info['face'] = mcolors.to_hex(fig.get_facecolor())
                if spec['kind'] in catalog.THREE_D_KINDS:
                    info['view3d'] = view3d(fig)
    return buf.getvalue()


# ------------------------------------------------------------------ rotatable 3D preview
PREVIEW_GRID = 48           # faces per side of a surface in the preview
PREVIEW_POINTS = 6000       # points of all 3D scatters together
PREVIEW_LINE = 1500         # points per 3D line
PREVIEW_TRIANGLES = 6000


def _thin(n, most):
    """Indices that keep at most `most` of n items, evenly spread (first and last kept)."""
    if n <= most:
        return np.arange(n)
    return np.unique(np.linspace(0, n - 1, most).round().astype(int))


def _coords(*arrays):
    """Lists for JSON, with None where a value is missing (a break in a line)."""
    return [[None if not np.isfinite(v) else round(float(v), 6) for v in np.asarray(a, dtype=float).ravel()]
            for a in arrays]


def view3d(fig):
    """What the page needs to rotate the 3D axes of a drawn figure smoothly while the mouse drags
    (web/view3d.js): for each 3D axes the inputs of mplot3d's projection (Axes3D.get_proj) and the
    map from projected coordinates to the image, plus a light copy of what the axes show, in the
    colours drawn. Call after the figure is drawn (positions and limits are then final)."""
    from matplotlib.colors import to_hex
    W, H = fig.bbox.width, fig.bbox.height
    renderer = fig._get_renderer()           # the figure may have no Agg canvas of its own

    def frac(bb):            # display box → [left, top, right, bottom] fractions from the top left
        return [float(bb.x0 / W), float(1 - bb.y1 / H), float(bb.x1 / W), float(1 - bb.y0 / H)]

    # What the preview must leave visible: colour bars and other 2D axes, legends, titles.
    keep = []
    for ax in fig.axes:
        if ax.name != '3d' and ax.get_visible():
            keep.append(frac(ax.get_tightbbox(renderer)))
        legend = ax.get_legend()
        if legend is not None and legend.get_visible():
            keep.append(frac(legend.get_window_extent(renderer)))
        if ax.name == '3d':
            for title in (ax.title, ax._left_title, ax._right_title):
                if title.get_text() and title.get_visible():
                    keep.append(frac(title.get_window_extent(renderer)))
    for artist in [*fig.legends, *fig.texts, getattr(fig, '_suptitle', None)]:
        if artist is not None and artist.get_visible():
            keep.append(frac(artist.get_window_extent(renderer)))
    out = []
    for ax in fig.axes:
        if ax.name != '3d' or not ax.get_visible():
            continue
        o, ex, ey = ax.transData.transform([(0, 0), (1, 0), (0, 1)])
        x0, y0, x1, y1 = ax.get_position().extents
        layers = []
        budget = PREVIEW_POINTS
        for col in ax.collections:
            mesh = getattr(col, '_pp_mesh', None)
            if mesh and mesh[0] in ('grid', 'wire'):
                X, Y, Z = mesh[1:]
                r, c = _thin(Z.shape[0], PREVIEW_GRID + 1), _thin(Z.shape[1], PREVIEW_GRID + 1)
                X, Y, Z = X[np.ix_(r, c)], Y[np.ix_(r, c)], Z[np.ix_(r, c)]
                layer = {'type': mesh[0], 'rows': int(Z.shape[0]), 'cols': int(Z.shape[1])}
                layer['x'], layer['y'], layer['z'] = _coords(X, Y, Z)
                if mesh[0] == 'grid':
                    face = (Z[:-1, :-1] + Z[1:, :-1] + Z[:-1, 1:] + Z[1:, 1:]) / 4
                    layer['colors'] = [to_hex(c) for c in col.to_rgba(face.ravel())]
                else:
                    layer['color'] = to_hex(col.get_edgecolor()[0])
                layers.append(layer)
            elif mesh and mesh[0] in ('tri', 'triwire'):
                from matplotlib.tri import Triangulation
                x, y, z = (np.asarray(a, dtype=float) for a in mesh[1:])
                idx = _thin(x.size, PREVIEW_TRIANGLES // 2)
                x, y, z = x[idx], y[idx], z[idx]
                tri = Triangulation(x, y).triangles
                layer = {'type': mesh[0], 'triangles': tri.tolist()}
                layer['x'], layer['y'], layer['z'] = _coords(x, y, z)
                if mesh[0] == 'tri':
                    layer['colors'] = [to_hex(c) for c in col.to_rgba(z[tri].mean(axis=1))]
                else:
                    layer['color'] = to_hex(col.get_edgecolor()[0])
                layers.append(layer)
            elif hasattr(col, '_offsets3d'):                   # a 3D scatter
                xs, ys, zs = (np.ma.filled(np.ma.asarray(a, dtype=float), np.nan) for a in col._offsets3d)
                idx = _thin(xs.size, max(50, budget))
                budget -= idx.size
                fc = col.get_facecolor()
                sizes = col.get_sizes()
                layer = {'type': 'points', 'size': float(np.sqrt(sizes[0])) if len(sizes) else 6.0,
                         'alpha': float(fc[0][3]) if len(fc) else 1.0}
                layer['x'], layer['y'], layer['z'] = _coords(xs[idx], ys[idx], zs[idx])
                if len(fc) > 1:
                    layer['colors'] = [to_hex(fc[i]) for i in idx]
                else:
                    layer['color'] = to_hex(fc[0]) if len(fc) else '#000000'
                layers.append(layer)
        for line in ax.lines:
            if not hasattr(line, 'get_data_3d') or not line.get_visible():
                continue
            xs, ys, zs = (np.asarray(a, dtype=float) for a in line.get_data_3d())
            idx = _thin(xs.size, PREVIEW_LINE)
            ls = line.get_linestyle()
            layer = {'type': 'line' if ls not in ('None', 'none', '', ' ') else 'points',
                     'color': to_hex(line.get_color()), 'width': float(line.get_linewidth()),
                     'size': float(line.get_markersize()), 'alpha': float(line.get_alpha() or 1.0)}
            layer['x'], layer['y'], layer['z'] = _coords(xs[idx], ys[idx], zs[idx])
            layers.append(layer)
        pane = [to_hex(a.pane.get_facecolor(), keep_alpha=True) for a in (ax.xaxis, ax.yaxis, ax.zaxis)]
        # How far mplot3d moves each axis label from the cube (axis3d.Axis._draw_ticks / _update_label_position).
        ax_points = 72 * float(sum(fig.dpi_scale_trans.inverted().transform(ax.bbox.size)))
        label_shift = [(a.labelpad + 21.0) * 48 / ax_points for a in (ax.xaxis, ax.yaxis, ax.zaxis)]
        axis_info = []
        for a in (ax.xaxis, ax.yaxis, ax.zaxis):
            ticks = a._update_ticks()           # the ticks inside the limits, as last drawn
            first = ticks[0] if ticks else None
            axis_info.append({
                'ticks': [float(t.get_loc()) for t in ticks],
                'ticklabels': [t.label1.get_text() if t.label1.get_visible() else '' for t in ticks],
                'tick_shift': ((first.get_pad() if first else 3.5) + 8.0) * 48 / ax_points,
                'tick_size': float(first.label1.get_fontsize()) if first else 10.0,
                'tick_color': to_hex(first.label1.get_color()) if first else '#000000',
                'tick_width': float(a._axinfo['tick']['linewidth'][True]),
                'grid': ({'color': to_hex(a._axinfo['grid']['color']), 'width': float(a._axinfo['grid']['linewidth'])}
                         if ax._draw_grid else None),
                'line': {'color': to_hex(a.line.get_color()), 'width': float(a.line.get_linewidth())},
            })
        out.append({
            'limits': [round(float(v), 9) for v in ax._get_scaled_limits()],
            'box': [float(v) for v in ax._roll_to_vertical(ax._box_aspect)],
            'dist': float(ax._dist), 'focal': float(ax._focal_length) if np.isfinite(ax._focal_length) else None,
            'elev': float(ax.elev), 'azim': float(ax.azim), 'roll': float(ax.roll),
            # projected (px, py) → fraction of the image from its top left corner
            'affine': [(ex[0] - o[0]) / W, (ey[0] - o[0]) / W, o[0] / W,
                       -(ex[1] - o[1]) / H, -(ey[1] - o[1]) / H, 1 - o[1] / H],
            'bbox': [float(x0), float(1 - y1), float(x1), float(1 - y0)],
            'face': to_hex(ax.get_facecolor()) if ax.get_facecolor()[3] > 0 else to_hex(fig.get_facecolor()),
            'pane': pane, 'edge': to_hex(ax.xaxis.pane.get_edgecolor()),
            'text': to_hex(ax.xaxis.label.get_color()),
            'labels': [ax.get_xlabel(), ax.get_ylabel(), ax.get_zlabel()], 'label_shift': label_shift,
            'label_rotate': [bool(a.get_rotate_label(a.label.get_text())) for a in (ax.xaxis, ax.yaxis, ax.zaxis)],
            'axis': axis_info,
            'label_size': float(ax.xaxis.label.get_fontsize()),
            'layers': layers,
        })
    if not out:
        return None
    return {'axes': out, 'size_in': [round(float(v), 4) for v in fig.get_size_inches()],
            'face': to_hex(fig.get_facecolor()), 'keep': keep}


def axes_geometry(fig):
    """Where each set of data axes lies in the drawn image, so a click becomes data x, y:
    [{'box': [x0, y0, x1, y1] (fractions of the figure, from the bottom left), 'xlim', 'ylim', 'xscale', 'yscale'}].
    Colour bars, polar axes and second y axes (same box as the first) are left out."""
    out = []
    for ax in fig.axes:
        if ax.name != 'rectilinear' or ax.get_label() == '<colorbar>' or not ax.get_visible():
            continue
        box = [round(float(v), 5) for v in ax.get_position().extents]
        if any(g['box'] == box for g in out):
            continue
        out.append({'box': box, 'xlim': [float(v) for v in ax.get_xlim()], 'ylim': [float(v) for v in ax.get_ylim()],
                    'xscale': ax.get_xscale(), 'yscale': ax.get_yscale(),
                    # dates: x is in days since 1970 (Matplotlib's epoch), limits are written as dates
                    'xdate': isinstance(ax.xaxis.get_major_formatter(), (mdates.AutoDateFormatter, mdates.ConciseDateFormatter,
                                                                         mdates.DateFormatter))})
    return out


MAX_MOVABLES = 400


def movables(fig):
    """The texts the user can drag and rewrite on the preview (named by _move_text, _place_labels, _tag_legend):
    [{'id', 'kind': 'text' | 'label' | 'legend', 'box': [x0, y0, x1, y1] (fractions of the figure from the bottom
    left), 'offset': [dx, dy] points already applied, 'text': what it says, 'field': where the specification keeps
    it (None: spec['texts']), 'anchor': the point a value label belongs to, 'ref': a legend's axes box}]."""
    from matplotlib.legend import Legend
    from matplotlib.text import Text
    renderer = fig._get_renderer()
    W, H = fig.bbox.width, fig.bbox.height
    frac = lambda bb: [round(float(v), 5) for v in (bb.x0 / W, bb.y0 / H, bb.x1 / W, bb.y1 / H)]  # noqa: E731
    first = next((ax for ax in fig.axes if ax.get_visible() and ax.get_label() != '<colorbar>'), None)
    out = []
    for artist in dict.fromkeys(fig.findobj(lambda a: hasattr(a, '_pp_id'))):
        if len(out) >= MAX_MOVABLES or not artist.get_visible():
            continue
        extra, kind = {}, 'text'
        if isinstance(artist, Legend):
            parent = artist.axes if artist.axes is not None else first
            if parent is None:
                continue
            kind, text = 'legend', artist.get_title().get_text()
            extra['ref'] = frac(parent.bbox)
            bb = artist.get_window_extent(renderer)
        elif getattr(artist, '_pp_label', False):            # a value label: listed while its point is in view
            ax = artist.axes
            p = ax.transData.transform(artist.xy)
            if not (np.isfinite(p).all() and ax.bbox.x0 - 1 <= p[0] <= ax.bbox.x1 + 1 and ax.bbox.y0 - 1 <= p[1] <= ax.bbox.y1 + 1):
                continue
            artist.update_positions(renderer)
            kind, text = 'label', artist.get_text()
            extra['anchor'] = [float(p[0] / W), float(p[1] / H)]
            bb = Text.get_window_extent(artist, renderer)   # the text alone, without its leader line
        else:
            text = artist.get_text()
            if not text:
                continue
            bb = artist.get_window_extent(renderer)
        if not (bb.width > 0 and bb.height > 0 and np.isfinite(bb.extents).all()):
            continue
        out.append({'id': artist._pp_id, 'kind': kind, 'box': frac(bb), 'text': text,
                    'field': getattr(artist, '_pp_field', None),
                    'offset': [float(v) for v in getattr(artist, '_pp_offset', (0, 0))], **extra})
    return out


def zoom_axes(fig):
    """Axes zoomed with the mouse wheel rather than a box: polar (the radius) and 3D (the three ranges)."""
    W, H = fig.bbox.width, fig.bbox.height
    out = []
    for ax in fig.axes:
        if not ax.get_visible() or ax.name not in ('polar', '3d'):
            continue
        bb = ax.bbox
        item = {'type': ax.name, 'box': [float(bb.x0 / W), float(bb.y0 / H), float(bb.x1 / W), float(bb.y1 / H)]}
        if ax.name == 'polar':
            item['rlim'] = [float(v) for v in ax.get_ylim()]
        else:
            item.update(xlim=[float(v) for v in ax.get_xlim()], ylim=[float(v) for v in ax.get_ylim()],
                        zlim=[float(v) for v in ax.get_zlim()])
        out.append(item)
    return out


if __name__ == '__main__':
    import sys
    print(__doc__, file=sys.stderr)
