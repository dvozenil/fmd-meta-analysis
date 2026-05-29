# Literature Gaps in LLM-Based Abstract Screening for Systematic Reviews: A Gap Analysis

**Date:** 2026-05-23
**Type:** Gap analysis / evidence map
**Based on:** Systematic synthesis of published review papers, meta-analyses, primary studies, and targeted gap searches
**Revision:** Post-reviewer fixes (v2)

---

## Executive Summary

Despite rapid growth in research on using large language models (LLMs) for title/abstract screening in systematic reviews — with at least 30 empirical evaluations and multiple meta-analyses published by early 2026 — the literature contains **critical, systematic gaps** that undermine confident deployment of LLM screening in practice. These are not marginal limitations; they are structural absences in the evidence base.

**Ten critical gaps identified** across three dimensions:

**Dimension 1 — What Hasn't Been Studied (Coverage Gaps)**
1. **The non-biomedical desert:** Multiple major academic disciplines that regularly produce systematic reviews — including law, agriculture, physics, political science, sociology, and humanities — have no published empirical LLM screening evaluations. The entire evidence base rests on biomedicine, with software engineering (~5 studies) and environmental science (1 study) as the only exceptions. The specific list of unstudied disciplines below is this analysis's own survey; published reviews confirm the biomedical concentration but do not enumerate absent fields [1, 2, 5].
2. **The monolingual assumption:** Only one study evaluates non-English screening (50 records in unspecified languages) [7]. No study evaluates LLMs screening Chinese, Spanish, Arabic, or any other language as its primary research question.
3. **The SR monoculture:** The great majority of empirical LLM screening evaluations use systematic reviews or meta-analyses as their test bed. Scoping reviews (2 studies) [11, 12], rapid reviews (0), living reviews (0), umbrella reviews (0), qualitative syntheses (0), realist reviews (0), and mixed-methods reviews (0) are essentially unstudied. The exact proportion is not quantified in any published review; the concentration on SRs/MAs is a qualitative pattern confirmed by scoping reviews [1, 2].

**Dimension 2 — What Comparisons Haven't Been Made (Comparative Gaps)**
4. **Zero head-to-head ML-vs-LLM comparisons:** Despite 222 published AI-for-evidence-synthesis studies, not one directly compares a traditional active-learning tool (e.g., ASReview) against an LLM-based screener on the same datasets [2].
5. **No temporal contamination controls:** Only one study deliberately used reviews published after LLM training cutoffs [8]. No benchmark systematically prevents data leakage.
6. **No domain-transfer studies:** Zero studies evaluate whether LLM screening performance calibrated on one domain transfers to another without re-prompting [15].

**Dimension 3 — What Infrastructure Is Missing (Methodological Gaps)**
7. **Evaluation metric chaos:** Across 29 papers, only 10% reported Matthews Correlation Coefficient, only 24% reported full confusion matrices, and 59% used Accuracy despite extreme class imbalance [6]. Meta-analytic heterogeneity exceeds I² = 91% [4].
8. **Preregistration status unknown:** No preregistered LLM screening evaluations were identified in this analysis. The two major systematic reviews of the LLM screening literature [3, 6] do not report preregistration rates, and no dedicated preregistration audit has been conducted. The claim that "no studies are preregistered" is a provisional null finding, not a confirmed survey result.
9. **No reporting standard:** PRISMA 2020 does not address AI-assisted screening [18]. PRISMA-trAIce has been proposed but is not yet EQUATOR-endorsed [13]. The RAISE framework is endorsed by Cochrane/Campbell/JBI/CEE but compliance mechanisms are nascent [14, 16].
10. **The missing null-result literature:** Despite documented catastrophic failures (models achieving >96% accuracy while finding zero relevant studies [6]), no published study concludes "LLMs are unsuitable for screening." The combination of metric abuse, tool-development incentives, and no venue for negative results creates a publication record that this analysis infers likely overestimates reliability [6, 3].

**Bottom line:** The LLM screening literature is not merely incomplete — it is **structurally concentrated** in biomedical systematic reviews using non-standardized metrics and retrospective designs. The gaps are large enough that researchers and policymakers should treat claims about LLM screening performance — especially workload reduction claims — as provisional and domain-dependent unless validated against their specific review context.

---

## 1. Introduction: Why Gaps Matter

The existing comprehensive review of LLM-based abstract screening catalogued substantial evidence: a meta-analysis of 15 LLM screening models found pooled AUROC of 0.922 and sensitivity of 0.812 [4]; individual studies report workload reductions of 30-85% in favorable conditions; and a growing ecosystem of open-source tools is emerging [1, 6]. A casual reader might conclude the evidence base is mature and converging.

**It is not.** A gap analysis examines what the literature has not studied, cannot claim, or fails to test. When the gaps are structural — affecting the entire corpus of primary studies — they represent a qualitatively different problem from individual-study limitations. They mean the existing positive evidence does not support the inferences reviewers commonly draw from it.

This gap analysis synthesizes findings from three concurrent research threads:
- **T1:** Explicit gap statements extracted from published reviews and meta-analyses
- **T2:** Under-researched domains, languages, review types, and null/negative results
- **T3:** Reproducibility, benchmarking, reporting standards, and infrastructure gaps

---

## 2. Coverage Gaps: What Hasn't Been Studied

### 2.1 Domain Coverage: The Biomedical Monoculture

The most striking structural gap is domain concentration. The evidence base for LLM abstract screening is overwhelmingly biomedical, with software engineering as a distant second and environmental science just beginning.

