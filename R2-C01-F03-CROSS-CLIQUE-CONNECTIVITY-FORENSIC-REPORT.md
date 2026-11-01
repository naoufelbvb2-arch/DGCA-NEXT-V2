# DGCA NEXT V2 — R2-C01-F03 Forensic Investigation Report

## Sensory Cross-Clique Connectivity, Synaptic Evidence & Structural Reuse Forensics

### Executive Summary

- **Investigation ID:** `R2-C01-F03`
- **Status:** **FORENSIC INVESTIGATION COMPLETE — ALL CROSS-CLIQUE MECHANISMS EMPIRICALLY CHARACTERIZED**
- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Baseline Main Commit:** `f044c20b532f89749675120ffb1d8ada997e3a5e`
- **Accepted CF03 Experimental Commit:** `6ef522b3b7a41ad2d5d50f573524e50d5999d93e`
- **Active Forensic Branch:** `experiment/r2-c01-f03-cross-clique-connectivity`
- **Architectural Scope:** Zero Core modifications authorized; read-only causal diagnostics and formal regression verification.
- **Regression Outcome:** **257 passed, 0 failed** (baseline 253 + 4 new automated forensic verification tests).
- **Authorized Verdict:** **`R2-C01-F03 FORENSIC COMPLETE — CROSS-CLIQUE MECHANISMS CHARACTERIZED`**

---

## 1. Authoritative Provenance & Investigation Scope

| Dimension | Baseline Main | Accepted CF03 HEAD | Active Forensic Branch |
| :--- | :--- | :--- | :--- |
| **Commit SHA** | `f044c20b532f89749675120ffb1d8ada997e3a5e` | `6ef522b3b7a41ad2d5d50f573524e50d5999d93e` | `experiment/r2-c01-f03-cross-clique-connectivity` |
| **Branch** | `main` | `experiment/r2-c01-cf03-birth-time-grow` | `experiment/r2-c01-f03-cross-clique-connectivity` |
| **Epistemic Modularity** | Strictly Enforced | Strictly Enforced | Strictly Enforced (`ZERO_SELECTION_LEAKAGE`) |
| **Core Laws Changed** | None | Bounded experimental flag | **Zero production changes** |
| **Test Suite Size** | 249 tests | 253 tests | **257 tests (100% passing)** |

This forensic investigation was chartered to establish the precise mechanistic basis for neural representation multiplicity in DGCA NEXT V2. Specifically, it resolves why repeated exposure to identical sensory footprints (e.g. `ماء`, `تفاح`, and filler `حليب`) leads to the birth of multiple structurally disjoint assemblies (e.g. Assembly 7 & 9 for `ماء`, Assembly 14 & 17 for `تفاح`) and why canonical `GROW` laws fail to recruit secondary sensory cells into the founder assembly.

---

## 2. Quantitative Synaptic Graph Matrices (F03-S01)

Across all audit roots ($r \in \{12, 14, 15, 16, 17, 27, 28, 31, 32, 56, 112\}$), pairwise connectivity within each 16-cell sensory footprint was exhaustively classified:

### A. Subgraph Synaptic Classifications Across Audit Roots

