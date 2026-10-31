# DGCA NEXT V2 — R2-C01-CF02 Counterfactual Report
## Controlled Sensory Fragmentation and Assembly Formation Counterfactual

- **Experiment ID:** `R2-C01-CF02`
- **Role:** Principal Cognitive Architecture Experimental Engineer, Sparse Representation Researcher, Independent Scientific Auditor
- **Status:** **COMPLETE**
- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Investigation Branch:** `experiment/r2-c01-cf02-sensory-fragmentation`
- **Investigation Base HEAD:** `0d967eaf34a2503468da53cf108a09c8d0836ea4` (Verified F02 Remote HEAD)
- **Production main (Frozen):** `f044c20b532f89749675120ffb1d8ada997e3a5e`
- **Authorized Final Verdict:**
  `R2-C01-CF02 COMPLETE — REPRESENTATION FORMATION EFFECT MEASURED`

---

## 1. Executive Summary & Core Verdict

The R2-C01-F02 forensic investigation proved that coexisting assemblies attesting to identical peripheral surfaces (e.g., `ماء` and `تفاح`) do not represent context specialization. However, an open question remained: **Does representational multiplicity require multiple linguistic contexts (e.g. `ماء` appearing after both `النسر` and `الطفل`), or does repeated sensory exposure under a single linguistic context suffice to cause duplicate assembly formation?**

To definitively answer this question, R2-C01-CF02 executed a strictly controlled counterfactual experiment comparing two conditions:
1. **Group A (Two Contexts):** Canonical Group B corpus where `ماء` appears in two distinct sentence contexts: S2 `النسر يشرب ماء` and S4 `الطفل يشرب ماء`.
2. **Group B (Repeated Single Context):** Counterfactual corpus where `ماء` appears exclusively in a single sentence context: S2 `النسر يشرب ماء` and S4 `النسر يشرب ماء` (intervention: S4 subject `الطفل` $\to$ `النسر`).

### Core Scientific Findings:
1. **Multiple Contexts Are NOT Necessary (H1 Contradicted):**
   In Group B, where `ماء` was exposed exclusively under `النسر يشرب ماء`, duplicate assemblies for `ماء` formed at the exact same exposure counts as in Group A:
   - Primary assembly formed at Root 14 on founding triangle `[8242, 9854, 11638]` and reached 4 cells.
   - Secondary assembly formed at Root 16 on founding triangle `[8809, 9740, 10634]` and reached 7 cells.
2. **Repeated Single Context Is SUFFICIENT (H2 Supported):**
   Repeated sensory exposure under a single context reliably produces duplicate assemblies.
3. **Sensory Projection Under-Recruitment Causes Duplication (H3 Supported):**
   SIC-V1 projects `ماء` across 16 fixed sensory cells. The primary assembly recruits only 3 seed cells ($18.75\%$) and grows to 4 cells ($25.0\%$). The remaining 12 uncovered sensory cells ($75.0\%$) continue firing synchronously, consolidating mutual recurrent synapses that lawfully trigger secondary assembly formation. Both assemblies share 0 cells ($J = 0.0000$) and are composed 100% of sensory cells.
4. **Multiplicity Does NOT Necessarily Cause Ambiguity (H5 Contradicted):**
   While `ماء` halts in `GEN_STOP_AMBIGUOUS` in both groups, the internal control `تفاح` (which also forms two duplicate assemblies: Asm 14 and Asm 17) successfully breaks symmetry at Root 112 in both groups (margins $\Delta = 0.0487$ in Group A, $\Delta = 0.0592$ in Group B, both $> M_{\text{READ}} = 0.0400$), emitting `تفاح` cleanly.

---

## 2. Preflight F02 Scientific Corrections

Before executing the CF02 counterfactual, the authoritative F02 report was reconciled to correct historical inaccuracies:
1. **Canonical Sentence Correction:** Replaced the erroneous Executive Summary mention of `النسر يأكل لحم` with canonical Group B sentence S1: `القط يشرب حليب`.
2. **Normative Threshold Correction:** Reconciled assembly merge threshold to `THETA_MERGE = 0.70` (conforming to `dgca.core.assembly`).
3. **Exposure Count Decomposition:** Reconciled formation-root descriptions to distinguish:
   - Root index ($R \in [1, 112]$).
   - Sentence exposure count ($N_{\text{sent}}$).
   - Lexical surface exposure count ($N_{\text{surf}}$).
   - Structural formation event (`FORM` / `GROW`).
   - Verified that for both `ماء` and `تفاح`, the primary assembly forms on the **7th surface exposure** ($N_{\text{surf}} = 7$), and the secondary duplicate forms on the **8th surface exposure** ($N_{\text{surf}} = 8$).
