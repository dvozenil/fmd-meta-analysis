# Using Large Language Models for Abstract Screening in Systematic Reviews and Meta-Analyses: A Literature Review

**Date:** 2026-05-22  
**Scope:** Empirical studies, methods papers, tools, benchmarks, and meta-analyses evaluating the use of large language models (LLMs) for title/abstract eligibility screening in systematic reviews, meta-analyses, and scoping reviews, with primary focus on literature published 2023–2026.

---

## 1. Introduction

Systematic reviews and meta-analyses are the cornerstone of evidence-based medicine and policy, but their production is notoriously labor-intensive. A single review can require screening thousands of titles and abstracts, with abstract screening alone accounting for up to 20% of total review effort and spanning weeks to months of researcher time [^1][^13]. One economic analysis estimated the total labor cost of a single meta-analysis at over $141,000, with screening constituting a major fraction [^13]. The volume of published research is growing rapidly—by 2024, PubMed alone contained over 36 million articles, and over one million new articles in biomedicine are published every year [^13]—making manual screening increasingly unsustainable.

The advent of large language models (LLMs) such as GPT-4, Claude, and Llama has catalyzed a wave of research into automating or semi-automating the screening step. Unlike earlier machine-learning classifiers, which typically required hundreds or thousands of labeled training examples per review, LLMs offer zero-shot or few-shot classification based on natural-language inclusion and exclusion criteria. This review synthesizes the emerging evidence on LLM-based abstract screening, covering methods, empirical performance, comparisons with traditional machine learning, available tools, limitations, and open questions.

---

## 2. Background: From Traditional ML to LLMs

### 2.1 Pre-LLM Automation

Before the LLM era, automation efforts centered on supervised classifiers and active learning. Cohen et al. pioneered SVM-based citation classification for systematic reviews using bag-of-words and TF-IDF features [^5]. Marshall et al. developed RobotSearch (RobotReviewer), a Cochrane-trained machine-learning classifier for identifying randomized controlled trials that became a widely used baseline [^6]. ASReview LAB, first described by van de Schoot et al., uses active learning with classical models (neural networks, SVMs, XGBoost) to prioritize records, reducing workload but still requiring human labeling to train the model [^7].

### 2.2 The LLM Paradigm Shift

LLMs shift the automation paradigm by eliminating the need for review-specific training data. Researchers can prompt a model with the review’s research question, inclusion criteria, and exclusion criteria, and receive a binary or graded relevance decision for each record. This zero-shot capability was first rigorously evaluated for screening by Tran et al., who reported high sensitivity (>90%) for GPT-3.5-Turbo in title/abstract screening and established a foundational benchmark for subsequent studies [^8].

A major scoping review by Harasgama et al. identified 222 studies of AI tools for evidence synthesis and noted that **no study had directly compared active-learning tools such as ASReview against LLM-based screeners in head-to-head randomized or benchmark evaluations** [^9]. This does not mean that no head-to-head comparisons exist at all: as discussed below, several studies have compared traditional *supervised* ML classifiers (RobotSearch, Abstrackr) against LLMs [^31][^32]. The gap identified by Harasgama is specific to *active-learning* systems that iteratively retrain on human labels, a distinction that matters for workflow design.

---

## 3. Methods Taxonomy

### 3.1 Zero-Shot and Few-Shot Prompting

The dominant approach in the literature is **zero-shot prompting**, where the LLM is given the review’s eligibility criteria and asked to classify each title/abstract without examples [^10][^11][^12]. Several studies have demonstrated that performance is highly sensitive to prompt design. A prospective evaluation of **515 unique prompts** across four medical systematic reviews found that average recall/sensitivity ranged from ~70% to ~95% depending on prompt characteristics, while precision remained low (mean 18.5%) across all conditions [^13]. Key findings from that study include:

- **Including the review’s title and inclusion/exclusion criteria** in the prompt significantly improved F1-score (β = +5.46% and +8.05%, respectively).
- **Focusing prompts on methods** rather than topics or results improved F1 (β = +0.78%).
- **Screening titles alone** yielded higher F1 than screening abstracts (β = +3.67%), likely because abstracts introduce noisier information that conflicts with concise criteria matching.
- **Larger models** improved performance: Mistral Large (123B) outperformed Llama3-8b by ~7.8 percentage points in F1 [^13].

A related study on a living systematic review showed that iterative prompt refinement with GPT-4o achieved **100% sensitivity** for studies ultimately included after full-text screening, at the cost of moderate specificity, yielding simulated workload reductions of **65–85%** [^14].

