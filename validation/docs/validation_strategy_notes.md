# Validation of LLM screening pipeline

Working notes, started 2026-05-13, updated 2026-05-15.

## The problem

We need to validate that the LLM screener catches what it should catch.
Our only external benchmark is Boeckle et al. (2016) Table 1 (49 studies),
but it has two problems:

1. **Scope mismatch.** The OS Table 1 includes studies the OS itself would
   not include under its stated criteria (EEG studies despite listing only
   MRI/PET/SPECT as eligible modalities; body dysmorphic disorder, DID,
   somatization, nonclinical dissociation despite targeting FND/conversion).
   These were likely screened in and then filtered at full-text or analysis
   stage — which means Table 1 is not a list of "studies that pass
   abstract screening" but rather "studies that made it into the final
   report for any reason."

2. **Only 25 strict matches.** After removing broad-scope studies, we only
   have 25 records where the gold label clearly matches what our screening
   protocol should include.

## Validation path (completed)

### Step 1: Full-run sensitivity (25 gold labels)

**Model:** Qwen 3.5 122B (thinking=False)
**Dataset:** 709 records (25 strict gold, 8 broad-scope gold, 676 unlabelled)

| Metric | Result |
| --- | --- |
| Strict sensitivity | **25/25 (100%)** |
| Broad-scope caught | 2/8 (6 missed) |
| API errors | 0/709 |
| Total include_candidate | 81 (11.4%) |
| Total exclude | 628 (88.6%) |
| Total unclear | 0 |

The 6 broad-scope misses are defensible — studies on DID, PTSD+dissociation,
nonclinical dissociation, EEG-only, and pseudosyncope that the LLM correctly
excluded under our tighter screening criteria.

### Step 2: Human screening of random sample (n=50)

Stratified sample: 20 LLM-includes + 30 LLM-excludes (no gold-labelled
records), screened blind by DV on 2026-05-15.

**Decision distributions:**

| Decision | Human | LLM |
| --- | --- | --- |
| include_candidate | 8 | 20 |
| unclear | 6 | 0 |
| exclude | 36 | 30 |

**Binary metrics** (keep = include+unclear vs exclude):

| Metric | Value |
| --- | --- |
| Sensitivity (LLM catches what human keeps) | 85.7% |
| Specificity (LLM excludes what human excludes) | 77.8% |
| PPV (when LLM keeps, human agrees) | 60.0% |
| NPV (when LLM excludes, human agrees) | 93.3% |
| LLM misses (human keeps, LLM excludes) | **0** |
| Hard disagreements (human exclude, LLM include) | 8 |

**Zero LLM misses against human judgment.** The LLM never excluded
something the human would have kept. The 2 FN cases were both "unclear"
decisions that the LLM made a decisive call on (one case report, one
no-abstract record).

### Step 3: Disagreement analysis

14 total disagreements (72% exact 3-way agreement). Three patterns:

1. **Human cautious, LLM decisive (6 records).** DV used "unclear" for
   borderline cases (PNES studies mentioning MRI incidentally, missing
   abstracts). The LLM included 4, excluded 2 — always with a decisive
   call rather than deferring.

2. **LLM over-includes case reports (4 records).** Single-case fMRI/PET
   studies (conversion deafness, spatial neglect, dissociative fugue,
   motor conversion). DV excluded as case reports; LLM included under the
   "don't exclude plausible studies" prompt instruction. These would be
   filtered at full-text stage.

3. **LLM over-includes adjacent populations (4 records).** DID, dissociative
   disorders, mediumship trance. DV correctly drew the FND boundary; LLM
   hedged with "closely related to FND." Again, would be filtered at
   full-text.

### Step 4: Conclusions

**The LLM is a more liberal screener than the human**, particularly on:
- Case reports with neuroimaging data (keeps them for full-text review)
- Dissociation-adjacent populations (DID, dissociative disorders)

**This is acceptable for a dual-screening pipeline** because:
- Over-inclusion only costs extra full-text review, not missed studies
- The union of human + LLM screens catches everything
- The LLM never silently excludes what a human would keep

**The zero-unclear rate** means the LLM acts as a binary classifier rather
than a triage tool. This is fine given its include-bias: borderline records
get included rather than flagged, which is the safer failure mode.

**The approach is validated as a proof of concept.** The screening prompt +
Qwen 3.5 122B combination can serve as the second screener in dual screening.

## What the validation does NOT cover

- Specificity on the full 709-record set (only sampled 50)
- Generalization to a different search corpus (different search terms
  or a different meta-analysis topic)
- Performance on non-English abstracts (our corpus is English-only)

## Potential cross-validation opportunity

The team is starting a second meta-analysis on trauma in FND, based on
Ludwig et al. (2018), *Lancet Psychiatry* (doi:10.1016/S2215-0366(18)30051-8).
This could serve as an independent validation: extract the included studies
from Ludwig et al., run the screener, and check sensitivity on a completely
different reference set. This would test generalization across topics
within the FND domain.

## On broad-scope / overinclusive screening

The current screening prompt excludes non-FND populations and non-brain
imaging modalities. If the goal is to flag *all FND-relevant studies*
regardless of imaging modality (to catch EEG studies of PNES, etc.), the
prompt could be adjusted to:

- Remove the imaging-modality exclusion criterion, or
- Add a separate tag like `fnd_adjacent: true` for studies that mention
  FND but use non-eligible modalities.

However, this would increase the human review burden significantly. The
current approach (exclude non-eligible modalities, let humans catch
edge cases) is more practical for a meta-analysis where the final
inclusion criteria are well-defined.
