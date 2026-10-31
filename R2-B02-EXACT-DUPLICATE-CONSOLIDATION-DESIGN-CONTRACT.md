# DGCA NEXT V2 — R2-B02 DESIGN CONTRACT

## Exact-Duplicate Assembly Consolidation — Formal Design Contract

- **Author:** Principal Cognitive Architecture Engineer, Formal Learning-Law Designer, and Scientific Verification Architect
- **Date:** October 30, 2026
- **Status:** **`R2-B02 DESIGN CONTRACT READY — AWAITING LEAD ENGINEER REVIEW`**
- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Frozen Main Baseline SHA:** [`faf361b6b95de6287b466eb1dc524ea49c732635`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Accepted R2-B01 Forensic Evidence Baseline:** [`205efa0e664dc26f31f131d5efc19ac37b3eb95d`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Authoritative Corrected Forensic Baseline:** [`1f18572fc1176bc8273b7478ef2e8c7e45c1b199`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Normative References:**
  - `DGCA_CORE_RC4_1.md` §2.0 (Executable Assembly Operators: `MAINTAIN → GROW → FORM → MERGE/SPLIT`)
  - `DGCA_CORE_RC4_1.md` §9.4 (I/O Envelope, Readout Ledger & Structural Generation Invalidation)
  - `DGCA_CORE_RC4_1.md` §11 (Machine State Serialization, Reproducibility & Cold Reset)
  - `DGCA_LLA_RC4_1.md` §6.6, §8.2 & §8.3 (LG-T01, LG-T02, LG-T03, LG-T16)
  - `R2-B01-FINAL-EVIDENCE-ATTESTATION.md` (Authoritative Forensic Evidence Attestation)

---

## 1. Scientific Problem Statement

The R2-B01 forensic investigation rigorously established the empirical mechanism underlying the terminal generation failure observed during the 56-root cold-start curriculum:
- On the Cat prompt `['القط']`, autonomous generation succeeds canonically:
  $$[\text{'القط'}] \longrightarrow (\text{'يشرب'}, \text{'حليب'}) \longrightarrow \text{GEN\_STOP\_EOS}$$
- On the Eagle prompt `['النسر']`, autonomous generation halts with ambiguity at step 2:
  $$[\text{'النسر'}] \longrightarrow (\text{'يشرب'}, \text{'ماء'}) \longrightarrow \text{GEN\_STOP\_AMBIGUOUS}$$

The root-cause investigation confirmed:
1. **Disjoint Seed Birth (Root 8, Event 3):** Under stimulus `النسر يشرب ماء <EOS>`, unassigned committed emitters formed two strictly disjoint 3-cell triangles: Assembly 5 (`[8834, 9209, 10570]`) and Assembly 6 (`[10646, 10915, 11153]`) with $\text{Jaccard}(A_5, A_6) = 0.0000$.
2. **Mutual Recruitment & Structural Convergence (Root 9):** During the Root 9 root-close assembly pipeline (`END_EXPOSURE`), symmetric co-activation and mutual support in the shared co-active context drove mutual recruitment under the frozen `GROW` operator. Assembly 5 recruited Assembly 6's cells and vice versa, rendering both assemblies 100% structurally identical at Root 9 ($8$ cells) and Root 10 ($9$ cells: `[8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117]`).
3. **Persistent Rejection under Frozen Core MERGE Rule:** Across Roots 9 to 56 (48 consecutive evaluations), `_try_merge_pair(5, 6)` evaluated the pair. Although $\text{Jaccard}(A_5, A_6) = 1.0000 \ge \Theta_{\text{merge}} = 0.70$ and $|\text{union}| = 9 \le K_{\text{max}} = 16$, the pair was rejected in all 48 opportunities because the exclusive sets were empty ($A_5 \setminus A_6 = \emptyset, A_6 \setminus A_5 = \emptyset$). Under the frozen Core §2.0 contract:
   $$\text{between\_strength} = \text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\}, \quad \text{with } (\text{empty exclusive side} \implies 0)$$
   Evaluating `between_strength` yielded $0.0000 < \Theta_{\text{ob}} = 0.40$, blocking consolidation.
4. **Readout Collision at Root 56:** Both assemblies remained active, had identical 9-cell membership, identical structural generation ($7$), and identical surface attestation on the ledger (`<EOS>`, `Marker.EOS`). At Step 2 of Eagle rollout (`ماء` $\to$ `<EOS>`), both assemblies computed an exact floating-point tie ($\text{score} = 0.2069442431$, $\text{Q6} = 206944$), yielding a margin of $0.0000000000 < M_{\text{read}} = 0.04$, which legally forced `StatusCode.AMBIGUOUS` and `GEN_STOP_AMBIGUOUS`.

The problem is a **contract-compliant structural consolidation limitation** in the Core §2.0 MERGE law. Disjoint assemblies that lawfully converge into identical cell sets can never be consolidated under the existing rule, creating permanent structural duplicates that inevitably collide at readout.

---

## 2. Frozen-Law Analysis

The current normative specification for the `MERGE` operator is defined in `DGCA_CORE_RC4_1.md` §2.0 (Operator 4):

```markdown
4. MERGE: take live pairs (A.id, B.id) ascending, after GROW/FORM, skipping any ID changed by MERGE/SPLIT within the last T_c=200 completed external events; with Jaccard of member sets >= theta_merge=.70, between_strength >= theta_ob=.40 where between_strength = mean{R_ij^B : i in A \ B, j in B \ A} (empty exclusive side => 0); require |union| <= 16 and every proposed union member meets the MAINTAIN guards and membership limits. Merge into lower ID, archive higher ID, advance survivor generation; recompute pair list once from new shadow state and process each initial pair at most once. No old ID may remain a live readout key.
```

### Mathematical & Structural Decomposition

1. **Jaccard Similarity Gate:**
   $$\text{Jaccard}(A, B) = \frac{|A \cap B|}{|A \cup B|}$$
   For identical assemblies ($A = B$), $|A \cap B| = |A \cup B| = |A|$, yielding $\text{Jaccard}(A, B) = 1.0000 \ge \Theta_{\text{merge}} = 0.70$. The pair passes this gate trivially.

2. **Exclusive-Set Mutual Support Gate:**
   The exclusive member sets are defined as:
   $$\text{excl}_A = A \setminus B, \qquad \text{excl}_B = B \setminus A$$
   Cross-pair mutual support is calculated over the Cartesian product $\text{excl}_A \times \text{excl}_B$:
   $$\text{between\_strength} = \frac{1}{|\text{excl}_A| \cdot |\text{excl}_B|} \sum_{i \in \text{excl}_A} \sum_{j \in \text{excl}_B} R_{ij}^B$$
   The specification explicitly mandates the boundary condition:
   $$\text{empty exclusive side} \implies \text{between\_strength} = 0$$

### Why the Boundary Condition Exists

The `empty exclusive side => 0` rule was designed to prevent **proper subset / superset merges** ($A \subset B$ or $B \subset A$).
Consider a smaller assembly $A$ fully contained inside a larger assembly $B$ ($A \subset B$, with $|A| < |B|$):
- Here, $A \setminus B = \emptyset$, but $B \setminus A \ne \emptyset$.
- If an empty exclusive set were permitted or assigned an arbitrary positive value (e.g., $1.0$), a smaller specialized cluster $A$ would be absorbed into a larger generalized cluster $B$ without any evidence of mutual synaptic attraction between the exclusive cells of $B$ and the cells of $A$.
- Therefore, the rule `empty exclusive side => 0` correctly and safely protects against subset absorption.

### Where the Boundary Condition Fails

The boundary condition makes no distinction between:
- **Case 1 (Asymmetric Empty Side — Proper Subset):** Exactly one side is empty ($A \setminus B = \emptyset \land B \setminus A \ne \emptyset$, or vice versa). Here, $A \ne B$.
- **Case 2 (Symmetric Empty Sides — Exact Duplicate):** Both sides are empty ($A \setminus B = \emptyset \land B \setminus A = \emptyset$). Here, $A = B$.

In Case 2, there are no exclusive cells on *either* side. The two assemblies already share 100% of their physical cells. Requiring synaptic attraction between exclusive cells is a physical impossibility because no exclusive cells exist. Treating this as $\text{between\_strength} = 0$ incorrectly treats complete structural identity as complete synaptic disconnection.

---

## 3. Comparative Evaluation of Alternative Semantics

Two formal approaches can resolve this limitation:

### Alternative A: Explicit Exact-Duplicate Structural Branch (Recommended)

Under Alternative A, Core §2.0 Operator 4 is amended with an explicit structural predicate:
If $\text{Members}(A) = \text{Members}(B)$, the exclusive-set mutual support gate is recognized as vacuously satisfied, and the pair qualifies for consolidation under an exact-duplicate condition. If $\text{Members}(A) \ne \text{Members}(B)$, the existing between-strength formula and its `empty exclusive side => 0` rule apply without modification.

### Alternative B: Defined Mathematical Convention for Empty Exclusive Sets

Under Alternative B, the mathematical definition of `between_strength` is modified:
$$\text{between\_strength} = \begin{cases}
1.0 & \text{if } A \setminus B = \emptyset \land B \setminus A = \emptyset \\
0.0 & \text{if } (A \setminus B = \emptyset \oplus B \setminus A = \emptyset) \\
\text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\} & \text{otherwise}
\end{cases}$$

### Rigorous Comparative Analysis

| Evaluation Criterion | Alternative A: Explicit Structural Branch | Alternative B: Defined Numeric Convention | Technical Assessment |
| :--- | :--- | :--- | :--- |
| **Formal Clarity** | **High.** Explicitly separates identity consolidation from synaptic mutual attraction. | **Low.** Conflates absence of exclusive cells with maximal synaptic strength. | Alternative A makes structural intent explicit in the specification. |
| **Mathematical Correctness** | **Rigorous.** Acknowledges that cross-support over $\emptyset \times \emptyset = \emptyset$ is undefined ($\text{N/A}$); bypasses the metric lawfully. | **Artificial.** Assigns an arbitrary scalar ($1.0$) to an empty average. Does not represent an empirical measurement. | Alternative B violates scientific reproducibility principles by treating undefined support as an empirical value. |
| **Interaction with Thresholds** | **Independent.** Bypasses $\Theta_{\text{ob}} = 0.40$ cleanly; robust to future changes in synaptic scales or thresholds. | **Coupled.** Relies on $1.0 \ge \Theta_{\text{ob}}$. If $\Theta_{\text{ob}}$ or support definitions change, numeric side-effects may emerge. | Alternative A provides invariant decoupling. |
| **Compatibility with Guards** | **Full.** All downstream structural guards ($K_{\text{max}}$, $M_{\text{max}}$, `keep`, cooldown) remain strictly enforced. | **Full.** Downstream guards remain enforced. | Both preserve structural sanity checks. |
| **Risk of Subset Merges ($A \subset B$)** | **Zero.** The exact-duplicate branch requires $A = B$. If $A \subset B$, it falls through to the existing rule and is rejected. | **Moderate.** If implemented naively (`if not excl_a or not excl_b`), it admits subset merges. Requires strict conjunction guard. | Alternative A provides stronger structural defense. |
| **Deterministic Execution** | **Deterministic.** Evaluates `Members(A) == Members(B)` via sorted tuple comparison. | **Deterministic.** Computes identical boolean logic through numeric proxy. | Both are deterministic. |

### Design Decision & Justification

**Alternative A is selected as the recommended design.**
- Consolidation of exact structural duplicates is fundamentally an **identity-deduplication operation**, not a synaptic attraction event.
- It is scientifically inappropriate to invent an empirical value ($1.0$) for non-existent synaptic edges between non-existent exclusive cells.
- Alternative A is formally clean, conceptually transparent, and mathematically honest.

---

## 4. Exact Eligibility Predicate (Proposed Normative Amendment)

### Proposed Core §2.0 Text Amendment

We propose amending `DGCA_CORE_RC4_1.md` §2.0 Item 4 (MERGE) to read as follows (amended text emphasized):

> **4. `MERGE`:** Take live pairs $(A.\text{id}, B.\text{id})$ ascending ($A.\text{id} < B.\text{id}$), after `GROW`/`FORM`, skipping any ID changed by `MERGE`/`SPLIT` within the last $T_c = 200$ completed external events.
> A candidate pair is eligible for merge if and only if:
> 1. Both assemblies are live: $A.\text{status} = \text{LIVE} \land B.\text{status} = \text{LIVE}$;
> 2. Union cardinality is bounded: $|A \cup B| \le K_{\text{max}} = 16$;
> 3. Jaccard similarity meets threshold: $\text{Jaccard}(A, B) \ge \Theta_{\text{merge}} = 0.70$;
> 4. **Mutual Support or Exact Duplication:** Either:
>    - **(Branch 4a — Exact Duplicate Consolidation):** $\text{Members}(A) = \text{Members}(B)$; OR
>    - **(Branch 4b — Partial Overlap Synaptic Merge):** $\text{Members}(A) \ne \text{Members}(B)$, both exclusive sets are non-empty ($A \setminus B \ne \emptyset \land B \setminus A \ne \emptyset$), and $\text{between\_strength} \ge \Theta_{\text{ob}} = 0.40$, where $\text{between\_strength} = \text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\}$;
> 5. Every proposed union member $x \in A \cup B$ satisfies post-merge membership limits ($M_{\text{max}} = 12$) and MAINTAIN keep guards ($d(x, A \cup B) \ge 2$, $D(x, A \cup B) \ge \rho_{\text{keep}} = 0.35$, $\text{Spec}(x, A \cup B) \ge \sigma_{\text{keep}} = 0.20$).
>
> If eligible, merge into lower ID ($A.\text{id}$), archive higher ID ($B.\text{id}$), advance survivor structural generation, and apply cooldown $T_c = 200$ to the survivor. Process each initial pair at most once.