Structured eligibility frameworks such as **PICO** (Population, Intervention, Comparison, Outcome) and **PCC** (Population, Concept, Context) have also been shown to improve accuracy when explicitly embedded in prompts [^15][^16].

### 3.2 Chain-of-Thought and Structured Decomposition

Rather than asking for a single inclusion verdict, some studies decompose the decision into multiple Boolean criteria. Delgado-Chaves et al. evaluated **18 LLMs** across three systematic reviews using a criteria-by-criteria approach and found that GPT-4o-mini and GPT-3.5-turbo achieved the highest Matthews Correlation Coefficients (0.342 and 0.312, respectively), while open-source models such as Llama 3.1 8B and Mixtral 8x22b were competitive [^10]. Notably, the same benchmark found that Llama 3.1 8B outperformed its 70B counterpart on prevalence-adjusted metrics, underscoring that model size is not the sole determinant of screening quality [^10].

Similarly, the "3-layer strategy" study in *JMIR* split screening into three sequential layers (research design, target patients, interventions/controls) and reported that GPT-4 achieved **100% sensitivity** in identifying the small set of records ultimately used for meta-analysis, though with varying specificity across layers [^12].

### 3.3 Fine-Tuning

While most studies use off-the-shelf models, fine-tuning represents a promising but less-explored avenue. Schroeder et al. fine-tuned a **1.2-billion-parameter** open-weight LLM on >8,500 human-labeled titles and abstracts, reporting an **80.8% improvement in weighted F1** over the base model, with 86.4% human–model agreement and a 91.2% true-positive rate [^17]. This suggests that even small, locally deployable models can reach strong performance when fine-tuned on review-specific data, though the approach reintroduces the burden of creating a large training set. The IARG-UF group has released a fine-tuned LFM-2.5 1.2B model for Phase I screening on Hugging Face [^18].

### 3.4 Multi-Model Consensus and Ensembling

Several studies have moved beyond single-model prompting to aggregate outputs from multiple LLMs. A 2025 study on the **CLEF eHealth TAR benchmark** (28 systematic reviews) found that **majority voting** across multiple LLMs achieved the best workload reduction, with WSS@95 up to 0.680 (theoretical 68% workload reduction at 95% recall) [^19].

A confidence-weighted voting framework evaluated on 900 articles from 17 systematic reviews achieved a **macro F1 of 0.796**, exceeding abstract-only classification (0.676) and K-means baselines (0.446) [^20].

An empirical study comparing GPT-4o, Gemini 1.5 Pro, Claude 3.5 Sonnet, and Llama 3.3 70B found that an ensemble approach improved sensitivity but at the cost of increased false positives, illustrating the classic sensitivity–specificity trade-off [^21].

### 3.5 Retrieval-Augmented Generation (RAG) and Agentic Workflows

A smaller number of studies have integrated **Retrieval-Augmented Generation (RAG)** or **multi-agent architectures**. One comparative study evaluated an in-house LLM system using prompt engineering for title/abstract screening and RAG for full-text screening against the commercial tool Rayyan. The LLM system achieved an **article exclusion rate of 99.5%**, **specificity of 99.6%**, and **negative predictive value of 100%** [*sic*, in that study], reducing total screening time by **95.5%** compared with manual screening while maintaining zero false negatives [^22]. *Caveat: this result comes from a single-review case study and should not be treated as generalizable.*

On the open-source tool front, **LUMINA** introduces an agentic framework with four small agents—a fast classifier, a PICOS-structured detailed screener, a reviewer (LLM-as-a-judge), and an improver—that cooperate through a bounded review/improve loop. Across 15 published systematic reviews, LUMINA reported mean sensitivity of 0.96 and specificity of 0.88, with a false-negative rate under 2% [^23].

---

## 4. Empirical Performance

### 4.1 Meta-Analytic Evidence

Given the rapid proliferation of primary studies, several groups have conducted systematic reviews and meta-analyses of LLM screening performance. Their pooled estimates provide the most robust quantitative summary to date.