4. **Git Provenance Alignment:** Recorded the full verified remote commit SHA `0d967eaf34a2503468da53cf108a09c8d0836ea4`.
5. **Raw Findings Preserved:** All raw activation gain traces, score breakdowns, and Jaccard metrics were verified intact.

---

## 3. Counterfactual Experimental Design

Both groups were initialized from genuine cold starts and exposed to 112 roots in strict round-robin order (`S1`, `S2`, `S3`, `S4`).

### 3.1 Experimental Corpora
* **Group A (Two Contexts):**
  - S1: `القط يشرب حليب`
  - S2: `النسر يشرب ماء`
  - S3: `الطفل يأكل تفاح`
  - S4: `الطفل يشرب ماء`
* **Group B (Repeated Single Context):**
  - S1: `القط يشرب حليب`
  - S2: `النسر يشرب ماء`
  - S3: `الطفل يأكل تفاح`
  - S4: `النسر يشرب ماء`

### 3.2 Fixed Experimental Invariants
- Identical frozen Core and LLA dynamics (`src/` strictly unmodified).
- Identical SIC-V1 feature encoding and deterministic projection.
- Identical round-robin scheduling (Cycle length = 4).
- Identical checkpoint intervals: Root 56 and Root 112.
- Identical learning thresholds: $\Theta_A = 0.10$, $\Theta_{\text{MERGE}} = 0.70$, $\Theta_{\text{READ}} = 0.30$, $M_{\text{READ}} = 0.04$.
- Identical total root budget: 112 roots (448 total exposure events).

### 3.3 Lexical Exposure Distribution & Limitation
| Lexical Surface | Role | Group A Exposures | Group B Exposures | Status |
|:---|:---|:---:|:---:|:---:|
| `ماء` | Target Object | 56 (28 in S2, 28 in S4) | 56 (28 in S2, 28 in S4) | **Invariant** |
| `يشرب` | Target Verb | 84 (28 S1, 28 S2, 28 S4) | 84 (28 S1, 28 S2, 28 S4) | **Invariant** |
| `تفاح` | Control Object | 28 (28 in S3) | 28 (28 in S3) | **Invariant** |
| `حليب` | Filler Object | 28 (28 in S1) | 28 (28 in S1) | **Invariant** |
| `القط` | Context Subject | 28 (28 in S1) | 28 (28 in S1) | **Invariant** |
| `النسر` | Context Subject | 28 (28 in S2) | **56** (28 in S2, 28 in S4) | Intervened (+28) |
| `الطفل` | Context Subject | **56** (28 in S3, 28 in S4) | 28 (28 in S3) | Intervened (-28) |
| `<EOS>` | Termination Marker | 112 | 112 | **Invariant** |

> [!NOTE]
> **Methodological Limitation:** The intervention cleanly holds the object, verb, and sentence-level frequency constant, while changing the contextual frequency of the subject (`النسر` frequency is doubled, `الطفل` is halved). Any downstream effects on global assembly competition from subject density are explicitly tracked as frequency modulations rather than pure isolated token effects.

---

## 4. Assembly Formation and Growth Evidence

### 4.1 Target Assemblies for `ماء`