### Mathematical Formulation of the Predicate

Let $\mathcal{P}_{\text{merge}}(A, B)$ be the complete merge eligibility predicate for pair $A, B$ with $A.\text{id} < B.\text{id}$:

$$\mathcal{P}_{\text{merge}}(A, B) \iff \mathcal{G}_{\text{lifecycle}}(A, B) \land \mathcal{G}_{\text{cooldown}}(A, B) \land \mathcal{G}_{\text{size}}(A, B) \land \mathcal{G}_{\text{similarity}}(A, B) \land \mathcal{G}_{\text{consolidation}}(A, B) \land \mathcal{G}_{\text{membership}}(A, B) \land \mathcal{G}_{\text{keep}}(A, B)$$

Where:
1. **Lifecycle Guard:**
   $$\mathcal{G}_{\text{lifecycle}}(A, B) \iff (A.\text{status} = \text{LIVE}) \land (B.\text{status} = \text{LIVE})$$
2. **Cooldown Guard:**
   $$\mathcal{G}_{\text{cooldown}}(A, B) \iff (t_{\text{clock}} - A.\text{last\_merge\_split} \ge T_c) \land (t_{\text{clock}} - B.\text{last\_merge\_split} \ge T_c)$$
3. **Union Cardinality Guard:**
   $$\mathcal{G}_{\text{size}}(A, B) \iff 1 \le |A \cup B| \le K_{\text{max}} \quad (K_{\text{max}} = 16)$$