| Review | Studies / Assessments | Pooled Sensitivity (Title/Abstract) | Pooled Specificity (Title/Abstract) | Key Notes |
|--------|----------------------|-------------------------------------|-------------------------------------|-----------|
| Kim et al., 2025 (JMAI) [^11] | 14 LLM models (meta-analysis) | ~90% (SROC) | ~90% (SROC) | Developed GPT-4o-mini tool; 100% sens, 81% spec, 14% prec |
| Systematic review, 2025 (PubMed) [^24] | 63 studies (148 assessments) | Median PPA 0.92 (IQR 0.69–0.98) | Median NPA 0.89 (IQR 0.72–0.95) | GPT-family dominated (77% of assessments) |
| MedRxiv meta-analysis, 2026 [^25] (preprint) | 18 studies | 0.92 | 0.94 | SROC AUC = 0.98; CoT/examples improved sensitivity |
| Clark et al., 2025 (Cambridge) [^26] | 19 studies (evidence synthesis) | — | — | Incorrect inclusions: 0–29% (median 10%); incorrect exclusions: 1–83% (median 28%) |

*Table 1: Summary of meta-analytic findings on LLM abstract screening.*

These reviews converge on a central finding: **LLMs can achieve high sensitivity for abstract screening**, often in the 90–100% range under optimal prompting, but **specificity and precision are generally modest**, frequently falling below 50% and 30%, respectively [^10][^13][^11][^24][^25].

### 4.2 The Sensitivity–Specificity Trade-Off

The most consistent empirical pattern across the literature is a **pronounced trade-off between sensitivity and specificity**. Because missing a relevant study (false negative) is more damaging to a systematic review than including an irrelevant one (false positive), most researchers optimize for sensitivity. This optimization strategy produces:

- **High sensitivity** (often >90%, and up to 100% in some studies) [^8][^14][^11][^27]
- **Low precision** (commonly <10–30%) [^10][^13][^28]
- **Moderate-to-low specificity** (ranging from ~38% to ~95% depending on the threshold and prompt) [^27][^29]

For example, the large prospective prompt-engineering study found an average precision of only 18.5% across 12,360 runs, meaning the vast majority of papers flagged for inclusion by the LLM were ultimately irrelevant [^13]. Conversely, a study of GPT-3.5 reported pooled specificity as low as 37.7% while maintaining 97.1% sensitivity [^27].

This trade-off is not merely a technical nuisance; it defines the practical utility of LLMs in review workflows. A tool with 100% sensitivity and 20% precision is excellent as a **safety net** (no relevant studies are lost) but poor as a **filter** (reviewers must still examine many false positives).

### 4.3 LLMs vs. Traditional Machine Learning

A 2025 diagnostic accuracy study provides rare head-to-head data comparing modern LLMs against the established traditional-ML baseline RobotSearch. Evaluated on 1,000 citations, **RobotSearch** achieved the lowest false-negative fraction (6.4%) but the highest false-positive fraction (22.2%). In contrast, the LLMs (ChatGPT 4.0, Claude 3.5, Gemini 1.5, DeepSeek-V3) had **very low false-positive fractions (2.8–3.8%)** but higher false-negative fractions (6.4–13.0%) [^30]. This pattern suggests that LLMs are more conservative excluders than traditional ML classifiers—an important distinction for workflow design.

A comparative study of Abstrackr (an established ML-assisted screening tool) and GPT models found that GPT was superior in precision (0.51 vs. 0.21), specificity (0.84 vs. 0.71), and F1 (0.52 vs. 0.31), while Abstrackr performed better for initial screening prioritization [^31].

These comparisons apply to *supervised* traditional ML tools, not to active-learning systems such as ASReview LAB. To date, no published study has compared ASReview-style active learning against LLM-based screeners in a head-to-head benchmark [^9].

### 4.4 Workload Reduction and Efficiency

Despite low precision, LLMs can still deliver substantial **efficiency gains** because they confidently exclude large volumes of clearly irrelevant records. However, the metrics used to measure efficiency vary across studies and should not be treated as interchangeable:

**Reviewer-burden reduction (simulated or prospective):**
- **33–93%** reduction in one reviewer’s workload (PNAS study of 18 LLMs across three reviews) [^10]
- **65%** reduction in avoidable workload (GPT-3.5 study extrapolated to all therapeutic health SRs published in 2022) [^27]
- **65–85%** simulated workload reduction (GPT-4o living systematic review) [^14]
- **34.5–37.5%** reduction in screening demands from top-performing prompt configurations [^13]
- **64%** workload savings in a large scoping review feasibility study (15,307 abstracts) [^15]

**Algorithmic workload metrics:**
- **WSS@95 up to 0.680** (theoretical 68% workload reduction at 95% recall) from multi-LLM majority voting on the CLEF eHealth benchmark [^19]

**Time reduction (single-review case studies):**
- **95.5%** reduction in screening time in a single-review LLM+RAG evaluation [^22] *(single review; not generalizable)*

