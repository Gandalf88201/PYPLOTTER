"""Peak finding with positions, heights, prominences, widths (FWHM) and areas (scipy.signal.find_peaks).

Heights, widths and areas are measured above the chosen baseline (see the Baseline analysis). The area
of each peak runs from the lowest point between it and the neighbouring peak on each side, or from where
the signal meets the baseline if that comes first (perpendicular drop), so overlapping peaks share
the signal instead of borrowing a distant minimum.
"""
import numpy as np
import pandas as pd

from piplotter import baselines

PLUGIN = {
    'id': 'peaks',
    'order': 30,
    'name': {'en': 'Peak finding', 'it': 'Ricerca dei picchi'},
    'category': 'signal',
    'description': {'en': 'Finds peaks (or minima) by prominence; reports position, height, FWHM and area above the baseline.',
                    'it': 'Trova i picchi (o i minimi) per prominenza; riporta posizione, altezza, FWHM e area sopra la linea di base.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        *baselines.params(extra=[('none', {'en': 'none (y = 0)', 'it': 'nessuna (y = 0)'})], default='arpls'),
        {'id': 'prominence', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Minimum prominence (empty = 5% of range)', 'it': 'Prominenza minima (vuoto = 5% dell’intervallo)'}},
        {'id': 'distance', 'type': 'int', 'default': 1, 'min': 1,
         'label': {'en': 'Minimum distance (points)', 'it': 'Distanza minima (punti)'}},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'label': {'en': 'Only from x =', 'it': 'Solo da x ='}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'label': {'en': 'Only to x =', 'it': 'Solo fino a x ='}},
        {'id': 'minima', 'type': 'bool', 'default': False, 'label': {'en': 'Find minima instead', 'it': 'Cerca i minimi'}},
        {'id': 'labels', 'type': 'bool', 'default': True,
         'label': {'en': 'Write the position above each peak', 'it': 'Scrivi la posizione sopra ogni picco'}},
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}


def label_of(v):
    """Short text for a number: 4 significant digits, no exponent for ordinary values."""
    v = float(v)
    if v != 0 and (abs(v) >= 1e6 or abs(v) < 1e-3):
        return f'{v:.3g}'
    return np.format_float_positional(v, precision=4, unique=False, fractional=False, trim='-')


def peak_bounds(s, idx):
    """(left, right) indices of each peak of s (signal above the baseline): the lowest point towards each
    neighbouring peak, or the first point at or below the baseline if that comes sooner."""
    out = []
    for k, i in enumerate(idx):
        lo = idx[k - 1] if k else 0
        hi = idx[k + 1] if k + 1 < len(idx) else s.size - 1
        left = lo + int(np.argmin(s[lo:i + 1]))
        under = np.nonzero(s[left:i + 1] <= 0)[0]
        if under.size:
            left += int(under[-1])
        right = i + int(np.argmin(s[i:hi + 1]))
        under = np.nonzero(s[i:right + 1] <= 0)[0]
        if under.size:
            right = i + int(under[0])
        out.append((left, right))
    return out


def run(df, p, ctx):
    from scipy import signal
    from scipy.integrate import trapezoid
    x, y = ctx.xy(df, p['x'], p['y'])
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    b = ctx.baseline(x, y, p)                      # on the whole signal, then the range
    base = b.values if b is not None else np.zeros_like(y)
    keep = np.ones(x.size, bool)
    if p.get('xmin') is not None:
        keep &= x >= p['xmin']
    if p.get('xmax') is not None:
        keep &= x <= p['xmax']
    x, y, base = x[keep], y[keep], base[keep]
    if x.size < 3:
        raise ValueError(ctx.tr('Fewer than three points in the range.', 'Meno di tre punti nell’intervallo.'))
    s = (base - y) if p['minima'] else (y - base)  # signal above (or depth below) the baseline
    prom = p['prominence'] if p['prominence'] is not None else 0.05 * (s.max() - s.min())
    idx, props = signal.find_peaks(s, prominence=prom, distance=p['distance'])
    bounds = peak_bounds(s, idx)
    heights = s[idx]
    xi = np.arange(x.size)
    if idx.size:
        lefts = np.array([lo for lo, _ in bounds])
        rights = np.array([hi for _, hi in bounds])
        # FWHM at half the height above the baseline, within each peak's own bounds.
        _, _, wl, wr = signal.peak_widths(s, idx, rel_height=0.5,
                                          prominence_data=(np.maximum(heights, 1e-300), lefts, rights))
        lx, rx = np.interp(wl, xi, x), np.interp(wr, xi, x)
    else:
        lx = rx = np.array([])
    rows, found = [], []
    for k, i in enumerate(idx):
        lo, hi = bounds[k]
        area = float(trapezoid(s[lo:hi + 1], x[lo:hi + 1]))
        fwhm = float(rx[k] - lx[k]) if heights[k] > 0 else float('nan')
        rows.append({ctx.tr('position', 'posizione'): x[i], ctx.tr('height', 'altezza'): heights[k],
                     ctx.tr('prominence', 'prominenza'): props['prominences'][k], 'FWHM': fwhm,
                     ctx.tr('from x', 'da x'): x[lo], ctx.tr('to x', 'a x'): x[hi],
                     ctx.tr('area above baseline', 'area sopra la linea di base'): area})
        found.append({'index': int(i), 'position': float(x[i]), 'height': float(heights[k]), 'signal': float(y[i]),
                      'baseline': float(base[i]), 'prominence': float(props['prominences'][k]), 'fwhm': fwhm,
                      'area': area, 'left': float(x[lo]), 'right': float(x[hi])})
    r = ctx.result()
    r.value(ctx.tr('peaks found', 'picchi trovati'), len(idx), key='n_peaks')
    r.keep('peaks', found)    # for recipes: position, height (above baseline), signal, baseline, fwhm, area, left, right
    r.value(ctx.tr('baseline', 'linea di base'), b.label if b is not None else ctx.tr('none (y = 0)', 'nessuna (y = 0)'))
    r.value(ctx.tr('prominence threshold', 'soglia di prominenza'), prom)
    r.table(ctx.tr('Peaks', 'Picchi'), rows)
    if b is not None:
        r.cite(*b.refs)
        if b.below > 0.05:
            r.text(ctx.tr('More than 5 % of the points are under the baseline: check it with the Baseline analysis.',
                          'Oltre il 5 % dei punti è sotto la linea di base: controllala con l’analisi Linea di base.'))

    xname = p['x'] or 'index'
    label = ctx.tr('peaks', 'picchi')
    base_name = ctx.tr('baseline', 'linea di base')
    marks = np.full(y.size, np.nan)
    marks[idx] = y[idx]
    columns = {xname: x, p['y']: y, label: marks}
    if b is not None:
        columns[base_name] = base
        r.overlay(pd.DataFrame({xname: x, base_name: base}), xname, base_name, label=base_name,
                  style={'linestyle': '--', 'linewidth': 0.9})
    marks_frame = pd.DataFrame({xname: x[idx], label: y[idx]})
    text = None
    if p['labels']:
        text = ctx.tr('position', 'posizione')
        marks_frame[text] = [label_of(v) for v in x[idx]]
    r.overlay(marks_frame, xname, label, label=label, text=text,
              style={'linestyle': 'none', 'marker': '^' if p['minima'] else 'v', 'text_below': bool(p['minima'])})
    r.data(pd.DataFrame(columns), name=f'{label} · {p["y"]}',
           plot={'kind': 'line', 'x': xname, 'y': [p['y'], label] + ([base_name] if b is not None else []),
                 'series': {label: {'linestyle': 'none', 'marker': 'v'}, base_name: {'linestyle': '--'}}})
    return r
