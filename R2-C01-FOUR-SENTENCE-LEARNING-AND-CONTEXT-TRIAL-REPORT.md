# R2-C01 Four-Sentence Learning, Context Discrimination & Memory Retention Trial Report

## EXECUTIVE SUMMARY

This report presents the authoritative scientific audit, empirical findings, and mathematical analysis of **Experiment R2-C01**, the first multi-sequence trial in the DGCA NEXT V2 R2-C series.

The trial investigated whether the frozen DGCA NEXT V2 architecture can autonomously learn, preserve, and retrieve four overlapping Arabic language sequences under a balanced interleaved training schedule without catastrophic interference, fixture assistance, or unauthorized semantic guidance.

**Final Experimental Verdict:**
```
R2-C01 PARTIAL — LEARNING OR CONTEXT DISCRIMINATION INCOMPLETE
```

### Key Quantitative Findings
* **Native Structural Learning (Gate A: PASS):** 121 cells committed in `Region.LANGUAGE`, 1,115 directed synapses formed (798 `LOCAL`, 317 `ASSOCIATIVE`, 662 `CONSOLIDATED`), and 13 LIVE Assemblies formed autonomously without fixtures or teacher intervention.
* **Deterministic Replay (Gate E: PASS):** Bitwise identity reproduced across independent cold starts (`f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`).
* **Read-Only Transaction Integrity (Gate D: PASS):** Bit-for-bit immutability of `WState`, `HSlowState`, `RState`, `SurfaceReadoutLedgerV1`, and `TransactionPublicationView` during generation.
* **Trained Context Retention (Gate B: PARTIAL):** 3 of 4 lexical completions were correctly generated on Step 0 (`الماء`, `التفاح`, `الماء`), but P1 (`القط يشرب`) halted with `GEN_STOP_NO_MATCH` due to associative dilution, and 0 of 4 probes reached `<EOS>` due to lateral runaway saturation in the control pass.
* **Context Discrimination (Gate C: FAIL / PARTIAL):** Multi-branch discrimination succeeded for P2, P3, and P4 at Step 0, and single-token ambiguity (`الطفل`) stopped lawfully (`GEN_STOP_AMBIGUOUS` with margin $0.005879 < M_{\text{read}}$). However, sequence completion to boundary `<EOS>` failed uniformly, and at 112 roots P2 suffered cross-context intrusion (`الماء` $\to$ `يأكل` $\to$ `التفاح`).

---

## 1. EXACT BASELINE AND EXPERIMENT IDENTITIES

* **Authoritative Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
* **Frozen Production Main Baseline SHA:** `f044c20b532f89749675120ffb1d8ada997e3a5e`
* **Isolated Experiment Branch:** `experiment/r2-c01-four-sentence-context`
* **Production Code Modifications:** **ZERO** changes to `src/` or frozen normative specifications (`DGCA_CORE_RC4_1.md`, `DGCA_LLA_RC4_1.md`).
* **Experimental Artifacts Added:**
  - Automated Acceptance Suite: `tests/test_r2_c01_acceptance.py`
  - Forensic Trial Runner: `tools/forensics/run_r2_c01_trial.py`
  - Structured Telemetry Data: `tools/forensics/r2_c01_trial_data.json`
  - Scientific Report: `R2-C01-FOUR-SENTENCE-LEARNING-AND-CONTEXT-TRIAL-REPORT.md`

---

## 2. INPUT CORPUS AND CANONICAL SIC REPRESENTATION

The trial utilized precisely the four authorized Arabic sequences with three lexical events followed by the existing `Marker.EOS` boundary marker:

* **S1:** `القط يشرب الحليب` + `Marker.EOS`
* **S2:** `النسر يشرب الماء` + `Marker.EOS`
* **S3:** `الطفل يأكل التفاح` + `Marker.EOS`
* **S4:** `الطفل يشرب الماء` + `Marker.EOS`

Strict surface integrity was preserved: exact NFC surfaces (`الحليب`, `الماء`, `التفاح`), without substitution of indefinite forms (`حليب`, `ماء`) or non-standard normalization.

### Canonical SIC-V1 Feature Decomposition and Projection
Each event was encoded via frozen mechanical SIC-V1 feature decomposition into sub-word character n-grams. The mechanical projections into `Region.LANGUAGE` produced the following canonical cell footprints:

