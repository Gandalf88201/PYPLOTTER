"""Non-linear least-squares curve fitting (scipy.optimize.curve_fit).

Built-in models with automatic starting values, or your own formula such as
``a*exp(-x/tau) + c``. Fits either a column Y against X, or the histogram of one column (e.g. a
Gaussian over the distribution of values); with a histogram figure open, its bins are used and the
curve is drawn on it. Reports parameters ± standard errors, 95 % confidence intervals,
R², adjusted R², RMSE, reduced χ² (with error column), AIC and BIC, and returns the data
with the fitted curve and residuals.
"""
import ast

import numpy as np
import pandas as pd

R_GAS = 8.314462618  # J mol⁻¹ K⁻¹

MODELS = {
    'linear':      ('y = a·x + b', ['a', 'b']),
    'poly2':       ('y = a·x² + b·x + c', ['a', 'b', 'c']),
    'poly3':       ('y = a·x³ + b·x² + c·x + d', ['a', 'b', 'c', 'd']),
    'exp_decay':   ('y = A·exp(−x/τ) + C', ['A', 'tau', 'C']),
    'exp2_decay':  ('y = A₁·exp(−x/τ₁) + A₂·exp(−x/τ₂) + C', ['A1', 'tau1', 'A2', 'tau2', 'C']),
    'stretched':   ('y = A·exp(−(x/τ)^β) + C  (KWW)', ['A', 'tau', 'beta', 'C']),
    'power':       ('y = A·x^n', ['A', 'n']),
    'gaussian':    ('y = A·exp(−(x−μ)²/(2σ²)) + C', ['A', 'mu', 'sigma', 'C']),
    'lorentzian':  ('y = A·γ²/((x−x₀)² + γ²) + C', ['A', 'x0', 'gamma', 'C']),
    'voigt':       ('y = A·V(x−x₀; σ, γ) + C', ['A', 'x0', 'sigma', 'gamma', 'C']),
    'logistic':    ('y = L/(1 + exp(−k(x−x₀))) + C', ['L', 'k', 'x0', 'C']),
    'hill':        ('y = Vmax·xⁿ/(Kⁿ + xⁿ)', ['Vmax', 'K', 'n']),
    'michaelis':   ('y = Vmax·x/(Km + x)', ['Vmax', 'Km']),
    'arrhenius':   ('k = A·exp(−Ea/(R·T)),  x = T in K, Ea in J/mol', ['A', 'Ea']),
    'sine':        ('y = A·sin(2π·f·x + φ) + C', ['A', 'f', 'phi', 'C']),
}

