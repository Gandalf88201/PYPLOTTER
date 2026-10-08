"""Analysis plugins: built-in ones in pyplotter/analyses/, yours in ~/.pyplotter/plugins/.

A plugin is one Python file with a ``PLUGIN`` dictionary and a ``run(df, p, ctx)`` function
(see ``TEMPLATE`` below or docs in PLUGINS.md). A user plugin with the same ``id`` as a
built-in one replaces it, so every analysis can be customised. Plugins run inside the local
PyPlotter service with your user rights: only install plugins you trust.
"""
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import traceback

import numpy as np
import pandas as pd

BUILTIN_DIR = Path(__file__).resolve().parent / 'analyses'
USER_DIR = Path(os.environ.get('PYPLOTTER_PLUGINS') or
                Path(os.environ.get('PYPLOTTER_HOME') or Path.home() / '.pyplotter') / 'plugins')
PARAM_TYPES = {'column', 'columns', 'int', 'float', 'bool', 'choice', 'text', 'points'}
CATEGORIES = ['recipe', 'fit', 'timeseries', 'stats', 'signal', 'custom']
MAX_TABLE_ROWS = 5000


class PluginError(ValueError):
    """Wrong parameters or data for an analysis (shown to the user as is)."""


# ------------------------------------------------------------------ results
class Result:
    """What an analysis returns. Build it with ctx.result()."""

    def __init__(self, lang):
        self.lang = lang
        self.summary, self.tables, self.texts, self.refs = [], [], [], []
        self.frame, self.plot, self.name = None, None, None
        self.overlays = []
        self.out = {}            # key -> (value, error): numbers other analyses (recipes) can read

    def value(self, label, value, error=None, unit='', key=None):
        """One line of the summary table: label, value (± error) and unit.

        key: a fixed, language-independent name under which recipes find this number (see keep).
        """
        self.summary.append({'label': str(label), 'value': _cell(value), 'error': _cell(error), 'unit': str(unit or '')})
        if key:
            self.keep(key, value, error)
        return self

    def keep(self, key, value, error=None):
        """Store a number for recipes without showing it (read back with get)."""
        self.out[str(key)] = (value, error)
        return self

    def get(self, key, default=None):
        """Value stored with value(..., key=) or keep(); default if the analysis did not provide it."""
        return self.out.get(key, (default, None))[0]

    def error(self, key):
        return self.out.get(key, (None, None))[1]

    def table(self, title, data, index=False):
        """A table from a DataFrame, a list of dicts or a dict of lists."""
        if not isinstance(data, pd.DataFrame):
            data = pd.DataFrame(data)
        if index:
            data = data.reset_index()
        data = data.head(MAX_TABLE_ROWS)
        self.tables.append({'title': str(title), 'columns': [str(c) for c in data.columns],
                            'rows': [[_cell(v) for v in row] for row in data.itertuples(index=False, name=None)]})
        return self

    def text(self, text):
        self.texts.append(str(text))
        return self

    def data(self, frame, plot=None, name=None):
        """New data set (e.g. fitted curve, ACF) that can be plotted and exported like any file.

        plot: a figure spec for it, e.g. {'kind': 'line', 'x': 'lag', 'y': ['acf']}.
        """
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(frame)
        self.frame, self.plot, self.name = frame.reset_index(drop=True), plot or {}, name
        return self

    def overlay(self, frame, x, y, lo=None, hi=None, label=None, band_label=None, style=None, on_figure=True,
                text=None):
        """A layer that can be drawn over the original figure: curve x→y and optional band lo…hi.

        Use the same x units as the analysed data (e.g. the fitted curve on a fine grid with its
        95 % confidence band). style: {'color', 'linestyle', 'linewidth', 'marker', 'band_alpha'}.
        style legend=False draws the layer without a legend entry (e.g. one curve per peak).
        on_figure=False: the layer belongs only to this result's own plot (its x is not the data's x,
        e.g. a curve over a histogram computed by the analysis).
        text: a column of labels written above each point (below for style marker '^'), e.g. peak positions.
        Returns the overlay index, which a data plot can use as {'overlays': [{'ref': index}]}.
        """
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(frame)
        for c in (x, y, lo, hi, text):
            if c is not None and c not in frame.columns:
                raise PluginError(f'Overlay column not found: {c}')
        self.overlays.append({'frame': frame.reset_index(drop=True), 'x': x, 'y': y, 'lo': lo, 'hi': hi,
                              'label': str(label or y), 'band_label': band_label, 'style': dict(style or {}),
                              'on_figure': bool(on_figure), 'text': text})
        return len(self.overlays) - 1

    def include(self, sub, title, overlays=False):
        """Add another analysis' result (from ctx.run) as one step of this one: its summary and tables
        appear under the step title, its texts and references are kept. overlays=True also takes its
        layers (on_figure as they were). Returns the index of its first overlay in this result."""
        first = len(self.overlays)
        if sub.summary:
            it = self.lang == 'it'
            self.tables.append({'title': f'{title} · ' + ('riepilogo' if it else 'summary'),
                                'columns': ['grandezza', 'valore'] if it else ['quantity', 'value'],
                                'rows': [[s['label'], _join(s)] for s in sub.summary]})
        for tb in sub.tables:
            self.tables.append({**tb, 'title': f'{title} · {tb["title"]}'})
        self.texts.extend(f'{title}: {t}' for t in sub.texts)
        self.refs.extend(sub.refs)
        if overlays:
            self.overlays.extend(dict(o) for o in sub.overlays)
        return first

    def cite(self, *refs):
        self.refs.extend(str(r) for r in refs if r)
        return self


