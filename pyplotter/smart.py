"""Column profiling, default data mapping and plot-type recommendations."""
import bisect
import re

import numpy as np
import pandas as pd

ERROR_NAME = re.compile(r'(^|[\s_\-(\[])(err|error|errors|errore|errori|std|sd|stdev|dev|devstd|sigma|unc|uncertainty|incertezza|sem|se|ci|±|delta)([\s_\-)\]]|$)', re.I)


def column_kind(s):
    if pd.api.types.is_bool_dtype(s):
        return 'category'
    if pd.api.types.is_datetime64_any_dtype(s) or isinstance(s.dtype, pd.DatetimeTZDtype):
        return 'datetime'
    if pd.api.types.is_timedelta64_dtype(s):
        return 'numeric'
    if pd.api.types.is_numeric_dtype(s):
        return 'numeric'
    return 'category'


MAX_UNIQUE_ROWS = 2_000_000      # longer columns: distinct values are not counted
BLOCK_CELLS = 4_000_000          # cells profiled at a time by profile_block


def profile(df):
    """One entry per column: kind, dtype, missing and distinct values; range, monotony and integers for numbers.

    Plain integer and float columns are profiled a block at a time with NumPy, so that tables with
    tens of thousands of columns open in seconds; the other columns, one by one.
    """
    fast = profile_block(df) if len(df) <= MAX_UNIQUE_ROWS else {}
    cols = []
    for i, name in enumerate(df.columns):
        info = {'name': name, **(fast.get(i) or profile_column(df.iloc[:, i]))}
        info['is_error'] = bool(ERROR_NAME.search(str(name)))
        cols.append(info)
    return cols


def profile_column(s):
    kind = column_kind(s)
    info = {'kind': kind, 'dtype': str(s.dtype), 'missing': int(s.isna().sum()),
            'unique': int(s.nunique(dropna=True)) if len(s) <= MAX_UNIQUE_ROWS else None}
    if kind == 'numeric':
        v = pd.to_numeric(s, errors='coerce').dropna()
        info['min'] = _num(v.min()) if len(v) else None
        info['max'] = _num(v.max()) if len(v) else None
        info['monotonic'] = bool(len(v) > 2 and (v.is_monotonic_increasing or v.is_monotonic_decreasing)
                                 and v.nunique() > 0.5 * len(v))
        with np.errstate(invalid='ignore'):
            info['integer'] = bool(len(v) and np.all(np.mod(v.to_numpy(dtype=float), 1) == 0))
    elif kind == 'datetime':
        info['monotonic'] = bool(s.dropna().is_monotonic_increasing)
    return info