A compact-LLM study evaluating GPT-4o-mini, Llama 3.1 8B, and Gemma 2 9B found that using a 50- or 75-point inclusion threshold offered an optimal trade-off, with processing costs as low as **$0.14–$1.93 per review** for the API-based model, and zero cost for locally run open models (but ~4 hours processing time) [^28]. GPT-5 screening in orthopedic systematic reviews cost approximately **$0.003 per abstract** [^32].

### 4.5 Model Comparisons

**Proprietary vs. open-source:** GPT-4o and GPT-4o-mini consistently rank among the top performers in head-to-head benchmarks [^10][^21][^28]. However, the performance gap is narrowing. The PNAS benchmark found that Llama 3.1 8B outperformed its 70B counterpart on some metrics, and Mistral models achieved the highest prevalence-adjusted kappa scores [^10]. A validation study of Llama 3 70B vs. ChatGPT-4o-mini reported that Llama 3 achieved higher sensitivity (77.5% vs. 56.2%) but lower specificity (91.4% vs. 95.1%) [^29].

**Size does not guarantee superiority:** Multiple studies have found that larger parameter counts do not always translate to better screening performance, particularly when metrics are adjusted for class imbalance [^10][^13]. This is encouraging for teams seeking to use locally deployed, privacy-preserving models.

**Domain transfer:** Performance varies substantially across medical specialties and review topics. A locally deployed 20B model showed 100% sensitivity in a technology-focused surgical pathology review but only 85.7% in a psychosocial review, suggesting that the **objectivity and specificity of inclusion criteria** strongly influence LLM accuracy [^33]. The software-engineering benchmark SESR-Eval similarly found that accuracy varied more across review topics than across models, leading the authors to conclude that LLMs are not yet ready for unsupervised automation in that domain [^34].

### 4.6 A Cautionary Counterpoint

Not all evaluations are optimistic. A 2026 study in *JMIR Formative Research* evaluated **GPT-5 and ASReviewLab** on 25 Cochrane systematic reviews and found that both tools ranked many included studies low in their output lists. Under worst-case conditions, reviewers would still need to examine **96% of abstracts** before all included studies were found [^35]. The authors concluded that **AI cannot yet safely reduce the total number of abstracts requiring human review** in high-recall review contexts—a direct challenge to optimistic claims that LLMs can safely eliminate 60–95% of the screening burden across all review types.

Similarly, a stage-aware governance study found that while LLMs performed well at title/abstract screening (F1 ~0.83–0.89), their performance **degraded substantially at the full-text eligibility stage** (F1 dropping to 0.58–0.65), suggesting that success at abstract screening does not generalize to later review stages [^36].

---

## 5. Datasets and Benchmarks

Reproducible evaluation requires shared benchmarks. Several datasets and evaluation frameworks have emerged:

- **SESR-Eval** (2025): A dataset of 34,528 labeled primary studies from 24 software-engineering systematic reviews, designed to benchmark LLM title/abstract screening outside the medical domain [^34].
- **TrialReviewBench** (2025): A benchmark of 100 published systematic reviews and 2,220 clinical studies introduced by the TrialMind group, evaluating search, screening, and extraction [^37].
- **CLEF eHealth TAR Benchmark**: Technology-Assisted Review shared tasks (2017–2019) providing 28 systematic-review datasets widely used for evaluating screening algorithms, including recent multi-agent LLM studies [^19].
- **Kim et al. benchmark** (JMAI, 2025): A meta-analysis and tool-development study that tested a GPT-4o-mini screening tool against existing systematic reviews [^11].
- **Living systematic review test set** (PubMed, 2025): A longitudinal evaluation using repeated updates of a single review to assess prompt stability over time [^14].
- **MA-LLM pipeline** (Research Synthesis Methods, 2026): An open-source Python pipeline with 515 prompts and four gold-standard medical reviews, enabling reproducible prompt-comparison studies [^13].

Most studies to date, however, use **prospective or retrospective validation against a single "gold standard" review** (i.e., human decisions from a published review). This creates a risk of circularity if the gold-standard review is within the LLM’s training data. The MA-LLM pipeline study addressed this by selecting only reviews published after the LLMs’ training cut-offs [^13], a practice that should become standard.

---

## 6. Tools and Implementations

A growing ecosystem of open-source and commercial tools integrates LLMs into systematic review workflows. Table 2 summarizes representative tools.

