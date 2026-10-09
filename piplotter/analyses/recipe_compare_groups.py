"""Recipe: are the groups different?

Steps: 1. descriptive statistics per group, 2. Compare groups with automatic test choice (normality of
each group by Shapiro–Wilk → Welch t-test / ANOVA, otherwise Mann–Whitney / Kruskal–Wallis; post-hoc
tests and effect size), 3. a plain-language conclusion; box plot of the groups.
"""
PLUGIN = {
    'id': 'recipe_compare_groups',
    'order': 30,
    'name': {'en': 'Are the groups different?', 'it': 'I gruppi sono diversi?'},
    'category': 'recipe',
    'description': {'en': 'Statistics per group and the right test chosen automatically, with effect size and '
                          'pairwise comparisons.',
                    'it': 'Statistiche per gruppo e il test giusto scelto in automatico, con effect size e confronti '
                          'a coppie.'},
    'steps': [
        {'en': 'Descriptive statistics of each group', 'it': 'Statistica descrittiva di ogni gruppo'},
        {'en': 'Normality of each group → parametric or rank test', 'it': 'Normalità di ogni gruppo → test parametrico o sui ranghi'},
        {'en': 'Test, effect size and pairwise comparisons', 'it': 'Test, effect size e confronti a coppie'},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'value', 'type': 'column', 'default': 'y', 'label': {'en': 'Values', 'it': 'Valori'}},
        {'id': 'group', 'type': 'column', 'default': 'x', 'label': {'en': 'Group column', 'it': 'Colonna dei gruppi'}},
        {'id': 'alpha', 'type': 'float', 'default': 0.05, 'min': 0.001, 'max': 0.5,
         'label': {'en': 'Significance level α', 'it': 'Livello di significatività α'}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    if p['value'] == p['group']:
        raise ValueError(ctx.tr('Choose different columns for values and groups.',
                                'Scegli colonne diverse per valori e gruppi.'))
    step = ctx.tr('Step', 'Passo')
    desc = ctx.run('descriptive', df, columns=[p['value']], group=p['group'])
    test = ctx.run('compare_groups', df, value=p['value'], group=p['group'], columns=[], test='auto', alpha=p['alpha'])

    pval, sig = test.get('p'), test.get('significant')
    r = ctx.result()
    r.value(ctx.tr('groups', 'gruppi'), test.get('k'))
    r.value(ctx.tr('groups compatible with normal', 'gruppi compatibili con la normale'),
            ctx.tr('yes', 'sì') if test.get('groups_normal') else 'no')
    r.value(ctx.tr('test chosen', 'test scelto'), test.get('test'), key='test')
    r.value('p', pval, key='p')
    if test.get('effect') is not None:
        r.value(ctx.tr('effect size', 'effect size') + f' ({test.get("effect_name")})', test.get('effect'), key='effect')
    a = p['alpha']
    ptxt = 'p < 0.001' if pval < 1e-3 else f'p = {pval:.3g}'
    r.text(ctx.tr(f'The groups differ significantly ({ptxt}, α = {a:g}).' if sig else
                  f'No significant difference between the groups ({ptxt}, α = {a:g}).',
                  f'I gruppi differiscono in modo significativo ({ptxt}, α = {a:g}).' if sig else
                  f'Nessuna differenza significativa tra i gruppi ({ptxt}, α = {a:g}).'))
    if sig and (test.get('k') or 0) > 2:
        r.text(ctx.tr('Which groups differ: see the pairwise table of step 2.',
                      'Quali gruppi differiscono: vedi la tabella a coppie del passo 2.'))
    r.include(desc, f'{step} 1 · ' + ctx.tr('descriptive statistics', 'statistica descrittiva'))
    r.include(test, f'{step} 2 · ' + ctx.tr('test', 'test'))
    r.data(test.frame, name=ctx.tr('groups', 'gruppi'), plot=test.plot)
    return r
