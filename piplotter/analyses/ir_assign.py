"""Infrared peak assignment: candidate groups for each band, from a table of characteristic frequencies.

The spectrum is turned into absorbance (A = −log10 T when it is a transmittance) against wavenumber, the
baseline is removed and the peaks are found as in Peak finding. Each peak is compared with BANDS below
(range, expected intensity and width). Candidates are ranked by how narrow their range is, how well the
intensity and the width match, and how strongly other peaks of the spectrum support the same group (an
ester C–O band counts more when an ester C=O band is there too).

They are candidates, not proofs: a table cannot tell overlapping bands apart, and the same range holds
several groups. Confirm the assignments with reference spectra. BANDS holds standard values compiled for
π-plotter from the textbooks and monographs in PLUGIN['references']; to change or extend it, customise
this analysis and edit BANDS (one line per band).
"""
import re

import numpy as np
import pandas as pd

from piplotter import baselines

# Families of bands: name (en, it) and kind — 'o' organic, 'i' inorganic and minerals, 'x' both.
FAMILIES = {
    'alcohol': (('alcohol', 'alcol'), 'o'), 'phenol': (('phenol', 'fenolo'), 'o'),
    'acid': (('carboxylic acid', 'acido carbossilico'), 'o'),
    'carboxylate': (('carboxylate (salt, metal soap)', 'carbossilato (sale, sapone metallico)'), 'x'),
    'ester': (('ester', 'estere'), 'o'), 'ketone': (('ketone', 'chetone'), 'o'), 'aldehyde': (('aldehyde', 'aldeide'), 'o'),
    'anhydride': (('anhydride', 'anidride'), 'o'), 'acyl_chloride': (('acid chloride', 'cloruro acilico'), 'o'),
    'amide': (('amide, protein', 'ammide, proteina'), 'o'), 'urethane': (('urethane', 'uretano'), 'o'),
    'amine': (('amine', 'ammina'), 'o'), 'imine': (('imine', 'immina'), 'o'), 'nitrile': (('nitrile', 'nitrile'), 'o'),
    'isocyanate': (('isocyanate', 'isocianato'), 'o'), 'isothiocyanate': (('isothiocyanate', 'isotiocianato'), 'o'),
    'azide': (('azide', 'azide'), 'o'), 'nitro': (('nitro compound', 'nitrocomposto'), 'o'),
    'nitrate_ester': (('nitrate ester (e.g. nitrocellulose)', 'estere nitrico (es. nitrocellulosa)'), 'o'),
    'alkane': (('alkyl chain (CH₂, CH₃)', 'catena alchilica (CH₂, CH₃)'), 'o'), 'alkene': (('alkene', 'alchene'), 'o'),
    'alkyne': (('alkyne', 'alchino'), 'o'), 'aromatic': (('aromatic ring', 'anello aromatico'), 'o'),
    'ether': (('ether', 'etere'), 'o'), 'epoxide': (('epoxide', 'epossido'), 'o'),
    'halide': (('organic halide', 'alogenuro organico'), 'o'), 'thiol': (('thiol', 'tiolo'), 'o'),
    'sulfoxide': (('sulfoxide', 'solfossido'), 'o'),
    'sulfonyl': (('sulfone, sulfonamide, sulfonate', 'solfone, solfonammide, solfonato'), 'o'),
    'phosphorus': (('organophosphorus (P=O, P–O–C)', 'organofosforato (P=O, P–O–C)'), 'o'),
    'silane': (('silane (Si–H)', 'silano (Si–H)'), 'x'), 'silicone': (('silicone, siloxane', 'silicone, silossano'), 'o'),
    'carbonyl_metal': (('metal carbonyl', 'metallo-carbonile'), 'x'),
    'cyanide': (('hexacyanoferrate (e.g. Prussian blue)', 'esacianoferrato (es. blu di Prussia)'), 'i'),
    'water': (('water', 'acqua'), 'x'), 'carbonate': (('carbonate (e.g. calcite)', 'carbonato (es. calcite)'), 'i'),
    'sulfate': (('sulfate (e.g. gypsum)', 'solfato (es. gesso)'), 'i'), 'nitrate': (('nitrate', 'nitrato'), 'i'),
    'phosphate': (('phosphate (e.g. apatite)', 'fosfato (es. apatite)'), 'i'),
    'silicate': (('silicate, silica (e.g. quartz, clays)', 'silicato, silice (es. quarzo, argille)'), 'i'),
    'clay': (('clay mineral (Al–OH)', 'minerale argilloso (Al–OH)'), 'i'),
    'oxalate': (('metal oxalate', 'ossalato metallico'), 'i'), 'ammonium': (('ammonium', 'ammonio'), 'i'),
    'artefact': (('atmospheric CO₂ (artefact)', 'CO₂ atmosferica (artefatto)'), 'x'),
}

# Companion bands: a band that only counts together with another one (an ester C–O band with an ester
# C=O band, an aryl ether with the bands of an aromatic ring). Each is a list of alternatives
# (from, to cm⁻¹, minimum intensity relative to the strongest peak); without any of them in a range the
# spectrum covers, the band is ranked much lower.
ESTER_CO = [(1800, 1715, 0.3)]
ACID_CO = [(1725, 1680, 0.3)]
ALDEHYDE_CO = [(1740, 1685, 0.3)]
ANHYDRIDE_HIGH = [(1850, 1800, 0.2)]
AMIDE_I = [(1695, 1630, 0.2)]
CARBOXYLATE_ASYM = [(1620, 1510, 0.2)]
OXALATE_CO = [(1650, 1600, 0.3)]
NITRO_ASYM = [(1570, 1500, 0.2)]
NITRATE_ESTER_ASYM = [(1660, 1625, 0.2)]
OH_STRETCH = [(3600, 3150, 0.05)]
CH_STRETCH = [(2990, 2840, 0.05)]
AROMATIC_RING = [(1625, 1575, 0.03), (1525, 1470, 0.03)]
AROMATIC = AROMATIC_RING + [(3100, 3000, 0.02)]
ALKENE = [(1680, 1620, 0.03), (3100, 3010, 0.03)]
ALKYNE_CH = [(3330, 3260, 0.1)]
CARBONATE_V3 = [(1510, 1390, 0.5)]
SULFATE_V3 = [(1210, 1040, 0.5)]
NITRATE_V3 = [(1410, 1340, 0.3)]
PHOSPHATE_V3 = [(1120, 940, 0.5)]
SILICATE_V3 = [(1200, 950, 0.3)]
SILOXANE = [(1130, 1000, 0.3)]
CO2_STRETCH = [(2380, 2300, 0.02)]
NH_STRETCH = [(3500, 3300, 0.03)]
NH4_STRETCH = [(3300, 3000, 0.1)]
NITRATE_ESTER_SYM = [(1285, 1270, 0.2)]
NITRO_SYM = [(1390, 1300, 0.2)]
OXALATE_CO_SYM = [(1335, 1310, 0.2)]
CARBONATE_BENDS = [(890, 850, 0.05)]
SULFATE_V4 = [(680, 580, 0.05)]
PHOSPHATE_V4 = [(620, 540, 0.05)]
CARBOXYLATE_SYM = [(1450, 1360, 0.1)]
ALKENE_CC = [(1680, 1620, 0.03), (1000, 880, 0.1)]
ALKENE_CH = [(3100, 3010, 0.02), (1000, 880, 0.1)]
ALKYNE_CC = [(2260, 2100, 0.01), (700, 610, 0.1)]
EPOXIDE_RING = [(1280, 1230, 0.1)]
WATER_BEND = [(1700, 1600, 0.05)]
ALDEHYDE_CH = [(2860, 2700, 0.02)]
URETHANE_NH = [(1550, 1510, 0.1)]