| Lexical Surface | Boundary / Marker | Canonical Feature Bundle | Distinct F0 Sensory Cells |
| :--- | :--- | :--- | :--- |
| `القط` | `NONE` | `^ال`, `^القط$`, `~لقط`, `قط$` | `(9061, 10595, 11077, 11811)` |
| `يشرب` | `NONE` | `^يش`, `^يشرب$`, `~شرب`, `رب$` | `(8327, 9005, 10167, 10696)` |
| `الحليب` | `NONE` | `^ال`, `^الحليب$`, `~لحلي`, `يب$` | `(8430, 9731, 9910, 10692)` |
| `<EOS>` | `Marker.EOS` | `^<EOS>$`, `~EOS`, `^<E`, `S>$` | `(8728, 10417, 11859, 12117)` |
| `النسر` | `NONE` | `^ال`, `^النسر$`, `~لنس`, `سر$` | `(8589, 9205, 9369, 9487)` |
| `الماء` | `NONE` | `^ال`, `^الماء$`, `~لما`, `اء$` | `(9039, 9534, 11336, 11442)` |
| `الطفل` | `NONE` | `^ال`, `^الطفل$`, `~لطف`, `فل$` | `(8958, 10326, 11140, 11370)` |
| `يأكل` | `NONE` | `^يأ`, `^يأكل$`, `~أكل`, `كل$` | `(9103, 9201, 10087, 11942)` |
| `التفاح` | `NONE` | `^ال`, `^التفاح$`, `~لتف`, `اح$` | `(8916, 10028, 10386, 12202)` |

#### Morphological Feature Sharing Observation
All six definite nouns (`القط`, `النسر`, `الطفل`, `الحليب`, `الماء`, `التفاح`) share the Arabic definite prefix n-gram `^ال` (salience 0.90), which mechanically projects to cells `(8416, 8575, 8586)`. This structural overlap plays a major causal role in assembly formation and ledger tracking.

---

## 3. TRAINING SCHEDULE AND NUMBER OF COMPLETED ROOTS

Cold-start training was executed using a strictly balanced, pre-registered round-robin schedule:
$$\text{Schedule: } \text{Order } [S_1, S_2, S_3, S_4] \text{ cycled cyclically for } root\_id \in [1, 56]$$
$$\text{Sentence Index } = (root\_id - 1) \pmod 4$$

* **Initial Measurement Budget:** 56 completed roots (14 genuine completed roots per sentence).
* **Extended Observation Budget:** 112 completed roots (28 completed roots per sentence).
* **Execution Contract:** Non-adaptive; zero dynamic threshold tuning, learning rate alteration, or training reshuffling.

---

## 4. LEARNING AND STRUCTURAL EVIDENCE

Across 56 roots from cold start ($W_0 = \emptyset$), the system autonomously acquired the following structural architecture:

### Quantitative Structural Milestones

| Metric | Cold Start ($t=0$) | Root 14 | Root 28 | Root 42 | Root 56 | Root 112 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Committed Cells** | 0 | 72 | 108 | 121 | **121** | 121 |
| **Local Synapses** | 0 | 486 | 724 | 788 | **798** | 656 |
| **Associative Synapses** | 0 | 182 | 275 | 308 | **317** | 307 |
| **Consolidated Synapses** | 0 | 148 | 412 | 586 | **662** | 668 |
| **Candidate Synapses** | 0 | 520 | 587 | 510 | **453** | 295 |
| **Live Assemblies** | 0 | 6 | 10 | 13 | **13** | 13 |
| **Tracked Ledger Rows** | 0 | 12 | 21 | 25 | **27** | 29 |
| **Attested Ledger Rows** | 0 | 8 | 17 | 21 | **23** | 25 |

### Discovered Live Assemblies at Root 56

