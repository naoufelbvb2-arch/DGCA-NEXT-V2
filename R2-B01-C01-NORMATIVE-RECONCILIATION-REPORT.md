# DGCA NEXT V2 — R2-B01-C01 NORMATIVE RECONCILIATION REPORT

## Final Normative Reconciliation & Forensic Evidence Correction

- **Author:** Principal Scientific Verification Engineer, Formal Specification Auditor, Neural Architecture Research Engineer
- **Date:** October 30, 2026
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Starting Authoritative Baseline:** `f378d171dd9b602743c2bc1abd9a355458416a4b`
- **Frozen Main Baseline:** `faf361b6b95de6287b466eb1dc524ea49c732635`
- **Normative References:**
  - `DGCA_CORE_RC4_1.md` §2.0 (Executable Assembly Operators: `MAINTAIN → GROW → FORM → MERGE/SPLIT`)
  - `DGCA_CORE_RC4_1.md` §9.4 (Readout Ledger & Structural Generation Invalidation)
  - `DGCA_LLA_RC4_1.md` §6.6, §8.2 & §8.3 (LG-T01, LG-T02, LG-T03, LG-T16)
- **Status:** **`R2-B01-C01 VERIFIED — AWAITING FINAL FORENSIC FREEZE`**

---

## 1. Executive Summary

This report establishes the formal normative reconciliation and empirical evidence verification for the R2-B01 forensic investigation into Assembly 5 and 6 duplicate formation and Eagle readout collision.

Following independent review by the Lead Engineer, this audit reconciles material specification inaccuracies in the original forensic report, audits all normative constants against `DGCA_CORE_RC4_1.md` §2.0, proves exact event attribution with reproducible empirical traces, verifies downstream merge predicates under read-only conditions, and formalizes ledger attestation constraints.

---

## 2. Empirical Causal Mechanism

The empirical causal chain from cold-start to readout collision is established as follows:

1. **Dual Legal Seeding at Birth (Root 8, Event 3):**
   In Root 8, during the Event 3 pass of the FORM stage, eight fresh unassigned cells ($U_t$) formed two legal, completely disjoint 3-cell reciprocal triangles:
   - Assembly 5: `[8834, 9209, 10570]`
   - Assembly 6: `[10646, 10915, 11153]`
   - Initial relationship: $\text{Jaccard} = 0.0000$, $\text{Intersection} = 0$.
2. **Symmetric Recruitment during Post-Exposure GROW (Root 9):**
   During the Root 9 root-close assembly pipeline pass (`END_EXPOSURE`), Stage 2 (`GROW`) evaluated the consolidated reciprocal graph $W^*$. High mutual support in the shared co-active context caused Assembly 5 to recruit Assembly 6's cells and vice versa, converging to 8 identical cells:
   `[8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116]`.
   At Root 10, both recruited cell `12117`, reaching their final 9-cell membership tuple.
3. **Consolidation Lock via Frozen Specification Contract (Roots 9–56):**
   In every root from 9 through 56, `_try_merge_pair(5, 6)` evaluated the pair. Because $A_5 = A_6$, both exclusive sets were empty ($A_5 \setminus A_6 = \emptyset, A_6 \setminus A_5 = \emptyset$). By the explicit rule of Core §2.0 item 4 (`empty exclusive side => 0`), `between_strength` was set to `0.0`. Consequently, `0.0 < THETA_OB (0.40)` rejected the merge in all 48 consecutive opportunities.
4. **Exact Readout Score Tie (Root 56, Eagle Step 2):**
   At Step 2 of Eagle autonomous rollout (`ماء` $\to$ `<EOS>`), Assemblies 5 and 6 computed identical scores:
   $$\text{Score}(A_5) = \text{Score}(A_6) = 0.2069442431 \quad (\text{Q6} = 206944)$$
   With score margin $0.0000000000 < M_{\text{read}} (0.04)$, the generator triggered `StatusCode.AMBIGUOUS` and safely halted with `GEN_STOP_AMBIGUOUS`.

---

## 3. Frozen-Law Compliance Verdict

A central correction of this audit concerns the formal classification of the production MERGE implementation:

### Formal Specification Contract:
`DGCA_CORE_RC4_1.md` §2.0 item 4 explicitly specifies:
$$\text{between\_strength} = \text{mean}\{R_{ij}^B : i \in A \setminus B, j \in B \setminus A\} \quad \mathbf{(empty\ exclusive\ side \implies 0)}$$

