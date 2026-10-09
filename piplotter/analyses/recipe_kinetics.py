"""Recipe: reaction kinetics — order, rate constant and half-life.

Steps: 1. the decay (or growth) of a concentration or signal is fitted with the integrated rate laws of
zero, first and second order (Curve fitting), 2. the order with the lowest AIC is chosen (or the one you
set), 3. rate constant k and half-life t½ with errors; the chosen curve is drawn on the figure.

  zero order    y = A₀ − k·(t − t₀)                 t½ = A₀ / (2k)
  first order   y = A·exp(−k·(t − t₀)) + C          t½ = ln 2 / k
  second order  y = A / (1 + A·k·(t − t₀)) + C      t½ = 1 / (k·A)
(t₀ = first measured time, A₀ = initial value, A = initial amplitude above the final value C.)
Time is counted from t₀, so data recorded on any clock (t = 100…160 s) give the same k as data from 0.
k is reported as a positive rate also when the signal grows (a product forming).
"""
import numpy as np

PLUGIN = {
    'id': 'recipe_kinetics',
    'order': 60,
    'name': {'en': 'Reaction kinetics (order, k, t½)', 'it': 'Cinetica di reazione (ordine, k, t½)'},
    'category': 'recipe',
    'description': {'en': 'Zero, first and second order compared on the same data: the best order, the rate constant '
                          'and the half-life with errors.',
                    'it': 'Ordine zero, uno e due confrontati sugli stessi dati: l’ordine migliore, la costante di '
                          'velocità e il tempo di dimezzamento con errori.'},
    'steps': [
        {'en': 'Fit of the integrated rate laws of order 0, 1 and 2',
         'it': 'Fit delle leggi cinetiche integrate di ordine 0, 1 e 2'},
        {'en': 'Choice of the order (lowest AIC)', 'it': 'Scelta dell’ordine (AIC minimo)'},
        {'en': 'Rate constant k and half-life t½; curve on the figure',
         'it': 'Costante di velocità k e tempo di dimezzamento t½; curva sulla figura'},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'default': 'x', 'label': {'en': 'Time', 'it': 'Tempo'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Concentration or signal', 'it': 'Concentrazione o segnale'}},
        {'id': 'sigma', 'type': 'column', 'optional': True, 'default': 'yerr',
         'label': {'en': 'Error of y (weights, optional)', 'it': 'Errore di y (pesi, facoltativo)'}},
        {'id': 'order', 'type': 'choice', 'default': 'auto', 'label': {'en': 'Order', 'it': 'Ordine'},
         'choices': [{'value': 'auto', 'label': {'en': 'best by AIC', 'it': 'il migliore per AIC'}},
                     {'value': '0', 'label': {'en': 'zero', 'it': 'zero'}},
                     {'value': '1', 'label': {'en': 'first', 'it': 'primo'}},
                     {'value': '2', 'label': {'en': 'second', 'it': 'secondo'}}]},
    ],
    'references': [
        'Akaike, H. A new look at the statistical model identification. IEEE Trans. Autom. Control 19, 716–723 (1974). '
        'doi:10.1109/TAC.1974.1100705',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


def run(df, p, ctx):
    from piplotter.plugins import PluginError
    t, y = ctx.xy(df, p['x'], p['y'])
    order_idx = np.argsort(t)
    t, y = t[order_idx], y[order_idx]
    if t.size < 5:
        raise ValueError(ctx.tr('At least 5 points are needed.', 'Servono almeno 5 punti.'))
    span = float(t.max() - t.min()) or 1.0
    t0 = float(t[0])
    dt = f'(x - ({t0!r}))'                      # time since the first measurement
    first, amp, final = float(y[0]), float(y[0] - y[-1]), float(y[-1])
    common = dict(source='xy', x=p['x'], y=p['y'], sigma=p['sigma'], band='confidence', xmin=None, xmax=None)
    setups = {
        '0': dict(model='custom', formula=f'A0 - k*{dt}', p0=f'A0={first!r}, k={float(amp / span)!r}'),
        '1': dict(model='custom', formula=f'A*exp(-k*{dt}) + C', p0=f'A={amp!r}, k={float(3 / span)!r}, C={final!r}'),
        '2': dict(model='custom', formula=f'A/(1 + A*k*{dt}) + C',
                  p0=f'A={amp!r}, k={float(3 / (span * amp)) if amp else 1.0!r}, C={final!r}'),
    }
    wanted = list(setups) if p['order'] == 'auto' else [p['order']]
    fits, failed = {}, {}
    for o in wanted:
        try:
            fits[o] = ctx.run('fit_curve', df, **common, **setups[o])
        except (ValueError, RuntimeError, PluginError) as exc:
            failed[o] = str(exc)[:120]
    if not fits:
        raise ValueError(ctx.tr('No rate law could be fitted: ', 'Nessuna legge cinetica è stata adattata: ')
                         + '; '.join(failed.values()))
    best = min(fits, key=lambda o: fits[o].get('aic') if np.isfinite(fits[o].get('aic') or np.nan) else np.inf)
    fit = fits[best]
    names = {'0': ctx.tr('zero order', 'ordine zero'), '1': ctx.tr('first order', 'primo ordine'),
             '2': ctx.tr('second order', 'secondo ordine')}

    def rate(o, f):
        """k ± error and t½ ± error for one fit (k positive for decay and growth alike)."""
        k, ek = f.get('k'), f.error('k')
        if o == '0':
            a0, ea0 = f.get('A0'), f.error('A0')
            th = a0 / (2 * k) if k else np.nan
            eth = abs(th) * np.hypot(ek / k, ea0 / a0) if k and a0 else np.nan
        elif o == '1':
            th = np.log(2) / k if k else np.nan
            eth = np.log(2) * ek / k ** 2 if k else np.nan
        else:
            a, ea = f.get('A'), f.error('A')
            th = 1 / (k * a) if k and a else np.nan
            eth = abs(th) * np.hypot(ek / k, ea / a) if k and a else np.nan
        return abs(k), ek, abs(th), eth

    k, ek, th, eth = rate(best, fit)
    unit = p['x']
    r = ctx.result()
    r.value(ctx.tr('order', 'ordine'), names[best] + (ctx.tr(' (lowest AIC)', ' (AIC minimo)') if p['order'] == 'auto' else ''),
            key='order')
    k_unit = {'0': f'{p["y"]}/{unit}', '1': f'1/{unit}', '2': f'1/({p["y"]}·{unit})'}[best]
    r.value(ctx.tr('rate constant k', 'costante di velocità k'), k, ek, k_unit, key='k')
    r.value(ctx.tr('half-life t½', 'tempo di dimezzamento t½'), th, eth, unit, key='t_half')
    if best == '1':
        r.value(ctx.tr('lifetime τ = 1/k', 'tempo di vita τ = 1/k'), 1 / k if k else np.nan,
                ek / k ** 2 if k else None, unit, key='tau')
    r.value('R²', fit.get('r2'), key='r2')

    rows = []
    for o, f in fits.items():
        ko, eko, tho, etho = rate(o, f)
        rows.append({ctx.tr('order', 'ordine'): names[o], 'k': ko, '± k': eko, 't½': tho, '± t½': etho,
                     'R²': f.get('r2'), 'AIC': f.get('aic'), 'ΔAIC': f.get('aic') - fit.get('aic')})
    for o, msg in failed.items():
        rows.append({ctx.tr('order', 'ordine'): names[o], 'k': None, 'AIC': None,
                     'note': ctx.tr('did not converge: ', 'non converge: ') + msg})
    r.table(ctx.tr('Rate laws compared', 'Leggi cinetiche a confronto'), rows)

    close = [names[o] for o, f in fits.items() if o != best and f.get('aic') - fit.get('aic') < 2]
    if close:
        r.text(ctx.tr(f'{", ".join(close).capitalize()} fits almost as well (ΔAIC < 2): the data do not decide the order; '
                      'measure longer (beyond 2–3 half-lives) to tell them apart.',
                      f'Anche {", ".join(close)} descrive quasi altrettanto bene (ΔAIC < 2): i dati non decidono l’ordine; '
                      'misura più a lungo (oltre 2–3 tempi di dimezzamento) per distinguerli.'))
    if np.isfinite(th) and span < 2 * abs(th):
        r.text(ctx.tr('The data cover less than two half-lives: k and the order are uncertain.',
                      'I dati coprono meno di due tempi di dimezzamento: k e l’ordine sono incerti.'))
    if y[-1] > y[0]:
        r.text(ctx.tr('The signal grows (product formation): k is the rate of the reaction that forms it.',
                      'Il segnale cresce (formazione di prodotto): k è la velocità della reazione che lo forma.'))

    step = ctx.tr('Step', 'Passo')
    first = r.include(fit, f'{step} 1 · {names[best]}', overlays=True)
    r.overlays[first]['label'] = names[best]
    for o, f in fits.items():
        if o != best:
            r.include(f, f'{step} 1 · {names[o]}')
    r.data(fit.frame, name=ctx.tr('kinetics', 'cinetica') + f' · {p["y"]}',
           plot={**fit.plot, 'overlays': [{'ref': first}]})
    return r