1. **Assembly 1 (gen 10, 12 members):** `(8416, 8420, 8575, 8586, 9007, 9178, 9618, 10220, 10704, 10899, 10933, 12044)` — Formed natively around the shared Arabic definite article `^ال`.
2. **Assembly 2 (gen 7, 9 members):** `(8728, 8834, 9209, 10417, 10570, 10646, 10915, 11859, 12117)` — Canonical `<EOS>` boundary assembly (attested across 48 roots).
3. **Assembly 3 (gen 7, 9 members):** `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` — Co-active `<EOS>` boundary assembly (attested across 48 roots).
4. **Assembly 4 (gen 2, 4 members):** `(8327, 9005, 10167, 10696)` — Lexical `يشرب` assembly (attested across 34 roots).
5. **Assembly 5 (gen 7, 9 members):** `(8651, 9669, 11119, 11195, 11663, 11784, 11807, 12123, 12241)` — Extended `يشرب` assembly (attested across 11 roots).
6. **Assembly 6 (gen 5, 7 members):** `(9039, 9534, 10044, 10308, 10690, 11336, 11442)` — Lexical `الماء` assembly (attested across 20 roots).
7. **Assembly 7 (gen 2, 4 members):** `(8958, 10326, 11140, 11370)` — Lexical `الطفل` assembly (attested across 20 roots).
8. **Assembly 8 (gen 2, 4 members):** `(9061, 10595, 11077, 11811)` — Lexical `القط` assembly (attested across 7 roots).
9. **Assembly 9 (gen 3, 5 members):** `(9103, 9201, 10087, 10318, 11942)` — Lexical `يأكل` assembly (attested across 5 roots at gen 2).
10. **Assembly 10 (gen 5, 7 members):** `(8916, 8961, 10028, 10181, 10386, 10737, 12202)` — Lexical `التفاح` assembly (attested across 6 roots).
11. **Assembly 11 (gen 3, 5 members):** `(8430, 9731, 9910, 9951, 10692)` — Lexical `الحليب` assembly (attested across 6 roots).
12. **Assembly 12 (gen 1, 3 members):** `(9205, 9369, 9487)` — Lexical `النسر` assembly (attested across 6 roots).
13. **Assembly 13 (gen 3, 5 members):** `(9201, 10318, 11641, 11782, 11961)` — Co-active `يأكل` assembly (attested across 4 roots at gen 2).

All assemblies emerged through genuine structural lifecycle dynamics (`FORM`, `GROW`, `MERGE`). Zero manual fixtures or pre-baked graphs were used.

---

## 5. ALL GENERATION TRACES

Read-only generation rollouts were executed via `generate_episode()` ($T_{\text{gen\_max}} = 6, \theta_{\text{read}} = 0.08, M_{\text{read}} = 0.04$).

### Primary Trained-Context Probes (56 Roots)

#### Probe P1: `القط يشرب` (Target: `الحليب` $\to$ `<EOS>`)
* **Step 0:** Readout Status: `NO_MATCH`
  - Winner: `None`
  - Top Score: $0.021402$ (Asm 11 gen 3, `الحليب`, eligible: 2/5 members)
  - Runner-up: $0.000000$ | Margin: $0.021402$ (below $\theta_{\text{read}} = 0.08$)
* **Stop Status:** `GEN_STOP_NO_MATCH`
* **Emitted Surfaces:** `()` (empty)

#### Probe P2: `النسر يشرب` (Target: `الماء` $\to$ `<EOS>`)
* **Step 0:** Readout Status: `OK`
  - Winner: Assembly 6, Generation 5
  - Top Score: $0.625366$ | Runner-up: $0.326347$ (Asm 11 gen 3) | Margin: $0.299019$
  - Emitted Surface: `الماء` (Marker: `NONE`)
* **Step 1:** Readout Status: `OK` (Neural Winner)
  - Winner: Assembly 9, Generation 3 (`يأكل`)
  - Top Score: $0.096262$ | Runner-up: $0.000000$ | Margin: $0.096262$
  - Ledger Resolution: `READOUT_UNKNOWN` (Asm 9 mutated to gen 3 at root 55 with count 1 < 2; non-retroactive attestation applies)
* **Stop Status:** `GEN_STOP_READOUT_UNKNOWN`
* **Emitted Surfaces:** `('الماء',)`

#### Probe P3: `الطفل يأكل` (Target: `التفاح` $\to$ `<EOS>`)
* **Step 0:** Readout Status: `OK`
  - Winner: Assembly 10, Generation 5
  - Top Score: $0.482176$ | Runner-up: $0.000000$ | Margin: $0.482176$
  - Emitted Surface: `التفاح` (Marker: `NONE`)
* **Step 1:** Readout Status: `NO_MATCH`
  - Winner: `None`
  - Top Score: $0.000000$ | Runner-up: $0.000000$ | Margin: $0.000000$