### Production Code Under Review:
[`src/dgca/core/assembly.py#L538-L551`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L538-L551):
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

### Formal Compliance Finding:
1. **The production code is 100% compliant with the frozen Core contract.** The conditional `if not excl_a or not excl_b: between_strength = 0.0` is an exact translation of `(empty exclusive side => 0)`.
2. **Not a Software Defect:** It is categorically incorrect to label this implementation as a "bug" or "predicate defect".
3. **Formal Classification:** The observed behavior is classified as a **contract-compliant structural consolidation limitation**.
4. **Tripartite Distinction:**
   - *Implementation Status:* Fully verified and compliant relative to the frozen specification.
   - *Empirical Consequence:* Prevents identical duplicate assemblies from consolidating via MERGE.
   - *Remediation Path:* Any modification constitutes a **formal scientific specification amendment** for R2-B02, requiring Lead Engineer approval, rather than an engineering bug fix.

---

## 4. Verified Facts versus Inferred Conclusions

To ensure scientific integrity, the findings are categorized strictly:

| Phenomenon | Verification Level | Evidentiary Basis |
|:---|:---:|:---|
| **Identity of Members at Root 56** | **Verified Fact** | Bit-exact ordered tuple equality: `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` on both assemblies. |
| **Disjoint Seeds at Birth** | **Verified Fact** | Root 8 state snapshot: $A_5 = \{8834, 9209, 10570\}$ and $A_6 = \{10646, 10915, 11153\}$, $\text{Jaccard} = 0.0000$. |
| **Event 3 Birth Attribution** | **Verified Fact** | Journal verification: all 6 seed cells qualified as fresh emitters strictly during Event 3 (`<EOS>`); 0 qualified in Events 0–2. |
| **Root-Close GROW Execution** | **Verified Fact** | Architecture verification: GROW executes at root close on $W^*$, not inside intra-root event execution passes. |
| **MERGE Rejection Point** | **Verified Fact** | Instrumented logging: all 48 evaluations from Roots 9–56 executed line 551 `return False` with `between_strength = 0.0`. |
| **Readout Score Equality** | **Verified Fact** | IEEE 754 binary float equality: both assemblies scored `0.2069442431` ($\text{Q6} = 206944$) with margin `0.0000000000`. |
| **Downstream Guard Feasibility** | **Verified Fact (Read-Only)** | Read-only evaluation at Root 56: union cardinality ($9 \le 16$), membership limits ($2 \le 12$), and keep guards ($9/9$ pass) all pass. |
| **Dynamic Merge Viability** | **Inferred Hypothesis** | Dynamic effects of generation advance ($7 \to 8$), cooldown ($T_c = 200$), and re-attestation budget remain untested in runtime execution. |
| **Hypothetical Between-Strength = 1.0** | **Refuted Assumption** | Cross-support is mathematically undefined on empty sets ($\emptyset \times \emptyset = \emptyset$); any non-zero value is an axiomatic convention, not an empirical measurement. |

---

## 5. Correct Normative Constants

All parameters are reconciled against `DGCA_CORE_RC4_1.md` §2.0 and production constants in `src/dgca/core/assembly.py`:

| Parameter | Symbol | Correct Normative Value | Previous Report Erratum | Correct Description in Specification |
|:---|:---:|:---:|:---:|:---|
| Core Coverage Threshold | $\rho_{\text{core}}$ | **`0.70`** | `0.40` | Live Assembly core coverage threshold to suppress fresh FORM |
| Membership Capacity | $M_{\text{max}}$ | **`12`** | `2` | Maximum number of live assemblies a cell may belong to |
| Maximum Assembly Size | $K_{\text{max}}$ | **`16`** | `12` | Upper bound on assembly member set cardinality |
| Minimum Assembly Size | $K_{\text{min}}$ | **`3`** | `3` | Lower bound on assembly cardinality (subminimum archived) |
| Merge Jaccard Threshold | $\Theta_{\text{merge}}$ | **`0.70`** | `0.70` | Jaccard similarity threshold for candidate merge pairs |
| Between-Assembly Support | $\Theta_{\text{ob}}$ | **`0.40`** | `0.40` | Mutual support threshold between exclusive member sets |
| Readout Ambiguity Margin | $M_{\text{read}}$ | **`0.04`** | `0.04` | Minimum margin between top-1 and top-2 candidate scores |
| Minimum Reciprocal Degree | $d_{\text{min}}$ | **`2`** | `2` | Minimum reciprocal neighbors within assembly |
| Prospective GROW Density | $\rho_G$ | **`0.50`** | `0.55` | Prospective density threshold for member addition |
| Prospective GROW Specificity | $\sigma_G$ | **`0.30`** | `0.55` | Prospective specificity threshold for member addition |
| MAINTAIN Keep Density | $\rho_{\text{keep}}$ | **`0.35`** | Unstated | Density threshold for retaining members in MAINTAIN |
| MAINTAIN Keep Specificity | $\sigma_{\text{keep}}$ | **`0.20`** | Unstated | Specificity threshold for retaining members in MAINTAIN |
| Merge Cooldown Period | $T_c$ | **`200`** | Unstated | External event cooldown window after MERGE/SPLIT |
| Max FORM per Root | $K_{\text{FORM\_PER\_END}}$ | **`12`** | Unstated | Maximum number of new assemblies formed across one root |

---

## 6. Exact Status of Event Attribution

### Verified Proof of Event 3 Attribution for FORM:
1. In Root 8 (stimulus sequence: `النسر` [0], `يشرب` [1], `ماء` [2], `<EOS>` [3]):
   - **Event 0:** 87 committed cells; 0 live assemblies covered; 16 fresh cells $\to$ Formed Assembly 3 (`[8416, 8575, 8586]`). Seeds for Asm 5 & 6 were **not fresh emitters**.
   - **Event 1:** 87 committed cells; Assembly 4 covered 7 cells; 12 fresh cells $\to$ Formed Assembly 4 (`[9669, 11119, 12123]`). Seeds for Asm 5 & 6 were **not fresh emitters**.
   - **Event 2:** 87 committed cells; Assembly 4 covered 10 cells; 16 fresh cells $\to$ 0 triangles formed. Seeds for Asm 5 & 6 were **not fresh emitters**.
   - **Event 3:** 87 committed cells; Assembly 2 covered 14 cells; exactly 8 fresh cells in $U_t$:
     $$U_t = [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116]$$
     All three seed cells of Assembly 5 (`8834, 9209, 10570`) and all three seed cells of Assembly 6 (`10646, 10915, 11153`) were fresh emitters **strictly in Event 3**.
2. **FORM Conclusion:** Assemblies 5 and 6 are demonstrably and mathematically proven to have formed during the **Event 3 pass** of Stage 3 (`FORM`) in Root 8.

### Correction of GROW Attribution:
- Stage 2 (`GROW`) does not execute per event. In accordance with Core §2.0, GROW executes **once per completed external root at root close** (`END_EXPOSURE`) as part of the post-exposure assembly pipeline pass.
- All prior claims that GROW occurred "during Event 3" have been corrected: GROW executed during the **Root 9 root-close assembly pipeline**.

---

## 7. Downstream Merge Eligibility (Read-Only Counterfactual Analysis)

In the frozen production code, execution in `_try_merge_pair` returned `False` at line 551 (`if between_strength < THETA_OB: return False`).

To determine whether subsequent guards would have blocked the merge if `between_strength` had been satisfied, an independent read-only evaluation was performed against the runtime state:

1. **Union Cardinality Guard:**
   $$|A_5 \cup A_6| = |\{8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117\}| = 9 \le K_{\text{max}} (16) \implies \mathbf{PASS}$$
2. **Membership Capacity Guard:**
   For every member $x$ in the proposed union, the projected live assembly count after archiving $A_6$ and retaining $A_5$ was measured:
   - Cell 12117 belongs to $\{A_2, A_5\} \implies 2 \le M_{\text{max}} (12)$
   - Cells 8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116 belong to $\{A_5\} \implies 1 \le M_{\text{max}} (12)$
   - Result: All 9 cells pass membership capacity $\implies \mathbf{PASS}$.