4. **Jaccard Similarity Guard:**
   $$\mathcal{G}_{\text{similarity}}(A, B) \iff \frac{|A \cap B|}{|A \cup B|} \ge \Theta_{\text{merge}} \quad (\Theta_{\text{merge}} = 0.70)$$
5. **Consolidation Support Disjunction:**
   $$\mathcal{G}_{\text{consolidation}}(A, B) \iff \underbrace{(A = B)}_{\text{Exact Duplicate}} \lor \left( \underbrace{(A \ne B) \land (A \setminus B \ne \emptyset) \land (B \setminus A \ne \emptyset) \land (\text{between\_strength}(A, B) \ge \Theta_{\text{ob}})}_{\text{Partial Overlap Mutual Support}} \right)$$
6. **Cell Membership Limit Guard:**
   $$\mathcal{G}_{\text{membership}}(A, B) \iff \forall x \in A \cup B: \quad |\{C \in \mathcal{A}_{\text{live}} \setminus \{B\} : x \in C\} \cup \{A\}| \le M_{\text{max}} \quad (M_{\text{max}} = 12)$$
7. **Keep Guard Integrity:**
   $$\mathcal{G}_{\text{keep}}(A, B) \iff \forall x \in A \cup B: \quad \text{CheckKeepGuards}(x, A \cup B) = \text{True}$$

