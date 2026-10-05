"""Correlation coefficients with p-values (Pearson, Spearman, Kendall) for pairs of columns."""
import itertools

import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'correlation',
    'order': 40,
    'name': {'en': 'Correlation (Pearson, Spearman, Kendall)', 'it': 'Correlazione (Pearson, Spearman, Kendall)'},
    'category': 'stats',
    'description': {'en': 'Correlation matrix with p-values and confidence intervals.',
                    'it': 'Matrice di correlazione con p-value e intervalli di confidenza.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'columns', 'type': 'columns', 'default': 'ys', 'min_count': 2, 'label': {'en': 'Columns', 'it': 'Colonne'}},
        {'id': 'method', 'type': 'choice', 'default': 'pearson', 'label': {'en': 'Coefficient', 'it': 'Coefficiente'},
         'choices': [{'value': 'pearson', 'label': 'Pearson r'}, {'value': 'spearman', 'label': 'Spearman ρ'},
                     {'value': 'kendall', 'label': 'Kendall τ'}]},
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}


def run(df, p, ctx):
    from scipy import stats
    cols = p['columns']
    data = pd.DataFrame({c: ctx.numeric(df, c, dropna=False) for c in cols})
    fn = {'pearson': stats.pearsonr, 'spearman': stats.spearmanr, 'kendall': stats.kendalltau}[p['method']]
    rows = []
    mat = pd.DataFrame(np.eye(len(cols)), index=cols, columns=cols)
    for a, b in itertools.combinations(cols, 2):
        pair = data[[a, b]].dropna()
        if len(pair) < 3:
            continue
        res = fn(pair[a], pair[b])
        coef = float(res.statistic)
        row = {'A': a, 'B': b, 'N': len(pair), ctx.tr('coefficient', 'coefficiente'): coef, 'p': float(res.pvalue)}
        if p['method'] == 'pearson':
            ci = res.confidence_interval(0.95)
            row.update({'CI 95% low': ci.low, 'CI 95% high': ci.high})
        rows.append(row)
        mat.loc[a, b] = mat.loc[b, a] = coef
    r = ctx.result()
    r.table(ctx.tr('Pairs', 'Coppie'), rows)
    r.table(ctx.tr('Matrix', 'Matrice'), mat.round(4), index=True)
    r.data(data, name=f'{p["method"]} correlation', plot={'kind': 'corr', 'y': cols})
    return r