* **Stop Status:** `GEN_STOP_NO_MATCH`
* **Emitted Surfaces:** `('التفاح',)`

#### Probe P4: `الطفل يشرب` (Target: `الماء` $\to$ `<EOS>`)
* **Step 0:** Readout Status: `OK`
  - Winner: Assembly 6, Generation 5
  - Top Score: $0.624067$ | Runner-up: $0.326783$ (Asm 11 gen 3) | Margin: $0.297284$
  - Emitted Surface: `الماء` (Marker: `NONE`)
* **Step 1:** Readout Status: `NO_MATCH`
  - Winner: `None`
  - Top Score: $0.034556$ | Runner-up: $0.000000$ | Margin: $0.034556$
* **Stop Status:** `GEN_STOP_NO_MATCH`
* **Emitted Surfaces:** `('الماء',)`

---

### Extended Observation Probes (112 Roots)

At 112 roots, the identical evaluation protocol produced:
* **P1 (`القط يشرب`):** Top score $0.042544 < \theta_{\text{read}} = 0.08$ $\to$ `GEN_STOP_NO_MATCH`. Emitted `()`.
* **P2 (`النسر يشرب`):**
  - Step 0: `الماء` (Asm 6 gen 5, score $0.561658$, margin $0.311727$)
  - Step 1: `يأكل` (Asm 9 gen 3, score $0.082090$, margin $0.082090$) — now attested after additional exposures
  - Step 2: `التفاح` (Asm 10 gen 5, score $0.460725$, margin $0.460725$)
  - Step 3: `NO_MATCH` (score $0.000000$)
  - **Emitted Surfaces:** `('الماء', 'يأكل', 'التفاح')` $\to$ Stop `GEN_STOP_NO_MATCH`. (Demonstrates cross-context syntactic intrusion from S3).
* **P3 (`الطفل يأكل`):** Step 0 emits `التفاح` (Asm 10 gen 5, score $0.459695$), Step 1 `NO_MATCH` ($0.000000$) $\to$ Stop `GEN_STOP_NO_MATCH`.
* **P4 (`الطفل يشرب`):** Step 0 emits `الماء` (Asm 6 gen 5, score $0.561153$), Step 1 `NO_MATCH` ($0.015812$) $\to$ Stop `GEN_STOP_NO_MATCH`.

---

### Context Ambiguity Probes

#### Ambiguity Probe A1: `الطفل` (Prefix shared by S3 and S4)
* **Step 0:** Readout Status: `AMBIGUOUS`
  - Top Candidate: Assembly 4 gen 2 (`يشرب`), score: $0.524701$
  - Second Candidate: Assembly 9 gen 2 (`يأكل`), score: $0.518821$
  - Runner-up Margin: $0.005879 < M_{\text{read}} = 0.04$
* **Stop Status:** `GEN_STOP_AMBIGUOUS`
* **Emitted Surfaces:** `()` (empty)
* **Audit Finding:** The model safely detected the branching ambiguity between `يشرب` and `يأكل` without unlawfully guessing or forcing an arbitrary winner.

#### Ambiguity Probe A2: `يشرب` (Prefix shared by S1, S2, S4)
* **Step 0:** Readout Status: `OK`
  - Winner: Assembly 6 gen 5 (`الماء`), score: $0.626052$ | Second: $0.327223$ | Margin: $0.298830$
  - Emitted Surface: `الماء`
* **Step 1:** Readout Status: `AMBIGUOUS`
  - Margin: $0.005923 < M_{\text{read}} = 0.04$
* **Stop Status:** `GEN_STOP_AMBIGUOUS`
* **Emitted Surfaces:** `('الماء',)`
* **Audit Finding:** `الماء` followed `يشرب` in two sentences (S2 and S4 = 28 roots), whereas `الحليب` followed in one sentence (S1 = 14 roots). The 2:1 training root frequency legitimately favored `الماء` at Step 0, followed by a lawful ambiguity stop at Step 1.

---

### Unsupported Combination Diagnostics

#### Diagnostic U1: `النسر يأكل` (Unobserved in training)
* **Step 0:** Emitted `التفاح` (Asm 10 gen 5, score $0.482145$, margin $0.482145$)
* **Step 1:** Stop `GEN_STOP_NO_MATCH` (score $0.000000$)
* **Emitted Surfaces:** `('التفاح',)`