---

## 5. Survivor Identity, Generation Advancement, and Lifecycle Semantics

To prevent non-deterministic identity drift, all state updates must strictly follow normative conventions:

### Identity Assignment (Lower-ID Survivor)
- **Surviving Assembly:** $A_{\text{surv}} = \min(A, B)$. Its identifier $A_{\text{surv}}.\text{id}$ is permanently retained.
- **Archived Assembly:** $A_{\text{arch}} = \max(A, B)$. Its identifier $A_{\text{arch}}.\text{id}$ transitions permanently to `AssemblyStatus.ARCHIVED`.
- **Identity Invariant:** No selection of survivor ID based on peripheral attestation maturity, activation count, or timestamp is permitted. Lower numeric ID is strictly authoritative.

### Structural Generation Advancement
Because structural consolidation alters the identity context of the assembly, generation advancement must occur:
$$A_{\text{surv}}.\text{structural\_generation} \leftarrow \max(A.\text{structural\_generation}, B.\text{structural\_generation}) + 1$$
$$A_{\text{arch}}.\text{structural\_generation} \leftarrow A_{\text{arch}}.\text{structural\_generation} + 1$$

*Example (Root 9):*
Before consolidation: $A_5.\text{generation} = 7$, $A_6.\text{generation} = 7$.
After consolidation: $A_5.\text{generation} = 8$, $A_6.\text{generation} = 8$ (`ARCHIVED`).

### Reverse Index Updates (`assemblies_by_member`)
In `WState.assemblies_by_member`:
- For every cell $c \in \text{Members}(A_{\text{surv}})$:
  - Previously, `assemblies_by_member[c]` contained both $A_{\text{surv}}.\text{id}$ and $A_{\text{arch}}.\text{id}$.
  - After consolidation, $A_{\text{arch}}.\text{id}$ is removed from the set of active assemblies.
  - The cell's active membership count decreases by exactly 1:
    $$M_{\text{live}}(c) \leftarrow M_{\text{live}}(c) - 1$$
  - This strictly respects the cell membership cap $M_{\text{max}} = 12$.

### Merge Cooldown Enforcement
Consolidation must trigger the standard merge cooldown to prevent cascading structural instability:
$$A_{\text{surv}}.\text{last\_mutation\_close\_serial} \leftarrow W.\text{close\_serial}$$
$$A_{\text{surv}}.\text{last\_merge\_split\_close\_serial} \leftarrow W.\text{completed\_external\_events\_count}$$
$$A_{\text{arch}}.\text{last\_mutation\_close\_serial} \leftarrow W.\text{close\_serial}$$
$$A_{\text{arch}}.\text{last\_merge\_split\_close\_serial} \leftarrow W.\text{completed\_external\_events\_count}$$
During the subsequent $T_c = 200$ completed external events, $A_{\text{surv}}$ is ineligible for any further `MERGE` or `SPLIT` operations.

### Reporting & Outbox Notification
The transaction manager records the consolidation in `EndExposureReport.assembly_reports`:
- Outcome code: `MERGE_CONSOLIDATED_EXACT_DUPLICATE` (or standard `MERGE_SUCCESS` with duplicate flag).
- `AssemblyMutationNotification` emitted to outbox:
  - `survivor_id`: $A_{\text{surv}}.\text{id}$
  - `survivor_generation`: $A_{\text{surv}}.\text{structural\_generation}$
  - `archived_id`: $A_{\text{arch}}.\text{id}$
  - `archived_generation`: $A_{\text{arch}}.\text{structural\_generation}$
  - `mutation_type`: `MUTATION_MERGE`

---

## 6. Peripheral Ledger Safety and Re-Attestation Lifecycle

A structural-generation change has profound implications for peripheral surface decoding. Under Core §9.4 and §9.4.1, the readout ledger indexes attestations strictly by the tuple:
$$(\text{assembly\_id}, \text{structural\_generation})$$

### Normative Constraints on Ledger Interactions

```
                +-------------------------------------------+
                | Consolidation at Root 9:                  |
                | Asm 5 (Gen 7) + Asm 6 (Gen 7) -> Asm 5 (Gen 8) |
                +-------------------------------------------+
                                     |
                                     v
       +-----------------------------------------------------------+
       | Ledger State:                                             |
       | - Row (5, 7): Surface Envelope '<EOS>' [HISTORICAL ONLY]  |
       | - Row (6, 7): Surface Envelope '<EOS>' [ARCHIVED ID]      |
       | - Row (5, 8): EMPTY (0 attestations registered)           |
       +-----------------------------------------------------------+
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
+-------------------------------+         +----------------------------------+
| Immediate Readout Attempt:    |         | Subsequent External Exposure:    |
| - Query ledger for (5, 8)     |         | - Root with 'النسر يشرب ماء <EOS>'|
| - Result: EMPTY TUPLE ()      |         | - Asm 5 fires during <EOS>       |
| - Verdict: UNATTESTED READOUT |         | - Ledger registers Row (5, 8)    |
| - Surface Emission: HALTED    |         | - Verdict: RE-ATTESTED           |
+-------------------------------+         | - Surface Emission: SUCCESS      |
                                          +----------------------------------+
```

