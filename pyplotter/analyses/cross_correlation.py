"""Normalised cross-correlation of two equally spaced series (scipy.signal.correlate)."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'cross_correlation',
    'order': 30,
    'name': {'en': 'Cross-correlation', 'it': 'Correlazione incrociata'},
    'category': 'timeseries',
    'description': {'en': 'Correlation of two series as a function of the lag; finds the delay of best match.',
                    'it': 'Correlazione tra due serie in funzione del ritardo; trova il ritardo di massima somiglianza.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'a', 'type': 'column', 'default': 'y', 'label': {'en': 'Series A', 'it': 'Serie A'}},
        {'id': 'b', 'type': 'column', 'default': 'y2', 'label': {'en': 'Series B', 'it': 'Serie B'}},
        {'id': 'dt', 'type': 'float', 'default': 1, 'min': 0, 'label': {'en': 'Time step', 'it': 'Passo temporale'}},
        {'id': 'maxlag', 'type': 'int', 'optional': True, 'min': 1,
         'label': {'en': 'Maximum lag (points, empty = auto)', 'it': 'Ritardo massimo (punti, vuoto = auto)'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. '
        'Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    from scipy import signal

    a = ctx.numeric(df, p['a'], dropna=False)
    b = ctx.numeric(df, p['b'], dropna=False)
    ok = a.notna() & b.notna()
    a, b = a[ok].to_numpy(float), b[ok].to_numpy(float)
    n = a.size
    if n < 10:
        raise ValueError(ctx.tr('At least 10 paired values are needed.', 'Servono almeno 10 coppie di valori.'))
    a = (a - a.mean()) / (a.std() or 1)
    b = (b - b.mean()) / (b.std() or 1)
    cc = signal.correlate(a, b, mode='full', method='auto') / n
    lags = signal.correlation_lags(n, n, mode='full')
    m = int(p['maxlag']) if p['maxlag'] else max(10, n // 4)
    keep = np.abs(lags) <= m
    lags, cc = lags[keep], cc[keep]
    best = int(np.argmax(np.abs(cc)))
    r = ctx.result()
    r.value('N', n)
    r.value(ctx.tr('correlation at zero lag', 'correlazione a ritardo zero'), float(cc[lags == 0][0]))
    r.value(ctx.tr('strongest correlation', 'correlazione più forte'), float(cc[best]))
    r.value(ctx.tr('at lag', 'al ritardo'), float(lags[best] * p['dt']))
    r.value(ctx.tr('approx. 95% band (±2/√N)', 'banda ~95% (±2/√N)'), 2 / np.sqrt(n))
    r.text(ctx.tr(f'A positive lag means that {p["a"]} follows {p["b"]}.',
                  f'Un ritardo positivo indica che {p["a"]} segue {p["b"]}.'))
    out = pd.DataFrame({'lag': lags * p['dt'], 'cross-correlation': cc})
    r.data(out, name=f'xcorr · {p["a"]} × {p["b"]}',
           plot={'kind': 'line', 'x': 'lag', 'y': ['cross-correlation']})
    return r
