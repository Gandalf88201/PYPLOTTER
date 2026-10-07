# PyPlotter — next version (draft)

- **Rotate 3D figures with the mouse.** Drag a 3D surface, scatter or waterfall: a light copy of the data
  turns smoothly in the page, with Matplotlib's own projection, panes, grid, ticks and labels. On release
  the elevation and azimuth are kept and the figure is drawn again. Double-click restores the default view.
- *Italiano:* **ruota i grafici 3D col mouse** — trascina la figura: l’anteprima gira in modo fluido con la
  proiezione di Matplotlib; al rilascio gli angoli restano e la figura viene ridisegnata (doppio clic: vista
  predefinita).
- **Zoom with the mouse.** Drag a box on the axes: its corners become the axis limits (the X/Y min/max
  fields) and the figure is drawn again with ticks for the new range. A thin horizontal box zooms x only,
  and y then follows the data in that range (one small band of a spectrum fills the plot). *Previous zoom*,
  *Whole figure* or a double-click go back. Works on every kind with axes (lines, scatter, bars, box and
  violin plots, histograms, heat maps, contours…). **The mouse wheel** zooms around the pointer (Shift: x
  only); on **polar** figures it zooms the radius, on **3D** figures the three ranges (what falls outside is
  clipped). Pie charts and pair plots have no zoom.
- **Move and rewrite every text.** Titles, axis labels, the colour-bar label, the legend, pie slice names
  and shares, pair-plot labels and value labels can be dragged on the figure, on every kind including 3D.
  **Double-click a text to rewrite it** (formulas between `$…$`, e.g. `cm$^{-1}$`): titles and axis labels
  go to their fields in the Text panel, the others are kept with the figure. *Original text* and *Original
  position* undo each one; *Texts back in place* moves them all back. Everything is kept in every export.
- **Peak labels no longer overlap.** A label that would cover another one, a curve or the legend moves up
  or aside, joined to its peak by a thin leader line; the y axis grows to make room above the tallest peak
  unless its limit is fixed. Labels are placed in points, so the preview and the export match.
- *Italiano:* **zoom col mouse** — trascina un riquadro sugli assi: diventano i limiti degli assi e la figura
  viene ridisegnata con le tacche del nuovo intervallo; un riquadro sottile ingrandisce solo x e y segue i dati
  visibili. *Zoom precedente*, *Figura intera* o doppio clic per tornare indietro. Vale per tutti i grafici
  con assi; **la rotella** ingrandisce attorno al puntatore, e nei grafici **polari** (raggio) e **3D** (i tre
  assi). **Ogni testo si sposta trascinandolo e si riscrive con un doppio clic** (titoli, etichette degli
  assi, barra dei colori, legenda, fette della torta, valori dei picchi; formule tra `$…$`) e resta così in
  ogni esportazione. **Le etichette dei picchi non si sovrappongono più**: si spostano in alto o di lato
  con una sottile linea di richiamo verso il picco.

---

# PyPlotter 0.1.2

**3D figures, JCAMP-DX spectra and modules of your choice from PyPI.**
*Italiano più sotto.*

## What's new

### 3D figures
- **3D surface** z(x, y) from X, Y, Z columns: a grid, or scattered points (triangulated). Optionally a
  wire frame only. Colour map, colour bar and colour limits as for contour plots.
- **3D scatter** of X, Y, Z, one colour per series or group, or the points joined by a 3D line.
- **Waterfall** of spectra: each Y column is a curve at its own depth, given by the column name when it
  is a number (a time, a temperature) or by its position.
- View elevation and azimuth, Z limits and a Z label. Interactive HTML export with rotatable 3D (Plotly).

### Files
- **JCAMP-DX** spectra (`.jdx`, `.dx`), plain or compressed (AFFN, PAC, SQZ, DIF, DUP), as exported by
  instruments and the NIST WebBook. A file whose point count does not match its header is refused.

### Your modules from PyPI
- *Modules › Your modules*: type the name of any package on PyPI and press *Check*. pip lists what it
  would install, nothing is changed yet, and every package is shown with its **licence**.
  - Open-source (OSI-approved) packages install normally.
  - A licence that is not OSI-approved, proprietary or not recognised is marked. *Install* stays
    disabled until you tick *“I have read the licence terms…”*.
- Only plain package names are accepted, and the version shown is the version installed.
- Each module you added is listed with:
  - its licence and the packages installed with it;
  - a reference to cite, added to the results of analyses that use it;
  - an *Uninstall* button.
- They are recorded in `~/.pyplotter/user-modules.json`. In a new environment they appear as *not
  installed*, with *Install again*.
- These are third-party code that PyPlotter does not check: install only what you trust.

---

## Italiano

- **Grafici 3D:**
  - superficie z(x, y), da una griglia o da punti sparsi, anche solo come reticolo;
  - dispersione o linea 3D;
  - **cascata** di spettri: una curva per colonna, alla profondità data dal nome della colonna;
  - angoli di vista, limiti e etichetta Z, esportazione HTML interattiva.
- **JCAMP-DX** (`.jdx`, `.dx`), anche compressi.
- **I tuoi moduli da PyPI** (*Moduli › I tuoi moduli*):
  - scrivi il nome di un pacchetto e premi *Controlla*: vedi il pacchetto e ogni dipendenza con la sua
    licenza;
  - una licenza non approvata OSI, proprietaria o non riconosciuta richiede la tua conferma esplicita;
  - per ogni modulo: riferimento da citare e *Disinstalla*;
  - dopo la perdita dell’ambiente, *Installa di nuovo*.
  - Sono codice di terze parti non controllato da PyPlotter.

