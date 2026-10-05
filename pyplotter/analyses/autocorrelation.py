"""Autocorrelation (ACF) and partial autocorrelation (PACF) of a series, with statsmodels.

Also reports the integrated autocorrelation time (automatic window, Sokal), the 1/e and
first-zero-crossing times and, optionally, an exponential fit of the ACF decay.
"""
import warnings

import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'autocorrelation',
    'order': 10,
    'name': {'en': 'Autocorrelation (ACF / PACF)', 'it': 'Autocorrelazione (ACF / PACF)'},
    'category': 'timeseries',
    'description': {'en': 'ACF with confidence band, PACF, correlation times. Rows must be equally spaced in time.',
                    'it': 'ACF con banda di confidenza, PACF, tempi di correlazione. Righe equispaziate nel tempo.'},
    'requires': ['statsmodels', 'scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Series', 'it': 'Serie'}},
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x',
         'label': {'en': 'Time column (optional, sets the lag unit)', 'it': 'Colonna del tempo (facoltativa, unità dei ritardi)'}},
        {'id': 'dt', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Time step (if no time column)', 'it': 'Passo temporale (senza colonna del tempo)'}},
        {'id': 'nlags', 'type': 'int', 'optional': True, 'min': 1,
         'label': {'en': 'Maximum lag (points, empty = auto)', 'it': 'Ritardo massimo (punti, vuoto = auto)'}},
        {'id': 'alpha', 'type': 'float', 'default': 0.05, 'min': 0.001, 'max': 0.5,
         'label': {'en': 'Significance level of the band', 'it': 'Livello di significatività della banda'}},
        {'id': 'partial', 'type': 'bool', 'default': False, 'label': {'en': 'Also compute the PACF', 'it': 'Calcola anche la PACF'}},
        {'id': 'fit_exp', 'type': 'bool', 'default': True,
         'label': {'en': 'Fit exp(−t/τ) to the initial decay', 'it': 'Fit exp(−t/τ) del decadimento iniziale'}},
    ],
    'references': [
        'Seabold, S. & Perktold, J. statsmodels: Econometric and statistical modeling with Python. '
        'Proc. 9th Python in Science Conf. 92–96 (2010). doi:10.25080/Majora-92bf1922-011',
        'Madras, N. & Sokal, A. D. The pivot algorithm: a highly efficient Monte Carlo method for the self-avoiding walk. '
        'J. Stat. Phys. 50, 109–186 (1988). doi:10.1007/BF01022990',
    ],
}


def integrated_time(rho, c=5.0):
    """τ_int = 1/2 + Σ ρ(t), summed up to the first window M with M ≥ c·τ_int(M) (Sokal)."""
    tau = 0.5
    for m in range(1, len(rho)):
        tau += rho[m]
        if m >= c * tau:
            return tau, m
    return tau, len(rho) - 1


def run(df, p, ctx):
    from statsmodels.tsa.stattools import acf, pacf

    y = ctx.numeric(df, p['y']).to_numpy(dtype=float)
    n = y.size
    if n < 10:
        raise ValueError(ctx.tr('At least 10 values are needed.', 'Servono almeno 10 valori.'))
    dt, unit, ctx_note = 1.0, ctx.tr('points', 'punti'), None
    if p['x']:
        t = ctx.numeric(df, p['x'], dropna=False)[df[p['y']].notna()].to_numpy(dtype=float)
        steps = np.diff(t[np.isfinite(t)])
        if steps.size:
            dt = float(np.median(steps))
            unit = p['x']
            if np.any(np.abs(steps - dt) > 1e-6 * abs(dt)):
                ctx_note = ctx.tr('Time steps are not constant; the median step is used.',
                                  'Il passo temporale non è costante; uso il passo mediano.')
    elif p['dt']:
        dt, unit = float(p['dt']), ctx.tr('time', 'tempo')
    nlags = int(p['nlags']) if p['nlags'] else min(n - 1, max(10, n // 4))
    nlags = min(nlags, n - 1)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', FutureWarning)
        rho, conf = acf(y, nlags=nlags, alpha=p['alpha'], fft=True, missing='drop')[:2]
    lags = np.arange(nlags + 1) * dt
    out = pd.DataFrame({'lag': lags, 'ACF': rho, 'CI low': conf[:, 0], 'CI high': conf[:, 1]})
    # Band for "no correlation" (Bartlett) is the CI shifted to zero
    out['band +'] = conf[:, 1] - rho
    out['band −'] = conf[:, 0] - rho
    ycols = ['ACF', 'band +', 'band −']
    if p['partial']:
        pl = min(nlags, n // 2 - 1, 200)          # PACF beyond a few hundred lags is rarely meaningful
        out['PACF'] = np.r_[pacf(y, nlags=pl, method='ldb'), np.full(nlags - pl, np.nan)]
        ycols.insert(1, 'PACF')

    tau_int, window = integrated_time(rho)
    r = ctx.result()
    if ctx_note:
        r.text(ctx_note)
    r.value('N', n)
    r.value(ctx.tr('mean', 'media'), y.mean())
    r.value(ctx.tr('variance', 'varianza'), y.var(ddof=1))
    r.value(ctx.tr('integrated autocorrelation time τ_int', 'tempo di autocorrelazione integrato τ_int'), tau_int * dt, None, unit)
    r.value(ctx.tr('summation window', 'finestra di somma'), window * dt, None, unit)
    g = max(1.0, 2 * tau_int)
    r.value(ctx.tr('statistical inefficiency g = 2τ_int', 'inefficienza statistica g = 2τ_int'), g)
    r.value(ctx.tr('effective independent samples N/g', 'campioni indipendenti effettivi N/g'), n / g)
    r.value(ctx.tr('standard error of the mean (corrected)', 'errore standard della media (corretto)'),
            y.std(ddof=1) * np.sqrt(g / n))
    below = np.where(rho < np.exp(-1))[0]
    if below.size:
        r.value(ctx.tr('1/e time', 'tempo 1/e'), below[0] * dt, None, unit)
    zero = np.where(rho <= 0)[0]
    if zero.size:
        r.value(ctx.tr('first zero crossing', 'primo attraversamento dello zero'), zero[0] * dt, None, unit)
    if p['fit_exp']:
        from scipy.optimize import curve_fit
        stop = int(zero[0]) if zero.size else nlags
        stop = max(stop, 3)
        try:
            (tau,), cov = curve_fit(lambda t, tau: np.exp(-t / tau), lags[:stop], rho[:stop],
                                    p0=[max(dt, (below[0] if below.size else stop / 2) * dt)])
            r.value(ctx.tr('exponential fit τ (ACF ≈ e^(−t/τ))', 'τ del fit esponenziale (ACF ≈ e^(−t/τ))'),
                    tau, float(np.sqrt(cov[0, 0])), unit)
            out['exp fit'] = np.exp(-lags / tau)
            ycols.append('exp fit')
        except Exception:
            r.text(ctx.tr('The exponential fit did not converge.', 'Il fit esponenziale non è andato a convergenza.'))
    r.data(out, name=f'ACF · {p["y"]}', plot={
        'kind': 'line', 'x': 'lag', 'y': ycols,
        'text': {'xlabel': f'lag ({unit})', 'ylabel': 'ACF'},
        'series': {'band +': {'linestyle': '--', 'color': '#888888', 'label': f'{int((1 - p["alpha"]) * 100)}% band'},
                   'band −': {'linestyle': '--', 'color': '#888888', 'label': '_nolegend_'},
                   'exp fit': {'linestyle': ':', 'label': 'exp(−t/τ)'}}})
    return r