PLUGIN = {
    'id': 'fit_curve',
    'order': 10,
    'name': {'en': 'Curve fitting', 'it': 'Fit di curve'},
    'category': 'fit',
    'description': {'en': 'Least-squares fit of a model or of your own formula, with errors and goodness of fit.',
                    'it': 'Fit ai minimi quadrati di un modello o di una formula a scelta, con errori e bontà del fit.'},
    'requires': ['scipy'],
    'params': [
        {'id': 'source', 'type': 'choice', 'default': 'auto', 'label': {'en': 'Data to fit', 'it': 'Dati da adattare'},
         'choices': [{'value': 'auto', 'label': {'en': 'automatic (histogram if the figure is a histogram)',
                                                 'it': 'automatico (istogramma se il grafico è un istogramma)'}},
                     {'value': 'xy', 'label': {'en': 'column Y against column X', 'it': 'colonna Y in funzione di X'}},
                     {'value': 'hist', 'label': {'en': 'histogram of a column (distribution of its values)',
                                                 'it': 'istogramma di una colonna (distribuzione dei valori)'}}]},
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'show_if': {'source': ['auto', 'xy']},
         'label': {'en': 'X (empty = row number)', 'it': 'X (vuoto = numero di riga)'}},
        {'id': 'y', 'type': 'column', 'default': 'y',
         'label': {'en': 'Y (or the column of the histogram)', 'it': 'Y (o la colonna dell’istogramma)'}},
        {'id': 'bins', 'type': 'int', 'optional': True, 'min': 3, 'max': 2000, 'show_if': {'source': ['auto', 'hist']},
         'label': {'en': 'Histogram bins (empty = as in the figure / automatic)',
                   'it': 'Intervalli dell’istogramma (vuoto = come nel grafico / automatico)'}},
        {'id': 'sigma', 'type': 'column', 'optional': True, 'default': 'yerr', 'show_if': {'source': ['auto', 'xy']},
         'label': {'en': 'Y error (weights, optional)', 'it': 'Errore Y (pesi, facoltativo)'}},
        {'id': 'model', 'type': 'choice', 'default': 'exp_decay', 'label': {'en': 'Model', 'it': 'Modello'},
         'choices': [{'value': k, 'label': v[0]} for k, v in MODELS.items()] +
                    [{'value': 'custom', 'label': {'en': 'Custom formula…', 'it': 'Formula personalizzata…'}}]},
        {'id': 'formula', 'type': 'text', 'default': 'a*exp(-x/tau) + c', 'show_if': {'model': ['custom']},
         'label': {'en': 'Custom formula in x', 'it': 'Formula personalizzata in x'},
         'help': {'en': 'Functions: exp log log10 sqrt sin cos tan arctan sinh cosh tanh abs erf; constants pi, e.',
                  'it': 'Funzioni: exp log log10 sqrt sin cos tan arctan sinh cosh tanh abs erf; costanti pi, e.'}},
        {'id': 'p0', 'type': 'text', 'default': '',
         'label': {'en': 'Starting values (e.g. tau=10, c=0)', 'it': 'Valori iniziali (es. tau=10, c=0)'}},
        {'id': 'band', 'type': 'choice', 'default': 'confidence',
         'label': {'en': 'Error band of the curve', 'it': 'Banda d’errore della curva'},
         'choices': [{'value': 'confidence', 'label': {'en': '95% confidence (of the fitted curve)', 'it': 'confidenza 95% (della curva)'}},
                     {'value': 'prediction', 'label': {'en': '95% prediction (of new points)', 'it': 'predizione 95% (di nuovi punti)'}},
                     {'value': 'none', 'label': {'en': 'none', 'it': 'nessuna'}}]},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'label': {'en': 'Fit from x =', 'it': 'Fit da x ='}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'label': {'en': 'Fit up to x =', 'it': 'Fit fino a x ='}},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. '
        'Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}

SAFE_FUNCS = {'exp', 'log', 'log10', 'log2', 'sqrt', 'sin', 'cos', 'tan', 'arcsin', 'arccos', 'arctan',
              'sinh', 'cosh', 'tanh', 'abs', 'erf', 'erfc', 'power'}
SAFE_CONSTS = {'pi', 'e'}


def compile_formula(text):
    """Turn 'a*exp(-x/tau)+c' into f(x, *params) with only arithmetic and whitelisted functions."""
    from scipy import special
    tree = ast.parse(text.replace('^', '**'), mode='eval')
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCS:
                raise ValueError('Allowed functions: ' + ', '.join(sorted(SAFE_FUNCS)))
        elif isinstance(node, ast.Name):
            if node.id not in SAFE_FUNCS | SAFE_CONSTS | {'x'} and node.id not in names:
                names.append(node.id)
        elif not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Load,
                                   ast.operator, ast.unaryop)):
            raise ValueError(f'Not allowed in a formula: {node.__class__.__name__}')
    if 'x' not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}:
        raise ValueError('The formula must use x.')
    if not names:
        raise ValueError('The formula has no parameters to fit.')
    env = {n: getattr(np, n) for n in SAFE_FUNCS if hasattr(np, n)}
    env.update(erf=special.erf, erfc=special.erfc, pi=np.pi, e=np.e, abs=np.abs)
    code = compile(tree, '<formula>', 'eval')

    def f(x, *args):
        return eval(code, {'__builtins__': {}}, {**env, 'x': x, **dict(zip(names, args))})  # noqa: S307
    return f, names


