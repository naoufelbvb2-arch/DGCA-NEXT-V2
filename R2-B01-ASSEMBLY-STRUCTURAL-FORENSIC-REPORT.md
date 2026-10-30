# DGCA NEXT V2 — R2-B01 FORENSIC INVESTIGATION REPORT

## Assembly Duplicate Formation & Readout Collision Forensic Investigation

- **Author:** Principal Cognitive Architecture Research Engineer, Neural Graph Forensics Specialist, Scientific Verification Engineer
- **Date:** October 30, 2026
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Starting Authoritative Baseline:** `faf361b6b95de6287b466eb1dc524ea49c732635` (frozen `main`)
- **Status:** **`R2-B01 FORENSIC INVESTIGATION COMPLETE — AWAITING DESIGN REVIEW`**

---

## Executive Summary

During the verification of the 56-root cold-start curriculum (`القط يشرب حليب` and `النسر يشرب ماء`), autonomous episode generation on the Cat prompt succeeded cleanly:
$$\text{Cat Branch: } [\text{'القط'}] \longrightarrow (\text{'يشرب'}, \text{'حليب'}) \longrightarrow \text{GEN\_STOP\_EOS}$$

However, autonomous generation on the Eagle prompt halted with ambiguity at the terminal step:
$$\text{Eagle Branch: } [\text{'النسر'}] \longrightarrow (\text{'يشرب'}, \text{'ماء'}) \longrightarrow \text{GEN\_STOP\_AMBIGUOUS}$$

This investigation conducted non-invasive, bit-exact instrumentation of the frozen production pipeline across all 56 roots to establish the precise structural and causal origin of this collision. 

The empirical findings establish that:
1. **Assemblies 5 and 6 are an `EXACT_DUPLICATE` pair.** At Root 56, both assemblies have identical membership tuples: `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)`, identical structural generation ($7$), identical status (`LIVE`), and identical attestation on the peripheral ledger (`<EOS>`, `Marker.EOS`).
2. **They were born disjoint in Root 8, Event 3 (`<EOS>`).** In Root 8, fresh unassigned emitters formed two completely disjoint triangles: Assembly 5 (`[8834, 9209, 10570]`) and Assembly 6 (`[10646, 10915, 11153]`) with $\text{Jaccard} = 0.0000$.
3. **They converged via GROW in Root 9.** During the subsequent exposure, symmetric coactivation and high mutual support recruited the other triangle's cells, rendering both assemblies 100% structurally identical at Root 9 ($8$ cells) and Root 10 ($9$ cells).
4. **MERGE failed to merge them due to a specific predicate defect.** In all 49 consecutive roots from Root 8 to Root 56, `_try_merge_pair(5, 6)` was evaluated. While $\text{Jaccard} = 1.0 \ge \Theta_{\text{merge}} (0.70)$ and union cardinality $\le K_{\text{max}} (12)$, the implementation computes `between_strength` strictly over $(A \setminus B) \times (B \setminus A)$. Because $A = B$, both exclusive sets are empty (`excl_a = []`, `excl_b = []`), triggering the fallback:
   ```python
   if not excl_a or not excl_b:
       between_strength = 0.0
   ```
   This assigned `between_strength = 0.0`, failing the gate `between_strength >= THETA_OB (0.40)` and permanently blocking MERGE.
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
   - Initializes a fresh, unseeded `MachineState()`, an empty `SurfaceReadoutLedgerV1()`, and a production `ExposureTransactionManager`.
   - Attaches non-invasive pre- and post-invocation loggers to `_run_form_stage`, `_run_grow_stage`, and `_try_merge_pair` in memory without modifying disk source code.
   - Streams 56 alternating exposure transactions:
     - Odd roots ($1, 3, \dots, 55$): `القط يشرب حليب <EOS>` (Branch AB)
     - Even roots ($2, 4, \dots, 56$): `النسر يشرب ماء <EOS>` (Branch DB)
   - Performs autonomous multi-step rollout for prompts `['القط']` and `['النسر']`.
   - Restores all monkeypatched module functions before exit.

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