class Context:
    """Helpers handed to run(): language, translations, result builder, numeric column access."""

    def __init__(self, lang='en', spec=None, runner=None):
        self.lang = lang if lang in ('en', 'it') else 'en'
        self.spec = spec or {}
        self._runner = runner

    def tr(self, en, it=None):
        return it if (self.lang == 'it' and it) else en

    def result(self):
        return Result(self.lang)

    def run(self, pid, df, **params):
        """Run another analysis on df and return its Result (recipes are built from these steps).

        The built-in version of the analysis is used, so a recipe gives the same numbers whatever
        customised copies are in the plugins folder. Parameters not given take their defaults.
        """
        if self._runner is None:
            raise PluginError('ctx.run is not available here.')
        return self._runner(pid, df, params)

    @staticmethod
    def numeric(df, column, dropna=True):
        if column not in df.columns:
            raise PluginError(f'Column not found: {column}')
        s = df[column]
        if pd.api.types.is_datetime64_any_dtype(s):
            s = (s - s.min()).dt.total_seconds()
        s = pd.to_numeric(s, errors='coerce')
        if s.notna().sum() == 0:
            raise PluginError(f'Column "{column}" has no numeric values.')
        return s.dropna() if dropna else s

    def baseline(self, x, y, p):
        """The baseline chosen in p (parameters from pyplotter.baselines.params), or None if p['baseline'] is
        not one of its methods. Returns an object with .values (one per x), .label, .refs, .anchors, .below."""
        from . import baselines
        try:
            return baselines.estimate(x, y, p, self.tr)
        except ValueError as exc:
            raise PluginError(str(exc))

    def xy(self, df, x, y):
        """Paired numeric arrays (x may be None = row number), NaN rows removed."""
        ys = self.numeric(df, y, dropna=False)
        xs = self.numeric(df, x, dropna=False) if x else pd.Series(np.arange(len(df), dtype=float), index=df.index)
        ok = xs.notna() & ys.notna()
        return xs[ok].to_numpy(dtype=float), ys[ok].to_numpy(dtype=float)


