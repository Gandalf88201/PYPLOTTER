"""Recipe: fit of the peaks of a spectrum or chromatogram.

Steps: 1. the baseline — the one defined with the Baseline analysis (anchor points or an automatic
method), subtracted first, or a constant or straight line fitted together with the peaks; 2. Peak finding
(positions, heights, widths) gives the starting values; 3. all peaks are fitted together as a sum of
Gaussians or Lorentzians (Curve fitting with a custom formula, so overlapping peaks share the data
correctly); 4. centre, height, FWHM and area of each peak with their errors. The baseline, the fitted
curve, each peak and the peak values are drawn on the figure.
"""
import numpy as np
import pandas as pd

from piplotter import baselines

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
        {'en': 'Baseline: the one you defined (subtracted), or fitted with the peaks',
         'it': 'Linea di base: quella che hai definito (sottratta), o adattata con i picchi'},
        {'en': 'Peak finding: positions and widths as starting values',
         'it': 'Ricerca dei picchi: posizioni e larghezze come valori iniziali'},
        {'en': 'Joint fit of all peaks (Gaussian or Lorentzian)',
         'it': 'Fit congiunto di tutti i picchi (gaussiane o lorentziane)'},
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
        *baselines.params(extra=[('linear', {'en': 'straight line fitted with the peaks', 'it': 'retta adattata con i picchi'}),
                                 ('constant', {'en': 'constant fitted with the peaks', 'it': 'costante adattata con i picchi'})],
                          default='poly'),
        {'id': 'prominence', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Minimum prominence (empty = 5% of range)', 'it': 'Prominenza minima (vuoto = 5% dell’intervallo)'}},
        {'id': 'max_peaks', 'type': 'int', 'default': 20, 'min': 1, 'max': 40,
         'label': {'en': 'At most … peaks (the most prominent)', 'it': 'Al massimo … picchi (i più prominenti)'}},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'label': {'en': 'Only from x =', 'it': 'Solo da x ='}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'label': {'en': 'Only to x =', 'it': 'Solo fino a x ='}},
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
    x, y = ctx.xy(df, p['x'], p['y'])
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    b = ctx.baseline(x, y, p)                      # None: a constant or straight line fitted with the peaks
    fixed = b is not None
    base = b.values if fixed else np.zeros_like(y)
    keep = np.ones(x.size, bool)
    if p.get('xmin') is not None:
        keep &= x >= p['xmin']
    if p.get('xmax') is not None:
        keep &= x <= p['xmax']
    x, y, base = x[keep], y[keep], base[keep]
    if x.size < 5:
        raise ValueError(ctx.tr('Fewer than five points in the range.', 'Meno di cinque punti nell’intervallo.'))
    xname, yname = p['x'] or 'index', p['y']
    work = pd.DataFrame({xname: x, yname: y - base})      # the signal above the baseline (or as it is)
    found = ctx.run('peaks', work, x=xname, y=yname, baseline='none', prominence=p['prominence'], distance=1,
                    minima=False, labels=False)
    peaks = found.get('peaks') or []
    if not peaks:
        raise ValueError(ctx.tr('No peak found: lower the minimum prominence.',
                                'Nessun picco trovato: abbassa la prominenza minima.'))
    peaks = sorted(sorted(peaks, key=lambda q: -q['prominence'])[:p['max_peaks']], key=lambda q: q['position'])
    c0 = 0.0 if fixed else float(np.percentile(y, 5))

    # Sum of peaks (+ baseline when it is fitted) as a Curve-fitting formula, the found peaks as starting values.
    # Limits keep each peak a peak: height ≥ 0, centre inside its own region (between the neighbouring
    # minima), width between a fraction of the point spacing and twice the region.
    terms, start, limits = [], [], []
    w_name = 's' if shape == 'gaussian' else 'g'
    step_x = float(np.median(np.diff(x)))
    for i, q in enumerate(peaks, 1):
        fwhm0 = q['fwhm'] if np.isfinite(q['fwhm']) and q['fwhm'] > 0 else (x[-1] - x[0]) / 50
        width = fwhm0 / (FWHM_G if shape == 'gaussian' else 2)
        if shape == 'gaussian':
            terms.append(f'A{i}*exp(-(x-m{i})**2/(2*s{i}**2))')
        else:
            terms.append(f'A{i}*g{i}**2/((x-m{i})**2+g{i}**2)')
        start += [f'A{i}={max(float(q["signal"] - c0), 1e-12)!r}', f'm{i}={float(q["position"])!r}', f'{w_name}{i}={float(width)!r}']
        left, right = min(q['left'], q['position'] - step_x), max(q['right'], q['position'] + step_x)
        limits += [f'A{i}=0..', f'm{i}={left!r}..{right!r}',
                   f'{w_name}{i}={step_x / 4!r}..{2 * max(right - left, fwhm0)!r}']
    formula = ' + '.join(terms)
    if not fixed:
        formula += ' + c0 + c1*x' if p['baseline'] == 'linear' else ' + c0'
        start += [f'c0={c0!r}'] + (['c1=0'] if p['baseline'] == 'linear' else [])
    try:
        fit = ctx.run('fit_curve', work, source='xy', x=xname, y=yname, sigma=None, model='custom', formula=formula,
                      p0=', '.join(start), bounds=', '.join(limits), band='confidence', xmin=None, xmax=None)
    except RuntimeError as exc:
        raise ValueError(ctx.tr(f'The joint fit of {len(peaks)} peaks did not converge ({exc}). Check the baseline '
                                '(anchor points where the signal really is at its base), fit fewer peaks, or a '
                                'smaller range (“Only from x / to x”).',
                                f'Il fit congiunto di {len(peaks)} picchi non è arrivato a convergenza ({exc}). Controlla '
                                'la linea di base (punti dove il segnale è davvero alla base), adatta meno picchi o un '
                                'intervallo più piccolo («Solo da x / fino a x»).'))

    rows, labels = [], []
    top_name = ctx.tr('peak top', 'cima del picco')
    grid = np.linspace(x.min(), x.max(), 1200)
    if fixed:
        under = np.interp(grid, x, base)
    else:
        under = fit.get('c0') + (fit.get('c1') * grid if p['baseline'] == 'linear' else 0 * grid)
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
        components[f'{ctx.tr("peak", "picco")} {i}'] = under + shape_value(shape, grid, a, m, w)
        top = float(np.interp(m, grid, under)) + a
        text = short(m) if p['labels'] == 'position' else f'{short(m)} (FWHM {short(fwhm)})'
        labels.append({xname: m, top_name: top, 'text': text})
    total = sum(areas)
    for row, area in zip(rows, areas):
        row[ctx.tr('area %', 'area %')] = 100 * area / total if total else np.nan

    r = ctx.result()
    r.value(ctx.tr('peaks fitted', 'picchi adattati'), len(peaks), key='n_peaks')
    r.value(ctx.tr('peak shape', 'forma dei picchi'), ctx.tr(shape, 'gaussiana' if shape == 'gaussian' else 'lorentziana'))
    r.value(ctx.tr('baseline', 'linea di base'), b.label if fixed else
            ctx.tr('straight line fitted with the peaks', 'retta adattata con i picchi') if p['baseline'] == 'linear' else
            ctx.tr('constant fitted with the peaks', 'costante adattata con i picchi'))
    r.value('R²', fit.get('r2'), key='r2')
    for row in rows:
        r.value(ctx.tr(f'peak {row["#"]}: centre', f'picco {row["#"]}: centro'), row[ctx.tr('centre', 'centro')],
                row[ctx.tr('± centre', '± centro')], key=f'centre{row["#"]}')
    r.table(ctx.tr('Peaks', 'Picchi'), rows)
    r.keep('peaks', rows)
    r.text(ctx.tr('Area errors ignore the correlation between height and width (approximate).',
                  'Gli errori sulle aree trascurano la correlazione tra altezza e larghezza (approssimati).'))
    if fixed:
        r.cite(*b.refs)
        r.text(ctx.tr('Errors are conditional on the baseline: it is subtracted first and not fitted.',
                      'Gli errori sono condizionati alla linea di base: è sottratta prima e non adattata.'))
    if fit.get('r2') is not None and fit.get('r2') < 0.95:
        r.text(ctx.tr('R² < 0.95: some peaks may be missing or have another shape; try a lower prominence, more peaks, '
                      'the other shape, or check the baseline.',
                      'R² < 0,95: potrebbero mancare picchi o avere un’altra forma; prova una prominenza minore, più '
                      'picchi, l’altra forma, o controlla la linea di base.'))

    # On the figure: baseline, total fit (with band), each peak dashed, values above the peaks — all on the
    # level of the original signal, so they sit on the spectrum as drawn.
    base_name = ctx.tr('baseline', 'linea di base')
    first = len(r.overlays)
    if fixed:
        r.overlay(pd.DataFrame({xname: x, base_name: base}), xname, base_name, label=base_name,
                  style={'linestyle': ':', 'linewidth': 0.9})
    curve = fit.overlays[0]
    frame = curve['frame'].copy()
    if fixed:
        lift = np.interp(frame[curve['x']].to_numpy(), x, base)
        for col in (curve['y'], curve['lo'], curve['hi']):
            if col is not None:
                frame[col] = frame[col] + lift
    r.overlay(frame, curve['x'], curve['y'], curve['lo'], curve['hi'], label=ctx.tr('fit (sum of peaks)', 'fit (somma dei picchi)'),
              band_label=curve['band_label'])
    for name, values in components.items():
        r.overlay(pd.DataFrame({xname: grid, name: values}), xname, name, label=name,
                  style={'linestyle': '--', 'linewidth': 0.8, 'legend': False})
    if p['labels'] != 'none':
        r.overlay(pd.DataFrame(labels), xname, top_name, label=ctx.tr('peak values', 'valori dei picchi'), text='text',
                  style={'linestyle': 'none', 'marker': 'v', 'markersize': 3, 'color': 'text'})
    r.include(fit, f'{step} 3 · ' + ctx.tr('joint fit', 'fit congiunto'))
    r.include(found, f'{step} 2 · ' + ctx.tr('peak finding', 'ricerca dei picchi'))
    fit_col = fit.get('fit_column')
    data = pd.DataFrame({xname: x, yname: y, fit_col: fit.frame[fit_col].to_numpy() + base})
    plot_y = [yname]
    if fixed:
        data[base_name] = base
        plot_y.append(base_name)
    r.data(data, name=ctx.tr('peak fit', 'fit dei picchi') + f' · {yname}',
           plot={'kind': 'line', 'x': xname, 'y': plot_y,
                 'series': {yname: {'linestyle': 'none', 'marker': 'o', 'markersize': 2}},
                 'overlays': [{'ref': k} for k in range(first, len(r.overlays))]})
    return r