| Tool | Type | Key Features | LLM Support | URL |
|------|------|--------------|-------------|-----|
| **ASReview LAB** | Open-source desktop / CLI / web | Active learning with ELAS models; ASReview Dory extension adds dense embeddings and neural classifiers; simulation toolkit | Custom (classical ML + neural); LLM extensions emerging | https://github.com/asreview/asreview |
| **MetaScreener** | Open-source multi-LLM ensemble | Web UI, CLI, and API; multi-model consensus; PDF screening | GPT-4o, Claude, Llama, Mistral, DeepSeek, Qwen | https://github.com/ChaokunHong/MetaScreener |
| **LUMINA** | Open-source agentic framework | 4-agent pipeline (Classifier, Screener, Reviewer, Improver); full audit trail | OpenAI API compatible | https://github.com/zanwenfu/agentic-reviewers-for-SRMA |
| **LLMSurver** | Browser-based web app | Privacy-first; multi-LLM consensus voting; runs entirely client-side | Any OpenAI-compatible endpoint | https://llmsurver.dbvis.de |
| **AISysRev** | Open-source MVP | Dockerized web app for LLM title/abstract screening | Configurable via API | https://github.com/EvoTestOps/AISysRev |
| **CAN-SR** | Open-source platform | Government of Canada platform; L1 (abstract) and L2 (full-text) screening; data extraction | Azure OpenAI (GPT-4o, GPT-3.5-turbo) | https://github.com/PHACDataHub/CAN-SR |
| **Arakis** | Open-source platform | End-to-end pipeline: search, screen, extract, analyze, draft; PRISMA 2020 tracking | GPT-4 via API | https://github.com/mustafa-boorenie/arakis |
| **ReviewAid** | Open-source Streamlit app | Full-text screening and data extraction; batch PDF upload; Ollama support | GPT-4o, DeepSeek, Cohere, Claude, GLM, Ollama | https://github.com/aurumz-rgb/ReviewAid |
| **SLR** | Open-source desktop + web | 9 AI providers; deduplication; 2-stage screening; extraction tables | OpenAI, Anthropic, Google, DeepSeek, Mistral, Kimi, Grok, Ollama, custom | https://github.com/sadeghanisi/SLR |
| **MechaScreener** | Open-source tool | Zero-shot LLM screening; assigns 1–5 inclusion probability scores; validated on 10 Cochrane reviews | Configurable LLM backend | https://www.medrxiv.org/content/10.64898/2026.04.28.26352009v1 |
| **ReviewCopilot** | Open-source Python screener | Title/abstract and full-text screening; validated on 6,000+ articles across 4 SRs | OpenAI API | https://github.com/jamesjiadazhan/ReviewCopilot |
| **LocalLLM screening tools** | Scripts / CLI | Ollama-based local inference for privacy-sensitive settings | Any Ollama model (e.g., Llama 3, GPT-OSS:20B) | https://github.com/PauloHenriqueMelo/Systematic_Review_Screening_LLM |

*Table 2: Representative tools for LLM-assisted systematic review screening.*

---

## 7. Limitations, Risks, and the Case for Human Oversight

### 7.1 Hallucinations and Criteria Drift

LLMs can hallucinate study characteristics or misinterpret inclusion criteria, particularly when criteria are subjective or nuanced [^10][^26]. The PNAS study noted that some models failed to adhere to strict output formatting instructions, causing parsing errors and missing records [^10]. A systematic review of generative AI in evidence synthesis concluded that the current evidence **does not support fully autonomous screening without human oversight** [^26].

### 7.2 Training Data Contamination

A critical but frequently overlooked issue is **data leakage**: if a published systematic review was in an LLM’s training corpus, the model may appear to perform well by recall rather than by reasoning. Few studies control for this explicitly. The MA-LLM pipeline study selected reviews published after the LLMs’ knowledge cut-offs, representing a best practice [^13].

### 7.3 Tail Risk: The JMIR Formative Finding

The most significant cautionary evidence comes from the *JMIR Formative* study of GPT-5 and ASReviewLab on 25 Cochrane systematic reviews. Both systems left some included studies ranked very low, meaning that a workflow relying on early stopping or top-k screening could miss relevant studies entirely [^35]. This finding directly challenges claims that LLMs can safely eliminate 60–95% of the screening burden across all review types. Workload reduction estimates appear to be **highly review-dependent**, with broad reviews and rare conditions posing greater tail risk than narrow, well-defined topics.

### 7.4 Stage Degradation

A stage-aware governance study found that LLM performance degrades significantly when moving from title/abstract screening to full-text eligibility assessment (F1 dropping from ~0.89 to ~0.58–0.65) [^36]. This suggests that abstract-screening success should not be assumed to generalize to later review stages, and that different oversight regimes may be needed for each stage.