def _join(s):
    """'value ± error unit' text of a summary entry."""
    def num(v):
        return f'{v:.6g}' if isinstance(v, float) else str(v)
    text = num(s['value']) if s['value'] is not None else '—'
    if s['error'] is not None:
        text += ' ± ' + num(s['error'])
    return (text + ' ' + s['unit']).strip()


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return v if math.isfinite(v) else None
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    return str(v)


# ------------------------------------------------------------------ manager
class PluginManager:
    def __init__(self, builtin_dir=BUILTIN_DIR, user_dir=USER_DIR):
        self.builtin_dir = Path(builtin_dir)
        self.user_dir = Path(user_dir)
        self.plugins = {}
        self.errors = []
        self.reload()

    def reload(self):
        self.plugins, self.errors = {}, []
        self.builtins = {}       # the built-in versions, also when a user plugin replaces them (for recipes)
        for source, folder in (('builtin', self.builtin_dir), ('user', self.user_dir)):
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob('*.py')):
                if path.name.startswith(('_', '.')):
                    continue
                try:
                    plugin = self._load(path, source)
                except Exception as exc:
                    self.errors.append({'file': path.name, 'source': source, 'error': _short_tb(exc, path)})
                    continue
                previous = self.plugins.get(plugin['id'])
                if previous and previous['source'] == 'user' and source == 'user':
                    self.errors.append({'file': path.name, 'source': source,
                                        'error': f'Duplicate id "{plugin["id"]}" (also in {previous["file"]}).'})
                    continue
                plugin['overrides'] = bool(previous and previous['source'] == 'builtin' and source == 'user')
                self.plugins[plugin['id']] = plugin
                if source == 'builtin':
                    self.builtins[plugin['id']] = plugin
        return self

    def _load(self, path, source):
        name = f'pyplotter_plugin_{source}_{re.sub(r"[^0-9a-zA-Z_]", "_", path.stem)}'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        meta = getattr(module, 'PLUGIN', None)
        if not isinstance(meta, dict) or not callable(getattr(module, 'run', None)):
            raise PluginError('A plugin needs a PLUGIN dictionary and a run(df, p, ctx) function.')
        meta = validate_meta(meta)
        return {**meta, 'module': module, 'source': source, 'file': path.name, 'path': str(path),
                'imports': imported_modules(path)}

    # -------------------------------------------------------------- listing & running
    def describe(self, missing=lambda ids: [], blocked=lambda requires, imports: []):
        """missing(requires): modules not installed; blocked(requires, imports): [module, error] pairs of
        installed modules (or parts of them) that do not import, so the analysis cannot run."""
        out = []
        for p in sorted(self.plugins.values(), key=lambda p: (CATEGORIES.index(p['category'])
                                                               if p['category'] in CATEGORIES else 99, p['order'], p['id'])):
            out.append({k: p[k] for k in ('id', 'name', 'description', 'category', 'params', 'requires',
                                           'references', 'source', 'file', 'overrides', 'steps')}
                       | {'missing': missing(p['requires']), 'blocked': blocked(p['requires'], p['imports'])})
        return {'plugins': out, 'errors': self.errors, 'user_dir': str(self.user_dir)}

    def get(self, pid):
        p = self.plugins.get(pid)
        if not p:
            raise PluginError(f'Unknown analysis: {pid}')
        return p

    def run(self, pid, df, params, lang='en', spec=None, builtin=False, depth=0):
        plugin = self.builtins.get(pid) if builtin else None
        plugin = plugin or self.get(pid)
        if depth > 5:
            raise PluginError('Recipes nested too deeply (a recipe that calls itself?).')
        values = coerce_params(plugin['params'], params or {}, df, roles(spec or {}, df))

        def runner(sub_id, sub_df, sub_params):
            return self.run(sub_id, sub_df, sub_params, lang, spec, builtin=True, depth=depth + 1)[2]

        ctx = Context(lang, spec, runner)
        result = plugin['module'].run(df, values, ctx)
        if not isinstance(result, Result):
            raise PluginError('run() must return ctx.result() (a Result).')
        result.cite(*plugin['references'])
        return plugin, values, result

    # -------------------------------------------------------------- user files
    def user_path(self, filename):
        name = str(filename or '')
        if not re.fullmatch(r'[A-Za-z0-9_\-]+\.py', name):
            raise PluginError('Plugin file names may contain letters, digits, _ and - and must end in .py')
        return self.user_dir / name

    def read(self, filename=None, pid=None):
        if pid:
            p = self.get(pid)
            return {'file': p['file'], 'source': p['source'], 'code': Path(p['path']).read_text(encoding='utf-8')}
        path = self.user_path(filename)
        return {'file': path.name, 'source': 'user', 'code': path.read_text(encoding='utf-8')}

    def save(self, filename, code):
        path = self.user_path(filename)
        self.user_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.py.tmp')
        tmp.write_text(code, encoding='utf-8')
        tmp.replace(path)
        self.reload()
        errors = [e for e in self.errors if e['file'] == path.name]
        return {'file': path.name, 'errors': errors}

    def create(self, name):
        slug = re.sub(r'[^a-z0-9_]+', '_', str(name or 'my_analysis').strip().lower()).strip('_') or 'my_analysis'
        path, n = self.user_path(f'{slug}.py'), 1
        while path.exists() or slug in self.plugins:
            n += 1
            path = self.user_path(f'{slug}_{n}.py')
        pid = path.stem
        title = ' '.join(str(name or 'My analysis').split())     # one line; repr() escapes quotes and backslashes
        code = (TEMPLATE.replace('my_analysis', pid)
                .replace("{'en': 'My analysis', 'it': 'La mia analisi'}", f"{{'en': {title!r}, 'it': {title!r}}}"))
        return self.save(path.name, code)

    def create_integration(self, package, import_name):
        """A first analysis that uses one of the user's modules (listed in its "requires"): the start of an
        integration, which puts the module's icon in the bar of plot types. Returns save()'s answer."""
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', str(package or '')) \
                or not str(import_name or '').isidentifier():
            raise PluginError('Not a package name.')
        slug = re.sub(r'[^a-z0-9_]+', '_', package.lower()).strip('_')[:40]
        slug = slug if slug[:1].isalpha() else 'm_' + slug
        path, n = self.user_path(f'{slug}_tools.py'), 1
        while path.exists() or path.stem in self.plugins:
            n += 1
            path = self.user_path(f'{slug}_tools_{n}.py')
        code = (INTEGRATION.replace('PACKAGE', package).replace('IMPORT_NAME', import_name)
                .replace('PLUGIN_ID', path.stem))
        return self.save(path.name, code)

    def customize(self, pid):
        """Copy a built-in analysis into the user folder (same id → replaces the built-in)."""
        p = self.get(pid)
        if p['source'] == 'user':
            return {'file': p['file'], 'errors': []}
        target = self.user_path(Path(p['path']).name)
        if not target.exists():
            self.user_dir.mkdir(parents=True, exist_ok=True)
            code = Path(p['path']).read_text(encoding='utf-8')
            code = (f'# Customised copy of the built-in analysis "{pid}" (PyPlotter {pid}).\n'
                    f'# It replaces the built-in one while this file exists; delete or disable it to go back.\n\n') + code
            target.write_text(code, encoding='utf-8')
        self.reload()
        return {'file': target.name, 'errors': [e for e in self.errors if e['file'] == target.name]}

    def disable(self, filename):
        """Rename a user plugin to .py.disabled (nothing is deleted)."""
        path = self.user_path(filename)
        if path.exists():
            target = path.with_suffix('.py.disabled')
            if target.exists():
                target = path.with_name(path.stem + f'.{int(path.stat().st_mtime)}.py.disabled')
            shutil.move(str(path), str(target))
        self.reload()
        return {'file': path.name}

    def open_folder(self):
        import subprocess
        self.user_dir.mkdir(parents=True, exist_ok=True)
        cmd = {'darwin': ['open'], 'win32': ['explorer']}.get(sys.platform, ['xdg-open'])
        subprocess.Popen(cmd + [str(self.user_dir)])
        return {'path': str(self.user_dir)}


