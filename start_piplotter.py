#!/usr/bin/env python3
"""Start π-plotter: a local Python service plus the interface in your browser.

Standard library only. Whatever Python starts this script, π-plotter runs inside its own
environment ./.venv (created here on first use), so packages never go into a system or
Homebrew Python. NumPy, pandas, Matplotlib and the optional modules are installed from the
browser page. Set PIPLOTTER_NO_VENV=1 to use the current interpreter instead (e.g. a conda env).
"""
import argparse
import atexit
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

for _stream in (sys.stdout, sys.stderr):      # the name has a π: never fail on a console with a narrow encoding
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass

if sys.version_info < (3, 10):
    sys.exit('π-plotter needs Python 3.10 or newer.')

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'


def ensure_private_env():
    """Re-run this script with .venv's Python unless we already are in a virtual environment."""
    if sys.prefix != sys.base_prefix or os.environ.get('PIPLOTTER_NO_VENV') == '1':
        return
    py = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not py.exists():
        print(f'Creating the π-plotter environment in {VENV} with Python {sys.version.split()[0]} …', flush=True)
        import venv
        error = None
        for symlinks in ((True, False) if os.name != 'nt' else (False,)):   # copies where links are unsupported
            try:
                venv.EnvBuilder(with_pip=True, symlinks=symlinks, clear=True).create(VENV)
                error = None
                break
            except Exception as exc:
                error = exc
        if error is not None or not py.exists():
            shutil.rmtree(VENV, ignore_errors=True)
            sys.exit(f'π-plotter: could not create {VENV} ({error}).\n'
                     'On Debian/Ubuntu install the python3-venv package, then start π-plotter again.')
    args = [str(py), str(Path(__file__).resolve())] + sys.argv[1:]
    if os.name == 'nt':
        sys.exit(subprocess.call(args))
    os.execv(str(py), args)


def persistent_token():
    """Random token kept in ~/.piplotter/token (owner-only), so open tabs keep working after a restart."""
    home = home_dir()
    path = home / 'token'
    try:
        token = path.read_text(encoding='ascii').strip()
        if len(token) >= 32:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        home.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='ascii') as fh:
            fh.write(token)
    except OSError:
        pass                      # read-only home: a per-run token still works
    return token


def take_over(port, token):
    """If a π-plotter already runs on the port, ask it to stop so only the newest one serves pages."""
    import json
    import urllib.error
    import urllib.request
    base = f'http://127.0.0.1:{port}'
    headers = {'X-Token': token, 'Content-Type': 'application/json'}
    try:
        with urllib.request.urlopen(urllib.request.Request(base + '/api/status', headers=headers), timeout=2) as r:
            json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            print(f'Note: another program (perhaps an older π-plotter) uses port {port}; '
                  'close its window if you do not need it. Starting on the next free port.', flush=True)
        return
    except Exception:
        return                                   # nothing listening
    try:
        req = urllib.request.Request(base + '/api/shutdown', data=b'{}', headers=headers, method='POST')
        urllib.request.urlopen(req, timeout=3).read()
        print(f'Closed the π-plotter that was already running on port {port}.', flush=True)
    except Exception:
        return
    import socket
    for _ in range(40):                          # wait until the port is free
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) != 0:
                return
        time.sleep(0.15)


ensure_private_env()
sys.path.insert(0, str(ROOT))
from piplotter import AUTHOR, NAME, home_dir  # noqa: E402
from piplotter.server import serve  # noqa: E402


def main():
    sys.stdout.reconfigure(line_buffering=True)   # messages appear at once in the launcher window
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=int(os.environ.get('PIPLOTTER_PORT', 8770)))
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--max-upload-gb', type=float, default=20)
    ap.add_argument('--offline', action='store_true', help='do not check PyPI for new versions')
    args = ap.parse_args()

    restarted = os.environ.get('PIPLOTTER_RESTARTED') == '1'
    token = os.environ.get('PIPLOTTER_TOKEN') or persistent_token()
    session = os.environ.get('PIPLOTTER_SESSION') or tempfile.mkdtemp(prefix='piplotter-')

    if not restarted:
        take_over(args.port, token)
    httpd = None
    ports = [args.port] * 10 if restarted else range(args.port, args.port + 20)
    for port in ports:
        try:
            httpd, app, url = serve(port, token, session, open_browser=not (args.no_browser or restarted),
                                    max_upload_gb=args.max_upload_gb, online=not args.offline)
            break
        except OSError:
            if restarted:      # the old process may hold the port for a moment
                time.sleep(0.5)
    if httpd is None:
        sys.exit(f'No free port between {args.port} and {args.port + 19}; use --port.')

    keep = {'session': False}

    def cleanup():
        if not keep['session']:
            shutil.rmtree(session, ignore_errors=True)
    atexit.register(cleanup)

    def restart():
        """Re-execute with the same port, token and uploaded files (after module updates)."""
        keep['session'] = True
        os.environ.update(PIPLOTTER_TOKEN=token, PIPLOTTER_SESSION=session, PIPLOTTER_RESTARTED='1',
                          PIPLOTTER_PORT=str(httpd.server_address[1]))
        httpd.socket.close()
        argv = [sys.executable, str(Path(__file__).resolve()), '--max-upload-gb', str(args.max_upload_gb)]
        argv += ['--offline'] if args.offline else []
        if os.name == 'nt':
            subprocess.Popen(argv)
            os._exit(0)
        os.execv(sys.executable, argv)
    app.restart_hook = restart

    def shutdown():
        print('\nA newer π-plotter window took over; this one stops here.', flush=True)
        httpd.shutdown()
    app.shutdown_hook = shutdown

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nπ-plotter stopped.')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
