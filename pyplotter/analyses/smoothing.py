"""Smoothing and derivatives: Savitzky–Golay, moving average, Gaussian filter (scipy.signal / scipy.ndimage)."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'smoothing',
    'order': 10,
    'name': {'en': 'Smoothing & derivative', 'it': 'Smoothing e derivata'},
    'category': 'signal',
    'description': {'en': 'Savitzky–Golay (with 1st/2nd derivative), moving average or Gaussian filter.',
                    'it': 'Savitzky–Golay (con derivata prima/seconda), media mobile o filtro gaussiano.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'method', 'type': 'choice', 'default': 'savgol', 'label': {'en': 'Method', 'it': 'Metodo'},
         'choices': [{'value': 'savgol', 'label': 'Savitzky–Golay'},
                     {'value': 'moving', 'label': {'en': 'moving average', 'it': 'media mobile'}},
                     {'value': 'gaussian', 'label': {'en': 'Gaussian filter', 'it': 'filtro gaussiano'}}]},
        {'id': 'window', 'type': 'int', 'default': 21, 'min': 3, 'label': {'en': 'Window (points)', 'it': 'Finestra (punti)'}},
        {'id': 'order', 'type': 'int', 'default': 3, 'min': 1, 'max': 9,
         'label': {'en': 'Polynomial order (Savitzky–Golay)', 'it': 'Ordine del polinomio (Savitzky–Golay)'}},
        {'id': 'deriv', 'type': 'choice', 'default': '0', 'label': {'en': 'Output', 'it': 'Risultato'},
         'choices': [{'value': '0', 'label': {'en': 'smoothed signal', 'it': 'segnale filtrato'}},
                     {'value': '1', 'label': {'en': '1st derivative', 'it': 'derivata prima'}},
                     {'value': '2', 'label': {'en': '2nd derivative', 'it': 'derivata seconda'}}]},
    ],
    'references': [
        'Savitzky, A. & Golay, M. J. E. Smoothing and differentiation of data by simplified least squares procedures. '
        'Anal. Chem. 36, 1627–1639 (1964). doi:10.1021/ac60214a047',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    from scipy import ndimage, signal
    x, y = ctx.xy(df, p['x'], p['y'])
    if p['x']:
        order = np.argsort(x, kind='stable')
        x, y = x[order], y[order]
    w = int(p['window'])
    w = min(w if w % 2 else w + 1, y.size - (1 - y.size % 2))
    deriv = int(p['deriv'])
    dx = float(np.median(np.diff(x))) if x.size > 1 else 1.0
    if p['method'] == 'savgol':
        if p['order'] >= w:
            raise ValueError(ctx.tr('The window must be larger than the polynomial order.',
                                    'La finestra deve essere più grande dell’ordine del polinomio.'))
        out = signal.savgol_filter(y, w, int(p['order']), deriv=deriv, delta=dx)
    else:
        sm = (pd.Series(y).rolling(w, center=True, min_periods=1).mean().to_numpy() if p['method'] == 'moving'
              else ndimage.gaussian_filter1d(y, sigma=w / 6))
        out = sm
        for _ in range(deriv):
            out = np.gradient(out, x)
    label = [ctx.tr('smoothed', 'filtrato'), "d/dx", "d²/dx²"][deriv]
    xname = p['x'] or 'index'
    r = ctx.result()
    r.value(ctx.tr('window used (points)', 'finestra usata (punti)'), w)
    if deriv == 0:
        r.value(ctx.tr('RMS of removed noise', 'RMS del rumore rimosso'), float(np.sqrt(np.mean((y - out) ** 2))))
    data = pd.DataFrame({xname: x, p['y']: y, label: out})
    ys = [p['y'], label] if deriv == 0 else [label]
    r.data(data, name=f'{label} · {p["y"]}', plot={'kind': 'line', 'x': xname, 'y': ys,
                                                   'series': {p['y']: {'alpha': 0.35}}})
    return r