*Note:* Roots 1–6 yielded zero assemblies because cell commit density and mutual support had not yet reached the formation threshold. Roots 17–56 yielded zero new assemblies because all events met the core coverage threshold ($C_t \ge \rho_{\text{core}} = 0.40$).

---

## 5. Birth Histories of Assemblies 5 and 6

Both Assembly 5 and Assembly 6 were born in **Root 8** during **Event 3** (`<EOS>`):

```
Root 8, Event 3 Context:
- Stimulus: <EOS> (Marker.EOS)
- Pre-event committed emitters in event: 16 cells
- Live assemblies before Event 3: Assemblies 1, 2, 3, 4
- Assemblies covering Event 3: Assembly 2 covered 8 cells (Core coverage >= 0.40)
- Unassigned committed fresh emitter pool U_t:
  U_t = [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116] (8 cells)
```

### Formation Sequence:
1. Candidate enumeration identified all 3-cell subsets of $U_t$ exhibiting reciprocal triangle mutual support ($N_{\text{rec}} \ge 1.0$).
2. Triangle 1 was selected: `[8834, 9209, 10570]`.
   - Created **Assembly 5** (Gen 1).
   - Cells `8834, 9209, 10570` were assigned locally to Assembly 5.
3. Remaining unassigned emitters in Event 3: `[10646, 10915, 11153, 11583, 12116]` (5 cells).
4. Candidate enumeration evaluated the remaining pool and identified a second valid reciprocal triangle: `[10646, 10915, 11153]`.
   - Created **Assembly 6** (Gen 1).
   - Cells `10646, 10915, 11153` were assigned locally to Assembly 6.
5. Remaining unassigned cells (`11583, 12116`) could not form a 3-cell triangle and remained unassigned.

**Direct Empirical Observation:** At the end of Root 8, Assemblies 5 and 6 were **completely disjoint**:
$$\text{Members}(A_5) \cap \text{Members}(A_6) = \emptyset, \quad \text{Jaccard}(A_5, A_6) = 0.0000$$

---

## 6. Exact Membership Comparison

The table below traces the structural evolution of Assemblies 5 and 6 from birth (Root 8) through convergence to the final curriculum root (Root 56):

| Root Index | Asm 5 Ordered Membership Tuple | Asm 6 Ordered Membership Tuple | Equality | Intersection | Union | Jaccard | Exclusive 5 | Exclusive 6 | Gen (5 / 6) |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Root 08** | `(8834, 9209, 10570)` | `(10646, 10915, 11153)` | **False** | 0 | 6 | 0.0000 | 3 cells | 3 cells | 1 / 1 |
| **Root 09** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116)` | **True** | 8 | 8 | 1.0000 | $\emptyset$ | $\emptyset$ | 6 / 6 |
| **Root 10** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |
| **Root 11** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |
| **...** | *(identical for Roots 12 through 55)* | *(identical for Roots 12 through 55)* | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |
| **Root 56** | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` | **True** | 9 | 9 | 1.0000 | $\emptyset$ | $\emptyset$ | 7 / 7 |

### Structural Classification:
- **Root 08 Classification:** `DISTINCT_STRUCTURE`
- **Roots 09–56 Classification:** **`EXACT_DUPLICATE`**
  $$\text{Members}(A_5) = \text{Members}(A_6), \quad A_5 \Delta A_6 = \emptyset, \quad \text{Jaccard}(A_5, A_6) = 1.000000$$

---

## 7. FORM Eligibility Analysis

The investigation examined whether the creation of both assemblies in Root 8, Event 3 complied with Core §9.1:

1. **Fresh Emitter Eligibility:** All 8 cells in $U_t$ were committed before Event 3 and satisfied:
   $$\text{live\_assembly\_count}(c) < M_{\text{max}} = 2$$
   None of the 8 cells were assigned to any live assembly.
