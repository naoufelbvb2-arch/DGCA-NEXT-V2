# DGCA NEXT V2 — R1-F02 Corrections to R1-F01 Audit Record

**Document:** Formal Addendum and Technical Corrigendum to `R1-F01-FORENSIC-REPORT.md`  
**Author:** Independent Forensic Verification Engineer  
**Audit Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Audit Branch:** `audit/r1-f02-evidence-closure`  
**Date:** October 28, 2026  

---

## 1. Purpose of this Addendum

In accordance with scientific integrity standards, original audit findings and records from report `R1-F01` must not be silently edited or retroactively altered. This standalone addendum formally identifies, documents, and corrects several technical, constant, and conceptual imprecisions identified in `R1-F01`.

---

## 2. Table of Corrections

| Item | R1-F01 Text / Imprecision | Corrected R1-F02 Fact | Normative Reference & Evidence |
|---|---|---|---|
| **1. Merge Threshold Constant** | Cited $\theta_{\text{OB}} = 0.50$ in text and formulas. | The actual defined threshold in production code is $\theta_{\text{OB}} = 0.40$. | `src/dgca/core/assembly.py:44`: `THETA_OB: float = 0.40`. (The bug remains identical: $0.0 < 0.40 \implies$ merge rejected). |
| **2. Assembly Duplication Nature** | Described duplicate Assemblies in natural learning as "exact structural duplicates". | Natural cold-start learning produces `SAME_SURFACE_DIFFERENT_STRUCTURE` (parallel sub-cliques for the same word), not `EXACT_STRUCTURAL_DUPLICATE` (count = 0). Exact duplicates were only verified via fixture. | Evaluated across roots 34, 56, 80: All live assemblies have distinct sorted member sets, but multiple assemblies exist for "يشرب", "حليب", "ماء". |
| **3. EOS Generation Failure Cause** | Implied autonomous multi-step generation failed because the model inherently could not learn EOS. | The benchmark explicitly set `append_eos=False`. When trained with `append_eos=True`, the model successfully forms native EOS Assemblies and emits `<EOS>` with `GEN_STOP_EOS`. | Controlled experiment in `scratch/task6_eos_experiment.py` and `tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_task6_eos_learning_and_multistep_rollout`. |
| **4. Feature vs Territory Distinction** | Conflated raw SIC-V1 Encoder feature hashes with downstream neural territory address spaces. | Encoder features are 32-bit SIC values hashed into global cell addresses across regions (`LANGUAGE: 8192..12287`), whereas microcolumns and territories are physical spatial partitions inside Core. | `dgca_v2_dynamic_core_reconstruction_encoder_specification.md §2.1` & `DGCA_CORE_RC4_1.md §1.1`. |
| **5. Design Rule vs Defect Distinction** | Described the $\mu$-source masking and $P_j^T > 0$ rule simply as "bugs". | $P_j^T > 0$ is a strict transcription of normative formula in `DGCA_CORE_RC4_1.md §9.2`. The defect is an *architectural specification defect* (omission of lateral Pass-2 causal drive), not an unauthorized coder deviation. | `DGCA_CORE_RC4_1.md §9.2`: `eligibleNext_j = 1[P_j^T > 0 and gain_j > 0]`. |

---

## 3. Detailed Technical Analysis of Corrections

### 3.1 Threshold Constant $\theta_{\text{OB}}$
- **Previous statement in R1-F01:**
  *"Because 0.0 < THETA_OB (0.50), _try_merge_pair returns False!"*
- **Correction:**
  In `src/dgca/core/assembly.py`, line 44 defines:
  ```python
  THETA_OB: float = 0.40
  ```
  The mathematical defect remains completely intact: when `set_a == set_b`, exclusions `excl_a` and `excl_b` are empty, resulting in `between_strength = 0.0`. Since $0.0 < 0.40$, exact duplicate Assemblies are unconditionally rejected by `_try_merge_pair`.

### 3.2 Exact Duplicate vs Multiple Sub-Cliques
- **Previous statement in R1-F01:**
  Combined exact duplicate sets with same-surface parallel Assemblies under a single umbrella.
- **Correction:**
  Forensic Task 2 tracked every LIVE Assembly through roots 34, 56, and 80.
  - `EXACT_STRUCTURAL_DUPLICATE`: Exactly 0 instances observed under natural cold-start learning.
  - `SAME_SURFACE_DIFFERENT_STRUCTURE`: Systematically observed for every lexical token:
    - Token "يشرب": Assembly 1 (gen=3, 5 cells) and Assembly 3 (gen=5, 7 cells).
    - Token "حليب": Assembly 5 (gen=2, 4 cells) and Assembly 8 (gen=6, 8 cells).
    - Token "ماء": Assembly 7 (gen=3, 5 cells) and Assembly 9 (gen=5, 7 cells).
  This proves that natural learning builds multiple overlapping microcolumn cliques for the same lexical surface rather than generating exact clone sets.

### 3.3 EOS Omission in the Baseline Curriculum
- **Previous statement in R1-F01:**
  *"Multi-step rollout stops at step 1 because no EOS assembly was learned."*
- **Correction:**
  The baseline training curriculum in Gate C and the initial R1-F01 test invoked `encode_exposure(..., append_eos=False)`. Consequently, the network was never presented with EOS tokens during training.
  When tested under an identical curriculum with `append_eos=True` (Task 6):
  1. Two native Assemblies formed for surface `<EOS>` (Assembly 2 and Assembly 3).
  2. The model achieved `GEN_STOP_EOS` on branch AB.
  3. A single-word prompt `['القط']` successfully generated a 2-step rollout: `['يشرب', 'حليب']` and terminated safely at `<EOS>`.

---

## 4. Final Note
These corrections strengthen, rather than weaken, the forensic foundation of DGCA NEXT V2. They precisely delineate between compiler/coding bugs (e.g. R1-B01, R1-B02, R1-H04, R1-H05), specification design flaws (e.g. R1-M03), and experimental artifact boundaries (e.g. EOS omission).