def model_function(model):
    from scipy.special import voigt_profile
    return {
        'linear': lambda x, a, b: a * x + b,
        'poly2': lambda x, a, b, c: a * x ** 2 + b * x + c,
        'poly3': lambda x, a, b, c, d: a * x ** 3 + b * x ** 2 + c * x + d,
        'exp_decay': lambda x, A, tau, C: A * np.exp(-x / tau) + C,
        'exp2_decay': lambda x, A1, tau1, A2, tau2, C: A1 * np.exp(-x / tau1) + A2 * np.exp(-x / tau2) + C,
        'stretched': lambda x, A, tau, beta, C: A * np.exp(-np.power(np.abs(x / tau), beta)) + C,
        'power': lambda x, A, n: A * np.power(x, n),
        'gaussian': lambda x, A, mu, sigma, C: A * np.exp(-(x - mu) ** 2 / (2 * sigma ** 2)) + C,
        'lorentzian': lambda x, A, x0, gamma, C: A * gamma ** 2 / ((x - x0) ** 2 + gamma ** 2) + C,
        'voigt': lambda x, A, x0, sigma, gamma, C: A * voigt_profile(x - x0, abs(sigma), abs(gamma)) + C,
        'logistic': lambda x, L, k, x0, C: L / (1 + np.exp(-k * (x - x0))) + C,
        'hill': lambda x, Vmax, K, n: Vmax * np.power(x, n) / (np.power(K, n) + np.power(x, n)),
        'michaelis': lambda x, Vmax, Km: Vmax * x / (Km + x),
        'arrhenius': lambda x, A, Ea: A * np.exp(-Ea / (R_GAS * x)),
        'sine': lambda x, A, f, phi, C: A * np.sin(2 * np.pi * f * x + phi) + C,
    }[model]


