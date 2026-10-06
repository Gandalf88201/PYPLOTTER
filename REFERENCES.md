# References / Riferimenti

PyPlotter is a front end: the figures are drawn by open-source scientific Python packages.
When a figure made with PyPlotter is published, cite the packages that drew it — at least
Matplotlib, NumPy and pandas, plus any optional module the figure used. The **Python script
(.zip)** export writes a `REFERENCES.txt` with exactly the references a figure needs.

PyPlotter è un'interfaccia: le figure sono disegnate da pacchetti Python scientifici open source.
Quando pubblichi una figura fatta con PyPlotter, cita i pacchetti che l'hanno prodotta — almeno
Matplotlib, NumPy e pandas, più i moduli facoltativi usati. L'esportazione **Script Python (.zip)**
scrive un `REFERENCES.txt` con esattamente i riferimenti necessari.

## Core / Base

- **Matplotlib** — Hunter, J. D. Matplotlib: A 2D Graphics Environment. *Computing in Science & Engineering* 9, 90–95 (2007). doi:10.1109/MCSE.2007.55
- **NumPy** — Harris, C. R. et al. Array programming with NumPy. *Nature* 585, 357–362 (2020). doi:10.1038/s41586-020-2649-2
- **pandas** — McKinney, W. Data Structures for Statistical Computing in Python. *Proc. 9th Python in Science Conf.*, 56–61 (2010). doi:10.25080/Majora-92bf1922-00a; The pandas development team, *pandas-dev/pandas*, Zenodo. doi:10.5281/zenodo.3509134

## Optional modules / Moduli facoltativi

- **statsmodels** — Seabold, S. & Perktold, J. statsmodels: Econometric and statistical modeling with Python. *Proc. 9th Python in Science Conf.*, 92–96 (2010). doi:10.25080/Majora-92bf1922-011
- **SciPy** — Virtanen, P. et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nature Methods* 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2
- **seaborn** — Waskom, M. L. seaborn: statistical data visualization. *Journal of Open Source Software* 6(60), 3021 (2021). doi:10.21105/joss.03021
- **Plotly** — Plotly Technologies Inc. *Collaborative data science*. Montréal, QC (2015). https://plot.ly
- **SciencePlots** — Garrett, J. D. *SciencePlots*. Zenodo (2021). doi:10.5281/zenodo.4106649
- **cmcrameri / Scientific colour maps** — Crameri, F. *Scientific colour maps*. Zenodo (2018). doi:10.5281/zenodo.1243862; Crameri, F., Shephard, G. E. & Heron, P. J. The misuse of colour in science communication. *Nature Communications* 11, 5444 (2020). doi:10.1038/s41467-020-19160-7
- **xarray** — Hoyer, S. & Hamman, J. xarray: N-D labeled Arrays and Datasets in Python. *Journal of Open Research Software* 5(1), 10 (2017). doi:10.5334/jors.148
- **Astropy** — Astropy Collaboration. The Astropy Project: Sustaining and Growing a Community-oriented Open-source Project and the Latest Major Release (v5.0) of the Core Package. *ApJ* 935, 167 (2022). doi:10.3847/1538-4357/ac7c74
- **h5py** — Collette, A. *Python and HDF5*. O'Reilly (2013).
- openpyxl, xlrd, odfpy, PyArrow, PyTables, netCDF4, pyreadstat and lxml do not ask for a specific citation; see their licences in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Colour palettes and colour maps / Tavolozze e mappe di colore

- **Okabe–Ito** palette — Okabe, M. & Ito, K. *Color Universal Design (CUD): how to make figures and presentations that are friendly to colorblind people* (2008). https://jfly.uni-koeln.de/color/
- **Tol** palettes (bright, vibrant, muted) — Tol, P. *Colour Schemes*. SRON Technical Note SRON/EPS/TN/09-002, issue 3.2 (2021). https://personal.sron.nl/~pault/
- **viridis, plasma, inferno, magma** — van der Walt, S. & Smith, N. *mpl colormaps* (2015). https://bids.github.io/colormap/
- **cividis** — Nuñez, J. R., Anderton, C. R. & Renslow, R. S. Optimizing colormaps with consideration for color vision deficiency to enable accurate interpretation of scientific data. *PLOS ONE* 13, e0199239 (2018). doi:10.1371/journal.pone.0199239
- **tab10** — Matplotlib's default qualitative cycle (Matplotlib licence).

## Methods used in PyPlotter's own code / Metodi usati nel codice di PyPlotter

