"""Backend tests: python -m unittest discover -s tests (needs numpy, pandas, matplotlib)."""
import gzip
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pyplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pyplotter import catalog, exporters, plotting, readers, samples, smart  # noqa: E402
from pyplotter.modules import ModuleManager, PipProgress, Job, version_tuple, load_registry  # noqa: E402


def has(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


class TempDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding='utf-8')
        return p


class TestCatalog(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(catalog.detect_format('a.CSV'), ('text', None))
        self.assertEqual(catalog.detect_format('a.csv.gz'), ('text', 'gzip'))
        self.assertEqual(catalog.detect_format('a.xlsx'), ('excel', None))
        self.assertEqual(catalog.detect_format('a.nc'), ('netcdf', None))
        self.assertEqual(catalog.detect_format('a.parquet.gz'), (None, 'gzip'))
        self.assertEqual(catalog.detect_format('a.weird')[0], None)

    def test_requirements_known(self):
        ids = {m['id'] for m in load_registry()}
        for info in list(catalog.FILE_FORMATS.values()) + list(catalog.KINDS.values()) + \
                list(catalog.STYLES.values()) + list(catalog.EXPORT_FORMATS.values()):
            self.assertTrue(set(info['requires']) <= ids, info)
        self.assertEqual(catalog.requirements_for('strip', 'nature', 'cmc.batlow', 'html'),
                         ['seaborn', 'scienceplots', 'cmcrameri', 'plotly'])

    def test_registry_open_source(self):
        for m in load_registry():
            self.assertTrue(m.get('license'), m['id'])
            self.assertNotIn('proprietary', m['license'].lower())


class TestModules(unittest.TestCase):
    def test_versions(self):
        self.assertLess(version_tuple('1.2'), version_tuple('1.10'))
        self.assertLess(version_tuple('2.0rc1'), version_tuple('2.0'))
        self.assertEqual(version_tuple('3.8.0'), version_tuple('3.8'))

    def test_progress_parser(self):
        job = Job('install', 'x')
        p = PipProgress(job, 2)
        for line in ['Collecting a', '  Downloading a-1.0-py3-none-any.whl.metadata (1 kB)',
                     'Downloading a-1.0-py3-none-any.whl (10 MB)', 'Progress 5 of 10']:
            p.feed(line)
        self.assertAlmostEqual(job.progress, 0.15 + 0.70 * 0.25, places=3)
        p.feed('  Using cached b-2.0-py3-none-any.whl (1 MB)')
        self.assertAlmostEqual(job.progress, 0.85, places=3)
        p.feed('Installing collected packages: a, b')
        self.assertEqual(job.phase, 'installing')

    def test_status_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            mm = ModuleManager(state_dir=tmp, online=False)
            st = mm.status()
            self.assertTrue(st['core_ready'])
            self.assertEqual(len(st['modules']), len(mm.modules))
            self.assertTrue(all('license' in r for r in st['modules']))


class TestReaders(TempDir):
    def test_italian_csv(self):
        p = self.write('it.csv', 'Tempo;Valore\n0,5;1,25\n1,0;2,5\n1,5;3,75\n')
        df, opts = readers.read_table(p, 'text')
        self.assertEqual(opts['sep'], ';')
        self.assertEqual(opts['decimal'], ',')
        self.assertEqual(list(df.columns), ['Tempo', 'Valore'])
        self.assertAlmostEqual(df['Valore'].iloc[2], 3.75)

    def test_whitespace_with_comment_header(self):
        p = self.write('spec.dat', '# measured 2024\n# wl  abs\n400 0.1\n401 0.2\n402 0.15\n')
        df, opts = readers.read_table(p, 'text')
        self.assertEqual(opts['sep'], 'whitespace')
        self.assertEqual(list(df.columns), ['wl', 'abs'])
        self.assertEqual(len(df), 3)

    def test_headerless_csv_and_dates(self):
        p = self.write('h.csv', '1,2,3\n4,5,6\n')
        df, _ = readers.read_table(p, 'text')
        self.assertEqual(list(df.columns), ['col1', 'col2', 'col3'])
        p = self.write('d.csv', 'date,v\n2024-01-01,1\n2024-01-02,2\n')
        df, _ = readers.read_table(p, 'text')
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df['date']))

    def test_gzip_tsv(self):
        p = self.dir / 'x.tsv.gz'
        with gzip.open(p, 'wt') as fh:
            fh.write('a\tb\n1\t2\n3\t4\n')
        df, opts = readers.read_table(p, 'text', compression='gzip')
        self.assertEqual(opts['sep'], '\t')
        self.assertEqual(df['b'].sum(), 6)

    def test_json_variants(self):
        p = self.write('a.json', json.dumps({'x': [1, 2, 3], 'y': [4, 5, 6]}))
        self.assertEqual(readers.read_table(p, 'json')[0].shape, (3, 2))
        p = self.write('b.json', json.dumps({'data': [{'x': 1, 'm': {'y': 2}}, {'x': 2, 'm': {'y': 3}}]}))
        self.assertIn('m.y', readers.read_table(p, 'json')[0].columns)
        p = self.write('c.jsonl', '{"x": 1}\n{"x": 2}\n')
        self.assertEqual(len(readers.read_table(p, 'jsonl')[0]), 2)

    def test_numpy_sqlite_zip(self):
        np.savez(self.dir / 'a.npz', first=np.arange(5), grid=np.ones((4, 3)))
        self.assertEqual(readers.list_tables(self.dir / 'a.npz', 'numpy'), ['first', 'grid'])
        self.assertEqual(readers.read_table(self.dir / 'a.npz', 'numpy', 'grid')[0].shape, (4, 3))
        db = self.dir / 'a.sqlite'
        with sqlite3.connect(db) as con:
            con.execute('CREATE TABLE "my table" (x REAL, y REAL)')
            con.executemany('INSERT INTO "my table" VALUES (?, ?)', [(1, 2), (3, 4)])
        self.assertEqual(readers.list_tables(db, 'sqlite'), ['my table'])
        self.assertEqual(readers.read_table(db, 'sqlite', 'my table')[0]['y'].sum(), 6)
        zp = self.dir / 'a.zip'
        with zipfile.ZipFile(zp, 'w') as zf:
            zf.writestr('folder/data.csv', 'x,y\n1,2\n')
            zf.writestr('__MACOSX/._data.csv', 'junk')
        self.assertEqual(readers.list_tables(zp, 'zip'), ['folder/data.csv'])
        self.assertEqual(readers.read_table(zp, 'zip', 'folder/data.csv')[0].shape, (1, 2))

    def test_jcamp(self):
        p = self.write('s.jdx', '##TITLE=test\n##JCAMP-DX=4.24\n##XUNITS=1/CM\n##YUNITS=ABSORBANCE\n'
                                '##FIRSTX=400\n##LASTX=405\n##NPOINTS=6\n##XFACTOR=1\n##YFACTOR=0.5\n'
                                '##XYDATA=(X++(Y..Y))\n400 2 4 6\n403 8 10 12\n##END=\n')
        df, _ = readers.read_table(p, 'jcamp')
        self.assertEqual(list(df.columns), ['x (1/CM)', 'y (ABSORBANCE)'])
        np.testing.assert_allclose(df.iloc[:, 0], [400, 401, 402, 403, 404, 405])
        np.testing.assert_allclose(df.iloc[:, 1], [1, 2, 3, 4, 5, 6])

    @unittest.skipUnless(has('openpyxl'), 'openpyxl not installed')
    def test_excel(self):
        p = self.dir / 'a.xlsx'
        with pd.ExcelWriter(p) as w:
            pd.DataFrame({'x': [1, 2]}).to_excel(w, sheet_name='One', index=False)
            pd.DataFrame({'y': [3, 4]}).to_excel(w, sheet_name='Two', index=False)
        self.assertEqual(readers.list_tables(p, 'excel'), ['One', 'Two'])
        self.assertEqual(list(readers.read_table(p, 'excel', 'Two')[0].columns), ['y'])


