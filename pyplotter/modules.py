"""Optional Python modules: registry, installed/latest versions and background pip installs.

Standard library only. The registry (registry.json) lists every package PyPlotter can use.
At each start the latest versions are fetched from PyPI in the background and cached in
~/.pyplotter/pypi-cache.json, so the list also works offline. Installs run
``python -m pip`` in this interpreter's environment and report a single progress value.
Installed modules are also imported once in a separate Python (at start and after every
install), so a package that pip lists but that cannot be loaded is reported as broken. The user's
modules are imported with their submodules: one whose parts all fail is unusable, even when its
top-level ``import`` works; one where only some parts fail works in part.

Besides the registry, the user can add any package from PyPI ("your modules"): its licence and the
licences of everything pip would install with it are shown first, a licence that is not
OSI-approved needs an explicit confirmation, and the choice is recorded in
~/.pyplotter/user-modules.json (so the modules can be installed again in a new environment).
A module that cannot be used once installed is removed again, with what came with it.
"""
import importlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import licenses

REGISTRY_FILE = Path(__file__).with_name('registry.json')
STATE_DIR = Path(os.environ.get('PYPLOTTER_HOME') or Path.home() / '.pyplotter')
PYPI_URL = 'https://pypi.org/pypi/{}/json'
PIP_MIN = (24, 1)          # first pip with --progress-bar raw
LOG_TAIL = 400
IMPORT_TIMEOUT = 180       # seconds for one import check (first imports compile and build caches)
# Run in a separate Python: a broken module cannot crash the service, and this process does not
# load modules it does not use (which would also mark them as needing a restart after an update).
IMPORT_CHECK = '''import importlib, sys
try:
    importlib.import_module(sys.argv[1])
except BaseException as exc:
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(1)
'''
# The user's modules are checked deeper: a package whose __init__ imports nothing (uvvispy) loads
# even when every part that does the work fails. Each top-level module and its public direct
# submodules are imported; a "PYPLOTTER-TRY" line before each import names the culprit if Python
# dies, and one "PYPLOTTER-RESULT" JSON line ends the check. What the packages print goes to stderr.
DEEP_CHECK = '''import importlib, json, pkgutil, sys, types
out, sys.stdout = sys.stdout, sys.stderr
SKIP = set(json.loads(sys.argv.pop(1)))
res = {"top": [], "own": 0, "parts": 0, "failed": []}
def attempt(name):
    print("PYPLOTTER-TRY " + name, file=out, flush=True)
    try:
        return importlib.import_module(name), ""
    except BaseException as exc:
        return None, f"{type(exc).__name__}: {exc}"[:300]
for top in sys.argv[1:]:
    mod, err = attempt(top)
    res["top"].append([top, err])
    if mod is None:
        continue
    res["own"] += sum(1 for k, v in vars(mod).items() if not k.startswith("_") and not isinstance(v, types.ModuleType))
    for info in sorted(pkgutil.iter_modules(getattr(mod, "__path__", None) or []), key=lambda i: i.name)[:80]:
        if info.name.startswith("_") or info.name in SKIP:
            continue
        res["parts"] += 1
        _, err = attempt(top + "." + info.name)
        if err:
            res["failed"].append([top + "." + info.name, err])
print("PYPLOTTER-RESULT " + json.dumps(res), file=out, flush=True)
'''
DEEP_SKIP = {'test', 'tests', 'testing', 'conftest', 'setup', 'docs', 'doc', 'examples', 'example', 'benchmarks'}


def _deep_names(imports):
    """The top-level modules of a user's module to check (a stray "tests" package is not one)."""
    return [n for n in imports if n not in DEEP_SKIP] or list(imports[:1])


def deep_verdict(stdout, returncode):
    """{'ok', 'error', 'failed', 'parts'} from the output of DEEP_CHECK. failed: the [module, error]
    pairs that do not import, out of `parts` (the submodules, plus the top level when it defines
    anything itself). A module is unusable when its top level fails or more than half of its parts
    fail (uvvispy: 6 of 6, aspecd: 14 of 16); with fewer failures (optional parts) it works in part."""
    lines = (stdout or '').splitlines()
    found = next((l.split(' ', 1)[1] for l in reversed(lines) if l.startswith('PYPLOTTER-RESULT ')), None)
    if found is None:
        last = next((l.split(' ', 1)[1] for l in reversed(lines) if l.startswith('PYPLOTTER-TRY ')), '?')
        return {'ok': False, 'error': f'Python stopped while importing {last} (exit code {returncode}).',
                'failed': [], 'parts': 0}
    res = json.loads(found)
    bad_top = [[n, e] for n, e in res['top'] if e]
    if len(bad_top) == len(res['top']):
        return {'ok': False, 'error': bad_top[0][1] if bad_top else 'Nothing to import.', 'failed': [], 'parts': 0}
    failed = bad_top + res['failed']
    parts = res['parts'] + len(res['top']) - 1 + (1 if res['own'] else 0)
    if 2 * len(failed) > parts:
        return {'ok': False, 'error': failed[0][1], 'failed': failed, 'parts': parts}
    return {'ok': True, 'error': '', 'failed': failed, 'parts': parts}


