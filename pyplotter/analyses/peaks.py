"""Peak finding with positions, heights, prominences, widths (FWHM) and areas (scipy.signal.find_peaks)."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'peaks',
    'order': 30,
    'name': {'en': 'Peak finding', 'it': 'Ricerca dei picchi'},
    'category': 'signal',
    'description': {'en': 'Finds peaks (or minima) by prominence; reports position, height, FWHM and area.',
                    'it': 'Trova i picchi (o i minimi) per prominenza; riporta posizione, altezza, FWHM e area.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'prominence', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Minimum prominence (empty = 5% of range)', 'it': 'Prominenza minima (vuoto = 5% dell’intervallo)'}},
        {'id': 'distance', 'type': 'int', 'default': 1, 'min': 1,
         'label': {'en': 'Minimum distance (points)', 'it': 'Distanza minima (punti)'}},
        {'id': 'minima', 'type': 'bool', 'default': False, 'label': {'en': 'Find minima instead', 'it': 'Cerca i minimi'}},
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}


def run(df, p, ctx):
    from scipy import signal
    from scipy.integrate import trapezoid
    x, y = ctx.xy(df, p['x'], p['y'])
    if p['x']:
        order = np.argsort(x, kind='stable')
        x, y = x[order], y[order]
    s = -y if p['minima'] else y
    prom = p['prominence'] if p['prominence'] is not None else 0.05 * (s.max() - s.min())
    idx, props = signal.find_peaks(s, prominence=prom, distance=p['distance'])
    widths, wh, left, right = signal.peak_widths(s, idx, rel_height=0.5)
    xi = np.arange(x.size)
    lx, rx = np.interp(left, xi, x), np.interp(right, xi, x)
    rows = []
    for k, i in enumerate(idx):
        lo, hi = int(props['left_bases'][k]), int(props['right_bases'][k])
        seg_x, seg_y = x[lo:hi + 1], y[lo:hi + 1]
        base = np.interp(seg_x, [x[lo], x[hi]], [y[lo], y[hi]])
        rows.append({ctx.tr('position', 'posizione'): x[i], ctx.tr('height', 'altezza'): y[i],
                     ctx.tr('prominence', 'prominenza'): props['prominences'][k], 'FWHM': rx[k] - lx[k],
                     ctx.tr('area above baseline', 'area sopra la linea di base'): abs(trapezoid(seg_y - base, seg_x))})
    r = ctx.result()
    r.value(ctx.tr('peaks found', 'picchi trovati'), len(idx))
    r.value(ctx.tr('prominence threshold', 'soglia di prominenza'), prom)
    r.table(ctx.tr('Peaks', 'Picchi'), rows)
    xname = p['x'] or 'index'
    marks = np.full(y.size, np.nan)
    marks[idx] = y[idx]
    label = ctx.tr('peaks', 'picchi')
    data = pd.DataFrame({xname: x, p['y']: y, label: marks})
    r.data(data, name=f'{label} · {p["y"]}', plot={'kind': 'line', 'x': xname, 'y': [p['y'], label],
                                                   'series': {label: {'linestyle': 'none', 'marker': 'v'}}})
    return r