2. **Core Coverage:** Existing Assembly 2 had core coverage:
   $$C_t(A_2) = \frac{|\text{Members}(A_2) \cap E_t|}{|\text{Members}(A_2)|} = \frac{4}{4} = 1.0 \ge \rho_{\text{core}} (0.40)$$
   However, Assembly 2 only accounted for 8 committed emitters, leaving 8 committed emitters completely uncovered.
3. **Reciprocal Triangle Test:** Both seed triples satisfied the triangle formation criteria:
   $$\min_{(i, j) \in \text{Triangle}} N_{\text{rec}}(i, j) \ge 1.0$$
4. **Legality Finding:** Under the frozen rules of `_run_form_stage`, both Assembly 5 and Assembly 6 were **100% legally admitted**. The algorithm permits multiple triangles to be seeded within a single event when $|U_t| \ge 6$, provided no cell is assigned to more than one triangle in that event.

---

## 8. MERGE Predicate Analysis

Given that Assemblies 5 and 6 reached $\text{Jaccard} = 1.0$ at Root 9, the investigation examined why `_try_merge_pair(5, 6)` never merged them.

### Evaluation History:
- The pair $(5, 6)$ was evaluated by `_try_merge_pair` in **49 consecutive roots** (Root 8 through Root 56).
- **At Root 08:**
  - $\text{Jaccard} = 0.0000 < \Theta_{\text{merge}} (0.70)$
  - Between-strength $= 0.239667 < \Theta_{\text{ob}} (0.40)$
  - Result: Correctly rejected (not eligible).
- **At Roots 09 through 56 (48 consecutive evaluations):**
  - Status: Both `AssemblyStatus.LIVE` $\implies$ **PASS**
  - Cooldown: $0$ (neither assembly recently underwent merge/split) $\implies$ **PASS**
  - Union Size: $|A_5 \cup A_6| = 8$ (Root 9) and $9$ (Roots 10–56) $\le K_{\text{max}} (12) \implies$ **PASS**
  - Jaccard Similarity: $\text{Jaccard} = 1.0000 \ge \Theta_{\text{merge}} (0.70) \implies$ **PASS**