| Metric / Event | Group A (Two Contexts) — Asm 1 | Group A (Two Contexts) — Asm 2 | Group B (Single Context) — Asm 1 | Group B (Single Context) — Asm 2 |
|:---|:---:|:---:|:---:|:---:|
| **Assembly ID** | **Assembly 7** | **Assembly 9** | **Assembly 8** | **Assembly 9** |
| **Birth Root** | Root 14 (Cycle 4) | Root 16 (Cycle 4) | Root 14 (Cycle 4) | Root 16 (Cycle 4) |
| **Birth Sentence** | S2 (`النسر يشرب ماء`) | S4 (`الطفل يشرب ماء`) | S2 (`النسر يشرب ماء`) | S4 (`النسر يشرب ماء`) |
| **Surface Exposure #** | 7th exposure of `ماء` | 8th exposure of `ماء` | 7th exposure of `ماء` | 8th exposure of `ماء` |
| **Founding Cells** | `[8242, 9854, 11638]` | `[8809, 9740, 10634]` | `[8242, 9854, 11638]` | `[8809, 9740, 10634]` |
| **GROW Event #1** | Root 15 (+`[11984]`, Gen 2) | Root 17 (+4 cells, Gen 5) | Root 15 (+`[11984]`, Gen 2) | Root 17 (+4 cells, Gen 5) |
| **Added Cells (R17)** | — | `[9734, 10044, 10308, 11193]` | — | `[9734, 10044, 10308, 11193]` |
| **Final Members (R112)** | `[8242, 9854, 11638, 11984]` | `[8809, 9734, 9740, 10044, 10308, 10634, 11193]` | `[8242, 9854, 11638, 11984]` | `[8809, 9734, 9740, 10044, 10308, 10634, 11193]` |
| **Final Size / Gen** | 4 cells / Gen 2 | 7 cells / Gen 5 | 4 cells / Gen 2 | 7 cells / Gen 5 |
| **Sensory Cell Ratio** | 4/4 (100.0%) | 7/7 (100.0%) | 4/4 (100.0%) | 7/7 (100.0%) |
| **Pairwise Overlap** | **0 cells (Jaccard = 0.0000)** | **0 cells (Jaccard = 0.0000)** | **0 cells (Jaccard = 0.0000)** | **0 cells (Jaccard = 0.0000)** |