# One band per line: range (cm⁻¹), expected intensity (s strong, m medium, w weak, v variable), width
# ('broad', 'sharp' or '' for either), short label for the figure, vibration (en, it), family, note (en, it)
# and, for some, the companion bands it needs.
BANDS = [
    # O–H, N–H and C–H stretching
    (3650, 3580, 'm', 'sharp', 'O–H', ('O–H stretch, free', 'stiramento O–H libero'), 'alcohol',
     ('dilute solutions or gas: no hydrogen bonds', 'soluzioni diluite o gas: senza legami a idrogeno')),
    (3550, 3200, 'v', 'broad', 'O–H', ('O–H stretch, hydrogen-bonded', 'stiramento O–H con legami a idrogeno'), 'alcohol',
     ('alcohols and phenols; also water (with a band near 1640)', 'alcoli e fenoli; anche acqua (con una banda vicino a 1640)')),
    (3600, 3200, 'v', 'broad', 'O–H', ('O–H stretch of water', 'stiramento O–H dell’acqua'), 'water',
     ('moisture and hydrates (gypsum near 3545 and 3400)', 'umidità e idrati (gesso vicino a 3545 e 3400)'), WATER_BEND),
    (3700, 3615, 'm', 'sharp', 'Al–OH', ('O–H stretch of structural hydroxyls', 'stiramento O–H degli ossidrili strutturali'), 'clay',
     ('kaolinite: several sharp bands at 3695–3620', 'caolinite: più bande strette a 3695–3620')),
    (3300, 2500, 's', 'broad', 'O–H', ('O–H stretch of carboxylic acid dimers', 'stiramento O–H dei dimeri degli acidi carbossilici'), 'acid',
     ('very broad, under the C–H bands', 'molto larga, sotto le bande C–H'), ACID_CO),
    (3500, 3300, 'm', 'sharp', 'N–H₂', ('N–H stretch, primary amine (two bands)', 'stiramento N–H, ammina primaria (due bande)'), 'amine', None),
    (3350, 3310, 'w', 'sharp', 'N–H', ('N–H stretch, secondary amine', 'stiramento N–H, ammina secondaria'), 'amine', None),
    (3500, 3150, 's', 'broad', 'N–H', ('N–H stretch of amides', 'stiramento N–H delle ammidi'), 'amide',
     ('primary amides: two bands near 3350 and 3180', 'ammidi primarie: due bande vicino a 3350 e 3180'), AMIDE_I),
    (3330, 3260, 's', 'sharp', '≡C–H', ('≡C–H stretch, terminal alkyne', 'stiramento ≡C–H, alchino terminale'), 'alkyne', None, ALKYNE_CC),
    (3100, 3010, 'm', 'sharp', '=C–H', ('=C–H stretch', 'stiramento =C–H'), 'alkene', None, ALKENE_CC),
    (3100, 3000, 'w', 'sharp', 'Ar–H', ('aromatic C–H stretch', 'stiramento C–H aromatico'), 'aromatic', None, AROMATIC_RING),
    (2990, 2840, 'v', 'sharp', 'C–H', ('C–H stretch of CH₃ and CH₂', 'stiramento C–H di CH₃ e CH₂'), 'alkane',
     ('CH₂ near 2920 and 2850, CH₃ near 2960 and 2870', 'CH₂ vicino a 2920 e 2850, CH₃ vicino a 2960 e 2870')),
    (2860, 2700, 'w', 'sharp', 'CHO', ('C–H stretch of aldehydes (Fermi doublet)', 'stiramento C–H delle aldeidi (doppietto di Fermi)'), 'aldehyde',
     ('two bands near 2820 and 2720', 'due bande vicino a 2820 e 2720'), ALDEHYDE_CO),
    (2600, 2550, 'w', 'sharp', 'S–H', ('S–H stretch', 'stiramento S–H'), 'thiol', None),
    # triple and cumulated bonds
    (2380, 2300, 'm', 'sharp', 'CO₂', ('CO₂ asymmetric stretch', 'stiramento asimmetrico di CO₂'), 'artefact',
     ('usually atmospheric CO₂ not removed with the background (doublet 2360/2340)',
      'di solito CO₂ atmosferica non tolta con il fondo (doppietto 2360/2340)')),
    (2275, 2250, 's', 'broad', 'N=C=O', ('N=C=O asymmetric stretch', 'stiramento asimmetrico N=C=O'), 'isocyanate', None),
    (2260, 2220, 'm', 'sharp', 'C≡N', ('C≡N stretch of nitriles', 'stiramento C≡N dei nitrili'), 'nitrile',
     ('conjugated nitriles towards the lower end', 'nitrili coniugati verso il limite inferiore')),
    (2260, 2100, 'w', 'sharp', 'C≡C', ('C≡C stretch', 'stiramento C≡C'), 'alkyne',
     ('weak or absent in symmetric internal alkynes', 'debole o assente negli alchini interni simmetrici')),
    (2250, 2100, 's', 'sharp', 'Si–H', ('Si–H stretch', 'stiramento Si–H'), 'silane', None),
    (2170, 2080, 's', 'sharp', 'N₃', ('N=N=N asymmetric stretch of azides', 'stiramento asimmetrico N=N=N delle azidi'), 'azide', None),
    (2140, 1990, 's', 'broad', 'N=C=S', ('N=C=S asymmetric stretch', 'stiramento asimmetrico N=C=S'), 'isothiocyanate', None),
    (2100, 2070, 's', 'sharp', 'C≡N', ('C≡N stretch of hexacyanoferrates', 'stiramento C≡N degli esacianoferrati'), 'cyanide',
     ('Prussian blue near 2090', 'blu di Prussia vicino a 2090')),
    (2150, 1850, 's', 'sharp', 'M–CO', ('C≡O stretch of terminal metal carbonyls', 'stiramento C≡O dei metallo-carbonili terminali'),
     'carbonyl_metal', None),
    # C=O
    (1850, 1800, 's', 'sharp', 'C=O', ('C=O stretch of anhydrides, upper band', 'stiramento C=O delle anidridi, banda alta'), 'anhydride',
     ('with a second band at 1790–1740', 'con una seconda banda a 1790–1740')),
    (1790, 1740, 's', 'sharp', 'C=O', ('C=O stretch of anhydrides, lower band', 'stiramento C=O delle anidridi, banda bassa'), 'anhydride', None, ANHYDRIDE_HIGH),
    (1815, 1770, 's', 'sharp', 'C=O', ('C=O stretch of acid chlorides', 'stiramento C=O dei cloruri acilici'), 'acyl_chloride', None),
    (1795, 1760, 's', 'sharp', 'C=O', ('C=O stretch of γ-lactones', 'stiramento C=O dei γ-lattoni'), 'ester', None),
    (1775, 1755, 's', 'sharp', 'C=O', ('C=O stretch of vinyl and phenyl esters', 'stiramento C=O degli esteri vinilici e fenilici'), 'ester', None),
    (1750, 1735, 's', 'sharp', 'C=O', ('C=O stretch of saturated esters', 'stiramento C=O degli esteri saturi'), 'ester',
     ('also lipids, drying oils and waxes', 'anche lipidi, oli siccativi e cere')),
    (1730, 1715, 's', 'sharp', 'C=O', ('C=O stretch of conjugated esters', 'stiramento C=O degli esteri coniugati'), 'ester',
     ('α,β-unsaturated and aryl esters', 'esteri α,β-insaturi e arilici')),
    (1750, 1740, 's', 'sharp', 'C=O', ('C=O stretch of cyclopentanones', 'stiramento C=O dei ciclopentanoni'), 'ketone', None),
    (1740, 1720, 's', 'sharp', 'C=O', ('C=O stretch of saturated aldehydes', 'stiramento C=O delle aldeidi sature'), 'aldehyde', None, ALDEHYDE_CH),
    (1725, 1705, 's', 'sharp', 'C=O', ('C=O stretch of saturated ketones', 'stiramento C=O dei chetoni saturi'), 'ketone', None),
    (1725, 1700, 's', '', 'C=O', ('C=O stretch of carboxylic acids', 'stiramento C=O degli acidi carbossilici'), 'acid',
     ('dimers; with the broad O–H at 3300–2500', 'dimeri; con l’O–H largo a 3300–2500')),
    (1740, 1690, 's', 'sharp', 'C=O', ('C=O stretch of urethanes (carbamates)', 'stiramento C=O degli uretani (carbammati)'), 'urethane', None, URETHANE_NH),
    (1710, 1680, 's', 'sharp', 'C=O', ('C=O stretch of conjugated acids', 'stiramento C=O degli acidi coniugati'), 'acid', None),
    (1710, 1685, 's', 'sharp', 'C=O', ('C=O stretch of conjugated aldehydes', 'stiramento C=O delle aldeidi coniugate'), 'aldehyde', None, ALDEHYDE_CH),
    (1700, 1665, 's', 'sharp', 'C=O', ('C=O stretch of conjugated ketones', 'stiramento C=O dei chetoni coniugati'), 'ketone',
     ('aryl ketones 1700–1680, enones 1685–1665', 'arilchetoni 1700–1680, enoni 1685–1665')),
    (1695, 1630, 's', '', 'amide I', ('amide I (C=O stretch)', 'ammide I (stiramento C=O)'), 'amide',
     ('proteins near 1650', 'proteine vicino a 1650')),
    (1620, 1510, 's', '', 'COO⁻', ('COO⁻ asymmetric stretch of carboxylates', 'stiramento asimmetrico COO⁻ dei carbossilati'), 'carboxylate',
     ('salts and metal soaps (lead and zinc soaps in oil paints near 1540–1510)',
      'sali e saponi metallici (saponi di piombo e zinco nei dipinti a olio vicino a 1540–1510)'), CARBOXYLATE_SYM),
    (1450, 1360, 'm', '', 'COO⁻', ('COO⁻ symmetric stretch of carboxylates', 'stiramento simmetrico COO⁻ dei carbossilati'), 'carboxylate', None, CARBOXYLATE_ASYM),
    (1650, 1600, 's', '', 'C=O', ('C=O asymmetric stretch of metal oxalates', 'stiramento asimmetrico C=O degli ossalati metallici'), 'oxalate',
     ('calcium oxalates: whewellite near 1620, weddellite near 1640', 'ossalati di calcio: whewellite vicino a 1620, weddellite vicino a 1640'), OXALATE_CO_SYM),
    (1335, 1310, 's', 'sharp', 'C–O', ('C–O symmetric stretch of metal oxalates', 'stiramento simmetrico C–O degli ossalati metallici'), 'oxalate',
     ('whewellite near 1317', 'whewellite vicino a 1317'), OXALATE_CO),
    (790, 770, 'm', 'sharp', 'O–C=O', ('O–C=O bend of metal oxalates', 'deformazione O–C=O degli ossalati metallici'), 'oxalate', None, OXALATE_CO),
    # C=C, C=N, N=O; N–H and H–O–H bending
    (1680, 1620, 'v', 'sharp', 'C=C', ('C=C stretch', 'stiramento C=C'), 'alkene',
     ('weak when symmetric; lower when conjugated', 'debole se simmetrico; più in basso se coniugato'), ALKENE_CH),
    (1690, 1640, 'v', '', 'C=N', ('C=N stretch', 'stiramento C=N'), 'imine', None),
    (1625, 1575, 'm', 'sharp', 'C=C ar', ('C=C stretch of the aromatic ring', 'stiramento C=C dell’anello aromatico'), 'aromatic',
     ('usually two bands near 1600 and 1580', 'di solito due bande vicino a 1600 e 1580'), AROMATIC),
    (1525, 1470, 'm', 'sharp', 'C=C ar', ('C=C stretch of the aromatic ring', 'stiramento C=C dell’anello aromatico'), 'aromatic', None, AROMATIC),
    (1650, 1580, 'm', '', 'δ N–H', ('N–H bend of primary amines', 'deformazione N–H delle ammine primarie'), 'amine', None, NH_STRETCH),
    (3100, 3060, 'w', '', 'amide B', ('amide B (N–H stretch in Fermi resonance)', 'ammide B (stiramento N–H in risonanza di Fermi)'),
     'amide', ('proteins near 3070', 'proteine vicino a 3070'), AMIDE_I),
    (1300, 1220, 'm', '', 'amide III', ('amide III (C–N stretch and N–H bend)', 'ammide III (stiramento C–N e deformazione N–H)'),
     'amide', ('proteins near 1240', 'proteine vicino a 1240'), AMIDE_I),
    (1570, 1515, 's', '', 'amide II', ('amide II (N–H bend and C–N stretch)', 'ammide II (deformazione N–H e stiramento C–N)'), 'amide',
     ('secondary amides; proteins near 1540', 'ammidi secondarie; proteine vicino a 1540'), AMIDE_I),
    (1700, 1600, 'm', '', 'H–O–H', ('H–O–H bend of water', 'deformazione H–O–H dell’acqua'), 'water',
     ('liquid water near 1640; hydrates such as gypsum near 1685 and 1620', 'acqua liquida vicino a 1640; idrati come il gesso vicino a 1685 e 1620'), OH_STRETCH),
    (1570, 1500, 's', 'sharp', 'NO₂', ('NO₂ asymmetric stretch of nitro compounds', 'stiramento asimmetrico NO₂ dei nitrocomposti'), 'nitro', None, NITRO_SYM),
    (1390, 1300, 's', 'sharp', 'NO₂', ('NO₂ symmetric stretch of nitro compounds', 'stiramento simmetrico NO₂ dei nitrocomposti'), 'nitro', None, NITRO_ASYM),
    (1660, 1625, 's', 'sharp', 'O–NO₂', ('NO₂ asymmetric stretch of nitrate esters', 'stiramento asimmetrico NO₂ degli esteri nitrici'),
     'nitrate_ester', ('nitrocellulose near 1650, 1280 and 840', 'nitrocellulosa vicino a 1650, 1280 e 840'), NITRATE_ESTER_SYM),
    (1285, 1270, 's', 'sharp', 'O–NO₂', ('NO₂ symmetric stretch of nitrate esters', 'stiramento simmetrico NO₂ degli esteri nitrici'),
     'nitrate_ester', None, NITRATE_ESTER_ASYM),
    # C–H bending
    (1485, 1430, 'm', 'sharp', 'δ C–H', ('CH₂ scissoring and CH₃ asymmetric bend', 'forbice CH₂ e deformazione asimmetrica CH₃'), 'alkane', None, CH_STRETCH),
    (1390, 1365, 'm', 'sharp', 'δ CH₃', ('CH₃ symmetric bend (umbrella)', 'deformazione simmetrica CH₃ (a ombrello)'), 'alkane',
     ('a doublet points to gem-dimethyl or isopropyl groups', 'un doppietto indica gruppi gem-dimetile o isopropile'), CH_STRETCH),
    (735, 715, 'm', 'sharp', 'ρ CH₂', ('CH₂ rocking, chains of four or more CH₂', 'oscillazione CH₂, catene di quattro o più CH₂'), 'alkane',
     ('doublet 730/720 in crystalline chains (waxes, polyethylene)', 'doppietto 730/720 nelle catene cristalline (cere, polietilene)'), CH_STRETCH),
    # inorganic anions and minerals
    (1510, 1390, 's', 'broad', 'CO₃²⁻', ('CO₃²⁻ asymmetric stretch (ν3)', 'stiramento asimmetrico CO₃²⁻ (ν3)'), 'carbonate',
     ('calcite near 1420 (lower in ATR), with 875 and 712', 'calcite vicino a 1420 (più in basso in ATR), con 875 e 712'), CARBONATE_BENDS),
    (2530, 2500, 'w', 'sharp', 'CO₃²⁻', ('combination band ν1+ν3 of carbonates', 'banda di combinazione ν1+ν3 dei carbonati'), 'carbonate',
     ('calcite near 2512', 'calcite vicino a 2512'), CARBONATE_V3),
    (1805, 1785, 'w', 'sharp', 'CO₃²⁻', ('combination band ν1+ν4 of carbonates', 'banda di combinazione ν1+ν4 dei carbonati'), 'carbonate',
     ('calcite near 1795', 'calcite vicino a 1795'), CARBONATE_V3),
    (890, 850, 'm', 'sharp', 'CO₃²⁻', ('CO₃²⁻ out-of-plane bend (ν2)', 'deformazione fuori dal piano CO₃²⁻ (ν2)'), 'carbonate',
     ('calcite near 875, aragonite near 855', 'calcite vicino a 875, aragonite vicino a 855'), CARBONATE_V3),
    (750, 690, 'w', 'sharp', 'CO₃²⁻', ('CO₃²⁻ in-plane bend (ν4)', 'deformazione nel piano CO₃²⁻ (ν4)'), 'carbonate',
     ('calcite near 712, dolomite near 729', 'calcite vicino a 712, dolomite vicino a 729'), CARBONATE_V3),
    (1210, 1040, 's', 'broad', 'SO₄²⁻', ('SO₄²⁻ asymmetric stretch (ν3)', 'stiramento asimmetrico SO₄²⁻ (ν3)'), 'sulfate',
     ('gypsum near 1140–1110', 'gesso vicino a 1140–1110'), SULFATE_V4),
    (680, 580, 'm', 'sharp', 'SO₄²⁻', ('SO₄²⁻ bend (ν4)', 'deformazione SO₄²⁻ (ν4)'), 'sulfate',
     ('gypsum near 670 and 600', 'gesso vicino a 670 e 600'), SULFATE_V3),
    (1410, 1340, 's', 'broad', 'NO₃⁻', ('NO₃⁻ asymmetric stretch (ν3)', 'stiramento asimmetrico NO₃⁻ (ν3)'), 'nitrate', None),
    (840, 815, 'm', 'sharp', 'NO₃⁻', ('NO₃⁻ out-of-plane bend (ν2)', 'deformazione fuori dal piano NO₃⁻ (ν2)'), 'nitrate', None, NITRATE_V3),
    (1120, 940, 's', 'broad', 'PO₄³⁻', ('PO₄³⁻ stretch (ν3)', 'stiramento PO₄³⁻ (ν3)'), 'phosphate',
     ('apatites near 1090 and 1035', 'apatiti vicino a 1090 e 1035'), PHOSPHATE_V4),
    (620, 540, 'm', 'sharp', 'PO₄³⁻', ('PO₄³⁻ bend (ν4)', 'deformazione PO₄³⁻ (ν4)'), 'phosphate',
     ('apatites near 603 and 565', 'apatiti vicino a 603 e 565'), PHOSPHATE_V3),
    (1200, 950, 's', 'broad', 'Si–O', ('Si–O–Si asymmetric stretch of silicates and silica',
                                       'stiramento asimmetrico Si–O–Si di silicati e silice'), 'silicate',
     ('quartz near 1080 with a shoulder near 1170; clays near 1030', 'quarzo vicino a 1080 con una spalla vicino a 1170; argille vicino a 1030')),
    (800, 775, 'm', 'sharp', 'Si–O', ('Si–O symmetric stretch, quartz doublet', 'stiramento simmetrico Si–O, doppietto del quarzo'), 'silicate',
     ('798 and 779 together point to quartz', '798 e 779 insieme indicano il quarzo'), SILICATE_V3),
    (520, 420, 's', '', 'Si–O', ('Si–O bend', 'deformazione Si–O'), 'silicate', None, SILICATE_V3),
    (1430, 1390, 's', '', 'NH₄⁺', ('NH₄⁺ bend', 'deformazione NH₄⁺'), 'ammonium', None, NH4_STRETCH),
    # C–O, C–N, C–halogen; S, P and Si groups
    (1320, 1210, 's', '', 'C–O', ('C–O stretch of carboxylic acids', 'stiramento C–O degli acidi carbossilici'), 'acid', None, ACID_CO),
    (1440, 1395, 'm', '', 'δ O–H', ('O–H in-plane bend of carboxylic acids', 'deformazione O–H nel piano degli acidi carbossilici'), 'acid', None, ACID_CO),
    (960, 900, 'm', 'broad', 'γ O–H', ('O–H out-of-plane bend of acid dimers', 'deformazione O–H fuori dal piano dei dimeri acidi'), 'acid', None, ACID_CO),
    (1300, 1150, 's', '', 'C–O', ('C(=O)–O stretch of esters', 'stiramento C(=O)–O degli esteri'), 'ester',
     ('acetates near 1240', 'acetati vicino a 1240'), ESTER_CO),
    (1260, 1180, 's', '', 'C–O', ('C–O stretch of phenols', 'stiramento C–O dei fenoli'), 'phenol', None, AROMATIC),
    (1210, 1100, 's', '', 'C–O', ('C–O stretch of tertiary alcohols', 'stiramento C–O degli alcoli terziari'), 'alcohol', None, OH_STRETCH),
    (1150, 1075, 's', '', 'C–O', ('C–O stretch of secondary alcohols', 'stiramento C–O degli alcoli secondari'), 'alcohol', None, OH_STRETCH),
    (1075, 1000, 's', '', 'C–O', ('C–O stretch of primary alcohols', 'stiramento C–O degli alcoli primari'), 'alcohol',
     ('also polysaccharides (cellulose, gums) near 1060–1030', 'anche polisaccaridi (cellulosa, gomme) vicino a 1060–1030'), OH_STRETCH),
    (1150, 1085, 's', '', 'C–O–C', ('C–O–C asymmetric stretch of dialkyl ethers', 'stiramento asimmetrico C–O–C degli eteri dialchilici'),
     'ether', None),
    (1275, 1200, 's', '', 'C–O–C', ('C–O–C asymmetric stretch of aryl alkyl ethers', 'stiramento asimmetrico C–O–C degli eteri arilalchilici'),
     'ether', ('with a second band at 1075–1020', 'con una seconda banda a 1075–1020'), AROMATIC),
    (950, 815, 'm', '', 'oxirane', ('epoxide ring deformation', 'deformazione dell’anello epossidico'), 'epoxide',
     ('uncured epoxy resins near 915', 'resine epossidiche non reticolate vicino a 915'), EPOXIDE_RING),
    (1250, 1020, 'm', '', 'C–N', ('C–N stretch of aliphatic amines', 'stiramento C–N delle ammine alifatiche'), 'amine', None, NH_STRETCH),
    (1340, 1250, 's', '', 'C–N', ('C–N stretch of aromatic amines', 'stiramento C–N delle ammine aromatiche'), 'amine', None, AROMATIC),
    (1400, 1000, 's', '', 'C–F', ('C–F stretch', 'stiramento C–F'), 'halide', None),
    (850, 550, 's', '', 'C–Cl', ('C–Cl stretch', 'stiramento C–Cl'), 'halide', None),
    (690, 515, 's', '', 'C–Br', ('C–Br stretch', 'stiramento C–Br'), 'halide', None),
    (1070, 1030, 's', '', 'S=O', ('S=O stretch of sulfoxides', 'stiramento S=O dei solfossidi'), 'sulfoxide', None),
    (1375, 1300, 's', '', 'SO₂', ('SO₂ asymmetric stretch', 'stiramento asimmetrico SO₂'), 'sulfonyl', None),
    (1200, 1120, 's', '', 'SO₂', ('SO₂ symmetric stretch', 'stiramento simmetrico SO₂'), 'sulfonyl', None),
    (1300, 1140, 's', '', 'P=O', ('P=O stretch', 'stiramento P=O'), 'phosphorus', None),
    (1050, 970, 's', '', 'P–O–C', ('P–O–C stretch', 'stiramento P–O–C'), 'phosphorus', None),
    (1275, 1255, 's', 'sharp', 'Si–CH₃', ('Si–CH₃ symmetric bend', 'deformazione simmetrica Si–CH₃'), 'silicone',
     ('silicones also have Si–O–Si at 1130–1000', 'i siliconi hanno anche Si–O–Si a 1130–1000'), SILOXANE),
    (1130, 1000, 's', 'broad', 'Si–O–Si', ('Si–O–Si and Si–O–C stretch of siloxanes', 'stiramento Si–O–Si e Si–O–C dei silossani'),
     'silicone', None),
    # out-of-plane C–H bending
    (995, 985, 's', 'sharp', 'γ =C–H', ('=C–H out-of-plane bend, vinyl (with 915–905)', '=C–H fuori dal piano, vinile (con 915–905)'),
     'alkene', None, ALKENE),
    (915, 905, 's', 'sharp', 'γ =CH₂', ('=CH₂ out-of-plane bend, vinyl', '=CH₂ fuori dal piano, vinile'), 'alkene', None, ALKENE),
    (980, 960, 's', 'sharp', 'γ =C–H', ('=C–H out-of-plane bend, trans', '=C–H fuori dal piano, trans'), 'alkene', None, ALKENE),
    (895, 885, 's', 'sharp', 'γ =CH₂', ('=CH₂ out-of-plane bend, vinylidene', '=CH₂ fuori dal piano, vinilidene'), 'alkene', None, ALKENE),
    (840, 800, 'm', 'sharp', 'γ =C–H', ('=C–H out-of-plane bend, trisubstituted', '=C–H fuori dal piano, trisostituito'), 'alkene', None, ALKENE),
    (730, 665, 'm', '', 'γ =C–H', ('=C–H out-of-plane bend, cis', '=C–H fuori dal piano, cis'), 'alkene', None, ALKENE),
    (770, 730, 's', 'sharp', 'γ Ar–H', ('aromatic C–H out-of-plane bend, mono- or ortho-substituted',
                                         'C–H aromatico fuori dal piano, mono- o orto-sostituito'), 'aromatic',
     ('monosubstituted rings also at 710–690', 'gli anelli monosostituiti anche a 710–690'), AROMATIC),
    (710, 690, 's', 'sharp', 'γ ring', ('aromatic ring out-of-plane bend, mono- or meta-substituted',
                                        'anello aromatico fuori dal piano, mono- o meta-sostituito'), 'aromatic', None, AROMATIC),
    (810, 750, 's', 'sharp', 'γ Ar–H', ('aromatic C–H out-of-plane bend, meta-substituted', 'C–H aromatico fuori dal piano, meta-sostituito'),
     'aromatic', None, AROMATIC),
    (860, 800, 's', 'sharp', 'γ Ar–H', ('aromatic C–H out-of-plane bend, para-substituted', 'C–H aromatico fuori dal piano, para-sostituito'),
     'aromatic', None, AROMATIC),
    (1225, 950, 'w', 'sharp', 'β Ar–H', ('aromatic C–H in-plane bend', 'C–H aromatico nel piano'), 'aromatic', None, AROMATIC),
    (700, 610, 's', 'broad', 'δ ≡C–H', ('≡C–H bend of terminal alkynes', 'deformazione ≡C–H degli alchini terminali'), 'alkyne', None, ALKYNE_CH),
    (672, 664, 'w', 'sharp', 'CO₂', ('CO₂ bend', 'deformazione di CO₂'), 'artefact',
     ('atmospheric CO₂, together with 2360/2340', 'CO₂ atmosferica, insieme a 2360/2340'), CO2_STRETCH),
]

