# DGCA NEXT V2 — R1-F02-C01 CRITICAL EVIDENCE CORRECTION REPORT

**Document Version:** 1.0  
**Author:** Independent Scientific Verification Engineer  
**Audit Stage:** R1-F02-C01 Evidence Correction & Verification  
**Repository:** `https://github.com/naoufelbvb2-arch/DGCA-NEXT-V2.git`  
**Pinned Baseline:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Previous Audit Commit:** `87ef197ee0f8183ba6e7ceb94b701b73e1a0bc56`  
**Audit Branch:** `audit/r1-f02-c01-eos-verification`  
**Final Disposition:** **`R1-F02-C01 PARTIALLY VERIFIED — OPEN EVIDENCE GAPS`**

---

## 1. EXECUTIVE SUMMARY

Following review by the Lead Engineer, an investigation was conducted into the experimental methodology used during the R1-F02 EOS verification. 

### Key Findings:
1. **Critical Discrepancy Confirmed:** The committed R1-F02 test `test_f01_task6_eos_learning_and_multistep_rollout` re-encoded the raw string `"<EOS>"` using `encode_lexical_token_event()`. This replaced canonical EOS special features with lexical n-grams and produced a completely different feature bundle digest.
2. **Outbox Mismatch Guard Bypassed:** Despite the digest mismatch between the re-encoded Core event and the peripheral envelope, the outbox did NOT reject the event. The outbox implementation checks `ev_digest = getattr(ev, "feature_bundle_digest", None)`, but `EventExecutionResult` has no `feature_bundle_digest` attribute (`ev_digest is None`). The mismatch guard was completely bypassed in production code.
3. **Reproduction of 93-Pass Claim:** The test suite does pass with 93 passes on commit `87ef197ee0f8183ba6e7ceb94b701b73e1a0bc56`, but it passed on a **scientifically flawed premise** (lexical cells recruited for string `"<EOS>"` rather than canonical special tokens).
4. **Canonical EOS Learning Verified:** When canonical EOS events (`\x1fEOS#0`, `\x1fEOS#1`, `\x1fEOS#2`) are passed into the pipeline using identity-preserving reconstruction (`dataclasses.replace`), sensory cells commit, LOCAL synapses form, and 3 canonical EOS Assemblies (2, 5, 6) are born and receive independent attestations with `Marker.EOS`.
5. **Autonomous Generation Asymmetry & M01 Blocker:**
   - On the **Cat branch** (`['القط']`), autonomous generation produces `['يشرب', 'حليب']` and cleanly halts at `<EOS>` with `GEN_STOP_EOS` through genuine neural selection of Assembly 2 (score $0.6484$, margin $0.1366 > 0.02$).
   - On the **Eagle branch** (`['النسر']`), generation produces `['يشرب', 'ماء']`, but fails on the terminal step: Assemblies 5 & 6 (which are **exact structural duplicates**, finding R1-M01) both score identical $0.206944$, creating an exact tie (margin $0.000000 < 0.02$), halting generation with `StatusCode.GEN_STOP_AMBIGUOUS`.
6. **Overall Disposition:** Because autonomous generation succeeds on one branch but is blocked on the rival branch by natural Assembly duplication (R1-M01), the evidence is classified as **`R1-F02-C01 PARTIALLY VERIFIED — OPEN EVIDENCE GAPS`**.

---

## 2. INVESTIGATION OF THE EOS ENCODING DISCREPANCY

### 2.1 Canonical vs Re-encoded Feature & Digest Telemetry

