"""Licence of a Python package from its metadata: is it an OSI-approved open-source licence?

The answer comes from, in order: the SPDX ``License-Expression`` (PEP 639), the ``License ::``
trove classifiers, and the free-text ``License`` field. The result is one of
  'osi'          an OSI-approved licence (https://opensource.org/licenses)
  'not_osi'      a known licence that is not OSI-approved (e.g. Creative Commons, source-available)
  'proprietary'  declared proprietary
  'unknown'      no licence information, or one that cannot be recognised
PyPlotter only installs packages on its own when the answer is 'osi'; anything else needs the
user's explicit confirmation. This is a convenience, not legal advice: the licence text decides.
"""
import re

# OSI-approved licences (SPDX identifiers, lower case). Not the whole list, but every licence common
# on PyPI; an identifier missing here gives 'unknown', never 'osi'.
OSI_SPDX = {
    '0bsd', 'afl-3.0', 'agpl-3.0', 'agpl-3.0-only', 'agpl-3.0-or-later', 'apache-1.1', 'apache-2.0', 'apsl-2.0',
    'artistic-2.0', 'blueoak-1.0.0', 'bsd-1-clause', 'bsd-2-clause', 'bsd-2-clause-patent', 'bsd-3-clause',
    'bsd-3-clause-lbnl', 'bsl-1.0', 'cddl-1.0', 'cecill-2.1', 'cnri-python', 'ecl-2.0', 'efl-2.0', 'epl-1.0',
    'epl-2.0', 'eudatagrid', 'eupl-1.1', 'eupl-1.2', 'gpl-2.0', 'gpl-2.0-only', 'gpl-2.0-or-later', 'gpl-3.0',
    'gpl-3.0-only', 'gpl-3.0-or-later', 'hpnd', 'intel', 'isc', 'lgpl-2.0', 'lgpl-2.0-only', 'lgpl-2.0-or-later',
    'lgpl-2.1', 'lgpl-2.1-only', 'lgpl-2.1-or-later', 'lgpl-3.0', 'lgpl-3.0-only', 'lgpl-3.0-or-later', 'lppl-1.3c',
    'mit', 'mit-0', 'mit-cmu', 'mpl-1.0', 'mpl-1.1', 'mpl-2.0', 'mpl-2.0-no-copyleft-exception', 'ms-pl', 'ms-rl', 'ncsa',
    'ofl-1.1', 'osl-3.0', 'php-3.01', 'postgresql', 'psf-2.0', 'python-2.0', 'qpl-1.0', 'unicode-dfs-2016',
    'unlicense', 'upl-1.0', 'w3c', 'zlib', 'zpl-2.0', 'zpl-2.1',
}
# Public-domain dedication, not OSI-approved: accepted next to OSI licences (numpy: "BSD-3-Clause AND … AND
# CC0-1.0" for bundled data), but not alone.
PUBLIC_DOMAIN = {'cc0-1.0'}
# Known licences that are not OSI-approved (data/content licences, source-available, non-commercial).
NOT_OSI_SPDX = {
    'busl-1.1', 'cc-by-1.0', 'cc-by-2.0', 'cc-by-3.0', 'cc-by-4.0', 'cc-by-sa-3.0', 'cc-by-sa-4.0', 'cc-by-nc-3.0',
    'cc-by-nc-4.0', 'cc-by-nc-sa-4.0', 'cc-by-nd-4.0', 'cc-by-nc-nd-4.0', 'cc0-1.0', 'elastic-2.0', 'json',
    'polyform-noncommercial-1.0.0', 'polyform-small-business-1.0.0', 'sspl-1.0', 'wtfpl',
}
# Free-text names often found in the License field, mapped to SPDX.
_TEXT = [
    (r'\bagpl|affero', 'AGPL-3.0'), (r'\blgpl|lesser general public', 'LGPL-3.0'), (r'\bgpl|general public licen', 'GPL-3.0'),
    (r'\bmpl\b|mozilla', 'MPL-2.0'), (r'apache', 'Apache-2.0'), (r'\bbsd\b|bsd[- ]?[23]', 'BSD-3-Clause'),
    (r'\bmit\b|expat', 'MIT'), (r'\bisc\b', 'ISC'), (r'\bpsf\b|python software foundation', 'PSF-2.0'),
    (r'\bzlib\b', 'Zlib'), (r'eclipse|\bepl\b', 'EPL-2.0'), (r'unlicen[sc]e', 'Unlicense'),
    (r'boost|\bbsl-1', 'BSL-1.0'), (r'\beupl\b', 'EUPL-1.2'), (r'cecill', 'CECILL-2.1'),
    (r'creative commons|\bcc[- ]by|\bcc0\b', 'CC-BY-4.0'),
    (r'permission is hereby granted, free of charge', 'MIT'),                    # the licence text itself
    (r'redistribution and use in source and binary forms', 'BSD-3-Clause'),
]
_NOT_OSI_CLASSIFIERS = ('public domain', 'freeware', 'free for non-commercial use', 'free for educational use',
                        'free for home use', 'free to use but restricted', 'aladdin', 'shareware')


