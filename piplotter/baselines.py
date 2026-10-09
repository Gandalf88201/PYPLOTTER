"""Baseline (background) under a spectrum or signal: set by hand with anchor points, or estimated.

Shared by the Baseline analysis and by Peak finding, Peak fit and Integral: an analysis lists
``params(...)`` among its parameters and calls ``ctx.baseline(x, y, p)`` (that is, ``estimate``).

Methods
- points      anchor points you choose (clicked on the figure or typed), joined by straight lines or by a
              smooth monotone curve (PCHIP; Fritsch & Carlson 1980); a point clicked or written with its y
              is used where it is, a point written with x alone takes the height of the signal there;
- poly        a straight line (or a constant, or a low-degree polynomial) under the signal, fitted with the
              asymmetric truncated quadratic cost of Mazet et al. (2005): points above the line by more than
              3 σ of the noise (the peaks) do not count, so the line stays flat where the signal is flat;
- arpls       asymmetrically reweighted penalized least squares (Baek et al. 2015);
- asls        asymmetric least squares (Eilers & Boelens 2005);
- snip        statistics-sensitive non-linear iterative peak clipping (Ryan et al. 1988; Morháč et al. 1997);
- rubberband  lower convex hull of the signal (Andrew 1979).

Spectra whose peaks point down (transmittance, reflectance dips) are handled by estimating the baseline of
−y: the automatic methods always look for a baseline *under* the peaks. ``bl_peaks`` says which way the
peaks point; 'auto' decides from the shape of the signal (see ``peaks_point_down``).
"""
import math

import numpy as np

METHODS = ('points', 'poly', 'arpls', 'asls', 'snip', 'rubberband')
AUTOMATIC = METHODS[1:]

REFS = {
    'poly': 'Mazet, V., Carteret, C., Brie, D., Idier, J. & Humbert, B. Background removal from spectra by designing '
            'and minimising a non-quadratic cost function. Chemom. Intell. Lab. Syst. 76, 121–133 (2005). '
            'doi:10.1016/j.chemolab.2004.10.003',
    'smooth': 'Fritsch, F. N. & Carlson, R. E. Monotone piecewise cubic interpolation. SIAM J. Numer. Anal. 17, '
              '238–246 (1980). doi:10.1137/0717021',
    'arpls': 'Baek, S.-J., Park, A., Ahn, Y.-J. & Choi, J. Baseline correction using asymmetrically reweighted '
             'penalized least squares smoothing. Analyst 140, 250–257 (2015). doi:10.1039/C4AN01061B',
    'asls': 'Eilers, P. H. C. & Boelens, H. F. M. Baseline correction with asymmetric least squares smoothing. '
            'Leiden University Medical Centre report (2005).',
    'snip': 'Ryan, C. G., Clayton, E., Griffin, W. L., Sie, S. H. & Cousens, D. R. SNIP, a statistics-sensitive '
            'background treatment for the quantitative analysis of PIXE spectra in geoscience applications. '
            'Nucl. Instrum. Methods Phys. Res. B 34, 396–402 (1988). doi:10.1016/0168-583X(88)90063-8',
    'snip2': 'Morháč, M., Kliman, J., Matoušek, V., Veselský, M. & Turzo, I. Background elimination methods for '
             'multidimensional coincidence γ-ray spectra. Nucl. Instrum. Methods Phys. Res. A 401, 113–132 (1997). '
             'doi:10.1016/S0168-9002(97)01023-1',
    'rubberband': 'Andrew, A. M. Another efficient algorithm for convex hulls in two dimensions. Inf. Process. '
                  'Lett. 9, 216–219 (1979). doi:10.1016/0020-0190(79)90072-3',
}

CHOICES = [
    ('points', {'en': 'anchor points (click on the figure)', 'it': 'punti di ancoraggio (clic sulla figura)'}),
    ('poly', {'en': 'automatic: straight line under the signal (or polynomial)', 'it': 'automatica: retta sotto il segnale (o polinomio)'}),
    ('arpls', {'en': 'automatic: arPLS (follows curved backgrounds)', 'it': 'automatica: arPLS (segue fondi curvi)'}),
    ('asls', {'en': 'automatic: asymmetric least squares', 'it': 'automatica: minimi quadrati asimmetrici'}),
    ('snip', {'en': 'automatic: SNIP (peak clipping)', 'it': 'automatica: SNIP (taglio dei picchi)'}),
    ('rubberband', {'en': 'automatic: rubber band (convex hull)', 'it': 'automatica: elastico (inviluppo convesso)'}),
]