Licenza MIT · © 2026 Tommaso Francese

---

# PyPlotter 0.1.1

**Baseline first, then the analysis** — and tables with tens of thousands of columns.
*Italiano più sotto.*

## What's new

### Baseline of spectra and signals
- A new **Baseline** analysis (*Analysis › Signal*). **Click anchor points on the figure** where the signal
  lies on its baseline (a readout shows x and y under the cursor), or type them. They are joined by
  straight lines or by a smooth monotone curve (PCHIP). Automatic methods are also available: arPLS,
  asymmetric least squares, SNIP and rubber band.
- The baseline, the anchor points and the corrected signal are drawn on a copy of the figure. A
  warning appears when more than 5 % of the points fall under the baseline.
- **Peak finding**, **Peak fit** and **Integral** offer the baseline you defined, already selected:
  - heights, FWHM and areas are measured above it;
  - each peak's area runs between the minima that separate it from its neighbours (perpendicular drop);
  - an x range can be chosen.
- **Peak fit** keeps every peak inside its own region (height ≥ 0, centre between its neighbours). The
  joint fit of many overlapping peaks now converges. When it doesn't, the message says what to change.
- **Curve fitting** has a new **Limits** field (e.g. `a=0..inf, tau=1..100`).

### Wide tables
- Every list of columns has **All / None** and a filter. The filter also takes ranges: of numeric names
  (`19600-19840`) or of positions (`#1-500`). **Shift+click** ticks a whole block.
- Opening a 20 000-column table takes well under a second of analysis instead of about 45 s.
- A **heat map** draws all the columns, anti-aliased, so no column is skipped. A **correlation matrix**
  takes up to 2 000 columns. Beyond these limits PyPlotter explains why and suggests a block or a heat map.

### Figures
- Analysis layers (e.g. **peak markers**) have their own **marker shape and size** in *Overlays*.
- The automatic legend is left out when it does not fit in the axes. One curve per fitted peak no
  longer adds a legend entry.
- Matrix tick labels fit the axes. Messages about figures that cannot be drawn follow the interface
  language.

### Fixes
- SQLite files are closed after reading. Before, they stayed open, which locks the file on Windows.

## Changes in behaviour
- **Peak finding:** areas are now measured above the chosen baseline (automatic arPLS by default). They
  used to be measured above a straight line under each peak, which could reach a distant minimum. Areas
  of overlapping peaks therefore differ from 0.1.0; they are now consistent.
- **Peak fit:** the default baseline is arPLS, subtracted before the fit. The straight line or constant
  fitted together with the peaks is still available. Up to 20 peaks are fitted by default.
- **Integral:** “Subtract the straight baseline between the ends” is now the *Baseline* choice
  *straight line between the ends of the range*.

## Updating
Download the source of this release and replace the old folder. Your settings and plugins in
`~/.pyplotter/` are kept. A **customised copy** of a built-in analysis stays as you wrote it, so it does
not get these changes. To use the new version, disable your copy in the plugin editor.

---

## Italiano

**Prima la linea di base, poi l’analisi** — e tabelle con decine di migliaia di colonne.

### Novità
- **Linea di base** (*Analisi › Segnale*):
  - **clicca i punti di ancoraggio sulla figura** (o scrivili), uniti da segmenti o da una curva liscia;
  - oppure scegli un metodo automatico: arPLS, minimi quadrati asimmetrici, SNIP o elastico;
  - linea, punti e segnale corretto compaiono su una copia della figura, con un avviso se la linea è
    troppo alta.
- **Ricerca dei picchi**, **Fit dei picchi** e **Integrale** propongono la linea già definita:
  - altezze, FWHM e aree sono misurate sopra di essa;
  - l’area di ogni picco va dai minimi che lo separano dai vicini;
  - si può scegliere un intervallo di x.
- Il **fit dei picchi** tiene ogni picco nella sua regione e converge anche con molti picchi
  sovrapposti. *Fit di curve* ha il nuovo campo **Limiti**.
- **Tabelle larghe:**
  - *Tutte* / *Nessuna*, filtro con intervalli (`19600-19840`, `#1-500`) e Maiusc+clic per i blocchi;
  - apertura di 20 000 colonne in meno di un secondo di analisi;
  - mappa di calore di tutte le colonne, correlazione fino a 2000 colonne.
- **Marcatori dedicati** (forma e dimensione) per i livelli delle analisi, come i picchi.
- La legenda automatica si omette se non sta negli assi.
- I file SQLite vengono chiusi dopo la lettura.

### Cambiamenti di comportamento
- **Ricerca dei picchi:** aree sopra la linea di base scelta (arPLS automatica di default). Le aree di
  picchi sovrapposti cambiano rispetto alla 0.1.0.
- **Fit dei picchi:** linea di base arPLS sottratta di default; fino a 20 picchi.
- **Integrale:** la retta tra gli estremi è ora una scelta di *Linea di base*.

### Aggiornare
Sostituisci la cartella con quella di questa versione. Impostazioni e plugin in `~/.pyplotter/`
restano. Una **copia personalizzata** di un’analisi inclusa non riceve queste modifiche.

Licenza MIT · © 2026 Tommaso Francese