### 7.5 Reporting Standards and Reproducibility

The PRISMA 2020 statement does not yet include explicit guidance on reporting AI-assisted screening. Researchers using LLMs must still document their search strategy, eligibility criteria, and screening process transparently. Several tool developers have begun integrating automatic PRISMA flow-diagram generation (e.g., Arakis, CAN-SR), but community standards for reporting LLM involvement remain underdeveloped [^23][^38].

### 7.6 Bias and Generalization

Performance is not uniform across domains. As noted above, LLMs struggle more with subjective or poorly defined criteria (e.g., psychosocial constructs) than with objective biomedical ones (e.g., randomized controlled trials of a specific drug) [^33]. The SESR-Eval benchmark found that inter-review variance exceeded inter-model variance, underscoring that **the review itself is a major source of performance heterogeneity** [^34].

### 7.7 Cost and Environmental Considerations

While API costs for compact models are low (often <$2 per review), large-scale screening with state-of-the-art proprietary models can become expensive. Moreover, local deployment of open models—while privacy-preserving and cost-free—requires GPU resources and technical expertise [^28][^33].

---

## 8. Future Directions

1. **Direct active-learning-vs-LLM benchmarks:** The Harasgama scoping review explicitly identified the absence of head-to-head comparisons between traditional active-learning tools (ASReview) and LLM-based screeners as a critical evidence gap [^9]. Closing this gap should be a top priority for the research community.

2. **Standardized benchmarks with temporal holdouts:** The field needs domain-agnostic benchmarks with temporally held-out test sets to prevent data leakage and enable fair model comparison. TrialReviewBench and SESR-Eval are promising starts.

3. **Human–AI hybrid workflows:** The emerging consensus is that LLMs are best deployed as **second reviewers or pre-screeners**, not replacements. Workflows where the LLM performs an initial pass and humans focus on discordant cases offer the strongest safety–efficiency balance [^10][^14][^27]. However, the JMIR Formative study suggests that even this framing may be optimistic for certain review types unless tail-risk is explicitly quantified [^35].

4. **Active learning + LLMs:** Combining LLM pseudo-labeling with active-learning prioritization (as explored in ASReview and weakly supervised learning frameworks) could reduce both false-negative risk and human workload [^39].

5. **Fine-tuning and domain adaptation:** As more labeled screening datasets accumulate, fine-tuning smaller open models may offer a reproducible, privacy-preserving alternative to API-dependent prompting [^17][^18].

6. **Agentic and multi-model systems:** LUMINA, LLMSurver, and confidence-weighted voting frameworks demonstrate that decomposition and consensus can improve reliability. Future work should evaluate whether these architectures generalize across review types and whether the added latency and cost are justified by gains in accuracy [^19][^20][^23].

7. **Clarifying reporting guidelines:** Organizations such as the Cochrane Collaboration and the PRISMA group should issue guidance on disclosing LLM use, prompt versioning, and criteria formulation to ensure transparency.

---

## 9. Conclusion

The evidence to date indicates that LLMs are **highly sensitive but poorly precise** tools for abstract screening in systematic reviews. Under well-designed prompts, modern models can identify 90–100% of relevant records while reducing human reviewer burden by roughly 30–85% in favorable cases. However, the same models typically flag large numbers of irrelevant records, and recent cautionary evidence from Cochrane reviews suggests that tail-risk (low-ranked included studies) may be higher than initially reported for broad reviews. Reviewers cannot simply accept LLM inclusion decisions without manual verification, and abstract-screening success does not reliably generalize to full-text eligibility assessment.

The most robust and reproducible strategy is a **hybrid workflow**: LLMs conduct an initial screening pass optimized for sensitivity, and human reviewers validate the retained records and adjudicate discordant cases. Prompt engineering, inclusion-criteria refinement, and model selection all materially affect performance, making standardized benchmarking and transparent reporting essential next steps.

**Bottom line:** LLMs have moved from experimental curiosity to practical assistant in the systematic review pipeline, but they remain assistants—not replacements—for human judgment.

---

## Sources

[^1]: Borah R, Brown AW, Capers PL, Kaiser K. Analysis of the time and workers needed to conduct systematic reviews of medical interventions using data from the PROSPERO registry. *BMJ Open*. 2017;7(2):e012545. https://bmjopen.bmj.com/content/7/2/e012545