def initial_guess(model, x, y):
    span = (x.max() - x.min()) or 1.0
    ymin, ymax = y.min(), y.max()
    imax = int(np.argmax(np.abs(y - np.median(y))))
    if model == 'linear':
        return list(np.polyfit(x, y, 1))
    if model == 'poly2':
        return list(np.polyfit(x, y, 2))
    if model == 'poly3':
        return list(np.polyfit(x, y, 3))
    if model == 'exp_decay':
        return [y[0] - y[-1], span / 3, y[-1]]
    if model == 'exp2_decay':
        return [(y[0] - y[-1]) / 2, span / 10, (y[0] - y[-1]) / 2, span / 2, y[-1]]
    if model == 'stretched':
        return [y[0] - y[-1], span / 3, 0.7, y[-1]]
    if model == 'power':
        ok = (x > 0) & (y > 0)
        if ok.sum() >= 2:
            n, lna = np.polyfit(np.log(x[ok]), np.log(y[ok]), 1)
            return [np.exp(lna), n]
        return [1.0, 1.0]
    if model in ('gaussian', 'lorentzian', 'voigt'):
        base = np.median(y)
        amp = y[imax] - base
        half = np.abs(y - base) > abs(amp) / 2
        width = max((x[half].max() - x[half].min()) / 2.355, span / 100) if half.any() else span / 10
        if model == 'gaussian':
            return [amp, x[imax], width, base]
        if model == 'lorentzian':
            return [amp, x[imax], width, base]
        return [amp * width * 2.5, x[imax], width / 2, width / 2, base]
    if model == 'logistic':
        return [ymax - ymin, 4 / span, x[len(x) // 2], ymin]
    if model == 'hill':
        return [ymax, np.median(x), 1.0]
    if model == 'michaelis':
        return [ymax, np.median(x)]
    if model == 'arrhenius':
        ok = (x > 0) & (y > 0)
        if ok.sum() >= 2:
            slope, lna = np.polyfit(1 / x[ok], np.log(y[ok]), 1)
            return [np.exp(lna), -slope * R_GAS]
        return [1.0, 5e4]
    if model == 'sine':
        dt = np.median(np.diff(np.sort(x))) or 1.0
        spec = np.abs(np.fft.rfft(y - y.mean()))
        freqs = np.fft.rfftfreq(y.size, dt)
        f = freqs[1 + int(np.argmax(spec[1:]))] if spec.size > 1 else 1 / span
        return [(ymax - ymin) / 2, f, 0.0, y.mean()]
    return None


def parse_p0(text, names, guess):
    p0 = list(guess) if guess is not None else [1.0] * len(names)
    for part in str(text or '').replace(';', ',').split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            k = k.strip()
            if k in names:
                p0[names.index(k)] = float(v)
    return p0


def curve_band(f, x, popt, pcov, tcrit, extra_var=0.0):
    """Half-width of the confidence band: t·sqrt(J·C·Jᵀ (+ extra variance)), J by central differences."""
    popt = np.asarray(popt, float)
    jac = np.empty((x.size, popt.size))
    for j in range(popt.size):
        h = 1e-6 * max(abs(popt[j]), 1e-8)
        up, dn = popt.copy(), popt.copy()
        up[j] += h
        dn[j] -= h
        jac[:, j] = (f(x, *up) - f(x, *dn)) / (2 * h)
    var = np.einsum('ij,jk,ik->i', jac, pcov, jac) + extra_var
    return tcrit * np.sqrt(np.clip(var, 0, None))


def free_name(name, taken):
    """name, or name with a numbered suffix, so that it differs from every name in taken."""
    out, k = name, 2
    while out in taken:
        out, k = f'{name} ({k})', k + 1
    return out


def histogram(df, p, ctx):
    """Histogram of column p['y']. With a histogram of that column open, the same bins and the same
    counts/density as the figure, so the fitted curve can be drawn on it."""
    v = ctx.numeric(df, p['y']).to_numpy(float)
    v = v[np.isfinite(v)]
    if v.size < 5:
        raise ValueError(ctx.tr('At least 5 values are needed for a histogram.', 'Servono almeno 5 valori per un istogramma.'))
    spec = ctx.spec or {}
    st = spec.get('style') or {}
    same = (spec.get('kind') == 'hist' and list(spec.get('y') or []) == [p['y']] and not spec.get('hue')
            and not any(isinstance(e, dict) and e.get('enabled', True) for e in spec.get('extra') or []))
    fig_bins = st.get('bins', 30)
    fig_bins = int(fig_bins) if str(fig_bins).isdigit() else (fig_bins or 'auto')
    bins = p['bins'] or (fig_bins if same else 'auto')
    density = bool(st.get('density')) if same else True
    values, edges = np.histogram(v, bins=np.histogram_bin_edges(v, bins=bins), density=density)
    return {'x': 0.5 * (edges[1:] + edges[:-1]), 'y': values.astype(float), 'n': v.size, 'bins': values.size,
            'density': density, 'on_figure': same and (not p['bins'] or p['bins'] == fig_bins),
            'yname': ctx.tr('density', 'densità') if density else ctx.tr('count', 'conteggio')}


def run(df, p, ctx):
    from scipy import optimize, stats

    mode = p['source']
    if mode == 'auto':
        mode = 'hist' if (ctx.spec or {}).get('kind') == 'hist' else 'xy'
    hist = histogram(df, p, ctx) if mode == 'hist' else None
    sigma = None
    if hist:
        x, y = hist['x'], hist['y']
        xname = p['y']
        yname = free_name(hist['yname'], {xname})          # a column called "density" or "count"
    else:
        yname = p['y']
        xname = p['x'] or free_name('index', {yname})
        x, y = ctx.xy(df, p['x'], p['y'])
    if p['sigma'] and not hist:
        s = ctx.numeric(df, p['sigma'], dropna=False)
        xs = ctx.numeric(df, p['x'], dropna=False) if p['x'] else pd.Series(np.arange(len(df), dtype=float), index=df.index)
        ys = ctx.numeric(df, p['y'], dropna=False)
        ok = xs.notna() & ys.notna() & s.notna() & (s > 0)
        x, y, sigma = (v[ok].to_numpy(dtype=float) for v in (xs, ys, s))
    keep = np.ones(x.size, bool)
    if p['xmin'] is not None:
        keep &= x >= p['xmin']
    if p['xmax'] is not None:
        keep &= x <= p['xmax']
    x, y = x[keep], y[keep]
    sigma = sigma[keep] if sigma is not None else None
    order = np.argsort(x)
    x, y = x[order], y[order]
    sigma = sigma[order] if sigma is not None else None

    if p['model'] == 'custom':
        f, names = compile_formula(p['formula'])
        equation = 'y = ' + p['formula']
        guess = None
    else:
        f = model_function(p['model'])
        equation, names = MODELS[p['model']]
        guess = initial_guess(p['model'], x, y)
    if x.size <= len(names):
        raise ValueError(ctx.tr(f'Too few points ({x.size}) for {len(names)} parameters.',
                                f'Troppi pochi punti ({x.size}) per {len(names)} parametri.'))
    p0 = parse_p0(p['p0'], names, guess)
    popt, pcov, info, msg, ier = optimize.curve_fit(f, x, y, p0=p0, sigma=sigma, absolute_sigma=sigma is not None,
                                                     maxfev=20000, full_output=True)
    perr = np.sqrt(np.clip(np.diag(pcov), 0, None)) if np.all(np.isfinite(pcov)) else np.full(len(popt), np.nan)
    fit_y = f(x, *popt)
    resid = y - fit_y
    n, k = x.size, len(popt)
    dof = max(1, n - k)
    tcrit = stats.t.ppf(0.975, dof)
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    adj_r2 = 1 - (1 - r2) * (n - 1) / dof if np.isfinite(r2) else np.nan
    rmse = np.sqrt(ss_res / n)
    rss = ss_res if sigma is None else float(np.sum((resid / sigma) ** 2))
    if sigma is not None:      # known errors: −2 ln L = χ² + const, the quantity the weighted fit minimised
        aic, bic = rss + 2 * k, rss + k * np.log(n)
    else:
        aic = n * np.log(ss_res / n) + 2 * k if ss_res > 0 else np.nan
        bic = n * np.log(ss_res / n) + k * np.log(n) if ss_res > 0 else np.nan

    r = ctx.result()
    r.text(equation)
    if hist:
        kind = ctx.tr('density', 'densità') if hist['density'] else ctx.tr('counts', 'conteggi')
        r.text(ctx.tr(f'Fit of the histogram of “{p["y"]}”: {hist["n"]} values in {hist["bins"]} bins ({kind}).',
                      f'Fit dell’istogramma di «{p["y"]}»: {hist["n"]} valori in {hist["bins"]} intervalli ({kind}).'))
        r.keep('bins', hist['bins'])
    rows = []
    for name, val, err in zip(names, popt, perr):
        rows.append({ctx.tr('parameter', 'parametro'): name, ctx.tr('value', 'valore'): val,
                     ctx.tr('std. error', 'errore std.'): err,
                     'CI 95% low': val - tcrit * err, 'CI 95% high': val + tcrit * err,
                     ctx.tr('rel. error %', 'errore rel. %'): abs(err / val) * 100 if val else np.nan})
    r.table(ctx.tr('Fitted parameters', 'Parametri del fit'), rows)
    for name, val, err in zip(names, popt, perr):
        r.keep(name, float(val), float(err))         # e.g. r.get('mu'), r.error('mu') in a recipe
    r.value('N', n, key='n')
    r.value(ctx.tr('degrees of freedom', 'gradi di libertà'), dof)
    r.value('R²', r2, key='r2')
    r.value(ctx.tr('adjusted R²', 'R² corretto'), adj_r2, key='adj_r2')
    r.value('RMSE', rmse, key='rmse')
    if sigma is not None:
        r.value('χ²_red', rss / dof)
    r.value('AIC', aic, key='aic')
    r.value('BIC', bic, key='bic')
    if ier not in (1, 2, 3, 4):
        r.text(ctx.tr('Warning: the optimiser reports: ', 'Attenzione, l’ottimizzatore riporta: ') + str(msg))
    if p['model'] == 'stretched':
        from scipy.special import gamma as G
        tau, beta = popt[1], popt[2]
        r.value(ctx.tr('mean relaxation time ⟨τ⟩ = (τ/β)Γ(1/β)', 'tempo medio ⟨τ⟩ = (τ/β)Γ(1/β)'), tau / beta * G(1 / beta))
        r.cite('Williams, G. & Watts, D. C. Non-symmetrical dielectric relaxation behaviour arising from a simple '
               'empirical decay function. Trans. Faraday Soc. 66, 80–85 (1970). doi:10.1039/TF9706600080')
    if p['model'] == 'arrhenius':
        r.value('Ea', popt[1] / 1000, perr[1] / 1000, 'kJ/mol')

    taken = {xname, yname, p['sigma']}
    fit_name = free_name('fit', taken)
    resid_name = free_name(ctx.tr('residual', 'residuo'), taken | {fit_name})
    r.keep('fit_column', fit_name)
    r.keep('resid_column', resid_name)
    data = pd.DataFrame({xname: x, yname: y, fit_name: fit_y, resid_name: resid})
    if sigma is not None:
        data[p['sigma']] = sigma
    # Smooth curve on a fine grid with its 95 % band, to draw over the original figure.
    grid = np.linspace(x.min(), x.max(), 400)
    curve = pd.DataFrame({xname: grid, fit_name: f(grid, *popt)})
    lo = hi = None
    band_label = None
    if p['band'] != 'none' and np.all(np.isfinite(pcov)):
        extra = 0.0
        if p['band'] == 'prediction':
            extra = np.interp(grid, x, sigma ** 2) if sigma is not None else ss_res / dof
        half = curve_band(f, grid, popt, pcov, tcrit, extra)
        lo, hi = free_name('band low', taken | {fit_name}), free_name('band high', taken | {fit_name})
        curve[lo], curve[hi] = curve[fit_name] - half, curve[fit_name] + half
        band_label = ctx.tr('95% confidence', 'confidenza 95%') if p['band'] == 'confidence' \
            else ctx.tr('95% prediction', 'predizione 95%')
        r.value(ctx.tr('band', 'banda'), band_label)
    ref = r.overlay(curve, xname, fit_name, lo, hi, label=ctx.tr('fit', 'fit') + f' ({p["model"]})', band_label=band_label,
                    on_figure=hist['on_figure'] if hist else True)
    r.table(ctx.tr('Fitted curve and band', 'Curva e banda del fit'), curve.iloc[::20])
    if hist:
        plot = {'kind': 'step', 'x': xname, 'y': [yname], 'overlays': [{'ref': ref}],
                'series': {yname: {'label': ctx.tr('histogram', 'istogramma')}},
                'text': {'xlabel': p['y'], 'ylabel': yname}}
    elif sigma is not None:
        plot = {'kind': 'errorbar', 'x': xname, 'y': [yname], 'yerr': p['sigma'], 'style': {'marker': 'o'},
                'series': {yname: {'linestyle': 'none', 'label': yname}}, 'overlays': [{'ref': ref}]}
    else:
        plot = {'kind': 'line', 'x': xname, 'y': [yname], 'overlays': [{'ref': ref}],
                'series': {yname: {'linestyle': 'none', 'marker': 'o', 'label': yname}}}
    r.data(data, name=f'fit · {yname}', plot=plot)
    return r