#### 1. Sensory Footprint for `ماء` (16 Cells: Total Possible Undirected Pairs = 120)
| Root | Directed Synapses in $W$ | Reciprocal Edges ($R_{ij}^B \ge 0.20$) | Graph Density | Disjoint Components | 3-Cliques (Triangles) | Pair Classifications Breakdown |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **12** | 74 | 0 | 0.0000 | 16 | 0 | `NO_EDGE`: 83, `CANDIDATE_ONLY`: 37 |
| **14** (Asm 7 Born) | 74 | 6 | 0.0500 | 13 | 4 | `NO_EDGE`: 83, `CANDIDATE`: 31, `RECIP_ELIGIBLE`: 6 |
| **15** | 74 | 6 | 0.0500 | 13 | 4 | `NO_EDGE`: 83, `CANDIDATE`: 31, `RECIP_ELIGIBLE`: 6 |
| **16** (Asm 9 Born) | 74 | 24 | 0.2000 | 6 | 20 | `NO_EDGE`: 83, `CANDIDATE`: 13, `RECIP_ELIGIBLE`: 24 |
| **17** | 74 | 24 | 0.2000 | 6 | 20 | `NO_EDGE`: 83, `CANDIDATE`: 13, `RECIP_ELIGIBLE`: 24 |
| **27** | 74 | 37 | 0.3083 | 1 | 32 | `NO_EDGE`: 83, `CANDIDATE`: 0, `RECIP_ELIGIBLE`: 37 |
| **28** | 74 | 37 | 0.3083 | 1 | 32 | `NO_EDGE`: 83, `CANDIDATE`: 0, `RECIP_ELIGIBLE`: 37 |
| **31** | 74 | 37 | 0.3083 | 1 | 32 | `NO_EDGE`: 83, `CANDIDATE`: 0, `RECIP_ELIGIBLE`: 37 |
| **32** | 74 | 37 | 0.3083 | 1 | 32 | `NO_EDGE`: 83, `CANDIDATE`: 0, `RECIP_ELIGIBLE`: 37 |
| **56** | 78 | 37 | 0.3083 | 1 | 32 | `NO_EDGE`: 83, `CANDIDATE`: 0, `RECIP_ELIGIBLE`: 37 |
| **112** | 78 | 39 | 0.3250 | 1 | 33 | `NO_EDGE`: 81, `CANDIDATE`: 0, `RECIP_ELIGIBLE`: 39 |

#### 2. Sensory Footprint for `تفاح` (16 Cells: Total Possible Undirected Pairs = 120)
| Root | Directed Synapses in $W$ | Reciprocal Edges ($R_{ij}^B \ge 0.20$) | Graph Density | Disjoint Components | 3-Cliques (Triangles) | Pair Classifications Breakdown |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **12..17** | 72 | 0 | 0.0000 | 16 | 0 | `NO_EDGE`: 84, `CANDIDATE_ONLY`: 36 |
| **27** (Asm 14 Born) | 72 | 6 | 0.0500 | 13 | 4 | `NO_EDGE`: 84, `CANDIDATE`: 30, `RECIP_ELIGIBLE`: 6 |
| **28** | 72 | 6 | 0.0500 | 13 | 4 | `NO_EDGE`: 84, `CANDIDATE`: 30, `RECIP_ELIGIBLE`: 6 |
| **31** (Asm 17 Born) | 72 | 24 | 0.2000 | 6 | 20 | `NO_EDGE`: 84, `CANDIDATE`: 12, `RECIP_ELIGIBLE`: 24 |
| **32** | 72 | 24 | 0.2000 | 6 | 20 | `NO_EDGE`: 84, `CANDIDATE`: 12, `RECIP_ELIGIBLE`: 24 |
| **56** | 72 | 24 | 0.2000 | 6 | 20 | `NO_EDGE`: 84, `CANDIDATE`: 12, `RECIP_ELIGIBLE`: 24 |
| **112** | 72 | 24 | 0.2000 | 6 | 20 | `NO_EDGE`: 84, `CANDIDATE`: 12, `RECIP_ELIGIBLE`: 24 |

#### 3. Sensory Footprint for `حليب` (16 Cells: Total Possible Undirected Pairs = 120)
| Root | Directed Synapses in $W$ | Reciprocal Edges ($R_{ij}^B \ge 0.20$) | Graph Density | Disjoint Components | 3-Cliques (Triangles) | Pair Classifications Breakdown |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **12..17** | 84 | 0 | 0.0000 | 16 | 0 | `NO_EDGE`: 78, `CANDIDATE_ONLY`: 42 |
| **27..28** | 86 | 3 | 0.0250 | 14 | 1 | `NO_EDGE`: 77, `CANDIDATE`: 40, `RECIP_ELIGIBLE`: 3 |
| **31..32** | 62 | 13 | 0.1083 | 7 | 5 | `NO_EDGE`: 89, `CANDIDATE`: 18, `RECIP_ELIGIBLE`: 13 |
| **56** | 92 | 16 | 0.1333 | 6 | 6 | `NO_EDGE`: 71, `CANDIDATE`: 33, `RECIP_ELIGIBLE`: 16 |
| **112** | 98 | 16 | 0.1333 | 6 | 6 | `NO_EDGE`: 71, `CANDIDATE`: 33, `RECIP_ELIGIBLE`: 16 |

