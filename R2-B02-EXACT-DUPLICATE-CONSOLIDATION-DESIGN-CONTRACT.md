# DGCA NEXT V2 — R2-B02 DESIGN CONTRACT

## Exact-Duplicate Assembly Consolidation — Formal Design Contract
### Normatively Reconciled Baseline under R2-B02-C01

| Parameter | Specification |
| :--- | :--- |
| **Document Version** | `2.0.0-normative-reconciled` |
| **Authoritative Baseline** | `faf361b6b95de6287b466eb1dc524ea49c732635` (`main`) |
| **Investigation Branch** | `investigation/r2-b01-assembly-forensics` |
| **Starting HEAD** | `2ea323f3afbf110028641dcd5349e61629ee9183` |
| **Accepted Forensic Baseline** | `205efa0e664dc26f31f131d5efc19ac37b3eb95d` (R2-B01 Closeout) |
| **Target Operators** | Core §2.0 Operator 4 (`MERGE`), Core §9.4 (`SurfaceReadoutLedgerV1`), `src/dgca/core/assembly.py` |
| **Status** | **NORMATIVELY RECONCILED — AWAITING FINAL DESIGN FREEZE** |

---

## 1. Scientific Problem Statement

The R2-B01 forensic investigation established the causal chain leading to catastrophic readout collisions in DGCA:
1. Disjoint neural assemblies ($A_5$ seeded by root `عطش` and $A_6$ seeded by root `شرب`) independently underwent synaptic growth (`GROW`) during Root 9 (`النسر يشرب ماء`).
2. Both assemblies recruited the exact same five committed language cells (`10646, 10915, 11153, 11583, 12116`), converging to an identical 8-cell structural composition:
   $$\text{Members}(A_5) \equiv \text{Members}(A_6) = \{10646, 10915, 11153, 11583, 12053, 12061, 12116, 12118\}$$
3. At the close of Root 9, the structural `MERGE` operator evaluated pair $(A_5, A_6)$. Under the frozen Core §2.0 specification:
   - Exclusive member sets are empty: $\text{Excl}(A_5) = \emptyset$, $\text{Excl}(A_6) = \emptyset$.
   - The mutual support between exclusive sets evaluates over an empty Cartesian product $\emptyset \times \emptyset$.
   - The frozen implementation defaults this undefined quantity to $0.0$.
   - Because $0.0 < \Theta_{\text{ob}} = 0.35$, the merge operation was **rejected**.
4. Both assemblies remained active (`LIVE`), resulting in dual structural identical attractors.
5. In subsequent exposure and readout, both assemblies produced identical continuous activation scores ($S_5 \equiv S_6$), triggering a collision failure in candidate resolution (`StatusCode.READOUT_AMBIGUOUS`).

### Separation of Scientific Gates
To prevent normative ambiguity, the architecture differentiates four distinct scientific gates:
1. **Structural Duplicate Elimination:** Core neural operator consolidating identical assemblies into a single survivor ($\min(a, b)$).
2. **New-Generation Attestation Recovery:** Peripheral ledger requirement that the new structural generation be confirmed by at least two distinct external roots (`MIN_ATTESTED_EXTERNAL_ROOTS = 2`).
3. **Neural Winner Selection:** Core dynamics selection of the winning assembly based solely on neural activation overlap; zero consultation of peripheral ledger.
4. **Language Generation Success:** Peripheral emission of grounded surface tokens upon successful attestation resolution.

Solving Gate 1 (structural duplicate elimination) is necessary for Gate 4, but does not instantly satisfy Gate 2 or Gate 4 without subsequent qualifying external grounding.

---

## 2. Frozen-Law Analysis

### Mathematical & Structural Decomposition
In `DGCA_CORE_RC4_1.md` §2.0 (Operator 4, `MERGE`), the merge condition between assemblies $A$ and $B$ requires satisfying three sequential structural predicates:

1. **Jaccard Overlap:**
   $$J(A, B) = \frac{|A \cap B|}{|A \cup B|} \ge \Theta_{\text{merge}} \quad (\Theta_{\text{merge}} = 0.80)$$
2. **Capacity Bounds:**
   $$|A \cup B| \le K_{\text{max}} \quad (K_{\text{max}} = 16)$$
3. **Exclusive-Set Mutual Support:**
   $$\text{BetweenStrength}(A, B) = \frac{1}{|A \setminus B| \cdot |B \setminus A|} \sum_{i \in A \setminus B} \sum_{j \in B \setminus A} R^B_{i, j}(W) \ge \Theta_{\text{ob}} \quad (\Theta_{\text{ob}} = 0.35)$$

### Why the Boundary Condition Exists
The between-strength predicate $\text{BetweenStrength}(A, B) \ge \Theta_{\text{ob}}$ was designed to ensure that the unshared (exclusive) cells of two assemblies exhibit strong reciprocal synaptic support before fusing them into a single attractor. If two assemblies share 80% of their cells, they should only merge if their distinct 20% peripheral cells are mutually bonded.

### Where the Boundary Condition Fails
When two assemblies converge to identical membership sets ($A = B$):
- Shared overlap is 100%: $J(A, B) = 1.0 \ge \Theta_{\text{merge}}$.
- Size bound is satisfied: $|A \cup B| = |A| \le K_{\text{max}}$.
- Exclusive sets are empty: $A \setminus B = \emptyset$ and $B \setminus A = \emptyset$.
- The denominator $|A \setminus B| \cdot |B \setminus A| = 0 \times 0 = 0$.

In [src/dgca/core/assembly.py](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L538-L551):
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
Because `excl_a` and `excl_b` are empty, `between_strength` is assigned `0.0`. Consequently, `0.0 < THETA_OB` triggers an immediate merge rejection.

### The Attestation Law (Core §9.4)
Under Core §9.4 and [src/dgca/peripheral/readout_ledger.py](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/peripheral/readout_ledger.py#L20-L22):
$$\text{MIN\_ATTESTED\_EXTERNAL\_ROOTS} = 2$$
A single external exposure **cannot** attest an assembly generation. Attestation strictly requires ten normative conditions:
1. **Root Diversity:** `len(confirmed_roots) >= 2` across distinct completed external roots (`root_id` distinct).
2. **Assembly Identity:** Matching `assembly_id`.
3. **Generation Matching:** Matching `structural_generation`.
4. **Canonical Surface & Feature Bundle:** Matching `surface_utf8_nfc` and `feature_bundle_digest`.
5. **Marker Consistency:** Matching `marker` (`Marker.EOS` when applicable).
6. **No Unresolved Conflicts:** No conflicting candidate row for `(surface, marker)` with differing bundle digest (`LG-T08`).
7. **Legal Event-Time Coverage & Freshness:** Event-time coverage $C_t \ge \rho_{\text{core}} = 0.70$ and freshness $M_{\text{fresh}} \ge \Theta_{\text{fresh}}$.
8. **Pre-Existing Live State:** Assembly was already `LIVE` before the witnessed event (no post-close witness claims).
9. **Generation Stability:** Unchanged generation across the entire root required for outbox notification.
10. **Zero Retroactive Attestation:** No retroactive attestation after structural mutation (`MERGE` or `GROW`).

---

## 3. Comparative Evaluation of Alternative Semantics

### Alternative A: Explicit Exact-Duplicate Structural Branch (Accepted)
Introduce an explicit semantic branch in Core §2.0 Operator 4:
If two live assemblies have identical membership sets ($A \equiv B$), they are recognized as exact structural duplicates and bypass the exclusive-set mutual-support test.

$$\text{Condition: } A \equiv B \iff A \setminus B = \emptyset \land B \setminus A = \emptyset$$

### Alternative B: Defined Mathematical Convention for Empty Exclusive Sets
Define by mathematical convention that the mean of an empty set of mutual-support values is $1.0$ (or $\infty$):
$$\text{If } |A \setminus B| = 0 \lor |B \setminus A| = 0 \implies \text{BetweenStrength}(A, B) \equiv 1.0$$

### Rigorous Comparative Analysis

| Dimension | Alternative A: Explicit Duplicate Branch | Alternative B: Convention $\text{BetweenStrength} = 1.0$ |
| :--- | :--- | :--- |
| **Mathematical Soundness** | **High.** Leaves the cross-support formula untouched; treats identity as a structural category. | **Low.** Assigns a fabricated continuous value to an undefined empty set. |
| **Semantic Clarity** | **High.** Explicitly models duplicate elimination. | **Low.** Conflates "no exclusive cells" with "infinitely strong exclusive cells". |
| **Leakage Risk** | **Zero.** Strictly restricted to $A \equiv B$. | **High.** If $A \subset B$, one exclusive set is empty, which would improperly bypass support for the remaining exclusive cells. |
| **Specification Cleanliness** | **Clean.** Preserves existing formulas for partial overlap. | **Fragile.** Requires re-defining division by zero in formal learning laws. |

### Design Decision & Justification
**Alternative A is formally accepted.** Exact duplicates are structurally identical attractors. Demanding mutual support between non-existent exclusive cells is a category error. Alternative A resolves this directly at the structural boundary without introducing artificial mathematical fictions.

---

## 4. Exact Eligibility Predicate (Proposed Normative Amendment)

### Proposed Core §2.0 Text Amendment
In `DGCA_CORE_RC4_1.md` §2.0, Item 4 (`MERGE`), replace the between-strength evaluation with:

> **Operator 4: MERGE**
> Live assembly pairs $(A, B)$ with $A.\text{id} < B.\text{id}$ are evaluated ascending by ID.
> 
> A pair $(A, B)$ is eligible for consolidation if and only if:
> 1. Both $A$ and $B$ are `LIVE` and neither is in merge/split cooldown ($T_c = 200$ completed external events).
> 2. Jaccard overlap satisfies $J(A, B) = \frac{|A \cap B|}{|A \cup B|} \ge \Theta_{\text{merge}} = 0.80$.
> 3. Union size satisfies $|A \cup B| \le K_{\text{max}} = 16$.
> 4. **Consolidation Support Gate:**
>    - **Branch 4a (Exact Structural Duplicate):** If $\text{Members}(A) \equiv \text{Members}(B)$ (i.e. $A \setminus B = \emptyset$ and $B \setminus A = \emptyset$), the pair is immediately eligible for consolidation; the mutual-support gate is satisfied.
>    - **Branch 4b (Partial Overlap):** If $A \setminus B \ne \emptyset$ and $B \setminus A \ne \emptyset$, the between-strength must satisfy:
>      $$\text{BetweenStrength}(A, B) = \frac{1}{|A \setminus B| \cdot |B \setminus A|} \sum_{i \in A \setminus B} \sum_{j \in B \setminus A} R^B_{i, j}(W) \ge \Theta_{\text{ob}} = 0.35$$
> 5. **Cell Membership & Keep Guards:** For every cell $x \in A \cup B$, the live assembly count after archiving $B$ does not exceed $M_{\text{max}} = 12$, and keep guards $\text{check\_maintain\_keep\_guards}(x, A \cup B)$ pass.

### Mathematical Formulation of the Predicate

$$\mathcal{P}_{\text{merge}}(A, B) = \mathcal{G}_{\text{status}}(A, B) \land \mathcal{G}_{\text{cooldown}}(A, B) \land \mathcal{G}_{\text{cap}}(A, B) \land \mathcal{G}_{\text{overlap}}(A, B) \land \mathcal{G}_{\text{support}}(A, B) \land \mathcal{G}_{\text{guards}}(A, B)$$

Where:
$$\mathcal{G}_{\text{status}}(A, B) = [A.\text{status} = \text{LIVE} \land B.\text{status} = \text{LIVE}]$$
$$\mathcal{G}_{\text{cooldown}}(A, B) = [\neg \text{InCooldown}(A) \land \neg \text{InCooldown}(B)]$$
$$\mathcal{G}_{\text{cap}}(A, B) = [|A \cup B| \le K_{\text{max}}]$$
$$\mathcal{G}_{\text{overlap}}(A, B) = [J(A, B) \ge \Theta_{\text{merge}}]$$
$$\mathcal{G}_{\text{support}}(A, B) = 
\begin{cases} 
\text{True} & \text{if } A \setminus B = \emptyset \land B \setminus A = \emptyset \quad \text{(Branch 4a: Exact Duplicate)} \\
\text{BetweenStrength}(A, B) \ge \Theta_{\text{ob}} & \text{if } A \setminus B \ne \emptyset \land B \setminus A \ne \emptyset \quad \text{(Branch 4b: Partial Overlap)} \\
\text{False} & \text{otherwise (e.g. proper subsets)}
\end{cases}$$
$$\mathcal{G}_{\text{guards}}(A, B) = \bigwedge_{x \in A \cup B} [M_{\text{live}}(x \mid B \to \text{ARCHIVED}) \le M_{\text{max}} \land \text{KeepGuard}(x, A \cup B)]$$

---

## 5. Survivor Identity, Generation Advancement, and Lifecycle Semantics

### Identity Assignment (Lower-ID Survivor)
- **Surviving Assembly:** $A_{\text{surv}} = \min(A, B)$. Its identifier $A_{\text{surv}}.\text{id}$ is permanently retained.
- **Archived Assembly:** $A_{\text{arch}} = \max(A, B)$. Its identifier $A_{\text{arch}}.\text{id}$ transitions permanently to `AssemblyStatus.ARCHIVED`.
- **Identity Invariant:** Lower numeric ID is strictly authoritative. No selection based on peripheral attestation maturity, activation count, or timestamp is permitted.

### Structural Generation Advancement
Consolidation alters the structural composition and membership context. Generation advancement follows the exact frozen production semantics of [`_try_merge_pair`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L564-L569):
$$A_{\text{surv}}.\text{structural\_generation} \leftarrow A_{\text{surv}}.\text{structural\_generation} + 1$$
$$A_{\text{arch}}.\text{structural\_generation} \leftarrow A_{\text{arch}}.\text{structural\_generation} + 1$$

> [!IMPORTANT]
> The generation increment `survivor.structural_generation += 1` must be strictly preserved. It must **not** be replaced with `max(gen_a, gen_b) + 1`. Both survivor and archived assemblies advance their structural generation by exactly 1 upon MERGE.

### Reverse Index Updates (`assemblies_by_member`)
In `WState.assemblies_by_member`:
- For every cell $c \in \text{Members}(A_{\text{surv}})$:
  - $A_{\text{arch}}.\text{id}$ is removed from the set of active assemblies.
  - The cell's active membership count decreases by exactly 1:
    $$M_{\text{live}}(c) \leftarrow M_{\text{live}}(c) - 1$$
  - This strictly respects the cell membership cap $M_{\text{max}} = 12$.

### Merge Cooldown Enforcement
Consolidation triggers the standard merge cooldown to prevent cascading structural instability:
$$A_{\text{surv}}.\text{last\_mutation\_close\_serial} \leftarrow W.\text{close\_serial}$$
$$A_{\text{surv}}.\text{last\_merge\_split\_close\_serial} \leftarrow W.\text{completed\_external\_events\_count}$$
$$A_{\text{arch}}.\text{last\_mutation\_close\_serial} \leftarrow W.\text{close\_serial}$$
$$A_{\text{arch}}.\text{last\_merge\_split\_close\_serial} \leftarrow W.\text{completed\_external\_events\_count}$$
During the subsequent $T_c = 200$ completed external events, $A_{\text{surv}}$ is ineligible for any further `MERGE` or `SPLIT` operations.

### Reporting & Transaction Notifications
Reporting strictly conforms to frozen schemas in [src/dgca/lifecycle/exposure_tx.py](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lifecycle/exposure_tx.py) and [src/dgca/core/assembly.py](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L55-L65):
- `AssemblyEndReport.merged_pairs` records the consolidated pair: `((a_id, b_id),)`.
- Peripheral outbox notifications use the standard `OutboxNotificationV1` schema emitted after commit.
- **No unauthorized notification schemas:** `AssemblyMutationNotification` does not exist in production and is unauthorized. No new transaction status codes or schema extensions are permitted.

---

## 6. Verified Baseline & Counterfactual Timeline

The following table compares the verified frozen baseline with the counterfactual consolidation trajectory:

| Curriculum Event | Baseline Production (Measured) | Counterfactual Consolidation (Predicted) | Status / Invariant |
| :--- | :--- | :--- | :--- |
| **Root 8 Close** | $A_5$ born (Gen 1, size 3); $A_6$ born (Gen 1, size 3). | $A_5$ born (Gen 1, size 3); $A_6$ born (Gen 1, size 3). | Frozen Law (Measured). |
| **Root 9 GROW** | Both recruit 5 cells (`10646, 10915, 11153, 11583, 12116`). Generations: $1 + 5 = 6$. Both Gen 6 (size 8). | Both recruit 5 cells. Generations: $1 + 5 = 6$. Both Gen 6 (size 8). | Frozen Law (Measured). |
| **Root 9 MERGE** | MERGE fails ($0.0 < \Theta_{\text{ob}}$). Both remain `LIVE` at Gen 6. | Branch 4a triggers. $A_5$ survives ($6 + 1 = 7$); $A_6$ archived ($6 + 1 = 7$). | Core §2.0 Operator 4 (Predicted). |
| **Root 10 GROW** | Unmodified baseline adds cell `12117` to both. Both become Gen 7 (size 9). | Cell `12117` added to $A_5$. Survivor generation increments: $7 + 1 = 8$ (size 9). | First stable post-merge generation is **Gen 8** (Predicted). |
| **Root 10 MERGE** | MERGE fails. Both remain `LIVE` at Gen 7. | Ineligible (Asm 6 archived; Asm 5 in $T_c = 200$ cooldown). | Cooldown Protection (Predicted). |
| **Root 10–56 Readout** | Dual identical attractors ($A_5, A_6$) score identically; `READOUT_AMBIGUOUS` collision. | Single attractor ($A_5$ Gen 8). Unattested until 2 external roots confirm. Fail-closed `GEN_STOP_READOUT_UNKNOWN`. | Collision Eliminated; Attestation Gate Active (Predicted). |
| **1st Eligible Ext. Root** | Both fire on `<EOS>`; collision halts readout. | $A_5$ Gen 8 fires on `<EOS>`; ledger records 1st confirmation (`external_count = 1 < 2`). Readout remains fail-closed `GEN_STOP_READOUT_UNKNOWN`. | Attestation Condition 1 Enforced (Predicted). |
| **2nd Eligible Ext. Root** | Collision persists. | $A_5$ Gen 8 fires on `<EOS>`; ledger records 2nd confirmation (`external_count = 2 \ge 2`). $A_5$ Gen 8 becomes **attested**! | `MIN_ATTESTED_EXTERNAL_ROOTS = 2` Satisfied (Predicted). |
| **Subsequent Readout** | Collision persists permanently. | Autonomous generation resolves $A_5$ Gen 8 to `<EOS>` cleanly with positive margin (`StatusCode.OK`). | Readout Recovery Achieved (Predicted). |

> [!NOTE]
> All counterfactual entries are formally labeled as **PREDICTED**, pending authorization of implementation and verification under R2-B03.

---

## 7. Peripheral Ledger Safety and Re-Attestation Lifecycle

Under Core §9.4 and [src/dgca/peripheral/readout_ledger.py](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/peripheral/readout_ledger.py), the readout ledger indexes candidate rows strictly by:
$$(\text{assembly\_id}, \text{structural\_generation})$$

```
                +-------------------------------------------------------+
                | Consolidation at Root 9 & Growth at Root 10:          |
                | Root 9: Asm 5 (Gen 6) -> Gen 7; Asm 6 -> Gen 7 (ARCH) |
                | Root 10: Asm 5 (Gen 7) + cell 12117 -> Gen 8          |
                +-------------------------------------------------------+
                                           |
                                           v
        +---------------------------------------------------------------+
        | Ledger State Post-Root 10:                                    |
        | - Row (5, 6): Historical pre-merge evidence [STALE]           |
        | - Row (6, 6): Historical archived-ID evidence [ARCHIVED]       |
        | - Row (5, 7): Intermediate transient generation [STALE]       |
        | - Row (5, 8): EMPTY (0 confirmations registered)              |
        +---------------------------------------------------------------+
                                           |
                +--------------------------+----------------------------+
                |                                                       |
                v                                                       v
+------------------------------------+         +------------------------------------+
| Autonomous Readout Query (Gen 8):  |         | Subsequent External Root 1:        |
| - Neural winner: Asm 5 (Gen 8)     |         | - Model exposed to root with <EOS> |
| - Query ledger for key (5, 8)      |         | - Asm 5 (Gen 8) fires on <EOS>     |
| - Result: 0 candidate rows         |         | - Outbox emits notification        |
| - Ledger: StatusCode.READOUT_UNKNOWN|        | - Ledger records Root 1 (count=1)  |
| - Generator maps failure code:     |         | - Count 1 < 2 -> NOT YET ATTESTED  |
|   GEN_STOP_READOUT_UNKNOWN         |         +------------------------------------+
| - Emission: HALTED (FAIL-CLOSED)   |                                  |
+------------------------------------+                                  v
                                               +------------------------------------+
                                               | Subsequent External Root 2:        |
                                               | - Distinct root exposed with <EOS> |
                                               | - Asm 5 (Gen 8) fires on <EOS>     |
                                               | - Ledger records Root 2 (count=2)  |
                                               | - Count 2 >= 2 -> ATTESTED!        |
                                               | - Subsequent Readout: SUCCESS (OK) |
                                               +------------------------------------+
```

### Invalidation & Safety Laws
1. **Strict Generation Invalidation:**
   Old-generation attestations (Gen 6 or 7) must **never** be matched for new-generation queries (Gen 8):
   $$\text{get\_candidate\_rows}(5, 8) \equiv ()$$
   Even though Assembly 5 had prior evidence for `<EOS>` at Gen 6, that evidence was witnessed on an 8-cell assembly prior to consolidation and subsequent growth. The post-merge entity is a new structural generation.
2. **Zero Retroactive Witnessing:**
   The surviving assembly cannot backdate or synthesize attestation. An attestation can only be registered when a genuine, live external event activates Assembly 5 at Gen 8.
3. **No Archived-ID Aliasing:**
   The readout ledger must **never** resolve an alias from $A_{\text{arch}}$ to $A_{\text{surv}}$:
   $$\text{Resolve}(6) \ne 5$$
   Creating an alias violates transactional immutability and corrupts audit trails. Assembly 6 is archived and permanently inert.
4. **Readout Failure Code Mapping:**
   If autonomous generation queries an unattested winner assembly:
   - Neural competition selects Assembly 5 as the sole winner based on activation overlap.
   - Ledger query `resolve_readout(5, 8)` finds zero rows or a single row with `external_count < 2`.
   - Ledger returns `StatusCode.READOUT_UNKNOWN`.
   - Generator function [`_map_ledger_failure_to_gen_stop()`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/generator.py#L76-L88) maps this to `StatusCode.GEN_STOP_READOUT_UNKNOWN`.
   - **No fallback to lower-ranked printable assemblies:** Under Core §9.3 and `LG-T12`, peripheral lookup is strictly evaluated on the neural winner. If the winner is unattested, generation halts fail-closed.
5. **Attestation Requirement:**
   Attestation strictly requires $\ge 2$ independent qualifying external roots (`MIN_ATTESTED_EXTERNAL_ROOTS = 2`).

---

## 8. Transactional Safety and Rollback Guarantees

The proposed amendment introduces zero modifications to transactional architecture:

### Ordinary MERGE Ineligibility
- If a candidate pair is ineligible (e.g., $J < 0.80$, capacity exceeded, keep guard failure, or cooldown active):
- `_try_merge_pair()` returns `False`.
- The merge loop simply proceeds to the next candidate pair in the active pass.
- **No transaction abort occurs.** The pipeline continues normally under frozen rules.

### Exceptional Pre-Publication Failure
- If an unhandled exception or critical invariant violation occurs in shadow execution:
- The transaction manager triggers `ABORT`.
- Uncommitted shadow assembly state is discarded.
- Under R2-A01, sensory states legally committed during `OPEN` are preserved; uncommitted shadow mutations are discarded. Pre-BEGIN state is not wiped if `OPEN` completed valid sensory commitments.

### Post-Commit Outbox Delivery Failure
- Once `END_EXPOSURE` commits, neural state transitions are durable and permanent.
- If outbox notification dispatch to the peripheral ledger fails, the committed neural state is **never rolled back**.
- Idempotent outbox reconciliation retains pending notifications for replay without side effects.

---

## 9. Counterexamples and Excluded Cases

| Case | Structure | Evaluation | Merge Outcome | Reason |
| :--- | :--- | :--- | :--- | :--- |
| **Case 1: Proper Subsets** | $A \subset B$ ($|A|=4, |B|=5$) | $A \setminus B = \emptyset$, but $B \setminus A = \{c_5\} \ne \emptyset$. | **REJECTED** | Fails Branch 4a condition ($B \setminus A \ne \emptyset$). Evaluates under Branch 4b, where empty $A \setminus B$ yields `between_strength = 0.0 < THETA_OB`. Prevents subset absorption. |
| **Case 2: Low-Jaccard Overlap** | $|A \cap B| = 6$, $|A \cup B| = 10$ | $J(A, B) = 0.60 < \Theta_{\text{merge}} = 0.80$. | **REJECTED** | Fails overlap threshold $\Theta_{\text{merge}}$ prior to support gate. |
| **Case 3: Weak Exclusive Support** | $|A|=8, |B|=8$, $|A \cap B|=7$ | $|A \setminus B|=1, |B \setminus A|=1$, $R^B = 0.20 < \Theta_{\text{ob}} = 0.35$. | **REJECTED** | Evaluates under Branch 4b; fails mutual-support threshold. |
| **Case 4: Cooldown Violation** | $A \equiv B$, but $A$ merged 50 events ago | $W.\text{completed\_events} - A.\text{last\_merge\_serial} = 50 < T_c = 200$. | **REJECTED** | Cooldown guard $\mathcal{G}_{\text{cooldown}}$ fails before predicate evaluation. |
| **Case 5: Cell Membership Overflow** | $A \equiv B$, member $x$ in 12 live assemblies | Live count after archiving $B$: $12 - 1 = 11 \le 12$. If union adds any cell exceeding 12: | **REJECTED** | Capacity guard $\mathcal{G}_{\text{guards}}$ fails. |

---

## 10. Scientific Acceptance Test Matrix

The acceptance suite consists of seven primary validation experiments and nine negative tests:

### Primary Validation Experiments

| Test ID | Experiment Name | Stimulus / Configuration | Expected Empirical Outcome | Invariant Verified |
| :--- | :--- | :--- | :--- | :--- |
| **EXP-B02-01** | Exact Duplicate Consolidation | Replay Root 9 where Assemblies 5 & 6 have converged to identical 8 cells. | $A_5$ remains `LIVE` (Gen 7 post-merge); $A_6$ becomes `ARCHIVED` (Gen 7); single assembly published; cooldown applied. | Core §2.0 Operator 4 (Branch 4a). |
| **EXP-B02-02** | Partial Overlap Invariance | Synthetic pair with 8 shared cells, 2 exclusive cells, $R^B = 0.50 \ge \Theta_{\text{ob}}$. | Pair merges legally under Branch 4b; between-strength evaluated accurately. | Core §2.0 Operator 4 (Branch 4b). |
| **EXP-B02-03** | Proper Subset Rejection | Synthetic pair with $A \subset B$ ($|A|=4, |B|=5$). | Merge rejected with `between_strength = 0.0 < THETA_OB`. | Prevention of subset absorption. |
| **EXP-B02-04** | Ledger Generation Safety | Query readout immediately after Root 9 consolidation without qualifying external exposure. | Surviving $A_5$ (Gen 7/8) has 0 ledger attestations; readout halts fail-closed with `GEN_STOP_READOUT_UNKNOWN`. | Core §9.4 ledger generation barrier. |
| **EXP-B02-05** | Post-Merge Re-Attestation | Expose consolidated model to 2 independent qualifying external roots containing `<EOS>`. | 1st root yields `external_count = 1` (readout remains unknown); 2nd root yields `external_count = 2` (attested); subsequent readout emits `<EOS>` cleanly. | Core §9.4 (`MIN_ATTESTED_EXTERNAL_ROOTS = 2`). |
| **EXP-B02-06** | 56-Root Curriculum Replay | Full 56-root curriculum with consolidation active at Root 9. | Empirical evaluation across all 56 roots; dual-replay state equality; optional extended-curriculum condition to evaluate re-attestation. | Curriculum determinism and non-interference. |
| **EXP-B02-07** | Transaction Fault Semantics | Evaluate ordinary ineligibility (returns `False`) vs injected pre-publication failure. | Ineligibility continues pipeline; injected failure discards shadow state while preserving legal OPEN sensory states; committed neural state durable. | Transaction failure boundaries. |

### Negative Tests

| Test ID | Description | Stimulus / Condition | Expected Negative Result |
| :--- | :--- | :--- | :--- |
| **EXP-B02-NEG-01** | Single External Confirmation | Model exposed to exactly 1 external root post-merge. | `external_count = 1 < 2`; ledger lookup returns `READOUT_UNKNOWN`; generator halts with `GEN_STOP_READOUT_UNKNOWN`. |
| **EXP-B02-NEG-02** | Repeated Observations Within Root | Model witnesses `<EOS>` multiple times within the same external root. | Ledger deduplicates by `root_id`; `len(confirmed_roots) == 1`; attestation rejected. |
| **EXP-B02-NEG-03** | Old-Generation Evidence Reuse | Readout queried at Gen 8 with pre-existing attestations at Gen 6 or 7. | Strict key mismatch `(5, 8) != (5, 6)`; 0 rows returned; generation invalidation enforced. |
| **EXP-B02-NEG-04** | Same-Surface / Differing-Bundle Conflict | Injected conflicting feature bundle for same surface string. | Ledger detects bundle divergence (`LG-T08`); returns `READOUT_AMBIGUOUS_PENDING`; readout halts fail-closed. |
| **EXP-B02-NEG-05** | Proper Subset Absorption Attempt | Candidate pair with $A \subset B$ ($|A|=4, |B|=5$). | Predicate returns `False`; pair remains unmerged; no subset absorption. |
| **EXP-B02-NEG-06** | Cooldown Bypass Attempt | Identical pair evaluated while $T_c < 200$ events since last mutation. | Predicate returns `False`; consolidation blocked during cooldown. |
| **EXP-B02-NEG-07** | Archived-ID Aliasing Attempt | Query peripheral readout for archived ID $A_6$. | Ledger lookup returns empty/unknown; zero alias resolution to $A_5$. |
| **EXP-B02-NEG-08** | Peripheral Selection Leakage | Ledger populated with attestations; evaluate neural winner selection. | Neural competition strictly ignores ledger rows; winner determined solely by continuous activation overlap (`LG-T12`). |
| **EXP-B02-NEG-09** | Ordinary Ineligibility Pipeline Continuity | Rejected pair in Stage 4. | `_try_merge_pair()` returns `False`; next pair in list is evaluated; transaction does not abort. |

---

## 11. Implementation Boundaries and Code Touchpoints

When authorized, implementation will be strictly confined to:

### Permitted Modifications
1. `src/dgca/core/assembly.py`:
   - In `_try_merge_pair()`: Insert the Branch 4a exact-duplicate check before exclusive-set cross-product evaluation:
     ```python
     excl_a = sorted(set_a - set_b)
     excl_b = sorted(set_b - set_a)
     if not excl_a and not excl_b:
         # Branch 4a: Exact Structural Duplicate consolidation (Core §2.0 Operator 4)
         between_strength_passed = True
     else:
         # Branch 4b: Partial Overlap cross-support evaluation
         if not excl_a or not excl_b:
             between_strength = 0.0
         else:
             cross_vals = [
                 compute_mutual_support_r_b(i, j, w)
                 for i in excl_a
                 for j in excl_b
             ]
             between_strength = sum(cross_vals) / float(len(cross_vals))
         between_strength_passed = (between_strength >= THETA_OB)

     if not between_strength_passed:
         return False
     ```

### Forbidden Modifications
- **Forbidden:** No modifications to `FORM`, `GROW`, `MAINTAIN`, or `SPLIT`.
- **Forbidden:** No modification to `src/dgca/peripheral/readout_ledger.py` or `src/dgca/peripheral/outbox.py`.
- **Forbidden:** No modification to `TransactionPublicationView` or `ExposureTransactionManager` in `src/dgca/lifecycle/exposure_tx.py`.
- **Forbidden:** No modification to `src/dgca/core/generator.py` winner selection or fallback logic.
- **Forbidden:** No introduction of `src/dgca/core/transaction.py` (nonexistent path).
- **Forbidden:** No new notification schemas (e.g. `AssemblyMutationNotification`) or custom transaction status codes.
- **Forbidden:** No synthesis of artificial ledger attestations or cross-generation evidence transfer.

---

## 12. Scientific Limitations & Lead Engineer Review

### Explicit Scientific Boundaries
Exact-duplicate consolidation addresses the specific causal defect of identical structural duplicates. It does **not** provide blanket guarantees:
1. **No Guarantee of Immediate Generation Success:** Consolidation eliminates duplicate collisions, but the surviving assembly enters a new structural generation (Gen 7 post-merge, Gen 8 post-Root 10). Autonomous generation halts with `GEN_STOP_READOUT_UNKNOWN` until at least two qualifying external roots ground the new generation.
2. **No Guarantee of Total Readout Unambiguity:** Future distinct assemblies could theoretically converge or collide if learning dynamics produce overlapping attractors.
3. **No Immediate Generation Stability:** Survivor generation advances upon merge ($6 \to 7$) and advances again if subsequent growth occurs at Root 10 ($7 \to 8$). Generation stability requires completion of growth phases.
4. **Curriculum Independence:** A fixed curriculum of 56 roots without subsequent exposures will leave the consolidated assembly unattested at curriculum close. An extended curriculum condition is required to observe re-attestation.
5. **Diverging Historical Surface Risk:** If two structurally identical assemblies historically witnessed different peripheral surfaces, Core consolidation **must not** consult those surfaces to resolve the discrepancy (zero selection leakage). Any loss of printable distinction must be reported faithfully, not hidden by aliasing or artificial evidence blending.

---

## Final Verdict Declaration

$$\mathbf{R2-B02\ DESIGN\ CONTRACT\ RECONCILED\ \text{—}\ AWAITING\ FINAL\ DESIGN\ FREEZE}$$
