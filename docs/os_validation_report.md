# Original Study Search Validation Report

Generated: 2026-05-13 17:16 UTC  
Search run: `fnd_search_20260512_154542`

## Context

This report validates whether our expanded FND neuroimaging search strategy
recovers the studies included in Boeckle et al. (2016) "Neural correlates
of conversion disorder: overview and meta-analysis of neuroimaging studies
on motor conversion disorder" (*BMC Psychiatry*, 16, 195).

The original study (OS) reported searching Medline, PsycINFO, Psyndex, and
Cochrane to August 2015. Its Table 1 lists 49 included studies.

## Why literal replication of the OS search is not viable

We initially attempted to replicate the OS using its published search terms
(`os_validation` mode) and later broadened terms (`os_table_recall` mode).
Neither approach could recover the full Table 1. Investigation revealed
several internal inconsistencies in the OS methodology:

1. **Database mismatch**: The Methods section names Medline, PsycINFO,
   Psyndex, and Cochrane, but the PRISMA flow includes 784 Scopus records
   from a database never mentioned.
2. **Search terms vs. included studies**: The published search string uses
   only ("dissociative disorder" OR "functional disorder" OR "conversion
   disorder") crossed with neuroimaging terms (MRI, fMRI, PET, VBM). Yet
   Table 1 includes studies on body dysmorphic disorder, somatization
   disorder, dissociative identity disorder, and psychogenic seizures --
   none of which match the published query.
3. **Imaging modality mismatch**: The Methods state eligible modalities are
   PET, MRI, and SPECT, but Table 1 includes studies using EEG (7 studies),
   MEG (1 study), and CT (1 study).
4. **Missing terminology**: Terms like hysteria/hysterical, psychogenic,
   somatoform, PNES, SPECT, and single photon emission appear nowhere in
   the published search string yet are required to find many Table 1 studies.

These discrepancies suggest that the OS search involved manual/synonym
decisions beyond what the published search string describes, making exact
replication impossible from the reported methodology alone.

## Our validation approach

Instead of trying to replicate an unreproducible search, we validated our
own production search strategy by running it with the OS cutoff date:

- **Search mode**: `full` (expanded FND neuroimaging terms with MeSH,
  language, and publication-type filters)
- **Date range**: inception to 2015/08/31 (matching the OS end date)
- **Databases**: PubMed, Europe PMC, Scopus
  (Web of Science skipped -- no API key)

### Per-database counts

| Database | Records |
| --- | ---: |
| pubmed | 306 |
| europepmc | 113 |
| wos | 0 |
| scopus | 577 |
| **After deduplication** | **709** |

We then matched the deduplicated results against all 49 OS Table 1 studies
using DOIs resolved from the CrossRef API, with title-similarity and
author-surname fallbacks.

## Results: 33/49 studies found

### Matched studies

| # | OS study | Disorder | Source DB | Match method |
| ---: | --- | --- | --- | --- |
| 1 | Atmaca, et al. [82] | motor conversion | pubmed | doi |
| 2 | Aybek, et al. [29] | motor conversion | pubmed | doi |
| 3 | aAybek, et al. [52] | motor conversion | europepmc | doi |
| 4 | aAybek, et al. [47] | motor conversion | pubmed | doi |
| 5 | Benbadis, et al. [85] | syncope of unknown origin | scopus | doi |
| 6 | Burke, et al. [89] | sensory conversion | pubmed | doi |
| 7 | Burgmer, et al. [90] | motor conversion | pubmed | doi |
| 8 | Cojan, et al. [19] | motor conversion | pubmed | doi |
| 9 | aCzarnecki, et al. [60] | motor conversion | pubmed | doi |
| 10 | ade Lange, et al. [16] | motor conversion | pubmed | doi |
| 11 | ade Lange, et al. [64] | motor conversion | pubmed | doi |
| 12 | de Lange, et al. [21] | motor conversion | pubmed | doi |
| 13 | de Ruiter, et al. [92] | non clinical dissociative experiences | pubmed | doi |
| 14 | Devinsky, et al. [93] | C-NES | pubmed | doi |
| 15 | aElzinga, et al. [46] | motor conversion | pubmed | doi |
| 16 | Felmingham, et al. [94] | dissociative PTSD | pubmed | doi |
| 17 | Ghaffar, et al. [62] | motor conversion | pubmed | doi |
| 18 | Karatas, et al. [101] | PNES | scopus | doi |
| 19 | Knyazeva, et al. [102] | PNES | scopus | doi |
| 20 | Labate, et al. [28] | PNES | pubmed | doi |
| 21 | Mailis-Gagnon, et al. [24] | hysterical anaesthesia | pubmed | doi |
| 22 | Moser, et al. [104] | dissociation | pubmed | doi |
| 23 | Nicholson, et al. [105] | motor conversion | pubmed | doi |
| 24 | Sar, et al. [107] | dissociative identity disorder | pubmed | doi |
| 25 | aStone, et al. [74] | motor conversion | pubmed | doi |
| 26 | avan Beilen, et al. [50] | motor conversion | pubmed | doi |
| 27 | van Der Kruijs, et al. [108] | PNES | pubmed | doi |
| 28 | aVoon, et al. [43] | conversion tremor, dystonia, gait disorder | pubmed | doi |
| 29 | aVoon, et al. [27] | motor conversion | pubmed | doi |
| 30 | Voon, et al. [25] | motor conversion | pubmed | doi |
| 31 | aVuilleumier, et al. [22] | sensorimotor conversion | pubmed | doi |
| 32 | Werring, et al. [109] | sensory conversion | pubmed | doi |
| 33 | Yazici, et al. [110] | Astasia-Abasia | pubmed | doi |

### Not found (16 studies)

| OS study | Disorder | Imaging | Miss category |
| --- | --- | --- | --- |
| Atmaca, et al. [83] | somatization disorder | sMRI (1.5 Tesla) | Out-of-scope disorder (not FND) |
| Atmaca, et al. [84] | motor conversion | sMRI (1.5 Tesla) | In-scope miss (investigate search terms) |
| Blakemore, et al. [86] | motor conversion | EEG | Out-of-scope imaging modality (EEG / MEG / CT) |
| Blakemore, et al. [87] | motor conversion | EEG | Out-of-scope imaging modality (EEG / MEG / CT) |
| Bonilha, et al. [88] | idiopathic dystonia | sMRI (3.0 Tesla) | In-scope miss (investigate search terms) |
| Carey, et al. [91] | body dysmorphic disorder | SPECT (HMPAO) | Out-of-scope disorder (not FND) |
| Feusner, et al. [95] | body dysmorphic disorder | fMRI (3.0 Tesla) | Out-of-scope disorder (not FND) |
| Feusner, et al. [96] | body dysmorphic disorder | sMRI (3.0 Tesla) | Out-of-scope disorder (not FND) |
| Garcia-Campayo, et al. [97] | somatization disorder | SPECT (HMPAO or TC-bicisate) | Out-of-scope disorder (not FND) |
| Hakala, et al. [98] | somatization disorder | sMRI (1.5 Tesla) | Out-of-scope disorder (not FND) |
| Hoechstetter, et al. [99] | motor conversion | MEG | Out-of-scope imaging modality (EEG / MEG / CT) |
| Hovorka, et al. [100] | PNES | EEG | Out-of-scope imaging modality (EEG / MEG / CT) |
| Krüger, et al. [103] | dissociation DES | EEG | Out-of-scope imaging modality (EEG / MEG / CT) |
| Rauch, et al. [106] | body dysmorphic disorder | MRI | Out-of-scope disorder (not FND) |
| Roelofs, et al. [66] | motor conversion | EEG | Out-of-scope imaging modality (EEG / MEG / CT) |
| aSpence, et al. [20] | motor conversion | PET | In-scope miss (investigate search terms) |

### Miss analysis

**Out-of-scope imaging modality (EEG / MEG / CT)** (6 studies)

- Blakemore, et al. [86]: motor conversion (EEG)
- Blakemore, et al. [87]: motor conversion (EEG)
- Hoechstetter, et al. [99]: motor conversion (MEG)
- Hovorka, et al. [100]: PNES (EEG)
- Krüger, et al. [103]: dissociation DES (EEG)
- Roelofs, et al. [66]: motor conversion (EEG)

**Out-of-scope disorder (not FND)** (7 studies)

- Atmaca, et al. [83]: somatization disorder (sMRI (1.5 Tesla))
- Carey, et al. [91]: body dysmorphic disorder (SPECT (HMPAO))
- Feusner, et al. [95]: body dysmorphic disorder (fMRI (3.0 Tesla))
- Feusner, et al. [96]: body dysmorphic disorder (sMRI (3.0 Tesla))
- Garcia-Campayo, et al. [97]: somatization disorder (SPECT (HMPAO or TC-bicisate))
- Hakala, et al. [98]: somatization disorder (sMRI (1.5 Tesla))
- Rauch, et al. [106]: body dysmorphic disorder (MRI)

**In-scope miss (investigate search terms)** (3 studies)

- Atmaca, et al. [84]: motor conversion (sMRI (1.5 Tesla))
- Bonilha, et al. [88]: idiopathic dystonia (sMRI (3.0 Tesla))
- aSpence, et al. [20]: motor conversion (PET)

## Conclusion

Our search strategy recovers **33/36 in-scope studies** from the OS Table 1
(3 in-scope misses).

The 16 unrecovered studies break down as:

- Out-of-scope imaging modality (EEG / MEG / CT): 6
- Out-of-scope disorder (not FND): 7
- In-scope miss (investigate search terms): 3

The vast majority of misses are explainable by being outside the scope
of our FND neuroimaging meta-analysis (wrong imaging modality or wrong
diagnosis). Any remaining in-scope misses are documented above for
investigation; they may reflect papers using unusual terminology or
papers absent from the databases we searched.

This validation set (with the 33 matched studies marked as known
includes) is used downstream to test LLM screening pipeline sensitivity.
