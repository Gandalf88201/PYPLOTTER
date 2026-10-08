"""Backend tests: python -m unittest discover -s tests (needs numpy, pandas, matplotlib)."""
from contextlib import closing
import gzip
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pyplotter.modules import clean_appledouble  # noqa: E402
clean_appledouble()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib  # noqa: E402

from pyplotter import catalog, exporters, licenses, modules, plotting, readers, samples, smart  # noqa: E402
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
            self.assertTrue(all(r['works'] is None for r in st['modules']))   # not checked yet

    def test_import_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / 'registry.json'
            reg.write_text(json.dumps({'schema': 'pyplotter-registry/1', 'modules': [
                {'id': 'numpy', 'pip': 'numpy', 'import': 'numpy', 'category': 'core'},
                # installed according to pip, but the import fails
                {'id': 'broken', 'pip': 'numpy', 'import': 'pyplotter_no_such_module', 'category': 'core'},
                {'id': 'absent', 'pip': 'pyplotter-no-such-dist', 'import': 'x', 'category': 'core'},
            ]}), encoding='utf-8')
            mm = ModuleManager(registry_path=reg, state_dir=tmp, online=False)
            mm.verify_async()
            for _ in range(600):
                if mm.check_state['state'] == 'done':
                    break
                time.sleep(0.1)
            rows = {r['id']: r for r in mm.status()['modules']}
            self.assertEqual(mm.status()['checks']['state'], 'done')
            self.assertIs(rows['numpy']['works'], True)
            self.assertIs(rows['broken']['works'], False)
            self.assertIn('ModuleNotFoundError', rows['broken']['import_error'])
            self.assertIsNone(rows['absent']['works'])
            self.assertEqual(mm._specs(['numpy'], False, reinstall=True), [f'numpy=={np.__version__}'])



