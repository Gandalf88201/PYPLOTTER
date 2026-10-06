"""Static catalogue of what PyPlotter offers and which optional modules each item needs.

Standard library only: the server reads it before NumPy, pandas or Matplotlib are installed.
It is also copied next to exported figure scripts, so it must not import from the package.
"""
from pathlib import PurePath

# ---------------------------------------------------------------- input file formats
# key: (extensions, required module ids from registry.json, multi-table container?)
FILE_FORMATS = {
    'text':    {'ext': ['.csv', '.tsv', '.txt', '.dat', '.xy', '.xye', '.asc', '.prn', '.tab', '.data', '.out', '.log'], 'requires': []},
    'excel':   {'ext': ['.xlsx', '.xlsm', '.xltx', '.xltm'], 'requires': ['openpyxl']},
    'xls':     {'ext': ['.xls'], 'requires': ['xlrd']},
    'ods':     {'ext': ['.ods'], 'requires': ['odfpy']},
    'json':    {'ext': ['.json'], 'requires': []},
    'jsonl':   {'ext': ['.jsonl', '.ndjson'], 'requires': []},
    'parquet': {'ext': ['.parquet', '.pq'], 'requires': ['pyarrow']},
    'feather': {'ext': ['.feather', '.arrow', '.ipc'], 'requires': ['pyarrow']},
    'orc':     {'ext': ['.orc'], 'requires': ['pyarrow']},
    'hdf5':    {'ext': ['.h5', '.hdf5', '.hdf', '.he5'], 'requires': ['h5py']},
    'netcdf':  {'ext': ['.nc', '.nc4', '.cdf', '.netcdf'], 'requires': ['xarray', 'netcdf4']},
    'matlab':  {'ext': ['.mat'], 'requires': ['scipy']},
    'numpy':   {'ext': ['.npy', '.npz'], 'requires': []},
    'fits':    {'ext': ['.fits', '.fit', '.fts'], 'requires': ['astropy']},
    'spss':    {'ext': ['.sav', '.zsav', '.por'], 'requires': ['pyreadstat']},
    'stata':   {'ext': ['.dta'], 'requires': []},
    'sas':     {'ext': ['.sas7bdat', '.xpt'], 'requires': []},
    'xml':     {'ext': ['.xml'], 'requires': []},
    'html':    {'ext': ['.html', '.htm'], 'requires': ['lxml']},
    'sqlite':  {'ext': ['.sqlite', '.sqlite3', '.db', '.db3'], 'requires': []},
    'jcamp':   {'ext': ['.jdx', '.dx', '.jcamp'], 'requires': []},
    'zip':     {'ext': ['.zip'], 'requires': []},
}
COMPRESSIONS = {'.gz': 'gzip', '.bz2': 'bz2', '.xz': 'xz'}
# Formats that can be read through a .gz/.bz2/.xz wrapper.
COMPRESSIBLE = {'text', 'json', 'jsonl'}


def detect_format(filename):
    """Return (format key, compression or None) for a file name; format is None when unknown."""
    suffixes = [s.lower() for s in PurePath(filename).suffixes]
    compression = None
    if suffixes and suffixes[-1] in COMPRESSIONS:
        compression = COMPRESSIONS[suffixes.pop()]
    ext = suffixes[-1] if suffixes else ''
    for key, info in FILE_FORMATS.items():
        if ext in info['ext']:
            if compression and key not in COMPRESSIBLE:
                return None, compression
            return key, compression
    if compression or not ext:
        return 'text', compression     # e.g. "spectrum.gz" or "DATA": try as text
    return None, compression


def all_extensions():
    return sorted({e for info in FILE_FORMATS.values() for e in info['ext']} | set(COMPRESSIONS))


