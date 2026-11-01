# DGCA NEXT V2 — R2-C01-CF03 Counterfactual Report
## Bounded Birth-Time Structural Reuse Counterfactual

- **Experiment ID:** `R2-C01-CF03`
- **Role:** Principal Cognitive Architecture Experimental Engineer, Sparse Structural Learning Researcher, Independent Scientific Verification Lead
- **Status:** **COMPLETE — EXPERIMENTAL INTERVENTION ISOLATED**
- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Investigation Branch:** `experiment/r2-c01-cf03-birth-time-structural-reuse`
- **Investigation Base HEAD:** `d1e64075f48499a6e657b90a79d12f117f3c9bff` (Accepted D01 Design HEAD)
- **Production main (Frozen):** `f044c20b532f89749675120ffb1d8ada997e3a5e`
- **Authorized Final Verdict:**
  `R2-C01-CF03 COMPLETE — BIRTH-TIME STRUCTURAL REUSE EFFECT MEASURED`

---

## 1. Executive Summary & Core Scientific Verdict

The R2-C01-D01 temporal audit revealed that newly born assemblies possess already-consolidated reciprocal local synaptic support for additional members at the moment of their birth, but cannot recruit them during that same exposure because the canonical pipeline executes `GROW` before `FORM` (`MAINTAIN` $\to$ `GROW` $\to$ `FORM` $\to$ `MERGE` $\to$ `SPLIT`). This introduced a 1-root latency, deferring structural growth to the subsequent root.

The objective of R2-C01-CF03 was to test the hypothesis: **Does allowing a newly formed assembly to execute an immediate, strictly lawful GROW pass during its birth close prevent or reduce subsequent independent duplicate assembly formation?**

### Core Experimental Verdict: Decisive Empirical Null Effect
1. **Accelerated Growth Commit (Confirmed):**
   In Group B (Experimental Birth-Time Growth), newly formed assemblies immediately recruited their pre-consolidated reciprocal candidates at their birth close:
   - Assembly 7 (`ماء`) recruited cell `11984` at **Root 14** (reaching Gen 2, size 4), eliminating the Root 15 growth latency observed in Group A.
   - Assembly 9 (`ماء`) recruited 4 candidate cells at **Root 16** (reaching Gen 5, size 7), eliminating the Root 17 growth latency observed in Group A.
   - Assemblies 13 & 14 (`تفاح`) recruited their candidate cells at **Root 27** (instead of Root 28).
   - Assemblies 16 & 17 (`تفاح`) recruited their candidate cells at **Root 31** (instead of Root 32).
2. **Duplicate Assembly Formation Persists (Null Effect):**
   Despite eliminating the growth delay, duplicate assembly formation was **completely unchanged**:
   - Exactly **two** structurally disjoint assemblies formed for `ماء` (Assembly 7 and Assembly 9) in both groups.
   - Exactly **two** structurally disjoint assemblies formed for `تفاح` (Assembly 14 and Assembly 17) in both groups.
   - Jaccard similarity between coexisting assemblies remained exactly **$0.0000$ (0 shared cells)**.
3. **Causal Mechanism Characterized:**
   Direct structural probing reveals that the unrecruited sensory cells of `ماء` (`[8809, 9740, 10634]`, etc.) **do not have reciprocal synapses ($R_{ij}^B \ge 0.10$) with Assembly 7's founding members**. In SIC-V1, sensory cells form discrete sub-lexical feature cliques. Assembly 7's founders had reciprocal support *only* for cell `11984`. Even with birth-time growth enabled, Assembly 7 cannot lawfully recruit cells from disjoint sub-cliques without violating Core keep guards ($d \ge 2$, $D \ge 0.50$, $\text{spec} \ge 0.30$). Consequently, the unrecruited 12 sensory cells remain outside Assembly 7 and inevitably sprout Assembly 9 on their next exposure.
4. **Readout Competition Invariance:**
   Both groups remain locked in `GEN_STOP_AMBIGUOUS` on `النسر يشرب` and `الطفل يشرب` (margins $\Delta = 0.007280 < M_{\text{READ}} = 0.040000$). Both groups cleanly break symmetry on `الطفل يأكل` (`تفاح`) at Root 112 (margin $\Delta = 0.048723 > M_{\text{READ}} = 0.040000$).

---

## 2. Experimental Implementation Boundary

The experimental intervention was strictly isolated in `src/dgca/core/assembly.py` and `src/dgca/lifecycle/exposure_tx.py`:

```python
# src/dgca/core/assembly.py: execute_assembly_end_pipeline
formed_ids, diagnostics = _run_form_stage(
    w_shadow, h_slow, event_results, preexisting_live, n_rec_cache
)
if enable_birth_time_grow and formed_ids:
    birth_grown_ids = _run_grow_stage(
        w_shadow, n_rec_cache, target_assembly_ids=formed_ids
    )
    grown_ids = sorted(set(grown_ids) | set(birth_grown_ids))
merged_pairs = _run_merge_stage(w_shadow, n_rec_cache)
```

### 2.1 Adherence to Invariants
- **Default Preservation:** `enable_birth_time_grow` defaults to `False` across the entire codebase. All baseline production flows and existing tests execute the unmodified frozen pipeline.
- **Exact Guard Reuse:** The birth-time pass invokes the exact normative `_run_grow_stage` function, evaluating the exact same candidate neighborhoods, candidate ordering by $(-R^B, \text{cell\_id})$, density thresholds ($\rho_G \ge 0.50$), specificity ($\sigma_G \ge 0.30$), and member keep guards.
- **Target Isolation:** Only newly formed assemblies (`target_assembly_ids=formed_ids`) are evaluated in the secondary pass; pre-existing assemblies are untouched.
- **Transaction Atomicity:** All mutations execute exclusively on shadow state $W^*$ before the single atomic publication pointer swap. Injected failure at `FP_01` produces a 100% clean rollback with 0 leaked assemblies or state mutations.
- **ZERO_SELECTION_LEAKAGE:** The intervention does not inspect, pass, or touch surface strings or ledger metadata.

---

## 3. Structural Timing Differences Across Critical Roots

| Root | Sentence Presented | Group A (Frozen Baseline) Pipeline Events | Group B (Birth-Time Grow) Pipeline Events | Structural Timing Effect |
|:---:|:---|:---|:---|:---|
| **Root 14** | S2 (`النسر يشرب ماء`) | `FORM`: Asm 7 (size 3, Gen 1)<br>`GROW`: () | `FORM`: Asm 7 (size 3, Gen 1)<br>`BIRTH_GROW`: Asm 7 + `11984` (size 4, Gen 2) | **Immediate recruitment** of pre-consolidated candidate `11984` at birth close. |
| **Root 15** | S3 (`الطفل يأكل تفاح`) | `FORM`: Asm 8 (size 3, Gen 1)<br>`GROW`: Asm 7 + `11984` (size 4, Gen 2) | `FORM`: Asm 8 (size 3, Gen 1)<br>`BIRTH_GROW`: Asm 8 + `11370` (size 4, Gen 2)<br>`GROW`: () | Asm 7 already grew at Root 14. Asm 8 grows immediately at birth close. |
| **Root 16** | S4 (`الطفل يشرب ماء`) | `FORM`: Asm 9 (size 3, Gen 1)<br>`GROW`: Asm 8 + `11370` (size 4, Gen 2) | `FORM`: Asm 9 (size 3, Gen 1)<br>`BIRTH_GROW`: Asm 9 + 4 cells (size 7, Gen 5)<br>`GROW`: () | **Duplicate Asm 9 still forms!** Immediately recruits its 4 candidate cells at birth close. |
| **Root 17** | S1 (`القط يشرب حليب`) | `FORM`: ()<br>`GROW`: Asm 9 + 4 cells (size 7, Gen 5) | `FORM`: ()<br>`GROW`: () | Asm 9 already grew at Root 16. No pending growth remains. |
| **Root 27** | S3 (`الطفل يأكل تفاح`) | `FORM`: Asm 13, Asm 14 (size 3, Gen 1)<br>`GROW`: () | `FORM`: Asm 13, Asm 14<br>`BIRTH_GROW`: Asm 13, Asm 14 (size 4, Gen 2) | Asm 14 recruits `11289` immediately at Root 27 close. |
| **Root 28** | S4 (`الطفل يشرب ماء`) | `FORM`: ()<br>`GROW`: Asm 13, Asm 14 (size 4, Gen 2) | `FORM`: ()<br>`GROW`: () | Growth latency eliminated for Asm 14. |
| **Root 31** | S3 (`الطفل يأكل تفاح`) | `FORM`: Asm 16, Asm 17 (size 3, Gen 1)<br>`GROW`: () | `FORM`: Asm 16, Asm 17<br>`BIRTH_GROW`: Asm 16, Asm 17 (size 7, Gen 5) | **Duplicate Asm 17 still forms!** Immediately recruits 4 cells at Root 31 close. |
| **Root 32** | S4 (`الطفل يشرب ماء`) | `FORM`: ()<br>`GROW`: Asm 16, Asm 17 (size 7, Gen 5) | `FORM`: ()<br>`GROW`: () | Growth latency eliminated for Asm 17. |

---

## 4. Assembly Formation & Membership Comparison (Root 112)

| Assembly ID | Lexical Surface | Birth Root | Birth Members | Final Members (Root 112) | Size (A / B) | Gen (A / B) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **7** | `ماء` | Root 14 | `[8242, 9854, 11638]` | `[8242, 9854, 11638, 11984]` | 4 / 4 | Gen 2 / 2 |
| **9** | `ماء` | Root 16 | `[8809, 9740, 10634]` | `[8809, 9734, 9740, 10044, 10308, 10634, 11193]` | 7 / 7 | Gen 5 / 5 |
| **14** | `تفاح` | Root 27 | `[9334, 9468, 10457]` | `[9334, 9468, 10457, 11289]` | 4 / 4 | Gen 2 / 2 |
| **17** | `تفاح` | Root 31 | `[8513, 10363, 10616]` | `[8513, 8961, 10181, 10363, 10616, 10737, 11830]` | 7 / 7 | Gen 5 / 5 |

### 4.1 Sensory Footprint Coverage for `ماء` (16 Cells)
- **Active Sensory Footprint:** `[8242, 8809, 8946, 9734, 9740, 9854, 10044, 10140, 10308, 10634, 10690, 11193, 11510, 11638, 11640, 11984]`
- **Assembly 7 Coverage:** 4 of 16 cells ($25.0\%$).
- **Assembly 9 Coverage:** 7 of 16 cells ($43.75\%$).
- **Cumulative Coverage:** 11 of 16 cells ($68.75\%$).
- **Unrecruited Residual Cells:** 5 of 16 cells ($31.25\%$).
- **Pairwise Assembly Overlap:** $J(A_7, A_9) = 0.0000$ (0 shared cells).

---

## 5. Readout Competition & Generation Probes

Generation episodes were evaluated from cold checkpoints at Root 56 and Root 112 across all four canonical probes:

| Checkpoint | Probe Prefix | Group A Top Candidate & Score | Group B Top Candidate & Score | Margin $\Delta$ (A / B) | First-Step Status | Full Trajectory |
|:---:|:---|:---|:---|:---:|:---:|:---|
| **Root 56** | P1 (`القط يشرب`) | Asm 11 (`حليب`): 0.049006 | Asm 11 (`حليب`): 0.049006 | 0.049006 / 0.049006 | `NO_MATCH` | `['NO_MATCH']` |
| **Root 56** | P2 (`النسر يشرب`) | Asm 7 (`ماء`): 0.630178<br>Asm 9 (`ماء`): 0.621774 | Asm 7 (`ماء`): 0.630178<br>Asm 9 (`ماء`): 0.621774 | 0.008404 / 0.008404 | `AMBIGUOUS` | `['AMBIGUOUS']` |
| **Root 56** | P3 (`الطفل يأكل`) | Asm 17 (`تفاح`): 0.476088<br>Asm 14 (`تفاح`): 0.461492 | Asm 17 (`تفاح`): 0.476088<br>Asm 14 (`تفاح`): 0.461492 | 0.014596 / 0.014596 | `AMBIGUOUS` | `['AMBIGUOUS']` |
| **Root 56** | P4 (`الطفل يشرب`) | Asm 7 (`ماء`): 0.630196<br>Asm 9 (`ماء`): 0.621769 | Asm 7 (`ماء`): 0.630196<br>Asm 9 (`ماء`): 0.621769 | 0.008426 / 0.008426 | `AMBIGUOUS` | `['AMBIGUOUS']` |
| **Root 112** | P1 (`القط يشرب`) | Asm 11 (`حليب`): 0.088060 | Asm 11 (`حليب`): 0.088060 | 0.088060 / 0.088060 | `OK` | `['حليب', 'NO_MATCH']` |
| **Root 112** | P2 (`النسر يشرب`) | Asm 7 (`ماء`): 0.565988<br>Asm 9 (`ماء`): 0.558708 | Asm 7 (`ماء`): 0.565988<br>Asm 9 (`ماء`): 0.558708 | 0.007280 / 0.007280 | `AMBIGUOUS` | `['AMBIGUOUS']` |
| **Root 112** | P3 (`الطفل يأكل`) | Asm 17 (`تفاح`): 0.468219<br>Asm 14 (`تفاح`): 0.419496 | Asm 17 (`تفاح`): 0.468219<br>Asm 14 (`تفاح`): 0.419496 | **0.048723 / 0.048723** | **`OK`** | `['تفاح', 'NO_MATCH']` |
| **Root 112** | P4 (`الطفل يشرب`) | Asm 7 (`ماء`): 0.565976<br>Asm 9 (`ماء`): 0.558695 | Asm 7 (`ماء`): 0.565976<br>Asm 9 (`ماء`): 0.558695 | 0.007282 / 0.007282 | `AMBIGUOUS` | `['AMBIGUOUS']` |

