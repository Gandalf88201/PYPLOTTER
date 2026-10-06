# Writing PyPlotter analysis plugins / Scrivere plugin di analisi

*Italiano più sotto.*

Every analysis in the **Analysis** panel is a plugin: one Python file with a `PLUGIN` dictionary and
a `run(df, p, ctx)` function. The built-in ones live in `pyplotter/analyses/`; yours live in your
**plugins folder** (`~/.pyplotter/plugins/`, or the folder in the environment variable
`PYPLOTTER_PLUGINS`). That folder is outside the program, so updating PyPlotter never touches it.

## Three ways to start

- **New plugin** (Analysis panel) creates a working example from a template and opens the editor.
- **Customise…** on any built-in analysis copies it into your folder. A user plugin with the same
  `id` as a built-in one **replaces** it — this is how you change a statistical method. Disable or
  delete your copy to go back to the original.
- Write a `.py` file in the plugins folder with any editor, then press ⟳ (reload).

Save in the in-app editor with **Save & reload** (or Ctrl/⌘+S). Loading errors are shown with the
line number; errors while running show the file and line too.

## Anatomy

```python
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'my_fit',                                    # unique, lower case; same id as a built-in = replace it
    'name': {'en': 'My fit', 'it': 'Il mio fit'},
    'category': 'fit',                                 # fit | timeseries | stats | signal | custom
    'description': {'en': '…', 'it': '…'},
    'requires': ['scipy'],                             # module ids from pyplotter/registry.json, installed on demand
    'params': [                                        # the form is generated from this list
        {'id': 'x', 'type': 'column', 'default': 'x', 'label': {'en': 'X', 'it': 'X'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Y', 'it': 'Y'}},
        {'id': 'n', 'type': 'int', 'default': 3, 'min': 1, 'label': 'Degree'},
    ],
    'references': ['Author, A. Title. Journal 1, 1–10 (2020). doi:…'],
}


def run(df, p, ctx):
    x, y = ctx.xy(df, p['x'], p['y'])                  # paired numeric arrays without NaN
    coef = np.polyfit(x, y, p['n'])
    r = ctx.result()
    r.value('R²', 0.99)                                # summary line: label, value, error=None, unit=''
    r.table('Coefficients', pd.DataFrame({'c': coef}))
    r.text('Any comment')
    r.data(pd.DataFrame({'x': x, 'y': y, 'fit': np.polyval(coef, x)}),
           plot={'kind': 'line', 'x': 'x', 'y': ['y', 'fit'],
                 'series': {'y': {'linestyle': 'none', 'marker': 'o'}}})
    r.cite('Extra reference shown with this result')
    return r
```

### Parameter types

