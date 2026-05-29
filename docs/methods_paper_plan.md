# Methods Paper Plan: LLM Screening Validation for Neuroimaging Meta-Analyses

Last updated: 2026-05-21

## Working title

"Comparing large language model classes for title/abstract screening in
neuroimaging systematic reviews: a dual-benchmark validation study"

## Motivation and literature gap

The field of LLM-assisted screening for systematic reviews is growing fast
(2024-2026), but several gaps remain that a well-designed study can fill:

1. **No head-to-head model-class comparison on the same screening task.**
   Most published studies test 1-3 models (e.g., Parmar et al. 2026 test
   GPT-4 + Claude + Gemini; Cambridge 2025 test Llama 3 + GPT-4o-mini).
   The PNAS paper (Gao et al. 2025) tested 18 LLMs but they were all run on
   3 general-medicine reviews, not on a neuroimaging/neuroscience task.
   Nobody has compared *classes* of models (small local < 10B, large open
   ~100B, frontier mid-tier, frontier full) on identical prompts and criteria
   for a single domain-specific task.

2. **No domain-specific validation in neuroimaging/neuroscience.**
   All published validations are in clinical medicine, oncology,
   physiotherapy, or general biomedical topics. Neuroimaging screening
   requires domain-specific judgment (imaging modality recognition,
   coordinate reporting, clinical population boundaries) that may challenge
   models differently.

3. **Poor evaluation methodology in existing papers.**
   LLM4SCREENLIT (arXiv Nov 2025) analyzed 29 papers and found: only 10%
   report MCC, only 24% report full confusion matrices, and zero papers
   price the cost of false negatives. Most rely on accuracy or F1, which
   are misleading under the extreme class imbalance typical of SR screening
   (~5-15% inclusion rate).

4. **No dual-benchmark validation on independent reference standards.**
   Most studies validate on a single review. We have two independent
   benchmarks: Boeckle et al. (2016) and Ludwig et al. (2018), which test
   generalization across topics within the same domain.

## How previous studies set up their screening

### Parmar et al. (2026, medRxiv/PMC) — "Collaborative LLMs"
- **Task:** 5 oncology SRs, 11,300 articles total
- **Models:** GPT-4 Turbo, Claude-3-Sonnet, Gemini-Pro-1.0 (3 commercial)
- **Prompt:** Zero-shot chain-of-thought; inclusion criteria as Boolean
  questions; temperature=0 for determinism
- **Evaluation:** Accuracy, precision (for exclusion), recall (for
  inclusion), WSS (work saved over sampling)
- **Key finding:** Collaborative approach (2 LLMs + conflict resolution by
  3rd) achieved 98.5% recall, 99.9% precision; WSS 63.5% vs 45.2%
  individual
- **Limitation:** Oncology only; proprietary models only; no WMCC or
  cost-benefit

### Gao et al. (2025, PNAS) — "Transforming literature screening"
- **Task:** 3 SRs (physiotherapy, neurology, digital health), 4,662 / 1,741 /
  66 records
- **Models:** 18 LLMs including GPT-3.5/4/4o, Claude, Llama 3 (8B, 70B),
  Mistral 7B, Gemma 7B/9B/27B, Mixtral 8x22B, Qwen 2.5 7B
- **Prompt:** Zero-shot; each inclusion criterion evaluated as separate
  Boolean; inclusion = all criteria true
- **Evaluation:** Precision, recall, specificity, F1, MCC, PABAK
- **Key finding:** Criteria formulation matters more than model choice;
  GPT-4o best by MCC (0.349); smaller models sometimes outperform larger
  ones; workload reduction 33-93%
- **Limitation:** No cost-benefit analysis; no WMCC; general medicine topics

### LLM4SCREENLIT (Nov 2025, arXiv) — Critical review
- **Analyzed:** 29 papers on LLM screening
- **Recommendations:**
  1. Report **Lost Evidence** (1 - recall) as primary metric
  2. Use **Weighted MCC (WMCC)** with w=10 default weighting
  3. Report **full confusion matrices** (TP, FP, TN, FN)
  4. Treat **unclassifiable outputs as positives** (human review)
  5. Include **non-LLM baselines** where available
  6. Use **leakage-aware designs** (separate prompt development from
     evaluation data)
  7. **Cost-benefit analysis**: price false negatives > false positives

