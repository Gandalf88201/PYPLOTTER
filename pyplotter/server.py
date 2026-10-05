"""Local HTTP service for the PyPlotter web interface.

Listens on loopback only. Every /api call must carry the per-session token embedded in the page
and a loopback Host header. Uploaded files live in a private session directory that is removed
when PyPlotter stops. The server starts with the standard library alone; NumPy, pandas and
Matplotlib are imported on first use, after the interface has installed them.
"""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
from urllib.parse import unquote, urlsplit

from . import __version__, catalog
from .modules import MissingModules, ModuleManager, clean_appledouble

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
MAX_JSON = 32 * 1024 * 1024
MAX_DATASETS = 12
PREVIEW_ROWS = 200
CHUNK = 1 << 20
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json'}


class ApiError(Exception):
    def __init__(self, message, status=400, code='error', **extra):
        super().__init__(message)
        self.status, self.code, self.extra = status, code, extra


def safe_name(name, fallback='data'):
    name = re.sub(r'[^\w.\-]+', '_', Path(str(name)).name, flags=re.UNICODE).strip('._')
    return name[:120] or fallback


def json_safe(v):
    """Make pandas/numpy cell values JSON-serialisable."""
    if v is None:
        return None
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (str, bool, int)):
        return v
    if hasattr(v, 'isoformat'):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if hasattr(v, 'item'):
        try:
            return json_safe(v.item())
        except Exception:
            pass
    s = str(v)
    return None if s in ('NaT', 'nan', '<NA>') else s


