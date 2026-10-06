"""Recipe: how does Y depend on X?

Steps: 1. Pearson and Spearman correlation, 2. straight-line fit with its 95 % confidence band (drawn on
the figure), 3. normality of the residuals (are the line's errors trustworthy?).
"""
import pandas as pd

PLUGIN = {
    'id': 'recipe_xy_relation',
    'order': 40,
    'name': {'en': 'Relation between two variables', 'it': 'Relazione tra due variabili'},
    'category': 'recipe',
    'description': {'en': 'Correlation, straight line with confidence band and a check of the residuals.',
                    'it': 'Correlazione, retta con banda di confidenza e verifica dei residui.'},
    'steps': [
        {'en': 'Correlation: Pearson r (linear) and Spearman ρ (monotonic)',
         'it': 'Correlazione: Pearson r (lineare) e Spearman ρ (monotona)'},
        {'en': 'Straight-line fit y = a·x + b with 95% band, on the figure',
         'it': 'Retta y = a·x + b con banda al 95%, sulla figura'},
        {'en': 'Normality of the residuals', 'it': 'Normalità dei residui'},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'default': 'x', 'label': {'en': 'X', 'it': 'X'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Y', 'it': 'Y'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    if p['x'] == p['y']:
        raise ValueError(ctx.tr('Choose two different columns.', 'Scegli due colonne diverse.'))
    step = ctx.tr('Step', 'Passo')
    pear = ctx.run('correlation', df, columns=[p['x'], p['y']], method='pearson')
    spear = ctx.run('correlation', df, columns=[p['x'], p['y']], method='spearman')
    fit = ctx.run('fit_curve', df, source='xy', x=p['x'], y=p['y'], sigma=None, model='linear', band='confidence')
    resid_name = fit.get('resid_column')
    resid = ctx.run('normality', pd.DataFrame({resid_name: fit.frame[resid_name]}), y=resid_name)

    r = ctx.result()
    r.value('N', pear.get('n'))
    r.value('Pearson r', pear.get('coef'), key='pearson_r')
    r.value('Pearson p', pear.get('p'), key='pearson_p')
    r.value('Spearman ρ', spear.get('coef'), key='spearman_rho')
    r.value('Spearman p', spear.get('p'), key='spearman_p')
    r.value(ctx.tr('slope a', 'pendenza a'), fit.get('a'), fit.error('a'), key='slope')
    r.value(ctx.tr('intercept b', 'intercetta b'), fit.get('b'), fit.error('b'), key='intercept')
    r.value('R²', fit.get('r2'), key='r2')
    r.value(ctx.tr('residuals compatible with normal', 'residui compatibili con la normale'),
            ctx.tr('yes', 'sì') if resid.get('normal') else 'no')

    rp, pp, rs = pear.get('coef'), pear.get('p'), spear.get('coef')
    strength = abs(rp)
    words = (ctx.tr('very weak', 'molto debole') if strength < 0.2 else ctx.tr('weak', 'debole') if strength < 0.4
             else ctx.tr('moderate', 'moderata') if strength < 0.6 else ctx.tr('strong', 'forte') if strength < 0.8
             else ctx.tr('very strong', 'molto forte'))
    sign = ctx.tr('positive', 'positiva') if rp > 0 else ctx.tr('negative', 'negativa')
    ptxt = 'p < 0.001' if pp < 1e-3 else f'p = {pp:.2g}'
    if pp < 0.05:
        r.text(ctx.tr(f'{words.capitalize()} {sign} linear relation (r = {rp:.3f}, {ptxt}).',
                      f'Relazione lineare {sign} {words} (r = {rp:.3f}, {ptxt}).'))
    else:
        r.text(ctx.tr(f'No significant linear relation (r = {rp:.3f}, {ptxt}).',
                      f'Nessuna relazione lineare significativa (r = {rp:.3f}, {ptxt}).'))
    if abs(rs) - abs(rp) > 0.1:
        r.text(ctx.tr('Spearman ρ is clearly larger than Pearson r: the relation is monotonic but not straight '
                      '(try a curve in Curve fitting).',
                      'Spearman ρ è chiaramente maggiore di Pearson r: la relazione è monotona ma non rettilinea '
                      '(prova una curva in «Fit di curve»).'))
    if not resid.get('normal'):
        r.text(ctx.tr('The residuals are not normal: the errors on slope and intercept are approximate.',
                      'I residui non sono normali: gli errori su pendenza e intercetta sono approssimati.'))

    r.include(pear, f'{step} 1 · Pearson')
    r.include(spear, f'{step} 1 · Spearman')
    first = r.include(fit, f'{step} 2 · ' + ctx.tr('straight line', 'retta'), overlays=True)
    r.include(resid, f'{step} 3 · ' + ctx.tr('residuals', 'residui'))
    r.data(fit.frame, name=ctx.tr('line fit', 'retta') + f' · {p["y"]}',
           plot={**fit.plot, 'overlays': [{'ref': first}]})
    return r
