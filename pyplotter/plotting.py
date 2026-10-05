"""PyPlotter figure renderer.

``render(df, spec, fmt)`` turns a DataFrame and a JSON figure specification into PNG, TIFF,
JPEG, PDF, SVG or EPS bytes. It depends only on NumPy, pandas and Matplotlib (seaborn for
strip/swarm plots), so the file can be shipped next to an exported figure and re-run
without PyPlotter: ``python make_figure.py``.
"""
import copy
import io
import logging
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import colors as mcolors, rc_context, style as mstyle, ticker  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

try:
    from . import catalog
except ImportError:          # standalone copy next to an exported figure
    import catalog

logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

UNITS = {'in': 1.0, 'cm': 1 / 2.54, 'mm': 1 / 25.4, 'pt': 1 / 72}
MAX_PIXELS = 400e6

DEFAULT_SPEC = {
    'kind': 'line', 'lang': 'en',
    'x': None, 'y': [], 'y2': [], 'hue': None, 'z': None, 'xerr': None, 'yerr': None,
    'series': {},
    'figure': {'width': 89, 'height': 67, 'units': 'mm', 'dpi': 600, 'transparent': False, 'background': '#ffffff'},
    'text': {'title': '', 'xlabel': '', 'ylabel': '', 'y2label': '', 'zlabel': '', 'font': '', 'size': 8,
             'title_size': 9, 'label_size': 8, 'tick_size': 7, 'legend_size': 7, 'mathtext': 'dejavusans',
             'bold_labels': False},
    'axes': {'xscale': 'linear', 'yscale': 'linear', 'xmin': None, 'xmax': None, 'ymin': None, 'ymax': None,
             'y2min': None, 'y2max': None, 'grid': 'auto', 'tick_direction': 'in', 'minor_ticks': True,
             'mirror_ticks': True, 'spines': 'box', 'invert_x': False, 'invert_y': False, 'aspect': 'auto',
             'xrotation': 0, 'sci': False, 'linewidth': 0.8},
    'legend': {'show': 'auto', 'loc': 'best', 'frame': False, 'ncol': 1, 'title': ''},
    'style': {'base': 'publication', 'palette': 'okabe-ito', 'cmap': 'viridis', 'cmap_reverse': False,
              'linewidth': 1.2, 'linestyle': '-', 'marker': '', 'markersize': 4, 'alpha': 1.0,
              'bins': 30, 'density': False, 'stacked': False, 'fill': True, 'levels': 12, 'contour_lines': True,
              'gridsize': 40, 'fit': 'linear', 'fit_degree': 2, 'annotate': False, 'capsize': 2,
              'error_style': 'bars', 'colorbar': True, 'vmin': None, 'vmax': None, 'polar_degrees': True,
              'bar_width': 0.8, 'agg': 'mean', 'show_fliers': True},
}

LABELS = {
    'en': {'count': 'Count', 'density': 'Density', 'probability': 'Cumulative probability', 'value': 'Value',
           'index': 'Index', 'fit': 'fit', 'frequency': 'Frequency', 'correlation': 'Correlation'},
    'it': {'count': 'Conteggio', 'density': 'Densità', 'probability': 'Probabilità cumulativa', 'value': 'Valore',
           'index': 'Indice', 'fit': 'fit', 'frequency': 'Frequenza', 'correlation': 'Correlazione'},
}


class SpecError(ValueError):
    """The specification does not fit the data (missing column, wrong type…)."""


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


class Series:
    """Style of one plotted series: palette colour + per-column overrides."""

    def __init__(self, spec):
        self.spec = spec
        self.count = 0
        self.colors = palette_colors(spec['style']['palette'], 12)

    def next(self, key, label):
        st = self.spec['style']
        over = self.spec['series'].get(str(key), {}) if key is not None else {}
        color = over.get('color') or self.colors[self.count % len(self.colors)]
        self.count += 1
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
def _xy_loop(ax, d, ser, ycols, draw):
    for ycol in ycols:
        for g, sub in d.groups():
            x, y, ok = d.xy(ycol, sub)
            if not len(x):
                continue
            key = ycol if g is None else f'{ycol}::{g}'
            st = ser.next(key, _series_label(ycol, g, len(ycols)))
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
            out.append((str(g), f'{ycols[0]}::{g}', d.values(ycols[0], sub)))
        return out
    if not ycols and d.spec['x']:
        ycols = [d.spec['x']]
    for y in ycols:
        out.append((str(y), y, d.values(y)))
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
    ax.pie(vals, labels=labels, colors=[s['color'] for s in styles], autopct='%1.1f%%', startangle=90,
           counterclock=False, wedgeprops={'edgecolor': 'white', 'linewidth': 0.8},
           textprops={'fontsize': d.spec['text']['tick_size']})
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
                      interpolation='nearest')
        _label_matrix_axes(ax, [str(c) for c in xs], [str(r) for r in ys])
        if spec['style']['annotate'] and mat.size <= 600:
            _annotate(ax, mat)
        return m, spec['z']
    cols = ycols or [c for c in d.df.columns if pd.api.types.is_numeric_dtype(d.df[c])]
    mat = d.df[cols].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=float)
    m = ax.imshow(mat, aspect='auto', cmap=get_cmap(spec), vmin=vmin, vmax=vmax, interpolation='nearest')
    rows = d.col(spec['x']).astype(str).tolist() if spec['x'] else None
    _label_matrix_axes(ax, cols, rows)
    if spec['style']['annotate'] and mat.size <= 600:
        _annotate(ax, mat)
    return m, d.lang['value']


