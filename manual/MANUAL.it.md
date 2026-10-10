# π-plotter — Manuale d’uso

*Dr. T. Francese*

π-plotter trasforma quasi ogni file di dati in una figura di qualità editoriale e la analizza con moduli Python open source (NumPy, SciPy, statsmodels, Matplotlib…), tutto nel browser e tutto sul tuo computer. Questo manuale segue l’ordine in cui si lavora: **aprire i dati → scegliere cosa disegnare → dare lo stile alla figura → analizzare (fit, picchi, statistica…) → esportare**. Ogni passaggio ha un’immagine presa dal programma stesso.

> **Suggerimento:** il manuale è sempre raggiungibile dal pulsante **Manuale** nella barra in alto. Si apre in una nuova scheda, così lo tieni accanto al programma, e segue la lingua del programma (**EN / IT** in alto; in alto a destra nel manuale puoi cambiarla).

> **Nota sulle immagini:** sono le stesse del manuale inglese e mostrano l’interfaccia **in inglese**. Nel testo i nomi di pulsanti e menu sono quelli **italiani** dell’interfaccia italiana; dove può servire, il nome inglese che vedi nell’immagine è dato tra parentesi, per esempio **Apri file** (*Open files*).

## 1. Prima di cominciare

### 1.1 Avviare π-plotter

