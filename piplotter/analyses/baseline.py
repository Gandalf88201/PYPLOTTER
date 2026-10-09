"""Baseline of a spectrum or signal: anchor points clicked on the figure, or an automatic estimate.

The result is the corrected spectrum, drawn on its own (flat at 0, or at 100 % for transmittance) with
the level of the corrected baseline; on request also the spectrum before the correction, with its
baseline and anchor points. The correction subtracts the baseline, or — for transmittance, whose
baseline lies above the dips — divides by it (T / T₀), so the corrected spectrum stays in % with its
bands as deep as before. Peak finding, Peak fit and Integral offer the same baseline, so it is defined
once and then used by the analysis itself.
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
        {'id': 'correction', 'type': 'choice', 'default': 'auto',
         'label': {'en': 'Correction', 'it': 'Correzione'},
         'choices': [{'value': 'auto', 'label': {'en': 'automatic (divide transmittance, subtract otherwise)',
                                                 'it': 'automatica (divide la trasmittanza, altrimenti sottrae)'}},
                     {'value': 'subtract', 'label': {'en': 'subtract: signal − baseline', 'it': 'sottrai: segnale − linea di base'}},
                     {'value': 'divide', 'label': {'en': 'divide: signal / baseline (T / T₀)', 'it': 'dividi: segnale / linea di base (T / T₀)'}}]},
        {'id': 'show_original', 'type': 'bool', 'default': False,
         'label': {'en': 'Also show the spectrum before the correction, with its baseline',
                   'it': 'Mostra anche lo spettro prima della correzione, con la sua linea di base'}},
    ],
    'references': ['Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2'],
}


def divides(p, b, y):
    """True when the baseline is divided out: asked for, or automatic for dips under a baseline well above zero
    (transmittance, reflectance), where T / T₀ keeps the spectrum in its own units."""
    if p.get('correction') == 'divide':
        return True
    if p.get('correction') == 'subtract':
        return False
    top = float(np.nanmax(np.abs(y))) or 1.0
    return bool(b.down and np.min(b.values) > 0.5 * top)


def run(df, p, ctx):
    x, y = ctx.xy(df, p['x'], p['y'])
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    b = ctx.baseline(x, y, p)
    divide = divides(p, b, y)
    if divide:
        if np.any(np.abs(b.values) < 1e-12 * (float(np.nanmax(np.abs(y))) or 1.0)):
            raise ValueError(ctx.tr('The baseline reaches zero: it cannot be divided out; choose “subtract”.',
                                    'La linea di base arriva a zero: non si può dividere; scegli “sottrai”.'))
        scale = 100.0 if np.nanmax(np.abs(y)) > 1.5 else 1.0       # % stays %, a 0–1 fraction stays a fraction
        corrected, level = scale * y / b.values, scale
    else:
        corrected, level = y - b.values, 0.0

    r = ctx.result()
    r.value(ctx.tr('baseline', 'linea di base'), b.label)
    r.value(ctx.tr('peaks point', 'picchi rivolti'), ctx.tr('down (baseline above the signal)', 'in giù (linea sopra il segnale)')
            if b.down else ctx.tr('up (baseline under the signal)', 'in su (linea sotto il segnale)'))
    r.value(ctx.tr('correction', 'correzione'),
            (ctx.tr(f'divided by the baseline (× {level:g}: corrected baseline at {level:g})',
                    f'divisa per la linea di base (× {level:g}: linea corretta a {level:g})') if divide else
             ctx.tr('baseline subtracted (corrected baseline at 0)', 'linea di base sottratta (linea corretta a 0)')))
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
    corr_name = f'{p["y"]} ' + ctx.tr('(baseline-corrected)', '(corretta)')
    level_name = ctx.tr('corrected baseline', 'linea di base corretta')
    if b.anchors is not None:
        r.table(ctx.tr('Anchor points', 'Punti di ancoraggio'),
                pd.DataFrame({'x': b.anchors[:, 0], 'y': b.anchors[:, 1]}))
    show = bool(p.get('show_original'))
    # Without the spectrum before the correction, the layers belong only to the result's own figure, so the
    # corrected spectrum is drawn alone (“Plot the result”); with it, they also go on a copy of the figure.
    refs = [r.overlay(pd.DataFrame({xname: x[[0, -1]], level_name: [level, level]}), xname, level_name,
                      label=level_name, style={'linestyle': ':', 'linewidth': 1.0}, on_figure=False)]
    series = [corr_name]
    if show:
        refs.append(r.overlay(pd.DataFrame({xname: x, base_name: b.values}), xname, base_name, label=base_name,
                              style={'linestyle': '--', 'linewidth': 1.0}))
        if b.anchors is not None:
            anchor_name = ctx.tr('anchor points', 'punti di ancoraggio')
            refs.append(r.overlay(pd.DataFrame({xname: b.anchors[:, 0], anchor_name: b.anchors[:, 1]}), xname, anchor_name,
                                  label=anchor_name, style={'linestyle': 'none', 'marker': 'o', 'markersize': 3.5}))
        r.overlay(pd.DataFrame({xname: x, corr_name: corrected}), xname, corr_name, label=corr_name,
                  style={'linewidth': 0.9})
        series = [p['y'], corr_name]
    r.data(pd.DataFrame({xname: x, p['y']: y, base_name: b.values, corr_name: corrected}),
           name=corr_name, plot={'kind': 'line', 'x': xname, 'y': series, 'overlays': [{'ref': k} for k in refs]})
    return r