# ------------------------------------------------------------------ validation
def _bilingual(v, fallback=''):
    if isinstance(v, dict):
        return {'en': str(v.get('en') or v.get('it') or fallback), 'it': str(v.get('it') or v.get('en') or fallback)}
    return {'en': str(v or fallback), 'it': str(v or fallback)}


def validate_meta(meta):
    pid = str(meta.get('id') or '')
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,60}', pid):
        raise PluginError('PLUGIN["id"] must be lower-case letters, digits and _ (e.g. "my_fit").')
    params = []
    for prm in meta.get('params', []):
        if not isinstance(prm, dict) or not prm.get('id') or prm.get('type') not in PARAM_TYPES:
            raise PluginError(f'Bad parameter {prm!r}: needs "id" and a "type" among {sorted(PARAM_TYPES)}.')
        q = dict(prm)
        q['label'] = _bilingual(prm.get('label'), prm['id'])
        q['help'] = _bilingual(prm.get('help'), '') if prm.get('help') else None
        if q['type'] == 'choice':
            choices = prm.get('choices') or []
            q['choices'] = [c if isinstance(c, dict) else {'value': c, 'label': _bilingual(c)} for c in choices]
            for c in q['choices']:
                c['label'] = _bilingual(c.get('label'), c['value'])
        params.append(q)
    category = meta.get('category', 'custom')
    return {'id': pid, 'name': _bilingual(meta.get('name'), pid), 'description': _bilingual(meta.get('description'), ''),
            'category': category if category in CATEGORIES else 'custom', 'params': params,
            'requires': [str(r) for r in meta.get('requires', [])], 'references': [str(r) for r in meta.get('references', [])],
            'order': int(meta.get('order', 50)),
            'steps': [_bilingual(s) for s in meta.get('steps', [])]}     # recipes: what they do, in order


