#!/usr/bin/env python3
"""Start PyPlotter: a local Python service plus the interface in your browser.

Standard library only. Whatever Python starts this script, PyPlotter runs inside its own
environment ./.venv (created here on first use), so packages never go into a system or
Homebrew Python. NumPy, pandas, Matplotlib and the optional modules are installed from the
browser page. Set PYPLOTTER_NO_VENV=1 to use the current interpreter instead (e.g. a conda env).
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

if sys.version_info < (3, 10):
    sys.exit('PyPlotter needs Python 3.10 or newer.')

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'


def ensure_private_env():
    """Re-run this script with .venv's Python unless we already are in a virtual environment."""
    if sys.prefix != sys.base_prefix or os.environ.get('PYPLOTTER_NO_VENV') == '1':
        return
    py = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not py.exists():
        print(f'Creating the PyPlotter environment in {VENV} with Python {sys.version.split()[0]} …', flush=True)
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
            sys.exit(f'PyPlotter: could not create {VENV} ({error}).\n'
                     'On Debian/Ubuntu install the python3-venv package, then start PyPlotter again.')
    args = [str(py), str(Path(__file__).resolve())] + sys.argv[1:]
    if os.name == 'nt':
        sys.exit(subprocess.call(args))
    os.execv(str(py), args)


ensure_private_env()
sys.path.insert(0, str(ROOT))
from pyplotter.server import serve  # noqa: E402


def main():
    sys.stdout.reconfigure(line_buffering=True)   # messages appear at once in the launcher window
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=int(os.environ.get('PYPLOTTER_PORT', 8770)))
    ap.add_argument('--no-browser', action='store_true', help='do not open the browser')
    ap.add_argument('--max-upload-gb', type=float, default=20)
    ap.add_argument('--offline', action='store_true', help='do not check PyPI for new versions')
    args = ap.parse_args()

    restarted = os.environ.get('PYPLOTTER_RESTARTED') == '1'
    token = os.environ.get('PYPLOTTER_TOKEN') or secrets.token_urlsafe(24)
    session = os.environ.get('PYPLOTTER_SESSION') or tempfile.mkdtemp(prefix='pyplotter-')

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
        os.environ.update(PYPLOTTER_TOKEN=token, PYPLOTTER_SESSION=session, PYPLOTTER_RESTARTED='1',
                          PYPLOTTER_PORT=str(httpd.server_address[1]))
        httpd.socket.close()
        argv = [sys.executable, str(Path(__file__).resolve()), '--max-upload-gb', str(args.max_upload_gb)]
        argv += ['--offline'] if args.offline else []
        if os.name == 'nt':
            subprocess.Popen(argv)
            os._exit(0)
        os.execv(sys.executable, argv)
    app.restart_hook = restart

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nPyPlotter stopped.')
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
