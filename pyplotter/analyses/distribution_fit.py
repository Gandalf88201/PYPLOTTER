"""Fit probability distributions to a sample (scipy.stats) and rank them by AIC and the KS test."""
import numpy as np
import pandas as pd

DISTS = ['norm', 'lognorm', 'gamma', 'weibull_min', 'expon', 'beta', 't', 'logistic', 'cauchy', 'gumbel_r']

PLUGIN = {
    'id': 'distribution_fit',
    'order': 60,
    'name': {'en': 'Distribution fitting', 'it': 'Fit di distribuzioni'},
    'category': 'stats',
    'description': {'en': 'Maximum-likelihood fit of several distributions; best one by AIC; histogram with densities.',
                    'it': 'Fit di massima verosimiglianza di più distribuzioni; la migliore per AIC; istogramma con densità.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Column', 'it': 'Colonna'}},
        {'id': 'dists', 'type': 'text', 'default': 'norm, lognorm, gamma, weibull_min, expon',
         'label': {'en': 'Distributions (scipy.stats names)', 'it': 'Distribuzioni (nomi scipy.stats)'},
         'help': {'en': 'e.g. ' + ', '.join(DISTS), 'it': 'es. ' + ', '.join(DISTS)}},
        {'id': 'bins', 'type': 'int', 'default': 40, 'min': 5, 'label': {'en': 'Histogram bins', 'it': 'Intervalli istogramma'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
        'Akaike, H. A new look at the statistical model identification. IEEE Trans. Autom. Control 19, 716–723 (1974). '
        'doi:10.1109/TAC.1974.1100705',
    ],
}


def run(df, p, ctx):
    from scipy import stats
    v = ctx.numeric(df, p['y']).to_numpy(float)
    if v.size < 10:
        raise ValueError(ctx.tr('At least 10 values are needed.', 'Servono almeno 10 valori.'))
    names = [d.strip() for d in p['dists'].split(',') if d.strip()]
    counts, edges = np.histogram(v, bins=p['bins'], density=True)
    centers = 0.5 * (edges[1:] + edges[:-1])
    grid = np.linspace(edges[0], edges[-1], 400)
    rows, curves = [], {}
    for name in names:
        dist = getattr(stats, name, None)
        if not isinstance(dist, stats.rv_continuous):
            rows.append({ctx.tr('distribution', 'distribuzione'): name, 'note': ctx.tr('unknown name', 'nome sconosciuto')})
            continue
        try:
            params = dist.fit(v)
            ll = float(np.sum(dist.logpdf(v, *params)))
            k = len(params)
            # The cdf itself, not its name: SciPy ≥ 1.18 maps 'norm' to ndtr, which takes no loc/scale.
            ks = stats.kstest(v, dist.cdf, args=params)
            rows.append({ctx.tr('distribution', 'distribuzione'): name, 'log-likelihood': ll, 'AIC': 2 * k - 2 * ll,
                         'BIC': k * np.log(v.size) - 2 * ll, 'KS D': ks.statistic, 'KS p': ks.pvalue,
                         ctx.tr('parameters', 'parametri'): ', '.join(f'{x:.5g}' for x in params)})
            curves[name] = dist.pdf(grid, *params)
        except Exception as exc:
            rows.append({ctx.tr('distribution', 'distribuzione'): name, 'note': str(exc)[:120]})
    table = pd.DataFrame(rows)
    if 'AIC' in table:
        table = table.sort_values('AIC', na_position='last')
    r = ctx.result()
    if 'AIC' in table and table['AIC'].notna().any():
        best = table.iloc[0]
        r.value(ctx.tr('best distribution (lowest AIC)', 'distribuzione migliore (AIC minimo)'),
                best[ctx.tr('distribution', 'distribuzione')])
    r.table(ctx.tr('Fitted distributions', 'Distribuzioni adattate'), table)
    data = pd.concat([pd.DataFrame({'x': centers, ctx.tr('histogram', 'istogramma'): counts}),
                      pd.DataFrame({'x': grid, **curves})], ignore_index=True).sort_values('x', kind='stable')
    hist = ctx.tr('histogram', 'istogramma')
    r.data(data, name=f'distributions · {p["y"]}', plot={
        'kind': 'line', 'x': 'x', 'y': [hist, *curves],
        'series': {hist: {'linestyle': '-', 'alpha': 0.35, 'linewidth': 3}},
        'text': {'xlabel': p['y'], 'ylabel': ctx.tr('probability density', 'densità di probabilità')}})
    return r
