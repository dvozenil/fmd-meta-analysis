# Neurosynth Compose Integration: Post-Publication Hosting Plan

Last updated: 2026-07-03

## Summary

After the meta-analysis is published, we should export the curated
StudySet (studies + coordinates + annotations) to **Neurosynth Compose**
(NS-Compose) for public hosting, reproducibility, and community reuse.

This is a **low-effort addition** because we are already using NiMARE,
which speaks the same data formats (NiMADS) that NS-Compose and
NeuroStore use natively. The export is essentially one function call.

**Status:** Consideration / strong suggestion. Not yet committed.
**Decision needed:** Whether to structure extraction data with NiMADS
annotation fields from the start (recommended), or convert post hoc.

---

## Why this is worth doing

| Benefit | What it gives us |
|---|---|
| **Reproducibility** | A self-contained NiMADS bundle (JSON) that anyone can download and re-execute with NiMARE to get identical results |
| **Citable artifact** | The meta-analysis gets a unique ID on the platform, referenceable in the paper |
| **Community discovery** | Other researchers searching for FND-related terms on NeuroStore find our curated coordinates (with attribution) |
| **Provenance** | Every study, coordinate, and inclusion annotation is visible and traceable — reviewers can inspect why a study was included |
| **Future updates** | Positions the work for "living" updates without committing to a formal Living Systematic Review |
| **Functional decoding** | NS-Compose / NiMARE can run functional decoding against Neurosynth/NeuroQuery databases to characterize ALE clusters |

## Why it's low effort

We already use NiMARE for the ALE analysis. NiMARE has native NiMADS
support built in:

```python
from nimare.nimads import Studyset

# If using the legacy Dataset class:
studyset = Studyset.from_dataset(your_nimare_dataset)
studyset.to_nimads("fnd_studyset.json")

# If using the modern Studyset class (preferred):
studyset.to_nimads("fnd_studyset.json")  # already in the right format
```

The JSON file is directly uploadable to NeuroStore/NS-Compose via web UI
or the `neurostore-sdk` Python API.

---

## What gets uploaded

Three components, the first two are required, the third is optional:

### 1. StudySet (required)

A NiMADS JSON containing:

- **Studies** — each included paper with: DOI, PMID, title, authors,
  year, journal
- **Analyses** — each contrast/condition within a study, with:
  - Name and description of the contrast
  - Weights and conditions (e.g., "Task > Baseline", "Patients > Controls")
  - Points (activation coordinates: X, Y, Z, space, statistic type)
- **Metadata** — sample sizes, imaging modality, scanner field strength,
  coordinate space (MNI/Talairach)

### 2. Annotation (required)

A separate NiMADS annotation JSON that defines:

- **Which analyses are included** in the meta-analysis (inclusion labels)
- **Group assignments** (e.g., functional track, structural track,
  FND subtype: motor, PNES, sensory, mixed)
- **Contrast types** (e.g., "activation" vs "deactivation",
  "patient > control" vs "control > patient")

This is what makes the meta-analysis reproducible — someone downloading
the bundle sees not just coordinates but exactly which contrasts were
selected and how they were grouped.

### 3. Meta-Analysis Specification (optional)

The NiMARE workflow definition:

- Algorithm: ALE (Eickhoff et al., 2009)
- Kernel FWHM parameter
- Cluster-forming threshold
- Multiple comparison correction: FDR or FWE
- Which annotation column defines the included analyses

This can be specified through the NS-Compose web interface or packaged
as a NiMARE "Reproducible Bundle" for local/cloud execution.

---

## NiMADS Schema Reference

NiMADS (NeuroImaging Meta-Analysis Data Standard) is the shared data
format across NeuroStore, NS-Compose, and NiMARE. Key objects:

```
StudySet
├── name, description, publication, doi, pmid
└── studies[]
    ├── doi, name, authors, year, publication, pmid
    ├── metadata: { sample_size, modality, ... }
    └── analyses[]
        ├── name: "Patients > Controls (motor task)"
        ├── description: contrast description
        ├── weights: [1, -1]  (must match conditions length)
        ├── conditions[]
        │   └── name: "FND patients", description: "..."
        ├── points[]  (activation coordinates)
        │   ├── coordinates: [x, y, z]
        │   ├── space: "MNI" or "TAL"
        │   ├── kind: "peak" (or "center of mass")
        │   └── values[]: { kind: "z-statistic", value: 3.45 }
        └── images[]  (optional — for image-based meta-analysis)

Annotation
├── name: "fnd_inclusion_annotations"
├── description: "Inclusion labels for FND meta-analysis"
├── note_keys: { "include": "integer", "track": "string", "subtype": "string" }
└── notes[]: { analysis_id: "...", include: 1, track: "functional", subtype: "motor" }
```

Full schema: https://neurostuff.github.io/NIMADS/

---

## Recommended: Structure extraction for NiMADS from the start