def _label_matrix_axes(ax, xlabels, ylabels):
    def thin(labels):
        step = max(1, int(np.ceil(len(labels) / 25)))
        return np.arange(0, len(labels), step), [labels[i] for i in range(0, len(labels), step)]
    if xlabels is not None:
        p, l = thin(xlabels)
        ax.set_xticks(p, l, rotation=45 if max((len(s) for s in l), default=0) > 3 else 0,
                      ha='right' if max((len(s) for s in l), default=0) > 3 else 'center')
    if ylabels is not None:
        p, l = thin(ylabels)
        ax.set_yticks(p, l)
    ax.minorticks_off()


def plot_corr(ax, d, ser, ycols):
    cols = ycols if len(ycols) >= 2 else [c for c in d.df.columns if pd.api.types.is_numeric_dtype(d.df[c])]
    if len(cols) < 2:
        raise SpecError('A correlation matrix needs at least two numeric columns.')
    c = d.df[cols].apply(pd.to_numeric, errors='coerce').corr().to_numpy()
    cmap = matplotlib.colormaps['RdBu_r' if not d.spec['style']['cmap_reverse'] else 'RdBu']
    m = ax.imshow(c, cmap=cmap, vmin=-1, vmax=1, interpolation='nearest')
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


PLOTTERS = {
    'line': plot_line, 'scatter': plot_scatter, 'step': plot_step, 'area': plot_area, 'stem': plot_stem,
    'errorbar': plot_errorbar, 'regression': plot_regression, 'polar': plot_polar,
    'bar': plot_bar, 'barh': lambda ax, d, s, y: plot_bar(ax, d, s, y, horizontal=True),
    'box': plot_box, 'violin': plot_violin, 'strip': plot_strip,
    'swarm': lambda ax, d, s, y: plot_strip(ax, d, s, y, swarm=True), 'pie': plot_pie,
    'hist': plot_hist, 'kde': plot_kde, 'ecdf': plot_ecdf,
    'heatmap': plot_heatmap, 'contour': plot_contour, 'hexbin': plot_hexbin, 'hist2d': plot_hist2d,
    'corr': plot_corr,
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
    try:
        lo, hi = conv(xmin), conv(xmax)
        if lo is not None or hi is not None:
            ax.set_xlim(left=lo, right=hi)
    except (ValueError, TypeError):
        pass
    lo, hi = _num(a['ymin']), _num(a['ymax'])
    if lo is not None or hi is not None:
        ax.set_ylim(bottom=lo, top=hi)
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


def _legend(fig, ax, spec, handles, labels, kind):
    lg = spec['legend']
    show = lg['show']
    if show == 'hide' or not handles or (show == 'auto' and len(handles) < 2 and kind != 'regression'):
        return
    kw = dict(frameon=bool(lg['frame']), ncol=max(1, int(lg['ncol'] or 1)), title=lg['title'] or None,
              fontsize=float(spec['text']['legend_size']), title_fontsize=float(spec['text']['legend_size']))
    if lg['frame']:
        kw.update(fancybox=False, edgecolor='black', framealpha=1)
    loc = lg['loc']
    if loc.startswith('outside'):
        where = {'outside right': 'outside right upper', 'outside top': 'outside upper center',
                 'outside bottom': 'outside lower center'}.get(loc, 'outside right upper')
        if where != 'outside right upper' and lg['ncol'] in (1, '1', None):
            kw['ncol'] = min(len(handles), 4)
        fig.legend(handles, labels, loc=where, **kw)
    else:
        ax.legend(handles, labels, loc=loc, **kw)


def build_figure(df, spec):
    """Create the Matplotlib Figure. Call inside style_context(spec) and rc_context(_rc(spec))."""
    spec = normalize_spec(spec)
    kind = spec['kind']
    d = Data(df, spec)
    ser = Series(spec)
    w, h = figure_size(spec)
    bg = spec['figure'].get('background') or None
    fig = Figure(figsize=(w, h), layout='constrained', facecolor=bg if spec['style']['base'] != 'dark' else None)
    t = spec['text']
    weight = 'bold' if t['bold_labels'] else 'normal'

    if kind == 'pairplot':
        return _pairplot(fig, d, ser, spec, weight)

    ax = fig.add_subplot(projection='polar' if kind == 'polar' else None)
    ycols = spec['y']
    if kind in ('line', 'scatter', 'step', 'area', 'errorbar', 'regression', 'stem', 'polar', 'hexbin',
                'hist2d', 'contour') and not ycols:
        raise SpecError('Choose at least one Y column.')
    result = PLOTTERS[kind](ax, d, ser, ycols)

    xlabel, ylabel = t['xlabel'], t['ylabel']
    auto_x = spec['x'] or ''
    auto_y = ycols[0] if len(ycols) == 1 else ''
    if kind in ('hist', 'kde', 'ecdf'):
        auto_x = ycols[0] if len(ycols) == 1 else (spec['x'] or '')
        auto_y = result
    elif kind in ('box', 'violin', 'strip', 'swarm'):
        auto_x = spec['x'] if (spec['x'] and len(ycols) == 1) else ''
        auto_y = ycols[0] if len(ycols) == 1 else ''
    elif kind in ('bar', 'barh') and not ycols:
        auto_y = d.lang['count']
    elif kind == 'heatmap' and not spec['z']:
        auto_x, auto_y = '', ''
    elif kind == 'corr' or kind == 'pie':
        auto_x = auto_y = ''
    if kind == 'barh':
        auto_x, auto_y = auto_y, auto_x
    if kind != 'pie':
        ax.set_xlabel(xlabel or auto_x, fontweight=weight)
        ax.set_ylabel(ylabel or auto_y, fontweight=weight)
    if t['title']:
        ax.set_title(t['title'], fontweight=weight)

    if isinstance(result, tuple) and spec['style']['colorbar']:
        mappable, zlabel = result
        cb = fig.colorbar(mappable, ax=ax, pad=0.02, aspect=25)
        cb.set_label(t['zlabel'] or zlabel or '', fontweight=weight)
        cb.ax.tick_params(direction=spec['axes']['tick_direction'], labelsize=float(t['tick_size']))
        cb.outline.set_linewidth(float(spec['axes']['linewidth']))

    ax2 = None
    if spec['y2'] and kind in catalog.TWIN_KINDS:
        ax2 = ax.twinx()
        PLOTTERS[kind](ax2, d, ser, spec['y2'])
        ax2.set_ylabel(t['y2label'] or (spec['y2'][0] if len(spec['y2']) == 1 else ''), fontweight=weight)
        _style_axes(ax2, spec, kind, twin=True)
        ax2.tick_params(which='both', left=False, right=True)
        lo, hi = _num(spec['axes']['y2min']), _num(spec['axes']['y2max'])
        if lo is not None or hi is not None:
            ax2.set_ylim(bottom=lo, top=hi)
        if spec['axes']['yscale'] == 'log':
            ax2.set_yscale('log')

    category_x = kind in ('bar', 'box', 'violin', 'strip', 'swarm')
    category_y = kind == 'barh'
    _style_axes(ax, spec, kind, twin=ax2, category_x=category_x, category_y=category_y)
    xlike = d.col(spec['x']) if spec['x'] and kind in catalog.TWIN_KINDS | {'area', 'stem', 'regression'} else None
    _apply_limits(ax, spec, xlike, kind)

    handles, labels = ax.get_legend_handles_labels()
    if ax2 is not None:
        h2, l2 = ax2.get_legend_handles_labels()
        handles, labels = handles + h2, labels + l2
    if result != 'nolegend':
        _legend(fig, ax, spec, handles, labels, kind)
    return fig


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
            if j > 0:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel(yi, fontweight=weight)
    if spec['text']['title']:
        fig.suptitle(spec['text']['title'], fontweight=weight)
    if spec['hue'] and spec['legend']['show'] != 'hide':
        handles, labels = axes[1, 0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc='outside right upper', frameon=bool(spec['legend']['frame']),
                       title=spec['legend']['title'] or spec['hue'])
    return fig


# ------------------------------------------------------------------ output
def render(df, spec, fmt='png', dpi=None):
    """Render to bytes. fmt: png, tiff, jpg, pdf, svg or eps."""
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
            fig = build_figure(df, spec)
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
    return buf.getvalue()


if __name__ == '__main__':
    import sys
    print(__doc__, file=sys.stderr)