### The Source Code Blocker:
In [`src/dgca/core/assembly.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L538-L551):
```python
# Check mutual support between exclusive sets (Core §9.3)
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

### Mathematical & Logical Mechanism:
1. When two assemblies are structurally identical ($A_5 = A_6$):
   $$\text{excl\_a} = A_5 \setminus A_6 = \emptyset, \quad \text{excl\_b} = A_6 \setminus A_5 = \emptyset$$
2. Because `excl_a` and `excl_b` are empty, the guard `if not excl_a or not excl_b:` branch executes.
3. It explicitly assigns:
   $$\text{between\_strength} = 0.0$$
4. Next, the predicate tests:
   $$\text{between\_strength} < \Theta_{\text{ob}} \iff 0.0 < 0.40 \implies \mathbf{True}$$
5. The function immediately executes `return False`.

**Causal Verdict:** The condition `if not excl_a or not excl_b: between_strength = 0.0` treats exact identity as **zero mutual support**. This single line permanently blocked the legal merge of Assemblies 5 and 6 for 48 consecutive roots.

---

## 9. Readout Score and Ranking Comparison

At Root 56, episode generation was evaluated on both autonomous prompt sequences:

### Autonomous Prompt 1: `['القط']` (Cat Branch)
- **Step 0 (`القط` $\to$ `يشرب`):**
  - Top Candidate: Assembly 4 ($\text{score} = 0.5137547311$, $\text{Q6} = 513755$, elig = 7/7)
  - Runner-Up: Assembly 1 ($\text{score} = 0.4029698664$, $\text{Q6} = 402970$, elig = 4/5)
  - Margin: $0.1107848647 > M_{\text{read}} (0.04) \implies$ **OK**
  - Emitted: `'يشرب'`
- **Step 1 (`يشرب` $\to$ `حليب`):**
  - Top Candidate: Assembly 8 ($\text{score} = 0.0907288892$, $\text{Q6} = 90729$, elig = 2/4)
  - Runner-Up: Assembly 1 ($\text{score} = 0.0000000000$, $\text{Q6} = 0$, elig = 0/5)
  - Margin: $0.0907288892 > M_{\text{read}} (0.04) \implies$ **OK**
  - Emitted: `'حليب'`
- **Step 2 (`حليب` $\to$ `<EOS>`):**
  - Top Candidate: Assembly 2 ($\text{score} = 0.6484484204$, $\text{Q6} = 648448$, elig = 4/4)
  - Runner-Up: Assembly 5 ($\text{score} = 0.5118424509$, $\text{Q6} = 511842$, elig = 7/9)
  - Third Place: Assembly 6 ($\text{score} = 0.5118424509$, $\text{Q6} = 511842$, elig = 7/9)
  - Margin: $0.6484484204 - 0.5118424509 = 0.1366059695 > M_{\text{read}} (0.04) \implies$ **OK**
  - Emitted: `'<EOS>'` (`Marker.EOS`)
- **Final Result:** **`StatusCode.GEN_STOP_EOS`** (Clean Success).
  *Note:* Although Assemblies 5 and 6 tied for 2nd and 3rd place, Assembly 2 won by a decisive margin of $0.1366 > 0.04$, avoiding ambiguity.

---

### Autonomous Prompt 2: `['النسر']` (Eagle Branch)
- **Step 0 (`النسر` $\to$ `يشرب`):**
  - Top Candidate: Assembly 4 ($\text{score} = 0.5082440878$, $\text{Q6} = 508244$, elig = 7/7)
  - Runner-Up: Assembly 1 ($\text{score} = 0.3986255487$, $\text{Q6} = 398626$, elig = 4/5)
  - Margin: $0.1096185392 > M_{\text{read}} (0.04) \implies$ **OK**
  - Emitted: `'يشرب'`
- **Step 1 (`يشرب` $\to$ `ماء`):**
  - Top Candidate: Assembly 10 ($\text{score} = 0.1279571503$, $\text{Q6} = 127957$, elig = 2/4)
  - Runner-Up: Assembly 1 ($\text{score} = 0.0000000000$, $\text{Q6} = 0$, elig = 0/5)
  - Margin: $0.1279571503 > M_{\text{read}} (0.04) \implies$ **OK**
  - Emitted: `'ماء'`
- **Step 2 (`ماء` $\to$ `<EOS>`):**
  - Candidate 1: Assembly 5 ($\text{score} = 0.2069442431$, $\text{Q6} = 206944$, elig = 3/9)
  - Candidate 2: Assembly 6 ($\text{score} = 0.2069442431$, $\text{Q6} = 206944$, elig = 3/9)
  - Candidate 3: Assembly 2 ($\text{score} = 0.0935894215$, $\text{Q6} = 93589$, elig = 1/4)
  - Top Score: $0.2069442431$
  - Second Score: $0.2069442431$
  - Score Margin: **$0.0000000000$**
  - Ambiguity Gate: $\text{Margin } (0.0000) < M_{\text{read}} (0.04) \implies \mathbf{True}$
  - Step Status: `StatusCode.AMBIGUOUS`
- **Final Result:** **`StatusCode.GEN_STOP_AMBIGUOUS`** (Ambiguity Safe-Halt).

### Score Tie Breakdown:
The tie between Assemblies 5 and 6 at Step 2 is an **exact IEEE 754 64-bit binary float equality**:
$$\text{Score}(A_5) = \text{Score}(A_6) = \frac{1}{|A|} \sum_{c \in A} \text{gain}(c) = 0.20694424312674403$$
Because both assemblies contain the identical 9 cell IDs, evaluate over identical synaptic weights, and have identical generation 7, their readout scores are mathematically guaranteed to be identical down to the last binary bit.

---

## 10. Verified Root-Cause Classification

The forensic evidence demonstrates a **twin-stage structural and algorithmic failure chain**:

```
[Root 8, Event 3]
  Dense unassigned emitters (8 cells) form TWO legal, disjoint triangles
  --> Assembly 5: [8834, 9209, 10570]
  --> Assembly 6: [10646, 10915, 11153]
         │
         ▼
[Root 9, Event 3]
  GROW stage evaluates mutual support in shared context
  Both assemblies recruit each other's cells and fresh emitters
  --> Assembly 5 becomes [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116]
  --> Assembly 6 becomes [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116]
  STRUCTURAL CONVERGENCE TO EXACT DUPLICATE (Jaccard = 1.0)
         │
         ▼
[Roots 9 to 56]
  MERGE stage evaluates pair (5, 6) on every root:
  Jaccard = 1.0 >= 0.70 (PASS)
  Union size = 9 <= 12 (PASS)
  Status = LIVE (PASS)
  --> BUT excl_a = [] and excl_b = []
  --> Predicate sets between_strength = 0.0
  --> 0.0 < THETA_OB (0.40) strictly REJECTS MERGE
  MERGE IS PERMANENTLY DISABLED FOR IDENTICAL ASSEMBLIES
         │
         ▼
[Root 56, Prompt 'النسر']
  Step 2 readout evaluates candidate assemblies:
  Both Assembly 5 and Assembly 6 compute score = 0.2069442431
  Score margin = 0.0000000000 < M_read (0.04)
  --> StatusCode.AMBIGUOUS triggered
  --> Safe-halt with StatusCode.GEN_STOP_AMBIGUOUS
```

---

## 11. Competing Alternative Explanations

| Hypothesis | Proposed Mechanism | Empirical Finding | Causal Verdict |
|:---|:---|:---|:---:|
| **H1: Distinct Structures, Coincidental Tie** | Assemblies 5 and 6 have different cells but coincidentally computed identical scores. | Disproved. $A_5$ and $A_6$ share all 9 cells ($A_5 \Delta A_6 = \emptyset$). | **REFUTED** |
| **H2: Duplicate FORM Birth** | FORM stage created two identical assemblies at birth. | Disproved. At birth (Root 8), $A_5$ and $A_6$ had 0 cells in common ($\text{Jaccard} = 0.0$). | **REFUTED** |
| **H3: Ledger Attestation Collision** | Ledger attestation failed or confused token envelopes. | Disproved. Both assemblies recorded 46 confirmed roots for `<EOS>` with valid distinct outbox entries. | **REFUTED** |
| **H4: MERGE Never Evaluated Pair** | Pair $(5, 6)$ was never checked by `_try_merge_pair` due to ordering, cooldown, or capacity. | Disproved. Pair was evaluated in 49 consecutive roots; failed exclusively on `between_strength = 0.0`. | **REFUTED** |

---

## 12. Candidate Repair Strategies & Architectural Risks

The forensic findings point to three potential architectural interventions for the upcoming R2-B02 design phase:

### Candidate Strategy 1: Correct Empty Exclusive-Set Handling in MERGE (Recommended)
- **Concept:** When $\text{Jaccard}(A, B) \ge \Theta_{\text{merge}}$ and either exclusive set is empty ($A \subseteq B$ or $A = B$), `between_strength` should reflect total mutual support (or bypass `THETA_OB`), because identical assemblies by definition have maximal mutual support ($1.0$), not zero ($0.0$).
- **Defect Addressed:** Directly removes the artificial `between_strength = 0.0` blocker.
- **Architectural Risks:**
  - *ID Selection:* A deterministic rule must dictate which assembly ID survives (e.g. $\min(\text{ID}_A, \text{ID}_B)$) and which is archived.
  - *Ledger Aliasing:* The peripheral ledger must alias or transfer attestations of the archived ID to the surviving ID so historical evidence is not orphaned.
  - *Generation Bump:* The surviving assembly's generation must increment cleanly without violating immutability or outbox ordering.

### Candidate Strategy 2: Pre-Convergence GROW / FORM Invariant
- **Concept:** Inhibit dual triangle formation within the same event if unassigned emitters have high cross-mutual support, or prevent GROW from adding cells that cause $\text{Jaccard} \ge \Theta_{\text{merge}}$.
- **Defect Addressed:** Prevents exact duplicate formation from occurring in the first place.
- **Architectural Risks:**
  - Alters core neural learning dynamics in Core §9.1 and §9.2.
  - High risk of regression on other token sequences where multiple independent assemblies legitimately emerge from the same token.

### Candidate Strategy 3: Readout Deduplication Gate
- **Concept:** In `evaluate_full_vs_control_readout` or `generate_episode`, collapse candidate assemblies that have identical membership tuples before computing score margin.
- **Defect Addressed:** Prevents identical assemblies from colliding at the readout margin check.
- **Architectural Risks:**
  - Circumvents Core assembly lifecycle; leaves duplicate assemblies proliferating unchecked in $W$.
  - Leaks assembly structural inspection into readout evaluation, violating separation of concerns.

---

## 13. Full Regression Evidence

All frozen test suites were executed on `investigation/r2-b01-assembly-forensics` to confirm zero regression and complete baseline stability:

### 1. Full Master Regression Suite
```bash
python -m pytest tests/ -q
```
**Result:** `192 passed in 35.66s` (100% PASS).

### 2. Forensic Test Suite
```bash
python -m pytest tests/forensics/ -v
```
**Result:** `9 passed in 14.24s` (100% PASS).
- `test_f01_02_scenario_1_pre_commit_failure_zero_attestations`: PASSED
- `test_f01_02_scenario_2_post_commit_dispatch_partial_failure`: PASSED
- `test_f01_02_scenario_3_completed_root_cannot_abort`: PASSED
- `test_f01_02_scenario_4_post_commit_failure_readiness_barrier`: PASSED
- `test_f01_02_scenario_5_reconciliation_retry_and_idempotency`: PASSED
- `test_f01_task5_strengthened_cold_start_learning_from_zero`: PASSED
- `test_f01_task6_reencoded_eos_discrepancy_and_outbox_bypass`: PASSED
- `test_f01_task6_canonical_eos_learning_and_multistep_rollout`: PASSED
- `test_f01_persistence_not_implemented`: PASSED

---

## 14. Explicit Unresolved Questions

1. **Surviving Assembly Identity:** When Assemblies 5 and 6 merge, does Assembly 5 survive because it has the lower ID, or does the assembly with the higher attestation count survive?
2. **Peripheral Ledger Attestation Migration:** If Assembly 6 is marked `AssemblyStatus.ARCHIVED`, how should `SurfaceReadoutLedgerV1` treat lookups for Assembly 6? Should the ledger maintain an explicit alias mapping `alias[6] -> 5`?
3. **Outbox Notification Contract on MERGE:** When a merge occurs during `END_EXPOSURE`, what outbox notifications must be emitted to the ledger? Does the merge event itself produce an outbox attestation update?

---

## 15. Recommended Scope for R2-B02 Design Contract

The future R2-B02 design contract should be strictly bounded to:
1. **Mathematical correction of `_try_merge_pair()`:**
   - Formalize the predicate for empty exclusive sets: when $\text{Jaccard}(A, B) \ge \Theta_{\text{merge}}$ and $\min(|A \setminus B|, |B \setminus A|) = 0$, define between-support as $1.0$ (or bypass the cross-support check).
2. **Deterministic merge reconciliation in $W$:**
   - Specify surviving ID selection, member set union, status transition (`ARCHIVED`), and cooldown application.
3. **Peripheral ledger attestation reconciliation:**
   - Specify whether the peripheral ledger aliases merged assembly IDs or aggregates evidence counts across identical structural generations.
4. **Hard Boundary:**
   - Zero changes to neural equations (Core §2–§8).
   - Zero changes to LLA, transaction boundaries, or outbox dispatch architecture (R2-A01).