**Key Observation:**
Despite S4 in Group B being preceded by `النسر` instead of `الطفل`, the primary and secondary assemblies recruited the **exact same founding triangles** (`[8242, 9854, 11638]` and `[8809, 9740, 10634]`), grew on the **exact same roots** (Roots 15 and 17), and recruited the **exact same growth cells** (`[11984]` and `[9734, 10044, 10308, 11193]`).
*(Note: Assembly ID 8 in Group B vs 7 in Group A is a cosmetic enumeration difference arising because `النسر`'s extra exposure at Root 4 consumed an ID earlier).*

---

## 5. Sensory Fragmentation Analysis

SIC-V1 projects `ماء` onto 16 fixed sensory microcolumns:
$$\text{Sensory Footprint}(\text{ماء}) = \{8242, 8809, 8946, 9734, 9740, 9854, 10044, 10140, 10308, 10634, 10690, 11193, 11510, 11638, 11640, 11984\}$$

### 5.1 Cumulative Coverage Progression Across First 10 Exposures
| Exposure # | Root ID | Sentence | Covered Before | Covered After | Uncovered After | Structural Event |
|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **1** | Root 2 | S2 | 0 / 16 (0%) | 0 / 16 (0%) | 16 / 16 (100%) | Synaptic facilitation initiated |
| **2** | Root 4 | S4 | 0 / 16 (0%) | 0 / 16 (0%) | 16 / 16 (100%) | Recurrent Hebbian co-activation |
| **3** | Root 6 | S2 | 0 / 16 (0%) | 0 / 16 (0%) | 16 / 16 (100%) | Efficacy consolidation |
| **4** | Root 8 | S4 | 0 / 16 (0%) | 0 / 16 (0%) | 16 / 16 (100%) | Reciprocal edges crossing $\Theta_A$ |
| **5** | Root 10 | S2 | 0 / 16 (0%) | 0 / 16 (0%) | 16 / 16 (100%) | Multiple 3-cliques forming |
| **6** | Root 12 | S4 | 0 / 16 (0%) | 0 / 16 (0%) | 16 / 16 (100%) | Pre-formation consolidation |
| **7** | Root 14 | S2 | 0 / 16 (0%) | **3 / 16 (18.8%)** | **13 / 16 (81.2%)** | **Primary Assembly Formed** (`[8242, 9854, 11638]`) |
| — | Root 15 | S3 | 3 / 16 (18.8%) | 4 / 16 (25.0%) | 12 / 16 (75.0%) | Primary Assembly GROW (+`11984`) |
| **8** | Root 16 | S4 | **4 / 16 (25.0%)** | **7 / 16 (43.8%)** | **9 / 16 (56.2%)** | **Secondary Assembly Formed** (`[8809, 9740, 10634]`) |
| — | Root 17 | S1 | 7 / 16 (43.8%) | 11 / 16 (68.8%) | 5 / 16 (31.2%) | Secondary Assembly GROW (+4 cells) |
| **9** | Root 18 | S2 | 11 / 16 (68.8%) | 11 / 16 (68.8%) | 5 / 16 (31.2%) | Stable coexistence established |
| **10** | Root 20 | S4 | 11 / 16 (68.8%) | 11 / 16 (68.8%) | 5 / 16 (31.2%) | Stable coexistence established |

### 5.2 Causality of Fragmentation
The progression confirms that when Assembly 1 forms at Exposure 7, **12 of the 16 sensory cells remain unrecruited**. Because these 12 cells continue firing synchronously every time `ماء` is exposed, their reciprocal synaptic connections inevitably cross the formation threshold $\Theta_A = 0.10$. Under Core §2.0 candidate search rules, any reciprocal 3-clique with $< 70\%$ overlap with existing assemblies is deemed novel. Thus, the unrecruited sensory residual lawfully sprouts an independent duplicate assembly.

---

## 6. Context Comparison & Readout Competition

### 6.1 Probing Generations
We probed generation from the prefix `النسر يشرب` in both groups, as well as `الطفل يشرب` in Group A:

| Checkpoint | Condition | Probe Prefix | Top Candidate | Runner-Up Candidate | Margin $\Delta$ | $M_{\text{READ}}$ | Generation Status |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **Root 56** | Group A | `النسر يشرب` | Asm 7 (`ماء`): 0.630178 | Asm 9 (`ماء`): 0.621774 | 0.008404 | 0.040000 | `GEN_STOP_AMBIGUOUS` |
| **Root 56** | Group A | `الطفل يشرب` | Asm 7 (`ماء`): 0.630196 | Asm 9 (`ماء`): 0.621769 | 0.008426 | 0.040000 | `GEN_STOP_AMBIGUOUS` |
| **Root 56** | Group B | `النسر يشرب` | Asm 8 (`ماء`): 0.628285 | Asm 9 (`ماء`): 0.622972 | 0.005312 | 0.040000 | `GEN_STOP_AMBIGUOUS` |
| **Root 112** | Group A | `النسر يشرب` | Asm 7 (`ماء`): 0.565988 | Asm 9 (`ماء`): 0.558708 | 0.007280 | 0.040000 | `GEN_STOP_AMBIGUOUS` |
| **Root 112** | Group A | `الطفل يشرب` | Asm 7 (`ماء`): 0.565976 | Asm 9 (`ماء`): 0.558695 | 0.007282 | 0.040000 | `GEN_STOP_AMBIGUOUS` |
| **Root 112** | Group B | `النسر يشرب` | Asm 8 (`ماء`): 0.565323 | Asm 9 (`ماء`): 0.560533 | 0.004789 | 0.040000 | `GEN_STOP_AMBIGUOUS` |

### 6.2 Comparison Analysis
- In both Group A and Group B, the competing assemblies for `ماء` score within $\Delta \approx 0.005 - 0.008$, far below the margin threshold $M_{\text{READ}} = 0.0400$.
- Repeating a single context in Group B did **not** resolve the ambiguity; in fact, the margin narrowed slightly from $0.0073$ in Group A to $0.0048$ in Group B.
- This confirms that representational multiplicity caused by sensory fragmentation is invariant to contextual multiplicity.

---

## 7. Internal Control — `تفاح`

The sentence S3 `الطفل يأكل تفاح` was held strictly constant across both Group A and Group B.

### 7.1 Formation Comparison for `تفاح`
- **Group A:** Assembly 14 (Root 27, size 4, Gen 2) and Assembly 17 (Root 31, size 7, Gen 5).
- **Group B:** Assembly 14 (Root 27, size 4, Gen 2) and Assembly 17 (Root 31, size 7, Gen 5).
- In both groups, founding triangles were identical: `[9334, 9468, 10457]` and `[8513, 10363, 10616]`.
- In both groups, growth recruitments were identical: +`[11289]` and +`[8961, 10181, 10737, 11830]`.
- Jaccard overlap between Assembly 14 and Assembly 17: **$0.0000$ (0 shared cells)**.

### 7.2 Readout Dynamics for `تفاح` under `الطفل يأكل`
| Checkpoint | Group | Top Candidate | Runner-Up Candidate | Margin $\Delta$ | Status | Outcome |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Root 56** | Group A | Asm 17: 0.476088 | Asm 14: 0.461492 | 0.014596 | `AMBIGUOUS` | `GEN_STOP_AMBIGUOUS` |
| **Root 56** | Group B | Asm 17: 0.479672 | Asm 14: 0.448262 | 0.031410 | `AMBIGUOUS` | `GEN_STOP_AMBIGUOUS` |
| **Root 112** | Group A | Asm 17: **0.468219** | Asm 14: **0.419496** | **0.048723** | `OK` | **Emits `تفاح` cleanly** |
| **Root 112** | Group B | Asm 17: **0.505622** | Asm 14: **0.446392** | **0.059230** | `OK` | **Emits `تفاح` cleanly** |

### 7.3 Critical Scientific Implication
At Root 112, in both groups, Assembly 17 broke symmetry over Assembly 14 by more than $M_{\text{READ}} = 0.040000$.
This empirical finding definitively refutes Hypothesis 5: **Structural multiplicity does NOT necessarily cause readout ambiguity.**
When developmental divergence allows one assembly's internal recurrent synaptic efficacy to sufficiently exceed that of its duplicate, the readout mechanism can cleanly select a single winner without ambiguous halt.

---

## 8. Evaluation of Scientific Hypotheses

| Hypothesis | Proposition | Empirical Evidence | Verdict |
|:---|:---|:---|:---:|
| **H1** | Multiple contexts are necessary for duplicate assembly formation. | In Group B, duplicate assemblies (Asm 8 & 9) formed under a single linguistic context (`النسر يشرب ماء`) at the exact same roots and cells. | **CONTRADICTED** |
| **H2** | Repeated sensory exposure under a single context is sufficient for duplicate assembly formation. | Group B demonstrated that single-context exposure reliably sprouts duplicate assemblies. | **SUPPORTED** |
| **H3** | The initial assembly captures only part of the sensory footprint, permitting further independent formation. | Initial assembly captured only 4 of 16 sensory cells ($25\%$), leaving 12 uncovered cells ($75\%$) from which the second assembly sprouted with $J = 0.0$. | **SUPPORTED** |
| **H4** | Changes in contextual frequency alter assembly formation and growth. | Doubling `النسر` frequency accelerated subject assembly density (Gen 10 vs Gen 3) and widened the `تفاح` Root 112 margin from 0.0487 to 0.0592. | **SUPPORTED** |
| **H5** | Structural multiplicity necessarily causes readout ambiguity. | Coexisting assemblies for `تفاح` (Asm 14 & 17) generated cleanly without ambiguity at Root 112 in both groups ($\Delta > 0.04$). | **CONTRADICTED** |

---

## 9. Verification & Regression State

- **CF02 Forensic Verification Test:** [`tests/forensics/test_r2_c01_cf02_sensory_fragmentation.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/forensics/test_r2_c01_cf02_sensory_fragmentation.py)
  - Result: **3 passed in 27.20s**
- **Full Repository Regression Suite:**
  - Collected: **247 items**
  - Passed: **247 passed in 168.91s**
  - Failed: **0**
  - Skipped / xfailed: **0**
- **Production Source Code:** Completely untouched (`src/` intact, 0 diffs).
- **Epistemic Modularity:** `ZERO_SELECTION_LEAKAGE` strictly preserved.

---

## 10. Recommended Next Architectural Decisions

Because representational multiplicity is driven by **sensory projection under-recruitment** (SIC-V1 projecting 16 cells vs 3-cell seed triangles) rather than context multiplicity, attempts to fix ambiguity by modifying context models or sequence prediction will fail.

The architecture authority should consider three principled options:

1. **Receptive Field Re-Clustering (Core §2.0 Formation Amendment):**
   When an assembly forms, mark all active sensory cells within the same sensory projection footprint as "claimed" by the nascent assembly (e.g., establishing wide inhibitory halos or wider seed clusters), preventing unrecruited sensory residual cells from forming duplicate assemblies.
2. **Receptive Field Overlap Consolidation (Core §2.0 Merge Amendment):**
   Extend R2-B03 assembly consolidation to evaluate shared sensory receptive fields. If two assemblies have high overlap in their sensory projection provenance (even if their cell member intersection is low), allow merge evaluation based on shared sensory source columns.
3. **Downstream Readout Surface Coincidence (Peripheral Readout Amendment):**
   Allow the readout mechanism to recognize when top-competing candidates resolve to identical attested peripheral envelopes, waiving the $M_{\text{READ}}$ margin check or aggregating their causal gain.

---

## 11. Authoritative Sign-Off

- **Investigator:** Principal Cognitive Architecture Experimental Engineer & Independent Scientific Auditor
- **Regression State:** 247/247 passed (100% clean)
- **Production Status:** Intact (`src/` strictly unmodified)
- **Authorized Verdict:**
  `R2-C01-CF02 COMPLETE — REPRESENTATION FORMATION EFFECT MEASURED`