### Kim et al. (2025, JMAI) — Systematic review & meta-analysis
- Meta-analyzed LLM screening tools; found >90% sensitivity across multiple
  models; developed a new screening tool
- Useful as a reference for positioning our work

### Synthesa AI (medRxiv 2025)
- Commercial tool, 9 domains, 100% sensitivity, 99.4% specificity
- Found 32 extra relevant studies missed in original reviews
- Limitation: proprietary, not reproducible

## Assessment of our current approach

**Strengths:**
- Domain-specific (FND neuroimaging) — unique in the literature
- External benchmark (Boeckle 2016, 25 gold-label studies)
- 100% strict gold-label sensitivity with Qwen 3.5 122B
- Zero LLM misses on 50-record human comparison
- Open model (reproducible, locally deployable)
- Existing pipeline with prompt versioning and output archival

**Weaknesses to address for a methods paper:**
- Only one model seriously tested (Qwen 3.5 122B); Gemma4 pilot only
- No WMCC or cost-benefit analysis
- No formal confusion matrix reporting per LLM4SCREENLIT
- No prompt sensitivity analysis
- No independent second benchmark (Ludwig 2018 planned but not executed)
- Prompt development and evaluation on overlapping data (potential leakage)

## Proposed study design

### Model class ladder

| Class | Model | Parameters | Access | Cost |
| --- | --- | --- | --- | --- |
| Small local | Qwen 2.5 7B (or Llama 3.1 8B) | ~7-8B | LM Studio | Free (local GPU) |
| Medium open | Qwen 3 32B (or Mistral-Small 24B) | ~24-32B | LM Studio | Free (local GPU) |
| Large open | Qwen 3.5 235B (or DeepSeek-V3) | ~122-235B | LM Studio or API | Free/cheap |
| Frontier mid | GPT-4.1-mini (or Gemini 2.5 Flash) | Unknown | API | ~$0.40/1M input |
| Frontier full | GPT-4.1 (or Claude Sonnet 4) | Unknown | API | ~$2/1M input |

The exact models should be finalized based on what's available at run
time. The key is having representatives from each *class* (size/access tier).

The currently validated model (Qwen 3.5 122B) falls between "large open"
and the new Qwen 3.5 235B; include both if feasible.

### Evaluation benchmarks

**Benchmark 1: Boeckle et al. (2016) — FND neuroimaging**
- 709 records from OS-validation search
- 25 strict gold-label include_candidate
- 8 broad-scope (reported separately)
- Already available in `data/validation_screening_set.jsonl`

**Benchmark 2: Ludwig et al. (2018) — Trauma in FND**
- Independent reference set from Lancet Psychiatry paper
- 34 case-control studies extracted into `data/ludwig_included_studies.csv`
- `fnd_meta_search.py --ludwig_validation` implements 3-block search
- `scripts/validate_ludwig_recall.py` builds validation JSONL
- `prompts/trauma_v1.txt` provides Ludwig-specific screening prompt
- Tests generalization across topics within FND domain
- **Infrastructure built; needs end-to-end run**

### Prompt conditions

1. **Baseline prompt** — current production prompt (as validated)
2. **Sensitivity-enhanced prompt** — add explicit instruction to include
   when uncertain (per medRxiv 2026 locally deployed model paper)
3. **Criteria-decomposed prompt** — break inclusion criteria into separate
   Boolean questions (per PNAS approach)

All prompts identical across models. No per-model prompt tuning.

### Leakage-aware design

- Prompt development done on Benchmark 1 (Boeckle data)
- Benchmark 2 (Ludwig data) is fully held out — zero prompt exposure
- Report results separately for both benchmarks
- The "development vs. held-out" split addresses LLM4SCREENLIT concern #6

### Evaluation metrics (per LLM4SCREENLIT)

For each model x prompt x benchmark combination, report:

