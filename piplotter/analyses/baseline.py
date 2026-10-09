"""Baseline of a spectrum or signal: anchor points clicked on the figure, or an automatic estimate.

The baseline, the anchor points and the corrected signal (signal − baseline) are drawn on the figure;
the corrected data can be plotted and analysed. Peak finding, Peak fit and Integral offer the same
baseline, so it is defined once and then used by the analysis itself.
"""
import numpy as np
import pandas as pd

from piplotter import baselines

PLUGIN = {
    'id': 'baseline',
    'order': 25,
    'name': {'en': 'Baseline', 'it': 'Linea di base'},
    'category': 'signal',
    'description': {'en': 'Defines the baseline of a spectrum or signal — points clicked on the figure or an automatic '
                          'method — and subtracts it. Peak finding, Peak fit and Integral then use the same baseline.',
                    'it': 'Definisce la linea di base di uno spettro o segnale — punti cliccati sulla figura o un metodo '
                          'automatico — e la sottrae. Ricerca dei picchi, Fit dei picchi e Integrale usano poi la stessa linea.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        *baselines.params(default='poly'),
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}


def run(df, p, ctx):
    x, y = ctx.xy(df, p['x'], p['y'])
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    b = ctx.baseline(x, y, p)
    corrected = y - b.values
    r = ctx.result()
    r.value(ctx.tr('baseline', 'linea di base'), b.label)
    r.value(ctx.tr('peaks point', 'picchi rivolti'), ctx.tr('down (baseline above the signal)', 'in giù (linea sopra il segnale)')
            if b.down else ctx.tr('up (baseline under the signal)', 'in su (linea sotto il segnale)'))
    side = ctx.tr('above', 'sopra') if b.down else ctx.tr('under', 'sotto')
    r.value(ctx.tr(f'points clearly {side} the baseline', f'punti chiaramente {side} la linea di base'),
            100 * b.below, unit='%', key='below')
    if b.below > 0.05:
        r.text(ctx.tr(f'More than 5 % of the points are {side} the baseline: there it cuts into the signal '
                      '(move or add anchor points, choose a flatter shape, or check which way the peaks point).',
                      f'Oltre il 5 % dei punti è {side} la linea di base: lì taglia il segnale '
                      '(sposta o aggiungi punti di ancoraggio, scegli una forma più piatta, o controlla il verso dei picchi).'))
    r.text(ctx.tr('Next: Peak finding, Peak fit or Integral use this baseline (it is already selected there).',
                  'Poi: Ricerca dei picchi, Fit dei picchi o Integrale usano questa linea di base (vi è già selezionata).'))
    r.cite(*b.refs)

    xname = p['x'] or 'index'
    base_name = ctx.tr('baseline', 'linea di base')
    corr_name = f'{p["y"]} − ' + base_name
    if b.anchors is not None:
        r.table(ctx.tr('Anchor points', 'Punti di ancoraggio'),
                pd.DataFrame({'x': b.anchors[:, 0], 'y': b.anchors[:, 1]}))
    r.overlay(pd.DataFrame({xname: x, base_name: b.values}), xname, base_name, label=base_name,
              style={'linestyle': '--', 'linewidth': 1.0})
    if b.anchors is not None:
        anchor_name = ctx.tr('anchor points', 'punti di ancoraggio')
        r.overlay(pd.DataFrame({xname: b.anchors[:, 0], anchor_name: b.anchors[:, 1]}), xname, anchor_name,
                  label=anchor_name, style={'linestyle': 'none', 'marker': 'o', 'markersize': 3.5})
    r.overlay(pd.DataFrame({xname: x, corr_name: corrected}), xname, corr_name, label=corr_name,
              style={'linewidth': 0.9})
    r.data(pd.DataFrame({xname: x, p['y']: y, base_name: b.values, corr_name: corrected}),
           name=corr_name, plot={'kind': 'line', 'x': xname, 'y': [corr_name]})
    return r
