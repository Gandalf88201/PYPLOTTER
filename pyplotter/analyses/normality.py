"""Normality tests (Shapiro–Wilk, D'Agostino–Pearson, Anderson–Darling, Kolmogorov–Smirnov) and Q–Q data."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'normality',
    'order': 20,
    'name': {'en': 'Normality tests & Q–Q plot', 'it': 'Test di normalità e grafico Q–Q'},
    'category': 'stats',
    'description': {'en': 'Is the sample compatible with a normal distribution? Four tests and a Q–Q plot.',
                    'it': 'Il campione è compatibile con una distribuzione normale? Quattro test e un grafico Q–Q.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Column', 'it': 'Colonna'}},
        {'id': 'alpha', 'type': 'float', 'default': 0.05, 'min': 0.001, 'max': 0.5,
         'label': {'en': 'Significance level α', 'it': 'Livello di significatività α'}},
    ],
    'references': [
        'Shapiro, S. S. & Wilk, M. B. An analysis of variance test for normality (complete samples). '
        'Biometrika 52, 591–611 (1965). doi:10.1093/biomet/52.3-4.591',
        'D’Agostino, R. & Pearson, E. S. Tests for departure from normality. Biometrika 60, 613–622 (1973). '
        'doi:10.1093/biomet/60.3.613',
        'Anderson, T. W. & Darling, D. A. Asymptotic theory of certain “goodness of fit” criteria based on '
        'stochastic processes. Ann. Math. Stat. 23, 193–212 (1952). doi:10.1214/aoms/1177729437',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    from scipy import stats
    v = ctx.numeric(df, p['y']).to_numpy(float)
    n = v.size
    if n < 3:
        raise ValueError(ctx.tr('At least 3 values are needed.', 'Servono almeno 3 valori.'))
    a = p['alpha']
    yes, no = ctx.tr('compatible with normal', 'compatibile con la normale'), ctx.tr('NOT normal', 'NON normale')
    rows = []
    sample = v if n <= 5000 else np.random.default_rng(0).choice(v, 5000, replace=False)
    w, pw = stats.shapiro(sample)
    rows.append({'test': 'Shapiro–Wilk' + (' (5000 random values)' if n > 5000 else ''), 'statistic': w, 'p': pw,
                 ctx.tr('verdict', 'esito'): yes if pw >= a else no})
    if n >= 8:
        k2, pk = stats.normaltest(v)
        rows.append({'test': 'D’Agostino–Pearson K²', 'statistic': k2, 'p': pk,
                     ctx.tr('verdict', 'esito'): yes if pk >= a else no})
    try:                                   # SciPy ≥ 1.17: p-value interpolated from tables
        ad = stats.anderson(v, dist='norm', method='interpolate')
        rows.append({'test': 'Anderson–Darling', 'statistic': ad.statistic, 'p': ad.pvalue,
                     ctx.tr('verdict', 'esito'): yes if ad.pvalue >= a else no})
    except TypeError:                      # older SciPy: compare with the critical value nearest to α
        ad = stats.anderson(v, dist='norm')
        levels = list(ad.significance_level)
        idx = int(np.argmin([abs(l / 100 - a) for l in levels]))
        rows.append({'test': f'Anderson–Darling (α={levels[idx] / 100:g})', 'statistic': ad.statistic,
                     'p': None, ctx.tr('verdict', 'esito'): yes if ad.statistic < ad.critical_values[idx] else no})
    ks, pks = stats.kstest((v - v.mean()) / v.std(ddof=1), 'norm')
    rows.append({'test': ctx.tr('Kolmogorov–Smirnov (estimated parameters, approximate)',
                                'Kolmogorov–Smirnov (parametri stimati, approssimato)'),
                 'statistic': ks, 'p': pks, ctx.tr('verdict', 'esito'): yes if pks >= a else no})
    r = ctx.result()
    r.value('N', n)
    r.value(ctx.tr('skewness', 'asimmetria'), stats.skew(v, bias=False))
    r.value(ctx.tr('excess kurtosis', 'curtosi in eccesso'), stats.kurtosis(v, bias=False))
    r.table(ctx.tr('Normality tests', 'Test di normalità'), rows)
    (osm, osr), (slope, intercept, rr) = stats.probplot(v, dist='norm')
    qq = pd.DataFrame({ctx.tr('theoretical quantiles', 'quantili teorici'): osm,
                       ctx.tr('ordered values', 'valori ordinati'): osr,
                       ctx.tr('normal line', 'retta normale'): slope * osm + intercept})
    cols = list(qq.columns)
    r.data(qq, name=f'Q–Q · {p["y"]}', plot={'kind': 'line', 'x': cols[0], 'y': cols[1:],
                                             'series': {cols[1]: {'linestyle': 'none', 'marker': 'o'},
                                                        cols[2]: {'linestyle': '--'}}})
    return r
