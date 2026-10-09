"""The built-in user manual: manual/MANUAL.md (plus manual/img/*.png) shown at /manual.

A small Markdown reader, standard library only, for the subset the manual uses: headings, paragraphs,
bullet and numbered lists (nested by indentation), tables, fenced code, quotes (tips and warnings),
images with a caption, rules, and **bold**, *italic*, `code`, [links]. Everything else is escaped text.
The text is edited in manual/MANUAL.md; tools/make_manual_images.py redraws the pictures.
"""
import html
import re
import struct
from pathlib import Path

from . import AUTHOR, NAME, __version__

MANUAL_DIR = Path(__file__).resolve().parent.parent / 'manual'
IMG_URL = '/manual/img/'
CALLOUTS = {'tip': 'Tip', 'note': 'Note', 'warning': 'Warning', 'important': 'Important'}


def slug(text):
    text = re.sub(r'<[^>]+>|[`*_]', '', text)
    return re.sub(r'[^0-9a-z]+', '-', text.lower()).strip('-') or 'section'


def safe_url(url):
    url = url.strip()
    if url.startswith(('http://', 'https://', '#', '/manual')):
        return html.escape(url, quote=True)
    if re.fullmatch(r'img/[\w.\-]+', url):
        return IMG_URL + html.escape(url[4:], quote=True)
    return ''


def inline(text):
    """Escape, then re-introduce `code`, **bold**, *italic* and [links](url). Code is taken out first."""
    codes = []

    def stash(m):
        codes.append(f'<code>{html.escape(m.group(1))}</code>')
        return f'\x00{len(codes) - 1}\x00'

    text = re.sub(r'`([^`]+)`', stash, text)
    text = html.escape(text, quote=False)

    def link(m):
        url = safe_url(html.unescape(m.group(2)))
        if not url:
            return m.group(1)
        external = ' target="_blank" rel="noopener"' if url.startswith('http') else ''
        return f'<a href="{url}"{external}>{m.group(1)}</a>'

    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', link, text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', text)
    return re.sub(r'\x00(\d+)\x00', lambda m: codes[int(m.group(1))], text)