def params(extra=(), default='poly'):
    """The baseline parameters of an analysis.

    extra: [(value, {'en', 'it'})] choices listed before the methods (e.g. 'none'), which the analysis
    handles itself; default: the choice selected at first. The ids are the same in every analysis, so
    the baseline defined once is offered again in the next analysis.
    """
    when = {'baseline': ['points']}
    return [
        {'id': 'baseline', 'type': 'choice', 'default': default, 'label': {'en': 'Baseline', 'it': 'Linea di base'},
         'choices': [{'value': v, 'label': lab} for v, lab in list(extra) + CHOICES]},
        {'id': 'bl_points', 'type': 'points', 'optional': True, 'show_if': when,
         'label': {'en': 'Anchor points: x and y (or x alone), one per line', 'it': 'Punti di ancoraggio: x e y (o solo x), uno per riga'},
         'help': {'en': 'Click them on the figure where the signal lies on its baseline, between and around the peaks: '
                        'each click keeps its x and its y. A point written with x alone takes the height of the signal there.',
                  'it': 'Cliccali sulla figura dove il segnale poggia sulla linea di base, tra e attorno ai picchi: ogni '
                        'clic tiene la sua x e la sua y. Un punto scritto con la sola x prende l’altezza del segnale lì.'}},
        {'id': 'bl_curve', 'type': 'choice', 'default': 'linear', 'show_if': when,
         'label': {'en': 'Between the points', 'it': 'Tra i punti'},
         'choices': [{'value': 'linear', 'label': {'en': 'straight lines', 'it': 'segmenti di retta'}},
                     {'value': 'smooth', 'label': {'en': 'smooth curve (PCHIP)', 'it': 'curva liscia (PCHIP)'}}]},
        {'id': 'bl_degree', 'type': 'int', 'default': 1, 'min': 0, 'max': 6, 'show_if': {'baseline': ['poly']},
         'label': {'en': 'Shape (0 = flat, 1 = straight line, 2–6 = gently curved)', 'it': 'Forma (0 = piatta, 1 = retta, 2–6 = leggermente curva)'}},
        {'id': 'bl_stiffness', 'type': 'float', 'default': 7, 'min': 0, 'max': 12, 'show_if': {'baseline': ['arpls', 'asls']},
         'label': {'en': 'Stiffness (lower follows the signal more; 9 almost straight)', 'it': 'Rigidità (più bassa segue di più il segnale; 9 quasi retta)'},
         'help': {'en': 'If the baseline climbs into broad peaks, raise it.', 'it': 'Se la linea di base sale dentro picchi larghi, alzala.'}},
        {'id': 'bl_asymmetry', 'type': 'float', 'default': 0.01, 'min': 1e-5, 'max': 0.5, 'show_if': {'baseline': ['asls']},
         'label': {'en': 'Asymmetry p (smaller = lower baseline)', 'it': 'Asimmetria p (più piccola = linea più bassa)'}},
        {'id': 'bl_width', 'type': 'float', 'optional': True, 'min': 0, 'show_if': {'baseline': ['snip']},
         'label': {'en': 'Widest peak, in x units (empty = 1/6 of the range)', 'it': 'Picco più largo, in unità di x (vuoto = 1/6 dell’intervallo)'}},
        {'id': 'bl_peaks', 'type': 'choice', 'default': 'auto', 'show_if': {'baseline': list(AUTOMATIC)},
         'label': {'en': 'The peaks point', 'it': 'I picchi sono rivolti'},
         'choices': [{'value': 'auto', 'label': {'en': 'recognise from the signal', 'it': 'riconoscilo dal segnale'}},
                     {'value': 'up', 'label': {'en': 'up (absorbance, counts, intensity)', 'it': 'in su (assorbanza, conteggi, intensità)'}},
                     {'value': 'down', 'label': {'en': 'down (transmittance, dips)', 'it': 'in giù (trasmittanza, avvallamenti)'}}]},
    ]


class Baseline:
    """values: the baseline at each x (same order as the x given); label: method and settings in words;
    refs: references to cite; anchors: (n, 2) array of the anchor points used, or None; below: fraction
    of the points clearly on the wrong side of the baseline — under it, or above it when the peaks point
    down (above 5 % the baseline is probably misplaced there)."""

    def __init__(self, values, label, refs, anchors=None, below=0.0, down=False):
        self.values, self.label, self.refs, self.anchors, self.below = values, label, refs, anchors, below
        self.down = down             # the peaks point down: the baseline lies above the signal