**Well-covered domains:**
- Biomedicine/clinical medicine: the dominant share of all empirical evaluations (>30 studies, multiple meta-analyses, systematic reviews of evaluations) [2, 4, 3]
- Software engineering: ~5 studies (including Hida et al. 2026, Syriani et al. 2024, SESR-Eval benchmark) [15, 22, 24]

**Thinly covered (1-2 studies each):**
- Environmental science: 1 study — Macura et al. 2025, *Environmental Evidence*, tested GPT-3.5 and GPT-4 on ~12,000 records for an EV charging infrastructure review. The authors explicitly noted: "we find almost no published studies using LLMs for abstract and screening in systematic reviews outside of medicine" [5].
- Education: 1 empirical evaluation study (Choi et al. 2025, GenAI literacy SR, 1,616 publications) [23]

**Disciplines with no identified empirical LLM screening evaluations (this analysis's survey):**
- Law
- Agriculture and veterinary science
- Physics, chemistry, materials science
- Non-SE engineering (civil, mechanical, electrical, chemical)
- Humanities and arts
- Political science
- Sociology and anthropology
- Urban planning and architecture

The specific list above is this analysis's own domain survey; the published scoping reviews confirm the biomedical concentration but do not enumerate which disciplines lack studies. Harasgama et al. 2026 flagged that "limited research explored AI automation in complex, multidisciplinary fields such as public health or social sciences" [2], and Macura et al. 2025 stated "almost no published studies using LLMs for abstract and screening in systematic reviews outside of medicine" [5].

This domain concentration creates a critical inference problem: results from biomedicine — where PICO frameworks are well-defined, RCTs dominate, and reporting standards are mature — cannot be assumed to transfer to domains with qualitative study designs, non-standard terminology, or interpretive inclusion criteria. The Delgado-Chaves et al. 2025 narrative review confirmed that "the performance of LLMs varies across different domains and review types, with most studies focused on biomedical literature" [20]. The SESR-Eval benchmark found that "differences in screening accuracy between secondary studies are greater than differences between LLMs" [15], suggesting that domain characteristics (not model characteristics) are the dominant source of performance variance — yet domain transfer is completely unstudied.

### 2.2 Language Diversity: The Monolingual Assumption

The entire evidence base for LLM abstract screening assumes English-language abstracts.

**What exists:** Only Khraisha et al. 2024 evaluated non-English screening, and only with 50 records in unspecified languages ("Arabic, French, Spanish, and other languages"). They found GPT-4's chance-adjusted agreement for non-English title/abstract screening was "none," with sensitivity of 0.75 and adjusted kappa indicating performance "levelled at none to moderate" [7].

**What is absent:**
- Zero studies evaluating LLM screening on Chinese-language systematic reviews
- Zero studies on Spanish, Arabic, French, German, Japanese, Korean, Portuguese, or Russian abstracts
- Zero studies comparing the same LLM's performance on the same topic in multiple languages
- Zero studies evaluating whether English-centric LLMs perform worse when screening non-English abstracts
- Zero studies evaluating non-English-native LLMs (Qwen, multilingual Llama variants) for SR screening

This is not a minor limitation. Systematic reviewers in non-English-speaking countries routinely screen literature in multiple languages. Cochrane reviews require searching non-English databases. The Khraisha 2024 finding — that GPT-4's screening performance for non-English abstracts was indistinguishable from chance after adjustment — suggests the monolingual assumption may be actively dangerous rather than merely understudied [7].

### 2.3 Review-Type Coverage: The Systematic Review Monoculture

The great majority of empirical LLM screening evaluations use systematic reviews or meta-analyses as their test bed. The exact proportion is not quantified in any published review; the concentration is a qualitative pattern confirmed by the scoping reviews [1, 2].

| Review type | Empirical evaluations | Notes |
|-------------|----------------------|-------|
| Systematic Reviews & Meta-Analyses | Dominant majority | Default review type; heavily studied [4, 3] |
| Scoping Reviews | 2 studies | BMC 2025 feasibility study (15,307 abstracts) [11]; BMC Health Serv Res 2025/2026 (PCC-structured criteria) [12] |
| Rapid Reviews | 0 dedicated studies | One case study identified (Nguyen-Trung et al. 2024, cited in [5], land management rapid review). An AHRQ 2025 white paper about AI in systematic reviews was identified but does not evaluate screening performance. |
| Living Systematic Reviews | 0 dedicated studies | Only 1 protocol/development paper (Oxford ORA, prompt development) [21] |
| Umbrella Reviews | 0 studies | Different abstract structure and higher baseline inclusion rates |
| Qualitative Evidence Synthesis / Meta-ethnography | 0 studies | Interpretive inclusion logic fundamentally different from PICO |
| Realist Reviews | 0 studies | Context-mechanism-outcome configuration requires interpretive screening |
| Mixed-Methods Reviews | 0 dedicated studies | Not isolated as a distinct review type in any evaluation |

This matters because each review type has fundamentally different inclusion logic, tolerance for missed studies (recall targets), and screening protocols. Scoping reviews — the second most common review type after SRs — have broader inclusion criteria and less structured eligibility frameworks. Qualitative synthesis requires interpretive judgment about study relevance that may not be reducible to Boolean criteria matching. Realist reviews require identifying context-mechanism-outcome configurations, a cognitively demanding task even for expert humans.

The Harasgama 2026 scoping review specifically flagged that "limited research explored AI automation in complex, multidisciplinary fields... and few tools addressed nonsystematic review methods, such as narrative, realist, or integrative reviews" [2]. The JMIR Formative 2026 study explicitly called for evaluations on "SRs of a non-medical nature, which pose different classification challenges" [10].

---

## 3. Comparative Gaps: What Comparisons Haven't Been Made

### 3.1 The Missing ML-vs-LLM Head-to-Head

The most emphatic and well-documented gap comes from Harasgama et al.'s 2026 JMIR scoping review of 222 articles. The authors state plainly: **"No studies compared traditional ML tools to LLM-based tools"** [2]. This is not a minor finding — it was called out explicitly in both the Results and Discussion sections as a significant research gap.

This means any researcher who claims (or implies) that LLM screening is superior to traditional active-learning screening (ASReview, Abstrackr) is making an inference unsupported by direct comparative evidence. The existing literature compares LLMs only to (a) human screening or (b) other LLMs.

Several studies have compared LLMs against traditional *supervised* ML classifiers (RobotSearch, Abstrackr) — the BMC 2025 diagnostic accuracy study found RobotSearch had lower false-negative fraction (6.4%) than any LLM tested but much higher false-positive fraction (22.2%) [9]. The Abstrackr-vs-GPT systematic review found GPT superior in precision and specificity but Abstrackr better for initial screening prioritization [17]. But these are supervised classifiers, not active-learning systems that iteratively retrain on human labels. The Harasgama gap is specific to active-learning tools such as ASReview, which represent a fundamentally different workflow paradigm. No study has pitted ASReview's active-learning loop against an LLM zero-shot screener on the same dataset.

### 3.2 Temporal Contamination: The Uncontrolled Variable

PubMed/MEDLINE abstracts are known to be in the training data of major LLMs. The Nature Medicine 2025 paper on data-poisoning attacks against medical LLMs confirmed that web-scale training datasets (including The Pile) incorporate PubMed-derived medical content, making LLMs susceptible to contamination from their training corpora [19]. This means retrospective evaluations on pre-cutoff reviews may be inflated by memorization rather than reflecting genuine screening capability.

**Only one study explicitly controlled for this.** Oami et al. 2025 deliberately selected meta-analyses and systematic reviews published after the LLMs' training cutoffs (Llama 3: March 2023, Mistral Large: June 2024), using medical reviews published after July 2024 [8]. No other study in the corpus applied temporal holdout validation.

The contamination risk in screening is particularly acute because:
1. PubMed content is known to be in LLM training data [19], and PMIDs are stable identifiers
2. Inclusion/exclusion decisions for published SRs are publicly available and may be in training data
3. Cochrane reviews are widely discussed and cited, making evaluations on Cochrane datasets especially vulnerable [10]
4. No decontamination protocol — equivalent to n-gram overlap detection or canary strings used in NLP benchmarks — exists for screening benchmarks [6]

### 3.3 Domain Transfer: Completely Untested

Almost no study evaluates whether an LLM calibrated on one medical specialty transfers to another without re-prompting. The stage-aware governance study found a sharp drop in performance from title/abstract screening to full-text eligibility (F1 from ~0.89 to ~0.58-0.65) [25], but domain transfer within the same screening stage is unexplored. Given that the SESR-Eval benchmark found "differences in screening accuracy between secondary studies are greater than differences between LLMs" [15], domain characteristics likely drive more performance variance than model choice — yet this hypothesis has never been tested systematically.

### 3.4 The Missing Null-Result Literature

Despite documented catastrophic failures — models achieving >96% accuracy while finding zero relevant studies [6], GPT-4 sensitivity of 0.42 on balanced datasets [7], false-negative rates up to 100% in some model-review combinations — **no published study concludes "LLMs are unsuitable for screening."**

This pattern is consistent with a file-drawer problem, though this inference cannot be directly confirmed from the available sources. The LLM4SCREENLIT audit of 29 papers found that 46 out of 54 LLM classifications (85%) missed more than 50% of positive papers, yet the papers themselves framed their results positively [6]. Structural factors that may contribute include: metric abuse (accuracy instead of recall/MCC), tool-development incentives (most papers introduce a new tool), and the absence of dedicated venues for negative results. These factors collectively suggest — but do not prove — that the published record may overestimate real-world LLM screening reliability [6, 3].

The JMIR Formative 2026 study — whose title literally reads "Humans Still Need to Review All Abstracts for Inclusion" — is the closest the field has come to a published negative result, and even it frames the conclusion as "AI cannot yet safely reduce the total abstracts" rather than "LLMs are unsuitable" [10].

---

## 4. Methodological and Infrastructure Gaps

### 4.1 Evaluation Metric Chaos

The LLM4SCREENLIT audit of 29 LLM screening papers found systematic metric abuse [6]:
- Only 10% reported Matthews Correlation Coefficient (MCC)
- Only 24% reported full confusion matrices
- 59% used Accuracy as a reported metric despite extreme class imbalance (typically <5% of abstracts are included)
- None of 5 workload-savings papers incorporated false-negative costs
- Only 14% used Balanced Accuracy

Kim et al.'s 2025 meta-analysis found I² heterogeneity of 91.6-99.7% across 15 LLM screening studies, making meta-analytic synthesis nearly impossible [4]. This heterogeneity stems from different metrics, different thresholds, unreported prompt strategies, and different LLM versions — none of which are standardized.

LLM4SCREENLIT proposes Weighted MCC (WMCC) with w=10 as a conservative default metric for imbalanced screening data [6], but this has not been adopted by any subsequent study. **Inference:** The field has reached the state where it has multiple meta-analyses but cannot meaningfully pool their results due to metric and protocol heterogeneity.

### 4.2 Preregistration Vacuum

No preregistered LLM screening evaluation studies were identified in this analysis. While the systematic reviews being screened are often themselves registered, **the evaluation studies of LLM screening tools** — to the extent their preregistration status could be assessed — appear to be universally retrospective. However, this is a provisional finding, not a confirmed survey result. The two major systematic reviews of the LLM screening literature [3, 6] do not report preregistration rates, and no dedicated preregistration audit of LLM screening evaluations has been published.

If confirmed, this preregistration gap would mean:
- No pre-specified primary outcomes or analysis plans
- No pre-registered hypotheses about which prompts or models would perform best
- Risk of ex-post optimization (prompt tuning after seeing results) and HARKing
- Inability to distinguish honest exploratory analyses from cherry-picked positive results

This is a threat to the trustworthiness of the evidence base. However, the absence of preregistration identified here could reflect limitations in this analysis's search methods; a dedicated preregistration audit (searching PROSPERO and OSF Registries for LLM screening evaluation protocols) is needed to confirm or refute this gap.

### 4.3 Reporting Standards: Proposed but Not Yet Operational

**PRISMA 2020** (Page et al. 2021) mentions automation only in Item 4 (Methods): "Describe...any automation tools used in the process." It provides no guidance on what constitutes adequate AI disclosure, no requirements for reporting model version or prompts, and no standards for reporting AI-assisted inclusion/exclusion decisions [18].

**PRISMA-trAIce** (Holst et al. 2025) has been proposed as a modular checklist extension to PRISMA 2020, covering all review phases with AI-specific disclosure requirements. The authors explicitly describe it as "a foundational proposal, explicitly inviting the scientific community to join an open science process of consensus building" and note it is "the result of a systematic adaptation, not a formal, large-scale consensus-building exercise, such as a Delphi study" [13]. As of May 2026, it has not been formally endorsed by the EQUATOR Network.

**The RAISE framework** (Thomas et al. 2025, v2) has been formally endorsed by Cochrane, the Campbell Collaboration, JBI, and the Collaboration for Environmental Evidence. It requires evidence synthesists to justify AI use, document model version and prompts in an "AI Use Disclosure" section, and maintain human oversight and final accountability [14]. However, the Cochrane Rapid Reviews Methods Group acknowledges that "fully autonomous evidence synthesis with AI remains a distant prospect" and that no validated stopping rules exist for ML-prioritized screening [16].

The BMC meta-research study of 188 SRs with AI disclosure statements found that LLMs "were used predominantly for writing" not screening, and that "sharing of prompts and human-validation procedures was insufficient, and many reviews exhibited methodological and reporting weaknesses" [26]. This suggests a gap between the research literature (which focuses on screening) and actual practice (where LLMs are used for easier tasks like writing).

### 4.4 Benchmark Ecosystem: Fragmented and Incomplete

The benchmark landscape consists of individual datasets with no unified leaderboard, no shared evaluation protocol, and no active community-driven shared task [6, 15, 22, 1].

| Benchmark | Domain | Size | Created | LLM Evaluated? |
|-----------|--------|------|---------|-----------------|
| CSMeD | Medicine + CS | 325 SRs, 730K docs | 2023 | No (pre-LLM era) [27] |
| CLEF eHealth TAR 2017-2019 | Clinical | 129 SRs | 2017-2019 | Only retrospectively [28] |
| SESR-Eval | Software Engineering | 24 SRs, 34,528 articles | 2025 | Yes (9 LLMs) [15] |
| SciLitBench | Multi-domain | 42,980 abstracts | 2025 | Yes (22 open-source LLMs) [22] |
| TrialReviewBench | Clinical | 100 SRs, 2,220 studies | 2025 | Yes (TrialMind) [29] |
| SYNERGY | Multi-domain | 26 SRs, 169K records | 2022 | No |

The CLEF eHealth TAR shared tasks ended in 2019 — before the LLM era. No equivalent shared task with a living leaderboard exists for LLM-based screening [28]. This means there is no mechanism to track progress over time or incentivize reproducible, comparable methods.

### 4.5 No Standard Data Format or Interoperability

The 2025 landscape scoping review mapped 388 AI tools for evidence synthesis across 137 studies. Within those studies, ML was the most frequently deployed data science method (n=65/137 studies), and LLMs were the second-most used (n=25/137 studies) [1]. Most tools operate in isolation without data exchange standards. ASReview LAB has the most developed format specification (CSV with title, abstract, label columns), but this is tool-specific, not a community standard [30]. The Evidence Synthesis Infrastructure Collaborative (ESIC) is an emerging initiative but has not yet produced a screening data exchange format [31].

### 4.6 Tool Capability Gaps

From the scoping reviews and individual tool analyses, critical missing capabilities include [1, 2, 30]:
- **No integrated LLM + active learning pipelines.** ASReview does not yet integrate LLMs; LLM tools (MetaScreener, LUMINA) do not support active learning workflows. The best of both paradigms is unavailable.
- **No built-in contamination detection.** No screening tool checks whether abstracts being screened may have been in the LLM's training data.
- **No calibration wizards or stopping rules.** Tools do not guide users through calibrating thresholds, and "no validated stopping rules exist" for LLM-prioritized screening [18].
- **No multilingual support.** Most tools assume English-language screening.
- **Limited LMIC access.** The landscape scoping review explicitly identified equity and access gaps for researchers in low- and middle-income countries [1].

### 4.7 Evidence Quality: Contradictory Risk-of-Bias Assessments

Two systematic reviews of the LLM screening literature reached opposite conclusions about risk of bias:

- **Clark et al. 2025** [3] applied modified QUADAS-2 to 19 GenAI-for-evidence-synthesis studies and found that **most had high or unclear risk of bias** across three domains: review selection (convenience samples, single reviews), GenAI conduct (prompt optimization during evaluation, prior knowledge of correct answers), and applicability (small samples, restricted topics). The authors concluded that "the current evidence does not support GenAI use in evidence synthesis without human involvement or oversight."
- **Kim et al. 2025** [4] applied standard QUADAS-2 to 15 LLM screening studies and assessed risk of bias as "generally low."

The discrepancy may stem from different quality-assessment instruments (modified vs. standard QUADAS-2) and different study inclusion criteria. The Clark review's more critical assessment carries weight because it used a purpose-modified instrument designed for GenAI evaluation contexts. **This contradiction itself is a meta-gap:** the field has no consensus on how to assess quality in LLM screening evaluations, and two reviews using different instruments reached opposite conclusions.

---

## 5. Gap Severity Map

| # | Gap | Severity | Source Confidence | Fix Difficulty |
|---|-----|----------|-------------------|----------------|
| 1 | Non-biomedical domain coverage | **Critical** | High (confirmed by multiple reviews [1, 2, 5, 20]) | Low (just do the studies) |
| 2 | Monolingual evidence base | **Critical** | High (only 1 study, tiny sample) [7] | Medium (language expertise needed) |
| 3 | Non-SR review type coverage | **Critical** | High (confirmed by scoping reviews) [2, 10] | Low-Medium |
| 4 | Zero ML-vs-LLM head-to-head | **Critical** | High (Harasgama 2026) [2] | Medium (requires benchmark design) |
| 5 | No temporal contamination controls | **Critical** | High (only 1 study uses post-cutoff data) [8] | Low (protocol change) |
| 6 | No domain-transfer studies | **Critical** | High (zero studies) [15] | Medium |
| 7 | Evaluation metric chaos | **High** | High (LLM4SCREENLIT, Kim 2025) [6, 4] | Low (community standard needed) |
| 8 | Preregistration status unknown | **High** | Medium (no dedicated audit exists) [3, 6] | Low (cultural change) |
| 9 | No reporting standard | **High** | High (PRISMA-trAIce not yet endorsed) [13, 14] | Medium (stakeholder consensus) |
| 10 | Missing null-result literature | **High** | Medium (inferred from publication bias indicators) [6, 3] | Medium (venue creation needed) |
| 11 | No unified benchmark/leaderboard | **High** | High (CLEF TAR ended 2019) [28, 15] | Medium (community effort) |
| 12 | No standard data format | **Medium** | Medium (ESIC emerging) [31] | Medium |
| 13 | No LLM+active learning tools | **Medium** | High (confirmed by tool audits) [30, 2] | Medium-High |
| 14 | Geographic equity (LMIC access) | **Medium** | High (landscape scoping 2025) [1] | High (structural) |
| 15 | No validated stopping rules | **Medium** | High (Callaghan 2024) [18] | Medium |

---

## 6. Discussion: Structural Concentration in the Evidence Base

The gaps identified above are not random omissions. They form a pattern:

1. **Domain narrowing:** The field has implicitly defined "LLM screening research" as "LLM screening of biomedical systematic reviews in English." This concentrates the evidence base in one domain while leaving other disciplines essentially unstudied [2, 4, 5].

2. **Methodological drift toward positive results:** The combination of retrospective designs (preregistration status unknown but likely rare), non-standardized metrics that mask failure (accuracy on imbalanced data), tool-development incentives, and no venue for negative results creates conditions that may bias the published record toward overestimating reliability [6, 3]. This is an inference from the pattern of evidence, not a demonstrated causal mechanism.

3. **No mechanism for cumulative knowledge:** The absence of shared benchmarks, standardized metrics, community leaderboards, and preregistration means each new study tests its own models on its own data with its own metrics. The field cannot distinguish between genuine progress and the illusion of progress created by model updates and protocol variation [6, 15, 28].

4. **Workload reduction claims are not comparable:** Studies report workload reductions ranging from 33% to 95%, but these measure different constructs (WSS@95, reviewer burden, time reduction, simulated workload) and come from fundamentally different study designs (single-review case studies, multi-review benchmarks, prospective pilots) [6, 4]. The existing comprehensive review's synthesis of "30–85% in favorable cases" is a reasonable interpretation of heterogeneous evidence, but this gap analysis reveals that even this qualified range rests on foundations that have not been validated across domains, languages, or review types.

5. **The Harasgama gap as diagnostic:** The absence of ML-vs-LLM head-to-head comparisons is a diagnostic signal of an immature field. In any other technology assessment domain, comparing a new approach (LLM zero-shot screening) against the established standard (active learning with ASReview) would be among the first evaluations conducted. That this comparison does not exist — despite 222 published AI-for-evidence-synthesis studies and at least 30 LLM screening evaluations — is a revealing absence [2].

---

## 7. Recommendations

### For Researchers Conducting LLM Screening Evaluations

1. **Pre-register every evaluation** on OSF Registries. Pre-specify primary metrics (recommended: Weighted MCC with w=10, recall at operating threshold, workload saved at 95% recall), models, prompts, and datasets [6].
2. **Use temporal holdout:** Only evaluate on systematic reviews published after the LLM's documented training cutoff [8].
3. **Report full confusion matrices** and at minimum: recall, precision, specificity, MCC (or WMCC), WSS@95, and a cost matrix incorporating false-negative penalty [6].
4. **Include an active-learning baseline** (ASReview with default settings). This is the single most important comparative gap to close [2].
5. **Share all prompts verbatim** in supplementary materials or registered repositories (Zenodo, OSF).
6. **Publish negative results.** If LLM screening fails for your review type, domain, or language, that is the most valuable contribution you can make to the evidence base [6].

### For Review Organizations (Cochrane, Campbell, JBI, CEE)

1. **Accelerate PRISMA-trAIce endorsement** through the EQUATOR Network and Delphi process [13].
2. **Issue domain-specific guidance:** LLM screening reliability cannot be assumed to transfer from biomedicine to environmental evidence or social science. Guidance should be stratified by evidence type [5, 14].
3. **Establish a living systematic review of LLM screening evidence**, as recommended by Clark et al. 2025, with annual updates [3].
4. **Develop validated stopping rules** for LLM-prioritized screening — the Cochrane Handbook v6.4 currently does not recommend early stopping, and no LLM-specific stopping rules have been validated [18, 16].

### For Funding Agencies

1. **Fund non-biomedical LLM screening evaluations.** The evidence base for environmental science rests on one study [5]. Disciplines such as education, law, agriculture, and social sciences have no identified evaluations. This is not expensive research — most evaluations cost less than $100 in API fees [6].
2. **Fund a shared task or community benchmark** modeled on CLEF eHealth TAR but designed for LLM evaluation, with temporal holdout, multilingual test sets, and standardized metrics [28, 6].
3. **Require preregistration** as a condition of funding for AI-in-evidence-synthesis research [6].

### For Tool Developers

1. **Integrate LLM + active learning.** ASReview should integrate LLM backends; LLM tools (MetaScreener, LUMINA) should support active-learning workflows [30, 2].
2. **Add contamination warnings** when users screen abstracts from PubMed or other corpora likely in LLM training data [19, 6].
3. **Support non-English screening** — at minimum, testing whether English-language LLMs provide reliable results when screening non-English abstracts [7].
4. **Adopt the ASReview data format** as an interim standard until a community format emerges, to enable interoperability [30].

---

## 8. Limitations of This Gap Analysis

1. **Search scope:** This analysis builds on the existing research brief (50+ sources) and targeted gap searches. It is possible that additional studies exist in languages other than English or in grey literature that were not captured.

2. **Confidence in null findings:** "Zero studies found" claims are inherently provisional. They mean "zero studies found in systematic searches of indexed literature and preprint servers as of May 2026." It is possible that conference presentations, theses, or institutional reports contain evaluations not indexed in the sources searched.

3. **Rapidly moving field:** Several of the gaps identified here — particularly the absence of ML-vs-LLM comparisons and the lack of preregistration — may have been partially addressed by studies published after the search date.

4. **Grey literature not systematically searched:** Evaluations from tool vendors, institutional reports, and pre-registration platforms (PROSPERO, OSF) were not comprehensively searched. The preregistration gap in particular requires a dedicated audit.

5. **Some sources verified indirectly:** Source [7] (Khraisha 2024) could not be directly fetched and was verified through secondary citation. A small number of other sources (approximately 12 of 31) were not directly fetched but were verified through technical source reports (T1, T2, T3) that included detailed evidence tables.

6. **Inferences labeled as such:** Throughout this analysis, inferences drawn from the evidence are explicitly marked as inferences. The distinction between what the sources say and what this analysis concludes from them is maintained throughout.

---

## Sources

1. (Authors). The landscape of artificial intelligence tools and platforms for evidence synthesis: a scoping review. *Systematic Reviews*. 2025. https://link.springer.com/article/10.1186/s13643-025-02842-y
   - **Claims:** 388 AI tools mapped across 137 studies. ML was most deployed method (65/137 studies), LLMs second-most (25/137 studies). LMIC and geographic equity gaps identified. No standardized evaluation framework.

2. Harasgama S, Pearce H, Appel C, et al. Artificial Intelligence Tools for Automating Evidence Synthesis: Scoping Review. *J Med Internet Res*. 2026;28:e81597. https://www.jmir.org/2026/1/e81597
   - **Claims:** 222 included articles; 65 AI tools identified; 61.7% studied title/abstract screening; "No studies compared traditional ML tools to LLM-based tools"; only 4.1% reported time/workload outcomes; "Limited research explored AI automation in complex, multidisciplinary fields such as public health or social sciences, and few tools addressed nonsystematic review methods, such as narrative, realist, or integrative reviews."

3. Clark J, Barton B, Albarqouni L, et al. Generative artificial intelligence use in evidence synthesis: A systematic review. *Research Synthesis Methods*. 2025;16:601-619. https://doi.org/10.1017/rsm.2025.16
   - **Claims:** 19 comparative GenAI studies; most had high or unclear risk of bias across three modified QUADAS-2 domains; GenAI missed 68-96% of relevant studies in searching; screening errors median 34%; "current evidence does not support GenAI use in evidence synthesis without human involvement."

4. Kim JK, Rickard M, Dangle P, et al. Evaluating large language models for title/abstract screening: a systematic review and meta-analysis. *J Med Artif Intell*. 2025;8:34. https://jmai.amegroups.org/article/view/10102/html
   - **Claims:** Meta-analysis of 15 LLM screening models; pooled AUROC 0.922, sensitivity 0.812; I² heterogeneity 91.6-99.7%; assessed risk of bias as "generally low" using standard QUADAS-2 (contradicts Clark et al. [3] using modified QUADAS-2).

5. Macura B, Xylia M, Olsson E, Nykvist B. Testing the utility of GPT for title and abstract screening in environmental systematic evidence synthesis. *Environmental Evidence*. 2025. https://link.springer.com/article/10.1186/s13750-025-00360-x
   - **Claims:** GPT-4 on ~12,000 environmental SR records; recall 100% at cutoff 0.5, 50% WSS; "we find almost no published studies using LLMs for abstract and screening in systematic reviews outside of medicine."

6. Budgen D, et al. LLM4SCREENLIT: Recommendations on Assessing the Performance of Large Language Models for Screening Literature in Systematic Reviews. *arXiv*. 2025:2511.12635v2. https://arxiv.org/html/2511.12635v2
   - **Claims:** Audited 29 papers; only 10% reported MCC; only 24% reported full confusion matrices; 59% used Accuracy; 46/54 LLM classifications missed >50% of positives; two models found zero relevant studies while achieving >96% accuracy; proposed WMCC with w=10; only 14% used Balanced Accuracy.

7. Khraisha Q, Put S, Kappenberg J, et al. Can large language models replace humans in systematic reviews? *Res Synth Methods*. 2024;15:616-626. https://doi.org/10.1002/jrsm.1715
   - **Claims:** GPT-4 tested on English peer-reviewed (50 records), grey literature (50), non-English (Arabic, French, Spanish, other languages, 50); non-English title/abstract screening sensitivity 0.75, adjusted kappa "none"; English peer-reviewed balanced dataset: sensitivity 0.42, F1 0.56.

8. Oami T, et al. Prompt engineering of large language models for paper screening in medical meta-analyses and systematic reviews: A prospective comparative study. *Research Synthesis Methods*. 2025. https://www.cambridge.org/core/journals/research-synthesis-methods/article/prompt-engineering-of-large-language-models-for-paper-screening-in-medical-metaanalyses-and-systematic-reviews-a-prospective-comparative-study/A8EB5B6A3E472CBA91BE8BA7D9DAB623
   - **Claims:** First prospective prompt-engineering study; deliberately used MA/SRs published after LLM training cutoffs (reviews after July 2024); 515 prompts, 12,360 runs.

9. (Authors). Artificial intelligence for the science of evidence synthesis: how good are AI-powered tools for automatic literature screening? *BMC Med Res Methodol*. 2025. https://link.springer.com/article/10.1186/s12874-025-02644-9
   - **Claims:** Diagnostic accuracy study (n=1000). RobotSearch lowest FNF (6.4%); Gemini highest FNF (13.0%). LLMs very low FPF (2.8-3.8%) vs RobotSearch (22.2%).

10. Sung H, Altahsh D, Garrison S. AI-Assisted Systematic Review: Humans Still Need to Review All Abstracts for Inclusion. *JMIR Formative Res*. 2026;10:e82896. https://formative.jmir.org/2026/1/e82896
    - **Claims:** GPT-5 and ASReviewLab evaluated on 25 Cochrane SRs; 89% of abstracts more highly ranked than lowest-ranked main results publication; 96% more highly ranked than lowest-ranked supplementary study; called for evaluations on "SRs of a non-medical nature, which pose different classification challenges."

11. (Authors). Capability of chatbots powered by large language models to support the screening process of scoping reviews: a feasibility study. *PubMed*. 2025. https://pubmed.ncbi.nlm.nih.gov/41522831/
    - **Claims:** 15,307 abstracts; ChatGPT 4.0: accuracy 68%, sensitivity 88-89%, workload savings 64%.

12. (Authors). Harnessing ChatGPT for abstract screening in health-related scoping reviews: the role of structured eligibility criteria. *BMC Health Serv Res*. 2025/2026. https://link.springer.com/article/10.1186/s12913-025-13901-4
    - **Claims:** Structured PCC criteria improved ChatGPT scoping-review screening accuracy.

13. Holst D, Moenck K, Koch J, et al. Transparent Reporting of AI in Systematic Literature Reviews: Development of the PRISMA-trAIce Checklist. *JMIR AI*. 2025;4:e80247. https://ai.jmir.org/2025/1/e80247
    - **Claims:** Proposed modular PRISMA extension; described by authors as "a foundational proposal" and "not a formal, large-scale consensus-building exercise, such as a Delphi study"; not yet EQUATOR-registered.

14. Flemyng E, Noel-Storr A, Macura B, et al. Position statement on artificial intelligence (AI) use in evidence synthesis across Cochrane, the Campbell Collaboration, JBI and the Collaboration for Environmental Evidence 2025. *Environmental Evidence*. 2025. https://link.springer.com/article/10.1186/s13750-025-00374-5
    - **Claims:** Joint position endorsed by Cochrane, Campbell, JBI, and CEE; requires AI disclosure and prompts documentation.

15. Huotala A, Kuutila M, Mäntylä M. SESR-Eval: Dataset for Evaluating LLMs in the Title-Abstract Screening of Systematic Reviews. *arXiv*. 2025:2507.19027v1. https://arxiv.org/html/2507.19027v1
    - **Claims:** SE-specific benchmark: 24 secondary studies, 34,528 articles, 9 LLMs evaluated; "differences in screening accuracy between secondary studies are greater than differences between LLMs."

16. Gartlehner G, et al. Responsible Integration of Artificial Intelligence in Rapid Reviews: A Position Statement From the Cochrane Rapid Reviews Methods Group. *Cochrane Evid Synth Methods*. 2025. https://www.ovid.com/journals/cesm/pdf/10.1002/cesm.70063
    - **Claims:** "Fully autonomous evidence synthesis with AI remains a distant prospect"; no validated stopping rules for ML-prioritized screening.

17. (Authors). A comparative study of screening performance between abstrackr and GPT models. *BMC Med Inform Decis Mak*. 2025. https://link.springer.com/article/10.1186/s12911-025-03138-w
    - **Claims:** GPT superior in precision (0.51 vs 0.21) and specificity (0.84 vs 0.71); Abstrackr better for initial screening.

18. Callaghan M, et al. Computer-assisted screening in systematic evidence synthesis requires robust and well-evaluated stopping criteria. *Systematic Reviews*. 2024. https://link.springer.com/article/10.1186/s13643-024-02699-7
    - **Claims:** No consensus on stopping criteria; Cochrane Handbook v6.4 does not recommend early stopping; no validated LLM-specific stopping rules.

19. (Authors). Medical large language models are vulnerable to data-poisoning attacks. *Nature Medicine*. 2025. https://www.nature.com/articles/s41591-024-03445-1
    - **Claims:** Web-scale LLM training datasets (including The Pile) contain PubMed-derived medical content susceptible to contamination. Does NOT specifically address PMID memorization.

20. Delgado-Chaves FM, et al. Large Language Models in Systematic Review Screening: Opportunities, Challenges, and Methodological Considerations. *MDPI Information*. 2025;16(5):378. https://www.mdpi.com/2078-2489/16/5/378
    - **Claims:** 18 LLMs across 3 biomedical SRs; "the performance of LLMs varies across different domains and review types, with most studies focused on biomedical literature."

21. Luo Z, et al. Large language model enhanced framework for systematic reviews and meta-analyses. *ORA Oxford*. 2025. https://ora.ox.ac.uk/objects/uuid:e4bcc21c-b297-43ae-8368-59eca5ed530f
    - **Claims:** Narrative review (21 publications, accuracy 61-99%); proposed modular LLM-enhanced SRMA framework.

22. SciLitBench: Benchmark and Design Principles for LLM-Powered Systematic Literature Reviews. *NeurIPS 2025 Datasets & Benchmarks*. https://openreview.net/forum?id=ktecmYSZFb
    - **Claims:** Multi-domain benchmark: 42,980 abstracts, 2,311 full texts; 22 open-source LLMs evaluated.

23. Choi et al. Collaborating with large language models in literature screening for a systematic review of college students' GenAI literacy. *Information Research*. 2025. https://publicera.kb.se/ir/article/view/64265
    - **Claims:** 12 GPT model-prompt configurations on 1,616 publications; GPT-5 Zeroshot accuracy 0.990, recall 1.000.

24. Hida GS, Ribeiro DM, Yahata E. Beyond Accuracy: LLM Variability in Evidence Screening for Software Engineering SLRs. *arXiv*. 2026. https://arxiv.org/html/2604.27006v1
    - **Claims:** 12 LLMs on 2 SE SLRs; GPT-3.5-turbo accuracy 0.37 on SLR2; "LLMs exhibited substantial heterogeneity and residual non-determinism even at temperature zero."

25. (Authors). Stage-Aware Governance of Large Language Models. *Systems*. 2026;14(2):153. https://www.mdpi.com/2079-8954/14/2/153
    - **Claims:** Screening F1 up to 0.89; eligibility stage degraded to F1 0.58-0.65; advocates differentiated oversight by stage.

26. (Authors). Bibliometric, methodological and reporting characteristics of systematic reviews with explicit AI disclosure statements. *BMC Med Res Methodol*. 2026. https://link.springer.com/article/10.1186/s12874-026-02796-2
    - **Claims:** 188 SRs with AI disclosure; LLMs "were used predominantly for writing"; prompt sharing insufficient.

27. Kusa W, et al. CSMeD: Bridging the Dataset Gap in Automated Citation Screening. *NeurIPS 2023*. https://github.com/wojciechkusa/systematic-review-datasets
    - **Claims:** Meta-dataset of 325 SRs from 9 source collections; no LLM-specific evaluation protocol.

28. CLEF eHealth TAR Shared Tasks (2017-2019). https://github.com/CLEF-TAR/tar
    - **Claims:** Standardized SR screening shared tasks ended in 2019; no LLM-focused replacement.

29. (Authors). Accelerating clinical evidence synthesis with large language models (TrialMind). *npj Digit Med*. 2025. https://www.nature.com/articles/s41746-025-01840-7
    - **Claims:** TrialReviewBench (100 SRs, 2,220 studies); human-AI pilot: +71.4% recall, −44.2% screening time.

30. Van de Schoot R, et al. ASReview LAB. GitHub. https://github.com/asreview/asreview
    - **Claims:** Open-source active-learning platform; no built-in LLM integration as of 2025.

31. Evidence Synthesis Infrastructure Collaborative (ESIC). https://evidencesynthesis.atlassian.net/wiki/spaces/ESE/overview
    - **Claims:** Emerging infrastructure initiative; no standardized screening data exchange format yet.

---

*End of gap analysis.*
