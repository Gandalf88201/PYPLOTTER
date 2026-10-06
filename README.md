# PyPlotter

Publication-quality plots from almost any data file, in your browser, drawn by the scientific
Python stack (Matplotlib, NumPy, pandas, and optional modules installed on demand).
Bilingual (English / Italiano), light and dark mode. MIT licence.

*Italiano più sotto.*

## Start

1. Install **Python 3.10 or newer** (<https://www.python.org/downloads/>; on Windows tick *Add python.exe to PATH*).
2. Start PyPlotter:
   - **macOS**: double-click `start_pyplotter.command` (first time: right-click › **Open** › **Open**).
   - **Windows**: double-click `start_pyplotter.bat`.
   - **Linux**: `./start_pyplotter.command`.
   - Any system: `python3 start_pyplotter.py` (or `./start_pyplotter.py`). Whatever Python starts it,
     PyPlotter re-runs itself inside its private `.venv` (created on first use), so packages never go into
     a system or Homebrew Python. Set `PYPLOTTER_NO_VENV=1` to use the current environment (e.g. conda).
3. The browser opens at `http://127.0.0.1:8770`. On the first start the page installs NumPy,
   pandas and Matplotlib into PyPlotter's private environment (`.venv`) — one button, one progress bar.

Keep the terminal window open while you work; Ctrl+C stops PyPlotter. Starting PyPlotter again
closes the copy that is already running, so there is always only one; if the page loses its
service or belongs to an older run, a red bar at the top offers to reload. Problems are also
printed in the terminal window. Options:
`--port 8771`, `--no-browser`, `--offline` (skip the PyPI check), `--max-upload-gb 50`.

## What it does

- **Opens almost anything**: CSV/TSV/TXT/DAT (separator, decimal comma, header, comment lines and
  encoding detected automatically), compressed `.gz/.bz2/.xz`, ZIP archives, Excel (`.xlsx`, `.xls`),
  LibreOffice `.ods`, JSON/JSON Lines, Parquet, Feather/Arrow, ORC, HDF5, NetCDF, MATLAB `.mat`
  (also v7.3), NumPy `.npy/.npz`, FITS, SPSS, Stata, SAS, XML, HTML tables, SQLite and
  JCAMP-DX spectra. Multi-table files (sheets, datasets, variables) show a table picker.
- **Suggests the right plot** from the column types: time series → line, ordered X → line,
  point clouds → scatter or hexbin, categories → bars/box/violin, X-Y-Z grids → contour/heatmap,
  error columns (`err`, `std`, `sigma`, `errore`, …) → error bars, many variables → correlation.
- **24 plot types**: line, scatter, step, area, error bars (bars or band), fit with equation and R²
  (linear, polynomial, exponential, logarithmic, power), stem, polar, bars (grouped/stacked,
  mean ± std), horizontal bars, box, violin, strip, swarm, pie, histogram, density (KDE), ECDF,
  heatmap, contour, hexbin, 2D histogram, correlation matrix, pair plot; secondary Y axis.
- **Publication-ready output**: exact physical size (journal column presets in mm/cm/in),
  PNG/TIFF/JPEG at 150–1200 DPI, vector PDF/SVG/EPS with editable text (TrueType fonts embedded),
  interactive HTML (Plotly), and a **Python script** ZIP (data + settings + script + references)
  that recreates the figure without PyPlotter.
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
    (height, FWHM and area above the baseline), integrals.
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
  beyond that the figure has more cells than pixels, and PyPlotter says so. The data table shows the
  first 100 columns; an automatic legend is left out when it does not fit in the axes.
- **Baseline first, then the analysis** (spectra, chromatograms, any signal with peaks): the *Baseline*
  analysis takes anchor points you **click on the figure** (or type), joined by straight lines or a smooth
  curve, or an automatic method — arPLS, asymmetric least squares, SNIP or rubber band. It draws the baseline
  and the corrected signal and warns when the baseline is too high. *Peak finding*, *Peak fit* and *Integral*
  then offer the same baseline already selected: heights, widths and areas are measured above it, each
  peak's area runs between the minima that separate it from its neighbours, and the joint peak fit keeps
  every peak inside its own region (a range of x can be chosen too).
- **New** (top bar) starts a new analysis: closes data, figure, results and overlays, keeps your style.
- **Your own analyses**: write plugins, or customise any built-in analysis, in the in-app editor;
  they live in `~/.pyplotter/plugins/` and survive updates. See [PLUGINS.md](PLUGINS.md).
- **Module manager**: `pyplotter/registry.json` lists every optional module with its licence and
  citation. At each start PyPlotter checks PyPI for the latest versions; missing modules are offered
  when a feature needs them, updates are one click, each with a single progress bar. Each installed
  module is also **imported once in a separate Python** (at start, after installs, or with *Check
  imports*): a module that pip lists but that cannot be loaded is shown in red with its error and a
  *Reinstall* button.

## Privacy and security

Everything runs on your computer. The service listens on 127.0.0.1 only, every request needs the
token embedded in the page (a random value kept in `~/.pyplotter/token`, readable only by you, so open
tabs keep working after a restart), and uploaded files are kept in a private temporary folder
that is deleted when PyPlotter stops. Only package installs (pip) and the version check contact
the internet (PyPI). Analysis plugins are Python code running with your rights: install only plugins
you trust.

## Licences and citations

PyPlotter is MIT-licensed and depends only on open-source packages, installed by you from PyPI;
nothing third-party is bundled. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for every
licence and [REFERENCES.md](REFERENCES.md) for what to cite (also shown in the app under ⓘ).

## Developers

```
.venv/bin/python -m unittest discover -s tests
```

`pyplotter/plotting.py` is the renderer (a JSON spec → Matplotlib figure), `readers.py` the file
readers, `smart.py` the recommendations, `modules.py` the registry, PyPI check and pip installs,
`plugins.py` the analysis plugin system, `analyses/` the built-in analyses, `server.py` the local HTTP
API, `web/` the interface.

---

## Italiano

PyPlotter crea grafici di qualità editoriale da quasi ogni file di dati, nel browser, usando
Matplotlib, NumPy, pandas e moduli facoltativi installati quando servono. Interfaccia in italiano e
inglese, modalità chiara e scura. Licenza MIT.

**Avvio.** Installa Python 3.10 o successivo, poi fai doppio clic su `start_pyplotter.command`
(macOS; la prima volta: clic destro › **Apri** › **Apri**) o su `start_pyplotter.bat` (Windows), oppure esegui
`python3 start_pyplotter.py`: con qualunque Python venga avviato, PyPlotter usa sempre il proprio ambiente privato `.venv`
(mai il Python di sistema o di Homebrew). Si apre il browser:
al primo avvio la pagina installa NumPy, pandas e Matplotlib nell'ambiente privato di PyPlotter
con un solo pulsante e una barra di avanzamento. Tieni aperta la finestra del terminale; Ctrl+C chiude PyPlotter.

**Funzioni principali.**
- Apre CSV/TXT/DAT (riconosce da solo separatore `;`, virgola decimale, intestazione, righe di
  commento e codifica), Excel, ODS, JSON, Parquet, HDF5, NetCDF, MATLAB, NumPy, FITS, SPSS, Stata,
  SAS, XML, HTML, SQLite, spettri JCAMP-DX, archivi ZIP e file compressi.
- Suggerisce il grafico adatto in base ai tipi di colonna (serie temporali, X ordinata, nuvole di
  punti, categorie, griglie X-Y-Z, colonne di errore come `errore` o `dev std`, molte variabili).
- 24 tipi di grafico, asse Y secondario, fit con equazione e R².
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
  da citare. I risultati vengono disegnati **su una copia del grafico originale**, in una scheda accanto a
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
  linea, un box… per colonna fino a 2000 serie — oltre, la figura avrebbe più celle che pixel e PyPlotter
  lo dice. La tabella dati mostra le prime 100 colonne; la legenda automatica si omette se non sta negli assi.
- **Prima la linea di base, poi l’analisi** (spettri, cromatogrammi, ogni segnale con picchi): l’analisi
  *Linea di base* usa punti di ancoraggio che **clicchi sulla figura** (o scrivi), uniti da segmenti o da
  una curva liscia, oppure un metodo automatico — arPLS, minimi quadrati asimmetrici, SNIP o elastico.
  Disegna la linea e il segnale corretto e avvisa se la linea è troppo alta. *Ricerca dei picchi*, *Fit dei
  picchi* e *Integrale* propongono poi la stessa linea già selezionata: altezze, larghezze e aree sono
  misurate sopra di essa, l’area di ogni picco va dai minimi che lo separano dai vicini, e il fit congiunto
  tiene ogni picco nella sua regione (si può anche scegliere un intervallo di x).
- **Nuovo** (in alto) inizia una nuova analisi: chiude dati, figura, risultati e sovrapposizioni, mantiene lo stile.
- **Plugin personali**: scrivi le tue analisi o personalizza quelle incluse nell'editor dell'app; restano
  in `~/.pyplotter/plugins/` anche dopo gli aggiornamenti. Guida: [PLUGINS.md](PLUGINS.md).
- Gestore dei moduli: a ogni avvio controlla su PyPI le ultime versioni; i moduli mancanti vengono
  proposti quando servono e si installano o aggiornano con un clic, con la sola barra di avanzamento.
  Ogni modulo installato viene anche **importato in un Python separato** (all'avvio, dopo le
  installazioni o con *Verifica import*): un modulo che pip elenca ma che non si carica appare in rosso
  con il suo errore e il pulsante *Reinstalla*.

**Licenze e citazioni.** PyPlotter è software libero (MIT) e usa solo pacchetti open source scaricati
da PyPI; non include codice di terze parti. Le licenze sono in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), i riferimenti da citare in
[REFERENCES.md](REFERENCES.md) e nell'app (pulsante ⓘ).