class TestUserModules(unittest.TestCase):
    """Modules the user adds from PyPI, with pip replaced by a fake (no network)."""

    def test_package_names(self):
        for ok in ('lmfit', 'scikit-learn', 'zope.interface', 'A_b9'):
            self.assertEqual(modules.check_package_name(f' {ok} '), ok)
        for bad in ('', 'lmfit==1.0', 'lmfit>=1', 'x[extra]', 'git+https://github.com/a/b', 'https://x.org/p.whl',
                    '../pkg', '/tmp/pkg', '-r', '--index-url=http://evil', 'a b', 'x;rm', 'pkg-', 'a' * 101):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                modules.check_package_name(bad)
        self.assertEqual(modules.canonical('Scikit_Learn.x'), 'scikit-learn-x')

    def test_licences(self):
        c = licenses.classify
        cases = [
            (('MIT',), 'osi'), (('MIT OR LicenseRef-Proprietary',), 'osi'), (('GPL-3.0-only AND MIT',), 'osi'),
            (('Apache-2.0 WITH LLVM-exception',), 'osi'), (('LicenseRef-Proprietary',), 'proprietary'),
            (('CC-BY-NC-4.0',), 'not_osi'), (('Weird-1.0',), 'unknown'),
            (('BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0',), 'osi'), (('CC0-1.0',), 'not_osi'),
            (('MIT-CMU',), 'osi'),
            (('', ['License :: OSI Approved :: BSD License']), 'osi'),
            (('', ['License :: Other/Proprietary License']), 'proprietary'),
            (('', ['License :: Freeware']), 'not_osi'),
            (('', [], 'BSD 3-Clause License'), 'osi'), (('', [], 'Apache Software License 2.0'), 'osi'),
            (('', [], 'Copyright (c) 2024 Someone\n\nPermission is hereby granted, free of charge, to any person'), 'osi'),
            (('', [], 'Proprietary. All rights reserved.'), 'proprietary'), (('', [], ''), 'unknown'),
        ]
        for args, want in cases:
            with self.subTest(args=args):
                self.assertEqual(c(*args)['status'], want)
        self.assertEqual(c('', [], 'Copyright 2024 X\n\nPermission is hereby granted, free of charge')['license'], 'MIT')
        # a pip report entry and an installed distribution's metadata
        self.assertEqual(licenses.from_metadata({'license_expression': 'BSD-3-Clause'})['status'], 'osi')
        self.assertEqual(licenses.from_metadata(modules.metadata.distribution('numpy').metadata)['status'], 'osi')

    def _manager(self, tmp, report, installed, users=(), check=None):
        """A ModuleManager whose pip only records its arguments and answers the dry run with `report`
        (installing the module installs everything in it); check: what the import check finds."""
        mm = ModuleManager(state_dir=tmp, online=True)
        mm.calls = []
        mm._prepare_pip = lambda job: None
        mm.verify_async = lambda force=False: None
        mm._run_check = lambda names, deep: check or {'ok': True, 'error': '', 'failed': [], 'parts': 1}

        def fake_pip(job, args, on_line=None):
            mm.calls.append(args)
            if '--dry-run' in args:
                Path(args[args.index('--report') + 1]).write_text(json.dumps({'install': report}), encoding='utf-8')
            elif args[0] == 'install':
                for spec in [a for a in args if '==' in a]:
                    name, version = spec.split('==')
                    installed[modules.canonical(name)] = version
                if '--upgrade-strategy' in args:
                    installed.update({modules.canonical(r['metadata']['name']): r['metadata']['version'] for r in report})
            elif args[0] == 'uninstall':
                for name in args[args.index('--yes') + 1:]:
                    installed.pop(modules.canonical(name), None)
            return 0
        mm._pip = fake_pip
        real_version = modules.installed_version

        def version(dist):
            return installed.get(modules.canonical(dist)) if modules.canonical(dist) in ('propkg', 'helper') \
                else real_version(dist)

        def info(name):
            v = installed.get(modules.canonical(name))
            return v and {'name': 'propkg', 'version': v, 'license': 'LicenseRef-Proprietary', 'status': 'proprietary',
                          'summary': 'A test package', 'imports': ['propkg']}
        patches = [mock.patch.object(modules, 'installed_version', version), mock.patch.object(modules, 'dist_info', info),
                   mock.patch.object(modules, 'dependents', lambda name: list(users))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return mm

    @staticmethod
    def _wait(job):
        for _ in range(200):
            if job.state != 'running':
                return job
            time.sleep(0.02)
        raise AssertionError('job did not finish')

    REPORT = [
        {'requested': True, 'metadata': {'name': 'propkg', 'version': '1.0', 'summary': 'A test package',
                                         'license_expression': 'LicenseRef-Proprietary'}},
        {'requested': False, 'metadata': {'name': 'helper', 'version': '2.1', 'classifier': ['License :: OSI Approved :: MIT License']}},
    ]

    def test_inspect_confirm_install_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = {}
            mm = self._manager(tmp, self.REPORT, installed)
            with self.assertRaises(ValueError):
                mm.start_inspect('matplotlib')                      # in the registry: installed from the list
            with self.assertRaises(ValueError):
                mm.start_inspect('propkg --pre')
            job = self._wait(mm.start_inspect('propkg'))
            self.assertEqual(job.state, 'done', job.error)
            r = job.result
            self.assertTrue(r['needs_confirm'])
            self.assertEqual([(p['name'], p['status']) for p in r['packages']], [('propkg', 'proprietary'), ('helper', 'osi')])
            self.assertEqual(mm.calls[0][-3:], ['--upgrade-strategy', 'only-if-needed', 'propkg'])
            with self.assertRaises(ValueError):
                mm.start_user_install(job.id)                       # licence not confirmed
            with self.assertRaises(ValueError):
                mm.start_user_install('no-such-job', accept=True)
            done = self._wait(mm.start_user_install(job.id, accept=True))
            self.assertEqual(done.state, 'done', done.error)
            self.assertEqual(mm.calls[-1], ['install', '--progress-bar', 'raw', '--upgrade-strategy', 'only-if-needed',
                                            'propkg==1.0'])         # the version reviewed, as one argument
            saved = json.loads((Path(tmp) / 'user-modules.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['schema'], 'pyplotter-user-modules/1')
            rec = saved['modules'][0]
            self.assertEqual((rec['pip'], rec['version'], rec['status'], rec['accepted']), ('propkg', '1.0', 'proprietary', True))
            self.assertEqual([p['name'] for p in rec['packages']], ['propkg', 'helper'])
            mm.set_user_cite('propkg', 'Doe, J. Propkg (2024).')
            self.assertEqual(mm.user_citations(['propkg', 'scipy']), ['Doe, J. Propkg (2024).'])
            row = mm.status()['user_modules'][0]
            self.assertEqual((row['installed'], row['imports'], row['cite']), ('1.0', ['propkg'], 'Doe, J. Propkg (2024).'))
            self.assertEqual(mm.missing(['propkg']), [])

            # A new environment: the record stays, the module is missing and can be installed again.
            installed.clear()
            mm2 = self._manager(tmp, self.REPORT, installed)
            self.assertIsNone(mm2.status()['user_modules'][0]['installed'])
            self.assertEqual(mm2.missing(['propkg']), ['propkg'])
            with self.assertRaises(modules.MissingUserModules):
                mm2.require(['propkg'])
            installed['propkg'] = '1.0'

            mm3 = self._manager(tmp, self.REPORT, installed, users=['other-package'])
            with self.assertRaises(ValueError):
                mm3.start_uninstall('propkg')                       # another package needs it
            mm4 = self._manager(tmp, self.REPORT, installed)
            with self.assertRaises(ValueError):
                mm4.start_uninstall('numpy')                        # not one of the user's modules
            gone = self._wait(mm4.start_uninstall('propkg'))
            self.assertEqual(gone.state, 'done', gone.error)
            self.assertEqual(mm4.calls[-1], ['uninstall', '--yes', 'propkg'])
            self.assertEqual(json.loads((Path(tmp) / 'user-modules.json').read_text(encoding='utf-8'))['modules'], [])

    def test_unusable_install_is_undone(self):
        """A module that does not import once installed is removed again, with what came with it, and
        the packages it upgraded go back to their versions."""
        with tempfile.TemporaryDirectory() as tmp:
            installed = {'helper': '2.0'}                                   # upgraded to 2.1 by the install
            broken = {'ok': False, 'error': "ModuleNotFoundError: No module named 'pkg_resources'",
                      'failed': [['propkg.io', "ModuleNotFoundError: No module named 'pkg_resources'"]], 'parts': 1}
            mm = self._manager(tmp, self.REPORT, installed, check=broken)
            job = self._wait(mm.start_inspect('propkg'))
            done = self._wait(mm.start_user_install(job.id, accept=True))
            self.assertEqual(done.state, 'error')
            self.assertIn('installation was undone', done.error)
            self.assertTrue(done.result['rolled_back'])
            self.assertEqual(done.result['failed'], broken['failed'])
            self.assertEqual(installed, {'helper': '2.0'})                   # as before
            self.assertIn(['uninstall', '--yes', 'propkg'], mm.calls)
            self.assertIn(['install', '--no-deps', 'helper==2.0'], mm.calls)
            self.assertEqual(mm.user, {})                                    # not recorded
            self.assertFalse((Path(tmp) / 'user-modules.json').exists())

            # Working in part is kept, with the parts that fail.
            part = {'ok': True, 'error': '', 'failed': [['propkg.qt', "ModuleNotFoundError: No module named 'PyQt5'"]],
                    'parts': 4}
            mm2 = self._manager(tmp, self.REPORT, installed, check=part)
            job = self._wait(mm2.start_inspect('propkg'))
            done = self._wait(mm2.start_user_install(job.id, accept=True))
            self.assertEqual(done.state, 'done', done.error)
            self.assertEqual((done.result['failed'], installed['propkg']), (part['failed'], '1.0'))
            row = mm2.status()['user_modules'][0]
            self.assertEqual((row['works'], row['import_failed'], row['import_parts']), (True, part['failed'], 4))

            # Analyses that import the failing part are stopped, the others run.
            self.assertEqual(mm2.unusable(['propkg'], ['propkg', 'propkg.qt.widgets']), [part['failed'][0]])
            self.assertEqual(mm2.unusable(['propkg'], ['propkg', 'propkg.core']), [])
            self.assertEqual(mm2.unusable(['scipy'], ['scipy.optimize']), [])
            mm2.checks['user:propkg'] = {**broken, 'version': '1.0', 'deep': True}
            self.assertEqual(mm2.unusable(['propkg'], []), [['propkg', broken['error']]])

    def test_integration_plugins(self):
        from pyplotter import plugins
        with tempfile.TemporaryDirectory() as tmp:
            pm = plugins.PluginManager(user_dir=tmp)
            made = pm.create_integration('uvvispy', 'uvvispy')
            self.assertEqual(made, {'file': 'uvvispy_tools.py', 'errors': []})
            p = pm.plugins['uvvispy_tools']
            self.assertEqual((p['requires'], p['source']), (['uvvispy'], 'user'))
            self.assertIn('uvvispy', p['imports'])                   # imported inside run(): PyPlotter still starts
            self.assertEqual(pm.create_integration('uvvispy', 'uvvispy')['file'], 'uvvispy_tools_2.py')
            self.assertEqual(pm.create_integration('3d.Tools', 'tools3d')['file'], 'm_3d_tools_tools.py')
            for bad in (('../x', 'x'), ('x', 'not-an-import'), ('', 'x')):
                with self.subTest(bad=bad), self.assertRaises(plugins.PluginError):
                    pm.create_integration(*bad)
            (Path(tmp) / 'uses_parts.py').write_text(
                'from uvvispy import processing\nimport numpy.linalg as la\nfrom . import x\n', encoding='utf-8')
            self.assertEqual(plugins.imported_modules(Path(tmp) / 'uses_parts.py'),
                             ['numpy.linalg', 'uvvispy', 'uvvispy.processing'])
            listed = pm.describe(blocked=lambda req, imp: [['uvvispy', 'broken']] if 'uvvispy' in req else [])
            rows = {r['id']: r for r in listed['plugins']}
            self.assertEqual(rows['uvvispy_tools']['blocked'], [['uvvispy', 'broken']])
            self.assertEqual(rows['fit_curve']['blocked'], [])

    def test_open_source_needs_no_confirmation_and_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = [{'requested': True, 'metadata': {'name': 'propkg', 'version': '3.0', 'license_expression': 'MIT'}}]
            mm = self._manager(tmp, report, {})
            job = self._wait(mm.start_inspect('propkg'))
            self.assertFalse(job.result['needs_confirm'])
            self.assertEqual(self._wait(mm.start_user_install(job.id)).state, 'done')
            with self.assertRaises(ValueError):
                ModuleManager(state_dir=tmp, online=False).start_inspect('propkg')

    def test_tampered_record_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'user-modules.json').write_text(json.dumps({'schema': 'pyplotter-user-modules/1', 'modules': [
                {'pip': '--index-url=http://evil.example'}, {'pip': 'fine-name', 'version': '1'}]}), encoding='utf-8')
            mm = ModuleManager(state_dir=tmp, online=False)
            self.assertEqual(list(mm.user), ['fine-name'])

    def test_deep_import_check(self):
        """A user's module whose top level imports but whose parts do not is not reported as working."""
        packages = {
            # like uvvispy: an __init__ with only a docstring, every part needs a module that is missing
            'ppempty': {'__init__': '"""Docs only."""', 'io': 'import pyplotter_gone', 'plotting': 'import pyplotter_gone'},
            # the main code works, one optional part needs a module that is not installed
            'pppart': {'__init__': 'def f():\n    return 1', 'qt': 'import pyplotter_no_qt', 'core': 'X = 1',
                       'more': 'Y = 2'},
            # parts that print, tests and private modules (not checked)
            'ppfine': {'__init__': '', 'a': 'print("PYPLOTTER-RESULT {}")', 'tests': 'raise RuntimeError',
                       '_private': 'raise RuntimeError'},
            # Python dies while importing a part
            'ppcrash': {'__init__': '', 'boom': 'import os\nos._exit(3)'},
            'ppflat': None,                                   # a single-file module
        }
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as lib:
            for name, files in packages.items():
                if files is None:
                    (Path(lib) / f'{name}.py').write_text('Z = 3', encoding='utf-8')
                    continue
                (Path(lib) / name).mkdir()
                for mod, code in files.items():
                    (Path(lib) / name / f'{mod}.py').write_text(code, encoding='utf-8')
            mm = ModuleManager(state_dir=tmp, online=False)
            mm.user = {n: {'pip': n, 'imports': [n]} for n in packages}
            mm.user['ppgone'] = {'pip': 'ppgone', 'imports': ['ppgone']}
            with mock.patch.dict('os.environ', {'PYTHONPATH': lib}):
                r = {n: mm.check_import('user:' + n) for n in mm.user}
            self.assertFalse(r['ppempty']['ok'])
            self.assertEqual(r['ppempty']['parts'], 2)
            self.assertEqual([n for n, _ in r['ppempty']['failed']], ['ppempty.io', 'ppempty.plotting'])
            self.assertIn("No module named 'pyplotter_gone'", r['ppempty']['error'])
            self.assertTrue(r['pppart']['ok'])
            self.assertEqual(r['pppart']['parts'], 4)                       # 3 submodules + the top level
            self.assertEqual([n for n, _ in r['pppart']['failed']], ['pppart.qt'])
            self.assertEqual((r['ppfine']['ok'], r['ppfine']['failed'], r['ppfine']['parts']), (True, [], 1))
            self.assertFalse(r['ppcrash']['ok'])
            self.assertIn('ppcrash.boom', r['ppcrash']['error'])
            self.assertEqual((r['ppflat']['ok'], r['ppflat']['failed'], r['ppflat']['parts']), (True, [], 1))
            self.assertFalse(r['ppgone']['ok'])
            self.assertIn('ModuleNotFoundError', r['ppgone']['error'])

    def test_shallow_checks_of_user_modules_are_redone(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'import-check.json').write_text(json.dumps({'python': sys.executable, 'checks': {
                'user:old': {'version': '1', 'ok': True, 'error': ''},                  # before the deep check
                'user:new': {'version': '1', 'ok': True, 'error': '', 'failed': [], 'parts': 3, 'deep': True}}}),
                encoding='utf-8')
            mm = ModuleManager(state_dir=tmp, online=False)
            self.assertEqual(sorted(k for k in mm.checks if k.startswith('user:')), ['user:new'])


class TestReaders(TempDir):
    def test_italian_csv(self):
        p = self.write('it.csv', 'Tempo;Valore\n0,5;1,25\n1,0;2,5\n1,5;3,75\n')
        df, opts = readers.read_table(p, 'text')
        self.assertEqual(opts['sep'], ';')
        self.assertEqual(opts['decimal'], ',')
        self.assertEqual(list(df.columns), ['Tempo', 'Valore'])
        self.assertAlmostEqual(df['Valore'].iloc[2], 3.75)

    def test_thousands_separators_are_asked(self):
        # MONET-style export: numbers from 1000 on are quoted with a thousands comma
        rows = ['# Vibrational density of states', 'Wavenumber (cm⁻¹),VDOS']
        rows += [f'{x:.2f},{x / 1e4:.6f}' for x in (0, 500, 999.83)]
        rows += [f'"{x:,.1f}",{x / 1e4:.6f}' for x in (1003.3, 2500.0, 3999.3)]
        p = self.write('vdos.csv', '\n'.join(rows) + '\n')
        df, opts = readers.read_table(p, 'text')
        self.assertFalse(pd.api.types.is_float_dtype(df.iloc[:, 0]))       # not converted silently…
        sug = opts['suggestions']
        self.assertEqual((sug[0]['column'], sug[0]['style'], sug[0]['count']), ('Wavenumber (cm⁻¹)', 'comma', 3))
        self.assertEqual((sug[0]['example'], sug[0]['value']), ('1,003.3', 1003.3))
        df, opts = readers.read_table(p, 'text', options={'convert': {'Wavenumber (cm⁻¹)': 'comma'}})
        self.assertTrue(pd.api.types.is_float_dtype(df.iloc[:, 0]))         # …only when the user agrees
        self.assertAlmostEqual(df.iloc[-1, 0], 3999.3)
        self.assertEqual(opts['suggestions'], [])
        # European style 1.234,5 and the typographic minus
        p = self.write('eu.csv', 'a;b\n"1.234,5";1\n"2.000,25";2\n"\u22123,5";3\n')
        df, opts = readers.read_table(p, 'text')
        self.assertEqual(opts['suggestions'][0]['style'], 'dot')
        df, _ = readers.read_table(p, 'text', options={'convert': {'*': 'dot'}})
        self.assertEqual(list(df['a']), [1234.5, 2000.25, -3.5])
        # decimals with a dot are numbers, not dates; ISO dates stay dates
        p = self.write('dots.csv', 'x,y\n' + ''.join(f'{i / 7:.4f},{i}\n' for i in range(50)))
        df, opts = readers.read_table(p, 'text')
        self.assertTrue(pd.api.types.is_float_dtype(df['x']))
        self.assertEqual(opts['suggestions'], [])

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
        with closing(sqlite3.connect(db)) as con, con:
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

    @staticmethod
    def jcamp_compress(values, per_line=10, dup=True):
        """Encode integers as JCAMP-DX DIFDUP lines (SQZ first value, DIF differences, DUP repeats), with
        the last value of each line repeated as the Y check at the start of the next one."""
        sqz = '@ABCDEFGHI'
        dif = '%JKLMNOPQR'
        def char(v, table, neg):
            s = str(abs(v))
            return (table[int(s[0])] if v >= 0 else neg[int(s[0]) - 1]) + s[1:]
        lines, start = [], 0
        while start < len(values):
            chunk = values[start:start + per_line]
            out = [str(start), char(chunk[0], sqz, 'abcdefghi')]
            steps = [b - a for a, b in zip(chunk, chunk[1:])]
            i = 0
            while i < len(steps):
                j = i
                while dup and j + 1 < len(steps) and steps[j + 1] == steps[i]:
                    j += 1
                out.append(char(steps[i], dif, 'jklmnopqr'))
                if j > i:
                    out.append('STUVWXYZs'[j - i])            # the difference occurs j - i + 1 times
                i = j + 1
            lines.append(''.join(out))
            start += per_line - 1 if start + per_line < len(values) else per_line   # repeat the last value
        return lines

    def test_jcamp_compressed_forms(self):
        rng = np.random.default_rng(7)
        values = list(np.cumsum(rng.integers(-40, 40, 95)).astype(int))
        values[30:38] = [values[30]] * 8                             # a flat stretch: DUP of a zero difference
        values[50:56] = [values[50] + 7 * k for k in range(6)]       # a constant slope: DUP of a difference
        head = ('##TITLE=t\n##JCAMP-DX=5.01\n##XUNITS=1/CM\n##YUNITS=ABSORBANCE\n##FIRSTX=0\n'
                f'##LASTX={len(values) - 1}\n##NPOINTS={len(values)}\n##XFACTOR=1\n##YFACTOR=0.001\n'
                '##XYDATA=(X++(Y..Y))\n')
        p = self.write('difdup.jdx', head + '\n'.join(self.jcamp_compress(values)) + '\n##END=\n')
        df, _ = readers.read_table(p, 'jcamp')
        np.testing.assert_allclose(df.iloc[:, 1], np.array(values) * 0.001)
        # PAC: numbers separated only by their sign (as in NIST files), and AFFN with exponents
        pac = head.replace(f'##NPOINTS={len(values)}', '##NPOINTS=6').replace(f'##LASTX={len(values) - 1}', '##LASTX=5')
        df, _ = readers.read_table(self.write('pac.jdx', pac + '0-15-284+12\n3 39-354 1.5E+1\n##END=\n'), 'jcamp')
        np.testing.assert_allclose(df.iloc[:, 1], np.array([-15, -284, 12, 39, -354, 15]) * 0.001)
        with self.assertRaises(ValueError):                         # fewer values than ##NPOINTS: damaged
            readers.read_table(self.write('short.jdx', head + '0 1 2 3\n##END=\n'), 'jcamp')

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


    def test_block_profile_matches_column_profile(self):
        rng = np.random.default_rng(3)
        for n in (0, 1, 2, 3, 40):
            df = pd.DataFrame({
                'f': rng.normal(size=n), 'i': rng.integers(0, 5, n), 'up': np.arange(n, dtype=float),
                'down': -np.arange(n), 'const': np.ones(n), 'u8': rng.integers(0, 3, n).astype(np.uint8),
                'f32': rng.normal(size=n).astype(np.float32), 'whole': rng.integers(0, 9, n).astype(float),
                'half': np.arange(n) + 0.5, 'txt': (['a', 'b'] * n)[:n], 'flag': rng.integers(0, 2, n).astype(bool),
                'when': pd.date_range('2020', periods=n, freq='D'), 'Int': pd.array(rng.integers(0, 4, n), dtype='Int64'),
            })
            if n >= 3:
                gap = np.arange(n, dtype=float)
                gap[1] = np.nan
                holes = rng.normal(size=n)
                holes[::2] = np.nan
                big = np.arange(n, dtype=float)
                big[-1] = np.inf
                df = df.assign(gap=gap, holes=holes, empty=np.nan, big=big)
            fast = smart.profile_block(df)
            plain = [i for i, t in enumerate(df.dtypes) if isinstance(t, np.dtype) and t.kind in 'iuf']
            self.assertEqual(sorted(fast), plain)
            for i in plain:
                self.assertEqual(fast[i], smart.profile_column(df.iloc[:, i]), (n, df.columns[i]))

    def test_grid_search_is_linear_and_unchanged(self):
        def quadratic(cols, n_rows):             # the former search, pair by pair
            numeric = [c for c in cols if c['kind'] == 'numeric' and c.get('unique')]
            for i, a in enumerate(numeric):
                for b in numeric[i + 1:]:
                    if a['unique'] >= 3 and b['unique'] >= 3 and a['unique'] * b['unique'] == n_rows:
                        rest = [c['name'] for c in numeric if c['name'] not in (a['name'], b['name'])]
                        if rest:
                            return a['name'], b['name'], rest[0]
            return None
        rng = np.random.default_rng(4)
        for _ in range(300):
            cols = [{'name': f'c{j}', 'kind': str(rng.choice(['numeric', 'category'])),
                     'unique': int(rng.choice([0, 1, 2, 3, 4, 5, 6, 8, 12, 20]))} for j in range(rng.integers(2, 9))]
            n_rows = int(rng.choice([12, 16, 24, 36, 60]))
            self.assertEqual(smart.find_grid(cols, n_rows), quadratic(cols, n_rows))

    def test_wide_table_opens_quickly(self):
        rng = np.random.default_rng(5)
        df = pd.DataFrame(rng.normal(size=(50, 20000)), columns=[str(40 * i) for i in range(20000)])
        df.insert(0, 'frame', np.arange(50))
        start = time.perf_counter()
        cols = smart.profile(df)
        mapping = smart.default_mapping(cols, len(df))
        self.assertLess(time.perf_counter() - start, 10)          # was ~45 s, column by column
        self.assertEqual(mapping['x'], 'frame')
        self.assertEqual(len(cols), 20001)


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
        'surface3d': ('surface', {'x': 'x', 'y': ['y'], 'z': 'z'}),
        'scatter3d': ('cloud', {'x': 'x', 'y': ['y'], 'z': 'z', 'hue': 'class'}),
        'waterfall': ('spectra', {'x': 'Wavelength (nm)', 'y': ['Sample A', 'Sample B', 'Sample C']}),
    }

    def test_three_d_variants(self):
        """Scattered points become a triangulated surface; wire frame, a joined 3D line, numeric depths,
        view and z limits; a 3D figure offers no axes for clicking points."""
        cloud, spectra = samples.make('cloud'), samples.make('spectra')
        for spec in ({'kind': 'surface3d', 'x': 'x', 'y': ['y'], 'z': 'z'},
                     {'kind': 'surface3d', 'x': 'x', 'y': ['y'], 'z': 'z', 'style': {'wireframe': True}},
                     {'kind': 'scatter3d', 'x': 'x', 'y': ['y'], 'z': 'z', 'style': {'connect': True, 'elev': 10, 'azim': 30},
                      'axes': {'zmin': -5, 'zmax': 5}}):
            with self.subTest(spec=spec):
                info = {}
                self.assertTrue(plotting.render(cloud, spec, 'png', 40, info=info).startswith(b'\x89PNG'))
                self.assertEqual(info['axes'], [])
        wide = pd.DataFrame({'nm': np.arange(10.0), '10': np.arange(10.0), '20': np.ones(10), '35': np.zeros(10)})
        fig = plotting.build_figure(wide, {'kind': 'waterfall', 'x': 'nm', 'y': ['10', '20', '35']})
        self.assertEqual(sorted(set(fig.axes[0].lines[2].get_data_3d()[1])), [35.0])   # depth = the column's value
        with self.assertRaises(plotting.SpecError):
            plotting.render(spectra, {'kind': 'surface3d', 'x': 'Wavelength (nm)', 'y': ['Sample A']}, 'png', 40)

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_rotatable_preview_matches_matplotlib(self):
        """web/view3d.js projects points where Matplotlib draws them, at any view (and inverted axes)."""
        from mpl_toolkits.mplot3d import proj3d
        df = samples.make('surface')
        spec = plotting.normalize_spec({'kind': 'surface3d', 'x': 'x', 'y': ['y'], 'z': 'z', 'axes': {'invert_x': True}})
        with plotting.style_context(spec), plotting.rc_context(plotting._rc(spec)):
            fig = plotting.build_figure(df, spec)
            fig.savefig(io.BytesIO(), format='png', dpi=60)
            data = plotting.view3d(fig)
            ax = next(a for a in fig.axes if a.name == '3d')
            pts = [(-2.5, 1.0, 0.3), (0.0, 0.0, -0.8), (3.0, -2.0, 1.1)]
            views = [(25, -60), (10, 30), (70, 150), (-20, -170)]
            # Projected coordinates → image, with the map of the first drawing (the layout engine moves the
            # axes by a pixel or so at each drawing, here and in the app alike).
            A = data['axes'][0]['affine']
            to_image = lambda px, py: [A[0] * px + A[1] * py + A[2], A[3] * px + A[4] * py + A[5]]  # noqa: E731
            expected, labels, ticklabels = [], [], []
            for elev, azim in views:
                ax.view_init(elev=elev, azim=azim)
                xs, ys, _ = proj3d.proj_transform(*np.array(pts).T, ax.get_proj())
                expected.append([to_image(px, py) for px, py in zip(xs, ys)])
                fig.savefig(io.BytesIO(), format='png', dpi=60)          # places the axis labels
                labels.append([to_image(*a.label.get_position()) for a in (ax.xaxis, ax.yaxis, ax.zaxis)])
                drawn = []                                   # the tick labels as drawn (inside the limits)
                for a, (lo, hi) in zip((ax.xaxis, ax.yaxis, ax.zaxis), (ax.get_xbound(), ax.get_ybound(), ax.get_zbound())):
                    locs = a.get_majorticklocs()
                    drawn += [to_image(*t.label1.get_position()) for t in a.get_major_ticks()[:len(locs)]
                              if lo - 1e-12 <= t.get_loc() <= hi + 1e-12]
                ticklabels.append(drawn)
        v = data['axes'][0]
        self.assertEqual(len(data['axes']), 1)
        self.assertEqual(len(data['keep']), 1)                # the colour bar stays visible while rotating
        self.assertEqual({L['type'] for L in v['layers']}, {'grid'})
        self.assertLessEqual(v['layers'][0]['rows'], plotting.PREVIEW_GRID + 1)
        script = ('const V = require(%s); const v = %s; const out = %s.map(([e, a]) => { const P = V.projector(v, e, a); '
                  'const L = V.layout(v, e, a); return [%s.map(p => P(...p).slice(0, 2)), L.labels.map(c => c.slice(0, 2)), '
                  'L.ticks.map(t => t.at.slice(0, 2))]; }); '
                  'console.log(JSON.stringify(out));'
                  % (json.dumps(str(ROOT / 'web' / 'view3d.js')), json.dumps(v), json.dumps(views), json.dumps(pts)))
        got = json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)
        np.testing.assert_allclose([g[0] for g in got], expected, atol=1e-6)
        # Axis names where Matplotlib puts them: their offset scales with the axes size, which the layout
        # engine changes by a pixel or two at each drawing.
        np.testing.assert_allclose([g[1] for g in got], labels, atol=0.005)
        np.testing.assert_allclose([g[2] for g in got], ticklabels, atol=0.005)
        json.dumps(data, allow_nan=False)                     # what the server sends
        for kind, sample, spec in (('waterfall', 'spectra', {'x': 'Wavelength (nm)', 'y': ['Sample A', 'Sample B']}),
                                   ('scatter3d', 'cloud', {'x': 'x', 'y': ['y'], 'z': 'z', 'hue': 'class'})):
            info = {}
            plotting.render(samples.make(sample), dict(spec, kind=kind), 'png', 50, info=info)
            view = json.loads(json.dumps(info['view3d'], allow_nan=False))
            self.assertTrue(all(isinstance(k, list) and len(k) == 4 for k in view['keep']), kind)
            self.assertEqual({L['type'] for L in view['axes'][0]['layers']}, {'line' if kind == 'waterfall' else 'points'})

    @unittest.skipUnless(has('plotly'), 'plotly not installed')
    def test_three_d_interactive_html(self):
        for kind, (sample, spec) in self.CASES.items():
            if kind in catalog.THREE_D_KINDS:
                with self.subTest(kind=kind):
                    html = exporters.plotly_html(samples.make(sample), dict(spec, kind=kind))
                    self.assertIn(b'scene', html)

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

    def test_series_colours_reported(self):
        """The colours reported for the Series panel are the ones drawn, for every kind of palette."""
        import copy
        df = samples.make('cloud')
        for palette, base in (('okabe-ito', 'publication'), ('style', 'ggplot'), ('cmap:viridis', 'publication')):
            spec = copy.deepcopy(plotting.DEFAULT_SPEC)
            spec.update(kind='line', x='x', y=['y', 'z'])
            spec['style'].update(palette=palette, base=base)
            info = {}
            plotting.render(df, spec, 'png', 30, info=info)
            colors = [e['color'] for e in info['series']]
            self.assertEqual([e['key'] for e in info['series']], ['y', 'z'])
            self.assertEqual(len(set(colors)), 2, palette)
            self.assertEqual(plotting.series_colors(df, spec), dict(zip(['y', 'z'], colors)))
        spec['series'] = {'z': {'color': '#123456'}}
        self.assertEqual(plotting.series_colors(df, spec)['z'], '#123456')
        # one series + an analysis curve without its own colour: two different colours
        for palette in ('okabe-ito', 'style', 'cmap:viridis'):
            spec = copy.deepcopy(plotting.DEFAULT_SPEC)
            spec.update(kind='line', x='x', y=['y'])
            spec['style']['palette'] = palette
            spec['overlays'] = [{'id': 'o1', 'x': 'x', 'y': 'z', 'label': 'curve'}]
            ser = plotting.Series(plotting.normalize_spec(spec), n=2 if palette.startswith('cmap:') else 1)
            self.assertNotEqual(ser.next('y', 'y')['color'], ser.next('overlay:o1', 'curve')['color'], palette)
        # analysis layers: the colour each one was drawn with is reported too (Overlays panel)
        for palette in ('okabe-ito', 'style', 'cmap:viridis'):
            spec = copy.deepcopy(plotting.DEFAULT_SPEC)
            spec.update(kind='line', x='x', y=['y'])
            spec['style']['palette'] = palette
            spec['overlays'] = [{'id': 'free', 'x': 'x', 'y': 'z'},
                                {'id': 'fixed', 'x': 'x', 'y': 'w', 'style': {'color': '#abcdef'}}]
            info = {}
            plotting.render(df, spec, 'png', 30, info=info)
            layers = {e['overlay']: e['color'] for e in info['series'] if e.get('overlay')}
            series = [e['color'] for e in info['series'] if not e.get('overlay')]
            self.assertEqual(layers['fixed'], '#abcdef')
            self.assertNotEqual(layers['free'], series[0], palette)
            self.assertNotIn('overlay:free', plotting.series_colors(df, spec))
        # categories of a box plot are separate series
        spec = copy.deepcopy(plotting.DEFAULT_SPEC)
        spec.update(kind='box', x='class', y=['y'])
        self.assertEqual(len(plotting.series_colors(df, spec)), df['class'].nunique())

    def test_pie_and_many_groups_colours(self):
        import copy
        from urllib.parse import quote
        df = samples.make('groups')
        spec = copy.deepcopy(plotting.DEFAULT_SPEC)
        spec.update(kind='pie', x='Group', y=['Response (a.u.)'])
        spec['style']['palette'] = 'cmap:viridis'
        self.assertEqual(len(set(plotting.series_colors(df, spec).values())), 4)    # one colour per slice
        cloud = samples.make('cloud').head(3000)
        spec = copy.deepcopy(plotting.DEFAULT_SPEC)
        spec.update(kind='scatter', x='x', y=['y'], hue='z')                      # 3000 groups
        info = {}
        plotting.render(cloud, spec, 'png', 20, info=info)
        self.assertLessEqual(len(info['series']), plotting.ColorLog.MAX_SERIES)
        self.assertLess(len(quote(json.dumps(info['series'], ensure_ascii=False))), 64 * 1024)

    def test_download_name_header(self):
        from pyplotter.server import content_disposition
        value = content_disposition('Spettro_Δ_α.pdf')
        value.encode('latin-1')                                    # headers must be Latin-1
        self.assertIn("filename*=UTF-8''Spettro_%CE%94_%CE%B1.pdf", value)

    def test_datasets_dropped_least_recently_used(self):
        from pyplotter import server
        with tempfile.TemporaryDirectory() as tmp:
            app = server.App('t' * 32, tmp, ModuleManager(state_dir=tmp, online=False), 10 ** 9)
            main = app._register(pd.DataFrame({'a': [1.0, 2.0]}), 'main', {'sample': 'x'}, {})['dataset_id']
            for i in range(server.MAX_DATASETS * 2):
                app._register(pd.DataFrame({'a': [float(i)]}), f'r{i}', {'sample': 'x'}, {})
                app.dataset(main)                                  # the figure is redrawn: still in use
            self.assertIn(main, app.datasets)
            self.assertLessEqual(len(app.datasets), server.MAX_DATASETS)

    def test_palette_previews(self):
        pv = plotting.palette_previews()
        self.assertEqual(len(pv['cmap:viridis']), 8)
        self.assertIn('publication', pv['style'])

    def test_import_checks_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            mm = ModuleManager(state_dir=tmp, online=False)
            mm.checks = {'numpy': {'version': mm.installed('numpy'), 'ok': True, 'error': '', 'gen': 0}}
            mm._write_checks()
            again = ModuleManager(state_dir=tmp, online=False)
            self.assertTrue(again.checks['numpy']['ok'])
            self.assertIs(again.status()['modules'][0]['works'], True)

    def test_overlay_value_labels(self):
        """A layer with a text column writes its values above the points (peak positions)."""
        import copy
        df = samples.make('spectra')
        spec = copy.deepcopy(plotting.DEFAULT_SPEC)
        spec.update(kind='line', x='Wavelength (nm)', y=['Sample A'])
        frame = pd.DataFrame({'Wavelength (nm)': [450.0, 520.0], 'top': [1.0, 0.5], 'text': ['450', '520']})
        spec['overlays'] = [{'id': 'p', 'dataset_id': 'd', 'x': 'Wavelength (nm)', 'y': 'top', 'text': 'text',
                             'style': {'linestyle': 'none', 'marker': 'v'}}]
        svg = plotting.render(df, spec, 'svg', overlay_data={'p': frame}).decode('utf-8')
        self.assertIn('>450<', svg.replace(' ', ''))
        self.assertIn('>520<', svg.replace(' ', ''))

    def test_overlay_markers_of_their_own(self):
        """A layer's markers (e.g. peak markers) take their own shape and size; the value labels stay where
        the analysis put them whatever the marker."""
        import copy
        df = samples.make('spectra')
        frame = pd.DataFrame({'Wavelength (nm)': [450.0, 520.0], 'top': [1.0, 0.5], 'text': ['450', '520']})
        for marker, size, below in (('s', 9.0, False), ('^', 4.0, False), ('o', None, True)):
            spec = copy.deepcopy(plotting.DEFAULT_SPEC)
            spec.update(kind='line', x='Wavelength (nm)', y=['Sample A'])
            style = {'linestyle': 'none', 'marker': marker, 'text_below': below}
            if size:
                style['markersize'] = size
            spec['overlays'] = [{'id': 'p', 'dataset_id': 'd', 'x': 'Wavelength (nm)', 'y': 'top', 'text': 'text',
                                 'style': style}]
            spec = plotting.normalize_spec(spec)
            with plotting.style_context(spec), matplotlib.rc_context(plotting._rc(spec)):
                ax = plotting.build_figure(df, spec, overlay_data={'p': frame}).axes[0]
            line = [ln for ln in ax.get_lines() if list(ln.get_xdata()) == [450.0, 520.0]][0]
            self.assertEqual(line.get_marker(), marker)
            if size:
                self.assertEqual(line.get_markersize(), size)
            offsets = {a.get_text(): a.xyann[1] for a in ax.texts}
            self.assertEqual(offsets['450'] < 0, below)      # below the point only when asked

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

    def test_many_columns(self):
        rng = np.random.default_rng(6)
        df = pd.DataFrame(rng.normal(size=(30, 3000)), columns=[f'c{i}' for i in range(3000)])
        png = plotting.render(df, {'kind': 'heatmap', 'y': list(df.columns)}, 'png', dpi=50)
        self.assertTrue(png.startswith(b'\x89PNG'))
        with self.assertRaises(plotting.SpecError) as err:
            plotting.render(df, {'kind': 'corr', 'y': list(df.columns)}, 'png', dpi=50)
        self.assertEqual(err.exception.key, 'corr_too_many')
        self.assertEqual(err.exception.values, {'n': 3000, 'max': plotting.MAX_CORR_COLUMNS})
        with self.assertRaises(plotting.SpecError) as err:                  # one line per column: too many
            plotting.render(df, {'kind': 'line', 'y': list(df.columns)}, 'png', dpi=50)
        self.assertEqual(err.exception.key, 'too_many_series')
        fig = plotting.build_figure(df, {'kind': 'line', 'y': list(df.columns[:60])})
        self.assertIsNone(fig.axes[0].get_legend())                           # 60 entries: no automatic legend
        fig = plotting.build_figure(df, {'kind': 'line', 'y': list(df.columns[:60]), 'legend': {'show': 'show'}})
        self.assertIsNotNone(fig.axes[0].get_legend())
        fig = plotting.build_figure(df, {'kind': 'line', 'y': list(df.columns[:4])})
        self.assertIsNotNone(fig.axes[0].get_legend())                        # a few entries: it fits
        small = df.iloc[:, :6].copy()
        small['flat'] = 1.0                                        # constant: r is undefined
        np.testing.assert_allclose(plotting.corr_matrix(small), small.corr().to_numpy(), atol=1e-12)
        small.iloc[::3, 1] = np.nan                                # gaps: pairwise, like pandas
        np.testing.assert_allclose(plotting.corr_matrix(small), small.corr().to_numpy(), atol=1e-12)

    def test_axes_geometry_maps_clicks_to_data(self):
        import matplotlib
        df = pd.DataFrame({'x': np.linspace(400, 4000, 50), 'y': np.linspace(1, 100, 50)})
        for scale in ('linear', 'log'):
            spec = plotting.normalize_spec({'kind': 'line', 'x': 'x', 'y': ['y'], 'axes': {'yscale': scale}})
            with plotting.style_context(spec), matplotlib.rc_context(plotting._rc(spec)):
                fig = plotting.build_figure(df, spec)
                fig.savefig(io.BytesIO(), format='png', dpi=80)
                g = plotting.axes_geometry(fig)
                self.assertEqual(len(g), 1)
                ax = fig.axes[0]
                px, py = ax.transData.transform((1500.0, 20.0))         # where matplotlib draws the point
                w, h = fig.get_size_inches() * fig.dpi
                fx, fy = px / w, py / h
                box = g[0]['box']
                u = (fx - box[0]) / (box[2] - box[0])
                x = g[0]['xlim'][0] + u * (g[0]['xlim'][1] - g[0]['xlim'][0])
                v = (fy - box[1]) / (box[3] - box[1])
                if g[0]['yscale'] == 'log':
                    lo, hi = np.log10(g[0]['ylim'])
                    y = 10 ** (lo + v * (hi - lo))
                else:
                    y = g[0]['ylim'][0] + v * (g[0]['ylim'][1] - g[0]['ylim'][0])
                self.assertAlmostEqual(x, 1500.0, delta=1.0)
                self.assertAlmostEqual(y, 20.0, delta=0.2)
        info = {}
        plotting.render(df, {'kind': 'heatmap', 'y': ['x', 'y']}, 'png', dpi=40, info=info)
        self.assertEqual(len(info['axes']), 1)                          # the colour bar is left out

    def _peak_figure(self, **extra):
        x = np.arange(550.0, 4000.0)
        g = lambda c, w, a: a * np.exp(-0.5 * ((x - c) / w) ** 2)          # noqa: E731
        centres = [(674, 2, 6.5e-3), (660, 5, 3e-4), (688, 5, 3.5e-4), (1038, 6, 1.1e-4), (3047, 10, 2.3e-4),
                   (3070, 8, 1.9e-4), (3102, 10, 1.6e-4)]
        df = pd.DataFrame({'x': x, 'y': sum(g(*c) for c in centres)})
        idx = [int(np.argmin(abs(x - c))) for c, _, _ in centres]
        frame = pd.DataFrame({'x': x[idx], 'top': df['y'].to_numpy()[idx], 'text': [f'{v:.0f}' for v in x[idx]]})
        spec = {'kind': 'line', 'x': 'x', 'y': ['y'],
                'overlays': [{'id': 'p', 'dataset_id': 'd', 'x': 'x', 'y': 'top', 'text': 'text',
                              'style': {'linestyle': 'none', 'marker': 'v'}}], **extra}
        info = {}
        plotting.render(df, spec, 'png', 100, overlay_data={'p': frame}, info=info)
        return info

    def test_value_labels_do_not_overlap(self):
        """Crowded peak labels move apart (with a leader line); all of them stay inside the axes."""
        info = self._peak_figure()
        labels = [m for m in info['movables'] if m['kind'] == 'label']
        self.assertEqual(len(labels), 7)
        box = info['axes'][0]['box']
        for i, a in enumerate(labels):
            self.assertTrue(box[0] <= a['box'][0] and a['box'][2] <= box[2] and box[1] <= a['box'][1] and a['box'][3] <= box[3], a)
            for b in labels[i + 1:]:
                apart = a['box'][2] <= b['box'][0] or b['box'][2] <= a['box'][0] or a['box'][3] <= b['box'][1] or b['box'][3] <= a['box'][1]
                self.assertTrue(apart, (a['id'], b['id']))
        self.assertTrue(any(m['offset'][0] for m in labels))                  # some moved aside

    def test_dragged_texts_stay_where_put(self):
        info = self._peak_figure(moved={'label:p:3070': [12, 30], 'xlabel': [20, -4]}, legend={'pos': [0.05, 0.95]},
                                 text={'title': 'T'})
        by_id = {m['id']: m for m in info['movables']}
        self.assertEqual(by_id['label:p:3070']['offset'], [12.0, 30.0])
        self.assertEqual(by_id['xlabel']['offset'], [20.0, -4.0])
        self.assertIn('title', by_id)
        lg, ref = by_id['legend']['box'], by_id['legend']['ref']
        self.assertAlmostEqual((lg[0] - ref[0]) / (ref[2] - ref[0]), 0.05, delta=0.02)   # its top left corner
        self.assertAlmostEqual((lg[3] - ref[1]) / (ref[3] - ref[1]), 0.95, delta=0.02)

    def test_zoom_on_x_fits_y(self):
        """With only the x range fixed, y spans the data in that range (one small band of a spectrum)."""
        info = self._peak_figure(axes={'xmin': 2950, 'xmax': 3200})
        lo, hi = info['axes'][0]['ylim']
        self.assertLess(hi, 1e-3)                                              # not the 6.5e-3 peak outside
        self.assertGreater(hi, 2.3e-4)
        self.assertEqual(sorted(m['id'] for m in info['movables'] if m['kind'] == 'label'),
                         ['label:p:3047', 'label:p:3070', 'label:p:3102'])     # labels outside the range are not listed

    def test_every_kind_lists_its_texts(self):
        """Titles and labels of every kind can be dragged and rewritten; polar and 3D axes zoom with the wheel."""
        groups, surface = samples.make('groups'), samples.make('surface')
        value = [c for c in groups.columns if groups[c].dtype.kind == 'f'][0]
        cases = [(groups, {'kind': 'pie', 'x': 'Group', 'y': [value], 'texts': {'pie.name:Control': 'Controllo'}},
                  {'pie.name:Control': ('Controllo', None)}),
                 (groups, {'kind': 'box', 'x': 'Group', 'y': [value], 'text': {'ylabel': 'R'}}, {'ylabel': ('R', 'text.ylabel')}),
                 (surface, {'kind': 'contour', 'x': 'x', 'y': ['y'], 'z': 'z'}, {'cblabel': ('z', 'text.zlabel')}),
                 (surface, {'kind': 'surface3d', 'x': 'x', 'y': ['y'], 'z': 'z'}, {'zlabel': ('z', 'text.zlabel')})]
        for df, spec, expected in cases:
            info = {}
            plotting.render(df, dict(spec, text={'title': 'T', **spec.get('text', {})}), 'png', 40, info=info)
            by_id = {m['id']: (m['text'], m['field']) for m in info['movables']}
            self.assertEqual(by_id['title'], ('T', 'text.title'), spec['kind'])
            for key, val in expected.items():
                self.assertEqual(by_id[key], val, spec['kind'])
        info = {}
        plotting.render(surface, {'kind': 'surface3d', 'x': 'x', 'y': ['y'], 'z': 'z'}, 'png', 40, info=info)
        self.assertEqual([z['type'] for z in info['zoom']], ['3d'])

    def test_text_boxes_match_the_image_at_any_dpi(self):
        """Where the page outlines a text is where the image shows it, whatever DPI the preview uses
        (axis labels keep a position in pixels, so they must be measured at the DPI of the image)."""
        df = samples.make('spectra')
        boxes = []
        for dpi in (40, 300):
            info = {}
            plotting.render(df, {'kind': 'line', 'x': 'Wavelength (nm)', 'y': ['Sample A']}, 'png', dpi, info=info)
            by_id = {m['id']: m['box'] for m in info['movables']}
            self.assertLess(by_id['xlabel'][3], info['axes'][0]['box'][1] - 0.04)   # under the tick labels
            boxes.append(by_id)
        for key in ('xlabel', 'ylabel'):
            for a, b in zip(boxes[0][key], boxes[1][key]):
                self.assertAlmostEqual(a, b, delta=0.02, msg=key)

    def test_limits_keep_an_image_upright(self):
        """Zooming a heat map (rows drawn from the top) keeps its orientation."""
        df = pd.DataFrame(np.arange(20.0).reshape(5, 4), columns=list('abcd'))
        for axes in ({}, {'ymin': 0.5, 'ymax': 3.5}):
            info = {}
            plotting.render(df, {'kind': 'heatmap', 'y': list('abcd'), 'axes': axes}, 'png', 40, info=info)
            lo, hi = info['axes'][0]['ylim']
            self.assertGreater(lo, hi, axes)                                   # still top to bottom

    def test_preview_of_a_wide_table(self):
        from pyplotter import server
        with tempfile.TemporaryDirectory() as tmp:
            app = server.App('t' * 32, tmp, ModuleManager(state_dir=tmp, online=False), 10 ** 9)
            df = pd.DataFrame(np.zeros((3, 500)), columns=[f'c{i}' for i in range(500)])
            ds = app._register(df, 'wide', {'sample': 'x'}, {})
            self.assertEqual(len(ds['columns']), 500)
            self.assertEqual(ds['preview_cols'], server.PREVIEW_COLS)
            self.assertEqual({len(row) for row in ds['preview']}, {server.PREVIEW_COLS})

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