# ---------------------------------------------------------------- plot kinds
# inputs: which data roles the kind uses (drives the mapping panel).
# group: gallery section. requires: optional module ids.
KINDS = {
    'line':       {'group': 'xy',    'inputs': ['x', 'y', 'y2', 'hue'], 'requires': []},
    'scatter':    {'group': 'xy',    'inputs': ['x', 'y', 'y2', 'hue', 'z'], 'requires': []},
    'step':       {'group': 'xy',    'inputs': ['x', 'y', 'y2', 'hue'], 'requires': []},
    'area':       {'group': 'xy',    'inputs': ['x', 'y'], 'requires': []},
    'errorbar':   {'group': 'xy',    'inputs': ['x', 'y', 'xerr', 'yerr', 'y2'], 'requires': []},
    'regression': {'group': 'xy',    'inputs': ['x', 'y', 'hue'], 'requires': []},
    'stem':       {'group': 'xy',    'inputs': ['x', 'y'], 'requires': []},
    'polar':      {'group': 'xy',    'inputs': ['x', 'y'], 'requires': []},
    'bar':        {'group': 'cat',   'inputs': ['x', 'y', 'hue', 'yerr'], 'requires': []},
    'barh':       {'group': 'cat',   'inputs': ['x', 'y', 'hue', 'yerr'], 'requires': []},
    'box':        {'group': 'cat',   'inputs': ['x', 'y'], 'requires': []},
    'violin':     {'group': 'cat',   'inputs': ['x', 'y'], 'requires': []},
    'strip':      {'group': 'cat',   'inputs': ['x', 'y'], 'requires': ['seaborn']},
    'swarm':      {'group': 'cat',   'inputs': ['x', 'y'], 'requires': ['seaborn']},
    'pie':        {'group': 'cat',   'inputs': ['x', 'y'], 'requires': []},
    'hist':       {'group': 'dist',  'inputs': ['y', 'hue'], 'requires': []},
    'kde':        {'group': 'dist',  'inputs': ['y', 'hue'], 'requires': []},
    'ecdf':       {'group': 'dist',  'inputs': ['y', 'hue'], 'requires': []},
    'heatmap':    {'group': 'map',   'inputs': ['x', 'y', 'z'], 'requires': []},
    'contour':    {'group': 'map',   'inputs': ['x', 'y', 'z'], 'requires': []},
    'hexbin':     {'group': 'map',   'inputs': ['x', 'y'], 'requires': []},
    'hist2d':     {'group': 'map',   'inputs': ['x', 'y'], 'requires': []},
    'corr':       {'group': 'multi', 'inputs': ['y'], 'requires': []},
    'pairplot':   {'group': 'multi', 'inputs': ['y', 'hue'], 'requires': []},
    'surface3d':  {'group': '3d',    'inputs': ['x', 'y', 'z'], 'requires': []},
    'scatter3d':  {'group': '3d',    'inputs': ['x', 'y', 'z', 'hue'], 'requires': []},
    'waterfall':  {'group': '3d',    'inputs': ['x', 'y'], 'requires': []},
}
THREE_D_KINDS = {'surface3d', 'scatter3d', 'waterfall'}
TWIN_KINDS = {'line', 'scatter', 'step', 'errorbar'}

# ---------------------------------------------------------------- styles, palettes, colormaps
# base: Matplotlib style sheet(s) applied before PyPlotter's own settings.
STYLES = {
    'publication': {'base': ['default'], 'requires': []},
    'whitegrid':   {'base': ['seaborn-v0_8-whitegrid'], 'requires': []},
    'ticks':       {'base': ['seaborn-v0_8-ticks'], 'requires': []},
    'ggplot':      {'base': ['ggplot'], 'requires': []},
    'bmh':         {'base': ['bmh'], 'requires': []},
    'grayscale':   {'base': ['grayscale'], 'requires': []},
    'dark':        {'base': ['dark_background'], 'requires': []},
    'science':     {'base': ['science', 'no-latex'], 'requires': ['scienceplots']},
    'nature':      {'base': ['science', 'nature', 'no-latex'], 'requires': ['scienceplots']},
    'ieee':        {'base': ['science', 'ieee', 'no-latex'], 'requires': ['scienceplots']},
}