The annotation structure maps directly onto columns you'll likely
already have in your extraction spreadsheet. Planning the mapping now
avoids a painful conversion later.

### Suggested extraction columns → NiMADS annotation fields

| Extraction column | NiMADS field | Example values |
|---|---|---|
| `study_id` | Study DOI/name | 10.1038/nn.1234 |
| `contrast_name` | Analysis name | "FND > HC (motor task)" |
| `contrast_description` | Analysis description | "Patients vs healthy controls during motor execution" |
| `x`, `y`, `z` | Point coordinates | -42, -58, -15 |
| `space` | Point space | MNI, TAL |
| `stat_type` | Point value kind | z-statistic, t-statistic |
| `stat_value` | Point value value | 3.45 |
| `sample_size` | Study metadata | 23 |
| `modality` | Study metadata | fMRI, PET, VBM |
| `include` | Annotation note | 1 (include), 0 (exclude) |
| `track` | Annotation note | functional, structural_gm |
| `fnd_subtype` | Annotation note | motor, PNES, sensory, mixed |
| `contrast_direction` | Annotation note | activation, deactivation |
| `comparison_type` | Annotation note | patient_vs_control, control_vs_patient |

If your extraction spreadsheet uses these column names (or a close
variant), the conversion to NiMADS annotation JSON is straightforward.

---

## Upload process (post-publication)

### Option A: Web UI (simplest)

1. Go to https://compose.neurosynth.org/
2. Create a new Project
3. Import the NiMADS StudySet JSON (or manually import studies from
   NeuroStore if already indexed)
4. Upload the annotation JSON
5. Specify the meta-analysis parameters through the web interface
6. Optionally execute via Google Colab (or skip — analysis already run
   locally with NiMARE)
7. Set the StudySet and Meta-Analysis to public

### Option B: NeuroStore API (scriptable)

```python
# Using neurostore-sdk (pip install neurostore-sdk)
# or direct REST API calls to https://neurostore.org/api/

import json
import requests

# Upload studyset
with open("fnd_studyset.json") as f:
    studyset_data = json.load(f)

response = requests.post(
    "https://neurostore.org/api/studysets/",
    json=studyset_data,
    headers={"Content-Type": "application/json"}
)
studyset_id = response.json()["id"]

# Upload annotation
with open("fnd_annotation.json") as f:
    annotation_data = json.load(f)

response = requests.post(
    "https://neurostore.org/api/annotations/",
    json={**annotation_data, "studyset": studyset_id},
    headers={"Content-Type": "application/json"}
)
```

### Option C: NiMARE direct export (most integrated)

```python
from nimare.nimads import Studyset

# Build studyset from your analysis data
studyset = Studyset.from_nimads("fnd_studyset.json")

# Can also fetch existing NeuroStore studysets
# existing = nimare.io.fetch_neurostore_studyset("STUDYSET_ID")

# Run ALE directly on the Studyset (NiMARE supports this natively)
from nimare.meta.cbma import ALE
results = ALE(null_method="approximate").fit(studyset)

# Export for upload
studyset.to_nimads("fnd_studyset_final.json")
```

---

## What we do NOT commit to

- **Not a Living Systematic Review.** We register on PROSPERO as a
  classic review. FND neuroimaging doesn't move fast enough (5–10
  studies/year) to justify the ongoing maintenance burden of LSR
  (minimum quarterly re-searches, scheduled published updates).
- **Not using NS-Compose for the primary analysis.** We run NiMARE
  locally for full control over parameters, subgroup analyses, and
  custom contrasts. NS-Compose is used only for post-publication
  hosting and reproducibility.
- **Not replacing our search pipeline.** Our 5-database search
  (PubMed, Europe PMC, WoS, Scopus, PsycINFO) with LLM screening is
  more comprehensive than NS-Compose's NeuroStore + PubMed search for
  this niche population.

---

## Timeline

| Phase | Action | Effort |
|---|---|---|
| **Now (extraction planning)** | Add NiMADS-compatible columns to extraction spreadsheet | ~1 hour |
| **During analysis** | Track which contrasts are included, with annotation labels | Minimal overhead |
| **After publication** | Export StudySet + Annotation to NiMADS JSON, upload to NS-Compose | ~2–4 hours |
| **Optional** | Run functional decoding via NiMARE/NeuroQuery on ALE clusters | ~1 hour |

---

## References

- Kent et al. (2026). Neurosynth Compose: A web-based platform for
  flexible and reproducible neuroimaging meta-analysis. *Imaging
  Neuroscience*, 4, IMAG.a.1114. DOI: 10.1162/imag.a.1114
- NiMADS schema: https://neurostuff.github.io/NIMADS/
- NS-Compose docs: https://neurostuff.github.io/compose-docs/
- NiMARE docs: https://nimare.readthedocs.io/
- NeuroStore API: https://neurostore.org/api/
- NeuroStore Python SDK: https://github.com/neurostuff/neurostore-python-sdk