1. Installa una volta **Python 3.10 o successivo** ([python.org/downloads](https://www.python.org/downloads/)).
2. Avvia il programma:
  - **macOS**: doppio clic su `start_piplotter.command` (la prima volta: clic destro › **Apri** › **Apri**).
  - **Windows**: doppio clic su `start_piplotter.bat`.
  - **Linux** o qualunque sistema: `python3 start_piplotter.py`.
3. Si apre una finestra del terminale e il browser mostra π-plotter su `http://127.0.0.1:8770`. **Tieni aperta la finestra del terminale** mentre lavori; `Ctrl+C` al suo interno chiude il programma.
4. Solo la prima volta, la pagina propone di installare NumPy, pandas e Matplotlib (circa 80 MB). Premi **Installa e avvia**; una barra mostra l’avanzamento. Vanno nell’ambiente privato di π-plotter (la cartella `.venv`), mai nel Python di sistema.

Tutto gira sul tuo computer: il servizio ascolta solo su `127.0.0.1` e i tuoi file non ne escono. Solo l’installazione dei moduli (da PyPI) usa internet.

### 1.2 La finestra principale

![La finestra principale di π-plotter, con le aree numerate](img/window.png "La finestra principale. 1 Dati · 2 Variabili · 3 Tipi di grafico · 4 Figura e tabella dati · 5 Analisi · 6 Esporta · 7 Dimensioni, stile, testi, assi e legenda.")

La finestra ha tre colonne:

| Numero | Area | A cosa serve |
|---|---|---|
| 1 | **Dati** (a sinistra) | Aprire file, dati di esempio, elenco dei file caricati, opzioni di importazione. |
| 2 | **Variabili** (a sinistra) | Quale colonna è X, quali sono Y, colonne di errore, raggruppamento, come si combinano più file. |
| 3 | **Tipi di grafico** (in alto al centro) | Una barra di 27 tipi di grafico; il programma ne suggerisce uno (★). |
| 4 | **Figura / Tabella dati** (al centro) | La figura com’è quando la esporti; una seconda scheda mostra i dati. Accanto compaiono le schede dei risultati delle analisi. |
| 5 | **Analisi** (a destra) | Scegli un’analisi, imposta i parametri, eseguila, leggi i numeri. |
| 6 | **Esporta** (a destra) | Formato, risoluzione, nome del file. |
| 7 | **Dimensioni e impaginazione, Stile e colori, Serie, Testi e caratteri, Assi e tacche, Legenda** (a destra) | Tutto ciò che cambia l’aspetto della figura. |

Nella barra in alto: **Nuovo** inizia una nuova analisi (chiude dati, figura e risultati ma tiene il tuo stile), **Moduli** gestisce i moduli Python, **Manuale** apre questo manuale, **ⓘ** mostra licenze e cosa citare, **EN / IT** cambia lingua e il pulsante sole/luna passa dalla modalità chiara a quella scura.

## 2. Passo 1 — Apri i dati

### 2.1 Aprire un file

Premi **Apri file** (*Open files*) nel riquadro *Dati*, oppure **trascina uno o più file in un punto qualsiasi della pagina**.

![I riquadri Dati e Variabili dopo aver aperto l’esempio Spettri](img/data_panel.png "Il riquadro Dati (in alto) e il riquadro Variabili (in basso). Il file caricato compare nell’elenco con le sue dimensioni: 801 righe × 4 colonne.")

π-plotter legge CSV, TSV, TXT e DAT (separatore, virgola decimale, intestazione, righe di commento e codifica del testo vengono riconosciuti da soli), Excel (`.xlsx`, `.xls`), LibreOffice `.ods`, JSON, Parquet, Feather, ORC, HDF5, NetCDF, MATLAB `.mat`, NumPy `.npy/.npz`, FITS, SPSS, Stata, SAS, XML, tabelle HTML, SQLite, **spettri JCAMP-DX** (`.jdx`, `.dx`) e file ZIP o compressi (`.gz`, `.bz2`, `.xz`).

* Se un formato richiede un modulo facoltativo (per esempio `openpyxl` per Excel), una piccola finestra propone di installarlo, con una barra di avanzamento. Premi **Installa**; a installazione finita il file si può aprire.
* Un file con più tabelle (fogli di Excel, dataset HDF5, tabelle SQLite…) mostra sotto gli esempi un elenco **Tabella / foglio / dataset**: scegli quella che vuoi.
* L’elenco **File caricati** mostra ogni file con righe × colonne. Clicca un nome per mostrare quel file; clicca **✕** per toglierlo.

> **Suggerimento — non hai dati sotto mano?** I pulsanti **Esempi** (*Spettri, Spettro IR, Cinetica, Gruppi, Superficie, Nuvola di punti*) caricano piccoli insiemi di dati sintetici. Tutte le immagini di questo manuale li usano, così puoi ripetere ogni passaggio esattamente.

### 2.2 Quando il file non viene letto bene

Apri **Opzioni di importazione** (*Import options*; compaiono sotto gli esempi per i file di testo).

![Opzioni di importazione per un CSV all’italiana](img/import_options.png "Opzioni di importazione: separatore, separatore decimale, riga di intestazione e righe da saltare. Il file qui usa punto e virgola e virgole decimali; π-plotter li aveva già riconosciuti.")

1. Cambia **Separatore** (virgola, punto e virgola, tab, barra, spazi) e **Separatore decimale** se le colonne sono sbagliate.
2. Imposta **Riga di intestazione** (o *nessuna*) e **Righe da saltare** se il file comincia con delle note.
3. Premi **Applica**.

Se vengono trovati numeri con il separatore delle migliaia (per esempio `1,234.5`), π-plotter chiede se **Convertire in numeri**; altrimenti quelle righe mancherebbero nei grafici numerici.

### 2.3 Guarda i dati

La scheda **Tabella dati** (*Data table*) mostra le prime righe con il tipo di ogni colonna (`float64`, `int64`, testo, data…). Controlla qui che i numeri siano numeri.

![La scheda Tabella dati](img/data_table.png "La scheda Tabella dati: i nomi delle colonne, i loro tipi e i valori.")

### 2.4 Più file insieme

Apri (o trascina) più file insieme e vengono disegnati **nello stesso grafico**, con un colore e una voce di legenda per file. La sezione **Combina file** (*Combine files*) del riquadro *Variabili* permette di scegliere quali file, colonne e colonne di errore includere, oppure di passare a **Un pannello per file** (*One panel per file*).

![Riquadro Combina file con due file](img/combine_panel.png "Combina file: Stesso grafico o Un pannello per file, con assi condivisi, lettere dei pannelli e nomi dei file come titoli.")

![Due file disegnati come due pannelli con le lettere (a) e (b)](img/combine_figure.png "Un pannello per file, con assi condivisi e lettere (a), (b): pronto per una figura a più pannelli da rivista.")

### 2.5 Tabelle molto larghe

Le tabelle con migliaia di colonne (per esempio serie di spettri) vanno bene: ogni elenco di colonne ha **Tutte / Nessuna**, un filtro che accetta anche un intervallo di nomi numerici (`19600-19840`) o di posizioni (`#1-500`), e Maiusc+clic spunta un intero blocco. La mappa di calore disegna tutte le colonne; la matrice di correlazione ne accetta fino a 2000.

## 3. Passo 2 — Scegli le variabili e il tipo di grafico

### 3.1 Variabili

![Il riquadro Variabili per l’esempio Cinetica](img/variables.png "Variabili: Asse X, Asse Y (spunta una o più colonne), Asse Y secondario, Raggruppa per (colore).")

* **Asse X** — la colonna sull’asse orizzontale.
* **Asse Y (una o più)** — spunta ogni colonna da disegnare. Ognuna diventa una serie con il suo colore.
* **Asse Y secondario** — colonne disegnate rispetto a un secondo asse a destra (per esempio temperatura e concentrazione nello stesso grafico).
* **Raggruppa per (colore)** — una colonna di testo i cui valori dividono i dati in gruppi colorati.
* **Errore X / Errore Y** — compaiono per i tipi di grafico che possono disegnare barre d’errore; scegli la colonna con le incertezze (le colonne chiamate `err`, `std`, `sigma`, `errore`… vengono riconosciute da sole).

### 3.2 Tipi di grafico

![La barra dei tipi di grafico](img/plot_types.png "I 27 tipi di grafico. Le stelle indicano ciò che π-plotter suggerisce per i tuoi dati.")

La barra offre **27 tipi di grafico**: linea, dispersione, gradini, area, barre d’errore, fit (con equazione e R²), stelo, polare, barre, barre orizzontali, box, violino, strip, swarm, torta, istogramma, densità, ECDF, mappa di calore, contorni, esagoni, istogramma 2D, matrice di correlazione, grafico a coppie e tre tipi **3D** (superficie, dispersione 3D, cascata).

Il programma guarda il tipo delle colonne e **suggerisce** il grafico giusto: una ★ segna la prima scelta e i pulsanti **Suggeriti** (*Suggested*) sotto la figura ne propongono qualche altro. Una serie temporale diventa un grafico a linee, una nuvola di punti una dispersione (o esagoni se i punti sono molti), le categorie diventano barre o box, le griglie X-Y-Z contorni o mappe di calore.

> **Suggerimento:** se la figura sembra sbagliata, controlla prima il riquadro **Variabili**: di solito è spuntata una colonna che non dovrebbe esserlo (la colonna X, un contatore, una colonna di errore).

## 4. Passo 3 — Dai alla figura l’aspetto giusto

Tutti i controlli sono nella colonna di destra. La figura viene ridisegnata subito; è sempre disegnata alla sua **dimensione fisica reale**, quindi ciò che vedi è ciò che stamperà la rivista.

### 4.1 Dimensioni, stile, colori, serie

![Riquadri Esporta, Dimensioni e impaginazione e Stile e colori](img/style_basic.png "Esporta, Dimensioni e impaginazione e Stile e colori.")

* **Dimensioni e impaginazione** (*Size & layout*) — scegli un **Formato rivista** (Nature, Science, ACS, Elsevier, RSC, APS, IEEE, pagina di tesi, diapositiva, pannello da poster…) oppure scrivi **Larghezza** e **Altezza** in mm, cm o pollici. Lo sfondo trasparente è una spunta.
* **Stile e colori** (*Style & colours*) — lo **Stile** (pubblicazione pulita, griglia bianca, ggplot, Science / Nature-like / IEEE-like da SciencePlots…), la **Tavolozza colori** (Okabe–Ito e Tol sono sicure per i daltonici) e, per mappe di calore e superfici, la **Mappa di colore**. Qui si impostano per tutte le serie spessore della linea, dimensione del marcatore, opacità, tipo di linea e marcatore.

![Il riquadro Serie](img/style_series.png "Serie: ogni serie ha il suo colore (clicca il quadratino), etichetta, tipo di linea, marcatore e spessore. *ripristina* torna ai valori automatici.")

* **Serie** — cambia colore, etichetta in legenda, tipo di linea, marcatore e spessore di **una** serie. I colori di questo riquadro sono esattamente quelli della figura.

> **Nota:** i nomi delle riviste nei formati descrivono solo la larghezza delle colonne. Sono marchi dei rispettivi titolari, che non sono affiliati a π-plotter.

### 4.2 Testi, assi, legenda

![Il riquadro Testi e caratteri](img/style_text.png "Testi e caratteri: titolo, etichette degli assi, carattere, dimensioni in punti.")

![I riquadri Assi e tacche e Legenda](img/style_axes.png "Assi e tacche e Legenda.")

* **Testi e caratteri** (*Text & fonts*) — titolo ed etichette degli assi (di norma i nomi delle colonne), il carattere e le dimensioni **in punti**. Le formule vanno tra segni di dollaro: `$\alpha$`, `$10^{-3}$`, `$\mu$m`, `$H_2O$`.
* **Assi e tacche** (*Axes & ticks*) — scale lineare, logaritmica o symlog; limiti X/Y (vuoto = automatico); griglia; direzione delle tacche, tacche secondarie e speculari; cornice; notazione scientifica; **Inverti X** (per i numeri d’onda, che si leggono dall’alto verso il basso).
* **Legenda** — mostrata in automatico, sempre o mai; posizione (anche fuori dagli assi); colonne; titolo; cornice.

### 4.3 Zoom, sposta e riscrivi direttamente sulla figura

* **Zoom**: trascina un riquadro sulla figura, o gira la rotella del mouse. Gli assi vengono ridisegnati per il nuovo intervallo, non solo ingranditi. Maiusc+rotella o un riquadro sottile ingrandisce un solo asse. **↶ Zoom precedente** (*Previous zoom*) torna indietro di un passo, **⤢ Figura intera** mostra tutto (lo stesso fa il doppio clic sul grafico).

![Un riquadro di zoom disegnato sulla figura Spettri](img/zoom_box.png "Trascinando un riquadro sulla figura…")

![La stessa figura dopo lo zoom](img/zoom_done.png "…gli assi vengono ridisegnati per l’intervallo scelto. Il pulsante Zoom precedente compare in alto a destra.")

* **Sposta i testi**: trascina il titolo, un’etichetta degli assi, la legenda, l’etichetta della barra dei colori, l’etichetta di una fetta di torta o di un picco in un altro posto.
* **Riscrivi i testi**: doppio clic su un testo, scrivi il nuovo (formule tra `$…$`) e premi Invio. *Testo originale* e *Posizione originale* ripristinano quelli automatici.

Zoom, testi spostati e riscritti restano in ogni esportazione.

### 4.4 Figure tridimensionali

I tipi 3D sono la **superficie** z(x, y) (da una griglia regolare o da punti sparsi, anche solo reticolo), la **dispersione / linea 3D** e la **cascata** di spettri (una curva per colonna, alla profondità data dal nome della colonna, per esempio un tempo o una temperatura).

![Una superficie 3D](img/surface3d.png "Superficie 3D dall’esempio Superficie. Trascina la figura per ruotarla.")

**Trascina la figura per ruotarla**: una copia leggera dei dati gira in modo fluido nella pagina; al rilascio gli angoli restano e la figura viene ridisegnata con Matplotlib. Il doppio clic torna alla vista predefinita. Gli angoli di vista e i limiti di Z sono anche nel riquadro *Assi e tacche*.

### 4.5 Modelli di stile

**Salva modello di stile** (nel riquadro *Esporta*) scrive tutte le impostazioni di stile in un piccolo file JSON; **Carica modello** le applica a un’altra figura. Serve a dare a un intero articolo lo stesso aspetto.

## 5. Passo 4 — Analizza i dati

### 5.1 Come funziona il riquadro Analisi

Il riquadro **Analisi** è in cima alla colonna di destra. Gli stessi cinque passi valgono per ogni analisi:

1. **Scegli l’analisi** dall’elenco.
2. **Imposta i parametri** (colonne, modello, limiti…). Le colonne sono proposte in base alle tue variabili.
3. Premi **Esegui l’analisi** (*Run analysis*).
4. **Leggi i risultati** sotto il pulsante: una tabella di riepilogo, tabelle dei parametri, frasi in linguaggio semplice e i **riferimenti da citare**. *Copia* e *CSV* esportano ogni tabella.
5. Guarda il risultato sulla figura con **Mostra su una copia del grafico** (*Show on a copy of the figure*), oppure apri un risultato con assi propri (autocorrelazione, spettro di potenza, grafico Q–Q…) con **Traccia il risultato** (*Plot the result*).

![L’elenco delle analisi](img/analysis_list.png "L’elenco delle analisi, a gruppi. Le ricette vengono prima.")

> **Nota:** **la figura originale non viene mai modificata.** Le curve delle analisi sono disegnate su una *copia*, in una scheda accanto a *Figura* (si chiude con **×**). Le analisi eseguite mentre una copia è aperta si aggiungono a quella copia, che ha il proprio stile e si esporta come ogni figura. **← Torna al grafico originale** riporta ai dati.

Le analisi sono raggruppate così:

| Gruppo | Analisi |
|---|---|
| **Ricette** | Distribuzione gaussiana di una colonna · Media di una serie temporale · Equilibratura di una simulazione · I gruppi sono diversi? · Relazione tra due variabili · Fit dei picchi · Cinetica di reazione |
| **Fit** | Fit di curve |
| **Serie temporali e correlazione** | Autocorrelazione (ACF / PACF) · Block averaging · Correlazione incrociata |
| **Statistica** | Statistica descrittiva · Test di normalità e grafico Q–Q · Confronto tra gruppi · Correlazione · Regressione lineare e ANOVA · Fit di distribuzioni |
| **Elaborazione dei segnali** | Smoothing e derivata · Spettro di potenza · Linea di base · Ricerca dei picchi · Assegnazione dei picchi IR · Integrale e area |

Le **Ricette** sono l’ingresso più facile: ognuna concatena più analisi, sceglie valori predefiniti sensati e risponde in parole semplici. Se non sei sicuro, parti da una ricetta.

Ogni analisi usa moduli open source consolidati (SciPy, statsmodels) e ti dà i **riferimenti da citare** insieme ai risultati.

### 5.2 Fit di una curva — esempio svolto (cinetica)

Obiettivo: adattare un decadimento alla concentrazione di un reagente e ottenere la vita media con il suo errore.

1. Premi **Esempi › Cinetica**. Nel riquadro *Variabili* tieni **Time (min)** come X e spunta solo **Concentration (mM)** come Y. Scegli il tipo di grafico **Barre errore** e, come **Errore Y**, **Std. dev. (mM)**.
2. In *Analisi* scegli **Fit di curve**.

![Il modulo del Fit di curve](img/fit_form.png "Il modulo del Fit di curve: dati, X, Y, colonna di errore usata come pesi, modello, valori iniziali, limiti, banda d’errore e intervallo del fit.")

3. Imposta **Errore Y (pesi, facoltativo)** su **Std. dev. (mM)**: i punti con errore maggiore contano di meno.
4. Scegli il **Modello**: esponenziale (anche doppio e stretched/KWW), potenza, gaussiana, lorentziana, Voigt, logistica, Hill, Michaelis–Menten, Arrhenius, seno, polinomi — oppure scrivi **la tua formula** in x, per esempio `a*exp(-x/tau) + c`. Qui: `y = A·exp(−x/τ) + C`.
5. Facoltativo: dai **Valori iniziali** (`tau=10, c=0`) e **Limiti** (`a=0..inf, tau=1..100`) se il fit non converge; scegli la **Banda d’errore della curva** (confidenza 95 % della curva, predizione, o nessuna); restringi l’intervallo con **Fit da x =** e **Fit fino a x =**.
6. Premi **Esegui l’analisi**.

![Risultati del fit](img/fit_result.png "Risultati: bontà del fit e parametri adattati con errori standard e intervalli di confidenza al 95 %.")

Come leggerli:

* **R², R² corretto, RMSE, χ²_red** dicono quanto bene la curva descrive i dati (χ²_red vicino a 1 significa che la dispersione è in accordo con le barre d’errore che hai dato); **AIC** e **BIC** servono a confrontare modelli — più bassi sono, meglio è.
* **Parametri adattati** elenca valore, errore standard, intervallo di confidenza al 95 % ed errore relativo. Qui τ risulta vicino a 14 min, il valore usato per generare l’esempio.

7. Premi **Mostra su una copia del grafico** per disegnare la curva e la sua banda d’errore sopra i dati.

![Il fit disegnato su una copia della figura](img/fit_figure.png "Il fit e la sua banda al 95 % su una copia della figura (scheda «Figura + Fit di curve»). La figura originale resta intatta.")

> **Suggerimento:** il *Fit di curve* adatta anche l’**istogramma di una colonna** (per esempio una gaussiana su una distribuzione di valori): usa **Dati da adattare** per scegliere l’istogramma della colonna (viene scelto da solo quando la figura è un istogramma) e, se vuoi, il numero di **Intervalli dell’istogramma**.

### 5.3 Cinetica di reazione in un clic

La ricetta **Cinetica di reazione (ordine, k, t½)** adatta leggi di ordine zero, uno e due agli stessi dati, le confronta con l’AIC e dà l’ordine migliore, la costante di velocità *k* e il tempo di dimezzamento con gli errori. Scegli il tempo come X, la concentrazione come Y (e la sua colonna di errore come *Errore di y*) e premi **Esegui l’analisi**.

![Risultato della ricetta Cinetica di reazione](img/recipe_kinetics_result.png "Cinetica di reazione: la legge migliore, k e t½ con gli errori, e una tabella che confronta i tre ordini.")

![La legge migliore disegnata sui dati](img/recipe_kinetics_figure.png "La legge migliore (qui il primo ordine) su una copia della figura.")

### 5.4 Spettri e cromatogrammi: linea di base → picchi → fit dei picchi → area

Per ogni segnale con picchi (UV-Vis, IR, Raman, XRD, cromatogrammi…) lavora in quest’ordine: **prima la linea di base, poi l’analisi**.

#### Passo 1 — Linea di base

Scegli **Linea di base**. Di base il programma disegna **una retta sotto il segnale**; puoi anche cliccare tu i punti di ancoraggio, oppure scegliere un metodo che segue un fondo curvo.

![Il modulo della Linea di base](img/baseline_form.png "Il modulo della Linea di base con il valore predefinito: una retta sotto il segnale (Forma 1), e il verso dei picchi riconosciuto dal segnale.")

* **Automatica: retta sotto il segnale (o polinomio)** — il valore predefinito. La retta è adattata ai punti che stanno sulla linea di base; i punti più alti della retta di oltre tre volte il rumore (i picchi) non la sollevano (Mazet et al., 2005). **Forma** dice quanto può curvarsi: **0** un livello piatto, costante; **1** una retta (il valore predefinito); **2–6** un polinomio leggermente curvo per fondi che si piegano. Dove il segnale non ha picchi, il segnale corretto è piatto.
* **Punti di ancoraggio (clic sulla figura)**: premi **Scegli sulla figura** (*Pick on the figure*) e clicca dove il segnale poggia sulla sua linea di base, tra e attorno ai picchi; premi **Esc** o **Fatto** quando hai finito (**Togli l’ultimo** e **Cancella** correggono gli errori). **Ogni clic tiene la sua x e la sua y**, quindi il punto resta esattamente dove l’hai cliccato (la casella di testo mostra `x y`, un punto per riga). Un punto scritto con la **sola x** prende l’altezza del segnale lì. Scegli se i punti sono uniti da segmenti di retta o da una curva liscia.
* **Metodi automatici che seguono i fondi curvi**: *arPLS*, *minimi quadrati asimmetrici*, *SNIP* o *elastico*. Cambia **Rigidità** (più bassa segue di più il segnale) o **Asimmetria** se la linea sale dentro picchi larghi.
* **I picchi sono rivolti**: in su (assorbanza, conteggi, intensità) o in giù (trasmittanza, avvallamenti). Con **riconoscilo dal segnale** il programma decide dalla forma dei dati: per uno spettro in trasmittanza come l’esempio la linea di base viene disegnata **sopra** gli avvallamenti, lungo il bordo superiore dello spettro.

Altre due scelte decidono ciò che ottieni:

* **Correzione** — come la linea di base viene tolta dal segnale. *Automatica* **divide** uno spettro in trasmittanza (o riflettanza) per la sua linea di base, T / T₀ × 100, così lo spettro corretto resta in % con la linea di base al 100 % e le bande profonde come prima; per ogni altro segnale la linea di base viene **sottratta**, quindi sta a 0. Puoi anche forzare *sottrai* o *dividi*.
* **Mostra anche lo spettro prima della correzione, con la sua linea di base** — spenta di default.

Premi **Esegui l’analisi**, poi il pulsante verde sotto i risultati:

* Con l’opzione **spenta** (il valore predefinito) il pulsante è **Traccia il risultato**: una nuova scheda mostra **solo lo spettro corretto**, con la linea di base corretta come linea punteggiata (al 100 % o a 0). La figura originale non viene toccata.

![Lo spettro corretto da solo](img/baseline_figure.png "Trasmittanza IR divisa per la sua retta di base: lo spettro corretto è in %, piatto al 100 % (punteggiato) tra le bande, che mantengono la loro profondità.")

* Con l’opzione **accesa** il pulsante è **Mostra su una copia del grafico**: la copia mostra lo spettro prima della correzione, la sua linea di base (tratteggiata) e i punti di ancoraggio, e lo spettro corretto, così li puoi confrontare. *Traccia il risultato* dà le stesse curve in una figura a parte.

![Prima e dopo la correzione sugli stessi assi](img/baseline_original.png "Con «Mostra anche lo spettro prima della correzione»: lo spettro originale, la sua linea di base (tratteggiata) e lo spettro corretto insieme.")

> **Nota:** lo spettro corretto è un nuovo insieme di dati: nella sua scheda puoi dargli uno stile, esportarlo o analizzarlo ancora. La sua **Tabella dati** contiene x, il segnale originale, la linea di base e il segnale corretto.

I risultati dicono anche in che verso puntano i picchi, quale correzione è stata usata e quanti punti stanno dalla parte sbagliata della linea di base; oltre il 5 % il programma avverte che la linea taglia il segnale lì.

*Ricerca dei picchi*, *Fit dei picchi* e *Integrale* propongono poi la stessa linea di base già selezionata, così altezze, larghezze e aree sono misurate **sopra di essa**.

#### Passo 2 — Ricerca dei picchi

Scegli **Ricerca dei picchi**. Trova i picchi per **prominenza** (usa **Prominenza minima** per ignorare il rumore; vuoto significa il 5 % dell’intervallo) e riporta posizione, altezza, FWHM e area sopra la linea di base. Usa **Solo da x / fino a x** per restringere l’intervallo, o **Cerca i minimi** per gli avvallamenti. La **posizione è scritta sopra ogni picco**; le etichette affollate si spostano di lato con una linea di richiamo.

![Risultato della ricerca dei picchi](img/peaks_result.png "Ricerca dei picchi: una tabella con posizione, altezza, FWHM e area di ogni picco.")

![Picchi segnati sulla figura](img/peaks_figure.png "I picchi sono segnati e le loro posizioni scritte sopra.")

#### Passo 3 — Fit dei picchi

La ricetta **Fit dei picchi (spettri, cromatogrammi)** trova i picchi e li **adatta tutti insieme** con forme gaussiane o lorentziane (**Forma dei picchi**): centro, altezza, FWHM e area di ogni picco, con gli errori. Ogni picco resta dentro la sua regione. Come **Linea di base** puoi scegliere anche una retta o una costante adattate insieme ai picchi.

![Risultato della ricetta Fit dei picchi](img/peak_fit_result.png "Fit dei picchi: un riepilogo, i picchi adattati con gli errori e le statistiche del fit.")

![I picchi adattati](img/peak_fit_figure.png "Il fit (somma dei picchi), i singoli picchi (punteggiati) e le posizioni dei picchi sopra di essi.")

> **Nota:** gli errori sulle aree ignorano la correlazione tra altezza e larghezza (sono approssimati), e gli errori sono condizionati alla linea di base, che viene sottratta e non adattata.

#### Passo 4 — Integrale

**Integrale e area** dà l’area sotto la curva tra due valori di x (**Da x / A x**) e l’integrale cumulativo, volendo sopra la stessa linea di base.

### 5.5 Assegnazione dei picchi IR

Su uno spettro nel medio infrarosso (assorbanza o trasmittanza; numero d’onda in cm⁻¹, o lunghezza d’onda in µm o nm) l’**Assegnazione dei picchi IR** trova i picchi ed elenca per ognuno i **gruppi candidati** da una tabella di circa 110 bande caratteristiche: gruppi organici, e anioni inorganici e minerali (carbonati, solfati, silicati, ossalati…) per la scienza dei materiali e la conservazione.

1. Premi **Esempi › Spettro IR**, o apri il tuo spettro.
2. Scegli **Assegnazione dei picchi IR**. Il programma riconosce da solo trasmittanza o assorbanza e l’unità (**Lo spettro è**, **Unità di x** = *riconoscila*); cambiali se serve.
3. **Confronta con** sceglie la tabella: *tutta la tabella*, *gruppi organici* o *anioni inorganici e minerali*; **Gruppi organici con** è *solo C, H, O, N* a meno che tu scelga *anche S, P, Si, alogeni*.
4. Premi **Esegui l’analisi**, poi **Mostra su una copia del grafico**.

![Risultato dell’assegnazione dei picchi IR](img/ir_result.png "Assegnazione dei picchi IR: per ogni picco, i gruppi candidati con la loro affidabilità; e i gruppi che spiegano più picchi.")

![Picchi assegnati sullo spettro](img/ir_figure.png "Ogni picco ha un’etichetta, per esempio «1738 C=O» (un «?» segna uno incerto).")

I candidati sono ordinati per intervallo della banda, intensità e larghezza, e per le altre bande che lo stesso gruppo richiede: il C–O di un estere solo con il C=O di un estere, un etere arilico solo con un anello aromatico, i gruppi organici solo con bande C–H.

> **Importante:** sono **candidati, non prove**. Conferma con spettri di riferimento. La tabella delle bande (`BANDS` in `piplotter/analyses/ir_assign.py`) si può modificare con **Personalizza…**; le sue fonti sono elencate in `REFERENCES.md`.

### 5.6 Simulazioni e serie temporali

#### Equilibratura di una simulazione (MD, Monte Carlo)

Per una traiettoria (energia, densità, RMSD…) la ricetta **Equilibratura di una simulazione** trova automaticamente **da dove la serie è equilibrata** e dà la media della parte equilibrata **con il suo vero errore**. Scegli la serie (e la colonna del tempo) e premi **Esegui l’analisi**.

![Risultato della ricetta di equilibratura](img/equilibration_result.png "Equilibratura: inizio della parte equilibrata, la sua media con l’errore corretto e il numero di campioni indipendenti.")

![La parte equilibrata](img/equilibration_figure.png "La linea punteggiata segna l’inizio dell’equilibrio; la linea tratteggiata è la media del resto, con la sua banda ±SEM.")

L’inizio è scelto con il metodo di Chodera (2016): conserva il maggior numero possibile di campioni indipendenti.

#### Media di una serie temporale

**Media di una serie temporale (dati correlati)** dà la media con il suo vero errore, il tempo di correlazione e il numero di campioni indipendenti. Usa **Scarta il primo … %** per togliere a mano un periodo di equilibratura.

#### Autocorrelazione e block averaging

I punti consecutivi di una simulazione o di un registro di sensori **non sono indipendenti**, quindi il solito errore della media (SD/√N) è molto troppo piccolo.

* **Autocorrelazione (ACF / PACF)** (le righe devono essere equispaziate) disegna l’ACF con la sua banda di confidenza e dà il tempo di correlazione integrato τ, l’**inefficienza statistica** *g* e il **numero effettivo di campioni** N/g.

![Risultati dell’autocorrelazione](img/acf_result.png "Autocorrelazione: il tempo di correlazione, l’inefficienza statistica g e il numero effettivo di campioni indipendenti. Qui 3000 punti valgono circa 12 campioni indipendenti, quindi il vero errore è circa 16 volte quello ingenuo.")

![La funzione di autocorrelazione](img/acf_figure.png "L’ACF (linea continua), la banda al 95 % (tratteggiata) e il fit esponenziale del decadimento iniziale (punteggiato). Si apre come figura a sé, in una scheda con × per chiuderla.")

* **Block averaging (errore di dati correlati)** (Flyvbjerg–Petersen) mostra come la stima dell’errore cresce con la dimensione del blocco e si stabilizza sul vero errore. Se la curva non raggiunge un plateau, la serie è troppo corta.
* **Correlazione incrociata** confronta due serie in funzione del ritardo e trova il ritardo di migliore corrispondenza.

### 5.7 Statistica

#### Distribuzione gaussiana di una colonna

La ricetta **Distribuzione gaussiana di una colonna** disegna l’istogramma, adatta una gaussiana, controlla la normalità e dà media, σ e FWHM e il **vero errore della media**. **Le righe sono una serie temporale** è spuntata di default, in modo che l’errore della media sia corretto per valori correlati; toglila per misure indipendenti.

![Risultato della ricetta gaussiana](img/gaussian_result.png "Distribuzione gaussiana: i valori, il fit, i test di normalità e l’errore con block averaging.")

![Istogramma con il fit gaussiano](img/gaussian_figure.png "L’istogramma della colonna con il fit gaussiano.")

#### I gruppi sono diversi?

Apri l’esempio **Gruppi**, scegli **Box** come tipo di grafico e la ricetta **I gruppi sono diversi?** con le colonne *Valori* e *Gruppi*. Il test giusto viene scelto **in automatico**: ogni gruppo viene controllato per la normalità (Shapiro–Wilk), poi si usa un t-test di Welch (due gruppi) oppure un’ANOVA a una via con Tukey HSD, oppure, se i dati non sono compatibili con una distribuzione normale, Mann–Whitney o Kruskal–Wallis. La risposta è scritta in parole semplici, con dimensione dell’effetto e confronti a coppie.

![Risultato della ricetta dei gruppi](img/groups_result.png "«I gruppi differiscono in modo significativo (p < 0,001, α = 0,05)», il test scelto, la dimensione dell’effetto, le statistiche per gruppo e la tabella dei confronti a coppie.")

![Box plot dei gruppi](img/groups_figure.png "I gruppi come box plot.")

Per il pieno controllo usa **Confronto tra gruppi (t-test, ANOVA…)**: t-test, Mann–Whitney, Wilcoxon, ANOVA, Alexander–Govern, Kruskal–Wallis, Tukey HSD e dimensioni dell’effetto.

#### Relazione tra due variabili

La ricetta **Relazione tra due variabili** dà la correlazione (Pearson e Spearman, con i p-value), un fit a retta con la sua banda di confidenza e un controllo dei residui.

![Risultato della ricetta della relazione](img/xy_result.png "Relazione tra due variabili: correlazione, pendenza e intercetta, R² e se i residui sono compatibili con una distribuzione normale.")

![Dispersione con la retta](img/xy_figure.png "La retta e la sua banda al 95 % su una copia del grafico a dispersione.")

#### Le analisi singole

| Analisi | A cosa serve |
|---|---|
| **Statistica descrittiva** | N, media, SD, SEM, intervallo di confidenza, mediana, quartili, asimmetria, curtosi; anche separata per una colonna di gruppi. |
| **Test di normalità e grafico Q–Q** | Controllare se un campione è compatibile con una distribuzione normale (quattro test e un grafico Q–Q). |
| **Correlazione** | Matrice di correlazione (Pearson, Spearman, Kendall) con p-value e intervalli di confidenza. |
| **Regressione lineare e ANOVA** | Minimi quadrati ordinari con uno o più predittori o una formula come `y ~ x + C(group)`; coefficienti, p-value, R², AIC, tabella ANOVA e diagnostica. |
| **Fit di distribuzioni** | Fit di massima verosimiglianza di più distribuzioni; la migliore per AIC; istogramma con le densità. |
| **Smoothing e derivata** | Savitzky–Golay (con derivata prima / seconda), media mobile o filtro gaussiano. |
| **Spettro di potenza** | Contenuto in frequenza di un segnale equispaziato (FFT o Welch) e sue frequenze dominanti. |

## 6. Passo 5 — Esporta

![Il riquadro Esporta](img/export_card.png "Il riquadro Esporta: formato, risoluzione, nome del file, il pulsante Esporta figura e i pulsanti dei modelli di stile.")

1. Scegli il **Formato**:
  - **PNG**, **TIFF (LZW, per le riviste)**, **JPEG** — immagini raster a 150, 300, 600 o 1200 **DPI**;
  - **PDF**, **SVG**, **EPS** — formati vettoriali; il testo resta modificabile (i caratteri sono incorporati come TrueType);
  - **HTML interattivo** — una pagina creata con Plotly (zoom, valori al passaggio del mouse) che si apre in qualsiasi browser;
  - **Script Python (.zip)** — i dati, le impostazioni, uno script e i riferimenti: **ricrea la figura senza π-plotter** (`python make_figure.py`).
2. Scrivi un **Nome del file**.
3. Premi **Esporta figura**. Il file va nella cartella dei download del tuo browser.

La riga sotto il pulsante dice la dimensione: per esempio *1050 × 790 px a 300 DPI*, oppure *Formato vettoriale: nitido a qualsiasi dimensione*.

> **Suggerimento:** la figura esportata ha esattamente la dimensione fisica che hai scelto in *Dimensioni e impaginazione*. Una copia con le curve delle analisi si esporta come ogni altra figura: seleziona prima la sua scheda.

### Come citare

![La finestra Informazioni con licenze e riferimenti](img/about_dialog.png "La finestra ⓘ: la licenza di π-plotter, come citare, e ogni modulo con la sua licenza e il suo riferimento.")

Nei metodi del tuo articolo cita Matplotlib e gli altri moduli usati per la figura. Il pulsante **ⓘ** elenca ogni modulo con la sua licenza e il riferimento da citare, e ogni esportazione *Script Python* include un `REFERENCES.txt` con esattamente quei riferimenti. I risultati delle analisi mostrano i riferimenti dei metodi usati.

## 7. Plugin e moduli

### 7.1 Le tue analisi (plugin)

Ogni analisi è un piccolo plugin Python. In fondo al riquadro *Analisi*:

* **Personalizza…** (accanto alla descrizione di un’analisi inclusa) apre una copia modificabile;
* **Nuovo plugin** chiede un nome e apre un modello;
* **Cartella plugin** apre la cartella dove stanno i tuoi plugin (`~/.piplotter/plugins/`), che sopravvive agli aggiornamenti;
* **⟳** ricarica i plugin dopo che hai modificato un file altrove.

![L’editor dei plugin](img/plugin_editor.png "L’editor dei plugin con il modello di una nuova analisi. Salva e ricarica la fa comparire nell’elenco delle analisi.")

Un plugin dichiara i suoi parametri in un dizionario `PLUGIN` e implementa `run(df, p, ctx)`. Scrivi ciò che vuoi mostrare con `ctx.result()` (valori, tabelle, testo, riferimenti, un insieme di dati da disegnare). La guida completa, con esempi, è in `PLUGINS.md`.

> **Attenzione:** i plugin sono codice Python che gira con i tuoi permessi. Installa solo plugin di cui ti fidi.

### 7.2 Moduli Python

Il pulsante **Moduli** elenca ogni modulo che π-plotter può usare, con la sua licenza e la versione installata.

![La finestra Moduli](img/modules_dialog.png "Moduli: di base, motori grafici, analisi e statistica, stili… Ognuno ha la sua versione e un controllo «import OK».")

* A ogni avvio il programma controlla su PyPI le versioni più recenti (*Controlla aggiornamenti*; **Aggiorna tutti** con un clic). I moduli mancanti vengono proposti quando una funzione ne ha bisogno.
* **Verifica import** carica ogni modulo in un Python separato: uno che non si carica è mostrato in rosso con il suo errore e un pulsante **Reinstalla**.
* **I tuoi moduli (da PyPI)**: scrivi il nome di un pacchetto qualsiasi e premi **Controlla**; π-plotter chiede a pip cosa installerebbe (per ora non cambia nulla) e mostra ogni pacchetto con la sua **licenza**. Le licenze open source si installano normalmente; ogni altra licenza richiede una spunta su *«Ho letto le condizioni di licenza…»*. Dopo l’installazione il modulo viene importato **con i suoi sottomoduli**; se non è utilizzabile viene **tolto di nuovo**, insieme a ciò che era arrivato con lui, e vedi il perché. Un modulo che si importa è disponibile ai plugin; la sua icona compare in fondo alla barra dei tipi di grafico, con l’elenco delle sue funzioni.

> **Attenzione:** i moduli che aggiungi sono codice di terze parti che π-plotter non controlla. Installa solo ciò di cui ti fidi. Il controllo della licenza legge i metadati del pacchetto: è un aiuto, non una consulenza legale.

## 8. Domande e problemi

| Problema | Cosa fare |
|---|---|
| La pagina dice che il servizio non risponde | La finestra del terminale è stata chiusa. Riavvia π-plotter. |
| *«Questa pagina appartiene a un’altra sessione o versione di π-plotter»* | Premi **Ricarica** nella barra rossa. |
| Un file si apre con una sola colonna o numeri strani | Apri **Opzioni di importazione** e scegli separatore e separatore decimale. |
| La figura mostra colonne che non volevo | Togli la spunta in **Asse Y** (e controlla che X non sia spuntata). |
| La linea di base taglia il segnale o segue i picchi | Usa il valore predefinito *retta sotto il segnale* (Forma 0 o 1), controlla **I picchi sono rivolti** (in su o in giù), oppure clicca punti di ancoraggio dove il segnale sta sulla sua linea di base. |
| Un fit non converge o dà valori assurdi | Dai **Valori iniziali** e **Limiti**, restringi **Fit da / fino a**, oppure prova un modello più semplice. |
| I picchi vengono persi o il rumore è segnato come picco | Cambia **Prominenza minima**; sottrai prima una linea di base. |
| Un modulo è rosso in *Moduli* | Premi **Reinstalla**; il motivo è mostrato sotto il nome. |
| Dopo aver aggiornato i moduli il programma chiede di riavviare | Premi **Riavvia ora**. |

Gli errori vengono stampati anche nella finestra del terminale.

## 9. Su questo manuale

Questo manuale fa parte del programma: i testi sono i file `manual/MANUAL.md` (inglese) e `manual/MANUAL.it.md` (italiano), le immagini sono in `manual/img/` e sono **le stesse per le due lingue**; il programma le mostra con il pulsante **Manuale** (`/manual`, o `/manual?lang=it` per l’italiano).

**Per aggiornare il testo**, modifica i due file (mantieni gli stessi titoli e le stesse immagini nello stesso ordine: un test controlla che le due versioni coincidano). Si usa un piccolo sottoinsieme di Markdown: titoli (`##`, `###`), paragrafi, elenchi, tabelle, riquadri `> **Suggerimento:**` / `**Nota:**` / `**Attenzione:**` / `**Importante:**`, `![didascalia](img/nome.png "didascalia lunga")` per le immagini, `**grassetto**`, `*corsivo*`, `` `codice` `` e `[link](url)`. Non serve riavviare: ricarica la pagina.

**Per ridisegnare le immagini** dopo che cambiano l’interfaccia o un’analisi:

```
pip install playwright
.venv/bin/python tools/make_manual_images.py
```

Lo strumento avvia una sua copia di π-plotter (con una cartella di stato temporanea, così i tuoi plugin e moduli non vengono toccati), la pilota in un Chrome senza finestra, in inglese e in modalità chiara, e salva ogni immagine. `--only fit,ir` ridisegna solo quelle; per aggiungerne una scrivi una funzione con `@shot('nome')` nello strumento e richiamala come `img/nome.png` in entrambi i manuali. I numeri nel testo che vengono dagli esempi (per esempio τ ≈ 14 min) vanno ricontrollati dopo aver ridisegnato.

### Storia delle revisioni

| Versione | Modifiche al manuale |
|---|---|
| 0.2.3 | Prima edizione in italiano, con le stesse immagini del manuale inglese. |