class App:
    def __init__(self, token, session_dir, modules, max_upload_bytes):
        self.token = token
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.modules = modules
        self.max_upload = max_upload_bytes
        self.datasets = OrderedDict()
        self.render_lock = threading.Lock()
        self.lock = threading.Lock()
        self.files = self._load_files()
        self.restart_hook = None

    # -------------------------------------------------------------- uploaded files
    def _files_index(self):
        return self.session_dir / 'files.json'

    def _load_files(self):
        try:
            return json.loads(self._files_index().read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_files(self):
        self._files_index().write_text(json.dumps(self.files), encoding='utf-8')

    def file(self, fid):
        info = self.files.get(str(fid))
        if not info or not Path(info['path']).is_file():
            raise ApiError('The file is no longer available; open it again.', 404, 'file_gone')
        return info

    def add_upload(self, name, stream, length):
        if length <= 0:
            raise ApiError('Empty upload.')
        if length > self.max_upload:
            raise ApiError(f'File larger than the limit ({self.max_upload / 1024 ** 3:.0f} GB).', 413)
        fmt, compression = catalog.detect_format(name)
        if fmt is None:
            raise ApiError('Unsupported file type: ' + (Path(name).suffix or name), 415, 'unsupported',
                           extensions=catalog.all_extensions())
        fid = secrets.token_hex(8)
        folder = self.session_dir / fid
        folder.mkdir()
        path = folder / safe_name(name)
        remaining = length
        with open(path, 'wb') as out:
            while remaining > 0:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
        if remaining:
            shutil.rmtree(folder, ignore_errors=True)
            raise ApiError('Upload interrupted.')
        info = {'id': fid, 'name': name, 'path': str(path), 'format': fmt, 'compression': compression, 'size': length}
        with self.lock:
            self.files[fid] = info
            self._save_files()
        return info

    def describe_file(self, info):
        need = self.modules.missing(catalog.FILE_FORMATS[info['format']]['requires'] + self.modules.core_ids())
        out = {'file_id': info['id'], 'name': info['name'], 'format': info['format'], 'size': info['size'],
               'missing': need, 'tables': []}
        if not need:
            from . import readers
            try:
                out['tables'] = readers.list_tables(info['path'], info['format'])
            except MissingModules:
                raise
            except ImportError as exc:
                raise ApiError(f'A module needed for this file is missing: {exc}', 409, 'import_error')
            except Exception as exc:
                raise ApiError(f'Cannot read {info["name"]}: {exc}', 422, 'read_error')
            if not out['tables']:
                raise ApiError('No table or dataset found in the file.', 422, 'read_error')
        return out

    # -------------------------------------------------------------- datasets
    def open_table(self, body):
        info = self.file(body.get('file_id'))
        self.modules.require(catalog.FILE_FORMATS[info['format']]['requires'] + self.modules.core_ids())
        from . import readers, smart
        table = body.get('table') or None
        options = body.get('options') or {}
        try:
            df, used = readers.read_table(info['path'], info['format'], table, options, info.get('compression'))
        except (MissingModules, ApiError):
            raise
        except ImportError as exc:
            raise ApiError(f'A module needed for this file is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            raise ApiError(f'Cannot read {info["name"]}: {exc}', 422, 'read_error')
        if df.empty or not len(df.columns):
            raise ApiError('The table is empty.', 422, 'read_error')
        name = info['name'] + (f' › {table}' if table and table != 'data' else '')
        return self._register(df, name, {'file_id': info['id'], 'table': table, 'options': options}, used)

    def sample(self, which):
        self.modules.require(self.modules.core_ids())
        from . import samples
        df = samples.make(which)
        return self._register(df, f'sample: {which}', {'sample': which}, {})

    def _register(self, df, name, source, used):
        from . import smart
        cols = smart.profile(df)
        mapping = smart.default_mapping(cols, len(df))
        did = secrets.token_hex(6)
        with self.lock:
            self.datasets[did] = {'df': df, 'name': name, 'source': source, 'columns': cols}
            while len(self.datasets) > MAX_DATASETS:
                self.datasets.popitem(last=False)
        head = df.head(PREVIEW_ROWS)
        return {'dataset_id': did, 'name': name, 'rows': int(len(df)), 'columns': cols, 'mapping': mapping,
                'options': {k: v for k, v in used.items() if k != 'names'}, 'source': source,
                'recommend': smart.recommend(cols, mapping, len(df)),
                'preview': [[json_safe(v) for v in row] for row in head.itertuples(index=False, name=None)]}

    def dataset(self, did):
        ds = self.datasets.get(str(did))
        if ds is None:
            raise ApiError('The data set is no longer loaded; open the file again.', 404, 'dataset_gone')
        return ds

    # -------------------------------------------------------------- figures
    def check_spec(self, spec, export=None):
        st = spec.get('style') or {}
        need = catalog.requirements_for(spec.get('kind'), st.get('base'), st.get('cmap'), export)
        self.modules.require(self.modules.core_ids() + need)

    def render(self, body, export=None):
        ds = self.dataset(body.get('dataset_id'))
        spec = body.get('spec') or {}
        self.check_spec(spec, export)
        from . import plotting, exporters
        fmt = export or 'png'
        try:
            with self.render_lock:
                if fmt == 'html':
                    return exporters.plotly_html(ds['df'], spec), catalog.EXPORT_FORMATS['html']['mime']
                if fmt == 'py':
                    data = exporters.script_bundle(ds['df'], spec, 'figure', self.modules.modules)
                    return data, catalog.EXPORT_FORMATS['py']['mime']
                dpi = body.get('dpi') if not export else (body.get('dpi') or None)
                return plotting.render(ds['df'], spec, fmt, dpi), catalog.EXPORT_FORMATS[fmt]['mime']
        except plotting.SpecError as exc:
            raise ApiError(str(exc), 422, 'spec')
        except (MissingModules, ApiError):
            raise
        except ImportError as exc:
            raise ApiError(f'A module is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            traceback.print_exc()
            raise ApiError(f'The figure could not be drawn: {exc}', 422, 'render')

    def recommend(self, body):
        ds = self.dataset(body.get('dataset_id'))
        from . import smart
        mapping = body.get('mapping') or {}
        return {'recommend': smart.recommend(ds['columns'], mapping, len(ds['df'])),
                'warnings': smart.warnings_for(mapping, body.get('kind'), len(ds['df']))}

    def meta(self):
        fonts, default_spec = [], None
        if not self.modules.missing(self.modules.core_ids()):
            from .plotting import DEFAULT_SPEC
            default_spec = DEFAULT_SPEC
            try:
                from matplotlib import font_manager
                fonts = sorted({f.name for f in font_manager.fontManager.ttflist})
            except Exception:
                fonts = []
        return {'version': __version__, 'kinds': catalog.KINDS, 'twin_kinds': sorted(catalog.TWIN_KINDS),
                'styles': catalog.STYLES, 'palettes': catalog.PALETTES, 'colormaps': catalog.COLORMAPS,
                'export_formats': catalog.EXPORT_FORMATS, 'size_presets': catalog.SIZE_PRESETS,
                'file_formats': catalog.FILE_FORMATS, 'extensions': catalog.all_extensions(), 'fonts': fonts,
                'default_spec': default_spec}


def make_handler(app, port):
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}

    class Handler(BaseHTTPRequestHandler):
        server_version = f'PyPlotter/{__version__}'
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):   # quiet; errors are printed explicitly
            pass

        # ------------------------------------------------ responses
        def _send(self, status, body, ctype, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status=200):
            self._send(status, json.dumps(data, allow_nan=False, default=json_safe).encode('utf-8'),
                       'application/json; charset=utf-8')

        def _error(self, exc):
            if isinstance(exc, MissingModules):
                return self._json({'error': str(exc), 'code': 'missing_modules', 'modules': exc.ids}, 409)
            if isinstance(exc, ApiError):
                return self._json({'error': str(exc), 'code': exc.code, **exc.extra}, exc.status)
            traceback.print_exc()
            return self._json({'error': f'Internal error: {exc}', 'code': 'internal'}, 500)

        def _body(self):
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_JSON:
                raise ApiError('Request too large.', 413)
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw or b'{}')
            except json.JSONDecodeError:
                raise ApiError('Invalid JSON.')
            if not isinstance(data, dict):
                raise ApiError('Invalid request.')
            return data

        def _guard(self):
            if self.headers.get('Host', '') not in allowed_hosts:
                raise ApiError('Forbidden host.', 403, 'forbidden')
            if self.path.startswith('/api/') and not secrets.compare_digest(self.headers.get('X-Token', ''), app.token):
                raise ApiError('Invalid session token; reload the page.', 403, 'token')

        # ------------------------------------------------ GET
        def do_GET(self):
            try:
                self._guard()
                path = urlsplit(self.path).path
                if path in ('/', '/index.html'):
                    html = (WEB / 'index.html').read_text(encoding='utf-8').replace('{{TOKEN}}', app.token)
                    return self._send(200, html.encode('utf-8'), MIME['.html'],
                                      {'Content-Security-Policy': "default-src 'self'; img-src 'self' blob: data:; "
                                       "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                                       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                if path.startswith('/static/'):
                    name = unquote(path[len('/static/'):])
                    target = (WEB / name).resolve()
                    if WEB.resolve() not in target.parents or not target.is_file() or target.suffix not in MIME:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._send(200, target.read_bytes(), MIME[target.suffix])
                if path == '/api/status':
                    return self._json(app.modules.status())
                if path == '/api/meta':
                    return self._json(app.meta())
                if path.startswith('/api/jobs/'):
                    job = app.modules.job(path.rsplit('/', 1)[-1])
                    if not job:
                        raise ApiError('Unknown job.', 404)
                    return self._json(job.to_dict())
                raise ApiError('Not found', 404, 'not_found')
            except Exception as exc:
                self._error(exc)

        # ------------------------------------------------ POST
        def do_POST(self):
            try:
                self._guard()
                path = urlsplit(self.path).path
                if path == '/api/upload':
                    name = unquote(self.headers.get('X-Filename', '')) or 'data.csv'
                    info = app.add_upload(name, self.rfile, int(self.headers.get('Content-Length') or 0))
                    return self._json(app.describe_file(info))
                body = self._body()
                if path == '/api/file':
                    return self._json(app.describe_file(app.file(body.get('file_id'))))
                if path == '/api/open':
                    return self._json(app.open_table(body))
                if path == '/api/sample':
                    return self._json(app.sample(str(body.get('name') or 'spectra')))
                if path == '/api/recommend':
                    return self._json(app.recommend(body))
                if path == '/api/render':
                    data, mime = app.render(body)
                    return self._send(200, data, mime)
                if path == '/api/export':
                    fmt = str(body.get('format') or 'png').lower()
                    if fmt not in catalog.EXPORT_FORMATS:
                        raise ApiError('Unknown export format.')
                    data, mime = app.render(body, export=fmt)
                    ext = 'zip' if fmt == 'py' else fmt
                    fname = safe_name(body.get('filename') or 'figure', 'figure') + '.' + ext
                    return self._send(200, data, mime, {'Content-Disposition': f'attachment; filename="{fname}"'})
                if path == '/api/modules/refresh':
                    app.modules.refresh_async()
                    return self._json(app.modules.status())
                if path == '/api/modules/install':
                    ids = body.get('ids') or []
                    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                        raise ApiError('ids must be a list of module ids.')
                    unknown = [i for i in ids if i not in app.modules.by_id]
                    if unknown:
                        raise ApiError('Unknown module: ' + ', '.join(unknown))
                    job = app.modules.start_install(ids, upgrade=bool(body.get('upgrade')))
                    return self._json(job.to_dict())
                if path.startswith('/api/jobs/') and path.endswith('/cancel'):
                    job = app.modules.job(path.split('/')[3])
                    if job:
                        job.cancel()
                    return self._json(job.to_dict() if job else {})
                if path == '/api/restart':
                    if not app.restart_hook:
                        raise ApiError('Restart is not available.')
                    self._json({'ok': True})
                    threading.Timer(0.4, app.restart_hook).start()
                    return
                raise ApiError('Not found', 404, 'not_found')
            except Exception as exc:
                self._error(exc)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(port, token, session_dir, open_browser=True, max_upload_gb=20, online=True, quiet=False):
    clean_appledouble()          # exFAT drives on macOS: see modules.clean_appledouble
    modules = ModuleManager(online=online)
    app = App(token, session_dir, modules, int(max_upload_gb * 1024 ** 3))
    httpd = Server(('127.0.0.1', port), make_handler(app, port))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(app, port)
    url = f'http://127.0.0.1:{port}/'
    modules.refresh_async()      # latest versions from PyPI, at every start
    if not quiet:
        status = modules.status()
        print(f'PyPlotter {__version__} — {url}')
        print(f'Python {status["python"]} ({sys.executable})')
        if not status['core_ready']:
            print('First start: the browser page will install NumPy, pandas and Matplotlib.')
        print('Keep this window open; press Ctrl+C to stop.')
    if open_browser:
        threading.Timer(0.6, lambda: _open(url)).start()
    return httpd, app, url


def _open(url):
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass
