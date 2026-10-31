# DGCA Core Specification Normative Amendment — R2-B02

**Document Identifier:** `DGCA-CORE-AMENDMENT-R2-B02-20261031`  
**Target Specification:** `DGCA_CORE_RC4_1.md` — Section 2.0, Operator 4 (`MERGE`)  
**Status:** `NORMATIVE AMENDMENT CANDIDATE — AWAITING EXPLICIT MAIN PROMOTION RATIFICATION`  
**Date:** 2026-10-31  
**Companion Documents:** `DGCA_CORE_RC4_1.md`, `DGCA_LLA_RC4_1.md`, `R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md`  

---

## 1. Context, Purpose, and Normative Scope

### 1.1 Context
In the frozen `DGCA_CORE_RC4_1.md` §2.0 Operator 4, Assembly consolidation requires an exclusive-set between-strength evaluation:
$$\text{between\_strength} = \text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\} \quad (\text{empty exclusive side} \implies 0.0)$$
When two disjoint seed Assemblies converge lawfully via independent `GROW` operations into identical cell membership sets ($A \equiv B$), both exclusive sets are empty:
$$E_A = A \setminus B = \emptyset, \quad E_B = B \setminus A = \emptyset$$
Under the un-amended rule, the between-strength evaluates to $0.0 < \Theta_{\text{ob}} = 0.40$, preventing structural consolidation of identical duplicate assemblies and causing duplicate readout score collisions during autonomous generation.

### 1.2 Purpose
This amendment replaces the exclusive-set support rule in Core §2.0 Operator 4 with an explicit structural branch, allowing exact-duplicate assembly pairs to satisfy the mutual-support gate.

### 1.3 Scope of Amendment
- **Narrow Touchpoint:** This amendment modifies strictly the mutual-support evaluation gate of Core §2.0 Operator 4 (`MERGE`).
- **Preserved Laws:** All other Core §2.0 requirements, the MAINTAIN, GROW, FORM, and SPLIT operators, all LLA learning laws and equations, all transaction publication rules, and all peripheral readout and attestation rules are completely unchanged and preserved.
- **Specification Invariant:** `DGCA_CORE_RC4_1.md` remains frozen in repository history. This document serves as an authoritative versioned amendment with normative precedence upon promotion.

---

## 2. Normative Precedence Statement

> **Normative Precedence:**
> 1. In any repository context where this amendment is ratified and promoted, Section 3 of this document **formally supersedes** the mutual-support evaluation sentence of `DGCA_CORE_RC4_1.md` Section 2.0, Item 4 (`MERGE`).
> 2. All surrounding requirements of Core §2.0 Operator 4 (cooldown, Jaccard overlap, union size, membership limits, keep guards, lower-ID survivor, higher-ID archival, generation advancement, reverse index updates, and single-pass pair evaluation) remain in full normative force.
> 3. Where any conflict exists between the historical empty-exclusive-set sentence of Core RC4.1 and Section 3 of this amendment, this amendment shall govern.

---

## 3. Authoritative Replacement Text for Core §2.0 Operator 4 (`MERGE`)

In `DGCA_CORE_RC4_1.md` §2.0, Item 4 (`MERGE`), the evaluation of Assembly pair consolidation is replaced by the following normative text:

> ### Operator 4: MERGE
> 
> In the isolated shadow state $W^*$, take candidate live pairs $(A.\text{id}, B.\text{id})$ ascending ($A.\text{id} < B.\text{id}$) after `GROW` and `FORM`.
> 
> A candidate pair $(A, B)$ is eligible for consolidation if and only if **all** of the following conditions are satisfied:
> 
> 1. **Live Status:** Both $A$ and $B$ have status `LIVE`.
> 2. **Cooldown Guard:** Neither $A$ nor $B$ is in merge/split cooldown. Specifically, for each assembly $\text{asm} \in \{A, B\}$:
>    - **Never Previously Merged or Split:** If $\text{asm}.\text{last\_merge\_split\_close\_serial}$ is `None`, the assembly is **not** blocked by cooldown (`_is_in_merge_split_cooldown` returns `False`).
>    - **Previously Merged or Split:** If $\text{asm}.\text{last\_merge\_split\_close\_serial}$ is not `None`, the elapsed completed external events count must satisfy:
>      $$\text{CompletedExternalEventsCount} - \text{asm}.\text{last\_merge\_split\_close\_serial} \ge T_c = 200$$
>      If the elapsed count is $< T_c = 200$, the assembly is blocked and consolidation is rejected.
>    - **Preservation of Cooldown:** Exact structural equality never bypasses the cooldown guard.
> 3. **Jaccard Overlap:** The Jaccard similarity of member cell sets satisfies:
>    $$J(A, B) = \frac{|A \cap B|}{|A \cup B|} \ge \Theta_{\text{merge}} = 0.70$$
> 4. **Union Size Limit:** The prospective union size satisfies:
>    $$|A \cup B| \le K_{\text{max}} = 16$$
> 5. **Consolidation Support Gate:**
>    Let $E_A = \text{Members}(A) \setminus \text{Members}(B)$ and $E_B = \text{Members}(B) \setminus \text{Members}(A)$.
>    
>    - **Branch 4a — Exact Structural Duplicate:**
>      If both exclusive sets are empty ($E_A = \emptyset$ and $E_B = \emptyset$), the exclusive mutual-support gate is **satisfied** (`between_strength_passed = True`).
>      
>      > **MANDATORY NORMATIVE REQUIREMENT:**
>      > **Exact structural equality satisfies only the exclusive mutual-support gate, not complete merge eligibility.**
>      > Exact duplicates must still satisfy Conditions 1, 2, 3, 4, and 6 to be merged. Exact structural equality never grants unconditional consolidation.
>      
>    - **Branch 4b — Partial Overlap:**
>      If $E_A \ne \emptyset$ and $E_B \ne \emptyset$, the between-strength is computed as the mean reciprocal support across all cross-pairs:
>      $$\text{BetweenStrength}(A, B) = \frac{1}{|E_A| \cdot |E_B|} \sum_{i \in E_A} \sum_{j \in E_B} R_{ij}^B(W)$$
>      where $R_{ij}^B$ is computed via `compute_mutual_support_r_b(i, j, w)`.
>      The mutual-support gate is satisfied if and only if:
>      $$\text{BetweenStrength}(A, B) \ge \Theta_{\text{ob}} = 0.40$$
>      
>      If either exclusive set is empty while the other is non-empty (proper subsets or proper supersets, e.g., $A \subset B$ or $B \subset A$), $\text{BetweenStrength}(A, B) = 0.0 < \Theta_{\text{ob}} = 0.40$, and the mutual-support gate fails closed.
>      
> 6. **Cell Membership Limits and Keep Guards:**
>    For every cell $x \in A \cup B$:
>    - **Membership Capacity:** The count of live assemblies containing cell $x$ after archiving $B$ must not exceed $M_{\text{max}} = 12$:
>      $$|\{ \text{aid} \in \text{LiveAssemblies}(x) \setminus \{B.\text{id}\} \} \cup \{A.\text{id}\}| \le M_{\text{max}} = 12$$
>    - **MAINTAIN Keep Guards:** Cell $x$ must satisfy all maintain keep guards within the prospective union tuple:
>      $$\text{check\_maintain\_keep\_guards}(x, \text{tuple}(\text{sorted}(A \cup B)), W, n\_rec\_cache) = \text{True}$$
>      requiring $d(x, \text{union}) \ge D_{\text{min}} = 2$, $D(x, \text{union}) \ge \rho_{\text{keep}} = 0.35$, and $\text{Spec}(x, \text{union}) \ge \sigma_{\text{keep}} = 0.20$.
> 
> ### Consolidation Lifecycle Execution
> When all six conditions pass:
> 1. **Lower-ID Survivor:** Assembly $A$ (the lower ID, since $A.\text{id} < B.\text{id}$) is retained as the survivor (`LIVE`). Its member set becomes $\text{tuple}(\text{sorted}(A \cup B))$.
> 2. **Higher-ID Archival:** Assembly $B$ (the higher ID) transitions to `ARCHIVED`. Its member set is preserved for audit.
> 3. **Generation Increment:** Both $A$ and $B$ increment their structural generation by 1:
>    $$\text{asm\_a}.\text{structural\_generation} \mathrel{+}= 1, \quad \text{asm\_b}.\text{structural\_generation} \mathrel{+}= 1$$
> 4. **Clocks Updated:** For both $A$ and $B$:
>    - `last_mutation_close_serial` is set to shadow $W^*.close\_serial$.
>    - `last_merge_split_close_serial` is set to shadow $W^*.completed\_external\_events\_count$.
> 5. **Reverse Index Rebuilding:** The reverse lookup table `assemblies_by_member` is rebuilt atomically on shadow $W^*$ (`_rebuild_assemblies_by_member(W)`).
> 6. **Single-Pass Evaluation:** The initial pair list is recomputed at most once from the new shadow state; initial pairs are processed at most once.

---

## 4. Specification Consistency & Downstream Invariants

### 4.1 Consistency with Core §2.0 Assembly Definitions
- **Structural Identity:** Assembly identity is strictly structural, defined by `AssemblyID` and `member_cell_ids`. No semantic labels are attached.
- **Monotonic ID Allocation:** Merging never creates or consumes an `AssemblyID`. Lower-ID survivor semantics ensure strict monotonicity and determinism.
- **Reverse Index Integrity:** Rebuilding `assemblies_by_member` ensures that cell queries never return archived assembly IDs.

### 4.2 Consistency with Attestation & Readout Laws (Core §9.4 & §9.4.1)
- **Structural Generation Invalidation:** Advancing structural generation on survivor $A$ ($g_A \to g_A + 1$) strictly requires new qualifying attestation for generation $g_A + 1$ before peripheral readout resolution can resolve to survivor $A$.
- **Historical Ledger Preservation:** Historical Ledger rows previously recorded for prior generations or archived IDs are not automatically deleted upon merge. However, because readout lookup is strictly keyed by `(assembly_id, structural_generation)`, historical rows at generation $g_A$ cannot satisfy queries for generation $g_A + 1$.
- **Archival Evidence Boundary:** An archived assembly $B$ cannot produce new qualifying outbox evidence after archival. (This does not imply that archived identities can never possess historical candidate rows recorded prior to archival; rather, post-archival, zero new qualifying outbox notifications are emitted under $B$'s ID).
- **Generation Halting Dynamics:** Autonomous generation stop status is governed deterministically by the neural winner and Ledger resolution conditions. A specific stop status (such as `GEN_STOP_EOS` or `READOUT_UNKNOWN`) is not unconditionally guaranteed unless those neural selection and ledger resolution conditions are established.

### 4.3 Consistency with Transaction Isolation (Core §10 & LLA §7)
- Consolidation executes entirely on an isolated shadow machine state $W^*$.
- Pre-publication rollback (transaction abort on `FP_01`, `FP_02`) completely discards shadow state changes while preserving lawful sensory commitments made during OPEN (committed cell addresses).
- Post-commit peripheral dispatch faults (`FP_03`) defer outbox delivery to idempotent retry without rolling back durable state.

---

## 5. Formal Verdict & Ratification Criteria

This amendment is mathematically sound, preserves 100% of non-identical learning dynamics, and resolves the exact-duplicate assembly collision defect without side effects.

**Ratification Gate:** Permanent incorporation into production `main` requires formal governance sign-off in accordance with `R2-B05-NORMATIVE-PROMOTION-PREPARATION-REPORT.md`.