class TestSmart(unittest.TestCase):
    def test_mapping(self):
        df = samples.make('spectra')
        cols = smart.profile(df)
        m = smart.default_mapping(cols, len(df))
        self.assertEqual(m['x'], 'Wavelength (nm)')
        self.assertEqual(m['kind'], 'line')
        self.assertEqual(len(m['y']), 3)

    def test_errors_and_groups(self):
        df = samples.make('kinetics')
        m = smart.default_mapping(smart.profile(df), len(df))
        self.assertEqual(m['yerr'], None)       # two Y columns: no automatic error bars
        cols = smart.profile(df)
        recs = smart.recommend(cols, {'x': 'Time (min)', 'y': ['Concentration (mM)'], 'yerr': 'Std. dev. (mM)'}, len(df))
        self.assertEqual(recs[0]['kind'], 'errorbar')
        df = samples.make('groups')
        m = smart.default_mapping(smart.profile(df), len(df))
        self.assertEqual(m['x'], 'Group')
        self.assertIn(m['kind'], ('bar', 'box'))
        df = samples.make('surface')
        m = smart.default_mapping(smart.profile(df), len(df))
        self.assertEqual((m['x'], m['y'], m['z'], m['kind']), ('x', ['y'], 'z', 'contour'))
        df = samples.make('cloud')
        recs = smart.recommend(smart.profile(df), {'x': 'x', 'y': ['y']}, len(df))
        self.assertIn(recs[0]['kind'], ('scatter', 'hexbin'))


