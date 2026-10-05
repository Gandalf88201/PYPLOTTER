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
