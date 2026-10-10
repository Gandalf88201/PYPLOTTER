"""Local HTTP service for the π-plotter web interface.

Listens on loopback only. Every /api call must carry the per-session token embedded in the page
and a loopback Host header. Uploaded files live in a private session directory that is removed
when π-plotter stops. The server starts with the standard library alone; NumPy, pandas and
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
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import AUTHOR, NAME, __version__, catalog, manual
from .modules import MissingModules, MissingUserModules, ModuleManager, canonical, clean_appledouble

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
MAX_JSON = 32 * 1024 * 1024
MAX_DATASETS = 200                # kept in memory, least recently used dropped first …
MAX_DATASET_BYTES = 2 * 1024 ** 3  # … also when together they take more than this
PREVIEW_ROWS = 200
PREVIEW_COLS = 100      # the table shows the first columns: a wide table would be millions of cells
CHUNK = 1 << 20
MIME = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.json': 'application/json'}


class ApiError(Exception):
    def __init__(self, message, status=400, code='error', **extra):
        super().__init__(message)
        self.status, self.code, self.extra = status, code, extra


def safe_name(name, fallback='data'):
    name = re.sub(r'[^\w.\-]+', '_', Path(str(name)).name, flags=re.UNICODE).strip('._')
    return name[:120] or fallback


def content_disposition(fname):
    """Header value for a download name; HTTP headers are Latin-1, so non-ASCII names go in filename*."""
    ascii_name = fname.encode('ascii', 'replace').decode('ascii').replace('?', '_').replace('"', '_')
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(fname, safe="")}'


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


def build_id():
    """Fingerprint of the program files: pages from another version ask to reload."""
    import hashlib
    h = hashlib.sha1(__version__.encode())
    for folder, pattern in ((WEB, '*'), (Path(__file__).parent, '*.py')):
        for f in sorted(folder.glob(pattern)):
            if f.is_file() and not f.name.startswith('.'):
                h.update(f.name.encode())
                h.update(f.read_bytes())
    return h.hexdigest()[:12]


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
        self.shutdown_hook = None
        self.started = time.time()
        self.build = build_id()
        self._plugins = None
        self.views3d = OrderedDict()      # id -> view3d of a recent 3D render (the rotatable preview)
        self._overlay_alias = {}
        self._extra_refs = []

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

    def _register(self, df, name, source, used, references=()):
        from . import smart
        cols = smart.profile(df)
        mapping = smart.default_mapping(cols, len(df))
        did = secrets.token_hex(6)
        try:
            size = int(df.memory_usage(index=True, deep=False).sum())
        except Exception:
            size = 0
        with self.lock:
            self.datasets[did] = {'df': df, 'name': name, 'source': source, 'columns': cols,
                                  'references': list(references), 'bytes': size}
            # Least recently used first (dataset() marks use): the file being plotted is never the one
            # dropped, however many analyses register their results and layers.
            total = sum(d.get('bytes', 0) for d in self.datasets.values())
            while len(self.datasets) > 1 and (len(self.datasets) > MAX_DATASETS or total > MAX_DATASET_BYTES):
                _, old = self.datasets.popitem(last=False)
                total -= old.get('bytes', 0)
        head = df.iloc[:PREVIEW_ROWS, :PREVIEW_COLS]
        return {'dataset_id': did, 'name': name, 'rows': int(len(df)), 'columns': cols, 'mapping': mapping,
                'options': {k: v for k, v in used.items() if k != 'names'}, 'source': source,
                'recommend': smart.recommend(cols, mapping, len(df)),
                'preview': [[json_safe(v) for v in row] for row in head.itertuples(index=False, name=None)],
                'preview_cols': int(head.shape[1])}

    def dataset(self, did):
        with self.lock:
            ds = self.datasets.get(str(did))
            if ds is not None:
                self.datasets.move_to_end(str(did))          # recently used: dropped last
        if ds is None:
            raise ApiError('The data set is no longer loaded; open the file again.', 404, 'dataset_gone')
        return ds

    def reopen(self, source, depth=0):
        """Rebuild a data set from its source: file, sample, or analysis of another data set."""
        if not isinstance(source, dict) or depth > 10:
            raise ApiError('Unknown data source.', 400)
        if source.get('sample'):
            return self.sample(str(source['sample']))
        if source.get('analysis'):
            parent = self.reopen(source.get('parent'), depth + 1)
            out = self.run_analysis({'dataset_id': parent['dataset_id'], 'id': source['analysis'],
                                     'params': source.get('params') or {}, 'spec': source.get('spec') or {},
                                     'lang': source.get('lang', 'en')})
            if source.get('overlay') is not None:
                return out['overlays'][int(source['overlay'])]['dataset']
            return out['dataset']
        return self.open_table(source)

    # -------------------------------------------------------------- analyses & plugins
    def plugin_manager(self):
        self.modules.require(self.modules.core_ids())
        if self._plugins is None:
            from .plugins import PluginManager
            self._plugins = PluginManager()
        return self._plugins

    def analyses(self):
        return self.plugin_manager().describe(missing=self.modules.missing, blocked=self.modules.unusable)

    def run_analysis(self, body):
        from .plugins import PluginError
        ds = self.dataset(body.get('dataset_id'))
        pm = self.plugin_manager()
        try:
            plugin = pm.get(str(body.get('id')))
        except PluginError as exc:
            raise ApiError(str(exc), 404, 'plugin')
        self.modules.require(self.modules.core_ids() + plugin['requires'])
        blocked = self.modules.unusable(plugin['requires'], plugin['imports'])
        if blocked:
            raise ApiError('This analysis needs modules that do not import: '
                           + '; '.join(f'{name} ({error})' for name, error in blocked), 409, 'blocked_module')
        lang = body.get('lang') if body.get('lang') in ('en', 'it') else 'en'
        spec = body.get('spec') or {}
        try:
            plugin, values, res = pm.run(plugin['id'], ds['df'], body.get('params') or {}, lang, spec)
        except (PluginError, ValueError, KeyError, TypeError, ZeroDivisionError, RuntimeError, ArithmeticError) as exc:
            raise ApiError(_plugin_message(exc, plugin), 422, 'analysis')
        except ImportError as exc:
            raise ApiError(f'A module is missing: {exc}', 409, 'import_error')
        except Exception as exc:
            traceback.print_exc()
            raise ApiError(_plugin_message(exc, plugin), 422, 'analysis')
        out = {'plugin': {'id': plugin['id'], 'name': plugin['name'], 'source': plugin['source'], 'file': plugin['file']},
               'params': values, 'summary': res.summary, 'tables': res.tables, 'texts': res.texts,
               'references': list(dict.fromkeys(res.refs + self.modules.user_citations(plugin['requires']))),
               'dataset': None, 'plot': res.plot}
        from .readers import tidy
        source = {'analysis': plugin['id'], 'params': values, 'parent': ds['source'], 'spec': spec, 'lang': lang}
        refs = ds.get('references', []) + out['references']
        title = res.name or plugin['name'][lang]
        out['overlays'] = []
        for k, ov in enumerate(res.overlays):
            reg = self._register(ov['frame'], f'{ds["name"]} › {title} · {ov["label"]}', {**source, 'overlay': k}, {},
                                 references=refs)
            reg.pop('preview', None)
            out['overlays'].append({
                'dataset': reg, 'source': {**source, 'overlay': k}, 'dataset_id': reg['dataset_id'],
                'x': ov['x'], 'y': ov['y'], 'lo': ov['lo'], 'hi': ov['hi'], 'label': ov['label'],
                'band_label': ov['band_label'], 'style': ov['style'], 'band': bool(ov['lo'] and ov['hi']),
                'on_figure': ov.get('on_figure', True), 'text': ov.get('text'),
                'id': secrets.token_hex(5), 'references': out['references']})
        out['analysed_dataset'] = str(body.get('dataset_id'))
        if res.frame is not None and len(res.frame.columns):
            name = f'{ds["name"]} › {title}'
            out['dataset'] = self._register(tidy(res.frame.copy()), name, source, {}, references=refs)
            plot = dict(res.plot or {})
            if plot.get('overlays'):         # {'ref': k} → the k-th overlay of this result
                resolved = []
                for o in plot['overlays']:
                    if isinstance(o, dict) and 'ref' in o and int(o['ref']) < len(out['overlays']):
                        base = {k: v for k, v in out['overlays'][int(o['ref'])].items() if k != 'dataset'}
                        resolved.append({**base, **{k: v for k, v in o.items() if k != 'ref'}})
                plot['overlays'] = resolved
            out['plot'] = plot
        return out

    def _frames(self, items):
        """{item id: DataFrame} for overlay / extra-file entries of a spec ({'id', 'dataset_id', 'source'});
        data sets that are gone (e.g. after a restart) are rebuilt from their source when possible."""
        data = {}
        for o in items or []:
            if not isinstance(o, dict) or not o.get('dataset_id'):
                continue
            did = self._overlay_alias.get(o['dataset_id'], o['dataset_id'])
            with self.lock:
                ds = self.datasets.get(did)
                if ds is not None:
                    self.datasets.move_to_end(did)
            if ds is None and o.get('source'):
                try:
                    ds_new = self.reopen(o['source'])
                    self._overlay_alias[o['dataset_id']] = ds_new['dataset_id']
                    ds = self.datasets.get(ds_new['dataset_id'])
                except Exception:
                    ds = None
            if ds is not None:
                data[o.get('id')] = ds['df']
                for r in ds.get('references', []):
                    if r not in self._extra_refs:
                        self._extra_refs.append(r)
        return data

    def overlay_data(self, spec):
        return self._frames(spec.get('overlays'))

    def extra_data(self, spec):
        return self._frames(spec.get('extra'))

    def plugin_action(self, action, body):
        from .plugins import PluginError
        pm = self.plugin_manager()
        try:
            if action == 'read':
                return pm.read(body.get('file'), body.get('id'))
            if action == 'save':
                code = str(body.get('code') or '')
                if len(code) > 2_000_000:
                    raise PluginError('The plugin file is too large.')
                return pm.save(body.get('file'), code)
            if action == 'new':
                return pm.create(body.get('name'))
            if action == 'customize':
                return pm.customize(str(body.get('id')))
            if action == 'integration':          # the first analysis using one of the user's modules
                rec = self.modules.user.get(canonical(str(body.get('name') or '')))
                if not rec:
                    raise PluginError('Not one of your modules.')
                return pm.create_integration(rec['pip'], (rec.get('imports') or [''])[0])
            if action == 'disable':
                return pm.disable(body.get('file'))
            if action == 'folder':
                return pm.open_folder()
            if action == 'reload':
                pm.reload()
                return self.analyses()
        except (PluginError, OSError) as exc:
            raise ApiError(str(exc), 422, 'plugin')
        raise ApiError('Unknown plugin action.', 404)

    # -------------------------------------------------------------- figures
    def check_spec(self, spec, export=None):
        st = spec.get('style') or {}
        need = catalog.requirements_for(spec.get('kind'), st.get('base'), st.get('cmap'), export)
        self.modules.require(self.modules.core_ids() + need)

    def render(self, body, export=None, info=None):
        ds = self.dataset(body.get('dataset_id'))
        spec = body.get('spec') or {}
        self.check_spec(spec, export)
        from . import plotting, exporters
        fmt = export or 'png'
        try:
            with self.render_lock:
                self._extra_refs = []
                overlays = self.overlay_data(spec)
                extras = self.extra_data(spec)
                if fmt == 'html':
                    return exporters.plotly_html(ds['df'], spec, overlays, extras), catalog.EXPORT_FORMATS['html']['mime']
                if fmt == 'py':
                    data = exporters.script_bundle(ds['df'], spec, 'figure', self.modules.modules,
                                                   extra_refs=ds.get('references', []) + self._extra_refs,
                                                   source=ds['source'], overlay_data=overlays, extra_data=extras)
                    return data, catalog.EXPORT_FORMATS['py']['mime']
                dpi = body.get('dpi') if not export else (body.get('dpi') or None)
                return (plotting.render(ds['df'], spec, fmt, dpi, overlays, extras, info=info),
                        catalog.EXPORT_FORMATS[fmt]['mime'])
        except plotting.SpecError as exc:
            raise ApiError(str(exc), 422, 'spec', key=exc.key, values=exc.values)
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
        fonts, default_spec, previews = [], None, {}
        if not self.modules.missing(self.modules.core_ids()):
            from .plotting import DEFAULT_SPEC, palette_previews
            default_spec = DEFAULT_SPEC
            previews = palette_previews()
            try:
                from matplotlib import font_manager
                fonts = sorted({f.name for f in font_manager.fontManager.ttflist})
            except Exception:
                fonts = []
        return {'version': __version__, 'kinds': catalog.KINDS, 'twin_kinds': sorted(catalog.TWIN_KINDS),
                'styles': catalog.STYLES, 'palettes': catalog.PALETTES, 'colormaps': catalog.COLORMAPS,
                'export_formats': catalog.EXPORT_FORMATS, 'size_presets': catalog.SIZE_PRESETS,
                'file_formats': catalog.FILE_FORMATS, 'extensions': catalog.all_extensions(), 'fonts': fonts,
                'default_spec': default_spec, 'palette_previews': previews}


def make_handler(app, port):
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}

    class Handler(BaseHTTPRequestHandler):
        server_version = f'piplotter/{__version__}'
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

        def _log_error(self, status, message):
            if status in (404,) and 'gone' not in message:
                return
            print(f'[π-plotter {time.strftime("%H:%M:%S")}] {status} {self.command} {urlsplit(self.path).path} — {message}',
                  file=sys.stderr, flush=True)

        def _error(self, exc):
            if isinstance(exc, ConnectionError):
                return      # the page cancelled the request (e.g. a newer render replaced it): nothing to answer
            if isinstance(exc, MissingModules):
                return self._json({'error': str(exc), 'code': 'missing_modules', 'modules': exc.ids}, 409)
            if isinstance(exc, MissingUserModules):
                return self._json({'error': str(exc), 'code': 'missing_user_modules', 'modules': exc.names}, 409)
            if isinstance(exc, ApiError):
                self._log_error(exc.status, f'{exc.code}: {exc}')
                return self._json({'error': str(exc), 'code': exc.code, **exc.extra}, exc.status)
            self._log_error(500, f'{exc.__class__.__name__}: {exc}')
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
                    html = (WEB / 'index.html').read_text(encoding='utf-8').replace('{{TOKEN}}', app.token) \
                        .replace('{{BUILD}}', app.build)
                    return self._send(200, html.encode('utf-8'), MIME['.html'],
                                      {'Content-Security-Policy': "default-src 'self'; img-src 'self' blob: data:; "
                                       "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
                                       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                if path in ('/manual', '/manual/'):
                    query = parse_qs(urlsplit(self.path).query)
                    page = manual.render_page(lang=(query.get('lang') or [''])[0], explicit='lang' in query)
                    return self._send(200, page.encode('utf-8'), MIME['.html'],
                                      {'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                       "script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
                if path.startswith('/manual/img/'):
                    image = manual.image_path(unquote(path[len('/manual/img/'):]))
                    if image is None:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._send(200, image.read_bytes(), MIME[image.suffix])
                if path.startswith('/static/'):
                    name = unquote(path[len('/static/'):])
                    target = (WEB / name).resolve()
                    if WEB.resolve() not in target.parents or not target.is_file() or target.suffix not in MIME:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._send(200, target.read_bytes(), MIME[target.suffix])
                if path == '/api/status':
                    return self._json({**app.modules.status(), 'build': app.build, 'started': app.started})
                if path == '/api/meta':
                    return self._json(app.meta())
                if path.startswith('/api/view3d/'):
                    view = app.views3d.get(path.rsplit('/', 1)[-1])
                    if view is None:
                        raise ApiError('Not found', 404, 'not_found')
                    return self._json(view)
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
                if path == '/api/analyses':
                    return self._json(app.analyses())
                if path == '/api/analyses/run':
                    return self._json(app.run_analysis(body))
                if path == '/api/reopen':
                    return self._json(app.reopen(body.get('source')))
                if path.startswith('/api/plugins/'):
                    return self._json(app.plugin_action(path.rsplit('/', 1)[-1], body))
                if path == '/api/recommend':
                    return self._json(app.recommend(body))
                if path == '/api/render':
                    info = {}
                    data, mime = app.render(body, info=info)
                    # The colour each series really got, for the Series panel (JSON, URL-encoded).
                    series = quote(json.dumps(info.get('series', []), ensure_ascii=False, default=json_safe))
                    axes = quote(json.dumps(info.get('axes', []), default=json_safe))
                    # The texts that can be dragged and rewritten on the preview, and the polar / 3D axes the wheel zooms.
                    movable = quote(json.dumps({'items': info.get('movables', []), 'face': info.get('face'), 'zoom': info.get('zoom', [])},
                                               default=json_safe))
                    headers = {'X-Series': series, 'X-Axes': axes, 'X-Movables': movable}
                    if info.get('view3d'):          # fetched by the page only when the user starts rotating
                        vid = secrets.token_hex(8)
                        app.views3d[vid] = info['view3d']
                        while len(app.views3d) > 8:
                            app.views3d.popitem(last=False)
                        headers['X-View3D'] = vid
                    return self._send(200, data, mime, headers)
                if path == '/api/export':
                    fmt = str(body.get('format') or 'png').lower()
                    if fmt not in catalog.EXPORT_FORMATS:
                        raise ApiError('Unknown export format.')
                    data, mime = app.render(body, export=fmt)
                    ext = 'zip' if fmt == 'py' else fmt
                    fname = safe_name(body.get('filename') or 'figure', 'figure') + '.' + ext
                    return self._send(200, data, mime, {'Content-Disposition': content_disposition(fname)})
                if path == '/api/modules/refresh':
                    app.modules.refresh_async()
                    return self._json(app.modules.status())
                if path == '/api/modules/verify':
                    app.modules.verify_async(force=True)
                    return self._json(app.modules.status())
                if path == '/api/modules/install':
                    ids = body.get('ids') or []
                    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                        raise ApiError('ids must be a list of module ids.')
                    unknown = [i for i in ids if i not in app.modules.by_id]
                    if unknown:
                        raise ApiError('Unknown module: ' + ', '.join(unknown))
                    job = app.modules.start_install(ids, upgrade=bool(body.get('upgrade')),
                                                    reinstall=bool(body.get('reinstall')))
                    return self._json(job.to_dict())
                if path.startswith('/api/modules/user/'):
                    return self._json(user_module_action(app.modules, path.rsplit('/', 1)[-1], body))
                if path.startswith('/api/jobs/') and path.endswith('/cancel'):
                    job = app.modules.job(path.split('/')[3])
                    if job:
                        job.cancel()
                    return self._json(job.to_dict() if job else {})
                if path == '/api/shutdown':      # a newer π-plotter is starting: give it the port
                    self._json({'ok': True})
                    if app.shutdown_hook:
                        threading.Timer(0.2, app.shutdown_hook).start()
                    return
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

    def handle_error(self, request, client_address):
        # A browser that closes a connection early (cancelled render, closed tab) is not an error.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def serve(port, token, session_dir, open_browser=True, max_upload_gb=20, online=True, quiet=False):
    clean_appledouble()          # exFAT drives on macOS: see modules.clean_appledouble
    modules = ModuleManager(online=online)
    app = App(token, session_dir, modules, int(max_upload_gb * 1024 ** 3))
    httpd = Server(('127.0.0.1', port), make_handler(app, port))
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(app, port)
    url = f'http://127.0.0.1:{port}/'
    modules.refresh_async()      # latest versions from PyPI, at every start
    modules.verify_async()       # installed modules really import (separate Python, in the background)
    if not quiet:
        status = modules.status()
        print(f'{NAME} {__version__} — {url}')
        print(AUTHOR)
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


def user_module_action(modules, action, body):
    """Modules the user adds from PyPI: inspect (licences first), install, uninstall, cite."""
    try:
        if action == 'inspect':
            return modules.start_inspect(body.get('name')).to_dict()
        if action == 'install':
            return modules.start_user_install(body.get('inspection'), accept=body.get('accept') is True).to_dict()
        if action == 'uninstall':
            return modules.start_uninstall(body.get('name')).to_dict()
        if action == 'cite':
            modules.set_user_cite(body.get('name'), body.get('cite'))
            return modules.status()
    except ValueError as exc:
        raise ApiError(str(exc), 400, 'user_module')
    raise ApiError('Not found', 404, 'not_found')


def _plugin_message(exc, plugin):
    """Error text for a failed analysis; for user plugins include the failing line of their file."""
    msg = f'{exc.__class__.__name__}: {exc}' if not str(exc).startswith(exc.__class__.__name__) else str(exc)
    if isinstance(exc, (ValueError,)) and exc.__class__.__name__ in ('ValueError', 'PluginError'):
        msg = str(exc)
    tb = traceback.extract_tb(exc.__traceback__)
    lines = [f for f in tb if f.filename == plugin.get('path')]
    if lines and plugin.get('source') == 'user':
        msg += f' ({plugin["file"]}, line {lines[-1].lineno})'
    return msg
