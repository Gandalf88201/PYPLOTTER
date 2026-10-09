"""π-plotter: publication-quality plots from any data file, in the browser, with a local Python service."""
import os
import shutil
import sys
from pathlib import Path

__version__ = '0.2.0'
NAME = 'π-plotter'
AUTHOR = 'Dr. T. Francese'

# Plugins written before the rename (customised copies of built-in analyses, yours) still say
# "from pyplotter import baselines": the old name keeps working as an alias of this package.
sys.modules.setdefault('pyplotter', sys.modules[__name__])


def home_dir():
    """The folder for tokens, user plugins and module lists: $PIPLOTTER_HOME or ~/.piplotter.

    The first time, what versions before the rename left in ~/.pyplotter (your plugins, your modules,
    the token) is copied there; the old folder itself is not touched."""
    env = os.environ.get('PIPLOTTER_HOME')
    if env:
        return Path(env)
    new, old = Path.home() / '.piplotter', Path.home() / '.pyplotter'
    if not new.exists() and old.is_dir():
        try:
            shutil.copytree(old, new, ignore=shutil.ignore_patterns('._*', 'pypi-cache.json', 'import-check.json'))
        except OSError:
            pass          # the new folder is then created empty, as on a first start
    return new