# A plain PyPI project name (PEP 508): no version, extras, URL, path or pip option can get through.
PACKAGE_NAME = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?')
USER_SCHEMA = 'pyplotter-user-modules/1'


class MissingModules(Exception):
    """Raised when an action needs registry modules that are not installed."""

    def __init__(self, ids):
        self.ids = list(ids)
        super().__init__('Missing modules: ' + ', '.join(self.ids))


class MissingUserModules(Exception):
    """Raised when an action needs modules the user added that are not installed (e.g. a new environment)."""

    def __init__(self, names):
        self.names = list(names)
        super().__init__('Not installed: ' + ', '.join(self.names) + '. Install them again from '
                         'Modules › Your modules.')


def canonical(name):
    """PEP 503 normalised project name (Scikit_Learn → scikit-learn)."""
    return re.sub(r'[-_.]+', '-', str(name)).lower()


def check_package_name(name):
    """The name as typed, if it is a plain PyPI project name; ValueError otherwise."""
    name = str(name or '').strip()
    if not PACKAGE_NAME.fullmatch(name):
        raise ValueError('Type only the name of a package on PyPI (letters, digits, “-”, “_”, “.”), without '
                         'a version, URL, path or pip option.')
    return name


def dist_info(name):
    """The installed distribution: {'name', 'version', 'license', 'status', 'summary', 'imports'}, or None."""
    try:
        dist = metadata.distribution(name)
        meta = dist.metadata
    except Exception:          # not installed, or broken metadata of a half-installed package
        return None
    return {'name': meta['Name'] or name, 'version': dist.version, **licenses.from_metadata(meta),
            'summary': meta.get('Summary') or '', 'imports': import_names(dist, name)}


def import_names(dist, name):
    """Top-level modules a distribution installs (what ``import`` takes), best guess first."""
    try:
        top = (dist.read_text('top_level.txt') or '').split()
    except Exception:
        top = []
    if not top:
        found = set()
        for f in dist.files or []:
            parts = f.parts
            if not parts or parts[0].endswith(('.dist-info', '.egg-info', '.data')) or parts[0] in ('..', '__pycache__'):
                continue
            if len(parts) == 1 and parts[0].endswith('.py'):
                found.add(parts[0][:-3])
            elif len(parts) == 2 and parts[1] == '__init__.py':
                found.add(parts[0])
        top = sorted(found)
    guess = canonical(name).replace('-', '_')
    top = [t for t in dict.fromkeys(top) if t.isidentifier() and not t.startswith('_')]
    top.sort(key=lambda t: t != guess)
    return top or [guess]


def dependents(name):
    """Names of the installed distributions that need `name` (optional extras not counted)."""
    target, out = canonical(name), set()
    for dist in metadata.distributions():
        try:
            own, reqs = canonical(dist.metadata['Name'] or ''), dist.requires or []
        except Exception:
            continue
        if own == target:
            continue
        for r in reqs:
            req, _, marker = r.partition(';')
            m = re.match(r'\s*([A-Za-z0-9._-]+)', req)
            if m and canonical(m.group(1)) == target and 'extra' not in marker:
                out.add(dist.metadata['Name'])
    return sorted(out, key=str.lower)


def load_registry(path=REGISTRY_FILE):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not str(data.get('schema', '')).startswith('pyplotter-registry/'):
        raise ValueError(f'{path}: not a PyPlotter registry')
    seen = set()
    for m in data['modules']:
        for key in ('id', 'pip', 'import', 'category'):
            if not m.get(key):
                raise ValueError(f'{path}: module entry without "{key}": {m}')
        if m['id'] in seen:
            raise ValueError(f'{path}: duplicate module id {m["id"]}')
        seen.add(m['id'])
    return data['modules']


def version_tuple(text):
    """Comparable key for a version string; pre-releases sort before the release."""
    if not text:
        return ()
    match = re.match(r'\s*v?(\d+(?:\.\d+)*)(.*)', str(text))
    if not match:
        return ()
    release = tuple(int(p) for p in match.group(1).split('.'))
    release += (0,) * (4 - len(release))
    rest = match.group(2).lower()
    pre = 0 if re.match(r'[.\-_]?(a|b|rc|alpha|beta|pre|dev)', rest) else 1
    return release + (pre,)


def installed_version(dist):
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None
    except Exception:  # broken metadata of a half-installed package
        return None


def clean_appledouble(root=None):
    """Delete macOS AppleDouble files (``._name``) inside the Python environment.

    On exFAT/FAT drives macOS writes a ``._name`` companion for every file; packages that scan
    their own data folders (Matplotlib style sheets, for one) then fail to parse them.
    Only companions of existing files are removed. Returns the number of files deleted.
    """
    if sys.platform != 'darwin':
        return 0
    root = Path(root or sys.prefix)
    if root == Path(sys.base_prefix):      # never touch a system-wide Python
        return 0
    removed = 0
    for folder, _dirs, files in os.walk(root):
        names = set(files)
        for name in files:
            if name.startswith('._') and (name[2:] in names or os.path.isdir(os.path.join(folder, name[2:]))):
                try:
                    os.unlink(os.path.join(folder, name))
                    removed += 1
                except OSError:
                    pass
    return removed


