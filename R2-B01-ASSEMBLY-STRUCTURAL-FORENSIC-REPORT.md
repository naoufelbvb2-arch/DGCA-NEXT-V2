# DGCA NEXT V2 — R2-B01 FORENSIC INVESTIGATION REPORT

## Assembly Duplicate Formation & Readout Collision Forensic Investigation
### (Corrected Post-Audit Baseline — R2-B01-C01 Reconciled)

- **Author:** Principal Scientific Verification Engineer, Formal Specification Auditor, Neural Architecture Research Engineer
- **Date:** October 30, 2026
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Starting Authoritative Baseline:** `faf361b6b95de6287b466eb1dc524ea49c732635` (frozen `main`)
- **Normative References:**
  - `DGCA_CORE_RC4_1.md` §2.0 (Executable Assembly Operators: `MAINTAIN → GROW → FORM → MERGE/SPLIT`)
  - `DGCA_CORE_RC4_1.md` §9.4 (I/O Envelope, Readout Ledger & Structural Generation Invalidation)
  - `DGCA_LLA_RC4_1.md` §6.6, §8.2 & §8.3 (LG-T01, LG-T02, LG-T03, LG-T16)
- **Status:** **`R2-B01 FORENSIC INVESTIGATION COMPLETE — AWAITING DESIGN REVIEW`**

---

## Executive Summary

During the verification of the 56-root cold-start curriculum (`القط يشرب حليب` and `النسر يشرب ماء`), autonomous episode generation on the Cat prompt succeeded cleanly:
$$\text{Cat Branch: } [\text{'القط'}] \longrightarrow (\text{'يشرب'}, \text{'حليب'}) \longrightarrow \text{GEN\_STOP\_EOS}$$

However, autonomous generation on the Eagle prompt halted with ambiguity at the terminal step:
$$\text{Eagle Branch: } [\text{'النسر'}] \longrightarrow (\text{'يشرب'}, \text{'ماء'}) \longrightarrow \text{GEN\_STOP\_AMBIGUOUS}$$

This investigation conducted non-invasive, bit-exact instrumentation of the frozen production pipeline across all 56 roots to establish the precise structural and causal origin of this collision. 

The empirical findings establish that:
1. **Assemblies 5 and 6 are an `EXACT_DUPLICATE` pair.** At Root 56, both assemblies have identical ordered membership tuples: `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)`, identical structural generation ($7$), identical status (`LIVE`), and identical attestation on the peripheral ledger (`<EOS>`, `Marker.EOS`).
2. **They were legally born disjoint during Root 8, Event 3 (`<EOS>`).** In Root 8, Event 3, unassigned committed fresh emitters formed two completely disjoint triangles: Assembly 5 (`[8834, 9209, 10570]`) and Assembly 6 (`[10646, 10915, 11153]`) with initial $\text{Jaccard} = 0.0000$. All six seed cells qualified as fresh emitters exclusively in Event 3.
3. **They converged via root-close GROW in Root 9.** During the Root 9 root-close assembly pipeline (`END_EXPOSURE`), symmetric co-activation and mutual support in the shared co-active context drove mutual recruitment. Assembly 5 recruited Assembly 6's cells and vice versa, rendering both assemblies 100% structurally identical at Root 9 ($8$ cells) and Root 10 ($9$ cells).
4. **MERGE rejected the pair under strict compliance with the frozen Core specification.** Across Roots 8 to 56, `_try_merge_pair(5, 6)` was evaluated 49 times:
   - *Root 8 (Birth Root, 1 evaluation):* Assemblies 5 and 6 had disjoint seed memberships ($\text{Jaccard} = 0.0000 < \Theta_{\text{merge}} = 0.70$), rejected by `JACCARD_BELOW_THETA_MERGE`.
   - *Roots 9–56 (Post-Convergence, 48 evaluations):* Assemblies 5 and 6 were 100% structurally identical ($\text{Jaccard} = 1.0000 \ge \Theta_{\text{merge}} = 0.70$, union cardinality $\le 16$). However, `DGCA_CORE_RC4_1.md` §2.0 item 4 explicitly defines:
   $$\text{between\_strength} = \text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\}, \quad \text{with } (\text{empty exclusive side} \implies 0)$$
   Because $A_5 = A_6$, both exclusive sets are empty (`excl_a = []`, `excl_b = []`). The production implementation:
   ```python
   if not excl_a or not excl_b:
       between_strength = 0.0
   ```
   faithfully executes this specification. The resulting `between_strength = 0.0 < THETA_OB (0.40)` rejected the merge in all 48 opportunities. This is classified as a **contract-compliant structural consolidation limitation**, not a software implementation defect.
