"""Recipe: is a column Gaussian, and with which mean and width?

Steps (each one is the built-in analysis of the same name, run through ctx.run):
1. histogram of the column (probability density), 2. least-squares Gaussian fit of the histogram
(Curve fitting), 3. normality tests (skewness, kurtosis, Shapiro–Wilk…), 4. block averaging for the
true error of the mean when the values are a time series (MD, Monte Carlo, sensors).
The maximum-likelihood estimates (sample mean and standard deviation) are reported next to the fit,
which depends a little on the number of bins.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'recipe_gaussian',
    'order': 10,
    'name': {'en': 'Gaussian distribution of a column', 'it': 'Distribuzione gaussiana di una colonna'},
    'category': 'recipe',
    'description': {'en': 'Histogram + Gaussian fit, normality check and the true error of the mean: '
                          'mean, σ and FWHM of the values in one go.',
                    'it': 'Istogramma + fit gaussiano, verifica di normalità e vero errore della media: '
                          'media, σ e FWHM dei valori in un colpo solo.'},
    'steps': [
        {'en': 'Histogram of the column (probability density)', 'it': 'Istogramma della colonna (densità di probabilità)'},
        {'en': 'Gaussian least-squares fit of the histogram', 'it': 'Fit gaussiano ai minimi quadrati dell’istogramma'},
        {'en': 'Normality tests (skewness, kurtosis, Shapiro–Wilk…)', 'it': 'Test di normalità (asimmetria, curtosi, Shapiro–Wilk…)'},
        {'en': 'Block averaging: true error of the mean for correlated data',
         'it': 'Block averaging: vero errore della media per dati correlati'},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Column', 'it': 'Colonna'}},
        {'id': 'bins', 'type': 'int', 'optional': True, 'min': 5, 'max': 1000,
         'label': {'en': 'Histogram bins (empty = automatic)', 'it': 'Intervalli dell’istogramma (vuoto = automatico)'}},
        {'id': 'series', 'type': 'bool', 'default': True,
         'label': {'en': 'Rows are a time series (correct the error of the mean)',
                   'it': 'Le righe sono una serie temporale (correggi l’errore della media)'}},
    ],
    'references': [
        'Freedman, D. & Diaconis, P. On the histogram as a density estimator: L2 theory. '
        'Z. Wahrscheinlichkeitstheorie verw. Gebiete 57, 453–476 (1981). doi:10.1007/BF01025868',
    ],
}

FWHM = 2 * np.sqrt(2 * np.log(2))     # full width at half maximum of a Gaussian = 2.3548 σ


def auto_bins(v):
    """Freedman–Diaconis rule, kept between 10 and 200 bins."""
    return int(np.clip(np.histogram_bin_edges(v, bins='fd').size - 1, 10, 200))


def run(df, p, ctx):
    v = ctx.numeric(df, p['y']).to_numpy(float)
    v = v[np.isfinite(v)]
    if v.size < 20:
        raise ValueError(ctx.tr('At least 20 values are needed.', 'Servono almeno 20 valori.'))
    bins = p['bins'] or auto_bins(v)
    step = ctx.tr('Step', 'Passo')

    # 1. histogram (density, so that the area is 1 and A·σ·√(2π) ≈ 1 for a good Gaussian)
    dens, edges = np.histogram(v, bins=bins, density=True)
    xname, dname = p['y'], ctx.tr('density', 'densità')
    if dname == xname:                      # the column itself is called "density"
        dname = f'{dname} ({xname})'
    hist = pd.DataFrame({xname: 0.5 * (edges[1:] + edges[:-1]), dname: dens})

    # 2. Gaussian fit of the histogram
    fit = ctx.run('fit_curve', hist, source='xy', x=xname, y=dname, sigma=None, model='gaussian', band='confidence')
    mu, mu_err = fit.get('mu'), fit.error('mu')
    sig, sig_err = abs(fit.get('sigma')), fit.error('sigma')

    # 3. normality
    norm = ctx.run('normality', pd.DataFrame({xname: v}), y=xname)

    # 4. error of the mean (block averaging) for time series
    block = ctx.run('block_average', pd.DataFrame({xname: v}), y=xname, x=None) if p['series'] and v.size >= 16 else None

    r = ctx.result()
    r.value('N', v.size)
    if block is not None:
        r.value(ctx.tr('mean (with block-averaging error)', 'media (con errore da block averaging)'),
                block.get('mean'), block.get('sem'), key='mean')
    else:
        r.value(ctx.tr('mean ± standard error', 'media ± errore standard'), v.mean(), v.std(ddof=1) / np.sqrt(v.size),
                key='mean')
    r.value(ctx.tr('standard deviation σ (of the values)', 'deviazione standard σ (dei valori)'), v.std(ddof=1), key='sd')
    r.value(ctx.tr('Gaussian fit: centre μ', 'fit gaussiano: centro μ'), mu, mu_err, key='mu')
    r.value(ctx.tr('Gaussian fit: width σ', 'fit gaussiano: larghezza σ'), sig, sig_err, key='sigma')
    r.value('FWHM = 2.3548 σ', FWHM * sig, FWHM * sig_err if sig_err is not None else None, key='fwhm')
    r.value(ctx.tr('Gaussian fit: R²', 'fit gaussiano: R²'), fit.get('r2'), key='r2')
    r.value(ctx.tr('skewness (0 for a Gaussian)', 'asimmetria (0 per una gaussiana)'), norm.get('skew'), key='skew')
    r.value(ctx.tr('excess kurtosis (0 for a Gaussian)', 'curtosi in eccesso (0 per una gaussiana)'),
            norm.get('kurtosis'), key='kurtosis')
    if block is not None:
        r.value(ctx.tr('statistical inefficiency g (1 = independent values)',
                       'inefficienza statistica g (1 = valori indipendenti)'), block.get('g'), key='g')
    r.value(ctx.tr('histogram bins', 'intervalli dell’istogramma'), bins)

    # Plain-language verdict
    skew, kurt, r2 = norm.get('skew'), norm.get('kurtosis'), fit.get('r2')
    good = r2 is not None and r2 > 0.95 and abs(skew) < 0.5 and abs(kurt) < 1
    if good:
        r.text(ctx.tr(f'The values are well described by a Gaussian (R² = {r2:.3f}, skewness {skew:+.2f}, '
                      f'excess kurtosis {kurt:+.2f}).',
                      f'I valori sono ben descritti da una gaussiana (R² = {r2:.3f}, asimmetria {skew:+.2f}, '
                      f'curtosi in eccesso {kurt:+.2f}).'))
    else:
        r.text(ctx.tr(f'The values depart from a Gaussian (R² = {r2:.3f}, skewness {skew:+.2f}, excess kurtosis '
                      f'{kurt:+.2f}): look at the figure; consider Distribution fitting for other shapes.',
                      f'I valori si discostano da una gaussiana (R² = {r2:.3f}, asimmetria {skew:+.2f}, curtosi in '
                      f'eccesso {kurt:+.2f}): guarda la figura; per altre forme usa «Fit di distribuzioni».'))
    if v.size > 5000 and not norm.get('normal'):
        r.text(ctx.tr('With this many values the normality tests reject even tiny deviations: judge from skewness, '
                      'kurtosis and the figure.',
                      'Con così tanti valori i test di normalità respingono anche scostamenti minimi: giudica da '
                      'asimmetria, curtosi e figura.'))
    if block is not None and block.get('g') and block.get('g') > 2:
        r.text(ctx.tr(f'The rows are correlated (g = {block.get("g"):.0f}): the error of the mean uses block averaging; '
                      'the fit error on μ is too small for these data.',
                      f'Le righe sono correlate (g = {block.get("g"):.0f}): l’errore della media usa il block averaging; '
                      'l’errore del fit su μ è troppo piccolo per questi dati.'))

    # Steps in detail
    first = r.include(fit, f'{step} 2 · ' + ctx.tr('Gaussian fit', 'fit gaussiano'), overlays=True)
    r.overlays[first]['on_figure'] = False          # x of the curve = values, not the figure's x
    r.include(norm, f'{step} 3 · ' + ctx.tr('normality', 'normalità'))
    if block is not None:
        r.include(block, f'{step} 4 · block averaging')
    r.table(f'{step} 1 · ' + ctx.tr('histogram', 'istogramma'), hist)

    r.data(hist, name=ctx.tr('histogram + Gaussian', 'istogramma + gaussiana') + f' · {p["y"]}', plot={
        'kind': 'step', 'x': xname, 'y': [dname], 'overlays': [{'ref': first}],
        'series': {dname: {'label': ctx.tr('histogram', 'istogramma'), 'linewidth': 1.2}},
        'text': {'xlabel': p['y'], 'ylabel': ctx.tr('probability density', 'densità di probabilità')}})
    return r
