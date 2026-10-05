"""Block averaging (Flyvbjerg–Petersen) for correlated data such as MD or MC time series.

Repeatedly halves the series into blocks and estimates the standard error of the mean at each
blocking level; the plateau gives the true error and the statistical inefficiency.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'block_average',
    'order': 20,
    'name': {'en': 'Block averaging (error of correlated data)', 'it': 'Block averaging (errore di dati correlati)'},
    'category': 'timeseries',
    'description': {'en': 'Mean and its true standard error for time-correlated data (MD, Monte Carlo, sensors).',
                    'it': 'Media e suo vero errore standard per dati correlati nel tempo (MD, Monte Carlo, sensori).'},
    'requires': [],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Series', 'it': 'Serie'}},
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Time column (for the overlay, optional)', 'it': 'Colonna del tempo (per la sovrapposizione, facoltativa)'}},
        {'id': 'discard', 'type': 'float', 'default': 0, 'min': 0, 'max': 90,
         'label': {'en': 'Discard the first … % (equilibration)', 'it': 'Scarta il primo … % (equilibratura)'}},
    ],
    'references': [
        'Flyvbjerg, H. & Petersen, H. G. Error estimates on averages of correlated data. '
        'J. Chem. Phys. 91, 461–466 (1989). doi:10.1063/1.457480',
        'Harris, C. R. et al. Array programming with NumPy. Nature 585, 357–362 (2020). doi:10.1038/s41586-020-2649-2',
    ],
}


def blocking(y):
    """Rows: level, block size, number of blocks, SEM, error of SEM."""
    rows, x, level = [], np.asarray(y, float), 0
    while x.size >= 4:
        n = x.size
        sem = np.sqrt(x.var(ddof=1) / n)
        rows.append((level, 2 ** level, n, sem, sem / np.sqrt(2 * (n - 1))))
        if n % 2:
            x = x[:-1]
        x = 0.5 * (x[0::2] + x[1::2])
        level += 1
    return pd.DataFrame(rows, columns=['level', 'block size', 'blocks', 'SEM', 'SEM error'])


def plateau(table):
    """First level whose SEM agrees (within its error) with all later ones; else the maximum."""
    sem, err = table['SEM'].to_numpy(), table['SEM error'].to_numpy()
    for i in range(len(sem) - 2):
        later = sem[i + 1:len(sem) - 1]
        if later.size and np.all(np.abs(later - sem[i]) <= err[i] + err[i + 1:len(sem) - 1]):
            return i
    return int(np.argmax(sem[:-1])) if len(sem) > 1 else 0


def run(df, p, ctx):
    t, y = ctx.xy(df, p['x'], p['y'])
    start = int(y.size * p['discard'] / 100)
    t, y = t[start:], y[start:]
    if y.size < 16:
        raise ValueError(ctx.tr('At least 16 values are needed.', 'Servono almeno 16 valori.'))
    table = blocking(y)
    i = plateau(table)
    sem_true = float(table['SEM'][i])
    sem_naive = float(table['SEM'][0])
    g = (sem_true / sem_naive) ** 2 if sem_naive > 0 else np.nan
    r = ctx.result()
    r.value(ctx.tr('values used', 'valori usati'), y.size)
    r.value(ctx.tr('mean', 'media'), y.mean(), sem_true)
    r.value(ctx.tr('naive standard error (uncorrelated)', 'errore standard ingenuo (non correlato)'), sem_naive)
    r.value(ctx.tr('block-averaged standard error', 'errore standard con block averaging'), sem_true,
            float(table['SEM error'][i]))
    r.value(ctx.tr('plateau block size', 'dimensione dei blocchi al plateau'), int(table['block size'][i]))
    r.value(ctx.tr('statistical inefficiency g', 'inefficienza statistica g'), g)
    r.value(ctx.tr('effective independent samples', 'campioni indipendenti effettivi'), y.size / g if g else np.nan)
    r.text(ctx.tr('Check the plot: the SEM should level off (plateau). If it keeps rising, the series is '
                  'too short for a reliable error.',
                  'Controlla il grafico: lo SEM deve stabilizzarsi (plateau). Se continua a salire, la serie è '
                  'troppo corta per un errore affidabile.'))
    r.table(ctx.tr('Blocking levels', 'Livelli di blocking'), table)
    xname = p['x'] or 'index'
    mean_name = ctx.tr('mean', 'media')
    line = pd.DataFrame({xname: [t[0], t[-1]], mean_name: [y.mean()] * 2,
                         'low': [y.mean() - 2 * sem_true] * 2, 'high': [y.mean() + 2 * sem_true] * 2})
    r.overlay(line, xname, mean_name, 'low', 'high', label=mean_name, band_label='±2 SEM (block)',
              style={'linestyle': '--'})
    r.data(table, name=f'blocking · {p["y"]}', plot={
        'kind': 'errorbar', 'x': 'block size', 'y': ['SEM'], 'yerr': 'SEM error',
        'axes': {'xscale': 'log'}, 'style': {'marker': 'o'},
        'text': {'xlabel': ctx.tr('block size (points)', 'dimensione blocco (punti)'),
                 'ylabel': ctx.tr('standard error of the mean', 'errore standard della media')}})
    return r