def _cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def render_body(md):
    """Markdown -> (HTML of the body, table of contents [(level, id, text)])."""
    lines = md.replace('\r\n', '\n').split('\n')
    out, toc, used = [], [], {}
    i = 0

    def heading_id(text):
        base = slug(text)
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f'{base}-{used[base]}'

    def parse_list(i, indent):
        """Lines of one list at this indentation (and deeper, nested)."""
        pat = re.compile(r'^(\s*)([-*]|\d+[.)])\s+(.*)$')
        first = pat.match(lines[i])
        ordered = first.group(2)[0].isdigit()
        items = []
        while i < len(lines):
            m = pat.match(lines[i])
            if m and len(m.group(1)) == indent:
                items.append([m.group(3)])
                i += 1
            elif m and len(m.group(1)) > indent and items:
                sub, i = parse_list(i, len(m.group(1)))
                items[-1].append(sub)
            elif lines[i].strip() and lines[i].startswith(' ' * (indent + 2)) and items and not m:
                items[-1][0] += ' ' + lines[i].strip()       # a wrapped line of the same item
                i += 1
            else:
                break
        tag = 'ol' if ordered else 'ul'
        body = ''.join('<li>' + inline(it[0]) + ''.join(it[1:]) + '</li>' for it in items)
        return f'<{tag}>{body}</{tag}>', i

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('```'):
            lang = line[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f'<pre><code{f" class=lang-{html.escape(lang)}" if lang else ""}>{html.escape(chr(10).join(code))}</code></pre>')
            continue
        m = re.match(r'^(#{1,4})\s+(.*?)\s*#*$', line)
        if m:
            level, text = len(m.group(1)), m.group(2)
            hid = heading_id(text)
            if level in (2, 3):
                toc.append((level, hid, re.sub(r'[`*]', '', text)))
            out.append(f'<h{level} id="{hid}">{inline(text)}<a class="anchor" href="#{hid}" aria-label="link">#</a></h{level}>'
                       if level > 1 else f'<h1 id="{hid}">{inline(text)}</h1>')
            i += 1
            continue
        if re.fullmatch(r'-{3,}|\*{3,}', line.strip()):
            out.append('<hr>')
            i += 1
            continue
        m = re.fullmatch(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', line.strip())
        if m:
            url = safe_url(m.group(2))
            caption = m.group(3) or m.group(1)
            if url:
                size = png_size(MANUAL_DIR / m.group(2)) if m.group(2).startswith('img/') else None
                dims = f' width="{size[0] // 2}" height="{size[1] // 2}"' if size else ''     # pictures are taken at 2x
                out.append(f'<figure><a href="{url}" target="_blank" rel="noopener"><img src="{url}"{dims} alt="{html.escape(m.group(1), quote=True)}" loading="lazy"></a>'
                           f'<figcaption>{inline(caption)}</figcaption></figure>')
            i += 1
            continue
        if line.lstrip().startswith('>'):
            quote = []
            while i < len(lines) and lines[i].lstrip().startswith('>'):
                quote.append(re.sub(r'^\s*>\s?', '', lines[i]))
                i += 1
            text = ' '.join(q for q in quote if q.strip())
            kind = re.match(r'\*\*(\w+)[.:]?\*\*', text)
            cls = kind.group(1).lower() if kind and kind.group(1).lower() in CALLOUTS else 'note'
            out.append(f'<aside class="callout {cls}">{inline(text)}</aside>')
            continue
        if '|' in line and i + 1 < len(lines) and re.fullmatch(r'\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*', lines[i + 1]):
            head = _cells(line)
            i += 2
            rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            th = ''.join(f'<th>{inline(c)}</th>' for c in head)
            tr = ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>' for r in rows)
            out.append(f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')
            continue
        if re.match(r'^\s*([-*]|\d+[.)])\s+', line):
            block, i = parse_list(i, len(line) - len(line.lstrip()))
            out.append(block)
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,4}\s|```|>|\s*([-*]|\d+[.)])\s+|!\[|\||-{3,}$)', lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f'<p>{inline(" ".join(para))}</p>')
    return '\n'.join(out), toc


PAGE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} · User manual</title>
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/manual.css">
<script src="/static/theme.js"></script>
</head>
<body>
<header class="m-top">
  <a class="m-brand" href="/manual">
    <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true"><rect x="1.5" y="1.5" width="29" height="29" rx="7" fill="var(--accent)"/><path d="M7 23 L12 15 L16 19 L25 8" fill="none" stroke="var(--on-accent)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="15" r="1.9" fill="var(--on-accent)"/><circle cx="16" cy="19" r="1.9" fill="var(--on-accent)"/></svg>
    <span class="m-name"><b>{name}</b><small>{author}</small></span>
  </a>
  <span class="m-title">User manual <span class="m-ver">v{version}</span></span>
  <a class="m-back" href="/">← Back to the program</a>
</header>
<div class="m-layout">
  <nav class="m-toc" aria-label="Contents">
    <div class="m-toc-title">Contents</div>
{toc}
  </nav>
  <main class="m-body">
{body}
    <footer class="m-foot">{name} {version} · {author}</footer>
  </main>
</div>
</body>
</html>
'''


def manual_text():
    path = MANUAL_DIR / 'MANUAL.md'
    return path.read_text(encoding='utf-8') if path.is_file() else '# User manual\n\nThe manual file (manual/MANUAL.md) was not found.'


def render_page(md=None):
    body, toc = render_body(manual_text() if md is None else md)
    items = ''.join(f'    <a class="l{lvl}" href="#{hid}">{html.escape(text)}</a>\n' for lvl, hid, text in toc)
    return PAGE.format(name=NAME, author=AUTHOR, version=__version__, toc=items.rstrip('\n'), body=body)


def png_size(path):
    """(width, height) of a PNG in pixels, read from its header; None if it is not a readable PNG."""
    try:
        with open(path, 'rb') as fh:
            head = fh.read(24)
        if head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR':
            return struct.unpack('>II', head[16:24])
    except OSError:
        pass
    return None


def image_path(name):
    """The file for /manual/img/<name>, or None (names with folders or odd characters are refused)."""
    if not re.fullmatch(r'[\w.\-]+\.(png|jpg|svg)', name):
        return None
    path = MANUAL_DIR / 'img' / name
    return path if path.is_file() else None