def estimate(x, y, p, tr=lambda en, it=None: en):
    """The baseline chosen in the parameters p (see params), or None when p['baseline'] is not a method."""
    method = p.get('baseline')
    if method not in METHODS:
        return None
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.size < 3:
        raise ValueError(tr('A baseline needs at least three points.', 'Una linea di base richiede almeno tre punti.'))
    order = np.argsort(x, kind='stable')
    xs, ys = x[order], y[order]
    anchors = None
    want = p.get('bl_peaks') or 'auto'
    down = want == 'down' or (want == 'auto' and peaks_point_down(ys))
    sign = -1.0 if down else 1.0                  # the automatic methods work under the peaks: flip dips
    if method == 'points':
        b, anchors = _through_points(xs, ys, p, tr)
        curve = p.get('bl_curve') == 'smooth'
        label = tr(f'{len(anchors)} anchor points, ' + ('smooth curve (PCHIP)' if curve else 'straight lines'),
                   f'{len(anchors)} punti di ancoraggio, ' + ('curva liscia (PCHIP)' if curve else 'segmenti di retta'))
        refs = [REFS['smooth']] if curve and len(anchors) > 2 else []
    elif method == 'poly':
        degree = 1 if p.get('bl_degree') is None else int(p['bl_degree'])
        b = sign * robust_poly(xs, sign * ys, degree)
        shape = {0: ('flat (constant)', 'piatta (costante)'), 1: ('straight line', 'retta')}.get(
            degree, (f'polynomial of degree {degree}', f'polinomio di grado {degree}'))
        label = tr(f'{shape[0]} under the signal', f'{shape[1]} sotto il segnale')
        refs = [REFS['poly']]
    elif method in ('arpls', 'asls'):
        stiff = 7.0 if p.get('bl_stiffness') is None else float(p['bl_stiffness'])
        # λ grows as n⁴ so that a stiffness means the same baseline whatever the number of points.
        lam = 10 ** stiff * (xs.size / 1000) ** 4
        if method == 'arpls':
            b = sign * arpls(sign * ys, lam)
            label = f'arPLS, λ = {lam:.3g}'
        else:
            asym = 0.01 if p.get('bl_asymmetry') is None else float(p['bl_asymmetry'])
            b = sign * asls(sign * ys, lam, asym)
            label = f'AsLS, λ = {lam:.3g}, p = {asym:g}'
        refs = [REFS[method]]
    elif method == 'snip':
        step = float(np.median(np.diff(xs))) or 1.0
        width = p.get('bl_width') or (xs[-1] - xs[0]) / 6
        half = int(min(max(1, math.ceil(width / (2 * abs(step)))), (xs.size - 1) // 2))
        b = sign * snip(sign * ys, half)
        label = tr(f'SNIP, window ± {half} points', f'SNIP, finestra ± {half} punti')
        refs = [REFS['snip'], REFS['snip2']]
    else:
        b = sign * rubberband(xs, sign * ys)
        label = tr('rubber band (convex hull)', 'elastico (inviluppo convesso)')
        refs = [REFS['rubberband']]
    if down and method != 'points':
        label += tr(', peaks pointing down', ', picchi rivolti in giù')
    values = np.empty_like(b)
    values[order] = b
    return Baseline(values, label, refs, anchors, below_fraction(sign * ys, sign * b), down)


def peaks_point_down(y):
    """True when the signal looks like dips from a high level (transmittance) rather than peaks from a low one:
    most points sit near the top of the range and a few go far below them."""
    lo, mid, hi = np.percentile(np.asarray(y, float), [2, 50, 98])
    return (mid - lo) > 1.5 * (hi - mid)


def below_fraction(y, b):
    """Fraction of points under the baseline by more than 3 σ of the point-to-point noise."""
    noise = 1.4826 * np.median(np.abs(np.diff(y) - np.median(np.diff(y)))) / math.sqrt(2) if y.size > 2 else 0.0
    return float(np.mean(y - b < -3 * noise)) if noise > 0 else float(np.mean(y - b < 0))


# ------------------------------------------------------------------ methods (x sorted, ascending)
def _through_points(x, y, p, tr):
    pts = p.get('bl_points') or []
    if not pts:
        raise ValueError(tr('No anchor points yet: press “Pick on the figure” and click where the signal lies on its '
                            'baseline, or write the x values; or choose an automatic baseline.',
                            'Nessun punto di ancoraggio: premi “Scegli sulla figura” e clicca dove il segnale poggia '
                            'sulla linea di base, oppure scrivi i valori di x; o scegli una linea di base automatica.'))
    half = max(2, x.size // 400)               # a point written without y: median of a few points of the signal
    found = {}
    for px, py in pts:
        if py is not None:
            v = float(py)                       # clicked (or written) height: used as it is
        else:
            i = int(np.clip(np.searchsorted(x, px), 0, x.size - 1))
            if i > 0 and abs(x[i - 1] - px) < abs(x[i] - px):
                i -= 1
            v = float(np.median(y[max(0, i - half):i + half + 1]))
        found.setdefault(float(px), []).append(v)
    ax = np.array(sorted(found))
    ay = np.array([np.mean(found[k]) for k in ax])
    if ax.size == 1:
        b = np.full(x.size, ay[0])
    elif p.get('bl_curve') == 'smooth' and ax.size > 2:
        from scipy.interpolate import PchipInterpolator
        b = PchipInterpolator(ax, ay, extrapolate=False)(x)
        b[x < ax[0]], b[x > ax[-1]] = ay[0], ay[-1]       # beyond the first and last point: level
    else:
        b = np.interp(x, ax, ay)
    return b, np.column_stack([ax, ay])


def noise_sigma(y):
    """Standard deviation of the point-to-point noise (robust: median absolute deviation of the differences)."""
    d = np.diff(np.asarray(y, float))
    return 1.4826 * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(2) if d.size > 1 else 0.0


def robust_poly(x, y, degree=1, k=3.0, max_iter=300):
    """Polynomial of the given degree under the peaks (Mazet et al. 2005, asymmetric truncated quadratic cost).

    Minimises Σ φ(yᵢ − b(xᵢ)) with φ(r) = r² for r < s and s² above: points higher than the baseline by more
    than s = k·σ (σ of the noise) cost a constant, so the peaks do not pull the line up, while the points
    below it pull it down as in least squares. Solved by half-quadratic iterations (each one a least-squares
    fit in which the points above the threshold are replaced by the current baseline), started from the
    lower half of the points; the iterate with the lowest cost is kept."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    degree = int(min(max(degree, 0), 6, x.size - 1))
    span = (x.max() - x.min()) / 2 or 1.0
    V = np.vander((x - (x.max() + x.min()) / 2) / span, degree + 1)       # scaled x: a well-conditioned fit
    scale = float(np.ptp(y)) or 1.0
    s = max(k * noise_sigma(y), 1e-6 * scale)
    low = y <= np.median(y)
    coef = np.linalg.lstsq(V[low], y[low], rcond=None)[0]
    best, best_cost = coef, np.inf
    for _ in range(max_iter):
        fit = V @ coef
        r = y - fit
        cost = float(np.sum(np.where(r < s, r * r, s * s)))
        if cost < best_cost:
            best, best_cost = coef, cost
        new = np.linalg.lstsq(V, np.where(r >= s, fit, y), rcond=None)[0]
        if np.max(np.abs(V @ (new - coef))) <= 1e-9 * scale:
            best = new if float(np.sum(np.where(y - V @ new < s, (y - V @ new) ** 2, s * s))) <= best_cost else best
            break
        coef = new
    return V @ best


def _second_difference(n):
    from scipy import sparse
    return sparse.diags([np.ones(n - 2), -2 * np.ones(n - 2), np.ones(n - 2)], [0, 1, 2], shape=(n - 2, n))


def arpls(y, lam, ratio=1e-6, max_iter=100):
    """Asymmetrically reweighted penalized least squares (Baek et al. 2015): a smooth curve under the signal,
    weights set by a logistic function of the residuals below it."""
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    n = y.size
    D = _second_difference(n)
    H = lam * (D.T @ D)
    w = np.ones(n)
    z = y
    for _ in range(max_iter):
        z = spsolve(sparse.csc_matrix(sparse.diags(w) + H), w * y)
        d = y - z
        neg = d[d < 0]
        if neg.size < 2 or neg.std() == 0:
            break
        m, s = neg.mean(), neg.std()
        w_new = 1 / (1 + np.exp(np.clip(2 * (d - (2 * s - m)) / s, -700, 700)))
        done = np.linalg.norm(w - w_new) / np.linalg.norm(w) < ratio
        w = w_new
        if done:
            break
    return z


def asls(y, lam, p=0.01, max_iter=50):
    """Asymmetric least squares (Eilers & Boelens 2005): points above the curve weigh p, below 1 − p."""
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    n = y.size
    D = _second_difference(n)
    H = lam * (D.T @ D)
    w = np.ones(n)
    z = y
    for _ in range(max_iter):
        z = spsolve(sparse.csc_matrix(sparse.diags(w) + H), w * y)
        w_new = np.where(y > z, p, 1 - p)
        if np.array_equal(w_new, w):
            break
        w = w_new
    return z


def snip(y, half):
    """SNIP (Ryan et al. 1988): each point is replaced by the mean of its neighbours at ±k when that is lower,
    for k = 1 … half; peaks narrower than about 2·half points are clipped away."""
    v = np.array(y, dtype=float)
    n = v.size
    for k in range(1, half + 1):
        v[k:n - k] = np.minimum(v[k:n - k], (v[:n - 2 * k] + v[2 * k:]) / 2)
    return v


def rubberband(x, y):
    """Lower convex hull of the points (monotone chain, Andrew 1979), joined by straight lines."""
    hull = []
    for i in range(x.size):
        while len(hull) >= 2:
            a, b = hull[-2], hull[-1]
            if (x[b] - x[a]) * (y[i] - y[a]) - (y[b] - y[a]) * (x[i] - x[a]) <= 0:
                hull.pop()
            else:
                break
        hull.append(i)
    return np.interp(x, x[hull], y[hull])