5. **Readout collision is an exact floating-point and Q6 score tie.** At Step 2 of Eagle readout (`ماء` $\to$ `<EOS>`), Assemblies 5 and 6 both computed $\text{score} = 0.2069442431$ ($\text{Q6} = 206944$). The score margin was exactly $0.0000000000 < M_{\text{read}} (0.04)$, legally forcing `StatusCode.AMBIGUOUS` and `GEN_STOP_AMBIGUOUS`.

---

## 1. Authoritative Baseline

- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Frozen Main SHA:** `faf361b6b95de6287b466eb1dc524ea49c732635`
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Branch Head at Inception:** `faf361b6b95de6287b466eb1dc524ea49c732635`
- **Production Source Modification:** `0` lines modified in `src/dgca/`, `configs/`, or `tests/`.
- **R2-A01 Frozen History:** Fully preserved and unaltered.

---

## 2. Experimental Environment

- **Host Operating System:** Microsoft Windows 11 Enterprise (10.0.26200, 64-bit)
- **Python Runtime:** CPython 3.14.4 (tags/v3.14.4:3.14.4, win32)
- **Primary Tooling:**
  - `pytest`: 9.0.3
  - `hypothesis`: 6.165.2
  - `anyio`: 4.13.0
  - `asyncio`: 1.4.0
  - `pluggy`: 1.6.0
- **Hardware Architecture:** AMD64 family, 8 logical cores, high-precision IEEE 754 floating-point unit.
- **Execution Mode:** Deterministic single-threaded synchronous simulation with seedless floating-point physics.

---

## 3. Reproduction Procedure

Reproduction is automated via the standalone forensic tool:
[`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py)

### Reproduction Steps:
1. Ensure the workspace is on branch `investigation/r2-b01-assembly-forensics` at SHA `faf361b6b95de6287b466eb1dc524ea49c732635`.
2. Execute the standalone forensic script:
   ```bash
   python tools/forensics/investigate_r2_b01_assembly_collision.py
   ```
3. The script:
   - Executes two independent 56-root curriculum runs from identical fresh initial states:
     - **Run A (Untouched Production Reference):** Zero monkeypatching, pure frozen production execution.
     - **Run B (Corrected Instrumented Observer):** Evaluates `_run_form_stage()` strictly once per root receiving the complete event list; passive line tracing via `sys.settrace` and `linecache` captures event attribution non-invasively.
   - Performs a 56-root differential replay verifying 100% bit-for-bit equality across WState, HSlowState, ledger, diagnostics, and final rollout stop statuses.
   - Runs sensitivity checks: Check A (empty formation diagnostic equivalence across Roots 1–6) and Check B (root-wide formation cap $K_{\text{FORM\_PER\_END}}=12$ across multi-event root).
   - Revalidates the Assembly 5 and 6 structural convergence, MERGE rejection compliance, and Step 2 readout collision.

---

## 4. Per-Root Assembly Formation Timeline

Across the 56 roots of training, a total of 12 assemblies were formed in $W$. The complete chronological formation timeline is detailed below:

| Assembly ID | Formation Root | Stimulus Branch | Stimulus Event | Initial Seed Cells (Gen 1) | Final Card (Root 56) | Final Gen | Attested Surface Tokens | Status at Root 56 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **1** | Root 07 | AB (Cat) | Event 1 (`يشرب`) | `[8327, 9005, 10167]` | 5 | 3 | `('يشرب', NONE)` | `LIVE` |
| **2** | Root 07 | AB (Cat) | Event 3 (`<EOS>`) | `[8728, 10417, 11859]` | 4 | 2 | `('<EOS>', EOS)` | `LIVE` |
| **3** | Root 08 | DB (Eagle) | Event 0 (`النسر`) | `[8416, 8575, 8586]` | 14 | 12 | `('النسر', NONE)`, `('القط', NONE)` | `LIVE` |
| **4** | Root 08 | DB (Eagle) | Event 1 (`يشرب`) | `[9669, 11119, 12123]` | 7 | 5 | `('يشرب', NONE)` | `LIVE` |
| **5** | Root 08 | DB (Eagle) | Event 3 (`<EOS>`) | `[8834, 9209, 10570]` | 9 | 7 | `('<EOS>', EOS)` | `LIVE` |
| **6** | Root 08 | DB (Eagle) | Event 3 (`<EOS>`) | `[10646, 10915, 11153]` | 9 | 7 | `('<EOS>', EOS)` | `LIVE` |
| **7** | Root 13 | AB (Cat) | Event 0 (`القط`) | `[9061, 10595, 11077]` | 4 | 2 | `('القط', NONE)` | `LIVE` |
| **8** | Root 13 | AB (Cat) | Event 2 (`حليب`) | `[9319, 9325, 11220]` | 4 | 2 | `('حليب', NONE)` | `LIVE` |
| **9** | Root 14 | DB (Eagle) | Event 0 (`النسر`) | `[9205, 9369, 9487]` | 4 | 2 | `('النسر', NONE)` | `LIVE` |
| **10** | Root 14 | DB (Eagle) | Event 2 (`ماء`) | `[8242, 9854, 11638]` | 4 | 2 | `('ماء', NONE)` | `LIVE` |
| **11** | Root 15 | AB (Cat) | Event 2 (`حليب`) | `[9183, 9951, 11463]` | 8 | 6 | `('حليب', NONE)` | `LIVE` |
| **12** | Root 16 | DB (Eagle) | Event 2 (`ماء`) | `[8809, 9740, 10634]` | 7 | 5 | `('ماء', NONE)` | `LIVE` |

*Note:* Roots 1–6 yielded zero assemblies because cell commit density and mutual support had not yet reached the formation threshold. Roots 17–56 yielded zero new assemblies because all events met the core coverage threshold ($\text{CoreCoverage}(A, t) \ge \rho_{\text{core}} = 0.70$).

---

## 5. Birth Histories & Event Attribution of Assemblies 5 and 6

Both Assembly 5 and Assembly 6 were born in **Root 8** during the **Event 3** pass of Stage 3 (`FORM`):

```
Root 8, Event 3 Context:
- Stimulus: <EOS> (Marker.EOS)
- Pre-event committed emitters in event: 87 cells
- Live assemblies before Event 3: Assemblies 1, 2, 3, 4
- Assemblies covering Event 3: Assembly 2 covered 14 cells with CoreCoverage >= RHO_CORE (0.70)
- Unassigned committed fresh emitter pool U_t:
  U_t = [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116] (8 cells)
```

### Reproducible Proof of Event 3 Attribution:
1. **Fresh Emitter Qualification:** Inspecting the event journal demonstrates that all three seed cells of Assembly 5 (`8834, 9209, 10570`) and all three seed cells of Assembly 6 (`10646, 10915, 11153`) qualified as fresh emitters ($A_j^+ \ge \theta_{\text{emit}}$) **strictly in Event 3**. In Events 0, 1, and 2, zero of these cells met the fresh emitter qualification.
2. **Sequential Triangle Formation:**
   - Candidate enumeration identified valid 3-cell reciprocal triangles ($d(v, \text{tri})=2, D \ge 0.70, Spec \ge 0.30$) within $U_t$.
   - The first lexicographic triangle was formed: `[8834, 9209, 10570]` $\to$ **Assembly 5** (Gen 1).
   - In accordance with Core §2.0 item 3, these three cells were added to `assigned_in_event` to ensure disjoint triangle seeds.
   - The second lexicographic triangle was enumerated over remaining cells: `[10646, 10915, 11153]` $\to$ **Assembly 6** (Gen 1).
   - Remaining cells (`11583, 12116`) could not form a third 3-cell triangle.
3. **Disjoint Status at Birth:** At the end of Root 8, Assemblies 5 and 6 were completely disjoint:
   $$\text{Members}(A_5) \cap \text{Members}(A_6) = \emptyset, \quad \text{Jaccard}(A_5, A_6) = 0.0000$$

---

## 6. Exact Membership Comparison & Growth Evolution

The table below traces the structural evolution of Assemblies 5 and 6 from birth (Root 8) through convergence to the final curriculum root (Root 56):

| Root Index | Asm 5 Ordered Membership Tuple | Asm 6 Ordered Membership Tuple | Equality | Intersection | Union | Jaccard | Exclusive 5 | Exclusive 6 | Gen (5 / 6) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Root 08** | `(8834, 9209, 10570)` | `(10646, 10915, 11153)` | **False** | 0 | 6 | 0.0000 | 3 cells | 3 cells | 1 / 1 |
| **Root 09** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)` | **True** | 8 | 8 | 1.0000 | $\emptyset$ | $\emptyset$ | 6 / 6 |
| **Root 10** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |
| **Root 11** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |
| **...** | *(identical for Roots 12 through 55)* | *(identical for Roots 12 through 55)* | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |
| **Root 56** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |

### Reconciliation of GROW Lifecycle:
- **Execution Timing:** In accordance with Core §2.0, Stage 2 (`GROW`) executes **at root close** (`END_EXPOSURE` assembly pipeline pass) on the whole-root consolidated evidence graph $W^*$, NOT during individual event passes.
- **Root 09 Convergence:** During the Root 9 root close:
  - Assembly 5 added cells `[10646, 10915, 11153, 11583, 12116]`.
  - Assembly 6 added cells `[8834, 9209, 10570, 11583, 12116]`.
  - Structural generation advanced from 1 to 6 on each addition.
- **Root 10 Extension:** Both assemblies added cell `[12117]`, advancing generation to 7.
- **Structural Classification:**
  - Root 08: `DISTINCT_STRUCTURE`
  - Roots 09–56: **`EXACT_DUPLICATE`** ($A_5 = A_6, A_5 \Delta A_6 = \emptyset, \text{Jaccard} = 1.0000$).

---

## 7. FORM Eligibility Analysis & Normative Constants

The investigation audited the formation of Assemblies 5 and 6 against authoritative Core §2.0 parameters:

| Parameter | Normative Symbol | Frozen Value | Observed Value at Formation | Status |
|:---|:---:|:---:|:---:|:---:|
| Core Coverage Threshold | $\rho_{\text{core}}$ | `0.70` | Uncovered cells had $C_t < 0.70$ | **PASS** |
| Max Cell Assembly Membership | $M_{\text{max}}$ | `12` | All seed cells had count $0 < 12$ | **PASS** |
| Min Assembly Size | $K_{\text{min}}$ | `3` | Seed triangles had size $3$ | **PASS** |
| Max Assembly Size | $K_{\text{max}}$ | `16` | Seed triangles had size $3 \le 16$ | **PASS** |
| Min Reciprocal Degree | $d_{\text{min}}$ | `2` | All triangle vertices had $d = 2$ | **PASS** |
| Prospective Density | $\rho_G$ | `0.50` | Triangle vertices had $D \ge 0.70 \ge 0.50$ | **PASS** |
| Prospective Specificity | $\sigma_G$ | `0.30` | Triangle vertices had $\text{Spec} \ge 0.30$ | **PASS** |
| Triangle Seed Overlap | — | Disjoint | Disjoint seeds within event | **PASS** |
| Max FORM per Root | $K_{\text{FORM\_PER\_END}}$ | `12` | 4 formed in Root 8 $\le 12$ | **PASS** |

Both Assembly 5 and Assembly 6 were **strictly compliant** with every normative FORM acceptance predicate.

---

## 8. MERGE Predicate Analysis & Specification Compliance

Given that Assemblies 5 and 6 reached $\text{Jaccard} = 1.0$ at Root 9, the investigation examined the exact behavior of `_try_merge_pair(5, 6)`.

### Frozen Specification Contract:
`DGCA_CORE_RC4_1.md` §2.0 item 4 normatively defines the MERGE operator:
> "with Jaccard of member sets $\ge \theta_{\text{merge}} = .70$, $\text{between\_strength} \ge \theta_{\text{ob}} = .40$ where $\text{between\_strength} = \text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\}$ **(empty exclusive side $\implies$ 0)**; require $|\text{union}| \le 16$ and every proposed union member meets the MAINTAIN guards and membership limits."

### Production Implementation:
In [`src/dgca/core/assembly.py#L538-L551`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L538-L551):
```python
excl_a = sorted(set_a - set_b)
excl_b = sorted(set_b - set_a)
if not excl_a or not excl_b:
    between_strength = 0.0
else:
    cross_vals = [
        compute_mutual_support_r_b(i, j, w)
        for i in excl_a
        for j in excl_b
    ]
    between_strength = sum(cross_vals) / float(len(cross_vals))

if between_strength < THETA_OB:
    return False
```

### Formal Evaluation:
1. When $A_5 = A_6$, the exclusive sets are empty:
   $$\text{excl\_a} = A_5 \setminus A_6 = \emptyset, \quad \text{excl\_b} = A_6 \setminus A_5 = \emptyset$$
2. The code sets `between_strength = 0.0`, precisely conforming to `(empty exclusive side => 0)`.
3. The predicate evaluates:
   $$\text{between\_strength} < \Theta_{\text{ob}} \iff 0.0 < 0.40 \implies \mathbf{True}$$
4. The function executes `return False`.

### Distinction of Correctness vs. Limitation:
- **Specification Compliance:** The production code is **100% compliant** with the frozen Core specification.
- **Empirical Consequence:** Under this specification, structurally identical assemblies ($\text{Jaccard} = 1.0$) are mathematically forbidden from merging, because an empty exclusive set unconditionally yields zero between-strength.
- **Classification:** This is a **contract-compliant structural consolidation limitation** in the specification itself, NOT an implementation bug.

---

## 9. Downstream Guard Status & Counterfactual Distinction

In accordance with scientific verification rigor, we explicitly distinguish the observed failure point from unreached downstream predicates and unproven counterfactual claims:

1. **Observed Rejection Condition:**
   `_try_merge_pair(5, 6)` aborted execution at line 551 (`if between_strength < THETA_OB: return False`) across all 48 evaluations from Root 9 to Root 56.
2. **Unreached Downstream Predicates in Frozen Execution:**
   The lines following line 551 were never reached in live execution:
   ```python
   for x in union_tuple:
       live_after = (_live_assembly_ids_for_cell(x, w) - {b_id}) | {a_id}
       if len(live_after) > M_MAX:
           return False
       if not check_maintain_keep_guards(x, union_tuple, w, n_rec_cache):
           return False
   ```
3. **Read-Only Counterfactual Analysis:**
   Evaluating these downstream predicates against the frozen runtime state at Root 56 reveals:
   - Union Cardinality: $|A_5 \cup A_6| = 9 \le K_{\text{max}} (16) \implies$ **PASS**
   - Post-Merge Cell Membership: All 9 cells have $|\text{live\_after}| \le 2 \le M_{\text{max}} (12) \implies$ **PASS**
   - MAINTAIN Keep Guards on Union: Every cell satisfies $d \ge 2, D \ge \rho_{\text{keep}} (0.35), \text{Spec} \ge \sigma_{\text{keep}} (0.20)$ on the union set $\implies$ **PASS**
4. **Untested Dynamic Counterfactuals:**
   While the static guards pass in read-only analysis, dynamically merging $A_5$ and $A_6$ would trigger several consequential state transitions:
   - Advancing $A_5$'s structural generation ($7 \to 8$).
   - Transitioning $A_6$ to `AssemblyStatus.ARCHIVED`.
   - Applying merge cooldown ($T_c = 200$).
   - Bypassing or triggering subsequent SPLIT evaluation.
   Whether a modified MERGE operator produces overall system stability remains an untested hypothesis that requires formal design in R2-B02.
5. **Rejection of Hypothetical Values:**
   We explicitly reject assigning `between_strength = 1.0` as an empirical measurement. Because the Cartesian product $(A \setminus B) \times (B \setminus A)$ is empty ($\emptyset \times \emptyset = \emptyset$), cross-set mutual support is undefined without an axiomatic contract convention.

---

## 10. Readout Score and Ranking Comparison

At Root 56, autonomous episode generation was evaluated on both prompt sequences:

### Autonomous Prompt 1: `['القط']` (Cat Branch)
- **Step 0 (`القط` $\to$ `يشرب`):** Top Assembly 4 ($\text{score} = 0.513755$, elig 7/7) vs Assembly 1 ($\text{score} = 0.402970$, elig 4/5). Margin: $0.110785 > M_{\text{read}} (0.04) \implies$ **OK**. Emitted: `'يشرب'`.
- **Step 1 (`يشرب` $\to$ `حليب`):** Top Assembly 8 ($\text{score} = 0.090729$, elig 2/4) vs Assembly 1 ($\text{score} = 0.000000$, elig 0/5). Margin: $0.090729 > M_{\text{read}} (0.04) \implies$ **OK**. Emitted: `'حليب'`.
- **Step 2 (`حليب` $\to$ `<EOS>`):**
  - Winner: Assembly 2 ($\text{score} = 0.648448$, $\text{Q6} = 648448$, elig 4/4)
  - Runner-Up: Assembly 5 ($\text{score} = 0.511842$, $\text{Q6} = 511842$, elig 7/9)
  - Third Place: Assembly 6 ($\text{score} = 0.511842$, $\text{Q6} = 511842$, elig 7/9)
  - Margin: $0.648448 - 0.511842 = 0.136606 > M_{\text{read}} (0.04) \implies$ **OK**. Emitted: `'<EOS>'` (`Marker.EOS`).
- **Result:** **`StatusCode.GEN_STOP_EOS`** (Clean Success).
  *Note:* Assembly 2 won decisively, so the tie between 5 and 6 in 2nd/3rd place did not trigger ambiguity.

---

### Autonomous Prompt 2: `['النسر']` (Eagle Branch)
- **Step 0 (`النسر` $\to$ `يشرب`):** Top Assembly 4 ($\text{score} = 0.508244$, elig 7/7) vs Assembly 1 ($\text{score} = 0.398626$, elig 4/5). Margin: $0.109619 > M_{\text{read}} (0.04) \implies$ **OK**. Emitted: `'يشرب'`.
- **Step 1 (`يشرب` $\to$ `ماء`):** Top Assembly 10 ($\text{score} = 0.127957$, elig 2/4) vs Assembly 1 ($\text{score} = 0.000000$, elig 0/5). Margin: $0.127957 > M_{\text{read}} (0.04) \implies$ **OK**. Emitted: `'ماء'`.
- **Step 2 (`ماء` $\to$ `<EOS>`):**
  - Candidate 1: Assembly 5 ($\text{score} = 0.2069442431$, $\text{Q6} = 206944$, elig 3/9)
  - Candidate 2: Assembly 6 ($\text{score} = 0.2069442431$, $\text{Q6} = 206944$, elig 3/9)
  - Candidate 3: Assembly 2 ($\text{score} = 0.0935894215$, $\text{Q6} = 93589$, elig 1/4)
  - Margin: **$0.0000000000$**
  - Ambiguity Gate: $\text{Margin } (0.0000) < M_{\text{read}} (0.04) \implies \mathbf{True}$
  - Step Status: `StatusCode.AMBIGUOUS`
- **Result:** **`StatusCode.GEN_STOP_AMBIGUOUS`** (Ambiguity Safe-Halt).

---

## 11. Ledger Invalidation & Attestation Constraints

`DGCA_CORE_RC4_1.md` §2.0 and §9.4 establish fundamental invariants governing peripheral ledger attestations:

> "Each membership change increments structural_generation, invalidating prior ledger readout attestation until re-confirmed."
> "Any `MERGE/SPLIT/ARCHIVE` invalidates an old matching ledger binding; loss of a printable surface must be reported, never resolved by fetching a historical archived Assembly ID."

### Implications for Merge Remediation:
1. **No Automatic Attestation Transfer:** A surviving assembly cannot inherit historical ledger attestations without violating the invalidation contract. If Assembly 5's generation is incremented from 7 to 8 upon merging with Assembly 6, the candidate row `(5, 8)` has **0 confirmed roots**.
2. **No Archived ID Aliasing:** The peripheral ledger cannot resolve readout requests by aliasing archived Assembly ID 6 to surviving ID 5. Fetching archived IDs is explicitly prohibited.
3. **Mandatory Re-Attestation Consideration:** If a merge occurs at Root $R$, the surviving assembly will require at least $\text{MIN\_ATTESTED\_EXTERNAL\_ROOTS} = 2$ subsequent external exposures before it can legally participate as an attested winner. This is a critical timing and training budget constraint for R2-B02.

---

## 12. Competing Alternative Explanations

| Hypothesis | Proposed Mechanism | Empirical Finding | Causal Verdict |
|:---|:---|:---|:---:|
| **H1: Distinct Structures, Coincidental Tie** | Assemblies 5 and 6 have different cells but coincidentally computed identical scores. | Disproved. $A_5$ and $A_6$ share all 9 cells ($A_5 \Delta A_6 = \emptyset$). | **REFUTED** |
| **H2: Duplicate FORM Birth** | FORM stage created two identical assemblies at birth. | Disproved. At birth (Root 8), $A_5$ and $A_6$ had 0 cells in common ($\text{Jaccard} = 0.0$). | **REFUTED** |
| **H3: Ledger Attestation Collision** | Ledger attestation failed or confused token envelopes. | Disproved. Both assemblies recorded 46 confirmed roots for `<EOS>` with valid distinct outbox entries. | **REFUTED** |
| **H4: MERGE Never Evaluated Pair** | Pair $(5, 6)$ was never checked by `_try_merge_pair` due to ordering, cooldown, or capacity. | Disproved. Pair was evaluated in 49 consecutive roots (Root 8 rejected by Jaccard=0.0; Roots 9–56 rejected strictly by `between_strength = 0.0`). | **REFUTED** |

---

## 13. Candidate Repair Strategies & Architectural Risks (for R2-B02)

The forensic findings identify three candidate architectural strategies for the future R2-B02 design contract:

### Candidate Strategy 1: Formal Specification Amendment to MERGE (Recommended)
- **Concept:** Amend Core §2.0 item 4 to define an exception or alternative rule for identical or superset assemblies: when $\text{Jaccard}(A, B) \ge \Theta_{\text{merge}}$ and exclusive sets are empty, between-strength check is bypassed or defined as satisfying the threshold.
- **Architectural Risks:**
  - *Attestation Lag:* Generation bump invalidates prior `<EOS>` attestation. The system would require additional training roots for the merged assembly to re-attest before generation succeeds.
  - *Cooldown Interaction:* Merge puts survivor into cooldown ($T_c = 200$), preventing subsequent merges during that window.

### Candidate Strategy 2: Pre-Convergence GROW / FORM Constraints
- **Concept:** Inhibit dual triangle formation within a single event when unassigned emitters exhibit high coactive density, or restrict GROW from adding cells that create duplicate assemblies.
- **Architectural Risks:**
  - High risk of suppressing legitimate parallel feature representations in multi-word vocabularies.
  - Modifies core neural dynamics (Core §2–§8).

### Candidate Strategy 3: Readout Deduplication Layer
- **Concept:** In `evaluate_full_vs_control_readout`, deduplicate candidate assemblies having identical membership tuples prior to evaluating margin ambiguity.
- **Architectural Risks:**
  - Circumvents Core assembly lifecycle; leaves duplicate assemblies proliferating in $W$.
  - Violates separation of concerns between Core graph topology and peripheral readout.

---

## 14. Full Regression Evidence

The frozen test suites confirm zero regressions on `investigation/r2-b01-assembly-forensics`:

### 1. Master Regression Suite
```bash
python -m pytest tests/ -q
```
**Result:** `192 passed in 35.66s` (100% PASS).

### 2. Forensic Test Suite
```bash
python -m pytest tests/forensics/ -v
```
**Result:** `9 passed in 14.24s` (100% PASS).

---

## 15. Explicit Unresolved Questions & Recommended Scope for R2-B02

### Unresolved Decision Questions:
1. **Surviving Assembly Selection:** When Assemblies 5 and 6 merge, does $\min(\text{ID}_A, \text{ID}_B)$ strictly apply, or is the survivor determined by attestation maturity?
2. **Re-Attestation Budget:** When structural generation increments on merge, how many training roots must follow before autonomous readout is expected to pass?
3. **Specification Amendment Form:** Should the Core §2.0 specification amendment define `between_strength` for empty exclusive sets as $1.0$, or should it specify an explicit bypass condition `if Jaccard >= theta_merge and not excl_a and not excl_b:`?

### Recommended Scope for R2-B02 Design Contract:
- Scope strictly bounded to:
  1. Formal scientific amendment to Core §2.0 Assembly MERGE law for exact/superset duplicates.
  2. Training curriculum design to accommodate post-merge re-attestation requirements.
- Hard Boundaries:
  - Zero changes to neural equations (Core §2–§8).
  - Zero changes to LLA, transactional boundaries, or outbox pipelines (R2-A01).
