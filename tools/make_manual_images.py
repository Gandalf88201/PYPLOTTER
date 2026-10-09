#!/usr/bin/env python3
"""Redraws the pictures of the user manual (manual/img/*.png) from the running program.

Run it after the interface or the analyses change, so that the manual shows what the program really looks like:

    pip install playwright            # development only; the system Chrome is used, no browser download
    .venv/bin/python tools/make_manual_images.py            # all pictures
    .venv/bin/python tools/make_manual_images.py --only window,fit_result

It starts its own π-plotter service (temporary state folder, so your plugins and modules are untouched),
drives it in a headless Chrome with the English interface in the light theme, and saves the screenshots.
Data: the built-in examples plus two small files written here (a correlated series, a semicolon CSV).
Add a picture by writing a function with @shot('name') and referring to img/name.png in manual/MANUAL.md.
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'manual' / 'img'
SHOTS = {}
VIEWPORT = {'width': 1500, 'height': 940}


def shot(name):
    def deco(fn):
        SHOTS[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------------------------- service
def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Service:
    def __init__(self, tmp, python):
        self.port = free_port()
        env = dict(os.environ, PIPLOTTER_HOME=str(tmp / 'home'), PIPLOTTER_NO_VENV='1')
        self.proc = subprocess.Popen([python, str(ROOT / 'start_piplotter.py'), '--no-browser', '--offline',
                                      '--port', str(self.port)], cwd=ROOT, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.url = f'http://127.0.0.1:{self.port}/'
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url, timeout=1).read()
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError('the π-plotter service did not start')

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def write_data(folder):
    """Two small files for the manual: a correlated series with a start-up drift, and a semicolon CSV."""
    rng = np.random.default_rng(7)
    n = 3000
    t = np.arange(n) * 0.002                                  # ps
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.93 * noise[i - 1] + rng.normal(0, 0.35)
    energy = -1520 + 18 * np.exp(-t / 0.35) + noise
    pd.DataFrame({'Time (ps)': t, 'Potential energy (kJ/mol)': energy}).to_csv(folder / 'md_energy.csv', index=False)
    for k, (amp, tau) in enumerate([(1.0, 12.0), (0.8, 18.0)], 1):
        tt = np.linspace(0, 60, 31)
        pd.DataFrame({'Time (min)': tt, 'Signal (a.u.)': amp * np.exp(-tt / tau) + rng.normal(0, 0.02, tt.size)}).to_csv(
            folder / f'run{k}.csv', index=False)
    (folder / 'misure_italiane.csv').write_text(
        '# Misure di laboratorio\nTempo (s);Temperatura (°C);Errore\n' + '\n'.join(
            f'{i * 10};{20 + 0.8 * i:.1f}'.replace('.', ',') + f';{0.2 + 0.01 * i:.2f}'.replace('.', ',') for i in range(15)),
        encoding='utf-8')


# ---------------------------------------------------------------------------------------------- helpers
class UI:
    def __init__(self, pg):
        self.pg = pg

    def wait_idle(self, extra=700):
        self.pg.wait_for_function('!document.querySelector("#spinner") || document.querySelector("#spinner").hidden', timeout=60000)
        self.pg.wait_for_timeout(extra)

    def fresh(self, sample=None, kind=None, width=VIEWPORT['width'], height=VIEWPORT['height']):
        pg = self.pg
        pg.set_viewport_size({'width': width, 'height': height})
        pg.goto(self.url)
        pg.wait_for_selector('#app:not([hidden])', timeout=30000)
        if sample:
            pg.click(f'[data-sample="{sample}"]')
            pg.wait_for_selector('#figureBox:not([hidden])', timeout=60000)
            self.wait_idle()
        if kind:
            self.kind(kind)

    def choose(self, selector, text):
        """Select the option whose label contains text (and tell the page)."""
        ok = self.pg.evaluate("""([sel, text]) => { const el = document.querySelector(sel);
            const o = [...el.options].find(o => o.textContent.includes(text)); if (!o) return false;
            el.value = o.value; el.dispatchEvent(new Event('change', { bubbles: true })); return true; }""", [selector, text])
        if not ok:
            raise RuntimeError(f'{selector}: no option containing {text!r}')

    def map(self, x=None, y=None, yerr=None, hue=None):
        """Variables card: x / hue / yerr by visible name; y = the list of columns to tick (all others are cleared)."""
        pg = self.pg
        for selector, text in (('#mapX', x), ('#mapYerr', yerr), ('#mapHue', hue)):
            if text:
                self.choose(selector, text)
        if y is not None:
            pg.evaluate("""names => { for (const l of document.querySelectorAll('#mapY label')) {
                const cb = l.querySelector('input'); const want = names.some(n => l.textContent.includes(n));
                if (cb.checked !== want) cb.click(); } }""", y)
        self.wait_idle()

    def kind(self, name):
        self.pg.click(f'#kindGallery [data-kind="{name}"]')
        self.wait_idle()

    def upload(self, path):
        self.pg.set_input_files('#fileInput', str(path))
        self.pg.wait_for_selector('#figureBox:not([hidden])', timeout=60000)
        self.wait_idle()

    def analysis(self, pid, **params):
        pg = self.pg
        pg.select_option('#anSelect', pid)
        pg.wait_for_selector('#anMain .an-form', timeout=10000)
        for key, value in params.items():
            field = pg.locator(f'#anMain [data-param="{key}"]')
            sel = field.locator('select')
            if sel.count():
                ok = sel.first.evaluate("""(el, v) => { const o = [...el.options].find(o => o.value === v) || [...el.options].find(o => o.textContent.includes(v));
                    if (!o) return false; el.value = o.value; el.dispatchEvent(new Event('change', { bubbles: true })); return true; }""", str(value))
                if not ok:
                    raise RuntimeError(f'{pid}.{key}: no option {value!r}')
            else:
                box = field.locator('input[type=text],input[type=number],textarea')
                if box.count():
                    box.first.fill(str(value))
                    box.first.dispatch_event('change')
                else:
                    cb = field.locator('input[type=checkbox]').first
                    cb.set_checked(bool(value))
        self.pg.wait_for_timeout(300)

    def run(self, wait=1800):
        self.pg.click('#anMain .an-actions .btn.primary >> nth=0')
        self.pg.wait_for_selector('#anResults .an-actions, #anResults .tbl, #anResults .error-box', timeout=90000)
        self.pg.wait_for_timeout(wait)

    def overlay(self, wait=2500):
        self.pg.click('#anResults .an-actions .btn.small.primary >> nth=0')
        self.wait_idle(wait)

    def shot(self, name, target=None, pad=0, clip=None):
        if name.endswith('_result'):               # the results panel is only 330 px wide on screen: draw it wider so no table is cut
            self.pg.add_style_tag(content='.layout { grid-template-columns: 300px minmax(0, 1fr) 780px !important; } '
                                          '.an-results .tbl { max-height: none !important; }')
            self.pg.wait_for_timeout(500)
            try:
                return self._shot(name, target, pad, clip)
            finally:
                self.pg.evaluate("document.querySelectorAll('style').forEach(s => { if (s.textContent.includes('780px !important')) s.remove(); })")
        return self._shot(name, target, pad, clip)

    def _shot(self, name, target=None, pad=0, clip=None):
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f'{name}.png'
        if clip:
            self.pg.screenshot(path=str(path), clip=clip)
        elif target is None:
            self.pg.screenshot(path=str(path))
        else:
            box = self.pg.locator(target).first.bounding_box()
            self.pg.screenshot(path=str(path), clip={'x': max(0, box['x'] - pad), 'y': max(0, box['y'] - pad),
                                                     'width': box['width'] + 2 * pad, 'height': box['height'] + 2 * pad})
        print('  ', path.relative_to(ROOT))

    def shot_between(self, name, first, last, pad=6):
        """From the top of one element to the bottom of another (same column), as one picture."""
        a = self.pg.locator(first).first.bounding_box()
        b = self.pg.locator(last).first.bounding_box()
        self.shot(name, clip={'x': max(0, a['x'] - pad), 'y': max(0, a['y'] - pad), 'width': a['width'] + 2 * pad,
                              'height': b['y'] + b['height'] - a['y'] + 2 * pad})

    def badges(self, items):
        """Numbered circles drawn on the page: [(css selector, number, 'tl'|'tr'|'l'|'r'), ...]."""
        self.pg.evaluate("""items => { for (const [sel, n, where] of items) {
            const el = document.querySelector(sel); if (!el) continue;
            const r = el.getBoundingClientRect(); const b = document.createElement('div');
            b.textContent = n; b.className = 'manual-badge';
            const x = where.includes('r') ? r.right - 14 : r.left + 4, y = where.includes('b') ? r.bottom - 14 : r.top - 8;
            b.style.cssText = `position:fixed;z-index:99999;left:${x}px;top:${y}px;width:26px;height:26px;border-radius:50%;
              background:#d9480f;color:#fff;font:700 14px/26px system-ui;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.4);
              border:2px solid #fff`;
            document.body.append(b); } }""", items)

    def clear_badges(self):
        self.pg.evaluate("document.querySelectorAll('.manual-badge').forEach(e => e.remove())")

    def collapse(self, selector):
        self.pg.evaluate("s => document.querySelectorAll(s).forEach(d => d.open = false)", selector)

    def expand(self, selector):
        self.pg.evaluate("s => document.querySelectorAll(s).forEach(d => d.open = true)", selector)

    def scroll_top(self):
        self.pg.evaluate("document.querySelectorAll('.panel').forEach(p => p.scrollTop = 0)")


# ---------------------------------------------------------------------------------------------- pictures
@shot('window')
def _(ui):
    ui.fresh('spectra')
    ui.collapse('#analysisCard')
    ui.badges([('.panel.left', 1, 'tl'), ('#mappingCard', 2, 'tl'), ('#kindGallery', 3, 'tl'), ('.stage-wrap', 4, 'tl'),
               ('#analysisCard', 5, 'tl'), ('.export-card', 6, 'tl'), ('#stylePanel > details:nth-of-type(2)', 7, 'tl')])
    ui.shot('window')


TALL = {'width': 1500, 'height': 2300}


def tall(ui):
    ui.pg.set_viewport_size(TALL)
    ui.pg.wait_for_timeout(600)


def normal(ui):
    ui.pg.set_viewport_size(VIEWPORT)
    ui.pg.wait_for_timeout(900)


@shot('data_panel')
def _(ui):
    ui.fresh('spectra')
    ui.shot_between('data_panel', '.panel.left .card', '#mappingCard')


@shot('import_options')
def _(ui):
    ui.fresh()
    ui.upload(ui.tmp / 'misure_italiane.csv')
    ui.pg.click('#importOptions summary')
    ui.pg.wait_for_timeout(300)
    ui.shot_between('import_options', '.panel.left .card', '#mappingCard')


@shot('variables')
def _(ui):
    ui.fresh('kinetics')
    ui.shot('variables', '#mappingCard', pad=6)


@shot('plot_types')
def _(ui):
    ui.fresh('spectra', width=2400)
    ui.shot('plot_types', '#kindGallery', pad=4)


@shot('export_card')
def _(ui):
    ui.fresh('spectra')
    ui.collapse('#analysisCard')
    ui.pg.select_option('#exportFormat', index=0)
    ui.wait_idle(400)
    ui.shot('export_card', '.export-card', pad=6)


@shot('data_table')
def _(ui):
    ui.fresh('kinetics')
    ui.pg.click('.tab[data-tab="table"]')
    ui.pg.wait_for_timeout(800)
    ui.shot('data_table', '.stage-wrap')


@shot('style_panel')
def _(ui):
    ui.fresh('spectra')
    tall(ui)
    ui.collapse('#analysisCard')
    ui.collapse('#seriesCard')
    ui.scroll_top()
    ui.shot_between('style_basic', '.export-card', '#stylePanel > details:nth-of-type(3)')
    ui.expand('#seriesCard')
    ui.shot('style_series', '#seriesCard', pad=4)


@shot('style_text_axes')
def _(ui):
    ui.fresh('spectra')
    tall(ui)
    ui.collapse('#stylePanel details')
    for title in ('Text & fonts', 'Axes & ticks', 'Legend'):
        ui.pg.evaluate("t => [...document.querySelectorAll('#stylePanel details')].find(d => d.querySelector('summary').textContent.includes(t)).open = true", title)
    ui.scroll_top()
    card = lambda t: f'#stylePanel details:has(> summary:has-text("{t}"))'
    ui.shot('style_text', card('Text & fonts'), pad=4)
    ui.shot_between('style_axes', card('Axes & ticks'), card('Legend'), pad=4)


@shot('zoom')
def _(ui):
    ui.fresh('spectra')
    box = ui.pg.locator('#figure').bounding_box()
    x0, y0 = box['x'] + box['width'] * 0.30, box['y'] + box['height'] * 0.12
    x1, y1 = box['x'] + box['width'] * 0.62, box['y'] + box['height'] * 0.78
    ui.pg.mouse.move(x0, y0)
    ui.pg.mouse.down()
    ui.pg.mouse.move((x0 + x1) / 2, (y0 + y1) / 2, steps=6)
    ui.pg.screenshot(path=str(OUT / 'zoom_box.png'), clip={'x': box['x'] - 20, 'y': box['y'] - 20, 'width': box['width'] + 40, 'height': box['height'] + 40})
    ui.pg.mouse.move(x1, y1, steps=6)
    ui.pg.screenshot(path=str(OUT / 'zoom_box.png'), clip={'x': box['x'] - 20, 'y': box['y'] - 20, 'width': box['width'] + 40, 'height': box['height'] + 40})
    ui.pg.mouse.up()
    ui.wait_idle(1500)
    ui.shot('zoom_done', '.stage-wrap')


@shot('analysis_list')
def _(ui):
    ui.fresh('spectra')
    tall(ui)
    ui.pg.evaluate("""() => {                      // a native <select> cannot be photographed open: draw its list
        const sel = document.querySelector('#anSelect'); const box = document.createElement('div');
        box.style.cssText = 'border:1px solid var(--border-strong);border-radius:8px;padding:6px 0;background:var(--panel);font-size:13px;max-height:none';
        for (const el of sel.querySelectorAll('optgroup, option')) {
          const d = document.createElement('div');
          if (el.tagName === 'OPTGROUP') { d.textContent = el.label; d.style.cssText = 'padding:5px 10px 2px;font-weight:700;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em'; }
          else { d.textContent = el.textContent; d.style.cssText = 'padding:2px 10px 2px 18px'; if (el.value === sel.value) d.style.background = 'var(--accent-soft)'; }
          box.append(d);
        }
        sel.style.display = 'none'; sel.after(box); }""")
    ui.pg.evaluate("document.querySelector('.panel.right').scrollTop = 0")
    ui.shot('analysis_list', '#analysisCard', pad=4)



@shot('fit')
def _(ui):
    ui.fresh('kinetics')
    ui.kind('errorbar')
    ui.map(y=['Concentration'], yerr='Std. dev.')
    tall(ui)
    ui.analysis('fit_curve', sigma='Std. dev. (mM)', model='y = A·exp(−x/τ) + C')
    ui.shot_between('fit_form', '#anBody .field', '#anMain .an-actions', pad=4)
    ui.run()
    ui.shot('fit_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('fit_figure', '.stage-wrap')


@shot('recipe_kinetics')
def _(ui):
    ui.fresh('kinetics')
    ui.kind('errorbar')
    ui.map(y=['Concentration'], yerr='Std. dev.')
    tall(ui)
    ui.analysis('recipe_kinetics')
    ui.run(3000)
    ui.shot('recipe_kinetics_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('recipe_kinetics_figure', '.stage-wrap')


@shot('baseline')
def _(ui):
    ui.fresh('ir', kind='line')
    tall(ui)
    ui.analysis('baseline', baseline='arpls')
    ui.shot_between('baseline_form', '#anBody .field', '#anMain .an-actions', pad=4)
    ui.run()
    ui.overlay()
    normal(ui)
    ui.shot('baseline_figure', '.stage-wrap')


@shot('peaks')
def _(ui):
    ui.fresh('spectra', kind='line')
    ui.pg.evaluate("() => { for (const l of document.querySelectorAll('#mapY label')) { if (/Sample [BC]/.test(l.textContent)) l.querySelector('input').click(); } }")
    ui.wait_idle()
    tall(ui)
    ui.analysis('peaks', y='Sample A')
    ui.run()
    ui.shot('peaks_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('peaks_figure', '.stage-wrap')


@shot('peak_fit')
def _(ui):
    ui.fresh('spectra', kind='line')
    ui.pg.evaluate("() => { for (const l of document.querySelectorAll('#mapY label')) { if (/Sample [BC]/.test(l.textContent)) l.querySelector('input').click(); } }")
    ui.wait_idle()
    tall(ui)
    ui.analysis('recipe_peak_fit', y='Sample A')
    ui.run(3500)
    ui.shot('peak_fit_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('peak_fit_figure', '.stage-wrap')


@shot('ir')
def _(ui):
    ui.fresh('ir', kind='line')
    tall(ui)
    ui.analysis('ir_assign')
    ui.run(3500)
    ui.shot('ir_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('ir_figure', '.stage-wrap')


@shot('series')
def _(ui):
    ui.fresh()
    ui.upload(ui.tmp / 'md_energy.csv')
    tall(ui)
    ui.analysis('recipe_equilibration')
    ui.run(3500)
    ui.shot('equilibration_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('equilibration_figure', '.stage-wrap')


@shot('autocorrelation')
def _(ui):
    ui.fresh()
    ui.upload(ui.tmp / 'md_energy.csv')
    tall(ui)
    ui.analysis('autocorrelation')
    ui.run(3000)
    ui.shot('acf_result', '#anResults', pad=4)
    ui.pg.click('#anResults .an-actions .btn.small >> nth=-1') if False else None
    ui.overlay()
    normal(ui)
    ui.shot('acf_figure', '.stage-wrap')


@shot('groups')
def _(ui):
    ui.fresh('groups', kind='box')
    tall(ui)
    ui.analysis('recipe_compare_groups')
    ui.run(3500)
    ui.shot('groups_result', '#anResults', pad=4)
    normal(ui)
    ui.shot('groups_figure', '.stage-wrap')


@shot('xy')
def _(ui):
    ui.fresh('cloud', kind='scatter')
    ui.map(x='x', y=['y'])
    tall(ui)
    ui.analysis('recipe_xy_relation')
    ui.run(3500)
    ui.shot('xy_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('xy_figure', '.stage-wrap')


@shot('gaussian')
def _(ui):
    ui.fresh('cloud', kind='hist')
    tall(ui)
    ui.analysis('recipe_gaussian', y='x')
    ui.run(3500)
    ui.shot('gaussian_result', '#anResults', pad=4)
    ui.overlay()
    normal(ui)
    ui.shot('gaussian_figure', '.stage-wrap')


@shot('surface3d')
def _(ui):
    ui.fresh('surface', kind='surface3d')
    ui.shot('surface3d', '.stage-wrap')


@shot('combine')
def _(ui):
    ui.fresh()
    ui.pg.set_input_files('#fileInput', [str(ui.tmp / 'run1.csv'), str(ui.tmp / 'run2.csv')])
    ui.pg.wait_for_selector('#figureBox:not([hidden])', timeout=60000)
    ui.wait_idle(1500)
    ui.shot('combine_panel', '.panel.left', pad=6)
    ui.pg.click('[data-layout="panels"]')
    ui.wait_idle(1500)
    ui.shot('combine_figure', '.stage-wrap')


@shot('dialogs')
def _(ui):
    ui.fresh('spectra', height=1500)
    ui.pg.click('#btnModules')
    ui.pg.wait_for_timeout(2500)
    ui.shot('modules_dialog', '#modulesDialog', pad=0)
    ui.pg.keyboard.press('Escape')
    ui.pg.click('#btnAbout')
    ui.pg.wait_for_timeout(800)
    ui.shot('about_dialog', '#aboutDialog', pad=0)
    ui.pg.keyboard.press('Escape')
    ui.pg.select_option('#anSelect', 'fit_curve')
    ui.pg.once('dialog', lambda d: d.accept('my analysis'))      # the name is asked with a browser prompt
    ui.pg.click('#btnNewPlugin')
    ui.pg.wait_for_selector('#pluginDialog[open]', timeout=15000)
    ui.pg.wait_for_timeout(600)
    ui.pg.evaluate("document.querySelector('#pluginPath').textContent = document.querySelector('#pluginPath').textContent.replace(/\\/[^ ]*\\/plugins/, '~/.piplotter/plugins')")
    ui.shot('plugin_editor', '#pluginDialog', pad=0)



def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', help='comma-separated picture names')
    ap.add_argument('--python', default=str(ROOT / '.venv' / 'bin' / 'python') if (ROOT / '.venv' / 'bin' / 'python').exists() else sys.executable,
                    help='Python that runs the π-plotter service (default: the project .venv)')
    args = ap.parse_args()
    names = [n for n in (args.only.split(',') if args.only else SHOTS) if n]
    unknown = [n for n in names if n not in SHOTS]
    if unknown:
        sys.exit(f'Unknown pictures: {", ".join(unknown)}. Available: {", ".join(SHOTS)}')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('This tool needs Playwright (development only): pip install playwright')
    with tempfile.TemporaryDirectory(prefix='piplotter-manual-') as tmp:
        tmp = Path(tmp)
        write_data(tmp)
        service = Service(tmp, args.python)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='chrome', headless=True)
                ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2, locale='en-US', bypass_csp=True)
                ctx.add_init_script("try { localStorage.setItem('pp-lang', '\"en\"'); localStorage.setItem('pp-theme', 'light'); } catch (e) {}")
                failed = []
                for name in names:
                    print(name)
                    pg = ctx.new_page()
                    ui = UI(pg)
                    ui.url, ui.tmp = service.url, tmp
                    try:
                        SHOTS[name](ui)
                    except Exception as exc:                       # keep going: one broken picture should not stop the rest
                        failed.append(name)
                        debug = Path(tempfile.gettempdir()) / f'piplotter-manual-failed-{name}.png'
                        try:
                            pg.screenshot(path=str(debug))
                        except Exception:
                            pass
                        print(f'   FAILED: {str(exc).splitlines()[0]} (screenshot of the page: {debug})')
                    finally:
                        pg.close()
                browser.close()
                if failed:
                    print('Failed:', ', '.join(failed))
        finally:
            service.stop()


if __name__ == '__main__':
    main()
