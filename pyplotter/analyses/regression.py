"""Linear models with statsmodels: multiple regression, ANOVA tables and robust errors via R-style formulas."""
import keyword

import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'regression',
    'order': 50,
    'name': {'en': 'Linear regression & ANOVA (statsmodels)', 'it': 'Regressione lineare e ANOVA (statsmodels)'},
    'category': 'stats',
    'description': {'en': 'OLS with one or more predictors or a formula such as y ~ x + C(group) + x:C(group); '
                          'coefficients, p-values, R², AIC, ANOVA table, diagnostics.',
                    'it': 'Minimi quadrati con uno o più predittori o una formula come y ~ x + C(gruppo) + x:C(gruppo); '
                          'coefficienti, p-value, R², AIC, tabella ANOVA, diagnostica.'},
    'requires': ['statsmodels'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Response (Y)', 'it': 'Risposta (Y)'}},
        {'id': 'predictors', 'type': 'columns', 'optional': True, 'default': 'xs',
         'label': {'en': 'Predictors', 'it': 'Predittori'}},
        {'id': 'formula', 'type': 'text', 'default': '',
         'label': {'en': 'or a formula (overrides the above)', 'it': 'oppure una formula (ha la precedenza)'},
         'help': {'en': 'Use Q("name with spaces") for column names that are not identifiers; C(col) for categories.',
                  'it': 'Usa Q("nome con spazi") per nomi di colonna non validi; C(col) per le categorie.'}},
        {'id': 'robust', 'type': 'choice', 'default': 'nonrobust', 'label': {'en': 'Standard errors', 'it': 'Errori standard'},
         'choices': [{'value': 'nonrobust', 'label': {'en': 'classical', 'it': 'classici'}},
                     {'value': 'HC3', 'label': {'en': 'robust (HC3)', 'it': 'robusti (HC3)'}}]},
        {'id': 'anova', 'type': 'bool', 'default': True, 'label': {'en': 'ANOVA table (type II)', 'it': 'Tabella ANOVA (tipo II)'}},
    ],
    'references': [
        'Seabold, S. & Perktold, J. statsmodels: Econometric and statistical modeling with Python. '
        'Proc. 9th Python in Science Conf. 92–96 (2010). doi:10.25080/Majora-92bf1922-011',
    ],
}


def term(name):
    return name if name.isidentifier() and not keyword.iskeyword(name) else 'Q("{}")'.format(name.replace('"', '\\"'))


def run(df, p, ctx):
    import statsmodels.formula.api as smf
    import statsmodels.api as sm
    from statsmodels.stats.stattools import durbin_watson, jarque_bera

    formula = p['formula'].strip()
    if not formula:
        preds = [c for c in (p['predictors'] or []) if c != p['y']]
        if not preds:
            raise ValueError(ctx.tr('Choose predictors or write a formula.', 'Scegli i predittori o scrivi una formula.'))
        parts = [f'C({term(c)})' if not pd.api.types.is_numeric_dtype(df[c]) else term(c) for c in preds]
        formula = f'{term(p["y"])} ~ ' + ' + '.join(parts)
    model = smf.ols(formula, data=df, missing='drop')
    fit = model.fit(cov_type=p['robust'])
    r = ctx.result()
    r.text(formula)
    coef = pd.DataFrame({ctx.tr('estimate', 'stima'): fit.params, ctx.tr('std. error', 'errore std.'): fit.bse,
                         't': fit.tvalues, 'p': fit.pvalues,
                         'CI 95% low': fit.conf_int()[0], 'CI 95% high': fit.conf_int()[1]})
    r.table(ctx.tr('Coefficients', 'Coefficienti'), coef, index=True)
    r.value('N', int(fit.nobs))
    r.value('R²', fit.rsquared)
    r.value(ctx.tr('adjusted R²', 'R² corretto'), fit.rsquared_adj)
    r.value('F', fit.fvalue)
    r.value('p (F)', fit.f_pvalue)
    r.value('AIC', fit.aic)
    r.value('BIC', fit.bic)
    r.value(ctx.tr('residual std. error', 'errore std. dei residui'), np.sqrt(fit.scale))
    r.value('Durbin–Watson', durbin_watson(fit.resid))
    jb, jbp, _, _ = jarque_bera(fit.resid)
    r.value(ctx.tr('Jarque–Bera normality of residuals, p', 'normalità dei residui Jarque–Bera, p'), jbp)
    if p['anova']:
        try:
            table = sm.stats.anova_lm(model.fit(), typ=2)
            r.table(ctx.tr('ANOVA (type II)', 'ANOVA (tipo II)'), table, index=True)
        except Exception as exc:
            r.text(ctx.tr('ANOVA table not available: ', 'Tabella ANOVA non disponibile: ') + str(exc))
    data = pd.DataFrame({ctx.tr('fitted', 'valori stimati'): fit.fittedvalues,
                         ctx.tr('residual', 'residuo'): fit.resid,
                         ctx.tr('observed', 'osservato'): model.endog})
    cols = list(data.columns)
    r.data(data, name='OLS', plot={'kind': 'scatter', 'x': cols[0], 'y': [cols[2]],
                                   'text': {'xlabel': cols[0], 'ylabel': cols[2]}})
    return r
