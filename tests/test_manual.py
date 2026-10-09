"""The built-in manual, the name π-plotter and its signature, and the move of ~/.pyplotter."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import piplotter  # noqa: E402
from piplotter import manual  # noqa: E402


class TestManualReader(unittest.TestCase):
    def test_blocks(self):
        body, toc = manual.render_body(
            '# Title\n\n## First part\n\nText with **bold**, *italic*, `code <b>` and [a link](#first-part).\n\n'
            '- one\n  - nested\n- two\n\n1. step\n2. step\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n'
            '> **Warning:** careful\n\n```\nx = 1 < 2\n```\n\n### Sub\n')
        self.assertIn('<h1 id="title">Title</h1>', body)
        self.assertIn('<h2 id="first-part">', body)
        self.assertEqual([(2, 'first-part', 'First part'), (3, 'sub', 'Sub')], toc)
        self.assertIn('<strong>bold</strong>', body)
        self.assertIn('<em>italic</em>', body)
        self.assertIn('<code>code &lt;b&gt;</code>', body)
        self.assertIn('<a href="#first-part">a link</a>', body)
        self.assertIn('<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul>', body)
        self.assertIn('<ol><li>step</li><li>step</li></ol>', body)
        self.assertIn('<th>a</th>', body)
        self.assertIn('<aside class="callout warning">', body)
        self.assertIn('x = 1 &lt; 2', body)

    def test_nothing_from_the_text_becomes_markup(self):
        body, _ = manual.render_body('Plain <script>alert(1)</script> text and [bad](javascript:alert(1)) '
                                     'and ![x](http://evil/x.png)\n')
        self.assertNotIn('<script>', body)
        self.assertNotIn('href="javascript', body)
        self.assertNotIn('<img', body)                  # only pictures of the manual folder are shown
        self.assertIn('&lt;script&gt;', body)

    def test_picture_and_caption(self):
        body, _ = manual.render_body('![alt text](img/window.png "A long caption")\n')
        self.assertIn('<figcaption>A long caption</figcaption>', body)
        self.assertIn('src="/manual/img/window.png"', body)

    def test_page_has_name_and_signature(self):
        page = manual.render_page('# T\n\n## A\n\ntext\n')
        self.assertIn('π-plotter', page)
        self.assertIn('Dr. T. Francese', page)
        self.assertIn(f'v{piplotter.__version__}', page)
        self.assertIn('href="#a"', page)


class TestManualFile(unittest.TestCase):
    def setUp(self):
        self.text = (manual.MANUAL_DIR / 'MANUAL.md').read_text(encoding='utf-8')
        self.prose = re.sub(r'`[^`\n]*`', '', self.text)         # an example of the syntax in `code` is not a picture

    def test_every_picture_exists(self):
        names = set(re.findall(r'!\[[^\]]*\]\(img/([\w.\-]+)', self.prose))
        self.assertGreater(len(names), 20)
        missing = sorted(n for n in names if manual.image_path(n) is None)
        self.assertEqual([], missing)

    def test_every_picture_is_used_and_is_a_png_of_a_sensible_size(self):
        used = set(re.findall(r'\(img/([\w.\-]+)', self.prose))
        for path in (manual.MANUAL_DIR / 'img').glob('*.png'):
            if path.name.startswith('._'):
                continue
            self.assertIn(path.name, used, f'{path.name} is not used in MANUAL.md')
            w, h = manual.png_size(path)
            self.assertTrue(200 < w < 4000 and 100 < h < 4000, (path.name, w, h))

    def test_inner_links_point_to_headings(self):
        body, toc = manual.render_body(self.text)
        ids = set(re.findall(r'<h[1-4] id="([^"]+)"', body))
        for target in re.findall(r'href="#([^"]+)"', body):
            if target not in {'#'}:
                self.assertIn(target, ids)

    def test_the_whole_manual_renders(self):
        page = manual.render_page()
        self.assertIn('Revision history', page)
        self.assertGreater(page.count('<figure>'), 20)

    def test_image_names_are_checked(self):
        self.assertIsNone(manual.image_path('../MANUAL.md'))
        self.assertIsNone(manual.image_path('a/b.png'))
        self.assertIsNone(manual.image_path('missing.png'))


class TestServedManual(unittest.TestCase):
    def test_pages(self):
        from piplotter import server
        with tempfile.TemporaryDirectory() as tmp:
            httpd, app, url = server.serve(0, 't' * 32, tmp, open_browser=False, online=False, quiet=True)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                page = urllib.request.urlopen(url + 'manual').read().decode('utf-8')
                self.assertIn('User manual', page)
                self.assertIn('Dr. T. Francese', page)
                img = urllib.request.urlopen(url + 'manual/img/window.png')
                self.assertEqual('image/png', img.headers['Content-Type'])
                self.assertTrue(img.read().startswith(b'\x89PNG'))
                for bad in ('manual/img/..%2FMANUAL.md', 'manual/img/nope.png', 'manual/img/'):
                    with self.assertRaises(urllib.error.HTTPError) as cm:
                        urllib.request.urlopen(url + bad)
                    self.assertEqual(404, cm.exception.code, bad)
                index = urllib.request.urlopen(url).read().decode('utf-8')
                self.assertIn('<title>π-plotter · Dr. T. Francese</title>', index)
                self.assertIn('class="brand-author">Dr. T. Francese<', index)
                self.assertIn('href="/manual"', index)
                self.assertIn('/static/manual.css', page)
                self.assertEqual(200, urllib.request.urlopen(url + 'static/manual.css').status)
            finally:
                httpd.shutdown()
                httpd.server_close()


class TestRename(unittest.TestCase):
    def test_old_import_name_still_works(self):
        """Plugins saved before the rename say "from pyplotter import baselines"."""
        code = 'import piplotter; from pyplotter import baselines; print(baselines.METHODS[0])'
        out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual('points', out.stdout.strip())

    def test_state_folder_is_moved_once(self):
        with tempfile.TemporaryDirectory() as home:
            old = Path(home) / '.pyplotter'
            (old / 'plugins').mkdir(parents=True)
            (old / 'plugins' / 'mine.py').write_text('X = 1\n', encoding='utf-8')
            (old / 'user-modules.json').write_text('{"schema": "pyplotter-user-modules/1", "modules": []}', encoding='utf-8')
            (old / 'pypi-cache.json').write_text('{}', encoding='utf-8')
            code = 'import piplotter; print(piplotter.home_dir())'
            env = {k: v for k, v in os.environ.items() if k != 'PIPLOTTER_HOME'}
            env.update(HOME=home, USERPROFILE=home)
            out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(0, out.returncode, out.stderr)
            new = Path(out.stdout.strip())
            self.assertEqual(Path(home) / '.piplotter', new)
            self.assertEqual('X = 1\n', (new / 'plugins' / 'mine.py').read_text(encoding='utf-8'))
            self.assertTrue((new / 'user-modules.json').is_file())
            self.assertFalse((new / 'pypi-cache.json').exists())          # a cache is not worth moving
            self.assertTrue((old / 'plugins' / 'mine.py').is_file())      # the old folder is left alone
            (new / 'plugins' / 'mine.py').write_text('X = 2\n', encoding='utf-8')
            subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual('X = 2\n', (new / 'plugins' / 'mine.py').read_text(encoding='utf-8'))   # not copied again

    def test_old_user_module_list_is_still_read(self):
        from piplotter.modules import ModuleManager
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'user-modules.json').write_text(
                '{"schema": "pyplotter-user-modules/1", "modules": [{"pip": "uvvispy", "license": "MIT"}]}', encoding='utf-8')
            mm = ModuleManager(state_dir=tmp, online=False)
            self.assertIn('uvvispy', mm.user)

    def test_no_old_name_is_left_in_the_program(self):
        allowed = {'__init__.py', 'test_manual.py', 'modules.py', 'app.js', 'RELEASE_NOTES.md'}
        bad = []
        for folder in ('piplotter', 'web', 'tests', 'tools'):
            for path in (ROOT / folder).rglob('*'):
                if path.is_file() and not path.name.startswith('._') and path.suffix in {'.py', '.js', '.html', '.css', '.json'} \
                        and path.name not in allowed and re.search(r'pyplotter', path.read_text(encoding='utf-8'), re.I):
                    bad.append(str(path.relative_to(ROOT)))
        self.assertEqual([], bad)


if __name__ == '__main__':
    unittest.main()