# Qualitative palettes; "cmap:<name>" samples a Matplotlib colormap. Sources (see REFERENCES.md):
# okabe-ito: Okabe & Ito (2008), Color Universal Design; tol-*: P. Tol (2021), SRON/EPS/TN/09-002;
# tableau10: Matplotlib's "tab10" cycle (Matplotlib licence); grayscale: PyPlotter.
PALETTES = {
    'okabe-ito':   ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9', '#F0E442', '#000000'],
    'tol-bright':  ['#4477AA', '#EE6677', '#228833', '#CCBB44', '#66CCEE', '#AA3377', '#BBBBBB'],
    'tol-vibrant': ['#0077BB', '#EE7733', '#009988', '#CC3311', '#33BBEE', '#EE3377', '#BBBBBB'],
    'tol-muted':   ['#332288', '#88CCEE', '#44AA99', '#117733', '#999933', '#DDCC77', '#CC6677', '#882255', '#AA4499'],
    'tableau10':   ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'],
    'grayscale':   ['#000000', '#555555', '#8C8C8C', '#B4B4B4', '#D2D2D2'],
    'cmap:viridis': [], 'cmap:cividis': [], 'cmap:plasma': [], 'cmap:coolwarm': [],
}

COLORMAPS = {
    'sequential': ['viridis', 'cividis', 'plasma', 'inferno', 'magma', 'turbo', 'Greys', 'Blues', 'Reds', 'YlOrRd', 'YlGnBu'],
    'diverging':  ['RdBu', 'coolwarm', 'bwr', 'seismic', 'PuOr', 'BrBG', 'Spectral', 'PiYG'],
    'cyclic':     ['twilight', 'hsv'],
    'crameri':    ['cmc.batlow', 'cmc.roma', 'cmc.vik', 'cmc.lajolla', 'cmc.hawaii', 'cmc.oslo', 'cmc.berlin', 'cmc.lipari'],
}
COLORMAP_REQUIRES = {'cmc.': ['cmcrameri']}

# ---------------------------------------------------------------- export
EXPORT_FORMATS = {
    'png':  {'raster': True,  'requires': [], 'mime': 'image/png'},
    'tiff': {'raster': True,  'requires': [], 'mime': 'image/tiff'},
    'jpg':  {'raster': True,  'requires': [], 'mime': 'image/jpeg'},
    'pdf':  {'raster': False, 'requires': [], 'mime': 'application/pdf'},
    'svg':  {'raster': False, 'requires': [], 'mime': 'image/svg+xml'},
    'eps':  {'raster': False, 'requires': [], 'mime': 'application/postscript'},
    'html': {'raster': False, 'requires': ['plotly'], 'mime': 'text/html'},
    'py':   {'raster': False, 'requires': [], 'mime': 'application/zip'},
}

# Common journal column widths (mm); heights give a pleasant default aspect.
SIZE_PRESETS = {
    'nature-1':    (89, 67),   'nature-2':    (183, 120),
    'science-1':   (57, 45),   'science-2':   (121, 85),  'science-3': (184, 110),
    'acs-1':       (82.5, 62), 'acs-2':       (178, 110),
    'elsevier-1':  (90, 68),   'elsevier-1.5': (140, 95), 'elsevier-2': (190, 120),
    'rsc-1':       (83, 63),   'rsc-2':       (171, 105),
    'aps-1':       (86, 65),   'aps-2':       (178, 110),
    'ieee-1':      (88.9, 66), 'ieee-2':      (181.9, 110),
    'thesis':      (150, 100), 'slide-16:9':  (254, 142.9), 'poster':    (300, 200),
}


def requirements_for(kind=None, style=None, cmap=None, export=None):
    """Module ids a figure needs beyond the core, de-duplicated and in a stable order."""
    need = []
    if kind in KINDS:
        need += KINDS[kind]['requires']
    if style in STYLES:
        need += STYLES[style]['requires']
    if cmap:
        for prefix, ids in COLORMAP_REQUIRES.items():
            if str(cmap).startswith(prefix):
                need += ids
    if export in EXPORT_FORMATS:
        need += EXPORT_FORMATS[export]['requires']
    return list(dict.fromkeys(need))