#### Diagnostic U2: `القط يأكل` (Unobserved in training)
* **Step 0:** Emitted `التفاح` (Asm 10 gen 5, score $0.482145$, margin $0.482145$)
* **Step 1:** Stop `GEN_STOP_NO_MATCH` (score $0.000000$)
* **Emitted Surfaces:** `('التفاح',)`

* **Diagnostic Analysis:** Neither relationship exists in the training data. The model emitted `التفاح` purely because `يأكل` had strong direct associative connections to `التفاح` learned from S3, and neither `النسر` nor `القط` provided any inhibitory contextual bias to suppress `يأكل -> التفاح`.

---

## 6. CORRECT AND INCORRECT CONTINUATIONS

| Probe | Prefix | Expected Continuation | Observed Continuation | Stop Code | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P1** | `القط يشرب` | `الحليب` $\to$ `<EOS>` | `()` (empty) | `GEN_STOP_NO_MATCH` | **INCORRECT** |
| **P2 (56r)** | `النسر يشرب` | `الماء` $\to$ `<EOS>` | `('الماء',)` | `GEN_STOP_READOUT_UNKNOWN` | **PARTIAL** |
| **P2 (112r)**| `النسر يشرب` | `الماء` $\to$ `<EOS>` | `('الماء', 'يأكل', 'التفاح')`| `GEN_STOP_NO_MATCH` | **INCORRECT** |
| **P3** | `الطفل يأكل` | `التفاح` $\to$ `<EOS>` | `('التفاح',)` | `GEN_STOP_NO_MATCH` | **PARTIAL** |
| **P4** | `الطفل يشرب` | `الماء` $\to$ `<EOS>` | `('الماء',)` | `GEN_STOP_NO_MATCH` | **PARTIAL** |
| **A1** | `الطفل` | Ambiguous (`يأكل` / `يشرب`) | `()` (empty) | `GEN_STOP_AMBIGUOUS` | **CORRECT** |
| **A2** | `يشرب` | Biased (`الماء` 2:1 `الحليب`) | `('الماء',)` | `GEN_STOP_AMBIGUOUS` | **CORRECT** |
| **U1** | `النسر يأكل` | Diagnostic | `('التفاح',)` | `GEN_STOP_NO_MATCH` | **DIAGNOSTIC** |
| **U2** | `القط يأكل` | Diagnostic | `('التفاح',)` | `GEN_STOP_NO_MATCH` | **DIAGNOSTIC** |

---

## 7. READOUT AND ATTESTATION EVIDENCE

### Peripheral Ledger Integrity
* `SurfaceReadoutLedgerV1` strictly respected `ZERO_SELECTION_LEAKAGE`: neural candidate ranking evaluated purely on cell activation gain without consulting peripheral metadata.
* Non-retroactive attestation (Core §9.4, LG-T03) correctly prevented newly mutated Assembly 9 gen 3 from claiming attestation from generation 2, causing the graceful halt `GEN_STOP_READOUT_UNKNOWN` in P2 at Step 1.
* Zero hash collisions or unhandled duplicate assemblies occurred in the ledger.

### Morphological Prefix Hyper-Attestation (Assembly 1)
Due to Arabic orthographic conventions where the definite article `ال` is prefixed without a space, SIC-V1 character n-gram extraction produced identical features (`^ال`, salt order cells `8416, 8575, 8586`) across all six nouns. As a result, Assembly 1 accumulated attestations for `التفاح`, `الحليب`, `الطفل`, `القط`, `الماء`, and `النسر`. However, during neural competition, specific lexical assemblies (Asm 6, 7, 8, 10, 11, 12) consistently outscored Assembly 1 for distinct tokens.

---

## 8. INTERFERENCE FINDINGS AND CAUSAL FORENSIC ANALYSIS

Deep forensic investigation revealed four distinct mechanical phenomena governing the model's behavior:

### Finding 1: Frequency-Biased Associative Dilution
In the balanced interleaved training schedule:
* `يشرب -> الماء` appeared in both S2 and S4 (total 28 exposures at 56 roots).
* `يشرب -> الحليب` appeared only in S1 (total 14 exposures at 56 roots).

