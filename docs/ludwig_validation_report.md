# Ludwig et al. (2018) Search Validation Report

Generated: 2026-06-10 20:11 UTC  
Search run: `fnd_search_20260528_111459`

## Context

This report validates whether our Ludwig-mode search strategy recovers
the 34 case-control studies included in Ludwig et al. (2018) "Stressful
life events and maltreatment in conversion (functional neurological)
disorder: systematic review and meta-analysis of case-control studies"
(*Lancet Psychiatry*, doi:10.1016/S2215-0366(18)30051-8).

Ludwig searched PubMed and Science Direct from 1965 to Nov 4, 2016 using:
`("psychogenic" OR "conversion disorder" OR "non-epileptic") AND ("abuse"
OR "life event") AND ("control" OR "controlled" OR "case-control")`.

They also identified 20 additional studies through reference-list chasing,
so database-only recall below 100% is expected.

### Per-database counts

| Database | Records |
| --- | ---: |
| pubmed | 34 |
| europepmc | 33 |
| wos | 0 |
| scopus | 192 |
| **After deduplication** | **197** |

## Results: 14/34 studies found

### Matched studies

| # | Study | Year | Symptom type | Source DB | Match method |
| ---: | --- | ---: | --- | --- | --- |
| 1 | Alper et al. | 1993 | Non-epileptic seizures | pubmed | doi |
| 2 | Baker et al. | 2012 | Functional voice disorder | scopus | doi |
| 3 | Binzer et al. | 1998 | Functional motor disorder | scopus | doi |
| 4 | Binzer et al. | 2004 | Non-epileptic seizures | scopus | doi |
| 5 | Jawad et al. | 1995 | Non-epileptic seizures | scopus | doi |
| 6 | Kaplan et al. | 2013 | Non-epileptic seizures | scopus | doi |
| 7 | Kranick et al. | 2011 | Functional motor disorder | pubmed | doi |
| 8 | Nicholson et al. | 2016 | Functional motor disorder | scopus | doi |
| 9 | Ozcetin et al. | 2009 | Non-epileptic seizures | pubmed | doi |
| 10 | Plioplys et al. | 2014 | Non-epileptic seizures | scopus | doi |
| 11 | Say et al. | 2014 | Non-epileptic seizures | pubmed | doi |
| 12 | Testa et al. | 2012 | Non-epileptic seizures | pubmed | doi |
| 13 | Betts et al. | 1992 | Non-epileptic seizures | pubmed | title_jaccard(0.62) |
| 14 | Tojek et al. | 2000 | Non-epileptic seizures | pubmed | title_jaccard(1.00) |

### Not found (20 studies)

These studies were likely found by Ludwig via reference-list chasing
or Science Direct (not directly replicated in our API search).

| Study | Year | Symptom type | Journal |
| --- | ---: | --- | --- |
| Akyuz et al. | 2004 | Non-epileptic seizures | Epileptic Disorders |
| Almis et al. | 2013 | Non-epileptic seizures | Comprehensive Psychiatry |
| Arnold et al. | 1996 | Non-epileptic seizures | Psychosomatics |
| Bakvis et al. | 2009 | Non-epileptic seizures | Epilepsia |
| Barnett et al. | 1971 | Functional neurological disorder | Psychiatry in Medicine |
| Berkhoff et al. | 1998 | Non-epileptic seizures | Epilepsia |
| Chabrol et al. | 1995 | Functional neurological disorder | European Psychiatry |
| Dikel et al. | 2003 | Non-epileptic seizures | Epilepsy and Behavior |
| House et al. | 1988 | Functional voice disorder | Journal of Psychosomatic Research |
| Kozlowska et al. | 2011 | Functional neurological disorder | Psychosomatic Medicine |
| Kuyk et al. | 1999 | Non-epileptic seizures | Journal of Nervous and Mental Disease |
| Litwin et al. | 2000 | Non-epileptic seizures | Journal of Trauma and Dissociation |
| McDade et al. | 1992 | Non-epileptic seizures | Seizure |
| Mokleby et al. | 2002 | Non-epileptic seizures | Epilepsia |
| Proenca et al. | 2011 | Non-epileptic seizures | Epilepsy and Behavior |
| Reilly et al. | 1999 | Non-epileptic seizures | Psychological Medicine |
| Roelofs et al. | 2002 | Functional neurological disorder | American Journal of Psychiatry |
| Salmon et al. | 2003 | Non-epileptic seizures | Psychosomatic Medicine |
| Scevola et al. | 2013 | Non-epileptic seizures | Epilepsy and Behavior |
| Steffen et al. | 2015 | Functional neurological disorder | BMC Psychiatry |

## Conclusion

Database search recovered **14/34** Ludwig-included
studies (20 not found).

Unrecovered studies are expected: Ludwig identified 20 of their 1189
initial records through reference-list chasing, and we do not search
Science Direct directly (partially covered by Scopus and Europe PMC).

This validation set (with the 14 matched studies marked as known
includes) is used downstream to test LLM screening pipeline sensitivity.