ROLE_NAMES = {'x', 'y', 'y2', 'xerr', 'yerr', 'hue', 'z', 'ys', 'xs'}


def roles(spec, df):
    """Column defaults a plugin may ask for: 'x', 'y', 'y2', 'yerr', 'hue', 'z' (one column), 'ys', 'xs' (lists)."""
    ys = [c for c in (spec.get('y') or []) if c in df.columns]
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    x = spec.get('x') if spec.get('x') in df.columns else None
    if not ys:
        ys = [c for c in numeric if c != x][:1]
    out = {k: (spec.get(k) if spec.get(k) in df.columns else None) for k in ('xerr', 'yerr', 'hue', 'z')}
    out.update(x=x, y=ys[0] if ys else None,
               y2=(ys[1] if len(ys) > 1 else next((c for c in (spec.get('y2') or []) if c in df.columns), None)),
               ys=ys, xs=[x] if x else [])
    return out


def parse_points(text, label='points'):
    """[(x, y or None), …] from text with one point per line (or separated by ;): "x" or "x y".

    A decimal comma is accepted ("1003,5"); a comma between numbers is not a separator, so that
    "100, 200" is refused instead of being read as one point.
    """
    if isinstance(text, (list, tuple)):
        return [(float(q[0]), None if len(q) < 2 or q[1] is None else float(q[1])) for q in text]
    out = []
    for part in re.split(r'[;\n]+', str(text or '')):
        tokens = part.split()
        if not tokens:
            continue
        try:
            nums = [float(tok.replace(',', '.')) if tok.count(',') == 1 and '.' not in tok and not tok.endswith(',')
                    else float(tok) for tok in tokens]
        except ValueError:
            raise PluginError(f'“{label}”: “{part.strip()}” is not a point. Write x, or x and y separated by a '
                              f'space, one point per line (or separated by ;).')
        if len(nums) > 2 or not all(math.isfinite(n) for n in nums):
            raise PluginError(f'“{label}”: “{part.strip()}” is not a point. Write x, or x and y separated by a '
                              f'space, one point per line (or separated by ;).')
        out.append((nums[0], nums[1] if len(nums) == 2 else None))
    return out