Because non-consolidated synapses are strictly masked during GENERATE (`mask_nonconsolidated=True`), associative links require sufficient evidence accumulation ($E_{\text{ext}} \ge E_{\text{thresh}}$ across multiple roots) to become active. Under 2:1 competition, the sensory cells of `يشرب` (`8327, 9005, 10167, 10696`) repeatedly fired when followed by `الماء`, preventing the synapses leading to `الحليب` from consolidating. At root 56, all direct associative synapses from `يشرب` to `الحليب` remained in `CANDIDATE` state and were masked out during generation.

### Finding 2: Context Candidate Fan-Out Bottleneck
Only a single contextual binding was formed:
$$\text{StableBinding } 8320: z=8320, \text{ anchor}=8327 (\text{يشرب}), \text{ } p\_sources=(9061, 10595) (\text{القط})$$

Under DGCA Core §7.4, a contextual candidate $z$ has a rigid $2\text{-}P / 2\text{-}C / 2\text{-}Y$ architecture with exactly 2 forward projection targets ($Y_1, Y_2$). Consequently:
* Cell $8320$ wired only to cells $8430$ and $9731$.
* Cells $9910, 9951, 10692$ of Assembly 11 received zero contextual drive.
* At generation time, with direct synapses masked, only 1 cell ($8430$) had an active consolidated connection, yielding an assembly score of:
$$\text{Score}(\text{Asm } 11) = \frac{0.075638 + 0.031370 + 0 + 0 + 0}{5} = 0.021402 < \theta_{\text{read}} (0.08)$$
This resulted directly in the `NO_MATCH` halt for P1.

### Finding 3: Runaway Lateral Saturation in the CONTROL Pass
None of the four probes reached `<EOS>` after emitting their terminal lexical tokens (`الماء`, `التفاح`). Forensic tracing of Step 1 revealed that:
$$\text{Score}(\text{Asm } 2) = \text{Score}(\text{Asm } 3) = 0.000000$$
$$\text{Gain}_j = \max(0.0, A_j(\text{FULL}) - A_j(\text{CONTROL})) = 0.000000 \quad \forall j$$

In DGCA Core §9.2, the CONTROL pass sets $P^T = 0$ (`control_zero_pt=True`), but does **not** suppress the spatial lateral drive $\sigma_j$ (`compute_spatial_lateral_drive`). Over 56 roots, dense local recurrent synapses ($S \approx 1.0$) developed across committed cells. When a terminal token was re-injected, its active cells triggered runaway lateral spread through local synapses. In the CONTROL pass, this spatial drive saturated all 92 Language cells to $A_j(\text{CONTROL}) = 1.000000$. Because activations are bounded in $[0, 1]$, $A_j(\text{FULL})$ could not exceed $1.0$, collapsing the differential causal gain to zero:
$$\text{Gain}_j = 1.0 - 1.0 = 0.0 \implies \text{Score} = 0.0 \implies \text{GEN\_STOP\_NO\_MATCH}$$

### Finding 4: Cross-Context Syntactic Intrusion
At 112 roots, extended training strengthened associative connections between `الماء` and `يأكل`, causing P2 (`النسر يشرب`) to chain into S3: `الماء` $\to$ `يأكل` $\to$ `التفاح`. Without negative contextual suppression or phrase-level boundaries, individual token-to-token associative pathways create spurious cross-sentence traversals.

---

## 9. DETERMINISTIC REPLAY RESULTS

Deterministic replay was tested by executing two independent cold-start trials from root 1 through 56 under identical canonical inputs and schedules:

* **Trial 1 Full State SHA-256 Digest:**
  `f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`
* **Trial 2 Full State SHA-256 Digest:**
  `f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`
* **Bitwise Determinism Match:** **100% IDENTICAL (`True`)**

### State Immutability Verification
State hashes before and after executing all primary, ambiguity, and unsupported generation probes:
* Pre-GENERATE State SHA-256: `f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`
* Post-GENERATE State SHA-256: `f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`
* Pre-GENERATE Ledger Digest: Matches Post-GENERATE Ledger Digest bit-for-bit (`True`).
* Zero state leakage or learning occurred during read-only generation.

---

## 10. SAVE / LOAD RESULTS

In accordance with normative Phase F specifications, complete cross-process disk persistence (`serialize_machine_state`, `save_checkpoint`) is intentionally not implemented in `dgca.common.serialization`.
* Test assertion in `tests/test_r2_c01_acceptance.py::test_r2_c01_save_load_contract` verified the absence of unauthorized disk serialization functions.
* Complete in-memory deep snapshot serialization and canonical hashing (`canonical_state_digest`) were verified to achieve 100% field coverage and bitwise equivalence across independent machine instances.

