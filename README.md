# π-plotter

*Dr. T. Francese*

Publication-quality plots from almost any data file, in your browser, drawn by the scientific
Python stack (Matplotlib, NumPy, pandas, and optional modules installed on demand).
Bilingual (English / Italiano), light and dark mode. MIT licence.

**New: a built-in user manual** (button *Manual* in the top bar, or `/manual`) walks through every step —
opening data, plotting, styling, fitting, peaks, statistics, export — with pictures taken from the
program, **in English and in Italian** (it opens in the language of the program; same pictures). Its texts are
[manual/MANUAL.md](manual/MANUAL.md) and [manual/MANUAL.it.md](manual/MANUAL.it.md).

*Formerly PyPlotter (renamed in 0.2.0: the name was already in use). Your plugins and module list in
`~/.pyplotter` are copied to `~/.piplotter` the first time, and old plugins that import `pyplotter` keep working.*

*Italiano più sotto.*

## Start

1. Install **Python 3.10 or newer** (<https://www.python.org/downloads/>; on Windows tick *Add python.exe to PATH*).
2. Start π-plotter:
   - **macOS**: double-click `start_piplotter.command` (first time: right-click › **Open** › **Open**).
   - **Windows**: double-click `start_piplotter.bat`.
   - **Linux**: `./start_piplotter.command`.
   - Any system: `python3 start_piplotter.py` (or `./start_piplotter.py`). Whatever Python starts it,
     π-plotter re-runs itself inside its private `.venv` (created on first use), so packages never go into
     a system or Homebrew Python. Set `PIPLOTTER_NO_VENV=1` to use the current environment (e.g. conda).
3. The browser opens at `http://127.0.0.1:8770`. On the first start the page installs NumPy,
   pandas and Matplotlib into π-plotter's private environment (`.venv`) — one button, one progress bar.

Keep the terminal window open while you work; Ctrl+C stops π-plotter. Starting π-plotter again
closes the copy that is already running, so there is always only one; if the page loses its
service or belongs to an older run, a red bar at the top offers to reload. Problems are also
printed in the terminal window. Options:
`--port 8771`, `--no-browser`, `--offline` (skip the PyPI check), `--max-upload-gb 50`.

## What it does

- **Opens almost anything**: CSV/TSV/TXT/DAT (separator, decimal comma, header, comment lines and
  encoding detected automatically), compressed `.gz/.bz2/.xz`, ZIP archives, Excel (`.xlsx`, `.xls`),
  LibreOffice `.ods`, JSON/JSON Lines, Parquet, Feather/Arrow, ORC, HDF5, NetCDF, MATLAB `.mat`
  (also v7.3), NumPy `.npy/.npz`, FITS, SPSS, Stata, SAS, XML, HTML tables, SQLite and
  JCAMP-DX spectra (`.jdx`, `.dx`; plain or compressed, as exported by instruments and NIST). Multi-table files (sheets, datasets, variables) show a table picker.
- **Suggests the right plot** from the column types: time series → line, ordered X → line,
  point clouds → scatter or hexbin, categories → bars/box/violin, X-Y-Z grids → contour/heatmap,
  error columns (`err`, `std`, `sigma`, `errore`, …) → error bars, many variables → correlation.
- **27 plot types**: line, scatter, step, area, error bars (bars or band), fit with equation and R²
  (linear, polynomial, exponential, logarithmic, power), stem, polar, bars (grouped/stacked,
  mean ± std), horizontal bars, box, violin, strip, swarm, pie, histogram, density (KDE), ECDF,
  heatmap, contour, hexbin, 2D histogram, correlation matrix, pair plot; secondary Y axis.
  **3D**: surface z(x, y) (from a grid or scattered points; wire frame optional), 3D scatter or line,
  and waterfall of spectra (one curve per column, at the depth given by the column name — a time,
  a temperature — or by its position), with view angles and z limits; also as interactive HTML.
  **Drag the figure to rotate it**: a light copy of the data turns smoothly in the page, with Matplotlib's own
  projection, panes, grid and labels; on release the angles are kept and the figure is drawn again
  (double-click: default view).
- **Zoom and edit on the figure**: drag a box or turn the mouse wheel to zoom (any plot with axes; the
  wheel also zooms polar and 3D figures) and the axes are drawn again for the new range. Drag any text —
  title, axis labels, legend, colour-bar label, slice and peak labels — to move it, double-click it to
  rewrite it (formulas between `$…$`). Peak labels never overlap: crowded ones move aside with a leader
  line. Everything is kept in every export.
- **Publication-ready output**: exact physical size (journal column presets in mm/cm/in),
  PNG/TIFF/JPEG at 150–1200 DPI, vector PDF/SVG/EPS with editable text (TrueType fonts embedded),
  interactive HTML (Plotly), and a **Python script** ZIP (data + settings + script + references)
  that recreates the figure without π-plotter.
- **Full control**: styles (clean publication, seaborn-like, ggplot, SciencePlots Science /
  Nature-like / IEEE-like), colour-blind-safe palettes, colour maps (incl. Crameri), per-series
  colour/label/line/marker, fonts and sizes in points, LaTeX-style math (`$\alpha$`, `$10^{-3}$`),
  log/symlog scales, limits, ticks (in/out, minor, mirrored), grid, frame, legend inside/outside.
  Style templates can be saved and loaded as JSON.
- **Recipes** — ready-made paths that run several analyses in a row and answer in plain words, first in
  the *Analysis* list: *Gaussian distribution of a column* (histogram + Gaussian fit, normality, true
  error of the mean), *Mean of a time series* and *Equilibration of a simulation* (block averaging,
  correlation time, automatic start of equilibrium, Chodera 2016) for MD/Monte Carlo data, *Are the
  groups different?* (the right test chosen automatically), *Relation between two variables*,
  *Peak fit* (all peaks fitted together; centre, height, FWHM, area, values written above the peaks)
  and *Reaction kinetics* (zero, first and second order compared by AIC; k and t½ with errors).
  Recipes are plugins too: see [PLUGINS.md](PLUGINS.md) to write your own.
- **Analysis** panel in the right sidebar, above *Export* — the figure stays open, the results (numbers,
  tables, references) stay in the panel, and curves are drawn on a copy of the figure (all through
  open-source Python modules, results with the references to cite):
  - *fitting* — 15 models (exponential, double, stretched/KWW, power, Gaussian, Lorentzian, Voigt,
    logistic, Hill, Michaelis–Menten, Arrhenius, sine, polynomials) or your own formula, weighted by an
    error column, with standard errors, 95 % CIs, R², adjusted R², RMSE, χ²_red, AIC, BIC (SciPy); it also
    fits the **histogram of a column** (e.g. a Gaussian over a distribution of values), drawn straight
    on a histogram figure with its own bins;
  - *time series* — autocorrelation and partial autocorrelation with confidence band, integrated
    correlation time, statistical inefficiency, effective samples (statsmodels); block averaging
    (Flyvbjerg–Petersen) for the true error of correlated data such as MD trajectories; cross-correlation;
  - *statistics* — descriptive statistics, normality tests with Q–Q plot, group comparisons (t-tests,
    Mann–Whitney, Wilcoxon, ANOVA, Alexander–Govern, Kruskal–Wallis, Tukey HSD, effect sizes),
    correlation with p-values, linear models and ANOVA with R-style formulas (statsmodels),
    distribution fitting ranked by AIC;
  - *signal* — baseline, Savitzky–Golay smoothing and derivatives, power spectrum, peak finding
    (height, FWHM and area above the baseline), integrals, and **IR peak assignment**: on a mid-IR
    spectrum (absorbance or transmittance; cm⁻¹, µm or nm) it finds the peaks and lists for each the
    candidate groups from a table of about 110 characteristic bands — organic groups, and inorganic anions
    and minerals (carbonates, sulfates, silicates, oxalates…) for materials and conservation science. The
    candidates are ranked by range, intensity and width, and by the other bands the same group needs (an
    ester C–O only with an ester C=O, an aryl ether only with an aromatic ring, organic groups only with
    C–H bands); each gets a confidence, the figure shows “1738 C=O” above the peaks (“?” when uncertain),
    and a table lists the groups that explain the most peaks. Groups with S, P, Si or halogens are offered
    on request. They are candidates, not proofs: the table (`BANDS` in `ir_assign.py`, editable with
    *Customise*) holds standard values from the references in REFERENCES.md. *Examples › IR spectrum* is
    a synthetic spectrum to try it on.
  Results are **drawn on a copy of the original figure**, in its own tab next to *Figure* (close it
  with ×; the original is never changed), with their error bands (95 % confidence or prediction band
  of fits and regressions, mean ± SEM of block averaging, smoothed curves, peak markers) — a fit
  weighted by an error column also shows the data with those error bars. Analyses run while a copy is
  open are added to it; each copy has its own style and exports like any figure. Results with axes of
  their own (autocorrelation, power spectrum, Q–Q plot, block averaging…) open as a figure of their own
  data, also in a tab closed with ×.
- **Several files**: open many files at once (or one after another). Files opened together are drawn
  in the same graph, one colour and legend entry per file; *Combine files* chooses which files, columns
  and error columns to include, or switches to **one panel per file** (shared axes, panel letters
  (a), (b)…, file names as titles), ready for multi-panel journal figures.
- **Wide tables** (tens of thousands of columns): every list of columns has *All* / *None*, a filter that
  also takes a range of numeric names (`19600-19840`) or of positions (`#1-500`), and Shift+click to tick
  a whole block. A heat map draws all of them (anti-aliased, so no column is skipped); a correlation
  matrix takes up to 2,000 columns and a plot with one line, box… per column up to 2,000 series —
  beyond that the figure has more cells than pixels, and π-plotter says so. The data table shows the
  first 100 columns; an automatic legend is left out when it does not fit in the axes.
- **Baseline first, then the analysis** (spectra, chromatograms, any signal with peaks): the *Baseline*
  analysis takes anchor points you **click on the figure** (or type), joined by straight lines or a smooth
  curve (each click keeps its x and y), or an automatic method — by default a straight line (or flat level, or low
  polynomial) under the signal that the peaks do not pull up (Mazet et al. 2005), or arPLS, asymmetric least squares,
  SNIP or rubber band for curved backgrounds; spectra whose peaks point down (transmittance) get the baseline above
  the dips, recognised automatically. The corrected spectrum opens on its own (transmittance divided by the
  baseline, T / T₀, so it stays in %; other signals with the baseline subtracted), optionally with the spectrum
  before the correction. It draws the baseline
  and the corrected signal and warns when the baseline is too high. *Peak finding*, *Peak fit* and *Integral*
  then offer the same baseline already selected: heights, widths and areas are measured above it, each
  peak's area runs between the minima that separate it from its neighbours, and the joint peak fit keeps
  every peak inside its own region (a range of x can be chosen too).
- **New** (top bar) starts a new analysis: closes data, figure, results and overlays, keeps your style.
- **Your own analyses**: write plugins, or customise any built-in analysis, in the in-app editor;
  they live in `~/.piplotter/plugins/` and survive updates. See [PLUGINS.md](PLUGINS.md).
- **Module manager**: `piplotter/registry.json` lists every optional module with its licence and
  citation. At each start π-plotter checks PyPI for the latest versions; missing modules are offered
  when a feature needs them, updates are one click, each with a single progress bar. Each installed
  module is also **imported once in a separate Python** (at start, after installs, or with *Check
  imports*): a module that pip lists but that cannot be loaded is shown in red with its error and a
  *Reinstall* button.
- **Your modules from PyPI** (*Modules › Your modules*): type the name of any package on PyPI and
  press *Check*. π-plotter asks pip what it would install (a dry run, nothing is changed) and shows the
  package and every dependency with its **licence**. Open-source (OSI-approved) licences install
  normally; a licence that is not OSI-approved, proprietary or not recognised is marked and needs a
  tick in *“I have read the licence terms…”* before *Install* is enabled. Only plain package names are
  accepted (no versions, URLs, paths or pip options), and the version shown is the one installed.
  Your modules are listed with their licence, the packages installed with them, an optional reference
  to cite (shown with the results of analyses whose plugin lists the module in `requires`) and an
  *Uninstall* button (refused when another package needs the module). They are recorded in
  `~/.piplotter/user-modules.json`: in a new environment they are shown as *not installed* with
  *Install again*. The import check goes deeper for your modules: each one is imported **with its
  submodules**, because a package whose `import` works may still have every part that does the work
  broken (uvvispy 0.1.1 with setuptools 84: `No module named 'pkg_resources'`). When more than half
  of its parts fail it is *cannot be used* (red); when fewer fail, usually optional parts, it *works
  in part* (amber). Either way the failing parts are listed, grouped by cause. The check also runs
  right after installing: a module that **cannot be used is removed again**, with the packages that
  came with it, and the packages it upgraded go back to their versions, so the environment stays as it
  was and the reason is shown. Installing a module only makes it available to analyses: its features
  appear in π-plotter through plugins that list it in `requires` (its **integration**). A module that
  no plugin uses says so, with *Create integration*, which writes a first, editable analysis that uses
  it. Once a module imports and is used, **its icon appears at the end of the bar of plot types**: it
  lists its functions (only the ones that work, if the module works in part), and choosing one opens it
  in *Analysis* (see PLUGINS.md). These are **third-party code** that π-plotter does not check: install only what
  you trust. The licence check reads the package metadata; it is a help, not legal advice.

## Privacy and security

Everything runs on your computer. The service listens on 127.0.0.1 only, every request needs the
token embedded in the page (a random value kept in `~/.piplotter/token`, readable only by you, so open
tabs keep working after a restart), and uploaded files are kept in a private temporary folder
that is deleted when π-plotter stops. Only package installs and checks (pip) and the version check
contact the internet (PyPI). Analysis plugins are Python code running with your rights: install only plugins
you trust.

## Licences and citations

π-plotter is MIT-licensed and depends only on open-source packages, installed by you from PyPI;
nothing third-party is bundled. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for every
licence and [REFERENCES.md](REFERENCES.md) for what to cite (also shown in the app under ⓘ).

## Developers

```
.venv/bin/python -m unittest discover -s tests
```

The manual is `manual/MANUAL.md` (English) and `manual/MANUAL.it.md` (Italian; keep the same sections and pictures: a test
checks it) plus `manual/img/*.png`, rendered by `piplotter/manual.py`. After an interface change,
redraw the pictures with `python tools/make_manual_images.py` (needs `pip install playwright` and Chrome; see the last
section of the manual).

`piplotter/plotting.py` is the renderer (a JSON spec → Matplotlib figure), `readers.py` the file
readers, `smart.py` the recommendations, `modules.py` the registry, PyPI check and pip installs,
`plugins.py` the analysis plugin system, `analyses/` the built-in analyses, `server.py` the local HTTP
API, `web/` the interface.

---

## Italiano

π-plotter crea grafici di qualità editoriale da quasi ogni file di dati, nel browser, usando
Matplotlib, NumPy, pandas e moduli facoltativi installati quando servono. Interfaccia in italiano e
inglese, modalità chiara e scura. Licenza MIT.

**Manuale.** Il pulsante *Manuale* in alto apre il manuale d'uso (in italiano o in inglese, come il programma) con tutti i passaggi e le immagini.
Il programma si chiamava PyPlotter: i tuoi plugin e l'elenco dei moduli in `~/.pyplotter` vengono copiati in `~/.piplotter`.

**Avvio.** Installa Python 3.10 o successivo, poi fai doppio clic su `start_piplotter.command`
(macOS; la prima volta: clic destro › **Apri** › **Apri**) o su `start_piplotter.bat` (Windows), oppure esegui
`python3 start_piplotter.py`: con qualunque Python venga avviato, π-plotter usa sempre il proprio ambiente privato `.venv`
(mai il Python di sistema o di Homebrew). Si apre il browser:
al primo avvio la pagina installa NumPy, pandas e Matplotlib nell'ambiente privato di π-plotter
con un solo pulsante e una barra di avanzamento. Tieni aperta la finestra del terminale; Ctrl+C chiude π-plotter.

**Funzioni principali.**
- Apre CSV/TXT/DAT (riconosce da solo separatore `;`, virgola decimale, intestazione, righe di
  commento e codifica), Excel, ODS, JSON, Parquet, HDF5, NetCDF, MATLAB, NumPy, FITS, SPSS, Stata,
  SAS, XML, HTML, SQLite, spettri JCAMP-DX (`.jdx`, `.dx`, anche compressi), archivi ZIP e file compressi.
- Suggerisce il grafico adatto in base ai tipi di colonna (serie temporali, X ordinata, nuvole di
  punti, categorie, griglie X-Y-Z, colonne di errore come `errore` o `dev std`, molte variabili).
- 27 tipi di grafico, asse Y secondario, fit con equazione e R². In **3D**: superficie z(x, y) (da una
  griglia o da punti sparsi, anche solo reticolo), dispersione o linea 3D e cascata di spettri (una curva
  per colonna, alla profondità data dal nome della colonna o dalla sua posizione), con angoli di vista.
  **Trascina la figura per ruotarla**: una copia leggera dei dati gira in modo fluido nella pagina, con la
  proiezione di Matplotlib; al rilascio gli angoli restano e la figura viene ridisegnata (doppio clic: vista
  predefinita).
- **Zoom e modifica sulla figura**: trascina un riquadro o gira la rotella per ingrandire (ogni grafico con
  assi; la rotella anche polari e 3D) e gli assi vengono ridisegnati per il nuovo intervallo. Trascina un
  testo — titolo, etichette degli assi, legenda, barra dei colori, fette, valori dei picchi — per spostarlo,
  doppio clic per riscriverlo (formule tra `$…$`). Le etichette dei picchi non si sovrappongono: quelle
  affollate si spostano con una linea di richiamo. Tutto resta in ogni esportazione.
- Esportazione alle dimensioni esatte delle colonne delle riviste: PNG/TIFF/JPEG fino a 1200 DPI,
  PDF/SVG/EPS vettoriali con testo modificabile, HTML interattivo e uno ZIP con script Python che
  ricrea la figura, completo dei riferimenti da citare.
- **Ricette** — percorsi pronti che eseguono più analisi in sequenza e rispondono in parole semplici,
  prime nell'elenco *Analisi*: *Distribuzione gaussiana di una colonna* (istogramma + fit gaussiano,
  normalità, vero errore della media), *Media di una serie temporale* ed *Equilibratura di una
  simulazione* (block averaging, tempo di correlazione, inizio automatico dell'equilibrio, Chodera 2016)
  per dati MD/Monte Carlo, *I gruppi sono diversi?* (il test giusto scelto in automatico), *Relazione tra
  due variabili*, *Fit dei picchi* (tutti i picchi insieme; centro, altezza, FWHM, area, valori scritti
  sopra i picchi) e *Cinetica di reazione* (ordine zero, uno e due confrontati con l'AIC; k e t½ con
  errori). Anche le ricette sono plugin: per scriverne di nuove vedi [PLUGINS.md](PLUGINS.md).
- Riquadro **Analisi** nella barra di destra, sopra *Esporta* (il grafico resta aperto e i risultati
  numerici restano visibili nel riquadro): fit (15 modelli o formula libera, con errori, intervalli di confidenza, R², AIC;
  anche dell'**istogramma di una colonna**, disegnato direttamente su un grafico a istogramma),
  autocorrelazione e PACF, tempo di correlazione, block averaging per l'errore di dati correlati (es. MD),
  correlazione incrociata, statistica descrittiva, test di normalità, confronto tra gruppi (t-test,
  ANOVA, Kruskal–Wallis, Tukey…), correlazioni, regressione e ANOVA con formule, fit di distribuzioni,
  smoothing, derivate, spettro, picchi, integrali — sempre con moduli Python open source e i riferimenti
  da citare. **Assegnazione dei picchi IR**: su uno spettro IR medio (assorbanza o trasmittanza; cm⁻¹, µm
  o nm) trova i picchi ed elenca per ognuno i gruppi candidati da una tabella di circa 110 bande
  caratteristiche — gruppi organici, anioni inorganici e minerali (carbonati, solfati, silicati, ossalati…)
  per la scienza dei materiali e la conservazione. I candidati sono ordinati per intervallo, intensità e
  larghezza, e per le altre bande che lo stesso gruppo richiede (il C–O di un estere solo con il C=O di un
  estere, un etere arilico solo con un anello aromatico, i gruppi organici solo con bande C–H); ognuno ha
  un'affidabilità, il grafico mostra «1738 C=O» sopra i picchi («?» se incerto) e una tabella elenca i
  gruppi che spiegano più picchi. I gruppi con S, P, Si o alogeni si includono su richiesta. Sono
  candidati, non prove: la tabella (`BANDS` in `ir_assign.py`, modificabile con *Personalizza*) contiene
  valori standard dai riferimenti di REFERENCES.md. *Esempi › Spettro IR* è uno spettro sintetico per
  provarla. I risultati vengono disegnati **su una copia del grafico originale**, in una scheda accanto a
  *Figura* che si chiude con × (l'originale non cambia mai), con le loro bande d'errore (confidenza o
  predizione al 95% di fit e regressioni, media ± SEM del block averaging, curve filtrate, picchi; un fit
  pesato mostra anche le barre d'errore dei dati). Le analisi eseguite con una copia aperta si aggiungono
  a quella copia, che ha il proprio stile e si esporta come ogni figura. I risultati con assi propri
  (autocorrelazione, spettro, grafico Q–Q, block averaging…) si aprono come figura dei propri dati, anche
  loro in una scheda che si chiude con ×.
- **Più file**: apri più file insieme (o uno dopo l'altro). I file aperti insieme vengono disegnati nello
  stesso grafico, un colore e una voce di legenda per file; *Combina file* sceglie file, colonne ed errori
  da includere, oppure passa a **un pannello per file** (assi condivisi, lettere (a), (b)…, nomi dei file
  come titoli), pronto per le figure a più pannelli delle riviste.
- **Tabelle larghe** (decine di migliaia di colonne): ogni elenco di colonne ha *Tutte* / *Nessuna*, un
  filtro che accetta anche un intervallo di nomi numerici (`19600-19840`) o di posizioni (`#1-500`), e
  Maiusc+clic per spuntare un intero blocco. La mappa di calore le disegna tutte (con anti-aliasing,
  nessuna colonna saltata); la matrice di correlazione accetta fino a 2000 colonne e i grafici con una
  linea, un box… per colonna fino a 2000 serie — oltre, la figura avrebbe più celle che pixel e π-plotter
  lo dice. La tabella dati mostra le prime 100 colonne; la legenda automatica si omette se non sta negli assi.
- **Prima la linea di base, poi l’analisi** (spettri, cromatogrammi, ogni segnale con picchi): l’analisi
  *Linea di base* usa punti di ancoraggio che **clicchi sulla figura** (o scrivi), uniti da segmenti o da
  una curva liscia (ogni clic tiene x e y), oppure un metodo automatico — di base una retta (o un livello piatto, o un
  polinomio basso) sotto il segnale che i picchi non sollevano (Mazet et al. 2005), oppure arPLS, minimi quadrati asimmetrici,
  SNIP o elastico per fondi curvi; negli spettri con picchi in giù (trasmittanza) la linea va sopra gli avvallamenti. Lo spettro corretto si apre da solo
  (la trasmittanza è divisa per la linea di base, T / T₀, e resta in %), su richiesta insieme allo spettro prima della correzione.
  Disegna la linea e il segnale corretto e avvisa se la linea è troppo alta. *Ricerca dei picchi*, *Fit dei
  picchi* e *Integrale* propongono poi la stessa linea già selezionata: altezze, larghezze e aree sono
  misurate sopra di essa, l’area di ogni picco va dai minimi che lo separano dai vicini, e il fit congiunto
  tiene ogni picco nella sua regione (si può anche scegliere un intervallo di x).
- **Nuovo** (in alto) inizia una nuova analisi: chiude dati, figura, risultati e sovrapposizioni, mantiene lo stile.
- **Plugin personali**: scrivi le tue analisi o personalizza quelle incluse nell'editor dell'app; restano
  in `~/.piplotter/plugins/` anche dopo gli aggiornamenti. Guida: [PLUGINS.md](PLUGINS.md).
- Gestore dei moduli: a ogni avvio controlla su PyPI le ultime versioni; i moduli mancanti vengono
  proposti quando servono e si installano o aggiornano con un clic, con la sola barra di avanzamento.
  Ogni modulo installato viene anche **importato in un Python separato** (all'avvio, dopo le
  installazioni o con *Verifica import*): un modulo che pip elenca ma che non si carica appare in rosso
  con il suo errore e il pulsante *Reinstalla*.
- **I tuoi moduli da PyPI** (*Moduli › I tuoi moduli*): scrivi il nome di un pacchetto su PyPI e premi
  *Controlla*. π-plotter chiede a pip cosa installerebbe (una prova, senza modifiche) e mostra il
  pacchetto e ogni dipendenza con la sua **licenza**. Le licenze open source (approvate OSI) si
  installano normalmente; una licenza non approvata OSI, proprietaria o non riconosciuta è segnalata e
  serve la spunta *«Ho letto le condizioni di licenza…»* per abilitare *Installa*. Si accettano solo
  nomi di pacchetti (niente versioni, URL, percorsi od opzioni di pip). I tuoi moduli sono elencati
  con licenza, pacchetti installati con essi, un riferimento da citare (facoltativo) e il pulsante
  *Disinstalla*; sono registrati in `~/.piplotter/user-modules.json`, così in un nuovo ambiente
  compaiono come *non installati* con *Installa di nuovo*. Per i tuoi moduli il controllo è più
  severo: ognuno viene importato **con i suoi sottomoduli**, perché un pacchetto il cui `import`
  funziona può avere rotte tutte le parti che fanno il lavoro (uvvispy 0.1.1 con setuptools 84:
  `No module named 'pkg_resources'`). Se non si importa più della metà delle parti è *non
  utilizzabile* (rosso); se ne falliscono meno, di solito parti facoltative, *funziona in parte*
  (arancione). In entrambi i casi le parti che non si importano sono elencate, raggruppate per causa.
  Il controllo parte anche subito dopo l'installazione: un modulo **non utilizzabile viene tolto di
  nuovo**, con i pacchetti arrivati insieme, e i pacchetti che aveva aggiornato tornano alle loro
  versioni; l'ambiente resta com'era e viene mostrato il motivo. Installare un modulo lo rende solo
  disponibile alle analisi: le sue funzioni compaiono in π-plotter tramite i plugin che lo elencano in
  `requires` (la sua **integrazione**). Un modulo che nessun plugin usa lo dice, con *Crea
  integrazione*, che scrive una prima analisi modificabile che lo usa. Quando un modulo si importa ed è
  usato, **la sua icona compare in fondo alla barra dei tipi di grafico**: elenca le sue funzioni (solo
  quelle che funzionano, se il modulo funziona in parte) e sceglierne una la apre in *Analisi* (vedi
  PLUGINS.md). Sono **codice di terze parti** non
  controllato da π-plotter: installa solo ciò di cui ti fidi. Il controllo della licenza legge i
  metadati del pacchetto: è un aiuto, non una consulenza legale.

**Licenze e citazioni.** π-plotter è software libero (MIT) e usa solo pacchetti open source scaricati
da PyPI; non include codice di terze parti. Le licenze sono in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), i riferimenti da citare in
[REFERENCES.md](REFERENCES.md) e nell'app (pulsante ⓘ).