1. **Full confusion matrix** (TP, FP, TN, FN)
2. **Lost Evidence** (1 - recall / sensitivity)
3. **Recall / Sensitivity** (how many true includes are caught)
4. **Specificity** (how many true excludes are correctly excluded)
5. **PPV / Precision** (when model says include, is it right)
6. **NPV** (when model says exclude, is it right)
7. **MCC** (Matthews Correlation Coefficient — chance-corrected)
8. **WMCC** (Weighted MCC with w=10 default; sensitivity analysis at w=5,20)
9. **F1-score** (for comparability with prior work)
10. **WSS@95** (Work Saved over Sampling at 95% recall, if applicable)
11. **Unclassifiable rate** (API errors, parse failures — treated as includes)
12. **Cost per record** (compute time + API cost)
13. **Wall-clock time** per model

### Cost-benefit analysis

- Price a false negative at 10x a false positive (LLM4SCREENLIT default)
- Compare total cost: (API cost) + (human review cost for FP + unclassifiable)
  + (penalty for missed studies)
- Report break-even analysis: at what FN penalty weight does model X
  become preferable to model Y?

## Suggested changes to current pipeline

1. **Add WMCC calculation** to `scripts/compare_human_llm.py` or create a
   new `scripts/evaluate_model_comparison.py` that computes all
   LLM4SCREENLIT metrics from confusion matrix data.

2. **Standardize output format** across all models: JSON with decision,
   reasoning, and confidence. Already partially done.

3. **Add API cost tracking** to `scripts/llm_screen_abstracts.py` —
   log token counts and compute cost per record for API-based models.

4. **Build Ludwig 2018 benchmark:** DONE — `data/ludwig_included_studies.csv`,
   `scripts/resolve_ludwig_references.py`, `scripts/validate_ludwig_recall.py`,
   `prompts/trauma_v1.txt`, and `fnd_meta_search.py --ludwig_validation`.

5. **Prompt variants:** DONE — prompts externalized to `prompts/` directory,
   `--prompt` flag added to `scripts/llm_screen_abstracts.py`. Currently:
   `prompts/neuroimaging_v1.txt` (baseline) and `prompts/trauma_v1.txt`
   (Ludwig). Add `prompts/sensitivity_v1.txt` and `prompts/decomposed_v1.txt`
   for the model comparison study.

## Execution plan

### Phase 1: Infrastructure (1-2 days)
- [x] Build Ludwig 2018 validation benchmark
- [x] Extract prompts into versioned files
- [ ] Add WMCC and full LLM4SCREENLIT metrics to evaluation scripts
- [ ] Add API cost tracking to screening script

### Phase 2: Model runs (2-3 days)
- [ ] Run all 5 models x 3 prompts x 2 benchmarks = 30 conditions
- [ ] Each run: ~700-1000 records, sequential for reproducibility
- [ ] Archive all raw outputs with model/prompt/benchmark metadata

### Phase 3: Analysis (1-2 days)
- [ ] Compute all metrics for each condition
- [ ] Generate comparison tables and figures
- [ ] Cost-benefit analysis
- [ ] Statistical comparison (bootstrap CIs for sensitivity differences)

### Phase 4: Writing (3-5 days)
- [ ] Follow TRIPOD-LLM reporting guidelines (referenced in Parmar 2026)
- [ ] Explicit comparison with Gao et al. (PNAS), Parmar et al., and
  LLM4SCREENLIT recommendations
- [ ] Deposit prompts, code, and evaluation data in supplementary/GitHub

## Target journals

1. **Research Synthesis Methods** — primary target; methods-focused,
   impact factor ~9, audience is exactly right
2. **Systematic Reviews** — BMC journal, open access, good fit
3. **Journal of Clinical Epidemiology** — if framed as methodology for
   evidence synthesis
4. **JAMIA** — if framed as health informatics

## Timeline estimate

- Phase 1-2: 1-2 weeks (infrastructure + runs)
- Phase 3: 1 week
- Phase 4: 2-3 weeks
- Total: ~4-6 weeks of active work (can overlap with meta-analysis screening)

## Key references

- Eickhoff SB et al. (2016). Behavior, sensitivity, and power of ALE. NeuroImage.
- Gao et al. (2025). Transforming literature screening. PNAS.
- Kim et al. (2025). Evaluating LLMs for title/abstract screening. JMAI.
- LLM4SCREENLIT (2025). Recommendations on assessing LLMs for screening. arXiv:2511.12635.
- Parmar et al. (2026). Collaborative LLMs for screening. medRxiv.
- Synthesa AI (2025). Validation across 9 studies. medRxiv.
