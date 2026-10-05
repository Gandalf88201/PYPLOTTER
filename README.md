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

Keep the terminal window open while you work; Ctrl+C stops PyPlotter. Options:
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
- **Module manager**: `pyplotter/registry.json` lists every optional module with its licence and
  citation. At each start PyPlotter checks PyPI for the latest versions; missing modules are offered
  when a feature needs them, updates are one click, each with a single progress bar.

## Privacy and security

Everything runs on your computer. The service listens on 127.0.0.1 only, every request needs the
per-session token embedded in the page, and uploaded files are kept in a private temporary folder
that is deleted when PyPlotter stops. Only package installs (pip) and the version check contact
the internet (PyPI).

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
`server.py` the local HTTP API, `web/` the interface.

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
- Gestore dei moduli: a ogni avvio controlla su PyPI le ultime versioni; i moduli mancanti vengono
  proposti quando servono e si installano o aggiornano con un clic, con la sola barra di avanzamento.

**Licenze e citazioni.** PyPlotter è software libero (MIT) e usa solo pacchetti open source scaricati
da PyPI; non include codice di terze parti. Le licenze sono in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), i riferimenti da citare in
[REFERENCES.md](REFERENCES.md) e nell'app (pulsante ⓘ).
