"""Descriptive statistics of one or more columns (pandas + scipy.stats)."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'descriptive',
    'order': 10,
    'name': {'en': 'Descriptive statistics', 'it': 'Statistica descrittiva'},
    'category': 'stats',
    'description': {'en': 'N, mean, SD, SEM, confidence interval, median, quartiles, skewness, kurtosis…',
                    'it': 'N, media, DS, SEM, intervallo di confidenza, mediana, quartili, asimmetria, curtosi…'},
    'requires': ['scipy'],
    'params': [
        {'id': 'columns', 'type': 'columns', 'default': 'ys', 'label': {'en': 'Columns', 'it': 'Colonne'}},
        {'id': 'group', 'type': 'column', 'optional': True, 'default': 'hue',
         'label': {'en': 'Split by group (optional)', 'it': 'Separa per gruppo (facoltativo)'}},
        {'id': 'conf', 'type': 'float', 'default': 0.95, 'min': 0.5, 'max': 0.999,
         'label': {'en': 'Confidence level', 'it': 'Livello di confidenza'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. '
        'Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def describe(v, conf, tr):
    from scipy import stats
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = v.size
    if n == 0:
        return {}
    mean, sd = v.mean(), v.std(ddof=1) if n > 1 else np.nan
    sem = sd / np.sqrt(n) if n > 1 else np.nan
    half = stats.t.ppf(0.5 + conf / 2, n - 1) * sem if n > 1 else np.nan
    q1, med, q3 = np.percentile(v, [25, 50, 75])
    return {'N': n, tr('mean', 'media'): mean, tr('SD', 'DS'): sd, 'SEM': sem,
            f'CI{conf:.0%} low': mean - half, f'CI{conf:.0%} high': mean + half,
            tr('median', 'mediana'): med, 'Q1': q1, 'Q3': q3, 'IQR': q3 - q1,
            'min': v.min(), 'max': v.max(), tr('CV %', 'CV %'): sd / mean * 100 if mean else np.nan,
            tr('skewness', 'asimmetria'): stats.skew(v, bias=False) if n > 2 else np.nan,
            tr('excess kurtosis', 'curtosi in eccesso'): stats.kurtosis(v, bias=False) if n > 3 else np.nan}


def run(df, p, ctx):
    rows = []
    for col in p['columns']:
        values = ctx.numeric(df, col, dropna=False)
        if p['group']:
            for g, sub in values.groupby(df[p['group']], sort=True):
                rows.append({ctx.tr('column', 'colonna'): col, ctx.tr('group', 'gruppo'): g,
                             **describe(sub, p['conf'], ctx.tr)})
        else:
            rows.append({ctx.tr('column', 'colonna'): col, **describe(values, p['conf'], ctx.tr)})
        missing = int(values.isna().sum())
        if missing:
            ctx_note = ctx.tr(f'{col}: {missing} missing or non-numeric values ignored.',
                              f'{col}: {missing} valori mancanti o non numerici ignorati.')
            rows[-1]['note'] = ctx_note
    table = pd.DataFrame(rows)
    r = ctx.result()
    r.table(ctx.tr('Descriptive statistics', 'Statistica descrittiva'), table)
    r.data(table, name='statistics', plot={'kind': 'bar', 'x': table.columns[1] if p['group'] else table.columns[0],
                                           'y': [ctx.tr('mean', 'media')]})
    return r