[^5]: Cohen AM, Hersh WR, Peterson K, et al. Reducing workload in systematic review preparation using automated citation classification. *J Am Med Inform Assoc*. 2006;13:206-219. https://doi.org/10.1197/jamia.M1929

[^6]: Marshall IJ, Noel-Storr A, Kuiper J, Thomas J, Wallace BC. Machine learning for identifying randomized controlled trials: an evaluation and practitioner's guide. *Res Synth Methods*. 2018;9(4):602-614. https://doi.org/10.1002/jrsm.1319

[^7]: van de Schoot R, de Bruin J, Schram R, et al. An open source machine learning framework for efficient and transparent systematic reviews. *Nat Mach Intell*. 2021;3:125-133. https://doi.org/10.1038/s42256-020-00287-7

[^8]: Tran B, Gartlehner G, Yaacoub S, et al. Sensitivity and specificity of using GPT-3.5 turbo models for title and abstract screening in systematic reviews and meta-analyses. *Ann Intern Med*. 2024;177(6):791-799. https://doi.org/10.7326/M23-3389

[^9]: Harasgama S, Pearce H, Appel C, et al. Artificial Intelligence Tools for Automating Evidence Synthesis: Scoping Review. *J Med Internet Res*. 2026;28:e81597. https://doi.org/10.2196/81597

[^10]: Delgado-Chaves FM, Jennings H, Atalaia A. Transforming literature screening: The emerging role of large language models in systematic reviews. *PNAS*. 2025;122(2):e241196212. https://pmc.ncbi.nlm.nih.gov/articles/PMC11745399/

[^11]: Kim JK, Rickard M, Dangle P, et al. Evaluating large language models for title/abstract screening: a systematic review and meta-analysis & development of new tool. *J Med Artif Intell*. 2025;8. https://jmai.amegroups.org/article/view/10102

[^12]: Strachan J. Human-Comparable Sensitivity of Large Language Models in Identifying Eligible Studies Through Title and Abstract Screening: 3-Layer Strategy Using GPT-3.5 and GPT-4 for Systematic Reviews. *J Med Internet Res*. 2024;26:e52758. https://pmc.ncbi.nlm.nih.gov/articles/PMC11364944/

[^13]: Adam TJ, Abosabie SAS, Abosabie SA, et al. Prompt engineering of large language models for paper screening in medical meta-analyses and systematic reviews: A prospective comparative study. *Research Synthesis Methods*. 2026. https://www.cambridge.org/core/journals/research-synthesis-methods/article/prompt-engineering-of-large-language-models-for-paper-screening-in-medical-metaanalyses-and-systematic-reviews-a-prospective-comparative-study/A8EB5B6A3E472CBA91BE8BA7D9DAB623

[^14]: Prompts for a large language model to screen titles and abstracts in a living systematic review. *BMJ Ment Health*. 2025. https://doi.org/10.1136/bmjment-2025-301762

[^15]: Capability of chatbots powered by large language models to support the screening process of scoping reviews: a feasibility study. *BMC Med Res Methodol*. 2025. https://pubmed.ncbi.nlm.nih.gov/41522831/

[^16]: Harnessing ChatGPT for abstract screening in health-related scoping reviews: the role of structured eligibility criteria. *BMC Health Serv Res*. 2025. https://link.springer.com/article/10.1186/s12913-025-13901-4

[^17]: Schroeder N, et al. Fine-Tuning A Large Language Model for Systematic Review Screening. *arXiv preprint*. 2025. https://arxiv.org/abs/2603.24767

[^18]: Intelligent-Agents-Research-Group/llm_systematic_review. GitHub repository. https://github.com/Intelligent-Agents-Research-Group/llm_systematic_review

[^19]: LLM-based Multi-Agent Collaboration for Abstract Screening towards Automated Systematic Reviews. *medRxiv preprint*. 2025. https://www.medrxiv.org/content/10.1101/2025.08.11.25333429v4

[^20]: Large language model-based paper classification framework with key-insight extraction and confidence-weighted voting. *Research Synthesis Methods*. 2025. https://www.cambridge.org/core/journals/research-synthesis-methods/article/large-language-modelbased-paper-classification-framework-with-keyinsight-extraction-and-confidenceweighted-voting/BF9B4D6D81FC834F2D654E4F26FEB37B

[^21]: Oami T, et al. Optimal large language models to screen citations for systematic reviews. *Research Synthesis Methods*. 2025. https://www.cambridge.org/core/journals/research-synthesis-methods/article/optimal-large-language-models-to-screen-citations-for-systematic-reviews/05DB6A4BA0DA60B51869E287068F068A