---

### B. Pairwise Mutual Support Matrix $R_{ij}^B$ Between Assembly 7 and Assembly 9 Founders

At Root 16 close (when Assembly 9 forms), the reciprocal mutual support values $R_{ij}^B$ between the 4 cells of Assembly 7 (`[8242, 9854, 11638, 11984]`) and the 8 founder cells of Assembly 9 (`[8809, 9734, 9740, 10044, 10308, 10634, 10690, 11193]`) are:

| Assembly 7 Cell \ Assembly 9 Cell | 8809 | 9734 | 9740 | 10044 | 10308 | 10634 | 10690 | 11193 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **8242** | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| **9854** | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| **11638** | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| **11984** | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

**Finding:** There is **strictly 0.0000 reciprocal support** between any cell in Assembly 7 and any cell in Assembly 9 at the moment Assembly 9 forms. In fact, **no directed synapse (candidate or consolidated) exists in $W$ between them**.

---

## 3. Reciprocal Connectivity Statistics (F03-S01)

- **Total Possible Undirected Pairs:** For a 16-cell sensory projection footprint, $\binom{16}{2} = 120$ possible undirected pairs exist.
- **Birth-Time Density of Assembly 7 (Root 14):**
  - Intra-clique eligible reciprocal edges = 6 (forming a 4-clique: $\{8242, 9854, 11638, 11984\}$).
  - Graph density = $6 / 120 = 0.0500$.
- **Birth-Time Density of Assembly 9 (Root 16):**
  - Intra-clique eligible reciprocal edges in Assembly 9 founder cluster = 18 edges (among 8 cells).
  - Plus 6 edges in Assembly 7 = 24 total reciprocal edges.
  - Overall graph density = $24 / 120 = 0.2000$.
  - **Cross-Clique Edges = 0**.

---

## 4. Component and Clique Topology (F03-S02)

### A. Connected Components
1. **At Root 14 Close (Birth of Assembly 7):**
   - **Component 1 (Size 4):** `[8242, 9854, 11638, 11984]` (The complete 4-clique).
   - **Components 2–13 (Size 1 each):** The remaining 12 cells (`[8809], [8946], [9734], [9740], [10044], [10140], [10308], [10634], [10690], [11193], [11510], [11640]`) are completely isolated vertices in the reciprocal graph ($R_{ij}^B = 0$).
2. **At Root 16 Close (Birth of Assembly 9):**
   - **Component 1 (Size 4):** `[8242, 9854, 11638, 11984]` (Assembly 7).
   - **Component 2 (Size 8):** `[8809, 9734, 9740, 10044, 10308, 10634, 10690, 11193]` (Assembly 9 founder component).
   - **Components 3–6 (Size 1 each):** `[8946], [10140], [11510], [11640]` (Periphery cells not yet recruited).
   - **Graph Topology:** Disjoint bipartite clusters. Diameter between Component 1 and Component 2 is **infinite ($\infty$)**.
3. **At Root 27 Close:**
   - Single connected component containing all 16 cells, with 37 reciprocal edges and 32 triangles.

### B. 3-Clique (Triangle) Enumeration
- **Root 14:** Exactly 4 triangles: all 4 are subsets of the 4 founder cells of Assembly 7 ($\binom{4}{3} = 4$).
- **Root 16:** Exactly 20 triangles: 4 triangles within Assembly 7, and 16 triangles within the 8-cell Component 2. **Zero triangles bridge the two components**.

---

## 5. GROW Eligibility Decomposition (F03-S03)

