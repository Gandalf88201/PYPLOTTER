# PyPlotter 0.1.3

**Zoom, move and rewrite on the figure itself — and peak labels that never overlap.**
*Italiano più sotto.*

## What's new

### Zoom
- **Drag a box** on the axes: its corners become the axis limits (the X/Y min/max fields of the Axes
  panel) and the figure is drawn again with ticks for the new range. Works on every plot with axes: lines,
  scatter, bars, box and violin plots, histograms, heat maps, contours, hexbin…
- A **thin box** zooms one axis only. Zoomed on x alone, **y follows the data in that range**: one small
  band of a spectrum fills the plot.
- The **mouse wheel** zooms around the pointer (Shift + wheel: x only). On **polar** figures it zooms the
  radius, on **3D** figures the three ranges; what falls outside a 3D box is clipped.
- *↶ Previous zoom*, *⤢ Whole figure* or a double-click on the plot go back. Pie charts and pair plots
  have no zoom.

### Move and rewrite every text
- **Drag** titles, axis labels (z too), the colour-bar label, the legend, pie slice names and shares,
  pair-plot labels and value labels, on every kind of plot.
- **Double-click a text to rewrite it.** Formulas go between `$…$`, e.g. `cm$^{-1}$`, `$\mu$g`,
  `H$_2$O`. Titles and axis labels are written in their fields of the Text panel; the legend's title in
  its own; the other texts are kept with the figure.
- *Original text* and *Original position* undo one text; *↺ Texts back in place* moves them all back.
- What you move and rewrite is kept in every export (PNG, TIFF, PDF, SVG, EPS, Python script) and in
  templates.

### Peak labels
- Labels that would cover another label, a curve or the legend move up or aside, joined to their peak by
  a thin **leader line**.
- The y axis grows to make room above the tallest peak, unless you fixed that limit.
- Labels are placed in points, so the preview and the export at any DPI match.

### 3D figures
- **Drag a 3D figure to rotate it**: a light copy of the data turns smoothly in the page, with
  Matplotlib's own projection. On release the angles are kept and the figure is drawn again.
  Double-click restores the default view.

### Fixes
- Setting the Y limits of a heat map no longer turns it upside down.

## Changes in behaviour
- With **only the X limits** set (by zoom or in the Axes panel), the Y axis now spans the data in that
  range instead of all the data.
- Peak labels may sit beside their peak, with a leader line, and the y axis may be taller to make room for
  them.

## Updating
Download the source of this release and replace the old folder. Your settings and plugins in
`~/.pyplotter/` are kept. Restart PyPlotter after updating.

---

## Italiano

**Zoom, spostamento e modifica dei testi direttamente sulla figura — e etichette dei picchi che non si
sovrappongono.**

### Novità
- **Zoom:**
  - trascina un riquadro sugli assi: diventa i limiti degli assi e la figura viene ridisegnata con le
    tacche del nuovo intervallo, su ogni grafico con assi;
  - un riquadro sottile ingrandisce un solo asse; ingrandendo solo x, **y segue i dati visibili**;
  - la **rotella** ingrandisce attorno al puntatore (Maiusc: solo x), nei grafici polari il raggio, nei
    3D i tre assi;
  - *↶ Zoom precedente*, *⤢ Figura intera* o doppio clic sul grafico per tornare indietro.
- **Testi:** titoli, etichette degli assi, barra dei colori, legenda, fette della torta, etichette del
  grafico a coppie e valori dei picchi si **spostano trascinandoli** e si **riscrivono con un doppio
  clic** (formule tra `$…$`). Restano in ogni esportazione; *Testo originale*, *Posizione originale* e
  *↺ Testi al loro posto* li ripristinano.
- **Etichette dei picchi** senza sovrapposizioni: si spostano in alto o di lato con una sottile linea di
  richiamo, e l’asse y si allunga per farle stare.
- **Grafici 3D:** trascina la figura per ruotarla; doppio clic per la vista predefinita.
- **Correzione:** i limiti Y non capovolgono più una mappa di calore.

### Cambiamenti di comportamento
- Con **solo i limiti X** impostati, l’asse Y copre i dati di quell’intervallo e non più tutti i dati.
- Le etichette dei picchi possono stare accanto al picco, con una linea di richiamo.

### Aggiornare
Sostituisci la cartella con quella di questa versione e riavvia PyPlotter. Impostazioni e plugin in
`~/.pyplotter/` restano.

Licenza MIT · © 2026 Tommaso Francese

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