def profile_block(df):
    """profile_column for every plain int/float column, vectorised: {position: info}."""
    groups = {}
    for i, dt in enumerate(df.dtypes):
        if isinstance(dt, np.dtype) and dt.kind in 'iuf':
            groups.setdefault(dt, []).append(i)
    n = len(df)
    step = max(1, BLOCK_CELLS // max(n, 1))
    out = {}
    for dt, where in groups.items():
        for start in range(0, len(where), step):
            part = where[start:start + step]
            a = df.iloc[:, part].to_numpy(dtype=dt)
            nan = np.isnan(a) if dt.kind == 'f' else np.zeros(a.shape, dtype=bool)
            valid = n - nan.sum(axis=0)
            s = np.sort(a, axis=0)                                   # missing values sort last
            change = (s[1:] != s[:-1]) & (np.arange(1, n)[:, None] < valid)
            unique = (valid > 0) + change.sum(axis=0)
            full = valid == n
            up = (a[1:] >= a[:-1]).all(axis=0)
            down = (a[1:] <= a[:-1]).all(axis=0)
            with np.errstate(invalid='ignore'):
                whole = ((np.mod(a, 1) == 0) | nan).all(axis=0) if dt.kind == 'f' else np.ones(len(part), bool)
            for j, col in enumerate(part):
                c = int(valid[j])
                if full[j] or c <= 2:
                    mono = bool(up[j] or down[j])
                else:                                                # gaps: the order of what is left
                    v = a[~nan[:, j], j]
                    mono = bool((v[1:] >= v[:-1]).all() or (v[1:] <= v[:-1]).all())
                out[col] = {'kind': 'numeric', 'dtype': str(dt), 'missing': n - c, 'unique': int(unique[j]),
                            'min': _num(s[0, j]) if c else None, 'max': _num(s[c - 1, j]) if c else None,
                            'monotonic': bool(c > 2 and mono and unique[j] > 0.5 * c),
                            'integer': bool(c and whole[j])}
    return out


def _num(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _discrete(info, n):
    """Numeric column with few distinct integer values behaves like a category."""
    return info['kind'] == 'numeric' and info.get('integer') and info.get('unique') is not None \
        and info['unique'] <= min(12, max(2, n // 5))


def find_grid(cols, n_rows):
    """(x, y, z) when two numeric columns form a regular grid (nx·ny = rows) and a third holds values."""
    numeric = [c for c in cols if c['kind'] == 'numeric' and c.get('unique')]
    by_unique = {}                     # distinct values -> positions: linear in the number of columns
    for i, c in enumerate(numeric):
        by_unique.setdefault(c['unique'], []).append(i)
    for i, a in enumerate(numeric):
        if a['unique'] < 3 or n_rows % a['unique'] or n_rows // a['unique'] < 3:
            continue
        later = by_unique.get(n_rows // a['unique'], [])
        for j in later[bisect.bisect_right(later, i):]:
            b = numeric[j]
            rest = next((c['name'] for c in numeric if c['name'] not in (a['name'], b['name'])), None)
            if rest is not None:
                return a['name'], b['name'], rest
    return None


def default_mapping(cols, n_rows):
    by = {c['name']: c for c in cols}
    numeric = [c['name'] for c in cols if c['kind'] == 'numeric']
    grid = find_grid(cols, n_rows) if n_rows >= 9 else None
    if grid:
        mapping = {'x': grid[0], 'y': [grid[1]], 'y2': [], 'hue': None, 'z': grid[2], 'xerr': None, 'yerr': None}
        mapping['kind'] = recommend(cols, mapping, n_rows)[0]['kind']
        return mapping
    x = None
    for c in cols:
        if c['kind'] == 'datetime':
            x = c['name']
            break
    if x is None:
        mono = [c['name'] for c in cols if c['kind'] == 'numeric' and c.get('monotonic') and not c['is_error']]
        if mono:
            x = mono[0]
        elif cols and cols[0]['kind'] == 'numeric' and len(numeric) > 1:
            x = cols[0]['name']
        elif cols and cols[0]['kind'] == 'category' and numeric:
            x = cols[0]['name']
    ys = [n for n in numeric if n != x and not by[n]['is_error']][:4]
    yerr = None
    if len(ys) == 1:
        errs = [n for n in numeric if by[n]['is_error'] and n != x]
        yerr = errs[0] if errs else None
    mapping = {'x': x, 'y': ys, 'y2': [], 'hue': None, 'z': None, 'xerr': None, 'yerr': yerr}
    recs = recommend(cols, mapping, n_rows)
    mapping['kind'] = recs[0]['kind'] if recs else 'line'
    return mapping


def recommend(cols, mapping, n_rows):
    """Ranked plot kinds for the current mapping: [{'kind', 'score', 'reason'}]."""
    by = {c['name']: c for c in cols}
    x = mapping.get('x')
    ys = [y for y in mapping.get('y') or [] if y in by]
    z = mapping.get('z')
    xi = by.get(x)
    xk = 'index' if xi is None else ('category' if xi['kind'] == 'category' or _discrete(xi, n_rows) else xi['kind'])
    yk = [by[y]['kind'] for y in ys]
    numeric_y = [y for y, k in zip(ys, yk) if k == 'numeric']
    scores = {}

    def add(kind, score, reason):
        if score > scores.get(kind, (0, ''))[0]:
            scores[kind] = (score, reason)

    surface = bool(z and z in by and xi is not None and xk == 'numeric' and numeric_y)
    if surface:
        add('contour', 0.92, 'surface')
        add('heatmap', 0.88, 'surface')
        add('scatter', 0.8, 'color_by_z')
        add('surface3d', 0.7, 'surface')
        add('scatter3d', 0.4, 'surface')
    if not ys:
        if xk == 'category':
            add('bar', 0.9, 'counts')
            add('pie', 0.5, 'counts')
        elif xk == 'numeric':
            add('hist', 0.9, 'distribution')
            add('kde', 0.75, 'distribution')
    if numeric_y:
        if mapping.get('yerr') or mapping.get('xerr'):
            add('errorbar', 0.97, 'errors')
        if xk == 'datetime':
            add('line', 0.95, 'time_series')
            add('area', 0.55, 'time_series')
            add('scatter', 0.5, 'time_series')
            add('step', 0.45, 'time_series')
        elif xk == 'numeric' and surface:
            pass
        elif xk == 'numeric':
            if xi.get('monotonic'):
                add('line', 0.95, 'monotonic_x')
                if 3 <= len(numeric_y) <= 60:
                    add('waterfall', 0.4, 'monotonic_x')
                add('scatter', 0.7, 'monotonic_x')
                add('step', 0.5, 'monotonic_x')
                add('area', 0.45, 'monotonic_x')
                add('stem', 0.3, 'monotonic_x')
            else:
                dense = n_rows > 5000
                add('scatter', 0.9 if dense else 0.95, 'cloud')
                add('regression', 0.75, 'cloud')
                add('hexbin', 0.93 if dense else 0.35, 'dense' if dense else 'cloud')
                add('hist2d', 0.6 if dense else 0.3, 'dense' if dense else 'cloud')
        elif xk == 'category':
            repeated = xi.get('unique') is not None and xi['unique'] < n_rows
            add('bar', 0.95, 'categorical_x')
            add('box', 0.88 if repeated else 0.4, 'groups')
            add('violin', 0.72 if repeated else 0.3, 'groups')
            add('strip', 0.55 if repeated else 0.25, 'groups')
            add('barh', 0.5, 'categorical_x')
            if len(numeric_y) == 1 and not repeated:
                add('pie', 0.35, 'categorical_x')
        else:   # no x: plot against the row index
            if len(numeric_y) == 1:
                add('hist', 0.9, 'distribution')
                add('kde', 0.8, 'distribution')
                add('line', 0.7, 'index')
                add('box', 0.6, 'distribution')
                add('ecdf', 0.5, 'distribution')
                add('violin', 0.45, 'distribution')
            else:
                add('line', 0.85, 'index')
                add('box', 0.8, 'compare_columns')
                add('violin', 0.65, 'compare_columns')
                add('hist', 0.6, 'distribution')
        if len(numeric_y) >= 3:
            add('corr', 0.7, 'many_vars')
            add('pairplot', 0.62, 'many_vars')
        if len(numeric_y) >= 2 and xk != 'numeric':
            add('heatmap', 0.35, 'matrix')
    ranked = sorted(({'kind': k, 'score': round(s, 2), 'reason': r} for k, (s, r) in scores.items()),
                    key=lambda d: -d['score'])
    return ranked[:8]


def warnings_for(mapping, kind, n_rows):
    out = []
    if kind in ('scatter', 'line') and n_rows > 300_000:
        out.append('many_points')
    if kind == 'pie' and n_rows > 12:
        out.append('pie_many')
    return out