- Density curves (KDE): Gaussian kernel with Silverman's rule-of-thumb bandwidth — Silverman, B. W. *Density Estimation for Statistics and Data Analysis*. Chapman & Hall (1986).
- Confidence and prediction bands of non-linear fits: first-order (delta-method) propagation of the parameter covariance, var = J·C·Jᵀ (J by central differences), with Student's t quantile; prediction bands add the residual (or measurement) variance. See e.g. Seber, G. A. F. & Wild, C. J. *Nonlinear Regression*. Wiley (1989).
- Curve fits: ordinary least squares (`numpy.polyfit`); exponential, logarithmic and power-law models are fitted as linear models of the transformed variables, and R² is computed on the original scale.
- JCAMP-DX reader (AFFN form): McDonald, R. S. & Wilks, P. A. JCAMP-DX: A Standard Form for Exchange of Infrared Spectra in Computer Readable Form. *Applied Spectroscopy* 42(1), 151–162 (1988).

## Methods of the built-in analyses / Metodi delle analisi incluse

Each analysis lists its references in the app next to the result; they are collected here.

- Block averaging — Flyvbjerg, H. & Petersen, H. G. Error estimates on averages of correlated data. *J. Chem. Phys.* 91, 461–466 (1989). doi:10.1063/1.457480
- Integrated autocorrelation time, automatic window — Madras, N. & Sokal, A. D. The pivot algorithm: a highly efficient Monte Carlo method for the self-avoiding walk. *J. Stat. Phys.* 50, 109–186 (1988). doi:10.1007/BF01022990
- Stretched exponential (KWW) — Williams, G. & Watts, D. C. Non-symmetrical dielectric relaxation behaviour arising from a simple empirical decay function. *Trans. Faraday Soc.* 66, 80–85 (1970). doi:10.1039/TF9706600080
- Shapiro–Wilk — Shapiro, S. S. & Wilk, M. B. An analysis of variance test for normality (complete samples). *Biometrika* 52, 591–611 (1965). doi:10.1093/biomet/52.3-4.591
- D'Agostino–Pearson — D'Agostino, R. & Pearson, E. S. Tests for departure from normality. *Biometrika* 60, 613–622 (1973). doi:10.1093/biomet/60.3.613
- Anderson–Darling — Anderson, T. W. & Darling, D. A. Asymptotic theory of certain "goodness of fit" criteria based on stochastic processes. *Ann. Math. Stat.* 23, 193–212 (1952). doi:10.1214/aoms/1177729437
- Welch t-test — Welch, B. L. The generalization of "Student's" problem when several different population variances are involved. *Biometrika* 34, 28–35 (1947). doi:10.1093/biomet/34.1-2.28
- Mann–Whitney U — Mann, H. B. & Whitney, D. R. *Ann. Math. Stat.* 18, 50–60 (1947). doi:10.1214/aoms/1177730491
- Kruskal–Wallis — Kruskal, W. H. & Wallis, W. A. Use of ranks in one-criterion variance analysis. *J. Am. Stat. Assoc.* 47, 583–621 (1952). doi:10.1080/01621459.1952.10483441
- Tukey HSD — Tukey, J. W. Comparing individual means in the analysis of variance. *Biometrics* 5, 99–114 (1949). doi:10.2307/3001913
- Effect sizes — Cohen, J. *Statistical Power Analysis for the Behavioral Sciences*, 2nd ed. Lawrence Erlbaum (1988).
- AIC — Akaike, H. A new look at the statistical model identification. *IEEE Trans. Autom. Control* 19, 716–723 (1974). doi:10.1109/TAC.1974.1100705
- Savitzky–Golay filter — Savitzky, A. & Golay, M. J. E. Smoothing and differentiation of data by simplified least squares procedures. *Anal. Chem.* 36, 1627–1639 (1964). doi:10.1021/ac60214a047
- Welch power spectrum — Welch, P. The use of fast Fourier transform for the estimation of power spectra. *IEEE Trans. Audio Electroacoust.* 15, 70–73 (1967). doi:10.1109/TAU.1967.1161901
- Automatic equilibration detection (recipe *Equilibration of a simulation*) — Chodera, J. D. A simple method for automated equilibration detection in molecular simulations. *J. Chem. Theory Comput.* 12, 1799–1805 (2016). doi:10.1021/acs.jctc.5b00784
- Histogram bin width (recipe *Gaussian distribution*) — Freedman, D. & Diaconis, P. On the histogram as a density estimator: L2 theory. *Z. Wahrscheinlichkeitstheorie verw. Gebiete* 57, 453–476 (1981). doi:10.1007/BF01025868

## Journal size presets / Formati rivista

The presets only set common column widths. Journal names are trademarks of their owners, who
are not affiliated with PyPlotter; always check the current author guidelines of the journal.

I formati impostano solo larghezze di colonna comuni. I nomi delle riviste sono marchi dei
rispettivi titolari, non affiliati a PyPlotter; verifica sempre le istruzioni per gli autori.
