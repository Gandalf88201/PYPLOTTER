"""Recipe: where does a simulation reach equilibrium, and what is the equilibrium average?

Steps: 1. for each possible start t₀ the statistical inefficiency g of the rest of the series is computed
and the start that keeps the most independent samples, (N − t₀)/g, is chosen (Chodera 2016),
2. block averaging of the equilibrated part gives the mean with its true error. The start of equilibrium
and the mean ± 2 SEM are drawn on the figure.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'recipe_equilibration',
    'order': 25,
    'name': {'en': 'Equilibration of a simulation (MD, MC)', 'it': 'Equilibratura di una simulazione (MD, MC)'},
    'category': 'recipe',
    'description': {'en': 'Finds automatically where the series is equilibrated and gives the average of the '
                          'equilibrated part with its true error.',
                    'it': 'Trova in automatico da dove la serie è equilibrata e dà la media della parte equilibrata '
                          'con il suo vero errore.'},
    'steps': [
        {'en': 'Start of equilibrium t₀: the one that keeps most independent samples',
         'it': 'Inizio dell’equilibrio t₀: quello che conserva più campioni indipendenti'},
        {'en': 'Block averaging of the equilibrated part', 'it': 'Block averaging della parte equilibrata'},
        {'en': 't₀ and mean ± 2 SEM on the figure', 'it': 't₀ e media ± 2 SEM sulla figura'},
    ],
    'requires': [],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Series (energy, RMSD, density…)',
                                                                 'it': 'Serie (energia, RMSD, densità…)'}},
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Time column (optional)', 'it': 'Colonna del tempo (facoltativa)'}},
    ],
    'references': [
        'Chodera, J. D. A simple method for automated equilibration detection in molecular simulations. '
        'J. Chem. Theory Comput. 12, 1799–1805 (2016). doi:10.1021/acs.jctc.5b00784',
    ],
}


def inefficiency(a):
    """Statistical inefficiency g = 1 + 2 Σ (1 − t/N) C(t), summed until C(t) first drops to ≤ 0 after
    t = 3 (as in pymbar); vectorised, so long trajectories stay fast."""
    a = np.asarray(a, float) - np.mean(a)
    n = a.size
    var = a.var()
    if n < 4 or var == 0:
        return 1.0
    f = np.fft.rfft(a, 2 * n)
    acov = np.fft.irfft(f * np.conj(f))[:n] / np.arange(n, 0, -1)
    c = acov[1:n - 1] / var                       # C(t) for t = 1 … n−2
    t = np.arange(1, n - 1)
    stop = np.nonzero((c <= 0) & (t > 3))[0]
    m = stop[0] if stop.size else c.size          # number of terms summed
    return max(1.0, 1.0 + 2.0 * float(np.sum(c[:m] * (1 - t[:m] / n))))


def run(df, p, ctx):
    t, y = ctx.xy(df, p['x'], p['y'])
    note = None
    if p['x'] and np.any(np.diff(t) < 0):        # not a time axis: rows in their order
        note = ctx.tr(f'“{p["x"]}” does not increase steadily, so it is not used as time: rows are counted instead.',
                      f'«{p["x"]}» non cresce in modo regolare, quindi non è usata come tempo: conto le righe.')
        p = {**p, 'x': None}
        t, y = ctx.xy(df, None, p['y'])
    n = y.size
    if n < 40:
        raise ValueError(ctx.tr('At least 40 values are needed.', 'Servono almeno 40 valori.'))
    starts = np.unique(np.linspace(0, n // 2, min(n // 2 + 1, 200)).astype(int))
    g = np.array([inefficiency(y[s:]) for s in starts])
    neff = (n - starts) / g
    best = int(np.argmax(neff))
    t0 = int(starts[best])
    tname = p['x'] or 'index'
    t0x = float(t[t0])

    block = ctx.run('block_average', df, y=p['y'], x=p['x'], discard=(t0 + 0.5) / n * 100)
    unit = f' {p["x"]}' if p['x'] else ''
    r = ctx.result()
    r.value(ctx.tr('start of equilibrium t₀', 'inizio dell’equilibrio t₀'), t0x, None, (p['x'] or ctx.tr('row', 'riga')), key='t0')
    r.value(ctx.tr('discarded (equilibration)', 'scartato (equilibratura)'), 100 * t0 / n, None, '%', key='discarded')
    r.value(ctx.tr('equilibrium mean ± true error', 'media all’equilibrio ± vero errore'), block.get('mean'),
            block.get('sem'), key='mean')
    r.value(ctx.tr('statistical inefficiency g', 'inefficienza statistica g'), float(g[best]), key='g')
    r.value(ctx.tr('independent samples', 'campioni indipendenti'), float(neff[best]), key='n_eff')
    if note:
        r.text(note)
    if t0 == 0:
        r.text(ctx.tr('No initial transient: the whole series is already at equilibrium.',
                      'Nessun transitorio iniziale: tutta la serie è già all’equilibrio.'))
    elif t0 >= starts[-1] * 0.9:
        r.text(ctx.tr('t₀ is close to the middle of the series: it may not be equilibrated yet — run longer.',
                      't₀ è vicino a metà della serie: potrebbe non essere ancora equilibrata — prolunga la simulazione.'))
    else:
        r.text(ctx.tr(f'Discard the first {100 * t0 / n:.1f}% (up to{unit} {t0x:.6g}) and average the rest: '
                      f'{block.get("mean"):.6g} ± {block.get("sem"):.2g}.',
                      f'Scarta il primo {100 * t0 / n:.1f}% (fino a{unit} {t0x:.6g}) e fai la media del resto: '
                      f'{block.get("mean"):.6g} ± {block.get("sem"):.2g}.'))

    step = ctx.tr('Step', 'Passo')
    marker = ctx.tr('start of equilibrium', 'inizio equilibrio')
    line = pd.DataFrame({tname: [t0x, t0x], marker: [float(np.min(y)), float(np.max(y))]})
    r.overlay(line, tname, marker, label=f'{marker} (t₀)', style={'linestyle': ':', 'color': '#666666'})
    r.include(block, f'{step} 2 · block averaging', overlays=True)
    if note or (not p['x'] and (ctx.spec or {}).get('x')):     # row numbers would not match the figure's x
        for o in r.overlays:
            o['on_figure'] = False
    scan = pd.DataFrame({'t₀': t[starts], 'g': g, ctx.tr('independent samples', 'campioni indipendenti'): neff})
    r.table(f'{step} 1 · ' + ctx.tr('scan of t₀', 'scansione di t₀'), scan)
    ny = scan.columns[2]
    r.data(scan, name=ctx.tr('equilibration scan', 'scansione equilibratura') + f' · {p["y"]}', plot={
        'kind': 'line', 'x': 't₀', 'y': [ny],
        'text': {'xlabel': f't₀ ({p["x"] or ctx.tr("row", "riga")})', 'ylabel': ny}})
    return r