| Property | Canonical EOS Event (`encode_exposure`) | Re-encoded Event (`encode_lexical_token_event('<EOS>')`) | Match? |
| :--- | :--- | :--- | :---: |
| **Event Marker** | `Marker.EOS` (1) | `Marker.LEXICAL` (0) | **NO** |
| **Features** | `(('\x1fEOS#0', '1.000000'), ('\x1fEOS#1', '0.900000'), ('\x1fEOS#2', '0.800000'))` | `(('S>$', '0.800000'), ('^<E', '0.900000'), ('^<EOS>$', '1.000000'), ('~EOS', '0.750000'))` | **NO** |
| **Feature Bundle Digest** | `d3b8e3133be9eb13bbb4438b661e2e3c1067369e17d995809b8115b821f007f8` | `eb190189f81b0c10f1927560dd789cb5b131e0db8f2261a4286ed7151e3d21b5` | **NO** |
| **Envelope Digest** | `d3b8e3133be9eb13bbb4438b661e2e3c1067369e17d995809b8115b821f007f8` | `d3b8e3133be9eb13bbb4438b661e2e3c1067369e17d995809b8115b821f007f8` | N/A |
| **Digest Equality** | `True` | `False` | **NO** |

### 2.2 Why the Outbox Mismatch Guard Failed to Trigger
In `src/dgca/peripheral/outbox.py`, lines 103–105:
```python
ev_digest = getattr(ev, "feature_bundle_digest", None)
if ev_digest is not None and envelope.feature_bundle_digest != ev_digest:
    continue
```
`ev` is an instance of `EventExecutionResult` (`src/dgca/core/dynamics.py`), which defines event runtime execution state (activations, drive, frontiers, supports, contributions). `EventExecutionResult` has **no `feature_bundle_digest` attribute**.

Therefore:
- `getattr(ev, "feature_bundle_digest", None)` always evaluates to `None`.
- `ev_digest is not None` evaluates to `False`.
- The mismatch guard is completely bypassed.
- The outbox published notifications matching sensory cells committed to the lexical token `"<EOS>"` with the canonical peripheral envelope containing `Marker.EOS`.

---

## 3. INDEPENDENT REPRODUCTION OF THE 93-PASS CLAIM

A clean checkout of commit `87ef197ee0f8183ba6e7ceb94b701b73e1a0bc56` was executed:
- **Python Executable:** `C:\Python314\python.exe` (v3.14.4, MSC v.1944 64-bit).
- **Target Test:** `pytest tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_task6_eos_learning_and_multistep_rollout -vv -s`
  - Output: `1 passed in 7.68s` (Exit Code: 0).
- **Full Suite:** `pytest -q`
  - Output: `93 passed in 41.63s` (Exit Code: 0).
  - Working tree: clean.

### Scientific Evaluation:
While the claim of 93 passes is mechanically reproducible, the scientific premise of Task 6 was defective. The model was not learning canonical EOS representations; it was learning lexical n-grams for the string `"<EOS>"` under an unverified outbox bypass.

---

## 4. CORRECTED CANONICAL EOS EXPERIMENT & CAUSAL CHAIN

In the corrected experiment, canonical EOS events were injected using `dataclasses.replace(env.core_event, exposure_id=root_id)`, preserving canonical features and digests without modification.

### 4.1 Complete Causal Chain
1. **Canonical EOS Observations:** Modality = `LANGUAGE (2)`, salience = `1.000000`, canonical features `\x1fEOS#0`, `\x1fEOS#1`, `\x1fEOS#2`, digest `d3b8e313...`.
2. **Sensory Commitment:** 48 sensory cells committed in Root 1, including sensory microcolumns mapped to the canonical EOS features.
3. **LOCAL Synapse Formation:** Internal LOCAL synapses formed within EOS member subsets (Asm 2: 12 internal synapses; Asm 5 & 6: 62 internal synapses each).
4. **Assembly Birth:** 
   - Assembly 2 born at close serial 7 (Root 7).
   - Assembly 5 & 6 born at close serial 8 (Root 8).
5. **Peripheral Attestations:**
   - Assembly 2: 48 independent external attestations, resolved with `Marker.EOS`.
   - Assembly 5: 46 independent external attestations, resolved with `Marker.EOS`.
   - Assembly 6: 46 independent external attestations, resolved with `Marker.EOS`.
6. **Neural Selection & Autonomous Rollout:**
   - Evaluated across 4 prompt configurations below.

