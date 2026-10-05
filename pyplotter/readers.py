"""Read any supported file into pandas DataFrames.

``list_tables(path, fmt)`` names the tables inside a file (sheets, datasets, variables…);
``read_table(path, fmt, table, options)`` returns ``(DataFrame, options_used)``.
Text files are sniffed: comment lines, separator, decimal comma, header row and encoding.
"""
import bz2
import csv
import gzip
import io
import json
import lzma
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

import numpy as np
import pandas as pd

from .catalog import detect_format, FILE_FORMATS

MAX_CELLS = 50_000_000
SNIFF_BYTES = 256 * 1024
ENCODINGS = ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1')
COMMENT_PREFIXES = ('#', '%', '!', '//', ';')
NUMBER = re.compile(r'^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eEdD][+-]?\d+)?$|^[+-]?(nan|inf|infinity)$', re.I)
SEPARATORS = ['\t', ';', ',', '|']


# ------------------------------------------------------------------ helpers
def _open_binary(path, compression):
    if compression == 'gzip':
        return gzip.open(path, 'rb')
    if compression == 'bz2':
        return bz2.open(path, 'rb')
    if compression == 'xz':
        return lzma.open(path, 'rb')
    return open(path, 'rb')


def _decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', errors='replace'), 'latin-1'


def unique_names(names):
    out, seen = [], {}
    for i, n in enumerate(names):
        n = str(n).strip() if n is not None and str(n).strip() not in ('', 'nan', 'None') else f'col{i + 1}'
        if n in seen:
            seen[n] += 1
            n = f'{n}_{seen[n]}'
        else:
            seen[n] = 0
        out.append(n)
    return out


# A number as text, possibly with thousands groups: 12  -3.5  1,003.3  1.003,3  1 003,3  2.5e-3
NUMBER_TEXT = re.compile(r"\s*[+\-\u2212]?(?:\d{1,3}(?:[,.\u00a0\u202f' ]\d{3})+|\d*)(?:[.,]\d+)?(?:[eE][+\-]?\d+)?\s*")
_GROUPS_COMMA = re.compile(r"(?<=\d)[,\u00a0\u202f' ](?=\d{3}(?!\d))")     # 1,003.3  1 003.3  1'003.3
_GROUPS_DOT = re.compile(r"(?<=\d)[.\u00a0\u202f' ](?=\d{3}(?!\d))")       # 1.003,3  1 003,3
THOUSANDS_STYLES = ('comma', 'dot')      # comma: 1,234.5   dot: 1.234,5


def _clean(s):
    return s.astype('string').str.strip().str.replace('\u2212', '-', regex=False)


def to_number(s, style=None):
    """Text → float. style None: plain numbers only; 'comma': 1,234.5; 'dot': 1.234,5 (NaN where impossible)."""
    txt = _clean(s)
    if style == 'comma':
        txt = txt.str.replace(_GROUPS_COMMA, '', regex=True)
    elif style == 'dot':
        txt = txt.str.replace(_GROUPS_DOT, '', regex=True).str.replace(',', '.', regex=False)
    return pd.to_numeric(txt, errors='coerce').astype(float)