Canonical Core §5.2 GROW requires:
1. Size bound: $|A| < K_{\text{MAX}} = 12$.
2. Reciprocal degree: $d(x, A) \ge D_{\text{MIN}} = 2$, where $d(x, A) = |N_{\text{rec}}(x) \cap A|$.
3. Density: $\text{dens}(x, prospective) \ge \rho_G = 0.70$.
4. Specificity: $\text{spec}(x, prospective) \ge \sigma_G = 0.20$.
5. Keep-guards: All existing members maintain degree $\ge D_{\text{MIN}}$ and specificity $\ge \sigma_K = 0.20$.

### Decomposition for Non-Member Sensory Cells of `ماء` at Root 14 & 16:

#### Assembly 7 at Root 14 Close (Members: `[8242, 9854, 11638]`):
| Candidate Cell $x$ | $d(x, A)$ | $\text{dens}(x, A \cup \{x\})$ | $\text{spec}(x)$ | $\sum R_{xj}^B$ | Keep-Guards | First Failed Condition | Verdict |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **11984** | **3** | **1.0000** | **1.0000** | **0.8299** | OK | None | **ELIGIBLE** (Recruited at R15) |
| **8809** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **8946** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **9734** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **9740** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **10044** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **10140** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **10308** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **10634** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **10690** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **11193** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **11510** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |
| **11640** | 0 | 0.0000 | 0.0000 | 0.0000 | OK | $d(x, A) < 2$ | `DEGREE_BELOW_D_MIN (d=0 < 2)` |

#### Assembly 7 at Root 16 Close (Members: `[8242, 9854, 11638, 11984]`):
All 12 secondary cells have $d(x, A) = 0 < 2$. Not a single cell passes the first guard.

#### Assembly 14 at Root 27 Close for `تفاح` (Members: `[9334, 9468, 10457]`):
- **Cell 11289:** $d=3, \text{dens}=1.0 \rightarrow$ **ELIGIBLE** (Recruited).
- **All remaining 11 apple cells:** $d(x, A) = 0 < 2 \rightarrow$ `DEGREE_BELOW_D_MIN (d=0 < 2)`.

**Causal Conclusion:** Non-member sensory cells do **not** fail GROW because of density bounds ($\rho_G$), specificity bounds ($\sigma_G$), or keep-guard invalidations. They fail at the **very first filter**: **they have zero reciprocal edges to the existing assembly ($d = 0 < D_{\text{MIN}} = 2$)**.

---

## 6. FORM Eligibility Decomposition (F03-S04)

In Core §5.3, FORM executes as follows:
1. **Uncovered Cells Calculation:**
   $$\text{CoreCoverage}(A, t) = \frac{|A \cap L_t|}{|A|} \ge 0.70$$
   If an existing assembly $A$ has $\ge 70\%$ overlap with active cells $L_t$, its members $A \cap L_t$ are marked covered.
   Uncovered set $U_t = L_t \setminus \bigcup_{A \text{ covered}} (A \cap L_t)$.
2. **At Root 16 Close for `ماء`:**
   - Active cells $L_t = 16$ cells.
   - Assembly 7 members present = $\{8242, 9854, 11638, 11984\}$ (4 cells).
   - $\text{CoreCoverage}(\text{Asm } 7, t) = 4 / 4 = 1.0000 \ge 0.70$.
   - Therefore, the 4 cells of Assembly 7 are marked covered.
   - **Crucial Uncovered Set:**
     $$U_t = L_t \setminus \{8242, 9854, 11638, 11984\} = \{8809, 8946, 9734, 9740, 10044, 10140, 10308, 10634, 10690, 11193, 11510, 11640\} \quad (12 \text{ cells})$$
3. **Seed Formation within $U_t$:**
   - Within $U_t$, 8 cells have formed a dense cluster with 16 triangles among themselves.
   - FORM enumerates triangles in $U_t$, selects seed triangle $\{8809, 9734, 9740\}$, and greedily expands it into the remaining reciprocal partners in $U_t$.
   - **Result:** Assembly 9 is born with 7 founder cells (later expanded to 8 cells).

**Finding:** Assembly 9 forms entirely lawfully under Core §5.3 because Assembly 7's 4 members cannot cover the other 12 sensory cells.

---

## 7. Synaptic Learning Pathway & Latent Table Partitioning (F03-S05)

Why did cross-clique synapses never form between Assembly 7 cells and Assembly 9 cells?

We audited `src/dgca/lifecycle/exposure_tx.py` lines 500–555 (`_update_coactive_latent_neighborhoods_for_event`) and `generate_event_link_proposals`:

```python
# From src/dgca/lifecycle/exposure_tx.py:516-533
top_curr_clique = active_curr[:4]
secondary_curr_clique = active_curr[4:]

for cid in active_curr:
    # ...
    # Partition top-4 F0 clique from secondary sub-lexical peers so F0 cells maintain high Spec(x, A) >= 0.20
    peer_pool = top_curr_clique if cid in top_curr_clique else secondary_curr_clique
    same_event_limit = 3 if active_prev else 6
    same_peers = [p for p in peer_pool if p != cid][:same_event_limit]
    desired_partners = same_peers + prev_peers
    for partner_id in desired_partners:
        w.latent_table.admit_or_recycle_coactive_partner(cid, partner_id, ...)
```

### Mechanistic Chain of Causality:
1. **Latent Table Neighborhood Partitioning:**
   - Active sensory cells are ranked by activity: `top_curr_clique = active_curr[:4]` (which become Assembly 7 founders) and `secondary_curr_clique = active_curr[4:]` (which become Assembly 9 founders).
   - For any cell in `top_curr_clique`, its `peer_pool` is strictly restricted to `top_curr_clique`.
   - Cells in `top_curr_clique` **never** admit cells in `secondary_curr_clique` into their latent table slots.
2. **Latent Table Eligibility:**
   - Intra-Top Latent Table Eligibility: **6 / 6 (100%)**.
   - Intra-Secondary Latent Table Eligibility: **30 / 66 (45.5%)**.
   - Cross-Clique Latent Table Eligibility: **1 / 48 (2.1%)**, and **0 / 32 (0.0%)** between Assembly 7 and Assembly 9 founders.
3. **Link Proposal Generation:**
   - `generate_event_link_proposals` checks `w.latent_table.is_eligible(src, tgt)`.
   - Since cross-clique pairs are ineligible in the latent table, **zero cross-clique link proposals are ever generated**.
4. **Synapse Creation in $W$:**
   - Because no link proposals exist, **zero candidate synapses** are ever created between the cliques.
   - Because no synapses exist in $W$, $R_{ij}^B = 0.0000$ identically for all cross-clique pairs.
5. **GROW Blockage:**
   - When GROW runs on Assembly 7, every non-member sensory cell has $d(x, A) = 0 < 2$. GROW is structurally impossible.

---

## 8. CF03 Evidence Reconciliation (F03-S06 Part A)

### Reconciling State-Hash Discrepancy Between Group A and Group B
In R2-C01-CF03, Group A (`enable_birth_time_grow=False`) and Group B (`enable_birth_time_grow=True`) produced:
- Identical target assembly memberships (Assemblies 7, 8, 9, 11, 13, 14, 15, 16, 17).
- Identical readout probe winners and identical readout scores.
- Yet their `state_hash` at Root 56 and Root 112 differed.

### Exact MachineState Diff Breakdown at Root 56 & Root 112:
1. **Target Assemblies Identical:**
   - Assembly 7 (`ماء`): `{8242, 9854, 11638, 11984}` in both Group A and Group B.
   - Assembly 9 (`ماء`): `{8809, 9734, 9740, 10044, 10308, 10634, 10690, 11193}` in both Group A and Group B.
   - Assembly 14 (`تفاح`): `{9334, 9468, 10457, 11289}` in both Group A and Group B.
   - Assembly 17 (`تفاح`): `{8513, 8961, 10181, 10363, 10616, 10737, 11083, 11830}` in both Group A and Group B.
2. **The Sole Divergent Structure in the Entire Network: Assembly 4 (Filler):**
   - **Group A:** Members = `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)` (size 8, generation 7).
   - **Group B:** Members = `(8834, 9209, 10570, 10646, 10915, 11153, 11583)` (size 7, generation 6).
   - **Mechanism:** In Group A, cell `12116` was recruited to Assembly 4. In Group B, earlier birth-time growth operations on preceding assemblies mutated reverse-index membership counts or altered tie-breaking order, preventing cell `12116` from being recruited to filler Assembly 4.
3. **Reconciled Finding:**
   - Complete MachineState snapshot hash equivalence between Group A and Group B is **FALSE**.
   - Target assembly structural membership and functional readout score equivalence is **TRUE**.

---

## 9. Post-Assembly Rollback Verification with `FP_02` (F03-S06 Part B)

To verify the transaction atomicity required by Section 9B, a controlled fault injection was conducted using fault injection point `FP_02` in `exposure_tx.py` line 1057.

- **Placement of `FP_02`:** Executes immediately after `_run_assembly_pipeline` finishes mutating assemblies and immediately before atomic publication view swap (`self.publication_view = next_pub`).
- **Execution under Test (`test_post_assembly_transactional_rollback_fp02`):**
  - Transaction initiated with `enable_birth_time_grow=True` and `tx._fault_injection_point = "FP_02"`.
  - Exposure 14 processed and `end_exposure(14)` invoked.
  - Runtime exception `RuntimeError("Injected fault at FP-02")` was successfully trapped.
- **Rollback Verification Results:**
  - `Root 14 in publication_view.completed_roots`: **`False`** (Unpublished).
  - `state.W.assemblies count`: **`0`** (No assemblies leaked into published state).
  - `state.W.completed_roots_high_watermark`: **`0`** (Watermark intact).
  - `working_copy` discarded; `state.W` completely uncommitted and unchanged.

---

## 10. Scientific Hypothesis Evaluation Matrix (F03-S07)

| Hypothesis | Proposed Mechanism | Empirical Test Result | Status |
| :--- | :--- | :--- | :--- |
| **H1: Missing Synapses** | Cross-clique synapses between founder and secondary cells are completely absent in $W$. | At Root 14 and 16, **0** directed synapses exist between Assembly 7 and 9. $R_{ij}^B = 0.0000$ identically. | **CONFIRMED (PRIMARY MECHANISM)** |
| **H2: Candidate Stagnation** | Cross-clique synapses exist as CANDIDATE but fail to accumulate consolidation evidence. | Zero cross-clique candidate synapses exist in $W$. | **REFUTED** (Edges do not exist at all) |
| **H3: Ineligible Support** | Synapses exist, but candidate cells fail GROW density ($\rho_G$) or specificity ($\sigma_G$) bounds. | Cells fail at $d(x, A) = 0 < D_{\text{MIN}} = 2$. Density and specificity checks are never reached. | **REFUTED AS PRIMARY** (Blocked at degree filter) |
| **H4: FORM Suppression Failure** | $\text{CoreCoverage} \ge 0.70$ fails to suppress secondary FORM because 12 cells remain uncovered. | $\text{CoreCoverage}(\text{Asm } 7) = 1.0$, covering 4 cells. The remaining 12 cells ($U_t$) form triangles and lawfully sprout Asm 9. | **CONFIRMED (SECONDARY MECHANISM)** |
| **H5: Latent Partitioning** | LLA explicitly partitions active cells into disjoint latent pools to preserve Tier-0 specificity. | `exposure_tx.py:516` partitions `active_curr[:4]` from `active_curr[4:]`. Latent eligibility across cliques is 0.0%. | **CONFIRMED (ROOT CAUSAL ARCHITECTURAL DRIVER)** |

---

## 11. Minimum Controlled Intervention Proposal

### Core Dilemma
The partitioning of `active_curr` in `_update_coactive_latent_neighborhoods_for_event` was intentionally introduced in earlier releases to guarantee that Tier-0 (F0) sensory cells maintain high specificity ($\text{spec}(x, A) \ge \sigma_G = 0.20$). However, because this partitioning is rigid and complete:
1. Cells in `top_curr_clique` (the top 4 F0 cells) never wire to cells in `secondary_curr_clique` (the other 12 sensory cells).
2. Consequently, no matter how many times the word is experienced, the sensory representation remains bifurcated into two disjoint components.
3. The secondary component inevitably satisfies all lawful criteria for FORM, producing a duplicate assembly.

### Candidate Architectural Options for Subsequent Evaluation:
1. **Option 1: Bounded Inter-Clique Latent Bridge:**
   Allow a controlled number (e.g. 1 or 2) of latent slots on F0 cells to admit top secondary-clique cells after a minimum number of exposures, enabling progressive bridging without degrading F0 specificity below $\sigma_G = 0.20$.
2. **Option 2: Semantic Equivalence / Morphological Merge Relaxation:**
   Allow Assemblies associated with identical peripheral surfaces under the same lexical context to execute a lawful `MERGE` when their combined footprint maintains acceptable readout margin.
3. **Option 3: Retention of Representational Multiplicity:**
   Treat representational multiplicity not as an architectural defect, but as an intentional sparse coding property where distinct assemblies encode distinct contextual nuances, resolving readout competition purely through the Readout Ledger.

---

## 12. Full Regression Verification

```
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
rootdir: C:\Users\Laptop\Desktop\DGCA NEXT V2
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.13.0, hypothesis-6.165.2, asyncio-1.4.0
collected 257 items

tests\forensics\test_f01_02_outbox_atomicity.py .....                    [  1%]
tests\forensics\test_f01_cold_start_and_persistence.py ....              [  3%]
tests\forensics\test_r2_c01_cf01_c02_consistency.py .....                [  5%]
tests\forensics\test_r2_c01_cf01_counterfactual.py .......               [  8%]
tests\forensics\test_r2_c01_cf02_sensory_fragmentation.py ...            [  9%]
tests\forensics\test_r2_c01_cf03_birth_time_grow.py ....                 [ 10%]
tests\forensics\test_r2_c01_d01_design.py ..                             [ 11%]
tests\forensics\test_r2_c01_f01_causal_forensics.py .......              [ 14%]
tests\forensics\test_r2_c01_f02_multiplicity.py ...                      [ 15%]
tests\forensics\test_r2_c01_f03_connectivity.py ....                     [ 17%]
tests\test_encoder_gates.py ..............                               [ 22%]
tests\test_fifr_b04_and_common.py .........                              [ 26%]
tests\test_phase2_anatomy_and_dynamics.py ........                       [ 29%]
tests\test_phase3_lla_and_transactions.py ..........                     [ 33%]
tests\test_phase4_context_and_graduation.py ...........                  [ 37%]
tests\test_phase5_hierarchy_and_assembly.py ...........                  [ 41%]
tests\test_phase6_readout_and_generation.py .......                      [ 44%]
tests\test_phase7_empirical_gates.py ......                              [ 46%]
tests\test_r2_a01_patch1_acceptance.py ................................. [ 59%]
...                                                                      [ 60%]
tests\test_r2_a01_patch2_acceptance.py ..............                    [ 66%]
tests\test_r2_a01_patch3_acceptance.py ........                          [ 69%]
tests\test_r2_a01_patch4_acceptance.py ........................          [ 78%]
tests\test_r2_a01_patch5_acceptance.py .........................         [ 88%]
tests\test_r2_b03_c01_acceptance.py .......                              [ 91%]
tests\test_r2_b03_exact_duplicate_merge.py ................              [ 97%]
tests\test_r2_c01_acceptance.py .......                                  [100%]

======================= 257 passed in 494.71s (0:08:14) =======================
```

---

## 13. Authorized Final Verdict

**`R2-C01-F03 FORENSIC COMPLETE — CROSS-CLIQUE MECHANISMS CHARACTERIZED`**