| type | value passed to `run` | options |
|---|---|---|
| `column` | a column name (or `None` if `optional`) | `default` may be a **role**: `x`, `y`, `y2`, `xerr`, `yerr`, `hue`, `z` = the column used in the current figure |
| `columns` | list of column names | `default: 'ys'` (the figure's Y columns) or `'xs'`; `min_count` |
| `int`, `float` | number (or `None` if `optional` and empty) | `min`, `max` |
| `bool` | `True` / `False` | |
| `choice` | the chosen `value` | `choices: [{'value': 'a', 'label': {'en': …, 'it': …}}, …]` |
| `text` | string | — |

Every parameter takes `label` and optional `help` (a string or `{'en': …, 'it': …}`).
`show_if: {'model': ['custom']}` shows a parameter only when another parameter has one of the
listed values (the custom-formula field of *Curve fitting* uses it).

Analyses live in the **Analysis** panel of the right sidebar, above *Export*: the figure stays open,
the numbers stay in the panel, and every overlay a result provides (`r.overlay`) is drawn on a **copy
of the figure** in its own tab (closed with ×) as soon as the analysis runs — the original figure is
never changed. Running the analysis again replaces its layers on that copy.

### The `ctx` helper

- `ctx.result()` → the result builder (`value`, `table`, `text`, `data`, `cite`).
- `ctx.xy(df, x, y)` → numeric arrays; `x=None` means the row number. Dates become seconds.
- `ctx.numeric(df, column, dropna=True)` → a numeric pandas Series.
- `ctx.tr(en, it)` → the text in the interface language; `ctx.lang` is `'en'` or `'it'`.
- `ctx.spec` → the current figure settings (read only).

`r.data(frame, plot=…)` creates a **new data set**: *Plot the result* opens it (automatically when the result has no overlay) as a figure in its own tab that you
can style and export like any file; the "Python script" export then carries the analysis name,
parameters (`provenance.json`) and references (`REFERENCES.txt`). `plot` uses the same keys as a
figure: `kind`, `x`, `y`, `y2`, `yerr`, `series`, `text`, `axes`, `style`. Use the label
`'_nolegend_'` to hide a series from the legend.

`r.overlay(frame, x, y, lo=None, hi=None, label=None, band_label=None, style=None)` adds a **layer
that is drawn on a copy of the original figure** (*Show on a copy of the figure*): the curve `x → y` and, if
`lo`/`hi` are given, a shaded error band (e.g. the 95 % confidence band of a fit). Use the same x
units as the analysed data. It returns an index that `r.data(..., plot={'overlays': [{'ref': i}]})`
can use to draw the layer on the result figure too. The user can recolour, relabel, hide or remove
each layer under **Overlays**; layers are exported with the figure and rebuilt after a restart.

Raise `ValueError('message')` for problems the user should fix; the message is shown as is.

> A **customised copy** of a built-in analysis is yours: later PyPlotter updates do not change it.
> To get the new version of a built-in analysis, disable your copy (or customise it again after
> renaming the old one).

### Recipes: ready-made paths of several analyses

A **recipe** (category `'recipe'`, listed first under *Recipes*) runs several analyses in a row and
reports the answer in plain words, e.g. *Gaussian distribution of a column* = histogram → Gaussian
fit → normality tests → block averaging. It is an ordinary plugin with two extras:

- `ctx.run('analysis_id', df, **params)` runs another analysis on any DataFrame and returns its
  result. The **built-in** version is always used, so your customised copies never change what a
  recipe computes.
- `res.get('key')` / `res.error('key')` read a number from that result. Analyses publish them with
  `r.value(label, value, error, key='mean')` (shown) or `r.keep('mean', value, error)` (not shown).
  Keys of the built-ins: *fit_curve* — each parameter name (`mu`, `sigma`, `a`, `b`…), `r2`, `rmse`,
  `aic`, `bic`, `bins` (histogram mode); *peaks* — `n_peaks`, `peaks` (list of {position, height,
  prominence, fwhm, left, right});
  *block_average* — `mean`, `sem`, `sem_naive`, `g`, `n_eff`; *autocorrelation* — `tau_int`, `g`,
  `n_eff`; *normality* — `skew`, `kurtosis`, `shapiro_p`, `normal`; *compare_groups* — `test`, `p`,
  `effect`, `significant`, `groups_normal`, `k`; *correlation* (first pair) — `coef`, `p`, `ci_low`,
  `ci_high`, `n`.

`r.include(res, 'Step 2 · fit', overlays=False)` adds a step's tables and references under that title
and returns the index of its first layer; `r.overlay(..., on_figure=False)` (or setting
`r.overlays[i]['on_figure'] = False`) keeps a layer for the result's own plot only, when its x is not
the data's x (a curve over a histogram). `r.overlay(..., text='column')` writes that column's values above the points
(below for marker `'^'`), e.g. peak positions. `'steps': [{'en': …, 'it': …}, …]` in `PLUGIN` lists what the
recipe does; the panel shows it above the form. See `pyplotter/analyses/recipe_*.py`.

### Modules and licences

List every registry module your plugin needs in `requires`; PyPlotter offers to install the missing
ones. To use a package that is not in the registry, add it to `pyplotter/registry.json` with its
licence (open-source only, see THIRD_PARTY_NOTICES.md) and citation. Put the references of the
methods you use in `references`.

### Security

Plugins are ordinary Python code that runs inside the local PyPlotter service with your user
rights. Only install plugins you have read or that come from people you trust.

---

## Italiano

Ogni analisi del riquadro **Analisi** (barra di destra, sopra *Esporta*) è un plugin: un file Python con un dizionario `PLUGIN` e una
funzione `run(df, p, ctx)`. Quelli inclusi stanno in `pyplotter/analyses/`; i tuoi nella **cartella
plugin** (`~/.pyplotter/plugins/`, oppure quella indicata da `PYPLOTTER_PLUGINS`), fuori dal
programma: gli aggiornamenti di PyPlotter non la toccano.

- **Nuovo plugin** crea un esempio funzionante e apre l'editor.
- **Personalizza…** su un'analisi inclusa la copia nella tua cartella: un plugin utente con lo stesso
  `id` **sostituisce** quello incluso. È il modo per modificare un metodo statistico. Disattiva o
  cancella la copia per tornare all'originale.
- Oppure scrivi un file `.py` nella cartella plugin con qualsiasi editor e premi ⟳.

**Salva e ricarica** (o Ctrl/⌘+S) nell'editor interno; gli errori indicano file e riga.

La struttura, i tipi di parametro e l'oggetto `ctx` sono descritti sopra con un esempio completo.
In sintesi: dichiara i parametri in `PLUGIN['params']` (PyPlotter genera il modulo), calcola in
`run`, restituisci `ctx.result()` con valori, tabelle, testo, un eventuale nuovo insieme di dati da
tracciare (`r.data(...)`), eventuali livelli da disegnare su una copia del grafico originale (scheda con ×) con la loro banda
d'errore (`r.overlay(...)`) e i riferimenti da citare. Nota: una **copia personalizzata** di
un'analisi inclusa non riceve gli aggiornamenti successivi di PyPlotter; disattivala per tornare
alla versione aggiornata. Elenca in `requires` i moduli necessari (solo
open source, con licenza e citazione nel registro). Lancia `ValueError('messaggio')` per errori che
l'utente deve correggere.

**Ricette.** Una ricetta (categoria `'recipe'`, prima voce del menu *Ricette*) esegue più analisi in
sequenza e dà la risposta in parole semplici. È un plugin normale con `ctx.run('id', df, **parametri)`,
che esegue un'altra analisi (sempre la versione **inclusa**, così le tue copie personalizzate non
cambiano i risultati di una ricetta) e restituisce il risultato; i numeri si leggono con
`res.get('chiave')` / `res.error('chiave')`, pubblicati dalle analisi con `r.value(..., key='…')` o
`r.keep('…', valore, errore)`. Le chiavi disponibili e `r.include(...)` / `on_figure=False` sono
descritte sopra; `'steps'` in `PLUGIN` elenca i passi mostrati nel riquadro. Esempi:
`pyplotter/analyses/recipe_*.py`.

**Sicurezza:** i plugin sono codice Python che gira con i tuoi permessi; installa solo plugin che
hai letto o di cui ti fidi.