1. **Strict Generation Invalidation:**
   Old-generation attestations (Gen 7) must **never** be matched for new-generation queries (Gen 8):
   $$\text{get\_rows\_for\_assembly}(5, 8) \equiv ()$$
   Even though Assembly 5 had valid evidence for `<EOS>` at Gen 7, that evidence was witnessed on a 9-cell assembly before consolidation. The post-merge entity is a new structural generation.
2. **Zero Retroactive Witnessing:**
   The surviving assembly cannot synthesize or backdate an attestation. No historical event witnessed Gen 8. An attestation can only be registered when a genuine, live external event activates Assembly 5 at Gen 8.
3. **No Archived-ID Aliasing:**
   The readout ledger must **never** resolve an alias from $A_{\text{arch}}$ to $A_{\text{surv}}$:
   $$\text{Resolve}(6) \ne 5$$
   Creating an alias would violate transactional immutability and break audit trails. Assembly 6 is archived and permanently inert.
4. **Readout Behavior During the Unattested Interval:**
   During the interval between consolidation (Root 9) and the next external witness of `<EOS>`, Assembly 5 is **unattested**.
   - If autonomous generation is queried on a prompt whose trajectory activates Assembly 5:
   - Assembly 5 produces high activation score, winning candidate selection.
   - However, when the decoder queries the ledger for surface tokens, zero attestations are returned.
   - Under `DGCA_CORE_RC4_1.md` §9.4, the generator halts without emitting an ungrounded string (`StatusCode.UNATTESTED_READOUT` or fail-closed halt).
   - This is the **correct, safe, normative behavior**. The system must never hallucinate a printable string from an unattested assembly generation.
5. **Minimum External Evidence for Re-Attestation:**
   Exactly **one valid external exposure** containing `<EOS>` (where Assembly 5 activates above threshold) is required to register a Gen 8 attestation on the ledger. Once attested, Assembly 5 will emit `<EOS>` with positive score margin, resolving the duplicate collision permanently.

---

## 7. Transactional Safety and Rollback Guarantees

The proposed amendment introduces zero modifications to the frozen R2-A01 transactional architecture:

### Shadow-State Execution
- All assembly operations (`MAINTAIN`, `GROW`, `FORM`, `MERGE`, `SPLIT`) execute on the shadow `WState` within `ExposureTransactionManager._run_assembly_pipeline()`.
- No intermediate state is exposed to concurrent readers or published to `TransactionPublicationView`.

### Atomic Commit & Rollback Semantics

```
[Start END_EXPOSURE Pipeline]
            |
            v
[Shadow State: MAINTAIN -> GROW -> FORM -> MERGE -> SPLIT]
            |
   (Is Pre-Commit Valid?)
       /         \
     NO          YES
     /             \
    v               v
[ABORT & ROLLBACK] [ATOMIC COMMIT]
- Discard shadow   - Swap shadow to active WState
- Zero mutations   - Publish EndExposureReport
- Zero outbox      - Emit Outbox notifications to ledger
- State Pristine   - Ledger records mutations atomically
```

1. **Pre-Publication Failure:**
   If any validation check fails during `MERGE` (e.g. membership capacity overflow, keep guard check failure, or memory fault):
   - The transaction manager triggers `ABORT`.
   - The shadow state is discarded.
   - Active `WState`, `HSlowState`, and `ReadoutLedger` remain 100% untouched.
2. **Post-Commit Dispatch Barrier:**
   Once `END_EXPOSURE` commits, the publication view is updated atomically. If an outbox dispatch failure occurs downstream:
   - The committed structural state is **not rolled back** (maintaining R2-A01 Gate 4 idempotency).
   - The reconciliation retry mechanism re-delivers the `AssemblyMutationNotification` to the ledger.

---

## 8. Counterexamples and Excluded Cases

To guarantee bounded scope, the eligibility predicate explicitly excludes all non-duplicate cases:

### Counterexample 1: Proper Subsets ($A \subset B$)
- **Configuration:** $A = \{1, 2, 3\}$, $B = \{1, 2, 3, 4\}$.
- **Evaluation:**
  - $\text{Members}(A) \ne \text{Members}(B)$ $\implies$ Branch 4a fails.
  - $A \setminus B = \emptyset$, while $B \setminus A = \{4\}$.
  - Because one exclusive set is empty, Branch 4b evaluates `empty exclusive side => between_strength = 0.0`.
  - $0.0 < \Theta_{\text{ob}} = 0.40$ $\implies$ Branch 4b fails.
- **Verdict:** **REJECTED.** Proper subsets cannot merge without mutual synaptic attraction between exclusive cells.

### Counterexample 2: Low-Jaccard Overlap
- **Configuration:** $A = \{1, 2, 3, 4\}$, $B = \{3, 4, 5, 6\}$.
- **Evaluation:**
  - $|A \cap B| = 2$, $|A \cup B| = 6 \implies \text{Jaccard} = 2/6 = 0.3333 < \Theta_{\text{merge}} = 0.70$.
  - Fails similarity gate.
- **Verdict:** **REJECTED.**

### Counterexample 3: Weak Exclusive Mutual Support
- **Configuration:** $A = \{1, 2, 3, 4, 5\}$, $B = \{2, 3, 4, 5, 6\}$.
- **Evaluation:**
  - $|A \cap B| = 4$, $|A \cup B| = 6 \implies \text{Jaccard} = 4/6 = 0.6667 < \Theta_{\text{merge}} = 0.70$.
  - If sizes are larger such that $\text{Jaccard} \ge 0.70$, but $R^B(1, 6) = 0.12 < \Theta_{\text{ob}} = 0.40$.
  - Fails mutual support gate.
- **Verdict:** **REJECTED.**

### Counterexample 4: Cooldown Violation
- **Configuration:** $\text{Members}(A) = \text{Members}(B)$, but $A$ was modified by a merge 50 external events ago ($t_{\text{clock}} - t_{\text{merge}} = 50 < T_c = 200$).
- **Evaluation:**
  - Fails cooldown guard $\mathcal{G}_{\text{cooldown}}$.
- **Verdict:** **REJECTED.** Cooldown is strictly preserved.

### Counterexample 5: Cell Membership Limit Overflow
- **Configuration:** $\text{Members}(A) = \text{Members}(B)$, but a cell $x \in A$ has reached membership capacity in other assemblies ($M_{\text{live}}(x) = 12$).
- **Evaluation:**
  - In an exact duplicate merge, $x$ belongs to both $A$ and $B$. Post-merge, $x$ belongs only to $A$.
  - Its live count becomes $12 - 1 = 11 \le 12$.
  - However, if the union evaluation evaluates any external addition that exceeds 12, it fails.
- **Verdict:** **PASS for exact duplicate, REJECT if capacity exceeded.**

---

## 9. Scientific Acceptance Test Matrix

The following five validation experiments constitute the mandatory acceptance suite for R2-B02 implementation approval:

| Test ID | Experiment Name | Stimulus / Configuration | Expected Empirical Outcome | Invariant Verified |
| :--- | :--- | :--- | :--- | :--- |
| **EXP-B02-01** | Exact Duplicate Consolidation | Replay Root 9 where Assemblies 5 & 6 have converged to identical 8 cells. | $A_5$ remains `LIVE` (Gen 8); $A_6$ becomes `ARCHIVED` (Gen 8); single assembly published; cooldown applied. | Core §2.0 Operator 4 (Branch 4a). |
| **EXP-B02-02** | Partial Overlap Invariance | Synthetic pair with 8 shared cells, 2 exclusive cells, $R^B = 0.50 \ge \Theta_{\text{ob}}$. | Pair merges legally under Branch 4b; between-strength evaluated accurately. | Core §2.0 Operator 4 (Branch 4b). |
| **EXP-B02-03** | Proper Subset Rejection | Synthetic pair with $A \subset B$ ($|A|=4, |B|=5$). | Merge rejected with `between_strength = 0.0 < THETA_OB`. | Prevention of subset absorption. |
| **EXP-B02-04** | Ledger Generation Safety | Query readout immediately after Root 9 consolidation without external exposure. | Surviving $A_5$ (Gen 8) has 0 ledger attestations; readout halts without emitting ungrounded string. | Core §9.4 ledger generation barrier. |
| **EXP-B02-05** | Post-Merge Re-Attestation | Expose consolidated model to 1 external root containing `النسر يشرب ماء <EOS>`. | $A_5$ fires on `<EOS>`, registers Gen 8 attestation; subsequent Eagle readout emits `<EOS>` cleanly. | Readout recovery via genuine external grounding. |
| **EXP-B02-06** | 56-Root Curriculum Replay | Full 56-root curriculum with consolidation active at Root 9. | 0 duplicate collisions; Assemblies 5 & 6 consolidated; full state equality across dual replays. | Curriculum determinism. |
| **EXP-B02-07** | Transaction Fault Injection | Inject simulated failure prior to atomic publication during consolidation. | Transaction aborts cleanly; shadow state discarded; active WState pristine; 0 outbox leakage. | R2-A01 Gate 1 & 3 transaction atomicity. |

