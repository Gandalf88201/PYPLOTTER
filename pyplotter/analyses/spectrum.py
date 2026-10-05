"""Power spectral density (Welch or periodogram, scipy.signal) and dominant frequencies."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'spectrum',
    'order': 20,
    'name': {'en': 'Power spectrum (FFT / Welch)', 'it': 'Spettro di potenza (FFT / Welch)'},
    'category': 'signal',
    'description': {'en': 'Frequency content of an equally spaced signal and its dominant frequencies.',
                    'it': 'Contenuto in frequenza di un segnale equispaziato e frequenze dominanti.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Time column (optional)', 'it': 'Colonna del tempo (facoltativa)'}},
        {'id': 'fs', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Sampling frequency (if no time column)', 'it': 'Frequenza di campionamento (senza colonna del tempo)'}},
        {'id': 'method', 'type': 'choice', 'default': 'welch', 'label': {'en': 'Method', 'it': 'Metodo'},
         'choices': [{'value': 'welch', 'label': 'Welch'}, {'value': 'periodogram', 'label': 'periodogram'}]},
        {'id': 'detrend', 'type': 'choice', 'default': 'constant', 'label': {'en': 'Detrend', 'it': 'Rimuovi trend'},
         'choices': [{'value': 'constant', 'label': {'en': 'mean', 'it': 'media'}},
                     {'value': 'linear', 'label': {'en': 'linear', 'it': 'lineare'}}]},
    ],
    'references': [
        'Welch, P. The use of fast Fourier transform for the estimation of power spectra. IEEE Trans. Audio '
        'Electroacoust. 15, 70–73 (1967). doi:10.1109/TAU.1967.1161901',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    from scipy import signal
    y = ctx.numeric(df, p['y']).to_numpy(float)
    fs, unit = 1.0, ctx.tr('cycles/point', 'cicli/punto')
    if p['x']:
        t = ctx.numeric(df, p['x']).to_numpy(float)
        dt = float(np.median(np.diff(t))) if t.size > 1 else 1.0
        fs, unit = 1 / dt, f'1/{p["x"]}'
    elif p['fs']:
        fs, unit = float(p['fs']), 'Hz'
    if p['method'] == 'welch':
        f, pxx = signal.welch(y, fs=fs, nperseg=min(y.size, max(256, y.size // 8)), detrend=p['detrend'])
    else:
        f, pxx = signal.periodogram(y, fs=fs, detrend=p['detrend'])
    keep = f > 0
    f, pxx = f[keep], pxx[keep]
    peaks, _ = signal.find_peaks(pxx)
    top = peaks[np.argsort(pxx[peaks])[::-1][:5]] if peaks.size else np.array([int(np.argmax(pxx))])
    r = ctx.result()
    r.value(ctx.tr('sampling frequency', 'frequenza di campionamento'), fs, None, unit)
    r.value(ctx.tr('frequency resolution', 'risoluzione in frequenza'), float(f[1] - f[0]) if f.size > 1 else None, None, unit)
    r.table(ctx.tr('Dominant frequencies', 'Frequenze dominanti'),
            [{ctx.tr('frequency', 'frequenza'): f[i], ctx.tr('period', 'periodo'): 1 / f[i], 'PSD': pxx[i]} for i in top])
    data = pd.DataFrame({ctx.tr('frequency', 'frequenza'): f, 'PSD': pxx})
    r.data(data, name=f'PSD · {p["y"]}', plot={'kind': 'line', 'x': data.columns[0], 'y': ['PSD'],
                                               'axes': {'yscale': 'log'},
                                               'text': {'xlabel': f'{data.columns[0]} ({unit})'}})
    return r