### 4.2 Rollout Evaluation Results

```
========================================================================================================
Prompt                         Emitted Surfaces            Stop Status              Causal Explanation
========================================================================================================
['القط']                       ('يشرب', 'حليب')            GEN_STOP_EOS             Step 0: Asm 4 ('يشرب', score 0.5137)
                                                                                    Step 1: Asm 8 ('حليب', score 0.0907)
                                                                                    Step 2: Asm 2 ('<EOS>', score 0.6484, margin 0.1366)
--------------------------------------------------------------------------------------------------------
['القط', 'يشرب']               ('حليب',)                   GEN_STOP_EOS             Step 0: Asm 8 ('حليب', score 0.0907)
                                                                                    Step 1: Asm 2 ('<EOS>', score 0.6484)
--------------------------------------------------------------------------------------------------------
['النسر']                       ('يشرب', 'ماء')             GEN_STOP_AMBIGUOUS       Step 0: Asm 4 ('يشرب', score 0.5137)
                                                                                    Step 1: Asm 10 ('ماء', score 0.1279)
                                                                                    Step 2: Asm 5 & Asm 6 TIE at 0.206944 (margin 0.0000)
--------------------------------------------------------------------------------------------------------
['النسر', 'يشرب']               ('ماء',)                    GEN_STOP_AMBIGUOUS       Step 0: Asm 10 ('ماء', score 0.1279)
                                                                                    Step 1: Asm 5 & Asm 6 TIE at 0.206944 (margin 0.0000)
========================================================================================================
```

---

## 5. ASSEMBLY CHECKPOINTS & NATURAL DUPLICATION FORENSICS

### 5.1 Roots 34, 56, and 80 Snapshots

| Curriculum | Root Checkpoint | Total LIVE Assemblies | Exact Structural Duplicates | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Natural (No EOS)** | 34 | 9 | **0** | Parallel sub-cliques for "يشرب" (1, 3), "حليب" (5, 8), "ماء" (7, 9) |
| **Natural (No EOS)** | 56 | 9 | **0** | Sub-clique member growth; no exact duplicates |
| **Natural (No EOS)** | 80 | 9 | **0** | Stable 9 assemblies; no exact duplicates |
| **Canonical (With EOS)** | 34 | 12 | **1 pair** (Asm 5 & 6) | `members=(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)` |
| **Canonical (With EOS)** | 56 | 12 | **1 pair** (Asm 5 & 6) | Both remain LIVE; merge cooldown/between-strength prevents merge |
| **Canonical (With EOS)** | 80 | 12 | **1 pair** (Asm 5 & 6) | Exact duplicates persist, causing unresolvable rollout ambiguity |

### 5.2 Forensic Significance:
Finding R1-M01 was originally demonstrated using a manual fixture. This experiment conclusively proves that **under the canonical EOS curriculum, exact structural duplicate Assemblies form NATURALLY during cold-start learning**, survive all merge passes, and directly crash autoregressive rollout on valid training branches.

---

## 6. REPRODUCIBILITY

To verify the corrected test suite and inspect programmatically generated telemetry:

```powershell
# 1. Switch to the verification branch
git checkout audit/r1-f02-c01-eos-verification

# 2. Run the newly added/corrected forensic tests (4 tests in cold start, 5 tests in assembly forensics)
python -m pytest tests/forensics/test_f01_cold_start_and_persistence.py -v
python -m pytest tests/forensics/test_f01_05_assembly_forensics.py -v

# 3. Run the complete test suite (95 tests)
python -m pytest -q

# 4. Programmatically regenerate the forensic manifest
python "C:\Users\Laptop\.gemini\antigravity\brain\836cd41f-c485-4208-b652-48feb4ae9138\scratch\generate_c01_manifest.py"
```

---

# R1-F02-C01 PARTIALLY VERIFIED — OPEN EVIDENCE GAPS
*(EOS mechanics verified; autonomous generation on eagle branch blocked by natural Assembly duplicate collision R1-M01)*