---

## 10. Implementation Boundaries and Code Touchpoints

When authorized, the implementation will be strictly confined to the following narrow touchpoints:

### Permitted Modifications
1. `src/dgca/core/assembly.py`:
   - In `_try_merge_pair()`: Insert the Branch 4a exact-duplicate check before exclusive-set cross-product evaluation:
     ```python
     if not excl_a and not excl_b:
         # Branch 4a: Exact Structural Duplicate consolidation
         between_strength_passed = True
     else:
         # Branch 4b: Partial Overlap cross-support evaluation
         if not excl_a or not excl_b:
             between_strength = 0.0
         else:
             cross_vals = [compute_mutual_support_r_b(i, j, w) for i in excl_a for j in excl_b]
             between_strength = sum(cross_vals) / float(len(cross_vals))
         between_strength_passed = (between_strength >= THETA_OB)
     ```
2. `src/dgca/core/transaction.py`:
   - Ensure `EndExposureReport` logs consolidation events with explicit duplicate classification.

### Forbidden Modifications
- **Forbidden:** No modification to `FORM` or `GROW` operators.
- **Forbidden:** No modification to `SurfaceReadoutLedgerV1` storage or lookup logic.
- **Forbidden:** No modification to `TransactionPublicationView` or `ExposureTransactionManager` atomic commit mechanics.
- **Forbidden:** No synthesis of artificial ledger attestations.
- **Forbidden:** No generalized multi-assembly clustering or fuzzy deduplication algorithms.

---

## 11. Risks and Open Decisions for Lead Engineer Review

### Risk 1: Readout Delay in Fixed Curricula
If a curriculum has a fixed number of roots (e.g., 56 roots) and does not provide an external exposure of `<EOS>` after consolidation, the surviving assembly will remain unattested at Root 56, and autonomous generation will halt with an unattested status rather than emitting `<EOS>`.
- *Mitigation:* The acceptance test plan explicitly defines an **Extended Curriculum Experiment** where an external exposure is appended to allow re-attestation. The Lead Engineer must confirm whether the standard 56-root benchmark should be evaluated in its unattested state or with a re-attestation exposure.

### Risk 2: Cooldown Window Scale ($T_c = 200$)
A cooldown of $T_c = 200$ external events means that once consolidated, Assembly 5 cannot undergo another merge or split for 200 events.
- *Assessment:* This is the frozen normative behavior of Core §2.0. In the 56-root curriculum, 56 roots $\times$ 4 events/root = 224 events. A 200-event cooldown prevents further structural mutation, which is desirable for stabilizing the consolidated attractor.

### Open Decision 1: Naming of the Mutation Code
Should the transaction report record this outcome as `MERGE_SUCCESS` (preserving backwards compatibility with existing consumers) or introduce `MERGE_CONSOLIDATED_EXACT_DUPLICATE`?
- *Recommendation:* Keep `MERGE_SUCCESS` as the primary enum status, but include `"exact_duplicate": True` in the report metadata dictionary.

---

## 12. Final Design Recommendation

We recommend formal approval of **Alternative A (Explicit Exact-Duplicate Structural Branch)** for implementation in Patch R2-B02.
- It addresses the exact physical defect identified in R2-B01.
- It preserves all frozen Core laws, transaction boundaries, and ledger safety mechanisms.
- It introduces zero fuzzy heuristics or unprincipled numerical conventions.
- It guarantees that duplicate assemblies consolidate deterministically into a single survivor, eliminating readout ambiguity at its causal root.

---

## Final Verdict Declaration

$$\mathbf{R2-B02\ DESIGN\ CONTRACT\ READY\ \text{—}\ AWAITING\ LEAD\ ENGINEER\ REVIEW}$$
