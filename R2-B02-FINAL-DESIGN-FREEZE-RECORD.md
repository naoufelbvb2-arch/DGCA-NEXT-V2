# DGCA NEXT V2 — R2-B02

## Final Design Freeze Record — Exact-Duplicate Assembly Consolidation

| Parameter | Specification |
| :--- | :--- |
| **Document Version** | `1.0.0-final-freeze` |
| **Authoritative Baseline** | `faf361b6b95de6287b466eb1dc524ea49c732635` (`main`) |
| **Investigation Branch** | `investigation/r2-b01-assembly-forensics` |
| **Verified Starting HEAD** | `2fc30a10b2afd1e21b6e1a11082120a23ee7f2c0` |
| **Accepted Forensic Evidence** | `205efa0e664dc26f31f131d5efc19ac37b3eb95d` |
| **Primary Design Contract** | [`R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B02-EXACT-DUPLICATE-CONSOLIDATION-DESIGN-CONTRACT.md) (`v2.2.0-frozen`) |
| **Design Freeze Identifier** | `DGCA-R2-B02-DESIGN-FROZEN-20261030` |
| **Target Implementation Phase** | Patch R2-B03 (Controlled Implementation Gate) |
| **Status** | **FORMALLY FROZEN — R2-B03 IMPLEMENTATION READY** |

---

## 1. Accepted Scientific Design

The formal scientific architecture for exact-duplicate assembly consolidation is **Alternative A (Explicit Exact-Duplicate Structural Branch)**.
- **Problem Resolution:** Addresses the boundary condition in Core §2.0 Operator 4 (`MERGE`) where identical assemblies ($A \equiv B$) produce empty exclusive sets ($A \setminus B = \emptyset \land B \setminus A = \emptyset$), causing the exclusive-set mutual-support formula to evaluate over an empty Cartesian product and evaluate to $0.0 < \Theta_{\text{ob}}$, improperly rejecting consolidation.
- **Structural Branch (Branch 4a):**
  If two live assemblies have identical cell memberships:
  $$\text{Members}(A) \equiv \text{Members}(B) \iff A \setminus B = \emptyset \land B \setminus A = \emptyset$$
  the pair is immediately recognized as an exact duplicate pair and satisfies the mutual-support gate.
- **Partial Overlap (Branch 4b):**
  For non-identical assembly pairs ($A \setminus B \ne \emptyset \land B \setminus A \ne \emptyset$), the existing frozen formula and threshold evaluation remain 100% untouched:
  $$\text{BetweenStrength}(A, B) = \frac{1}{|A \setminus B| \cdot |B \setminus A|} \sum_{i \in A \setminus B} \sum_{j \in B \setminus A} R^B_{i, j}(W) \ge \Theta_{\text{ob}} = 0.40$$
- **Identity & Lifecycle Invariant:** Lower numeric ID survives ($\min(a, b)$); higher numeric ID transitions to `AssemblyStatus.ARCHIVED` permanently. Both assemblies increment structural generation by 1 (`asm_a.structural_generation += 1`, `asm_b.structural_generation += 1`). Merge cooldown of $T_c = 200$ completed external events applies to both.

---

## 2. Frozen Normative Parameters

All structural, neural, and peripheral parameters are verified against `DGCA_CORE_RC4_1.md` and frozen production code:

| Parameter | Frozen Value | Defining Source | Operational Invariant |
| :--- | :---: | :--- | :--- |
| $\Theta_{\text{merge}}$ | `0.70` | `src/dgca/core/assembly.py` line 45 | Minimum Jaccard overlap for MERGE eligibility. |
| $\Theta_{\text{ob}}$ | `0.40` | `src/dgca/core/assembly.py` line 46 | Minimum exclusive-set mutual support for partial overlap (Branch 4b). |
| $K_{\text{max}}$ | `16` | `src/dgca/core/assembly.py` line 36 | Maximum assembly cell capacity ($K_{\text{min}} = 3$). |
| $M_{\text{max}}$ | `12` | `src/dgca/core/assembly.py` line 37 | Maximum live assembly memberships per committed cell. |
| $T_c$ | `200` | `src/dgca/core/assembly.py` line 47 | Cooldown window in completed external events post-mutation. |
| $\text{MIN\_ATTESTED\_EXTERNAL\_ROOTS}$ | `2` | `src/dgca/peripheral/readout_ledger.py` line 21 | Minimum distinct completed external roots for candidate attestation. |
| $M_{\text{read}}$ | `0.04` | `src/dgca/core/generator.py` line 38 | Readout score ambiguity margin gate. |
| $\rho_{\text{core}}$ | `0.70` | `src/dgca/core/assembly.py` line 40 | Minimum core event coverage threshold. |
| $\Theta_{\text{fresh}}$ | `0.50` | `src/dgca/core/assembly.py` line 42 | Minimum fresh emitter overlap threshold. |

---

## 3. Exact Implementation Boundaries

When implementation is authorized under R2-B03, changes must strictly observe the following boundaries:

### Permitted Implementation Scope
- Strictly confined to `_try_merge_pair()` in [`src/dgca/core/assembly.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/assembly.py#L511-L552):
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

### Strictly Forbidden Modifications
- **Forbidden:** No modification to `FORM`, `GROW`, `MAINTAIN`, or `SPLIT`.
- **Forbidden:** No modification to `src/dgca/peripheral/readout_ledger.py` or `src/dgca/peripheral/outbox.py`.
- **Forbidden:** No modification to `TransactionPublicationView` or `ExposureTransactionManager` in `src/dgca/lifecycle/exposure_tx.py`.
- **Forbidden:** No modification to `src/dgca/core/generator.py` candidate selection or fallback mechanics.
- **Forbidden:** No introduction of `src/dgca/core/transaction.py` (nonexistent path).
- **Forbidden:** No custom notification schemas (`AssemblyMutationNotification`) or custom transaction status codes.
- **Forbidden:** No synthesis of artificial ledger attestations or cross-generation evidence transfer.

---

## 4. Corrected Ledger Provenance

Under the frozen Outbox contract (`src/dgca/peripheral/outbox.py`), an assembly emits an outbox notification if and only if:
1. It existed `LIVE` before the witnessed external event.
2. It remained `LIVE` after root close.
3. Its `structural_generation` remained completely unchanged across the observation/publication boundary of the entire root.
4. Event-time core coverage satisfies $C_t \ge \rho_{\text{core}} = 0.70$ and freshness satisfies $M_{\text{fresh}} \ge \Theta_{\text{fresh}} = 0.50$.

### Provenance Audit Across Curriculum Roots
- **Root 8:** Assemblies 5 & 6 were born during the Event 3 (`Marker.EOS`) pass at root close. They did not exist `LIVE` prior to Event 3.
- **Root 9:** Assemblies 5 & 6 underwent Stage 2 GROW at root close (advancing Gen 1 to Gen 6), and under consolidation, Stage 4 MERGE advanced survivor $A_5$ to Gen 7. Neither assembly held a stable generation across Root 9 events.
- **Root 10:** Survivor $A_5$ was at Gen 7 during events, but Stage 2 GROW at root close mutated its generation to Gen 8. Its generation was not stable across Root 10.
- **Ledger Invariant:** Consequently, at Root 10 close, no speculative historical rows `(5, 6)`, `(6, 6)`, or `(5, 7)` exist in the ledger.
- **Candidate Key (5, 8):** At Root 10 close, the candidate map for key `(5, 8)` is strictly **EMPTY**:
  $$\text{get\_candidate\_rows}(5, 8) \equiv () \implies \text{external\_count} = 0$$
- **Pre-Existing Historical Records:** Any historical ledger records genuine to earlier roots remain immutable in ledger storage, but are strictly excluded from Gen 8 queries by key mismatch (`(5, 8) != (5, g)` for $g < 8$).

---

## 5. Final Acceptance Test Requirements

The mandatory acceptance test suite for R2-B03 consists of sixteen verified specifications:

### Primary Validation Suite (7 Experiments)
1. **EXP-B02-01 (Exact Duplicate Consolidation):** Replay Root 9 where Assemblies 5 & 6 converge to 8 identical cells; verify $A_5$ remains `LIVE` (Gen 7 post-merge) and $A_6$ transitions to `ARCHIVED` (Gen 7); single assembly published; cooldown applied.
2. **EXP-B02-02 (Partial Overlap Invariance):** Synthetic pair with 8 shared cells, 2 exclusive cells, $R^B = 0.50 \ge \Theta_{\text{ob}} = 0.40$; merges legally under Branch 4b with verified between-strength calculation.
3. **EXP-B02-03 (Proper Subset Rejection):** Synthetic pair with $A \subset B$ ($|A|=4, |B|=5$); merge rejected with `between_strength = 0.0 < THETA_OB`.
4. **EXP-B02-04 (Ledger Generation Safety):** Query readout immediately post-consolidation without external exposure; candidate key `(5, 8)` returns 0 rows; generator halts fail-closed with `GEN_STOP_READOUT_UNKNOWN`.
5. **EXP-B02-05 (Post-Merge Re-Attestation):** Expose consolidated model to 2 independent qualifying external roots containing `<EOS>`; verify Root 1 yields `external_count = 1` (readout remains unknown); Root 2 yields `external_count = 2` (attested); subsequent readout evaluates $A_5$ against ledger.
6. **EXP-B02-06 (56-Root Curriculum Replay):** Full 56-root curriculum with consolidation active at Root 9; evaluate state determinism across dual replays and measure actual candidate rankings without assuming automatic generation success.
7. **EXP-B02-07 (Transaction Fault Semantics):** Verify ordinary ineligibility returns `False` without aborting; verify injected shadow exception discards shadow mutations while preserving legal `OPEN` sensory states.

### Negative Test Suite (9 Tests)
1. **EXP-B02-NEG-01 (Single External Confirmation):** Single post-merge root yields `external_count = 1 < 2`; ledger returns `READOUT_UNKNOWN`; generator halts fail-closed (`GEN_STOP_READOUT_UNKNOWN`).
2. **EXP-B02-NEG-02 (Repeated Observations Within Root):** Multiple `<EOS>` events within the same external root deduplicate by `root_id`; `len(confirmed_roots) == 1`; attestation blocked.
3. **EXP-B02-NEG-03 (Old-Generation Evidence Invalidation):** Readout queried at Gen 8 against historical evidence for older generations ($g < 8$); strict key mismatch `(5, 8) != (5, g)` returns 0 rows; generation invalidation enforced.
4. **EXP-B02-NEG-04 (Same-Surface / Differing-Bundle Conflict):** Injected conflicting feature bundle for same surface string triggers `READOUT_AMBIGUOUS_PENDING`; readout halts fail-closed.
5. **EXP-B02-NEG-05 (Proper Subset Absorption Attempt):** Pair with $A \subset B$ evaluates to `False`; no subset absorption.
6. **EXP-B02-NEG-06 (Cooldown Bypass Attempt):** Identical pair evaluated while elapsed events $< T_c = 200$; consolidation rejected by cooldown guard.
7. **EXP-B02-NEG-07 (Archived Assembly Governance):** Archived $A_6$ strictly excluded from neural ranking; zero alias resolution from $A_6$ to $A_5$; zero evidence transfer from $A_6$ to $A_5$; historical ledger records for $A_6$ remain immutable when present; autonomous readout requires legal `LIVE` assembly at current generation.
8. **EXP-B02-NEG-08 (Peripheral Selection Leakage):** Neural candidate competition strictly ignores peripheral ledger rows; winner determined solely by continuous activation overlap (`LG-T12`).
9. **EXP-B02-NEG-09 (Ordinary Ineligibility Continuity):** Ineligible pair in Stage 4 returns `False`; loop proceeds to next candidate pair; transaction does not abort.

---

## 6. Git Commit & Source Provenance

- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Active Branch:** `investigation/r2-b01-assembly-forensics`
- **Starting Task HEAD:** `2fc30a10b2afd1e21b6e1a11082120a23ee7f2c0`
- **Frozen Main SHA:** `faf361b6b95de6287b466eb1dc524ea49c732635`
- **Accepted Forensic Evidence SHA:** `205efa0e664dc26f31f131d5efc19ac37b3eb95d`

---

## 7. Confirmation of Zero Production Changes

Full repository audit confirms:
- Source directory (`src/dgca/`): **0 files modified**
- Test directory (`tests/`): **0 files modified**
- Configuration files (`pyproject.toml`, etc.): **0 files modified**
- Forensic evidence digests: **0 files modified**
- Scope of work: Strictly bounded to documentation and specification freeze records.

---

## 8. Authorization Boundary for R2-B03

This document represents the formal closure of phase **R2-B02 (Design & Specification Freeze)**.
- **Zero implementation is authorized under R2-B02.**
- Implementation of the exact-duplicate structural branch is deferred to **Patch R2-B03**.
- Transition to R2-B03 requires explicit Lead Engineer approval.

---

## Final Freeze Declaration

$$\mathbf{R2-B02\ FINAL\ DESIGN\ FROZEN\ \text{—}\ R2-B03\ IMPLEMENTATION\ READY}$$