def coerce_params(params, given, df, role_values=None):
    role_values = role_values or {}
    out = {}
    for prm in params:
        pid, typ = prm['id'], prm['type']
        v = given.get(pid, prm.get('default'))
        if typ in ('column', 'columns') and isinstance(v, str) and v in ROLE_NAMES and v not in df.columns:
            v = role_values.get(v)
        optional = prm.get('optional', False)
        if typ == 'column':
            if v in (None, ''):
                if optional:
                    out[pid] = None
                    continue
                raise PluginError(f'Choose a column for “{prm["label"]["en"]}”.')
            if v not in df.columns:
                raise PluginError(f'Column not found: {v}')
        elif typ == 'columns':
            v = [c for c in (v or []) if c]
            missing = [c for c in v if c not in df.columns]
            if missing:
                raise PluginError('Columns not found: ' + ', '.join(missing))
            if not v and not optional:
                raise PluginError(f'Choose at least one column for “{prm["label"]["en"]}”.')
            if prm.get('min_count') and len(v) < prm['min_count']:
                raise PluginError(f'Choose at least {prm["min_count"]} columns for “{prm["label"]["en"]}”.')
            if prm.get('max_count') and len(v) > prm['max_count']:
                raise PluginError(f'Choose at most {prm["max_count"]:,} columns for “{prm["label"]["en"]}” '
                                  f'({len(v):,} chosen).')
        elif typ in ('int', 'float'):
            if v in (None, ''):
                if optional:
                    out[pid] = None
                    continue
                raise PluginError(f'“{prm["label"]["en"]}” needs a number.')
            try:
                v = int(float(v)) if typ == 'int' else float(v)
            except (TypeError, ValueError):
                raise PluginError(f'“{prm["label"]["en"]}” needs a number.')
            if prm.get('min') is not None and v < prm['min']:
                raise PluginError(f'“{prm["label"]["en"]}” must be ≥ {prm["min"]}.')
            if prm.get('max') is not None and v > prm['max']:
                raise PluginError(f'“{prm["label"]["en"]}” must be ≤ {prm["max"]}.')
        elif typ == 'bool':
            v = bool(v) and v not in ('false', '0', 'no')
        elif typ == 'choice':
            allowed = [c['value'] for c in prm['choices']]
            if v not in allowed:
                v = allowed[0] if allowed else None
        elif typ == 'points':
            v = parse_points(v, prm['label']['en'])
        else:
            v = '' if v is None else str(v)
        out[pid] = v
    return out


def imported_modules(path):
    """Every module a plugin file imports, wherever the import is (top level or inside run()):
    "from a import b" gives "a" and "a.b", since b may be a submodule."""
    import ast
    try:
        tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    except (OSError, SyntaxError, ValueError):
        return []
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module)
            out.update(f'{node.module}.{a.name}' for a in node.names if a.name != '*')
    return sorted(out)


def _short_tb(exc, path):
    tb = traceback.extract_tb(exc.__traceback__)
    lines = [f'line {f.lineno}: {f.line}' for f in tb if f.filename == str(path)]
    where = (lines[-1] + '\n') if lines else ''
    if isinstance(exc, SyntaxError):
        where = f'line {exc.lineno}: {(exc.text or "").strip()}\n'
    return f'{where}{exc.__class__.__name__}: {exc}'


