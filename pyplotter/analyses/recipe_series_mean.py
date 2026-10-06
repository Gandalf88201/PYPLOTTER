"""Recipe: average of a time series (MD, Monte Carlo, sensors) with its true error.

Steps: 1. block averaging (Flyvbjerg–Petersen), 2. autocorrelation (integrated correlation time), as
two independent estimates of how correlated the rows are; the mean with its corrected error is drawn
on the figure as a dashed line with a ±2 SEM band.
"""
import numpy as np

PLUGIN = {
    'id': 'recipe_series_mean',
    'order': 20,
    'name': {'en': 'Mean of a time series (correlated data)', 'it': 'Media di una serie temporale (dati correlati)'},
    'category': 'recipe',
    'description': {'en': 'Mean with its true error, correlation time and number of independent samples; '
                          'for MD/Monte Carlo trajectories and sensor logs.',
                    'it': 'Media con il suo vero errore, tempo di correlazione e numero di campioni indipendenti; '
                          'per traiettorie MD/Monte Carlo e registrazioni di sensori.'},
    'steps': [
        {'en': 'Block averaging: true standard error of the mean', 'it': 'Block averaging: vero errore standard della media'},
        {'en': 'Autocorrelation: correlation time τ and independent samples',
         'it': 'Autocorrelazione: tempo di correlazione τ e campioni indipendenti'},
        {'en': 'Mean ± 2 SEM drawn on the figure', 'it': 'Media ± 2 SEM disegnata sulla figura'},
    ],
    'requires': ['statsmodels', 'scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Series', 'it': 'Serie'}},
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Time column (optional)', 'it': 'Colonna del tempo (facoltativa)'}},
        {'id': 'discard', 'type': 'float', 'default': 0, 'min': 0, 'max': 90,
         'label': {'en': 'Discard the first … % (equilibration)', 'it': 'Scarta il primo … % (equilibratura)'}},
    ],
    'references': [
        'Flyvbjerg, H. & Petersen, H. G. Error estimates on averages of correlated data. '
        'J. Chem. Phys. 91, 461–466 (1989). doi:10.1063/1.457480',
    ],
}


def run(df, p, ctx):
    y = ctx.numeric(df, p['y'], dropna=False)
    start = int(y.notna().sum() * p['discard'] / 100)
    keep = y.notna().to_numpy().nonzero()[0][start:]
    part = df.iloc[keep]
    step = ctx.tr('Step', 'Passo')

    # Whole table to block averaging (it discards itself), so the mean line keeps the figure's x.
    block = ctx.run('block_average', df, y=p['y'], x=p['x'], discard=p['discard'])
    acf = ctx.run('autocorrelation', part, y=p['y'], x=p['x'], partial=False, fit_exp=True)

    mean, sem = block.get('mean'), block.get('sem')
    naive = block.get('sem_naive')
    g_block, g_acf = block.get('g'), acf.get('g')
    unit = acf.get('unit') or ''
    r = ctx.result()
    r.value(ctx.tr('values used', 'valori usati'), block.get('n'))
    r.value(ctx.tr('mean ± true standard error', 'media ± vero errore standard'), mean, sem, key='mean')
    r.value(ctx.tr('standard error if the rows were independent', 'errore standard se le righe fossero indipendenti'),
            naive, key='sem_naive')
    r.value(ctx.tr('correlation time τ_int', 'tempo di correlazione τ_int'), acf.get('tau_int'), None, unit, key='tau_int')
    r.value(ctx.tr('statistical inefficiency g (blocks / ACF)', 'inefficienza statistica g (blocchi / ACF)'),
            f'{g_block:.3g} / {g_acf:.3g}')
    r.value(ctx.tr('independent samples', 'campioni indipendenti'), block.get('n_eff'), key='n_eff')

    if g_block and g_block > 2:
        r.text(ctx.tr(f'The rows are correlated: the true error is {np.sqrt(g_block):.1f}× the naive one. '
                      f'Quote {mean:.6g} ± {sem:.2g}.',
                      f'Le righe sono correlate: il vero errore è {np.sqrt(g_block):.1f}× quello ingenuo. '
                      f'Riporta {mean:.6g} ± {sem:.2g}.'))
    else:
        r.text(ctx.tr('The rows are practically independent: the ordinary standard error is fine.',
                      'Le righe sono praticamente indipendenti: va bene l’errore standard ordinario.'))
    if g_block and g_acf and not (0.5 < g_block / g_acf < 2):
        r.text(ctx.tr('Blocks and ACF disagree on g by more than a factor 2: the series may be too short or not '
                      'stationary (check the beginning and use "Discard the first … %").',
                      'Blocchi e ACF non concordano su g di oltre un fattore 2: la serie può essere troppo corta o '
                      'non stazionaria (controlla l’inizio e usa «Scarta il primo … %»).'))

    r.include(block, f'{step} 1 · block averaging', overlays=True)     # mean ± 2 SEM on the figure
    r.include(acf, f'{step} 2 · ' + ctx.tr('autocorrelation', 'autocorrelazione'))
    r.data(acf.frame, name=f'ACF · {p["y"]}', plot=acf.plot)
    return r