3. **MAINTAIN Keep Guards on Proposed Union:**
   For every member $x$ in the union tuple, `check_maintain_keep_guards(x, union_tuple, w, n_rec_cache)` was evaluated against the normative thresholds:
   - $d(x, \text{union}) \ge d_{\text{min}} = 2$
   - $D(x, \text{union}) \ge \rho_{\text{keep}} = 0.35$
   - $\text{Spec}(x, \text{union}) \ge \sigma_{\text{keep}} = 0.20$
   - Empirical Result:
     - `8834`: $d=7 \ge 2, D=0.8750 \ge 0.35, \text{Spec}=0.7768 \ge 0.20 \implies$ **PASS**
     - `9209`: $d=8 \ge 2, D=1.0000 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `10570`: $d=7 \ge 2, D=0.8750 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `10646`: $d=8 \ge 2, D=1.0000 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `10915`: $d=8 \ge 2, D=1.0000 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `11153`: $d=7 \ge 2, D=0.8750 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `11583`: $d=6 \ge 2, D=0.7500 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `12116`: $d=7 \ge 2, D=0.8750 \ge 0.35, \text{Spec}=1.0000 \ge 0.20 \implies$ **PASS**
     - `12117`: $d=4 \ge 2, D=0.5000 \ge 0.35, \text{Spec}=0.5712 \ge 0.20 \implies$ **PASS**
   - Result: All 9 cells pass MAINTAIN keep guards on the union $\implies \mathbf{PASS}$.

**Audit Finding:** Under static read-only analysis, all downstream guards would have passed. However, because downstream execution was unreached, overall dynamic merge success remains an untested counterfactual hypothesis.

---

## 8. Attestation & Structural-Generation Constraints

`DGCA_CORE_RC4_1.md` §2.0 and §9.4 define explicit, normative rules regarding structural generation advance and peripheral ledger attestations:

1. **Mandatory Invalidation Contract:**
   > "Each membership change increments structural_generation, invalidating prior ledger readout attestation until re-confirmed."
   > "Any `MERGE/SPLIT/ARCHIVE` invalidates an old matching ledger binding; loss of a printable surface must be reported, never resolved by fetching a historical archived Assembly ID."
2. **Prohibition of Automatic Attestation Transfer:**
   Proposing that a surviving assembly automatically inherits historical attestations from an archived assembly or from its own prior generation directly violates the normative contract.
3. **Prohibition of Archived ID Aliasing:**
   The peripheral ledger cannot resolve readouts by aliasing an archived assembly ID (e.g. $A_6$) to a surviving ID (e.g. $A_5$). Doing so would violate the isolation boundary and permit unconfirmed structural generations to participate in readout.
4. **Attestation Budget Requirement:**
   If Assemblies 5 and 6 merge at Root $R$:
   - Assembly 5's generation increments from 7 to 8.
   - Candidate row `(5, 8)` has 0 confirmed roots.
   - Under `DGCA_CORE_RC4_1.md` §9.4 and `SurfaceReadoutLedgerV1`, at least $\text{MIN\_ATTESTED\_EXTERNAL\_ROOTS} = 2$ distinct completed external roots must subsequently confirm `(5, 8, '<EOS>', Marker.EOS)` before Assembly 5 becomes an attested readout candidate.
   - Autonomous rollout attempted before re-attestation will result in `UNATTESTED_READOUT` or fallback behavior.

---

## 9. Recommended Decision Questions for R2-B02

The R2-B02 design contract must resolve the following formal architectural questions:

1. **Specification Amendment Wording:**
   How should `DGCA_CORE_RC4_1.md` §2.0 item 4 be amended to handle exact duplicate and superset assemblies?
   - *Option A:* Define an explicit bypass: `if Jaccard >= theta_merge and not excl_a and not excl_b:` (bypass `between_strength` check).
   - *Option B:* Define between-strength on empty exclusive sets as satisfying the threshold when Jaccard is 1.0.
2. **Attestation Maturation Schedule:**
   Since merging increments the survivor's structural generation and invalidates prior attestations, how many post-merge training exposures must be budgeted in the curriculum before autonomous generation is evaluated?
3. **Surviving Assembly Identity:**
   Does $\min(\text{ID}_A, \text{ID}_B)$ apply strictly in all cases, or does attestation evidence count influence surviving ID selection?

---

## 10. Verification Suite Results

All test suites were executed on `investigation/r2-b01-assembly-forensics` to confirm baseline stability:

### Master Regression Suite:
```bash
python -m pytest tests/ -q
```
**Result:** `192 passed in 35.66s` (100% PASS).

### Forensic Suite:
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

## 11. Unmodified Frozen Production Baseline

- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Originating Frozen Main:** `faf361b6b95de6287b466eb1dc524ea49c732635`
- **Production Code Changes:** Exactly 0 modifications to `src/dgca/`, `configs/`, or existing test suites.
- **Scope Compliance:** Strictly confined to forensic script refinement and normative documentation reconciliation.

---

## 12. Final Status Declaration

**`R2-B01-C01 VERIFIED — AWAITING FINAL FORENSIC FREEZE`**