**Key Takeaways:**
1. Scores, rankings, and margins in Group B are **bit-for-bit identical** to Group A at Root 56 and Root 112.
2. The birth-time grow intervention changed the *root index* at which growth was committed (e.g. Root 14 instead of Root 15), but by Root 56 and Root 112, both groups converged to the exact same equilibrium states and readout dynamics.
3. The ambiguity halt on `ماء` persists; symmetry breaking on `تفاح` persists.

---

## 6. Acceptance Gates Evaluation

| Gate | Requirement | Evidence | Verdict |
|:---|:---|:---|:---:|
| **Gate A: Intervention Isolation** | Only the declared timing behavior differs between groups. | Only `enable_birth_time_grow` differed; all Core parameters, LLA laws, and corpora remained identical. | **PASS** |
| **Gate B: Structural Lawfulness** | All GROW and FORM constraints remain satisfied. | Reused exact `_run_grow_stage` logic, density, specificity, and keep guards; no capacity violations ($K_{\text{MAX}} \le 16$, $M_{\text{MAX}} \le 12$). | **PASS** |
| **Gate C: Representation Formation Effect** | Measure whether earlier structural reuse changes duplicate assembly formation. | Measured cleanly: **Decisive null effect**. Birth-time grow accelerates recruitment of connected neighbors but cannot recruit across disjoint sub-cliques; duplicate assemblies still sprout. | **PASS (Measured Null Effect)** |
| **Gate D: Generation Effect** | Measure candidate margins, correct first tokens, and complete EOS trajectories. | Accurately measured: identical score profiles, persistent ambiguous halts on `ماء`, identical symmetry breaking on `تفاح`. | **PASS** |
| **Gate E: Negative Controls** | No violation of safety, capacity, attestation, or epistemic boundaries. | 0 capacity violations, non-retroactive ledger intact, `ZERO_SELECTION_LEAKAGE` strictly preserved, transactional rollback verified under failure injection. | **PASS** |
| **Gate F: Reproducibility** | Deterministic cold-start replay and consistent canonical traces. | 100% deterministic replay confirmed via state snapshot SHA-256 hashes. | **PASS** |

---

## 7. Verification & Regression State

- **CF03 Forensic Verification Suite:** [`tests/forensics/test_r2_c01_cf03_birth_time_grow.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tests/forensics/test_r2_c01_cf03_birth_time_grow.py)
  - Result: **4 passed in 33.82s**
- **Full Repository Regression Suite:** `python -m pytest -q`
  - Collected: **253 items**
  - Passed: **253 passed in 256.23s**
  - Failed / Skipped / Xfailed: **0**
- **Production Source Code:** Completely regression-free; default baseline flow untouched.

---

## 8. Recommended Next Architectural Decision

The CF03 counterfactual provides a critical negative proof:
> **Scientific Finding:** Accelerating `GROW` execution to birth time is structurally incapable of preventing duplicate assembly formation because disjoint sensory sub-cliques do not have reciprocal local edges ($R_{ij}^B = 0.0 < \Theta_A$).

Therefore, future architectural work must **not** attempt pipeline reordering or timing optimizations. To resolve sensory fragmentation, the architecture authority must pursue one of the two genuine topological interventions identified in R2-C01-D01:

1. **Adaptive Sensory Receptive Field Clustering (Core §2.0 FORM):**
   When seeding an assembly from an externally grounded sensory event, cluster all co-active sensory microcolumns of the token up to $K_{\text{MAX}} = 16$ rather than restricting the seed to an arbitrary 3-clique.
2. **Receptive Field Overlap Consolidation (Core §2.0 MERGE):**
   Extend assembly merge operators to evaluate sensory receptive field provenance: if two assemblies share $> 70\%$ of their underlying sensory projection source columns, allow merge consolidation even if their internal cell Jaccard similarity is low.

---

## 9. Authoritative Sign-Off

- **Investigator:** Principal Cognitive Architecture Experimental Engineer & Independent Scientific Auditor
- **Regression State:** 253/253 passed (100% clean)
- **Branch:** `experiment/r2-c01-cf03-birth-time-structural-reuse`
- **Authorized Verdict:**
  `R2-C01-CF03 COMPLETE — BIRTH-TIME STRUCTURAL REUSE EFFECT MEASURED`
