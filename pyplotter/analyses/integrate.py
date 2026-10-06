"""Numerical integration: total area and cumulative integral (scipy.integrate, trapezoid/Simpson)."""
import numpy as np
import pandas as pd

from pyplotter import baselines

PLUGIN = {
    'id': 'integrate',
    'order': 40,
    'name': {'en': 'Integral & area', 'it': 'Integrale e area'},
    'category': 'signal',
    'description': {'en': 'Area under the curve between two x values and the cumulative integral.',
                    'it': 'Area sotto la curva tra due valori di x e integrale cumulativo.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'default': 'x', 'label': {'en': 'X', 'it': 'X'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Y', 'it': 'Y'}},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'label': {'en': 'From x =', 'it': 'Da x ='}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'label': {'en': 'To x =', 'it': 'A x ='}},
        *baselines.params(extra=[('none', {'en': 'none (area down to y = 0)', 'it': 'nessuna (area fino a y = 0)'}),
                                 ('ends', {'en': 'straight line between the ends of the range', 'it': 'retta tra gli estremi dell’intervallo'})],
                          default='none'),
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}


def run(df, p, ctx):
    from scipy import integrate
    x, y = ctx.xy(df, p['x'], p['y'])
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    b = ctx.baseline(x, y, p)                      # on the whole signal, then the range
    if b is not None:
        y = y - b.values
    keep = np.ones(x.size, bool)
    if p['xmin'] is not None:
        keep &= x >= p['xmin']
    if p['xmax'] is not None:
        keep &= x <= p['xmax']
    x, y = x[keep], y[keep]
    if x.size < 2:
        raise ValueError(ctx.tr('Fewer than two points in the range.', 'Meno di due punti nell’intervallo.'))
    if p['baseline'] == 'ends':
        y = y - np.interp(x, [x[0], x[-1]], [y[0], y[-1]])
    r = ctx.result()
    r.value(ctx.tr('range', 'intervallo'), f'{x[0]:.6g} … {x[-1]:.6g}')
    if b is not None:
        r.value(ctx.tr('baseline', 'linea di base'), b.label)
        r.cite(*b.refs)
    r.value(ctx.tr('area (trapezoid)', 'area (trapezi)'), integrate.trapezoid(y, x))
    if x.size >= 3:
        r.value(ctx.tr('area (Simpson)', 'area (Simpson)'), integrate.simpson(y, x=x))
    r.value(ctx.tr('area of |y|', 'area di |y|'), integrate.trapezoid(np.abs(y), x))
    cum = integrate.cumulative_trapezoid(y, x, initial=0)
    label = ctx.tr('cumulative integral', 'integrale cumulativo')
    r.data(pd.DataFrame({p['x']: x, p['y']: y, label: cum}), name=f'∫ {p["y"]}',
           plot={'kind': 'line', 'x': p['x'], 'y': [label]})
    return r