_FIELDS = ('hi', 'lo', 'intensity', 'shape', 'label', 'vibration', 'family', 'note', 'needs')

_BASELINE = [q for q in baselines.params(extra=[('none', {'en': 'none (y = 0)', 'it': 'nessuna (y = 0)'})], default='arpls')
             if q.get('show_if') != {'baseline': ['points']}]          # anchor points would be in the figure's units
_BASELINE[0] = {**_BASELINE[0], 'choices': [c for c in _BASELINE[0]['choices'] if c['value'] != 'points']}

PLUGIN = {
    'id': 'ir_assign',
    'order': 32,
    'name': {'en': 'IR peak assignment', 'it': 'Assegnazione dei picchi IR'},
    'category': 'signal',
    'description': {
        'en': 'Finds the peaks of a mid-IR spectrum and lists, for each, the candidate groups from a table of '
              'characteristic frequencies (organic groups and inorganic anions and minerals).',
        'it': 'Trova i picchi di uno spettro IR medio ed elenca, per ognuno, i gruppi candidati da una tabella di '
              'frequenze caratteristiche (gruppi organici, anioni inorganici e minerali).'},
    'requires': ['scipy'],
    'params': [
        {'id': 'x', 'type': 'column', 'default': 'x', 'label': {'en': 'Wavenumber or wavelength', 'it': 'Numero d’onda o lunghezza d’onda'}},
        {'id': 'y', 'type': 'column', 'default': 'y', 'label': {'en': 'Spectrum', 'it': 'Spettro'}},
        {'id': 'signal', 'type': 'choice', 'default': 'auto', 'label': {'en': 'The spectrum is', 'it': 'Lo spettro è'},
         'choices': [{'value': 'auto', 'label': {'en': 'recognise (from name and shape)', 'it': 'riconoscilo (da nome e forma)'}},
                     {'value': 'absorbance', 'label': {'en': 'absorbance (peaks up)', 'it': 'assorbanza (picchi in su)'}},
                     {'value': 'transmittance', 'label': {'en': 'transmittance, % or 0–1 (peaks down)',
                                                          'it': 'trasmittanza, % o 0–1 (picchi in giù)'}}]},
        {'id': 'xunit', 'type': 'choice', 'default': 'auto', 'label': {'en': 'X unit', 'it': 'Unità di x'},
         'choices': [{'value': 'auto', 'label': {'en': 'recognise', 'it': 'riconoscila'}},
                     {'value': 'cm-1', 'label': 'cm⁻¹'}, {'value': 'um', 'label': 'µm'}, {'value': 'nm', 'label': 'nm'}]},
        {'id': 'scope', 'type': 'choice', 'default': 'all', 'label': {'en': 'Compare with', 'it': 'Confronta con'},
         'choices': [{'value': 'all', 'label': {'en': 'all the table', 'it': 'tutta la tabella'}},
                     {'value': 'organic', 'label': {'en': 'organic groups', 'it': 'gruppi organici'}},
                     {'value': 'inorganic', 'label': {'en': 'inorganic anions and minerals', 'it': 'anioni inorganici e minerali'}}]},
        {'id': 'elements', 'type': 'choice', 'default': 'chon', 'label': {'en': 'Organic groups with', 'it': 'Gruppi organici con'},
         'choices': [{'value': 'chon', 'label': {'en': 'C, H, O, N only', 'it': 'solo C, H, O, N'}},
                     {'value': 'all', 'label': {'en': 'also S, P, Si, halogens', 'it': 'anche S, P, Si, alogeni'}}],
         'help': {'en': 'S, P, Si and halogen groups have broad ranges that fit many peaks: include them when the sample has '
                        'those elements.',
                  'it': 'I gruppi con S, P, Si e alogeni hanno intervalli larghi che si adattano a molti picchi: includili quando '
                        'il campione contiene quegli elementi.'}},
        *_BASELINE,
        {'id': 'prominence', 'type': 'float', 'optional': True, 'min': 0,
         'label': {'en': 'Minimum prominence, in absorbance (empty = 5% of range)',
                   'it': 'Prominenza minima, in assorbanza (vuoto = 5% dell’intervallo)'}},
        {'id': 'tolerance', 'type': 'float', 'default': 10, 'min': 0, 'max': 100,
         'label': {'en': 'Tolerance outside the table ranges (cm⁻¹)', 'it': 'Tolleranza fuori dagli intervalli della tabella (cm⁻¹)'}},
        {'id': 'candidates', 'type': 'int', 'default': 3, 'min': 1, 'max': 8,
         'label': {'en': 'Candidates per peak', 'it': 'Candidati per picco'}},
        {'id': 'xmin', 'type': 'float', 'optional': True, 'label': {'en': 'Only from (cm⁻¹)', 'it': 'Solo da (cm⁻¹)'}},
        {'id': 'xmax', 'type': 'float', 'optional': True, 'label': {'en': 'Only to (cm⁻¹)', 'it': 'Solo fino a (cm⁻¹)'}},
        {'id': 'labels', 'type': 'choice', 'default': 'assignment', 'label': {'en': 'Above each peak', 'it': 'Sopra ogni picco'},
         'choices': [{'value': 'assignment', 'label': {'en': 'position and group', 'it': 'posizione e gruppo'}},
                     {'value': 'position', 'label': {'en': 'position only', 'it': 'solo la posizione'}},
                     {'value': 'none', 'label': {'en': 'nothing', 'it': 'niente'}}]},
    ],
    'references': [
        'Socrates, G. Infrared and Raman Characteristic Group Frequencies: Tables and Charts, 3rd ed. Wiley, Chichester (2001).',
        'Silverstein, R. M., Webster, F. X., Kiemle, D. J. & Bryce, D. L. Spectrometric Identification of Organic '
        'Compounds, 8th ed. Wiley, Hoboken (2014).',
        'Pretsch, E., Bühlmann, P. & Badertscher, M. Structure Determination of Organic Compounds: Tables of Spectral '
        'Data, 4th ed. Springer, Berlin (2009). doi:10.1007/978-3-540-93810-1',
        'Larkin, P. J. Infrared and Raman Spectroscopy: Principles and Spectral Interpretation, 2nd ed. Elsevier, '
        'Amsterdam (2018).',
        'Farmer, V. C. (ed.) The Infrared Spectra of Minerals. Mineralogical Society Monograph 4, London (1974). '
        'doi:10.1180/mono-4',
        'Derrick, M. R., Stulik, D. & Landry, J. M. Infrared Spectroscopy in Conservation Science. Getty Conservation '
        'Institute, Los Angeles (1999).',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}


# Organic families with elements other than C, H, O, N (offered only when asked for).
HETEROATOM = {'thiol', 'sulfoxide', 'sulfonyl', 'isothiocyanate', 'phosphorus', 'halide', 'acyl_chloride', 'silane', 'silicone'}
# Any organic group has C–H bonds: its bands count only with a C–H stretching band somewhere.
ORGANIC = [(3100, 2840, 0.03)]


def bands(scope='all', elements='all'):
    """BANDS as dictionaries (lo < hi) for the chosen scope ('all', 'organic', 'inorganic') and elements
    ('all', or 'chon' without the groups of HETEROATOM). 'organic' is True for organic families."""
    out = []
    for row in BANDS:
        b = {'needs': None, **dict(zip(_FIELDS, row))}
        b['lo'], b['hi'] = sorted((b['lo'], b['hi']))
        kind = FAMILIES[b['family']][1]
        b['organic'] = kind == 'o'
        if elements == 'chon' and b['family'] in HETEROATOM:
            continue
        if scope == 'all' or kind == 'x' or kind == {'organic': 'o', 'inorganic': 'i'}[scope]:
            out.append(b)
    return out


def x_unit(x, name):
    """'cm-1', 'um' or 'nm' from the column name, or else from the values."""
    n = str(name or '').lower()
    if re.search(r'\bnm\b', n):
        return 'nm'
    if re.search(r'µm|μm|\bum\b|micron', n):
        return 'um'
    if re.search(r'cm|wavenumber|numero d', n):
        return 'cm-1'
    return 'um' if np.nanmax(x) < 50 else 'cm-1'


def is_transmittance(y, name):
    """True for a transmittance (bands point down): from the column name, or else from the shape — the
    level the signal mostly sits at is near the top of its range."""
    n = str(name or '').lower()
    if re.search(r'transm|trasm|%\s*t\b|\bt\s*\(\s*%|^t\b', n):
        return True
    if re.search(r'absorb|assorb|\babs\b|^a\b|kubelka|log\s*\(?1\s*/\s*r', n):
        return False
    lo, hi = np.nanpercentile(y, [1, 99])
    return bool(hi > lo and (np.nanmedian(y) - lo) / (hi - lo) > 0.6)


def _intensity_match(expected, rel):
    if expected == 'v':
        return 0.8
    seen = 2 if rel >= 0.33 else (1 if rel >= 0.1 else 0)
    return (1.0, 0.6, 0.25)[abs({'s': 2, 'm': 1, 'w': 0}[expected] - seen)]


def _shape_match(shape, fwhm):
    """A very broad peak (FWHM ≥ 100 cm⁻¹, like hydrogen-bonded O–H) favours the broad bands."""
    if not np.isfinite(fwhm) or not shape:
        return 1.0
    if shape == 'broad':
        return 1.5 if fwhm >= 100 else (1.0 if fwhm >= 35 else 0.4)
    return 1.0 if fwhm <= 40 else (0.8 if fwhm <= 90 else 0.25)


def assign(peaks, table, tol=10.0, span=(0.0, np.inf)):
    """For each peak ({'position' cm⁻¹, 'height', 'fwhm' cm⁻¹}) the candidate bands, best first:
    [{'band', 'score', 'inside', 'support', 'alone'}]. A band is a candidate when the peak lies in its
    range or within tol of it (then at a lower score). The score grows with how narrow the range is, how
    well the intensity (relative to the strongest peak) and the width match, and with support: how well
    the same family explains other peaks (its best score there, summed over the other peaks, at most 1).
    A band whose companion bands (needs; for organic groups also a C–H stretch) are missing where the
    spectrum (span, cm⁻¹) reaches scores a quarter ('alone')."""
    if not peaks:
        return []
    top = max(p['height'] for p in peaks) or 1.0

    def companion(needs, i):
        if not needs:
            return True
        needs = [(min(a, b), max(a, b), rel) for a, b, rel in needs]          # written high to low, as in IR
        if not any(lo < span[1] and hi > span[0] for lo, hi, _ in needs):
            return True                      # the spectrum does not reach where it would be
        return any(lo <= q['position'] <= hi and q['height'] / top >= rel
                   for j, q in enumerate(peaks) if j != i for lo, hi, rel in needs)
    raw = []
    for i, p in enumerate(peaks):
        rel, cands = p['height'] / top, []
        for b in table:
            off = max(b['lo'] - p['position'], p['position'] - b['hi'], 0.0)
            if off > tol:
                continue
            s = 100 / (b['hi'] - b['lo'] + 100) * _intensity_match(b['intensity'], rel) * _shape_match(b['shape'], p['fwhm'])
            if off > 0:
                s *= 0.5 * (1 - off / tol)
            alone = not companion(b['needs'], i)
            if b.get('organic') and not (b['lo'] < ORGANIC[0][0] and b['hi'] > ORGANIC[0][1]):
                alone = alone or not companion(ORGANIC, i)       # the C–H stretching bands themselves excepted
            if alone:
                s *= 0.25
            cands.append((s, off == 0, b, alone))
        raw.append(cands)
    best = []                                # family → best in-range score, for each peak
    for cands in raw:
        fam = {}
        for s, inside, b, _ in cands:
            if inside:
                fam[b['family']] = max(fam.get(b['family'], 0.0), s)
        best.append(fam)
    out = []
    for i, cands in enumerate(raw):
        ranked = []
        for s, inside, b, alone in cands:
            support = sum(f.get(b['family'], 0.0) for j, f in enumerate(best) if j != i)
            ranked.append({'band': b, 'score': s * (1 + min(support, 1.0)), 'inside': inside, 'support': support,
                           'alone': alone})
        ranked.sort(key=lambda c: -c['score'])
        out.append(ranked)
    return out


CONFIDENCE = {'high': ('high', 'alta'), 'medium': ('medium', 'media'), 'low': ('low', 'bassa')}


def confidence(c, high=0.8, medium=0.45):
    """'high', 'medium' or 'low' for a candidate: low when its companion bands are missing or the peak is
    outside its range, else by score."""
    if not c or c['alone'] or not c['inside'] or c['score'] < medium:
        return 'low'
    return 'high' if c['score'] >= high else 'medium'


def _range(b):
    return f'{b["hi"]:g}–{b["lo"]:g}'                     # IR habit: high wavenumber first


def run(df, p, ctx):
    L = 1 if ctx.lang == 'it' else 0
    x, y = ctx.xy(df, p['x'], p['y'])
    unit = x_unit(x, p['x']) if p['xunit'] == 'auto' else p['xunit']
    if np.any(x <= 0) and unit != 'cm-1':
        raise ValueError(ctx.tr('Wavelengths must be positive.', 'Le lunghezze d’onda devono essere positive.'))
    nu = {'cm-1': x, 'um': 1e4 / np.where(x > 0, x, np.nan), 'nm': 1e7 / np.where(x > 0, x, np.nan)}[unit]
    if min(np.nanmax(nu), 4000) - max(np.nanmin(nu), 400) < 300:
        raise ValueError(ctx.tr(f'The x values are not mid-infrared (400–4000 cm⁻¹ once read as {unit}): '
                                'choose the X unit, or the right column.',
                                f'I valori di x non sono nell’infrarosso medio (400–4000 cm⁻¹ letti come {unit}): '
                                'scegli l’unità di x, o la colonna giusta.'))
    trans = is_transmittance(y, p['y']) if p['signal'] == 'auto' else p['signal'] == 'transmittance'
    if trans:
        scale = 100.0 if np.nanmax(y) > 1.5 else 1.0
        a = -np.log10(np.clip(y / scale, 1e-4, None))
    else:
        a = y.copy()
    order = np.argsort(nu, kind='stable')
    nu_s, a_s, x_s, y_s = nu[order], a[order], x[order], y[order]
    b = ctx.baseline(nu_s, a_s, p)
    base = b.values if b is not None else np.zeros_like(a_s)
    work = pd.DataFrame({'nu': nu_s, 'A': a_s - base})
    found = ctx.run('peaks', work, x='nu', y='A', baseline='none', prominence=p['prominence'], distance=1,
                    minima=False, labels=False, xmin=p['xmin'], xmax=p['xmax'])
    peaks = sorted(found.get('peaks') or [], key=lambda q: -q['position'])
    if not peaks:
        raise ValueError(ctx.tr('No peak found: lower the minimum prominence.', 'Nessun picco trovato: abbassa la prominenza minima.'))
    table = bands(p['scope'], p['elements'])
    lo_s, hi_s = max(nu_s[0], p['xmin'] or -np.inf), min(nu_s[-1], p['xmax'] or np.inf)     # where peaks were sought
    ranked = assign(peaks, table, p['tolerance'], span=(lo_s, hi_s))

    r = ctx.result()
    r.value(ctx.tr('peaks found', 'picchi trovati'), len(peaks), key='n_peaks')
    r.value(ctx.tr('spectrum read as', 'spettro letto come'),
            ctx.tr('transmittance, turned into absorbance A = −log₁₀ T', 'trasmittanza, convertita in assorbanza A = −log₁₀ T')
            if trans else ctx.tr('absorbance', 'assorbanza'))
    r.value(ctx.tr('x read in', 'x letta in'), {'cm-1': 'cm⁻¹', 'um': 'µm', 'nm': 'nm'}[unit])
    r.value(ctx.tr('baseline', 'linea di base'), b.label if b is not None else ctx.tr('none (y = 0)', 'nessuna (y = 0)'))
    r.value(ctx.tr('bands in the table', 'bande nella tabella'), len(table))
    if b is not None:
        r.cite(*b.refs)

    level = lambda rel: ctx.tr(*(('strong', 'forte') if rel >= 0.33 else (('medium', 'media') if rel >= 0.1 else ('weak', 'debole'))))
    top = max((q['height'] for q in peaks), default=1.0) or 1.0
    rows, kept, marks, texts = [], [], [], []
    n = p['candidates']
    for q, cands in zip(peaks, ranked):
        rel = q['height'] / top
        best = cands[0] if cands else None
        bb = best['band'] if best else None
        conf = confidence(best)
        rows.append({
            'cm⁻¹': round(q['position'], 1), ctx.tr('intensity', 'intensità'): f'{level(rel)} ({rel:.0%})',
            'FWHM (cm⁻¹)': round(q['fwhm'], 1) if np.isfinite(q['fwhm']) else None,
            ctx.tr('most likely', 'più probabile'): bb['vibration'][L] if bb else ctx.tr('no band of the table', 'nessuna banda della tabella'),
            ctx.tr('group', 'gruppo'): FAMILIES[bb['family']][0][L] if bb else '',
            ctx.tr('confidence', 'affidabilità'): ctx.tr(*CONFIDENCE[conf]) if bb else '',
            ctx.tr('table range', 'intervallo in tabella'): (_range(bb) + ('' if best['inside'] else ' (±)')) if bb else '',
            ctx.tr('alternatives', 'alternative'): '; '.join(
                f'{c["band"]["label"]} {FAMILIES[c["band"]["family"]][0][L]} ({_range(c["band"])})' for c in cands[1:n]),
            ctx.tr('note', 'nota'): bb['note'][L] if bb and bb['note'] else '',
        })
        kept.append({'position': q['position'], 'height': q['height'], 'fwhm': q['fwhm'], 'candidates': [
            {'label': c['band']['label'], 'vibration': c['band']['vibration'][0], 'family': c['band']['family'],
             'lo': c['band']['lo'], 'hi': c['band']['hi'], 'score': c['score'], 'inside': c['inside'],
             'confidence': confidence(c)} for c in cands[:n]]})
        # The figure: position and the best group; two labels when the second is nearly as likely, "?" when
        # the best is a weak match.
        text = f'{q["position"]:.0f}'
        if p['labels'] == 'assignment' and best and conf == 'low':
            text += ' ?'
        elif p['labels'] == 'assignment' and best:
            labels = [bb['label']]
            if len(cands) > 1 and cands[1]['score'] >= 0.75 * best['score'] and cands[1]['band']['label'] != bb['label']:
                labels.append(cands[1]['band']['label'])
            text += ' ' + ' / '.join(labels)
        i = int(np.argmin(np.abs(nu_s - q['position'])))
        marks.append((x_s[i], y_s[i]))
        texts.append(text)
    r.keep('assignments', kept)
    r.table(ctx.tr('Assignments (candidates, best first)', 'Assegnazioni (candidati, il migliore per primo)'), rows)

    # Groups that explain peaks: those among the top candidates, strongest evidence first.
    groups = {}
    for q, cands in zip(peaks, ranked):
        seen = set()
        for c in cands[:n]:
            fam = c['band']['family']
            if c['score'] >= 0.5 * cands[0]['score'] and confidence(c) != 'low' and fam not in seen:
                seen.add(fam)
                g = groups.setdefault(fam, {'score': 0.0, 'peaks': []})
                g['score'] += c['score']
                g['peaks'].append(f'{q["position"]:.0f} {c["band"]["label"]}')
    if groups:
        r.table(ctx.tr('Groups compatible with the peaks', 'Gruppi compatibili con i picchi'), [
            {ctx.tr('group', 'gruppo'): FAMILIES[f][0][L], ctx.tr('peaks', 'picchi'): ', '.join(g['peaks']),
             ctx.tr('peaks explained', 'picchi spiegati'): len(g['peaks'])}
            for f, g in sorted(groups.items(), key=lambda kv: -kv[1]['score'])[:12]])

    # What the absence of bands rules out (only where the spectrum and the search reach).
    def covered(a_, b_):
        return lo_s <= a_ and hi_s >= b_

    def any_peak(a_, b_, rel_min):
        return any(a_ <= q['position'] <= b_ and q['height'] / top >= rel_min for q in peaks)
    if covered(1650, 1850) and not any_peak(1650, 1850, 0.15):
        r.text(ctx.tr('No strong band at 1850–1650 cm⁻¹: a C=O group (ketone, aldehyde, ester, acid, amide, anhydride) '
                      'is unlikely.',
                      'Nessuna banda intensa a 1850–1650 cm⁻¹: un gruppo C=O (chetone, aldeide, estere, acido, ammide, '
                      'anidride) è improbabile.'))
    if covered(3200, 3650) and not any_peak(3200, 3650, 0.1):
        r.text(ctx.tr('No band at 3650–3200 cm⁻¹: alcohols, phenols, water, amines and amides (O–H, N–H) are unlikely; '
                      'the O–H of carboxylic acids lies lower, at 3300–2500, often hidden under the C–H bands.',
                      'Nessuna banda a 3650–3200 cm⁻¹: alcoli, fenoli, acqua, ammine e ammidi (O–H, N–H) sono improbabili; '
                      'l’O–H degli acidi carbossilici sta più in basso, a 3300–2500, spesso nascosto sotto le bande C–H.'))
    if any(c and c[0]['band']['family'] == 'artefact' for c in ranked):
        r.text(ctx.tr('A band of atmospheric CO₂ (2360/2340 or 667 cm⁻¹) is there: record the background again rather '
                      'than reading it as part of the sample.',
                      'C’è una banda di CO₂ atmosferica (2360/2340 o 667 cm⁻¹): registra di nuovo il fondo invece di '
                      'leggerla come parte del campione.'))
    r.text(ctx.tr('These are candidates from a table of characteristic frequencies, not proofs: confirm them with '
                  'reference spectra. “(±)” marks a peak just outside the table range.',
                  'Sono candidati da una tabella di frequenze caratteristiche, non prove: confermali con spettri di '
                  'riferimento. “(±)” indica un picco appena fuori dall’intervallo della tabella.'))

    xname = p['x']
    label = ctx.tr('peaks', 'picchi')
    marks_frame = pd.DataFrame({xname: [m[0] for m in marks], label: [m[1] for m in marks]})
    text = None
    if p['labels'] != 'none':
        text = ctx.tr('assignment', 'assegnazione')
        marks_frame[text] = texts
    if b is not None:
        bname = ctx.tr('baseline', 'linea di base')
        bvals = (10 ** -base) * (100.0 if np.nanmax(y) > 1.5 else 1.0) if trans else base
        r.overlay(pd.DataFrame({xname: x_s, bname: bvals}), xname, bname, label=bname,
                  style={'linestyle': '--', 'linewidth': 0.9})
    r.overlay(marks_frame, xname, label, label=label, text=text,
              style={'linestyle': 'none', 'marker': '^' if trans else 'v', 'text_below': trans})
    full = pd.DataFrame({xname: x_s, p['y']: y_s})
    full[label] = np.nan
    for (mx, my) in marks:
        full.loc[full[xname] == mx, label] = my
    r.data(full, name=f'{ctx.tr("IR assignment", "assegnazione IR")} · {p["y"]}',
           plot={'kind': 'line', 'x': xname, 'y': [p['y'], label], 'axes': {'invert_x': unit == 'cm-1'},
                 'series': {label: {'linestyle': 'none', 'marker': '^' if trans else 'v'}}})
    return r
