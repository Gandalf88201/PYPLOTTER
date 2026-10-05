"""Optional Python modules: registry, installed/latest versions and background pip installs.

Standard library only. The registry (registry.json) lists every package PyPlotter can use.
At each start the latest versions are fetched from PyPI in the background and cached in
~/.pyplotter/pypi-cache.json, so the list also works offline. Installs run
``python -m pip`` in this interpreter's environment and report a single progress value.
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

REGISTRY_FILE = Path(__file__).with_name('registry.json')
STATE_DIR = Path(os.environ.get('PYPLOTTER_HOME') or Path.home() / '.pyplotter')
PYPI_URL = 'https://pypi.org/pypi/{}/json'
PIP_MIN = (24, 1)          # first pip with --progress-bar raw
LOG_TAIL = 400


class MissingModules(Exception):
    """Raised when an action needs registry modules that are not installed."""

    def __init__(self, ids):
        self.ids = list(ids)
        super().__init__('Missing modules: ' + ', '.join(self.ids))


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

    def installed(self, mid):
        m = self.by_id[mid]
        return installed_version(m['pip'])

    def missing(self, ids):
        return [i for i in dict.fromkeys(ids) if i in self.by_id and not self.installed(i)]

    def require(self, ids):
        missing = self.missing(ids)
        if missing:
            raise MissingModules(missing)
        importlib.invalidate_caches()

    def core_ids(self):
        return [m['id'] for m in self.modules if m.get('core')]

    def status(self):
        rows = []
        for m in self.modules:
            inst = installed_version(m['pip'])
            latest = self._cache['versions'].get(m['pip'])
            rows.append({
                'id': m['id'], 'pip': m['pip'], 'category': m['category'], 'core': bool(m.get('core')),
                'description': m.get('description', {}), 'url': m.get('url', ''), 'min': m.get('min', ''),
                'license': m.get('license', ''), 'cite': m.get('cite', ''),
                'installed': inst, 'latest': latest,
                'outdated': bool(inst and m.get('min') and version_tuple(inst) < version_tuple(m['min'])),
                'update': bool(inst and latest and version_tuple(latest) > version_tuple(inst)),
                'restart': m['id'] in self.restart_required,
            })
        return {'modules': rows, 'refresh': dict(self.refresh_state),
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

    # ------------------------------------------------------------ installs
    def job(self, jid):
        return self.jobs.get(jid)

    def start_install(self, ids, upgrade=False):
        ids = [i for i in dict.fromkeys(ids) if i in self.by_id]
        if not ids:
            raise ValueError('No known module to install.')
        for job in self.jobs.values():   # same request already running: reuse it
            if job.state == 'running' and job.kind == 'install' and job.result.get('ids') == ids:
                return job
        job = Job('install', ', '.join(self.by_id[i]['pip'] for i in ids))
        job.result = {'ids': ids, 'upgrade': bool(upgrade)}
        self.jobs[job.id] = job
        threading.Thread(target=self._run_install, args=(job, ids, upgrade), name=f'pip-{job.id}', daemon=True).start()
        return job

    def _specs(self, ids, upgrade):
        specs = []
        for i in ids:
            m = self.by_id[i]
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

    def _run_install(self, job, ids, upgrade):
        with self.install_lock:
            try:
                self._install(job, ids, upgrade)
            except InterruptedError:
                job.state = 'cancelled'
            except Exception as exc:
                job.error = str(exc) or exc.__class__.__name__
                job.state = 'error'

    def externally_managed(self):
        """True for a system/Homebrew Python that forbids pip installs (PEP 668) and is not a venv."""
        if self.python != sys.executable or sys.prefix != sys.base_prefix:
            return False
        import sysconfig
        return Path(sysconfig.get_path('stdlib'), 'EXTERNALLY-MANAGED').exists()

    def _install(self, job, ids, upgrade):
        if self.externally_managed():
            raise RuntimeError(f'{self.python} is managed by the system or Homebrew and cannot receive packages. '
                               'Start PyPlotter with start_pyplotter.command / .bat or start_pyplotter.py, '
                               'which use the private .venv environment.')
        before = {i: self.installed(i) for i in ids}
        job.set(0.01, phase='preparing')
        pipv = self.pip_version()
        if not pipv:
            raise RuntimeError('pip is not available in this Python environment.')
        if pipv < PIP_MIN:
            if self._pip(job, ['install', '--upgrade', 'pip']) != 0:
                raise RuntimeError(_pip_error(job.log, 'Updating pip failed.'))
        job.set(0.05, phase='resolving')
        specs = self._specs(ids, upgrade)
        extra = ['--upgrade'] if upgrade else []
        fd, report = tempfile.mkstemp(suffix='.json', prefix='pyplotter-pip-')
        os.close(fd)
        try:
            if self._pip(job, ['install', '--dry-run', '--quiet', '--report', report] + extra + specs) != 0:
                raise RuntimeError(_pip_error(job.log, 'pip could not resolve the packages.'))
            try:
                planned = json.loads(Path(report).read_text(encoding='utf-8')).get('install', [])
            except Exception:
                planned = []
        finally:
            os.unlink(report)
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
        job.state = 'done'


def _pip_error(log, fallback):
    errors = [l for l in log if l.startswith('ERROR') or 'error:' in l.lower()]
    return (errors[-1] if errors else fallback)[:500]