class TestPlotting(unittest.TestCase):
    CASES = {
        'line': ('spectra', {'x': 'Wavelength (nm)', 'y': ['Sample A', 'Sample B']}),
        'scatter': ('cloud', {'x': 'x', 'y': ['y'], 'z': 'z'}),
        'step': ('spectra', {'x': 'Wavelength (nm)', 'y': ['Sample A']}),
        'area': ('spectra', {'x': 'Wavelength (nm)', 'y': ['Sample A', 'Sample B'], 'style': {'stacked': True}}),
        'errorbar': ('kinetics', {'x': 'Time (min)', 'y': ['Concentration (mM)'], 'yerr': 'Std. dev. (mM)',
                                  'y2': ['Temperature (°C)']}),
        'regression': ('cloud', {'x': 'x', 'y': ['y'], 'style': {'fit': 'poly', 'fit_degree': 2}}),
        'stem': ('kinetics', {'x': 'Time (min)', 'y': ['Concentration (mM)']}),
        'polar': ('spectra', {'x': 'Wavelength (nm)', 'y': ['Sample A']}),
        'bar': ('groups', {'x': 'Group', 'y': ['Response (a.u.)'], 'hue': 'Batch'}),
        'barh': ('groups', {'x': 'Group', 'y': ['Response (a.u.)']}),
        'box': ('groups', {'x': 'Group', 'y': ['Response (a.u.)']}),
        'violin': ('groups', {'x': 'Group', 'y': ['Response (a.u.)']}),
        'pie': ('groups', {'x': 'Group', 'y': []}),
        'hist': ('cloud', {'y': ['x', 'y']}),
        'kde': ('cloud', {'y': ['w'], 'hue': 'class'}),
        'ecdf': ('cloud', {'y': ['x']}),
        'heatmap': ('surface', {'x': 'x', 'y': ['y'], 'z': 'z'}),
        'contour': ('surface', {'x': 'x', 'y': ['y'], 'z': 'z'}),
        'hexbin': ('cloud', {'x': 'x', 'y': ['y']}),
        'hist2d': ('cloud', {'x': 'x', 'y': ['y']}),
        'corr': ('cloud', {'y': ['x', 'y', 'z', 'w']}),
        'pairplot': ('cloud', {'y': ['x', 'y', 'w'], 'hue': 'class'}),
    }

    def test_every_kind_renders(self):
        missing = set(catalog.KINDS) - set(self.CASES) - {'strip', 'swarm'}
        self.assertFalse(missing)
        for kind, (sample, spec) in self.CASES.items():
            with self.subTest(kind=kind):
                spec = dict(spec, kind=kind)
                png = plotting.render(samples.make(sample), spec, 'png', dpi=80)
                self.assertTrue(png.startswith(b'\x89PNG'))

    def test_export_formats_and_size(self):
        df = samples.make('spectra')
        spec = {'kind': 'line', 'x': 'Wavelength (nm)', 'y': ['Sample A'],
                'figure': {'width': 89, 'height': 60, 'units': 'mm', 'dpi': 300}}
        png = plotting.render(df, spec, 'png')
        w = int.from_bytes(png[16:20], 'big')
        self.assertEqual(w, round(89 / 25.4 * 300))      # exact journal width at 300 dpi
        self.assertTrue(plotting.render(df, spec, 'pdf').startswith(b'%PDF'))
        self.assertIn(b'<svg', plotting.render(df, spec, 'svg'))
        self.assertTrue(plotting.render(df, spec, 'eps').startswith(b'%!PS'))
        self.assertTrue(plotting.render(df, spec, 'tiff')[:2] in (b'II', b'MM'))
        self.assertTrue(plotting.render(df, spec, 'jpg').startswith(b'\xff\xd8'))

    def test_customisation(self):
        df = samples.make('spectra')
        spec = {'kind': 'line', 'x': 'Wavelength (nm)', 'y': ['Sample A', 'Sample B'],
                'series': {'Sample A': {'color': '#ff0000', 'label': 'Ref', 'linestyle': '--', 'marker': 'o'}},
                'text': {'title': 'Absorbance $\\lambda$', 'font': 'DejaVu Serif', 'bold_labels': True},
                'axes': {'yscale': 'log', 'xmin': 400, 'xmax': 700, 'grid': 'both', 'spines': 'open', 'sci': True},
                'legend': {'loc': 'outside right', 'frame': True}, 'style': {'palette': 'tol-bright', 'base': 'ggplot'}}
        self.assertTrue(plotting.render(df, spec, 'png', dpi=60).startswith(b'\x89PNG'))

    def test_several_files(self):
        a = samples.make('spectra')
        b, c = a.copy(), a.copy()
        b['Sample A'] *= 0.7
        c['Sample A'] *= 0.4
        spec = {'kind': 'line', 'x': 'Wavelength (nm)', 'y': ['Sample A'], 'name': 'B1.dat',
                'extra': [{'id': 'e1', 'name': 'B2.dat', 'x': 'Wavelength (nm)', 'y': ['Sample A']},
                          {'id': 'e2', 'name': 'B3.dat', 'x': 'Wavelength (nm)', 'y': ['Sample A']}]}
        extra = {'e1': b, 'e2': c}
        svg = plotting.render(a, spec, 'svg', extra_data=extra).decode()
        for name in ('B1.dat', 'B2.dat', 'B3.dat'):
            self.assertIn(name, svg)                    # one legend entry per file
        svg = plotting.render(a, dict(spec, layout={'mode': 'panels', 'ncols': 2}), 'svg', extra_data=extra).decode()
        self.assertIn('(c) B3.dat', svg)                # one lettered panel per file
        for kind in ('scatter', 'errorbar', 'hist', 'kde', 'ecdf'):
            with self.subTest(kind=kind):
                self.assertTrue(plotting.render(a, dict(spec, kind=kind), 'png', dpi=40, extra_data=extra)
                                .startswith(b'\x89PNG'))
        # a missing file is skipped; the script bundle carries the other files
        self.assertTrue(plotting.render(a, spec, 'png', dpi=40).startswith(b'\x89PNG'))
        import subprocess
        data = exporters.script_bundle(a, spec, 'fig', load_registry(), extra_data=extra)
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
            self.assertTrue((Path(tmp) / 'fig' / 'extra_2.csv').exists())
            out = subprocess.run([sys.executable, 'make_figure.py'], cwd=Path(tmp) / 'fig', capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)

    def test_bad_spec(self):
        with self.assertRaises(plotting.SpecError):
            plotting.render(samples.make('spectra'), {'kind': 'line', 'y': ['nope']}, 'png')
        with self.assertRaises(plotting.SpecError):
            plotting.render(samples.make('spectra'), {'kind': 'line', 'y': []}, 'png')

    def test_fit(self):
        x = np.linspace(1, 10, 50)
        f, eq, r2 = plotting.fit_curve(x, 3 * x + 2, 'linear')
        self.assertAlmostEqual(r2, 1.0)
        self.assertIn('3x', eq)
        f, eq, r2 = plotting.fit_curve(x, 2 * np.exp(0.3 * x), 'exp')
        self.assertAlmostEqual(f(0.0), 2.0, places=6)

    def test_script_bundle_runs(self):
        import subprocess
        df = samples.make('kinetics')
        spec = {'kind': 'errorbar', 'x': 'Time (min)', 'y': ['Concentration (mM)'], 'yerr': 'Std. dev. (mM)'}
        data = exporters.script_bundle(df, spec, 'fig', load_registry())
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
            self.assertIn('Harris', (Path(tmp) / 'fig' / 'REFERENCES.txt').read_text())
            out = subprocess.run([sys.executable, 'make_figure.py'], cwd=Path(tmp) / 'fig', capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue((Path(tmp) / 'fig' / 'figure.pdf').is_file())


if __name__ == '__main__':
    unittest.main()
