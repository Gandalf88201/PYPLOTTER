"""Synthetic example data sets (generated here, so they carry no third-party licence)."""
import numpy as np
import pandas as pd

NAMES = ('spectra', 'ir', 'kinetics', 'groups', 'surface', 'cloud')


def make(name):
    rng = np.random.default_rng(42)
    if name == 'spectra':
        wl = np.linspace(350, 750, 801)

        def peak(c, w, a):
            return a * np.exp(-0.5 * ((wl - c) / w) ** 2)
        return pd.DataFrame({
            'Wavelength (nm)': wl,
            'Sample A': peak(450, 18, 1.0) + peak(520, 25, 0.45) + rng.normal(0, 0.008, wl.size),
            'Sample B': peak(470, 20, 0.8) + peak(600, 30, 0.6) + rng.normal(0, 0.008, wl.size),
            'Sample C': peak(500, 15, 0.55) + peak(650, 22, 0.9) + rng.normal(0, 0.008, wl.size),
        })
    if name == 'ir':
        # Mid-IR transmittance from Lorentzian bands placed like those of a small hydroxy ester (O–H, C–H,
        # C=O, C–O): an invented example, not a measured spectrum.
        nu = np.arange(4000.0, 399.0, -2.0)

        def band(c, fwhm, a):
            return a / (1 + ((nu - c) / (fwhm / 2)) ** 2)
        absorbance = sum(band(*b) for b in [
            (3450, 260, 0.30), (2985, 30, 0.22), (2940, 26, 0.15), (2880, 24, 0.08), (1738, 26, 0.95),
            (1455, 22, 0.16), (1375, 16, 0.22), (1265, 34, 0.45), (1210, 30, 0.40), (1130, 28, 0.55),
            (1045, 24, 0.35), (860, 18, 0.10)])
        absorbance = absorbance + 0.02 + rng.normal(0, 0.002, nu.size)
        return pd.DataFrame({'Wavenumber (cm⁻¹)': nu, 'Transmittance (%)': 100 * 10 ** -absorbance})
    if name == 'kinetics':
        t = np.linspace(0, 60, 25)
        c = 1.0 * np.exp(-t / 14.0)
        err = 0.02 + 0.04 * c
        return pd.DataFrame({'Time (min)': t, 'Concentration (mM)': c + rng.normal(0, err), 'Std. dev. (mM)': err,
                             'Temperature (°C)': 25 + 0.05 * t + rng.normal(0, 0.1, t.size)})
    if name == 'groups':
        groups = ['Control', 'Treatment A', 'Treatment B', 'Treatment C']
        means = [10.0, 12.5, 9.0, 14.0]
        rows = [(g, 'Batch 1' if i % 2 else 'Batch 2', rng.normal(m, 1.5)) for g, m in zip(groups, means) for i in range(30)]
        return pd.DataFrame(rows, columns=['Group', 'Batch', 'Response (a.u.)'])
    if name == 'surface':
        x, y = np.meshgrid(np.linspace(-3, 3, 61), np.linspace(-2, 2, 41))
        z = np.sin(x) * np.cos(y * 1.5) + 0.3 * np.exp(-((x - 1) ** 2 + y ** 2))
        return pd.DataFrame({'x': x.ravel(), 'y': y.ravel(), 'z': z.ravel()})
    if name == 'cloud':
        n = 4000
        x = rng.normal(0, 1, n)
        y = 2.1 * x + rng.normal(0, 1.2, n)
        return pd.DataFrame({'x': x, 'y': y, 'z': x * y + rng.normal(0, 0.5, n),
                             'w': rng.gamma(2, 1.5, n), 'class': rng.choice(['α', 'β', 'γ'], n)})
    raise ValueError(f'Unknown sample: {name}')
