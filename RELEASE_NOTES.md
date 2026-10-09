# π-plotter 0.2.0

**A new name, a signature, and a built-in user manual with pictures.**
*Italiano più sotto.*

## What's new

### The program is now π-plotter
- PyPlotter's name was already in use, so the program is **π-plotter** from now on. The window, the
  terminal banner, the exports and the documents say so; the launchers are `start_piplotter.command`,
  `start_piplotter.bat` and `start_piplotter.py`, the Python package is `piplotter`, and the environment
  variables start with `PIPLOTTER_`.
- Nothing is lost: the first start copies your plugins, your module list and the session token from
  `~/.pyplotter` to `~/.piplotter` (the old folder is left alone); plugins that still say
  `from pyplotter import baselines` keep working; saved style templates and module lists of the old name
  are still read.
- The GitHub repository is now `Gandalf88201/pi-plotter` (GitHub names cannot contain π); the old address
  redirects to it. The folder of the project on disk keeps its name.

### Signature
- **Dr. T. Francese** appears under the name in the top bar (as in MONET), in the *About* window, on the
  welcome page, in the terminal banner and in the manual.

### User manual
- A **Manual** button in the top bar opens the manual in a new tab. It follows the order of the work: open
  data, choose variables and plot, style the figure (size, colours, text, axes, zoom, 3D), analyse
  (fitting, kinetics, baseline and peaks, peak fit, IR assignment, equilibration and correlated errors,
  group tests, relations), export, plugins and modules, troubleshooting. 43 pictures are taken from the
  program itself.
- The text is `manual/MANUAL.md`; the pictures are `manual/img/`. `tools/make_manual_images.py` redraws all
  of them (or just some) after a change of the interface, so the manual can be kept up to date.
- The manual prints cleanly (print / save as PDF from the browser) and follows light and dark mode.

---

## Italiano

### Il programma ora si chiama π-plotter
- Il nome PyPlotter era già in uso: da ora il programma è **π-plotter**. Cambiano i file di avvio
  (`start_piplotter.*`), il pacchetto Python (`piplotter`) e le variabili d'ambiente (`PIPLOTTER_`).