def _spdx_status(expression):
    """'osi' when some alternative of the expression has only OSI licences; 'proprietary' / 'not_osi'
    when the expression names such a licence and no OSI alternative exists; else 'unknown'."""
    expr = re.sub(r'\bWITH\s+\S+', '', expression, flags=re.I).replace('(', ' ').replace(')', ' ')
    alternatives = [a.split() for a in re.split(r'\s+OR\s+', expr, flags=re.I)]
    seen = set()
    for alt in alternatives:
        ids = [i.lower().rstrip('+') for i in alt if i.upper() != 'AND']
        seen.update(ids)
        if ids and all(i in OSI_SPDX or i in PUBLIC_DOMAIN for i in ids) and any(i in OSI_SPDX for i in ids):
            return 'osi'
    if any('proprietary' in i or i == 'licenseref-proprietary' for i in seen):
        return 'proprietary'
    if any(i in NOT_OSI_SPDX for i in seen):
        return 'not_osi'
    return 'unknown'


def classify(expression='', classifiers=(), text=''):
    """{'license': short name to show, 'status': 'osi' | 'not_osi' | 'proprietary' | 'unknown'}."""
    expression = (expression or '').strip()
    if expression:
        return {'license': expression[:80], 'status': _spdx_status(expression)}
    lic = [c.split('::')[-1].strip() for c in classifiers or () if c.startswith('License ::')]
    if lic:
        osi = [c for c in classifiers if c.startswith('License :: OSI Approved')]
        if osi:
            name = osi[0].split('::')[-1].strip()
            return {'license': name if name != 'OSI Approved' else 'OSI Approved', 'status': 'osi'}
        joined = ' '.join(lic).lower()
        if 'proprietary' in joined:
            return {'license': lic[0], 'status': 'proprietary'}
        if any(k in joined for k in _NOT_OSI_CLASSIFIERS):
            return {'license': lic[0], 'status': 'not_osi'}
    first = next((l.strip() for l in (text or '').splitlines() if l.strip()), '')
    if first:
        low = first.lower()
        if 'proprietary' in low or 'all rights reserved' in low or 'commercial licen' in low:
            return {'license': first[:80], 'status': 'proprietary'}
        if re.fullmatch(r'[\w.+-]+(\s+(OR|AND|WITH)\s+[\w.+-]+)*', first):     # an SPDX id in the text field
            status = _spdx_status(first)
            if status != 'unknown':
                return {'license': first, 'status': status}
        head = text[:3000].lower()          # the field often holds the whole licence text
        for pattern, spdx in _TEXT:
            if re.search(pattern, head):
                return {'license': first[:80] if re.search(pattern, low) else spdx,
                        'status': 'osi' if spdx.lower() in OSI_SPDX else 'not_osi'}
        return {'license': first[:80], 'status': 'unknown'}
    if lic:
        return {'license': lic[0], 'status': 'unknown'}
    return {'license': '', 'status': 'unknown'}


def from_metadata(meta):
    """classify() for a metadata mapping: an email.message (importlib.metadata) or a pip report entry."""
    if hasattr(meta, 'get_all'):
        return classify(meta.get('License-Expression') or '', meta.get_all('Classifier') or [], meta.get('License') or '')
    return classify(meta.get('license_expression') or '', meta.get('classifier') or [], meta.get('license') or '')