def _spread(s, n=1000):
    """Up to n values taken across the whole column (not only its first rows)."""
    s = s.dropna().astype(str)
    return s if len(s) <= n else s.iloc[::max(1, len(s) // n)]


def tidy(df, decimal='.', convert=None, report=None):
    """Unique string column names, no fully empty rows/columns, numbers and datetimes recognised.

    Plain numbers are converted automatically. Numbers written with thousands separators
    ("1,003.3") are converted only when ``convert`` says so ({column or '*': 'comma'|'dot'|'none'});
    otherwise they are listed in ``report`` so that the interface can ask the user.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [' / '.join(str(p) for p in c if str(p) != '' and not str(p).startswith('Unnamed')) for c in df.columns]
    df = df.dropna(axis=1, how='all').dropna(axis=0, how='all')
    df.columns = unique_names(df.columns)
    convert = convert or {}
    for c in df.columns:
        s = df[c]
        if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
            continue
        sample = _spread(s)
        if not len(sample):
            continue
        looks_numeric = sample.str.fullmatch(NUMBER_TEXT).mean() > 0.95 and sample.str.contains(r'\d').mean() > 0.95
        if looks_numeric:
            n = s.notna().sum()
            plain = to_number(s)
            if plain.notna().sum() >= 0.95 * n:
                df[c] = plain
                continue
            choice = convert.get(c, convert.get('*'))
            if choice in THOUSANDS_STYLES:
                df[c] = to_number(s, choice)
                continue
            if choice == 'none' or report is None:
                continue
            for style in (THOUSANDS_STYLES if decimal != ',' else THOUSANDS_STYLES[::-1]):
                num = to_number(s, style)
                if num.notna().sum() >= 0.95 * n:
                    examples = s[plain.isna() & num.notna()].astype(str)
                    report.append({'column': c, 'style': style, 'count': int((plain.isna() & num.notna()).sum()),
                                   'rows': int(n), 'example': examples.iloc[0] if len(examples) else '',
                                   'value': float(num[plain.isna() & num.notna()].iloc[0]) if len(examples) else None})
                    break
            continue                       # numeric-looking text is never read as dates
        if sample.str.contains(r'\d[-/:.]\d', regex=True).mean() > 0.9:
            try:
                parsed = pd.to_datetime(s, errors='coerce', format='mixed')
            except (TypeError, ValueError):
                continue
            if parsed.notna().sum() >= 0.9 * s.notna().sum():
                df[c] = parsed
    if df.size > MAX_CELLS:
        raise ValueError(f'The table has {df.size:,} cells; the limit is {MAX_CELLS:,}.')
    return df.reset_index(drop=True)


def array_to_frame(arr, name='value'):
    arr = np.asarray(arr)
    if arr.dtype.byteorder not in ('=', '|') and arr.dtype.kind in 'iufc':
        arr = arr.astype(arr.dtype.newbyteorder('='))
    if arr.dtype.names:
        return pd.DataFrame({n: array_to_frame(arr[n]).iloc[:, 0] if arr[n].ndim == 1 else list(arr[n]) for n in arr.dtype.names})
    if arr.dtype.kind == 'c':
        arr = np.abs(arr)
    if arr.ndim == 0:
        return pd.DataFrame({name: [arr.item()]})
    if arr.ndim == 1:
        if arr.dtype.kind in 'SO':
            arr = np.array([x.decode(errors='replace') if isinstance(x, bytes) else x for x in arr], dtype=object)
        return pd.DataFrame({name: arr})
    if arr.ndim > 2:
        arr = arr.reshape(-1, arr.shape[-1])
    cols = [f'{name}[{j}]' for j in range(arr.shape[1])] if arr.shape[1] > 1 else [name]
    return pd.DataFrame(arr, columns=cols)


# ------------------------------------------------------------------ text sniffing
def sniff_text(path, compression=None):
    """Detect how to read a delimited text file. Returns pandas read_csv options."""
    with _open_binary(path, compression) as fh:
        raw = fh.read(SNIFF_BYTES)
    text, encoding = _decode(raw)
    lines = text.splitlines()
    if len(raw) == SNIFF_BYTES and lines:
        lines = lines[:-1]                       # last line may be cut
    # Leading comment / blank lines; remember the last comment as a possible header.
    skip, comment_header, comment = 0, None, None
    for line in lines:
        stripped = line.strip()
        prefix = next((p for p in COMMENT_PREFIXES if stripped.startswith(p)), None)
        if stripped and prefix is None:
            break
        if prefix:
            comment = comment or prefix[0]
            comment_header = stripped[len(prefix):].strip() or comment_header
        skip += 1
    body = [l for l in lines[skip:skip + 200] if l.strip()]
    if not body:
        raise ValueError('The file contains no data rows.')

    sep = None
    for cand in SEPARATORS:
        counts = [_fields(l, cand) - 1 for l in body[:100]]
        if counts[0] > 0 and min(counts) == max(counts):
            sep = cand
            break
    if sep is None:
        for cand in SEPARATORS:                  # tolerate a few ragged rows
            counts = [_fields(l, cand) - 1 for l in body[:100]]
            if counts[0] > 0 and sum(c == counts[0] for c in counts) >= 0.9 * len(counts):
                sep = cand
                break
    split = (lambda l: next(csv.reader([l], delimiter=sep))) if sep else (lambda l: l.split())
    rows = [split(l) for l in body[:100]]
    tokens = [t.strip().strip('"\'') for r in rows[1:] for t in r if t.strip()]

    decimal = '.'
    if sep != ',':
        comma = sum(bool(re.fullmatch(r'[+-]?\d+,\d+([eE][+-]?\d+)?', t)) for t in tokens)
        dot = sum(bool(re.fullmatch(r'[+-]?\d*\.\d+([eE][+-]?\d+)?', t)) for t in tokens)
        if comma > dot:
            decimal = ','

    def numeric(t):
        return bool(NUMBER.match(t.strip().strip('"\'')))

    first = [t for t in rows[0] if t.strip()]
    header = 0 if first and not all(numeric(t) for t in first) else None
    names = None
    if header is None and comment_header:
        cand = (next(csv.reader([comment_header], delimiter=sep)) if sep else comment_header.split())
        cand = [c.strip() for c in cand if c.strip()]
        if len(cand) == len(first) and not all(numeric(c) for c in cand):
            names = cand
    return {'sep': sep or 'whitespace', 'decimal': decimal, 'header': header, 'skiprows': skip,
            'encoding': encoding, 'comment': comment, 'names': names}


def _fields(line, sep):
    """Number of fields in a line, ignoring separators inside quotes ("1,003.3")."""
    try:
        return len(next(csv.reader([line], delimiter=sep)))
    except (csv.Error, StopIteration):
        return line.count(sep) + 1


def read_text(path, compression=None, options=None):
    detected = sniff_text(path, compression)
    opts = dict(detected)
    for key, value in (options or {}).items():
        if key in opts and value not in (None, '', 'auto'):
            opts[key] = value
    if (options or {}).get('header') == 'none':
        opts['header'] = None
    elif isinstance(opts['header'], str) and opts['header'].isdigit():
        opts['header'] = int(opts['header'])
    opts['skiprows'] = int(opts['skiprows'] or 0)
    sep = opts['sep']
    kwargs = dict(sep=r'\s+' if sep == 'whitespace' else sep, decimal=opts['decimal'], header=opts['header'],
                  skiprows=opts['skiprows'], encoding=opts['encoding'], compression=compression,
                  skip_blank_lines=True, on_bad_lines='warn')
    if opts.get('names') and opts['header'] is None:
        kwargs['names'] = opts['names']
    if opts.get('comment') and opts['comment'] != sep:
        kwargs['comment'] = opts['comment']
    if sep == 'whitespace' or len(sep) > 1:
        kwargs['engine'] = 'python'
    df = pd.read_csv(path, **kwargs)
    if opts['header'] is None and not opts.get('names'):
        df.columns = [f'col{i + 1}' for i in range(df.shape[1])]
    report = []
    df = tidy(df, opts['decimal'], (options or {}).get('convert'), report)
    opts['suggestions'] = report
    return df, opts


# ------------------------------------------------------------------ JCAMP-DX (spectra)
def read_jcamp(path):
    """JCAMP-DX spectra in AFFN form: ##XYDATA=(X++(Y..Y)), ##XYPOINTS or ##PEAK TABLE."""
    text, _ = _decode(Path(path).read_bytes())
    meta, mode = {}, None
    lines_x, lines_y = [], []        # X++(Y..Y): first x of each line and its y values
    pairs = []
    for line in text.splitlines():
        line = line.split('$$')[0].strip()
        if not line:
            continue
        if line.startswith('##'):
            key, _, value = line[2:].partition('=')
            key = re.sub(r'[\s\-_/]', '', key).upper()
            if key in ('XYDATA', 'XYPOINTS', 'PEAKTABLE'):
                mode = 'xpp' if '++' in value else 'pairs'
            elif key == 'END' and (lines_y or pairs):
                break
            else:
                meta[key] = value.strip()
                mode = None
            continue
        if mode == 'xpp':
            if re.search(r'[@%A-Za-z]', re.sub(r'(?<=\d)[eE](?=[+-]?\d)', '', line)):
                raise ValueError('Compressed JCAMP-DX (SQZ/DIF) is not supported; export the spectrum as AFFN or CSV.')
            vals = [float(v) for v in re.split(r'[\s,]+', line) if v]
            if len(vals) >= 2:
                lines_x.append(vals[0])
                lines_y.append(vals[1:])
        elif mode == 'pairs':
            for pair in re.split(r'[;\s]+', line):
                parts = [p for p in pair.split(',') if p]
                if len(parts) >= 2:
                    pairs.append((float(parts[0]), float(parts[1])))
    xf = float(meta.get('XFACTOR') or 1)
    yf = float(meta.get('YFACTOR') or 1)
    if lines_y:
        y = np.concatenate([np.asarray(v) for v in lines_y]) * yf
        if meta.get('FIRSTX') and meta.get('LASTX'):
            x = np.linspace(float(meta['FIRSTX']), float(meta['LASTX']), len(y))
        else:
            x = []
            for i, (x0, ys) in enumerate(zip(lines_x, lines_y)):
                nxt = lines_x[i + 1] if i + 1 < len(lines_x) else None
                step = (nxt - x0) / len(ys) if nxt is not None else (step if i else 1.0)
                x.extend(x0 + step * k for k in range(len(ys)))
            x = np.asarray(x) * xf
    elif pairs:
        arr = np.asarray(pairs)
        x, y = arr[:, 0] * xf, arr[:, 1] * yf
    else:
        raise ValueError('No spectrum data found in the JCAMP-DX file.')
    xname = f'x ({meta["XUNITS"]})' if meta.get('XUNITS') else 'x'
    yname = f'y ({meta["YUNITS"]})' if meta.get('YUNITS') else 'y'
    return pd.DataFrame({xname: x, yname: y})


# ------------------------------------------------------------------ table listing
def list_tables(path, fmt):
    path = str(path)
    if fmt in ('excel', 'xls', 'ods'):
        engine = {'excel': 'openpyxl', 'xls': 'xlrd', 'ods': 'odf'}[fmt]
        with pd.ExcelFile(path, engine=engine) as book:
            return [str(s) for s in book.sheet_names]
    if fmt == 'numpy' and path.lower().endswith('.npz'):
        with np.load(path, allow_pickle=False) as z:
            return list(z.files)
    if fmt == 'hdf5':
        return _hdf5_tables(path)
    if fmt == 'netcdf':
        import xarray as xr
        with xr.open_dataset(path) as ds:
            return [str(v) for v in ds.data_vars] or [str(c) for c in ds.coords]
    if fmt == 'matlab':
        return _mat_tables(path)
    if fmt == 'fits':
        from astropy.io import fits
        with fits.open(path, memmap=False) as hdul:
            return [f'{i}: {h.name or "HDU"}' for i, h in enumerate(hdul) if h.data is not None]
    if fmt == 'sqlite':
        with _sqlite(path) as con:
            rows = con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                               "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        return [r[0] for r in rows]
    if fmt == 'html':
        return [f'table {i + 1}' for i in range(len(pd.read_html(path)))]
    if fmt == 'zip':
        with zipfile.ZipFile(path) as zf:
            return [n for n in zf.namelist() if not n.endswith('/') and not Path(n).name.startswith('.')
                    and '__MACOSX' not in n and detect_format(n)[0] not in (None, 'zip')]
    return ['data']


def _hdf5_tables(path):
    tables = []
    try:
        with pd.HDFStore(path, mode='r') as store:
            tables = [k.lstrip('/') for k in store.keys()]
    except Exception:
        tables = []
    if tables:
        return ['pandas:' + t for t in tables]
    import h5py
    out = []
    with h5py.File(path, 'r') as f:
        f.visititems(lambda name, obj: out.append(name) if isinstance(obj, h5py.Dataset) and obj.size else None)
    return out


def _mat_tables(path):
    try:
        from scipy.io import whosmat
        names = [n for n, shape, cls in whosmat(path) if cls not in ('function_handle',)]
        if names:
            return names
    except NotImplementedError:
        pass
    except ValueError:
        pass
    import h5py   # MATLAB v7.3 files are HDF5
    out = []
    with h5py.File(path, 'r') as f:
        f.visititems(lambda name, obj: out.append(name) if isinstance(obj, h5py.Dataset) and not name.startswith('#') else None)
    return out


def _sqlite(path):
    return sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)


# ------------------------------------------------------------------ reading
def read_table(path, fmt, table=None, options=None, compression=None):
    """Read one table; returns (DataFrame, options actually used)."""
    path = str(path)
    options = options or {}
    used = {}
    if fmt == 'text':
        return read_text(path, compression, options)
    if fmt in ('excel', 'xls', 'ods'):
        engine = {'excel': 'openpyxl', 'xls': 'xlrd', 'ods': 'odf'}[fmt]
        header = options.get('header')
        header = None if header == 'none' else int(header) if str(header).isdigit() else 0
        skip = int(options.get('skiprows') or 0)
        df = pd.read_excel(path, sheet_name=table or 0, engine=engine, header=header, skiprows=skip)
        used = {'header': header, 'skiprows': skip}
    elif fmt == 'json':
        df = _read_json(path, compression)
    elif fmt == 'jsonl':
        df = pd.read_json(path, lines=True, compression=compression)
    elif fmt == 'parquet':
        df = pd.read_parquet(path)
    elif fmt == 'feather':
        df = pd.read_feather(path)
    elif fmt == 'orc':
        df = pd.read_orc(path)
    elif fmt == 'numpy':
        if path.lower().endswith('.npz'):
            with np.load(path, allow_pickle=False) as z:
                df = array_to_frame(z[table or z.files[0]], table or z.files[0])
        else:
            df = array_to_frame(np.load(path, allow_pickle=False), Path(path).stem)
    elif fmt == 'hdf5':
        df = _read_hdf5(path, table)
    elif fmt == 'netcdf':
        import xarray as xr
        with xr.open_dataset(path) as ds:
            name = table or next(iter(ds.data_vars))
            var = ds[name]
            if var.size > MAX_CELLS:
                raise ValueError(f'Variable {name} has {var.size:,} values; the limit is {MAX_CELLS:,}.')
            df = var.to_dataframe().reset_index()
    elif fmt == 'matlab':
        df = _read_mat(path, table)
    elif fmt == 'fits':
        df = _read_fits(path, table)
    elif fmt == 'spss':
        df = pd.read_spss(path)
    elif fmt == 'stata':
        df = pd.read_stata(path)
    elif fmt == 'sas':
        df = pd.read_sas(path)
    elif fmt == 'xml':
        df = _read_xml(path)
    elif fmt == 'html':
        tables = pd.read_html(path)
        idx = int(str(table).split()[-1]) - 1 if table else 0
        df = tables[idx]
    elif fmt == 'sqlite':
        with _sqlite(path) as con:
            name = table or list_tables(path, 'sqlite')[0]
            df = pd.read_sql_query('SELECT * FROM "{}"'.format(name.replace('"', '""')), con)
    elif fmt == 'jcamp':
        df = read_jcamp(path)
    elif fmt == 'zip':
        return _read_zip_member(path, table, options)
    else:
        raise ValueError(f'Unsupported format: {fmt}')
    report = []
    df = tidy(df, convert=options.get('convert'), report=report)
    used['suggestions'] = report
    return df, used


def _read_json(path, compression):
    with _open_binary(path, compression) as fh:
        data = json.loads(fh.read().decode('utf-8-sig'))
    if isinstance(data, dict):
        lists = {k: v for k, v in data.items() if isinstance(v, list)}
        if lists and all(not isinstance(v, (dict, list)) for vs in lists.values() for v in vs[:50]):
            n = max(len(v) for v in lists.values())
            if all(len(v) == n for v in lists.values()):
                return pd.DataFrame(lists)
        for key in ('data', 'records', 'rows', 'items', 'results', 'values'):
            if isinstance(data.get(key), list):
                return pd.json_normalize(data[key])
        if lists:
            key = max(lists, key=lambda k: len(lists[k]))
            return pd.json_normalize(lists[key]) if isinstance(lists[key][0], dict) else pd.DataFrame({key: lists[key]})
        return pd.json_normalize(data)
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return pd.DataFrame(data)
        return pd.json_normalize(data)
    raise ValueError('The JSON file does not contain a table.')


def _read_xml(path):
    try:
        import lxml  # noqa: F401
        parser = 'lxml'
    except ImportError:
        parser = 'etree'
    return pd.read_xml(path, parser=parser)


def _read_hdf5(path, table):
    if table and table.startswith('pandas:'):
        return pd.read_hdf(path, key=table[len('pandas:'):])
    import h5py
    with h5py.File(path, 'r') as f:
        name = table or _hdf5_tables(path)[0]
        ds = f[name]
        if ds.size > MAX_CELLS:
            raise ValueError(f'Dataset {name} has {ds.size:,} values; the limit is {MAX_CELLS:,}.')
        return array_to_frame(ds[()], name.rsplit('/', 1)[-1])


def _read_mat(path, table):
    try:
        from scipy.io import loadmat
        data = loadmat(path, squeeze_me=True, struct_as_record=False, variable_names=[table] if table else None)
        names = [k for k in data if not k.startswith('__')]
        if not names:
            raise ValueError('The .mat file has no numeric variables.')
        value = data[table or names[0]]
        if hasattr(value, '_fieldnames'):          # MATLAB struct: one column per field
            return pd.DataFrame({f: np.ravel(getattr(value, f)) for f in value._fieldnames
                                 if np.ndim(getattr(value, f)) <= 1})
        return array_to_frame(value, table or names[0])
    except NotImplementedError:
        import h5py
        with h5py.File(path, 'r') as f:
            name = table or _mat_tables(path)[0]
            return array_to_frame(np.asarray(f[name]).T, name.rsplit('/', 1)[-1])


def _read_fits(path, table):
    from astropy.io import fits
    from astropy.table import Table
    idx = int(str(table).split(':')[0]) if table else None
    with fits.open(path, memmap=False) as hdul:
        if idx is None:
            idx = next(i for i, h in enumerate(hdul) if h.data is not None)
        hdu = hdul[idx]
        if isinstance(hdu, (fits.BinTableHDU, fits.TableHDU)):
            tab = Table(hdu.data)
            keep = [n for n in tab.colnames if len(tab[n].shape) <= 1]
            return tab[keep].to_pandas()
        return array_to_frame(np.asarray(hdu.data), hdu.name or 'image')


def _read_zip_member(path, member, options):
    with zipfile.ZipFile(path) as zf:
        members = list_tables(path, 'zip')
        member = member or (members[0] if members else None)
        if member not in members:
            raise ValueError('The ZIP archive contains no supported data file.')
        info = zf.getinfo(member)
        if info.file_size > 4 * 1024 ** 3:
            raise ValueError('The ZIP member is larger than 4 GB; extract it first.')
        fmt, compression = detect_format(member)
        with tempfile.TemporaryDirectory(prefix='pyplotter-zip-') as tmp:
            target = Path(tmp) / ('member' + ''.join(Path(member).suffixes[-2:]))
            with zf.open(member) as src, open(target, 'wb') as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            inner = list_tables(target, fmt)
            return read_table(target, fmt, inner[0] if inner else None, options, compression)


def requirements(fmt):
    return list(FILE_FORMATS.get(fmt, {}).get('requires', []))
