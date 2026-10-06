"""Recipe: fit of the peaks of a spectrum or chromatogram.

Steps: 1. Peak finding (positions, heights, widths) gives the starting values, 2. all peaks are fitted
together as a sum of Gaussians or Lorentzians on a constant or straight baseline (Curve fitting with a
custom formula, so overlapping peaks share the data correctly), 3. centre, height, FWHM and area of
each peak with their errors. The fitted curve, each peak and the peak values are drawn on the figure.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'recipe_peak_fit',
    'order': 50,
    'name': {'en': 'Peak fit (spectra, chromatograms)', 'it': 'Fit dei picchi (spettri, cromatogrammi)'},
    'category': 'recipe',
    'description': {'en': 'Finds the peaks and fits them all together: centre, height, FWHM and area of each peak '
                          'with errors; values written above the peaks.',
                    'it': 'Trova i picchi e li adatta tutti insieme: centro, altezza, FWHM e area di ogni picco con '
                          'errori; valori scritti sopra i picchi.'},
    'steps': [
        {'en': 'Peak finding: positions and widths as starting values',
         'it': 'Ricerca dei picchi: posizioni e larghezze come valori iniziali'},
        {'en': 'Joint fit of all peaks + baseline (Gaussian or Lorentzian)',
         'it': 'Fit congiunto di tutti i picchi + linea di base (gaussiane o lorentziane)'},
        {'en': 'Centre, height, FWHM, area of each peak; values on the figure',
         'it': 'Centro, altezza, FWHM, area di ogni picco; valori sulla figura'},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Signal', 'it': 'Segnale'}},
        {'id': 'shape', 'type': 'choice', 'default': 'gaussian', 'label': {'en': 'Peak shape', 'it': 'Forma dei picchi'},
         'choices': [{'value': 'gaussian', 'label': {'en': 'Gaussian', 'it': 'gaussiana'}},
                     {'value': 'lorentzian', 'label': {'en': 'Lorentzian', 'it': 'lorentziana'}}]},
        {'id': 'baseline', 'type': 'choice', 'default': 'linear', 'label': {'en': 'Baseline', 'it': 'Linea di base'},
         'choices': [{'value': 'linear', 'label': {'en': 'straight line', 'it': 'retta'}},
                     {'value': 'constant', 'label': {'en': 'constant', 'it': 'costante'}}]},
        {'id': 'prominence', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Minimum prominence (empty = 5% of range)', 'it': 'Prominenza minima (vuoto = 5% dell’intervallo)'}},
        {'id': 'max_peaks', 'type': 'int', 'default': 8, 'min': 1, 'max': 30,
         'label': {'en': 'At most … peaks (the most prominent)', 'it': 'Al massimo … picchi (i più prominenti)'}},
        {'id': 'labels', 'type': 'choice', 'default': 'position', 'label': {'en': 'Text above each peak', 'it': 'Testo sopra ogni picco'},
         'choices': [{'value': 'position', 'label': {'en': 'centre', 'it': 'centro'}},
                     {'value': 'position_fwhm', 'label': {'en': 'centre and FWHM', 'it': 'centro e FWHM'}},
                     {'value': 'none', 'label': {'en': 'nothing', 'it': 'niente'}}]},
    ],
    'references': [
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}

FWHM_G = 2 * np.sqrt(2 * np.log(2))


def short(v):
    """Short text for a number: 4 significant digits, no exponent for ordinary values."""
    v = float(v)
    if v != 0 and (abs(v) >= 1e6 or abs(v) < 1e-3):
        return f'{v:.3g}'
    return np.format_float_positional(v, precision=4, unique=False, fractional=False, trim='-')


def shape_value(shape, x, a, m, w):
    if shape == 'gaussian':
        return a * np.exp(-(x - m) ** 2 / (2 * w ** 2))
    return a * w ** 2 / ((x - m) ** 2 + w ** 2)


def run(df, p, ctx):
    step = ctx.tr('Step', 'Passo')
    shape = p['shape']
    found = ctx.run('peaks', df, x=p['x'], y=p['y'], prominence=p['prominence'], distance=1, minima=False, labels=False)
    peaks = found.get('peaks') or []
    if not peaks:
        raise ValueError(ctx.tr('No peak found: lower the minimum prominence.',
                                'Nessun picco trovato: abbassa la prominenza minima.'))
    peaks = sorted(sorted(peaks, key=lambda q: -q['prominence'])[:p['max_peaks']], key=lambda q: q['position'])
    x, y = ctx.xy(df, p['x'], p['y'])
    c0 = float(np.percentile(y, 5))

    # Sum of peaks + baseline as a Curve-fitting formula, with the found peaks as starting values.
    terms, start = [], []
    w_name = 's' if shape == 'gaussian' else 'g'
    for i, q in enumerate(peaks, 1):
        width = max(q['fwhm'], 1e-12) / (FWHM_G if shape == 'gaussian' else 2)
        if shape == 'gaussian':
            terms.append(f'A{i}*exp(-(x-m{i})**2/(2*s{i}**2))')
        else:
            terms.append(f'A{i}*g{i}**2/((x-m{i})**2+g{i}**2)')
        start += [f'A{i}={float(q["height"] - c0)!r}', f'm{i}={float(q["position"])!r}', f'{w_name}{i}={float(width)!r}']
    base = 'c0 + c1*x' if p['baseline'] == 'linear' else 'c0'
    start += [f'c0={c0!r}'] + (['c1=0'] if p['baseline'] == 'linear' else [])
    formula = ' + '.join(terms) + ' + ' + base
    fit = ctx.run('fit_curve', df, source='xy', x=p['x'], y=p['y'], sigma=None, model='custom', formula=formula,
                  p0=', '.join(start), band='confidence', xmin=None, xmax=None)

    rows, labels = [], []
    xname = p['x'] or 'index'
    top_name = ctx.tr('peak top', 'cima del picco')
    grid = np.linspace(x.min(), x.max(), 1200)
    baseline = fit.get('c0') + (fit.get('c1') * grid if p['baseline'] == 'linear' else 0)
    components = {}
    areas = []
    for i in range(1, len(peaks) + 1):
        a, ea = fit.get(f'A{i}'), fit.error(f'A{i}')
        m, em = fit.get(f'm{i}'), fit.error(f'm{i}')
        w, ew = abs(fit.get(f'{w_name}{i}')), fit.error(f'{w_name}{i}')
        if shape == 'gaussian':
            fwhm, efwhm = FWHM_G * w, FWHM_G * ew
            area = a * w * np.sqrt(2 * np.pi)
        else:
            fwhm, efwhm = 2 * w, 2 * ew
            area = np.pi * a * w
        rel = np.sqrt((ea / a) ** 2 + (ew / w) ** 2) if a and w else np.nan
        areas.append(area)
        rows.append({'#': i, ctx.tr('centre', 'centro'): m, ctx.tr('± centre', '± centro'): em,
                     ctx.tr('height', 'altezza'): a, ctx.tr('± height', '± altezza'): ea,
                     'FWHM': fwhm, '± FWHM': efwhm, ctx.tr('area', 'area'): area,
                     ctx.tr('± area', '± area'): abs(area) * rel})
        comp = shape_value(shape, grid, a, m, w)
        components[f'{ctx.tr("peak", "picco")} {i}'] = baseline + comp
        top = float(np.interp(m, grid, baseline)) + a
        text = short(m) if p['labels'] == 'position' else f'{short(m)} (FWHM {short(fwhm)})'
        labels.append({xname: m, top_name: top, 'text': text})
    total = sum(areas)
    for row, area in zip(rows, areas):
        row[ctx.tr('area %', 'area %')] = 100 * area / total if total else np.nan

    r = ctx.result()
    r.value(ctx.tr('peaks fitted', 'picchi adattati'), len(peaks), key='n_peaks')
    r.value(ctx.tr('peak shape', 'forma dei picchi'), ctx.tr(shape, 'gaussiana' if shape == 'gaussian' else 'lorentziana'))
    r.value('R²', fit.get('r2'), key='r2')
    for row in rows:
        r.value(ctx.tr(f'peak {row["#"]}: centre', f'picco {row["#"]}: centro'), row[ctx.tr('centre', 'centro')],
                row[ctx.tr('± centre', '± centro')], key=f'centre{row["#"]}')
    r.table(ctx.tr('Peaks', 'Picchi'), rows)
    r.keep('peaks', rows)
    r.text(ctx.tr('Area errors ignore the correlation between height and width (approximate).',
                  'Gli errori sulle aree trascurano la correlazione tra altezza e larghezza (approssimati).'))
    if fit.get('r2') is not None and fit.get('r2') < 0.95:
        r.text(ctx.tr('R² < 0.95: some peaks may be missing or have another shape; try a lower prominence, more peaks '
                      'or the other shape.',
                      'R² < 0,95: potrebbero mancare picchi o avere un’altra forma; prova una prominenza minore, più '
                      'picchi o l’altra forma.'))

    # On the figure: total fit (with band), each peak dashed, values above the peaks.
    first = r.include(fit, f'{step} 2 · ' + ctx.tr('joint fit', 'fit congiunto'), overlays=True)
    r.overlays[first]['label'] = ctx.tr('fit (sum of peaks)', 'fit (somma dei picchi)')
    for name, curve in components.items():
        r.overlay(pd.DataFrame({xname: grid, name: curve}), xname, name, label=name,
                  style={'linestyle': '--', 'linewidth': 0.8})
    if p['labels'] != 'none':
        lab = pd.DataFrame(labels)
        r.overlay(lab, xname, top_name, label=ctx.tr('peak values', 'valori dei picchi'), text='text',
                  style={'linestyle': 'none', 'marker': 'v', 'markersize': 3, 'color': 'text'})
    r.include(found, f'{step} 1 · ' + ctx.tr('peak finding', 'ricerca dei picchi'))
    r.data(fit.frame, name=ctx.tr('peak fit', 'fit dei picchi') + f' · {p["y"]}',
           plot={**fit.plot, 'overlays': [{'ref': k} for k in range(first, len(r.overlays))]})
    return r
