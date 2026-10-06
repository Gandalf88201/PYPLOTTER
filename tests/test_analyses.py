"""Analysis plugins: built-ins run on sample data, user plugins load, override and report errors."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pyplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

from pyplotter import plotting, plugins, samples  # noqa: E402


def has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


@unittest.skipUnless(has('scipy') and has('statsmodels'), 'scipy and statsmodels needed')
class TestBuiltins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pm = plugins.PluginManager(user_dir=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    CASES = [
        ('fit_curve', 'kinetics', {'x': 'Time (min)', 'y': 'Concentration (mM)', 'sigma': 'Std. dev. (mM)', 'model': 'exp_decay'}),
        ('fit_curve', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A', 'model': 'gaussian', 'xmin': 400, 'xmax': 490}),
        ('fit_curve', 'kinetics', {'x': 'Time (min)', 'y': 'Concentration (mM)', 'model': 'custom',
                                   'formula': 'a*exp(-x/tau) + c', 'p0': 'tau=10'}),
        ('autocorrelation', 'spectra', {'y': 'Sample A', 'partial': True}),
        ('block_average', 'cloud', {'y': 'x'}),
        ('cross_correlation', 'spectra', {'a': 'Sample A', 'b': 'Sample B'}),
        ('descriptive', 'groups', {'columns': ['Response (a.u.)'], 'group': 'Group'}),
        ('normality', 'cloud', {'y': 'x'}),
        ('compare_groups', 'groups', {'value': 'Response (a.u.)', 'group': 'Group'}),
        ('correlation', 'cloud', {'columns': ['x', 'y', 'z']}),
        ('regression', 'cloud', {'y': 'y', 'predictors': ['x', 'class']}),
        ('distribution_fit', 'cloud', {'y': 'w'}),
        ('smoothing', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A'}),
        ('spectrum', 'spectra', {'y': 'Sample A'}),
        ('peaks', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample C'}),
        ('integrate', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample A'}),
        ('recipe_gaussian', 'cloud', {'y': 'w'}),
        ('recipe_series_mean', 'kinetics', {'y': 'Concentration (mM)', 'x': 'Time (min)'}),
        ('recipe_compare_groups', 'groups', {'value': 'Response (a.u.)', 'group': 'Group'}),
        ('recipe_xy_relation', 'cloud', {'x': 'x', 'y': 'y'}),
        ('recipe_peak_fit', 'spectra', {'x': 'Wavelength (nm)', 'y': 'Sample C'}),
        ('recipe_kinetics', 'kinetics', {'x': 'Time (min)', 'y': 'Concentration (mM)', 'sigma': 'Std. dev. (mM)'}),
        ('recipe_equilibration', 'cloud', {'y': 'x'}),
    ]

    def test_all_builtins_loaded(self):
        self.assertFalse(self.pm.errors)
        self.assertEqual({c[0] for c in self.CASES}, set(self.pm.plugins))
        for p in self.pm.plugins.values():
            self.assertTrue(p['references'], p['id'])

    def test_each_runs_and_plots(self):
        for pid, sample, params in self.CASES:
            with self.subTest(pid=pid, params=params):
                _, _, res = self.pm.run(pid, samples.make(sample), params, lang='it')
                self.assertTrue(res.summary or res.tables)
                if res.frame is not None:
                    png = plotting.render(res.frame, res.plot, 'png', dpi=40)
                    self.assertTrue(png.startswith(b'\x89PNG'))

    def test_fit_recovers_parameters(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(0, 50, 200)
        df = pd.DataFrame({'t': x, 's': 3.0 * np.exp(-x / 7.0) + 0.5})
        _, _, res = self.pm.run('fit_curve', df, {'x': 't', 'y': 's', 'model': 'exp_decay'})
        params = {row[0]: row[1] for row in res.tables[0]['rows']}
        self.assertAlmostEqual(params['tau'], 7.0, places=4)
        self.assertAlmostEqual(params['A'], 3.0, places=4)

    def test_recipe_gaussian_recovers_parameters(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(3).normal(108, 11, 20000)})
        _, _, res = self.pm.run('recipe_gaussian', df, {'y': 'v', 'series': False})
        self.assertAlmostEqual(res.get('mu'), 108, delta=0.5)
        self.assertAlmostEqual(res.get('sigma'), 11, delta=0.5)
        self.assertAlmostEqual(res.get('fwhm'), 2 * np.sqrt(2 * np.log(2)) * res.get('sigma'), places=9)
        self.assertGreater(res.get('r2'), 0.98)
        self.assertFalse(res.overlays[0]['on_figure'])          # the curve belongs to the histogram plot
        self.assertEqual(res.plot['overlays'], [{'ref': 0}])

    def test_recipes_use_builtin_steps(self):
        """A customised copy of an analysis must not change what a recipe computes."""
        import numpy as np
        import pandas as pd
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'fit_curve.py').write_text(
                "PLUGIN = {'id': 'fit_curve', 'name': 'broken fit', 'params': []}\n"
                "def run(df, p, ctx):\n    raise RuntimeError('user copy used')\n", encoding='utf-8')
            pm = plugins.PluginManager(user_dir=tmp)
            self.assertTrue(pm.plugins['fit_curve']['overrides'])
            df = pd.DataFrame({'v': np.random.default_rng(4).normal(0, 1, 2000)})
            _, _, res = pm.run('recipe_gaussian', df, {'y': 'v', 'series': False})
            self.assertAlmostEqual(res.get('mu'), 0, delta=0.2)

    def test_fit_histogram_mode(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(5).normal(5, 2, 5000)})
        hist_fig = {'kind': 'hist', 'y': ['v'], 'style': {'bins': 30, 'density': False}}
        _, vals, res = self.pm.run('fit_curve', df, {'y': 'v', 'model': 'gaussian'}, spec=hist_fig)
        self.assertEqual(vals['source'], 'auto')
        self.assertTrue(res.overlays[0]['on_figure'])           # same bins and counts as the figure
        width = np.ptp(df['v']) / 30
        self.assertAlmostEqual(res.get('A'), 5000 * width / (2 * np.sqrt(2 * np.pi)), delta=15)
        self.assertAlmostEqual(res.get('sigma'), 2, delta=0.1)
        # other bins than the figure: the curve stays on the result's own plot
        _, _, res = self.pm.run('fit_curve', df, {'y': 'v', 'model': 'gaussian', 'bins': 50}, spec=hist_fig)
        self.assertFalse(res.overlays[0]['on_figure'])
        # a line figure: Y against X as before
        _, _, res = self.pm.run('fit_curve', df.assign(t=np.arange(5000)), {'x': 't', 'y': 'v', 'model': 'linear'},
                                spec={'kind': 'line'})
        self.assertIsNone(res.get('bins'))

    def test_recipe_peak_fit_recovers_peaks(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(300, 550, 600)
        g = lambda a, m, f: a * np.exp(-(x - m) ** 2 / (2 * (f / 2.3548) ** 2))
        y = g(1.0, 400, 20) + g(0.6, 430, 30) + 0.1 + 0.0004 * (x - 300) + np.random.default_rng(0).normal(0, 0.01, x.size)
        _, _, res = self.pm.run('recipe_peak_fit', pd.DataFrame({'nm': x, 'A': y}), {'x': 'nm', 'y': 'A'})
        self.assertEqual(res.get('n_peaks'), 2)
        self.assertAlmostEqual(res.get('centre1'), 400, delta=0.3)
        self.assertAlmostEqual(res.get('centre2'), 430, delta=0.5)
        labels = res.overlays[-1]
        self.assertEqual(labels['text'], 'text')
        self.assertEqual(list(labels['frame']['text']), ['400', '430.1'])

    def test_recipe_kinetics_finds_order(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(0)
        t = np.linspace(0, 30, 25)
        first = pd.DataFrame({'t': t, 'c': 2.0 * np.exp(-0.15 * t) + 0.1 + rng.normal(0, 0.02, t.size)})
        _, _, res = self.pm.run('recipe_kinetics', first, {'x': 't', 'y': 'c'}, lang='en')
        self.assertTrue(res.get('order').startswith('first'))
        self.assertAlmostEqual(res.get('k'), 0.15, delta=0.01)
        self.assertAlmostEqual(res.get('t_half'), np.log(2) / res.get('k'), places=9)
        second = pd.DataFrame({'t': t, 'c': 2.0 / (1 + 2.0 * 0.05 * t) + rng.normal(0, 0.005, t.size)})
        _, _, res = self.pm.run('recipe_kinetics', second, {'x': 't', 'y': 'c'}, lang='en')
        self.assertTrue(res.get('order').startswith('second'))
        self.assertAlmostEqual(res.get('k'), 0.05, delta=0.004)

    def test_recipe_equilibration(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(1)
        n = 6000
        e = np.zeros(n)
        for i in range(1, n):
            e[i] = 0.9 * e[i - 1] + rng.normal(0, 1)
        y = -50 + 30 * np.exp(-np.arange(n) / 300) + e
        _, _, res = self.pm.run('recipe_equilibration', pd.DataFrame({'E': y}), {'y': 'E'})
        self.assertTrue(500 < res.get('t0') < 2000, res.get('t0'))
        self.assertAlmostEqual(res.get('mean'), -50, delta=4 * res.error('mean') + 0.2)
        # a column that is not a time axis is not used as time
        shuffled = pd.DataFrame({'E': y, 'noise': np.random.default_rng(2).normal(size=n)})
        _, _, res = self.pm.run('recipe_equilibration', shuffled, {'y': 'E', 'x': 'noise'}, lang='en')
        self.assertTrue(any('not used as time' in t for t in res.texts))
        self.assertTrue(500 < res.get('t0') < 2000)
        self.assertFalse(any(o['on_figure'] for o in res.overlays))

    def test_recipe_kinetics_any_time_origin(self):
        """Data recorded from t = 100 give the same k as data from t = 0; growth gives a positive k."""
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(0)
        t = np.linspace(100, 160, 25)
        first = 2.0 * np.exp(-0.1 * (t - 100)) + 0.1 + rng.normal(0, 0.01, t.size)
        _, _, res = self.pm.run('recipe_kinetics', pd.DataFrame({'t': t, 'c': first}), {'x': 't', 'y': 'c'}, lang='en')
        self.assertTrue(res.get('order').startswith('first'), res.get('order'))
        self.assertAlmostEqual(res.get('k'), 0.1, delta=0.005)
        zero = 5 - 0.05 * (t - 100) + rng.normal(0, 0.005, t.size)
        _, _, res = self.pm.run('recipe_kinetics', pd.DataFrame({'t': t, 'c': zero}),
                                {'x': 't', 'y': 'c', 'order': '0'}, lang='en')
        self.assertAlmostEqual(res.get('k'), 0.05, delta=0.002)
        self.assertAlmostEqual(res.get('t_half'), 50, delta=2)            # A0 / 2k from the first time
        growth = 2.0 - 2.0 / (1 + 2.0 * 0.05 * (t - 100)) + rng.normal(0, 0.005, t.size)
        _, _, res = self.pm.run('recipe_kinetics', pd.DataFrame({'t': t, 'c': growth}),
                                {'x': 't', 'y': 'c', 'order': '2'}, lang='en')
        self.assertAlmostEqual(res.get('k'), 0.05, delta=0.005)           # positive, not −0.05

    def test_names_that_collide_with_result_columns(self):
        import numpy as np
        import pandas as pd
        v = np.random.default_rng(1).normal(1.0, 0.05, 3000)
        _, _, res = self.pm.run('recipe_gaussian', pd.DataFrame({'density': v}), {'y': 'density', 'series': False})
        self.assertAlmostEqual(res.get('mu'), 1.0, delta=0.01)
        self.assertAlmostEqual(res.get('sigma'), 0.05, delta=0.005)
        _, _, res = self.pm.run('fit_curve', pd.DataFrame({'density': v}), {'source': 'hist', 'y': 'density',
                                                                           'model': 'gaussian'})
        self.assertEqual(len(set(res.frame.columns)), len(res.frame.columns))
        self.assertEqual(res.frame.columns[0], 'density')
        x = np.linspace(0, 10, 50)
        df = pd.DataFrame({'t': x, 'fit': 2 * x + 1})                     # a column called "fit"
        _, _, res = self.pm.run('fit_curve', df, {'source': 'xy', 'x': 't', 'y': 'fit', 'model': 'linear'})
        self.assertTrue(np.allclose(res.frame['fit'], 2 * x + 1))           # the data, not the fitted curve
        self.assertIn(res.get('fit_column'), res.frame.columns)

    def test_weighted_fit_aic_uses_chi2(self):
        import numpy as np
        import pandas as pd
        x = np.linspace(0, 10, 40)
        err = np.where(x < 5, 0.1, 2.0)
        y = 3 * x + 1 + np.random.default_rng(2).normal(0, err)
        _, _, res = self.pm.run('fit_curve', pd.DataFrame({'x': x, 'y': y, 'e': err}),
                                {'source': 'xy', 'x': 'x', 'y': 'y', 'sigma': 'e', 'model': 'linear'})
        resid = y - (res.get('a') * x + res.get('b'))
        self.assertAlmostEqual(res.get('aic'), float(np.sum((resid / err) ** 2)) + 4, places=6)

    def test_equilibration_inefficiency_matches_reference(self):
        """The vectorised statistical inefficiency equals the plain loop (as in pymbar)."""
        import numpy as np
        mod = self.pm.builtins['recipe_equilibration']['module']

        def reference(a):
            a = np.asarray(a, float) - np.mean(a)
            n, var = a.size, a.var()
            f = np.fft.rfft(a, 2 * n)
            c = np.fft.irfft(f * np.conj(f))[:n] / np.arange(n, 0, -1) / var
            g, t = 1.0, 1
            while t < n - 1:
                if c[t] <= 0 and t > 3:
                    break
                g += 2 * c[t] * (1 - t / n)
                t += 1
            return max(1.0, g)
        rng = np.random.default_rng(3)
        for phi in (0.0, 0.5, 0.95):
            e = np.zeros(3000)
            for i in range(1, e.size):
                e[i] = phi * e[i - 1] + rng.normal()
            self.assertAlmostEqual(mod.inefficiency(e), reference(e), places=9)

    def test_equilibration_layers_need_the_figure_x(self):
        """No time column in the recipe but a time axis in the figure: layers stay on the result plot."""
        import numpy as np
        import pandas as pd
        y = -50 + 30 * np.exp(-np.arange(2000) / 100) + np.random.default_rng(4).normal(0, 1, 2000)
        df = pd.DataFrame({'time (ps)': np.arange(2000) * 2.0, 'E': y})
        _, _, res = self.pm.run('recipe_equilibration', df, {'y': 'E', 'x': None}, spec={'x': 'time (ps)'})
        self.assertFalse(any(o['on_figure'] for o in res.overlays))
        _, _, res = self.pm.run('recipe_equilibration', df, {'y': 'E', 'x': 'time (ps)'}, spec={'x': 'time (ps)'})
        self.assertTrue(all(o['on_figure'] for o in res.overlays))

    def test_new_plugin_title_is_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            pm = plugins.PluginManager(user_dir=tmp)
            out = pm.create('media \\ "prova" l\'altra')
            self.assertEqual(out['errors'], [])
            p = [q for q in pm.plugins.values() if q['source'] == 'user'][0]
            self.assertEqual(p['name']['en'], 'media \\ "prova" l\'altra')

    def test_distribution_fit_normal(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(2).normal(108, 11, 5000)})
        _, _, res = self.pm.run('distribution_fit', df, {'y': 'v', 'dists': 'norm, gamma'})
        cols = res.tables[0]['columns']
        self.assertNotIn('note', cols)          # a failing distribution reports its error in 'note'
        best = dict(zip(cols, res.tables[0]['rows'][0]))
        self.assertGreater(best['KS p'], 0.01)

    def test_block_average_white_noise(self):
        import numpy as np
        import pandas as pd
        df = pd.DataFrame({'v': np.random.default_rng(1).normal(0, 1, 4096)})
        _, _, res = self.pm.run('block_average', df, {'y': 'v'})
        g = next(s['value'] for s in res.summary if 'inefficiency' in s['label'])
        self.assertLess(g, 1.6)          # uncorrelated data: g ≈ 1

    def test_fit_overlay_band_and_render(self):
        import io as _io
        import zipfile as _zip
        import numpy as np
        import pandas as pd
        from pyplotter import exporters
        from pyplotter.modules import load_registry
        rng = np.random.default_rng(3)
        x = np.linspace(0, 40, 60)
        sig = np.full(x.size, 0.03)
        df = pd.DataFrame({'t': x, 's': 2.0 * np.exp(-x / 9.0) + 0.1 + rng.normal(0, 0.03, x.size), 'e': sig})
        _, _, res = self.pm.run('fit_curve', df, {'x': 't', 'y': 's', 'sigma': 'e', 'model': 'exp_decay'})
        ov = res.overlays[0]
        curve = ov['frame']
        truth = 2.0 * np.exp(-curve['t'] / 9.0) + 0.1
        inside = ((curve[ov['lo']] <= truth) & (truth <= curve[ov['hi']])).mean()
        self.assertGreater(inside, 0.8)              # the 95 % band covers the true curve
        self.assertEqual(res.plot['kind'], 'errorbar')
        spec = {'kind': 'errorbar', 'x': 't', 'y': ['s'], 'yerr': 'e',
                'overlays': [{'id': 'o1', 'dataset_id': 'd', 'x': 't', 'y': 'fit', 'lo': ov['lo'], 'hi': ov['hi'],
                              'label': 'fit', 'band_label': '95% CI'}]}
        png = plotting.render(df, spec, 'png', dpi=50, overlay_data={'o1': curve})
        self.assertTrue(png.startswith(b'\x89PNG'))
        svg = plotting.render(df, spec, 'svg', overlay_data={'o1': curve}).decode()
        self.assertIn('95% CI', svg)
        # missing overlay data is skipped, not an error
        self.assertTrue(plotting.render(df, spec, 'png', dpi=40).startswith(b'\x89PNG'))
        data = exporters.script_bundle(df, spec, 'fig', load_registry(), overlay_data={'o1': curve})
        with tempfile.TemporaryDirectory() as tmp:
            _zip.ZipFile(_io.BytesIO(data)).extractall(tmp)
            self.assertTrue((Path(tmp) / 'fig' / 'overlay_1.csv').exists())
            run = subprocess.run([sys.executable, 'make_figure.py'], cwd=Path(tmp) / 'fig', capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_regression_and_block_overlays(self):
        _, _, res = self.pm.run('regression', samples.make('cloud'), {'y': 'y', 'predictors': ['x']})
        self.assertEqual(len(res.overlays), 2)       # confidence and prediction bands
        ci, pi = res.overlays
        width_ci = (ci['frame'][ci['hi']] - ci['frame'][ci['lo']]).mean()
        width_pi = (pi['frame'][pi['hi']] - pi['frame'][pi['lo']]).mean()
        self.assertLess(width_ci, width_pi)
        _, _, res = self.pm.run('block_average', samples.make('spectra'), {'y': 'Sample A', 'x': 'Wavelength (nm)'})
        self.assertEqual(res.overlays[0]['x'], 'Wavelength (nm)')

    def test_role_defaults(self):
        df = samples.make('kinetics')
        spec = {'x': 'Time (min)', 'y': ['Concentration (mM)'], 'yerr': 'Std. dev. (mM)'}
        _, values, _ = self.pm.run('fit_curve', df, {'model': 'linear'}, spec=spec)
        self.assertEqual((values['x'], values['y'], values['sigma']), ('Time (min)', 'Concentration (mM)', 'Std. dev. (mM)'))

    def test_formula_is_sandboxed(self):
        from importlib import import_module  # noqa: F401
        mod = self.pm.plugins['fit_curve']['module']
        for bad in ('__import__("os").system("x")', 'x.__class__', 'open("f")', 'lambda: x'):
            with self.assertRaises(ValueError):
                mod.compile_formula(bad)


class TestUserPlugins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pm = plugins.PluginManager(user_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_template_creates_working_plugin(self):
        r = self.pm.create('Mio test')
        self.assertEqual(r['errors'], [])
        pid = Path(r['file']).stem
        self.assertEqual(self.pm.plugins[pid]['name'], {'en': 'Mio test', 'it': 'Mio test'})
        _, _, res = self.pm.run(pid, samples.make('spectra'), {'x': 'Wavelength (nm)', 'y': 'Sample A'})
        self.assertEqual(res.frame.shape[1], 3)

    def test_customize_overrides_builtin(self):
        r = self.pm.customize('block_average')
        self.assertTrue((Path(self.tmp.name) / r['file']).exists())
        p = self.pm.plugins['block_average']
        self.assertEqual((p['source'], p['overrides']), ('user', True))
        self.pm.disable(r['file'])
        self.assertEqual(self.pm.plugins['block_average']['source'], 'builtin')
        self.assertTrue((Path(self.tmp.name) / 'block_average.py.disabled').exists())

    def test_errors_are_reported_not_raised(self):
        r = self.pm.save('broken.py', 'PLUGIN = {"id": "broken"}\ndef run(df, p, ctx)\n    pass\n')
        self.assertIn('SyntaxError', r['errors'][0]['error'])
        r = self.pm.save('noid.py', 'PLUGIN = {}\ndef run(df, p, ctx):\n    return ctx.result()\n')
        self.assertTrue(r['errors'])
        self.assertIn('fit_curve', self.pm.plugins)        # built-ins still there

    def test_unsafe_file_names_rejected(self):
        for name in ('../evil.py', 'a/b.py', 'x.sh', '.hidden.py'):
            with self.assertRaises(plugins.PluginError):
                self.pm.save(name, '')


class TestPersistentToken(unittest.TestCase):
    def test_token_survives_restart(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as home:
            code = ('import os, sys, runpy; sys.argv=["x"]; '
                    'g = runpy.run_path(r"%s", run_name="not_main"); print(g["persistent_token"]())' % (root / 'start_pyplotter.py'))
            env = dict(os.environ, PYPLOTTER_HOME=home, PYPLOTTER_NO_VENV='1')
            a = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True).stdout.strip()
            b = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True).stdout.strip()
            self.assertTrue(len(a) >= 32)
            self.assertEqual(a, b)
            if os.name != 'nt':
                self.assertEqual(os.stat(Path(home) / 'token').st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