TEMPLATE = '''"""My analysis — a PyPlotter plugin (edit freely, then "Save & reload").

PyPlotter calls run(df, p, ctx):
  df   the current data as a pandas DataFrame
  p    the parameter values chosen in the form (types already checked)
  ctx  helpers: ctx.result(), ctx.xy(df, x, y), ctx.numeric(df, col), ctx.tr(en, it), ctx.lang
Return ctx.result() filled with any of:
  .value(label, value, error=None, unit='')   one line of the summary table
  .table(title, DataFrame | list of dicts)    a table
  .text('...')                                a paragraph
  .data(DataFrame, plot={...})                a new data set to plot/export like any file
  .cite('Author, Journal (year). doi:...')    references to show with the result
Use any installed Python module; list registry modules in "requires" so PyPlotter installs them.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'my_analysis',
    'name': {'en': 'My analysis', 'it': 'La mia analisi'},
    'category': 'custom',
    'description': {'en': 'Mean and moving average of a column.', 'it': 'Media e media mobile di una colonna.'},
    'requires': [],                       # e.g. ['scipy'] or ['statsmodels']
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Column', 'it': 'Colonna'}},
        {'id': 'window', 'type': 'int', 'default': 10, 'min': 1, 'label': {'en': 'Window (points)', 'it': 'Finestra (punti)'}},
    ],
    'references': [],
}


def run(df, p, ctx):
    x, y = ctx.xy(df, p['x'], p['y'])
    smooth = pd.Series(y).rolling(p['window'], center=True, min_periods=1).mean().to_numpy()
    r = ctx.result()
    r.value(ctx.tr('Mean', 'Media'), y.mean(), y.std(ddof=1) / np.sqrt(y.size))
    r.value('N', y.size)
    xname = p['x'] or 'index'
    out = pd.DataFrame({xname: x, p['y']: y, 'moving average': smooth})
    r.data(out, plot={'kind': 'line', 'x': xname, 'y': [p['y'], 'moving average'],
                      'series': {p['y']: {'alpha': 0.4}}})
    return r
'''


INTEGRATION = '''"""PACKAGE in PyPlotter — the start of an integration (edit freely, then "Save & reload").

Every analysis whose PLUGIN lists "PACKAGE" in "requires" is a function of the PACKAGE icon in the
bar of plot types; copy this file (with a new "id") for each function you want there. The module is
imported inside run(), so PyPlotter starts even where PACKAGE is not installed.

PyPlotter calls run(df, p, ctx):
  df   the current data as a pandas DataFrame
  p    the parameter values chosen in the form (types already checked)
  ctx  helpers: ctx.result(), ctx.xy(df, x, y), ctx.numeric(df, col), ctx.tr(en, it), ctx.lang
Return ctx.result() filled with .value(), .table(), .text(), .data(DataFrame, plot={...}),
.overlay(...) (a curve over the figure) and .cite(...): see PLUGINS.md.
"""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'PLUGIN_ID',
    'name': {'en': 'PACKAGE: first function', 'it': 'PACKAGE: prima funzione'},
    'category': 'custom',
    'description': {'en': 'Starting point: hands one column to PACKAGE. Edit run() to call its functions.',
                    'it': 'Punto di partenza: passa una colonna a PACKAGE. Modifica run() per usarne le funzioni.'},
    'requires': ['PACKAGE'],
    'params': [
        {'id': 'x', 'type': 'column', 'optional': True, 'default': 'x', 'label': {'en': 'X (optional)', 'it': 'X (facoltativa)'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Column', 'it': 'Colonna'}},
    ],
    'references': [],
}


def run(df, p, ctx):
    import IMPORT_NAME

    x, y = ctx.xy(df, p['x'], p['y'])
    r = ctx.result()
    r.value(ctx.tr('PACKAGE version', 'Versione di PACKAGE'), getattr(IMPORT_NAME, '__version__', '?'))
    r.value('N', y.size)
    # Call PACKAGE here on x and y, then show what it returns, e.g. a new curve over the figure:
    #   out = pd.DataFrame({'x': x, 'result': y})
    #   r.overlay(out, 'x', 'result', label='PACKAGE')
    return r
'''