def _ssl_context():
    # python.org builds on macOS often lack CA certificates; pip's vendored certifi always exists.
    for name in ('certifi', 'pip._vendor.certifi'):
        try:
            return ssl.create_default_context(cafile=importlib.import_module(name).where())
        except Exception:
            continue
    return ssl.create_default_context()


def fetch_latest(dist, timeout=6.0, context=None):
    req = urllib.request.Request(PYPI_URL.format(dist), headers={'Accept': 'application/json', 'User-Agent': 'PyPlotter'})
    with urllib.request.urlopen(req, timeout=timeout, context=context or _ssl_context()) as resp:
        return json.load(resp)['info']['version']


class Job:
    """One background task with a 0..1 progress value and an i18n phase key."""

    def __init__(self, kind, title):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.state = 'running'          # running | done | error | cancelled
        self.phase = 'preparing'
        self.detail = ''
        self.progress = 0.0
        self.error = ''
        self.result = {}
        self.log = []
        self.started = time.time()
        self._proc = None
        self._cancel = False
        self._lock = threading.Lock()

    def add_log(self, line):
        with self._lock:
            self.log.append(line)
            del self.log[:-LOG_TAIL]

    def set(self, progress=None, phase=None, detail=None):
        with self._lock:
            if progress is not None:
                self.progress = max(self.progress, min(1.0, float(progress)))
            if phase is not None:
                self.phase = phase
            if detail is not None:
                self.detail = detail

    def cancel(self):
        self._cancel = True
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()

    def to_dict(self, with_log=False):
        with self._lock:
            out = {'id': self.id, 'kind': self.kind, 'title': self.title, 'state': self.state,
                   'phase': self.phase, 'detail': self.detail, 'progress': round(self.progress, 4),
                   'error': self.error, 'result': self.result, 'elapsed': round(time.time() - self.started, 1)}
            if with_log or self.state == 'error':
                out['log'] = self.log[-120:]
            return out


class PipProgress:
    """Turns pip's output into one progress value.

    0-5 % preparing (pip upgrade), 5-15 % resolving (dry run), 15-85 % downloads,
    85-100 % building/installing. Downloads are weighted equally; ``Progress a of b``
    lines (``--progress-bar raw``) move the bar inside the current download.
    """

    DOWNLOAD = re.compile(r'^\s*(Downloading|Using cached)\s+(\S+)')
    RAW = re.compile(r'^Progress (\d+) of (\d+)')

    def __init__(self, job, expected):
        self.job = job
        self.expected = max(1, expected)
        self.finished = 0          # downloads completed (or taken from the cache)
        self.current = None        # fraction of the running download
        self.seen = set()

    def _update(self):
        frac = (self.finished + (self.current or 0.0)) / self.expected
        self.job.set(0.15 + 0.70 * min(1.0, frac))

    def feed(self, line):
        line = line.rstrip()
        raw = self.RAW.match(line)
        if raw:
            done, total = int(raw.group(1)), int(raw.group(2))
            self.current = done / total if total else 0.0
            self._update()
            return
        dl = self.DOWNLOAD.match(line)
        if dl:
            name = dl.group(2)
            if name.endswith('.metadata') or name in self.seen:
                return
            self.seen.add(name)
            if self.current is not None:
                self.finished += 1
            if dl.group(1) == 'Using cached':
                self.finished += 1
                self.current = None
            else:
                self.current = 0.0
            self.job.set(phase='downloading', detail=_dist_from_file(name))
            self._update()
        elif line.startswith('Building wheel') or line.startswith('Building wheels'):
            self.job.set(0.85, phase='building', detail='')
        elif line.startswith('Installing collected packages'):
            self.job.set(0.88, phase='installing', detail=line.split(':', 1)[-1].strip()[:120])
        elif line.startswith('Successfully installed'):
            self.job.set(0.99, phase='installing')


def _dist_from_file(name):
    base = name.rsplit('/', 1)[-1]
    return re.split(r'-\d', base, maxsplit=1)[0]