---

## 11. SCIENTIFIC LIMITATIONS

1. **Contextual Fan-Out Capacity:** The rigid $2\text{-}P / 2\text{-}C / 2\text{-}Y$ architecture limits a single context candidate $z$ to driving at most 2 downstream cells. Assemblies of size $K \ge 5$ cannot be reliably driven by a single context cell without dense collateral recruitment.
2. **Causal Gain Collapse from Lateral Saturation:** In densely trained networks, lateral spatial drive $\sigma$ spreads unchecked in the CONTROL pass, causing $A(\text{CONTROL}) \to 1.0$ and wiping out the differential gain needed for readout.
3. **Morphological N-Gram Conflation:** Sub-word character n-gram encoding without morphological segmentation causes shared prefixes (e.g. Arabic `^ال`) to create hyper-generalized assemblies that cross lexical boundaries.

---

## 12. FULL REGRESSION RESULTS

Execution of the authoritative regression suite after adding the R2-C01 experimental harness and acceptance tests:

```bash
python -m pytest tests/test_r2_c01_acceptance.py -v
```
* **Collected Items:** 7
* **Passed Items:** 7 (100%)
* **Failures:** 0

Combined regression suite status:
* **Pre-Trial Baseline:** 215 passed
* **Post-Trial Suite:** **222 passed, 0 failed** in 248.59s.

---

## 13. GATE-BY-GATE EVALUATION

| Gate | Description | Authorized Criterion | Experimental Outcome | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Gate A** | **Genuine Learning** | Evidence-backed native structural & synaptic learning without fixtures. | 121 cells, 1,115 synapses (662 consolidated), 13 live assemblies formed natively. | **PASS** |
| **Gate B** | **Memory Retention** | All 4 observed sequences retrievable after interleaved training. | P2, P3, P4 generated correct next word; P1 failed (dilution); 0 reached `<EOS>`. | **PARTIAL** |
| **Gate C** | **Context Discrimination**| Probes discriminate context and reach `<EOS>` without cross-branch substitution.| P2, P3, P4 discriminate at Step 0; P1 failed; `<EOS>` unreached; 112r intrusion. | **FAIL** |
| **Gate D** | **Transaction Integrity** | Zero mutation, leakage, stale readout, or publication regression. | Bit-for-bit SHA-256 match before and after generation across all state partitions. | **PASS** |
| **Gate E** | **Deterministic Replay** | Identical canonical replay across independent cold starts. | Run 1 and Run 2 match bit-for-bit (`f7739b01...`). | **PASS** |
| **Gate F** | **Generalization** | Compositional generalization beyond trained sequences. | Diagnostic probes (`النسر يأكل`, `القط يأكل`) emitted `التفاح`; not proof of generalization. | **NOT PROVEN** |

---

## 14. EVIDENCE NEEDED BEFORE PLANNED FULL-TEXT EXPERIMENT

Before scaling DGCA NEXT V2 to larger or full-text corpora, the following architectural and mathematical challenges must be formally addressed:

1. **Lateral Inhibition or Control Gating:** The FULL vs CONTROL readout formulation requires an effective lateral damping mechanism (e.g., inhibition or local normalization) to prevent the CONTROL pass from saturating when $P^T = 0$.
2. **Contextual Recruitment Scaling:** Contextual representations must support broader target fan-out (or multi-cell contextual assemblies) to drive complete $K$-member assemblies ($K \ge 5$).
3. **Frequency-Compensated Synaptic Homeostasis:** Learning laws must prevent frequent transitions from completely starving lower-frequency competing branches.
4. **Morphological Token Segmentation:** SIC encoding for morphologically rich languages must differentiate prefix clitics (`ال`) from word roots to prevent spurious hyper-attestation.

---

## 15. FINAL VERDICT

In accordance with Section 12 of the R2-C01 specification:

```
R2-C01 PARTIAL — LEARNING OR CONTEXT DISCRIMINATION INCOMPLETE
```

* Zero production patches were applied to force an artificial pass.
* All experimental findings, harnesses, and test suites are strictly contained within branch `experiment/r2-c01-four-sentence-context`.
* No changes will be merged into `main`.