- Non si perde nulla: al primo avvio plugin, elenco dei moduli e token passano da `~/.pyplotter` a
  `~/.piplotter` (la vecchia cartella resta com'è); i plugin che importano `pyplotter` continuano a
  funzionare, e i modelli di stile e gli elenchi di moduli salvati col vecchio nome si leggono ancora.

### Firma
- **Dr. T. Francese** compare sotto il nome nella barra in alto (come in MONET), nella finestra
  *Informazioni*, nella pagina di benvenuto, nel terminale e nel manuale.

### Manuale d'uso
- Il pulsante **Manuale** apre il manuale (in inglese) in una nuova scheda: dall'apertura dei dati
  all'esportazione, passando per stile, zoom, 3D, fit, cinetica, linea di base e picchi, assegnazione IR,
  errori di dati correlati, test tra gruppi, plugin e moduli. Il testo è `manual/MANUAL.md` e le immagini
  si rigenerano con `tools/make_manual_images.py`.

---

# π-plotter 0.1.4

**Modules from PyPI that are checked for real, with an icon for their functions — and IR peak assignment.**
*Italiano più sotto.*

## What's new

### IR peak assignment
- A new analysis, **IR peak assignment** (*Analysis › Signal*), for mid-IR spectra in absorbance or
  transmittance (recognised from the column name and the shape), against cm⁻¹, µm or nm.
- It finds the peaks above the baseline and lists, for each, the **candidate groups** from a table of
  **111 characteristic bands**:
  - organic groups (O–H, N–H, C–H, C=O of esters, acids, ketones, aldehydes, amides…, C–O, aromatic and
    alkene bands, nitro, nitrile and more);
  - inorganic anions and minerals for materials and conservation science: carbonates, sulfates, nitrates,
    phosphates, silicates and quartz, clays, metal oxalates, carboxylates and metal soaps, Prussian blue;
  - water, and atmospheric CO₂ flagged as an artefact.
- Candidates are ranked by how narrow the range is, how well intensity and width match, and by the
  **companion bands** a group needs: an ester C–O only with an ester C=O, an aldehyde only with its
  C–H doublet, an aryl ether only with an aromatic ring, carbonate bends only with a strong carbonate
  band, organic groups only with C–H bands.
- Each peak gets a **confidence** (high, medium, low). The figure shows “1738 C=O” above the peaks,
  or “860 ?” when uncertain. A table lists the **groups that explain the most peaks**, and notes say
  what missing bands rule out (no strong band at 1850–1650 cm⁻¹: no C=O).
- Groups with S, P, Si or halogens are included on request: their broad ranges fit almost any peak.
- They are candidates, not proofs. The table (`BANDS` in `ir_assign.py`, editable with *Customise*)
  holds standard values compiled from the references listed in REFERENCES.md.
- *Examples › IR spectrum*: a synthetic spectrum to try it on.

### Your modules from PyPI
- **Deeper import check.** Each module you added is imported with its submodules. A package whose
  `import` works but whose working parts fail is shown as **cannot be used** (red), e.g. uvvispy 0.1.1
  with setuptools 84 (`No module named 'pkg_resources'`). When only a few parts fail, usually optional
  ones, it **works in part** (amber). The failing parts are listed, grouped by cause.
- **An install that cannot be used is undone.** Right after installing, the module is checked. If it
  cannot be used, the packages it added are removed and the ones it upgraded go back to their
  versions; the environment stays as it was and the reason is shown.
- **Integrations.** A module does something in π-plotter through the plugins that list it in
  `requires`.
  - A module that no plugin uses says so, with **Create integration**: a first, working analysis that
    uses it, opened in the editor.
  - A module that imports and is used gets **its own icon at the end of the bar of plot types**. The
    icon lists its functions; choosing one opens it in *Analysis*, ready for the open data.
  - Analyses that import a part of a module that fails are disabled, with the reason.

## Changes in behaviour
- Modules you added that showed “import OK” may now show *cannot be used* or *works in part*: they are
  checked again, more strictly, at the next start.
- The red badge on *Modules* and the line at the top of the Modules window count your modules too.
- Installing a module that cannot be used now leaves nothing behind.

## Updating
Download the source of this release and replace the old folder. Your settings and plugins in
`~/.piplotter/` are kept. Restart π-plotter after updating.

---

## Italiano

**Moduli da PyPI controllati davvero, con un’icona per le loro funzioni — e l’assegnazione dei picchi IR.**

### Novità
- **Assegnazione dei picchi IR** (*Analisi › Segnale*), per spettri IR medi in assorbanza o trasmittanza,
  in cm⁻¹, µm o nm:
  - trova i picchi ed elenca per ognuno i **gruppi candidati** da una tabella di **111 bande
    caratteristiche**: gruppi organici, anioni inorganici e minerali (carbonati, solfati, nitrati,
    fosfati, silicati e quarzo, argille, ossalati, saponi metallici, blu di Prussia), acqua e CO₂
    atmosferica come artefatto;
  - i candidati sono ordinati per intervallo, intensità, larghezza e **bande compagne** (il C–O di un
    estere solo con il suo C=O, un’aldeide solo con il doppietto C–H, i gruppi organici solo con bande C–H);
  - ogni picco ha un’**affidabilità**; il grafico mostra «1738 C=O» sopra i picchi, o «860 ?» se
    incerto; una tabella elenca i **gruppi che spiegano più picchi**;
  - i gruppi con S, P, Si o alogeni si includono su richiesta;
  - sono candidati, non prove: la tabella (`BANDS` in `ir_assign.py`, modificabile con *Personalizza*)
    contiene valori standard dai riferimenti di REFERENCES.md;
  - *Esempi › Spettro IR* per provarla.
- **I tuoi moduli da PyPI:**
  - **controllo più severo**: ogni modulo viene importato con i suoi sottomoduli; se le parti che fanno
    il lavoro non si importano è **non utilizzabile** (rosso), se ne falliscono poche **funziona in
    parte** (arancione); le parti che falliscono sono elencate per causa;
  - **un’installazione non utilizzabile viene annullata**: i pacchetti aggiunti vengono tolti e quelli
    aggiornati tornano alla versione precedente;
  - **integrazioni**: un modulo che nessun plugin usa lo dice, con **Crea integrazione**; un modulo
    usato ha **la sua icona in fondo alla barra dei tipi di grafico**, con l’elenco delle sue funzioni;
    le analisi che usano una parte rotta sono disattivate.

### Cambiamenti di comportamento
- Moduli che risultavano «import OK» possono ora risultare *non utilizzabili* o *funziona in parte*.
- Il contatore rosso su *Moduli* conta anche i tuoi moduli.

### Aggiornare
Sostituisci la cartella con quella di questa versione e riavvia π-plotter. Impostazioni e plugin in
`~/.piplotter/` restano.

Licenza MIT · © 2026 Tommaso Francese

---

# π-plotter 0.1.3

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
`~/.piplotter/` are kept. Restart π-plotter after updating.

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
Sostituisci la cartella con quella di questa versione e riavvia π-plotter. Impostazioni e plugin in
`~/.piplotter/` restano.

Licenza MIT · © 2026 Tommaso Francese

---

# π-plotter 0.1.2

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
- They are recorded in `~/.piplotter/user-modules.json`. In a new environment they appear as *not
  installed*, with *Install again*.
- These are third-party code that π-plotter does not check: install only what you trust.

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
  - Sono codice di terze parti non controllato da π-plotter.

Licenza MIT · © 2026 Tommaso Francese

---

# π-plotter 0.1.1

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
  takes up to 2 000 columns. Beyond these limits π-plotter explains why and suggests a block or a heat map.

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
`~/.piplotter/` are kept. A **customised copy** of a built-in analysis stays as you wrote it, so it does
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
Sostituisci la cartella con quella di questa versione. Impostazioni e plugin in `~/.piplotter/`
restano. Una **copia personalizzata** di un’analisi inclusa non riceve queste modifiche.

Licenza MIT · © 2026 Tommaso Francese