class ModuleManager:
    def __init__(self, registry_path=REGISTRY_FILE, state_dir=STATE_DIR, python=None, online=True):
        self.modules = load_registry(registry_path)
        self.by_id = {m['id']: m for m in self.modules}
        self.state_dir = Path(state_dir)
        self.cache_file = self.state_dir / 'pypi-cache.json'
        self.python = python or sys.executable
        self.online = online
        self.jobs = {}
        self.install_lock = threading.Lock()   # one pip at a time
        self.restart_required = set()
        self._cache = self._read_cache()
        self.refresh_state = {'state': 'idle', 'checked_at': self._cache.get('checked_at'), 'error': ''}
        self.check_file = self.state_dir / 'import-check.json'
        self.checks = self._read_checks()   # id -> {'version', 'ok', 'error', 'gen'}: last import check
        self.check_state = {'state': 'idle', 'checked_at': None}
        self._check_gen = 0
        self._check_again = False
        self._check_lock = threading.Lock()
        self.user_file = self.state_dir / 'user-modules.json'
        self.user = self._read_user()          # canonical name -> record (see _install_user)
        self.registry_dists = {canonical(m['pip']): m['id'] for m in self.modules}

    # ------------------------------------------------------------ status
    def _read_cache(self):
        try:
            data = json.loads(self.cache_file.read_text(encoding='utf-8'))
            return data if isinstance(data.get('versions'), dict) else {'versions': {}}
        except Exception:
            return {'versions': {}}

    def _write_cache(self):
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix('.tmp')
            tmp.write_text(json.dumps(self._cache, indent=1), encoding='utf-8')
            tmp.replace(self.cache_file)
        except OSError:
            pass

    def _read_checks(self):
        """Import checks of earlier runs with this same Python, so a start only re-checks what changed."""
        try:
            data = json.loads(self.check_file.read_text(encoding='utf-8'))
            if data.get('python') == self.python and isinstance(data.get('checks'), dict):
                # A user's module checked before the deep check existed is checked again.
                return {k: {**v, 'gen': 0} for k, v in data['checks'].items()
                        if k in self.by_id or (k.startswith('user:') and v.get('deep'))}
        except Exception:
            pass
        return {}

    def _write_checks(self):
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.check_file.with_suffix('.tmp')
            tmp.write_text(json.dumps({'python': self.python, 'checks': {
                k: {key: v[key] for key in ('version', 'ok', 'error', 'failed', 'parts', 'deep') if key in v}
                for k, v in self.checks.items()}}, indent=1), encoding='utf-8')
            tmp.replace(self.check_file)
        except OSError:
            pass

    def installed(self, mid):
        m = self.by_id[mid]
        return installed_version(m['pip'])

    def missing(self, ids):
        """Registry ids that are not installed, and names of the user's modules that are not installed."""
        out = []
        for i in dict.fromkeys(ids):
            if i in self.by_id:
                if not self.installed(i):
                    out.append(i)
            elif canonical(i) in self.user and not installed_version(self.user[canonical(i)]['pip']):
                out.append(i)
        return out

    def require(self, ids):
        missing = self.missing(ids)
        known = [i for i in missing if i in self.by_id]
        if known:
            raise MissingModules(known)
        if missing:
            raise MissingUserModules(missing)
        importlib.invalidate_caches()

    def user_citations(self, ids):
        """The references the user wrote for their modules among ids (e.g. a plugin's "requires")."""
        return [self.user[canonical(i)]['cite'] for i in dict.fromkeys(ids)
                if canonical(i) in self.user and self.user[canonical(i)].get('cite')]

    def core_ids(self):
        return [m['id'] for m in self.modules if m.get('core')]

    def status(self):
        rows = []
        for m in self.modules:
            inst = installed_version(m['pip'])
            latest = self._cache['versions'].get(m['pip'])
            check = self.checks.get(m['id'])
            if not (inst and check and check['version'] == inst):
                check = None
            rows.append({
                'id': m['id'], 'pip': m['pip'], 'category': m['category'], 'core': bool(m.get('core')),
                'description': m.get('description', {}), 'url': m.get('url', ''), 'min': m.get('min', ''),
                'license': m.get('license', ''), 'cite': m.get('cite', ''),
                'installed': inst, 'latest': latest,
                'outdated': bool(inst and m.get('min') and version_tuple(inst) < version_tuple(m['min'])),
                'update': bool(inst and latest and version_tuple(latest) > version_tuple(inst)),
                'restart': m['id'] in self.restart_required,
                'works': check['ok'] if check else None,      # None: not checked yet
                'import_error': check['error'] if check else '',
            })
        return {'modules': rows, 'user_modules': self.user_status(), 'refresh': dict(self.refresh_state),
                'checks': dict(self.check_state), 'online': self.online and self.refresh_state['state'] != 'offline',
                'core_ready': all(r['installed'] and not r['outdated'] for r in rows if r['core']),
                'restart_required': bool(self.restart_required),
                'python': sys.version.split()[0], 'executable': self.python}

    # ------------------------------------------------------------ PyPI check (each start)
    def refresh_async(self):
        if self.refresh_state['state'] == 'running' or not self.online:
            return
        self.refresh_state.update(state='running', error='')
        threading.Thread(target=self._refresh, name='pypi-refresh', daemon=True).start()

    def _refresh(self):
        context = _ssl_context()
        versions, errors = {}, []

        def one(m):
            try:
                versions[m['pip']] = fetch_latest(m['pip'], context=context)
            except Exception as exc:
                errors.append(f'{m["pip"]}: {exc}')

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(one, self.modules))
        if versions:
            self._cache['versions'].update(versions)
            self._cache['checked_at'] = time.time()
            self._write_cache()
        self.refresh_state.update(
            state='done' if versions else 'offline',
            checked_at=self._cache.get('checked_at'),
            error=errors[0] if errors and not versions else '')

    # ------------------------------------------------------------ import check (each start, after installs)
    def _check_targets(self):
        """(check key, distribution, modules to import) of every registry module and user module.
        A registry module imports one name; a user's module all its top-level names."""
        out = [(m['id'], m['pip'], [m.get('check') or m['import']]) for m in self.modules]
        for k, r in self.user.items():
            out.append(('user:' + k, r['pip'], _deep_names(r.get('imports') or [k.replace('-', '_')])))
        return out

    def check_import(self, mid):
        """Import a module in a fresh Python: {'ok', 'error', 'failed', 'parts'} (see deep_verdict).
        The user's modules are checked with their submodules (DEEP_CHECK), the registry's shallowly."""
        names = next((t[2] for t in self._check_targets() if t[0] == mid), None)
        if names is None:
            return {'ok': False, 'error': f'Unknown module {mid}.', 'failed': [], 'parts': 0}
        return self._run_check(names, deep=mid.startswith('user:'))

    def _run_check(self, names, deep):
        args = ['-c', DEEP_CHECK, json.dumps(sorted(DEEP_SKIP)), *names] if deep else ['-c', IMPORT_CHECK, names[0]]
        env = dict(os.environ, MPLBACKEND='Agg', PYTHONUNBUFFERED='1')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        try:
            out = subprocess.run([self.python, *args],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace', env=env,
                                 cwd=tempfile.gettempdir(), timeout=IMPORT_TIMEOUT, creationflags=flags)
        except subprocess.TimeoutExpired as exc:
            seen = exc.stdout.decode('utf-8', 'replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            last = next((l.split(' ', 1)[1] for l in reversed(seen.splitlines()) if l.startswith('PYPLOTTER-TRY ')),
                        names[0])
            return {'ok': False, 'error': f'The import of {last} did not finish within {IMPORT_TIMEOUT} s.',
                    'failed': [], 'parts': 0}
        except OSError as exc:
            return {'ok': False, 'error': str(exc), 'failed': [], 'parts': 0}
        if deep:
            return deep_verdict(out.stdout, out.returncode)
        if out.returncode == 0:
            return {'ok': True, 'error': '', 'failed': [], 'parts': 0}
        lines = [l for l in (out.stdout.strip() or out.stderr.strip()).splitlines() if l.strip()]
        error = lines[-1][:500] if lines else f'Python stopped while importing {names[0]} (exit code {out.returncode}).'
        return {'ok': False, 'error': error, 'failed': [], 'parts': 0}

    def verify_async(self, force=False):
        """Check in the background that installed modules import. force: check again even if
        the version did not change (an install may have changed a shared dependency)."""
        with self._check_lock:
            if force:
                self._check_gen += 1
            if self.check_state['state'] == 'running':
                self._check_again = True
                return
            self.check_state['state'] = 'running'
        threading.Thread(target=self._verify, name='import-check', daemon=True).start()

    def _verify(self):
        while True:
            gen = self._check_gen
            todo = []
            for key, dist, _ in self._check_targets():
                version = installed_version(dist)
                old = self.checks.get(key)
                # New or changed version, a forced check, or a module that failed before, even in part
                # (it may be fixed now).
                if version and not (old and old['version'] == version and old['gen'] >= gen and old['ok']
                                    and not old.get('failed')):
                    todo.append((key, version))

            def one(item):
                self.checks[item[0]] = {**self.check_import(item[0]), 'version': item[1], 'gen': gen,
                                        'deep': item[0].startswith('user:')}

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(one, todo))
            if todo:
                self._write_checks()
            with self._check_lock:
                if not self._check_again:
                    self.check_state.update(state='done', checked_at=time.time())
                    return
                self._check_again = False

    # ------------------------------------------------------------ installs
    def job(self, jid):
        return self.jobs.get(jid)

    def start_install(self, ids, upgrade=False, reinstall=False):
        """reinstall: install the same version again over a broken one (dependencies untouched)."""
        ids = [i for i in dict.fromkeys(ids) if i in self.by_id]
        if not ids:
            raise ValueError('No known module to install.')
        for job in self.jobs.values():   # same request already running: reuse it
            if job.state == 'running' and job.kind == 'install' and job.result.get('ids') == ids:
                return job
        job = Job('install', ', '.join(self.by_id[i]['pip'] for i in ids))
        job.result = {'ids': ids, 'upgrade': bool(upgrade), 'reinstall': bool(reinstall)}
        self.jobs[job.id] = job
        threading.Thread(target=self._run_install, args=(job, ids, upgrade, reinstall), name=f'pip-{job.id}',
                         daemon=True).start()
        return job

    def _specs(self, ids, upgrade, reinstall=False):
        specs = []
        for i in ids:
            m = self.by_id[i]
            current = self.installed(i)
            if reinstall and current:
                specs.append(f'{m["pip"]}=={current}')
            else:
                specs.append(m['pip'] if upgrade or not m.get('min') else f'{m["pip"]}>={m["min"]}')
        return specs

    def _pip(self, job, args, on_line=None):
        env = dict(os.environ, PYTHONUNBUFFERED='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_INPUT='1',
                   PIP_NO_COLOR='1')
        cmd = [self.python, '-m', 'pip'] + args
        job.add_log('$ ' + ' '.join(cmd))
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=flags)
        job._proc = proc
        for line in proc.stdout:
            if not line.startswith('Progress '):
                job.add_log(line.rstrip())
            if on_line:
                on_line(line)
        proc.wait()
        job._proc = None
        if job._cancel:
            raise InterruptedError
        return proc.returncode

    def pip_version(self):
        try:
            out = subprocess.run([self.python, '-m', 'pip', '--version'], capture_output=True, text=True, timeout=60)
            return version_tuple(out.stdout.split()[1])[:2] if out.returncode == 0 else ()
        except Exception:
            return ()

    def _run_install(self, job, ids, upgrade, reinstall=False):
        with self.install_lock:
            state = 'done'
            try:
                self._install(job, ids, upgrade, reinstall)
            except InterruptedError:
                state = 'cancelled'
            except Exception as exc:
                job.error = str(exc) or exc.__class__.__name__
                state = 'error'
            # Check every module again (shared dependencies may have changed), and start before the
            # job ends so the page sees the check running and follows it.
            self.verify_async(force=True)
            job.state = state

    def externally_managed(self):
        """True for a system/Homebrew Python that forbids pip installs (PEP 668) and is not a venv."""
        if self.python != sys.executable or sys.prefix != sys.base_prefix:
            return False
        import sysconfig
        return Path(sysconfig.get_path('stdlib'), 'EXTERNALLY-MANAGED').exists()

    def _prepare_pip(self, job):
        if self.externally_managed():
            raise RuntimeError(f'{self.python} is managed by the system or Homebrew and cannot receive packages. '
                               'Start PyPlotter with start_pyplotter.command / .bat or start_pyplotter.py, '
                               'which use the private .venv environment.')
        job.set(0.01, phase='preparing')
        pipv = self.pip_version()
        if not pipv:
            raise RuntimeError('pip is not available in this Python environment.')
        if pipv < PIP_MIN:
            if self._pip(job, ['install', '--upgrade', 'pip']) != 0:
                raise RuntimeError(_pip_error(job.log, 'Updating pip failed.'))

    def _dry_run(self, job, args):
        """What pip would install for `args`: the entries of its installation report (with metadata)."""
        fd, report = tempfile.mkstemp(suffix='.json', prefix='pyplotter-pip-')
        os.close(fd)
        try:
            if self._pip(job, ['install', '--dry-run', '--quiet', '--report', report] + args) != 0:
                raise RuntimeError(_pip_error(job.log, 'pip could not resolve the packages.'))
            try:
                return json.loads(Path(report).read_text(encoding='utf-8')).get('install', [])
            except Exception:
                return []
        finally:
            os.unlink(report)

    def _install(self, job, ids, upgrade, reinstall=False):
        before = {i: self.installed(i) for i in ids}
        self._prepare_pip(job)
        job.set(0.05, phase='resolving')
        specs = self._specs(ids, upgrade, reinstall)
        extra = ['--upgrade'] if upgrade else []
        if reinstall:
            extra += ['--force-reinstall', '--no-deps']
        planned = self._dry_run(job, extra + specs)
        names = [p.get('metadata', {}).get('name', '?') for p in planned]
        job.result['planned'] = names
        job.set(0.15, phase='downloading' if names else 'installing')
        if names:
            tracker = PipProgress(job, len(names))
            if self._pip(job, ['install', '--progress-bar', 'raw'] + extra + specs, tracker.feed) != 0:
                raise RuntimeError(_pip_error(job.log, 'Installation failed.'))
        job.set(0.995, phase='installing')
        clean_appledouble()
        importlib.invalidate_caches()
        after = {i: self.installed(i) for i in ids}
        # A module already imported by this process keeps its old code until restart.
        loaded = {p.get('metadata', {}).get('name', '').lower().replace('_', '-') for p in planned}
        for m in self.modules:
            dist = m['pip'].lower().replace('_', '-')
            if dist in loaded and m['import'] in sys.modules and before.get(m['id']) != installed_version(m['pip']):
                self.restart_required.add(m['id'])
        job.result.update(installed=after, restart=bool(self.restart_required))
        missing = [i for i, v in after.items() if not v]
        if missing:
            raise RuntimeError('Not installed: ' + ', '.join(missing))
        job.set(1.0, phase='done', detail='')


    # ------------------------------------------------------------ the user's own modules (from PyPI)
    def _read_user(self):
        try:
            data = json.loads(self.user_file.read_text(encoding='utf-8'))
            if not str(data.get('schema', '')).startswith('pyplotter-user-modules/'):
                return {}
            # Names are checked again: the file must not be able to pass options to pip.
            return {canonical(r['pip']): r for r in data.get('modules', [])
                    if isinstance(r, dict) and PACKAGE_NAME.fullmatch(str(r.get('pip', '')))}
        except Exception:
            return {}

    def _write_user(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.user_file.with_suffix('.tmp')
        tmp.write_text(json.dumps({'schema': USER_SCHEMA, 'modules': sorted(self.user.values(), key=lambda r: canonical(r['pip']))},
                                  indent=1, ensure_ascii=False), encoding='utf-8')
        tmp.replace(self.user_file)

    def user_status(self):
        rows = []
        for key, r in sorted(self.user.items()):
            inst = installed_version(r['pip'])
            check = self.checks.get('user:' + key)
            if not (inst and check and check['version'] == inst):
                check = None
            rows.append({'name': r['pip'], 'key': key, 'installed': inst, 'version': r.get('version', ''),
                         'license': r.get('license', ''), 'status': r.get('status', 'unknown'),
                         'accepted': bool(r.get('accepted')), 'summary': r.get('summary', ''),
                         'imports': r.get('imports', []), 'packages': r.get('packages', []), 'cite': r.get('cite', ''),
                         'added': r.get('added'), 'restart': 'user:' + key in self.restart_required,
                         'works': check['ok'] if check else None, 'import_error': check['error'] if check else '',
                         # submodules that do not import (all of them when works is False), out of import_parts
                         'import_failed': check.get('failed', []) if check else [],
                         'import_parts': check.get('parts', 0) if check else 0})
        return rows

    def _new_job(self, kind, title, target, *args):
        job = Job(kind, title)
        self.jobs[job.id] = job

        def run():
            try:
                target(job, *args)
                job.state = 'done'
            except InterruptedError:
                job.state = 'cancelled'
            except Exception as exc:
                job.error = str(exc) or exc.__class__.__name__
                job.state = 'error'
        threading.Thread(target=run, name=f'{kind}-{job.id}', daemon=True).start()
        return job

    def start_inspect(self, name):
        """Background dry run: the package, its licence and every package pip would install with it."""
        name = check_package_name(name)
        if canonical(name) in self.registry_dists:
            raise ValueError(f'“{name}” is already in PyPlotter’s list: install it there.')
        if not self.online:
            raise ValueError('Adding modules needs the internet (PyPlotter was started offline).')
        return self._new_job('inspect', name, self._inspect, name)

    def _inspect(self, job, name):
        self._prepare_pip(job)
        job.set(0.3, phase='resolving', detail=name)
        planned = self._dry_run(job, ['--upgrade-strategy', 'only-if-needed', name])
        packages, target = [], None
        for entry in planned:
            meta = entry.get('metadata', {})
            row = {'name': meta.get('name', '?'), 'version': meta.get('version', ''), **licenses.from_metadata(meta),
                   'summary': (meta.get('summary') or '')[:200], 'requested': bool(entry.get('requested'))}
            packages.append(row)
            if canonical(row['name']) == canonical(name):
                target = row
        if target is None:                     # already installed (e.g. as a dependency): nothing to download
            info = dist_info(name)
            if info is None:
                raise RuntimeError(f'pip found nothing to install for “{name}”.')
            target = {k: info[k] for k in ('name', 'version', 'license', 'status', 'summary')} | {'requested': True,
                                                                                                    'installed': True}
            packages.insert(0, target)
        packages.sort(key=lambda r: (not r['requested'], r['name'].lower()))
        job.result = {'name': target['name'], 'version': target['version'], 'license': target['license'],
                      'status': target['status'], 'summary': target['summary'], 'packages': packages,
                      'needs_confirm': any(r['status'] != 'osi' for r in packages),
                      'already': bool(target.get('installed'))}
        job.set(1.0, phase='done', detail='')

    def start_user_install(self, inspection, accept=False):
        """Install what an inspection showed, at the version shown. A licence that is not OSI-approved
        (or not recognised) in the package or in anything installed with it needs accept=True."""
        job = self.jobs.get(str(inspection or ''))
        if not job or job.kind != 'inspect' or job.state != 'done':
            raise ValueError('Check the package first.')
        found = job.result
        if found['needs_confirm'] and not accept:
            raise ValueError('Confirm the licence terms first.')
        for other in self.jobs.values():
            if other.state == 'running' and other.kind in ('install', 'user-install', 'uninstall'):
                raise ValueError('Another installation is running: wait for it to finish.')
        return self._new_job('user-install', found['name'], self._install_user, found, bool(accept))

    def _install_user(self, job, found, accepted):
        with self.install_lock:
            try:
                self._prepare_pip(job)
                # What the packages pip will change were before, to put them back if the module cannot be used.
                before = {canonical(r['name']): installed_version(r['name']) for r in found['packages']
                          if PACKAGE_NAME.fullmatch(str(r.get('name', '')))}
                spec = f'{check_package_name(found["name"])}=={found["version"]}'
                job.set(0.15, phase='downloading')
                tracker = PipProgress(job, max(1, len(found['packages'])))
                if self._pip(job, ['install', '--progress-bar', 'raw', '--upgrade-strategy', 'only-if-needed', spec],
                             tracker.feed) != 0:
                    raise RuntimeError(_pip_error(job.log, 'Installation failed.'))
                clean_appledouble()
                importlib.invalidate_caches()
                info = dist_info(found['name'])
                if info is None:
                    raise RuntimeError('Not installed: ' + found['name'])
                key = canonical(info['name'])
                job.set(0.995, phase='checking', detail=info['name'])
                check = self._run_check(_deep_names(info['imports']), deep=True)
                if not check['ok']:
                    job.set(phase='rolling_back', detail='')
                    left = self._roll_back(job, before)
                    job.result = {'name': info['name'], 'version': info['version'], 'rolled_back': True,
                                  'error': check['error'], 'failed': check['failed'], 'parts': check['parts'],
                                  'rollback_error': left}
                    raise RuntimeError(f'{info["name"]} {info["version"]} cannot be used here ({check["error"]}): '
                                       + ('the installation could not be fully undone: ' + left if left
                                          else 'the installation was undone.'))
                self.checks['user:' + key] = {**check, 'version': info['version'], 'gen': self._check_gen, 'deep': True}
                self._write_checks()
                old = self.user.get(key, {})
                if any(m in sys.modules for m in info['imports']) and old.get('version') not in (None, info['version']):
                    self.restart_required.add('user:' + key)
                self.user[key] = {
                    'pip': info['name'], 'version': info['version'], 'license': info['license'], 'status': info['status'],
                    'summary': info['summary'][:200], 'imports': info['imports'],
                    'accepted': accepted or old.get('accepted', False),     # the user confirmed a licence that is not OSI
                    'packages': [{k: r[k] for k in ('name', 'version', 'license', 'status')} for r in found['packages']],
                    'cite': old.get('cite', ''), 'added': old.get('added') or time.strftime('%Y-%m-%d'),
                }
                self._write_user()
                job.result = {'name': info['name'], 'version': info['version'], 'imports': info['imports'],
                              'failed': check['failed'], 'parts': check['parts']}
                job.set(1.0, phase='done', detail='')
            finally:
                self.verify_async(force=True)

    def _roll_back(self, job, before):
        """Put back what an install changed: remove the packages it added, reinstall the versions it
        replaced (`before`: canonical name → version or None). Returns what could not be undone, or ''."""
        added = [n for n, v in before.items() if v is None and installed_version(n)]
        replaced = [f'{n}=={v}' for n, v in before.items() if v and installed_version(n) not in (None, v)]
        left = []
        if added and self._pip(job, ['uninstall', '--yes', *added]) != 0:
            left.append(_pip_error(job.log, 'pip could not remove ' + ', '.join(added)))
        if replaced and self._pip(job, ['install', '--no-deps', *replaced]) != 0:
            left.append(_pip_error(job.log, 'pip could not reinstall ' + ', '.join(replaced)))
        clean_appledouble()
        importlib.invalidate_caches()
        return '; '.join(left)

    def unusable(self, requires, imports=()):
        """[module, error] pairs that stop a plugin needing `requires` and importing `imports`: a user's
        module that cannot be used stops every plugin that needs it; one that works in part only the
        plugins importing a part that fails. Modules not installed or not checked yet stop nothing here."""
        out = []
        for name in dict.fromkeys(requires):
            key = canonical(name)
            rec = self.user.get(key)
            check = self.checks.get('user:' + key)
            if not rec or not check or check['version'] != installed_version(rec['pip']):
                continue
            if not check['ok']:
                out.append([rec['pip'], check['error']])
                continue
            out += [[part, error] for part, error in check.get('failed', [])
                    if any(i == part or i.startswith(part + '.') for i in imports)]
        return out

    def start_uninstall(self, name):
        """Remove one of the user's modules (pip uninstall; the packages installed with it stay).
        A module that is not installed any more is only forgotten."""
        key = canonical(check_package_name(name))
        if key not in self.user:
            raise ValueError(f'“{name}” is not one of your modules.')
        if key in self.registry_dists:
            raise ValueError(f'“{name}” is used by PyPlotter and cannot be removed here.')
        if installed_version(self.user[key]['pip']):
            users = dependents(self.user[key]['pip'])
            if users:
                raise ValueError(f'“{name}” is needed by {", ".join(users)}: it cannot be removed.')
        return self._new_job('uninstall', self.user[key]['pip'], self._uninstall, key)

    def _uninstall(self, job, key):
        with self.install_lock:
            pip_name = self.user[key]['pip']
            if installed_version(pip_name):
                job.set(0.2, phase='uninstalling', detail=pip_name)
                if self._pip(job, ['uninstall', '--yes', check_package_name(pip_name)]) != 0:
                    raise RuntimeError(_pip_error(job.log, 'pip could not remove the package.'))
                importlib.invalidate_caches()
                if any(m in sys.modules for m in self.user[key].get('imports', [])):
                    self.restart_required.add('user:' + key)
            del self.user[key]
            self.checks.pop('user:' + key, None)
            self._write_user()
            job.set(1.0, phase='done', detail='')

    def set_user_cite(self, name, text):
        key = canonical(check_package_name(name))
        if key not in self.user:
            raise ValueError(f'“{name}” is not one of your modules.')
        self.user[key]['cite'] = str(text or '').strip()[:2000]
        self._write_user()


def _pip_error(log, fallback):
    errors = [l for l in log if l.startswith('ERROR') or 'error:' in l.lower()]
    return (errors[-1] if errors else fallback)[:500]