[^22]: Streamlining systematic reviews with large language models using prompt engineering and retrieval augmented generation. *BMC Med Res Methodol*. 2025;25:130. https://link.springer.com/article/10.1186/s12874-025-02583-5

[^23]: zanwenfu/agentic-reviewers-for-SRMA. GitHub repository. https://github.com/zanwenfu/agentic-reviewers-for-SRMA

[^24]: Large language models show promising performance for some systematic review tasks but call for cautious implementation: a systematic review. *PubMed*. 2025. https://pubmed.ncbi.nlm.nih.gov/41831731/

[^25]: Performance of Large Language Models in Automated Medical Literature Screening: A Systematic Review and Meta-analysis. *medRxiv preprint*. 2026. https://www.medrxiv.org/content/10.64898/2026.03.17.26348656v1

[^26]: Clark J, Barton B, Albarqouni L, et al. Generative artificial intelligence use in evidence synthesis: A systematic review. *Research Synthesis Methods*. 2025. https://www.cambridge.org/core/services/aop-cambridge-core/content/view/2DACF6D129AA6E46CB8A8740A03D0675/S175928792500016Xa.pdf/generative-artificial-intelligence-use-in-evidence-synthesis-a-systematic-review.pdf

[^27]: Sensitivity, specificity and avoidable workload of using a large language model for title and abstract screening in systematic reviews and meta-analyses. *medRxiv preprint*. 2023. https://www.medrxiv.org/content/10.1101/2023.12.15.23300018v1

[^28]: Compact large language models for title and abstract screening in systematic reviews: An assessment of feasibility, accuracy, and workload reduction. *Research Synthesis Methods*. 2025. https://www.cambridge.org/core/journals/research-synthesis-methods/article/compact-large-language-models-for-title-and-abstract-screening-in-systematic-reviews-an-assessment-of-feasibility-accuracy-and-workload-reduction/CB00FD70434780029EF6C027055331BA

[^29]: Validation of large language models (Llama 3 and ChatGPT-4o mini) for title and abstract screening in biomedical systematic reviews. *Research Synthesis Methods*. 2025. https://www.cambridge.org/core/journals/research-synthesis-methods/article/validation-of-large-language-models-llama-3-and-chatgpt4o-mini-for-title-and-abstract-screening-in-biomedical-systematic-reviews/EDE7C95374C7FF6200B7280D5742D906

[^30]: Artificial intelligence for the science of evidence synthesis: how good are AI-powered tools for automatic literature screening? *BMC Med Res Methodol*. 2025. https://link.springer.com/article/10.1186/s12874-025-02644-9

[^31]: A comparative study of screening performance between abstrackr and GPT models: Systematic review and contextual analysis. *BMC Med Inform Decis Mak*. 2025. https://link.springer.com/article/10.1186/s12911-025-03138-w

[^32]: Evaluating the Efficacy and Efficiency of GPT-5 for Automated Title and Abstract Screening in Orthopedic Surgery Systematic Reviews. *PubMed*. 2025. https://pubmed.ncbi.nlm.nih.gov/41326830/

[^33]: Evaluating a Locally Deployed 20-Billion Parameter Large Language Model for Automated Abstract Screening in Systematic Reviews. *medRxiv preprint*. 2026. https://www.medrxiv.org/content/10.64898/2026.03.04.26347506v1

[^34]: SESR-Eval: Dataset for Evaluating LLMs in the Title-Abstract Screening of Systematic Reviews. *arXiv preprint*. 2025. https://arxiv.org/abs/2507.19027

[^35]: Sung H, Altahsh D, Garrison S. AI-Assisted Systematic Review: Humans Still Need to Review All Abstracts for Inclusion. *JMIR Formative Res*. 2026. https://formative.jmir.org/2026/1/e82896

[^36]: Kim J, Shin H. Stage-Aware Governance of Large Language Models: Managing Uncertainty and Human Oversight in AI-Assisted Literature Review Systems. *Systems*. 2026. https://www.mdpi.com/2079-8954/14/2/153

[^37]: Accelerating clinical evidence synthesis with large language models. *npj Digit Med*. 2025. https://www.nature.com/articles/s41746-025-01840-7

[^38]: mustafa-boorenie/arakis. GitHub repository. https://github.com/mustafa-boorenie/arakis

[^39]: Weakly supervised active learning for abstract screening leveraging LLM-based pseudo-labeling. *medRxiv preprint*. 2025. https://eprints.whiterose.ac.uk/id/eprint/231720/1/2025.08.24.25334314v1.full.pdf
