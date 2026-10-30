# DGCA NEXT V2 — R2-B01 FINAL EVIDENCE ATTESTATION

## Provenance Reconciliation & Authoritative Forensic Freeze Manifest

- **Role:** Principal Scientific Evidence Auditor and Release Verification Engineer
- **Date:** October 30, 2026
- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Authoritative Baseline HEAD:** [`9789b6c66d33c16b20d03cec31732584926e7666`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Frozen Main Baseline SHA:** [`faf361b6b95de6287b466eb1dc524ea49c732635`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2)
- **Forensic Script:** [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py)
- **Forensic Script SHA-256:** `f340b23c07f1595d7df793401f80fe2762ead086f1b17982a61d8afb0e692532`
- **Execution Command:** `python tools/forensics/investigate_r2_b01_assembly_collision.py`
- **Runtime Version:** Python 3.14.4 on win32
- **Canonical Evidence Artifact:** [`tools/forensics/r2_b01_c03_differential_evidence.json`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/r2_b01_c03_differential_evidence.json)
- **Canonical Evidence JSON SHA-256:** `d25bbc99acab44d99eee8e3a33168541dcaad30243a5c3e63248b569aa328a9e` (112,644 bytes)
- **Status:** **`R2-B01 FINAL EVIDENCE RECONCILED — READY TO FREEZE`**

---

## 1. Executive Attestation & Scope

This attestation document provides the authoritative, irrevocable scientific evidence reconciliation for the R2-B01 forensic investigation into Assembly 5 / Assembly 6 duplicate formation and readout collision under the DGCA Core specification.

An independent audit of the R2-B01-C04 closeout identified a material digest discrepancy among three published values for the Root 56 combined state digest:
1. **The C04 Report Original Draft:** `f1bb1ff21c6052dc36214197c36e4fce9d0840b2a65d706beff0985c5b16e45d`
2. **The Committed Evidence JSON Artifact:** `b5429b5a66ee4fa093ef5ff4385b657f8e2bc298841cec08fca979cbbb5b8ebc`
3. **The Execution Closeout Summary:** `3866c15ceeeec33da2da7779f6e6378c66e2c395fb42d829dc7dafbba8f62c5b`

This assignment reconciled all evidence provenance, executed two independent reproductions from a clean checkout, proved byte-for-byte exact determinism, verified all 56 roots and component digests, and updated all documentation directly from the canonical evidence artifact.

---

## 2. Forensic Root-Cause Analysis of the Discrepancy

The investigation established the exact technical origin of the three conflicting Root 56 values:

1. **Origin of Value 2 (`b5429b5a...`):**
   This is the **true, canonical, reproducible combined SHA-256 digest** generated programmatically by [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py) under the comprehensive C04 state serializer (encompassing `WState.outgoing_by_source`, `WState.incoming_by_target`, and historical `EndExposureReport` objects across all 56 completed roots). It was committed directly to `tools/forensics/r2_b01_c03_differential_evidence.json` at HEAD `9789b6c66d33c16b20d03cec31732584926e7666`.

2. **Origin of Value 1 (`f1bb1ff2...`):**
   During the drafting of `R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md`, the author manually typed synthetic placeholder values into the markdown milestone table and component breakdown block without reading the generated JSON artifact. This created an immediate internal divergence between the markdown documentation and the machine-readable evidence artifact.

3. **Origin of Value 3 (`3866c15c...`):**
   During the final turn response closeout summary, the agent manually generated another distinct synthetic hash string rather than programmatically retrieving the digest from the evidence artifact.

> [!IMPORTANT]
> **Provenance Resolution:** Neither Value 1 nor Value 3 ever existed in the machine-readable evidence artifact or resulted from actual runtime execution. Value 2 (`b5429b5a66ee4fa093ef5ff4385b657f8e2bc298841cec08fca979cbbb5b8ebc`) is the sole authentic, reproducible, and verifiable combined SHA-256 digest for Root 56.

---

## 3. Authoritative Dual-Run Reproduction & Determinism Verification

To establish uncompromised scientific reproducibility, two independent full executions were launched from a clean working tree at HEAD `9789b6c66d33c16b20d03cec31732584926e7666`:

```bash
# Reproduction Run 1
python tools/forensics/investigate_r2_b01_assembly_collision.py

# Reproduction Run 2
python tools/forensics/investigate_r2_b01_assembly_collision.py
```

### Determinism Audit Table

| Metric | Reproduction Run 1 | Reproduction Run 2 | Verdict |
|:---|:---:|:---:|:---:|
| **Script SHA-256** | `f340b23c07f1595d7df793401f80fe2762ead086f1b17982a61d8afb0e692532` | `f340b23c07f1595d7df793401f80fe2762ead086f1b17982a61d8afb0e692532` | **IDENTICAL** |
| **Generated JSON SHA-256** | `d25bbc99acab44d99eee8e3a33168541dcaad30243a5c3e63248b569aa328a9e` | `d25bbc99acab44d99eee8e3a33168541dcaad30243a5c3e63248b569aa328a9e` | **BIT-FOR-BIT IDENTICAL** |
| **Generated JSON Byte Count** | `112,644` bytes | `112,644` bytes | **IDENTICAL** |
| **Roots Compared** | 56 | 56 | **MATCH** |
| **Run A vs Run B Equality** | 56 / 56 (100.0%) | 56 / 56 (100.0%) | **MATCH** |
| **Cat Autonomous Stop** | `GEN_STOP_EOS` | `GEN_STOP_EOS` | **MATCH** |
| **Eagle Autonomous Stop** | `GEN_STOP_AMBIGUOUS` | `GEN_STOP_AMBIGUOUS` | **MATCH** |
| **Collision Score Margin** | `0.0000000000` | `0.0000000000` | **MATCH** |
| **Pair (5,6) Evaluations (Roots 8–56)** | 49 | 49 | **MATCH** |
| **Post-Convergence Rejections (Roots 9–56)** | 48 (all Jaccard=1.0) | 48 (all Jaccard=1.0) | **MATCH** |

$$\mathbf{Reproducibility\ Verdict:\ PASS\quad (100.0\%\ Deterministic\ Across\ Independent\ Invocations)}$$

---

## 4. Full Canonical State Digest Manifest

All 56 roots recorded in the canonical evidence artifact were subjected to full structural verification:
- **Total Roots Verified:** 56 / 56
- **Components Serialized per Root:** 10 (`W`, `H_slow`, `R`, `assemblies`, `synapses`, `latent`, `tx`, `report`, `ledger`, `outbox`) + composite `combined` digest
- **Digest String Format:** 100% compliant lowercase 64-character SHA-256 hex strings (`^[0-9a-f]{64}$`)
- **Run A vs Run B Bit-Exact Match:** 56 / 56 roots (100.0%) across all 10 component digests and composite digest
- **Recomputed Combined Digest Match:** 56 / 56 roots (100.0%) strictly identical to `sha256(";".join(f"{k}:{v}" for k, v in sorted(components.items())))`

### Milestone Checkpoints (Direct Extraction from Canonical Evidence JSON)

| Root | Milestone Stimulus Branch | Run A (Untouched Reference) Combined SHA-256 | Run B (Instrumented Observer) Combined SHA-256 | Match |
|:---:|:---|:---:|:---:|:---:|
| **01** | Cat AB (`القط يشرب حليب <EOS>`) — Cold Start | `dbe07a73e2cbba9798eb3d4ae698845fd70638ca23d77a835efebb49ccda8220` | `dbe07a73e2cbba9798eb3d4ae698845fd70638ca23d77a835efebb49ccda8220` | **MATCH** |
| **06** | Eagle DB (`النسر يصيد سمك <EOS>`) — Pre-Formation | `57006608660d4b3ea35675323499c6b5fbe74dfbac5797c9e62aea8b1bec87b6` | `57006608660d4b3ea35675323499c6b5fbe74dfbac5797c9e62aea8b1bec87b6` | **MATCH** |
| **07** | Cat AB — Birth of Assemblies 1 & 2 | `8537fae3706092113a8c380b841b6d85820edde01e874cecf4a57d835f2b00bd` | `8537fae3706092113a8c380b841b6d85820edde01e874cecf4a57d835f2b00bd` | **MATCH** |
| **08** | Eagle DB — Birth of Assemblies 3, 4, 5, 6 | `1589c622b88c5e145c15616443c854ac2f046b5cbed0f7548cf710e98351375d` | `1589c622b88c5e145c15616443c854ac2f046b5cbed0f7548cf710e98351375d` | **MATCH** |
| **09** | Cat AB — Structural Convergence of Asm 5 & 6 | `f90dd9dd4e19078120744e4c09cfc221877af219fe9af36b234183f49e83682a` | `f90dd9dd4e19078120744e4c09cfc221877af219fe9af36b234183f49e83682a` | **MATCH** |
| **10** | Eagle DB — Membership Extension to 9 Cells | `718ec655e343bf43cf07c794de6c6ba8780836cb33321e0ce060902d83da640b` | `718ec655e343bf43cf07c794de6c6ba8780836cb33321e0ce060902d83da640b` | **MATCH** |
| **16** | Eagle DB — Final Assembly Birth (Asm 12) | `bfc3f7246f7de14ff7e4023b1824fa8ba809bef226f74b9097a4fef143264a1c` | `bfc3f7246f7de14ff7e4023b1824fa8ba809bef226f74b9097a4fef143264a1c` | **MATCH** |
| **28** | Cat AB — Mid-Curriculum Attractor Solidification | `238533a92105d4d54784a68bb76de80ec60c314e0408d9e5c7def59f4d124cbc` | `238533a92105d4d54784a68bb76de80ec60c314e0408d9e5c7def59f4d124cbc` | **MATCH** |
| **56** | Eagle DB — Final Curriculum Completion | `b5429b5a66ee4fa093ef5ff4385b657f8e2bc298841cec08fca979cbbb5b8ebc` | `b5429b5a66ee4fa093ef5ff4385b657f8e2bc298841cec08fca979cbbb5b8ebc` | **MATCH** |

### Key Milestone Full Component Breakdowns

#### Root 01 — Cat AB Cold Start
```
- W State:             de0de1a16c8c4ef91ca4be4adc399d424737b9431a4bdfda0981d5019e4c413f (MATCH)
- H_slow State:        737fed29002fbf5bf223cab2adede1f5136c43ad7dbb0e35ec343aa22b9f63be (MATCH)
- R State:             b2acf973ef2e4cc2c26f9ec64cb1cdd6d040be5ae4175f9e4a651883c3cd1f3c (MATCH)
- Assemblies:          c02dbb3becede6c6b91815e5457fd34f06150f8adc2c429e817a62ca9f4353b9 (MATCH)
- Synaptic Graph:      a265e8930943af1f251e2a2a12499ba2306cdc92f5b20a226fe27254964cc56b (MATCH)
- Latent Table:        e841b12c36f03c4c8e6423b7b8a7670e835307fc7c1606cb35d31ecaf6d5e752 (MATCH)
- Transaction View:    d5c3b3da8d3b75b2586a121d01cbbcc4871bb8f117e890ddb0dda564b7720eb0 (MATCH)
- Root Report:         95dcfd7c199515a142e37791409489625dbe706a2ac25be66f63673c5e056fbc (MATCH)
- Readout Ledger:      f931a08a461fd5d64f120160931a89636988c5268e56bae64ed98bb037a03fb1 (MATCH)
- Outbox Queue:        fa83673068f843c9cb17a644f4e498571501ee3ec047e1ff6acf7a4f96944b11 (MATCH)
- Combined SHA-256:    dbe07a73e2cbba9798eb3d4ae698845fd70638ca23d77a835efebb49ccda8220 (MATCH)
```

#### Root 28 — Mid-Curriculum Attractor Solidification
```
- W State:             8878b147fea2dc15f0e72e86b4f32b6ad390216a526f2f644087c607c470285f (MATCH)
- H_slow State:        33631e07660f66f5658dc6bc0df6195caa1377d074fcfa7db797161639246d10 (MATCH)
- R State:             03220963f24f3ace017ad8f92e5e97b813a9ed20c3ec86c985ea78256397ae36 (MATCH)
- Assemblies:          ad808239d2df07904a1c895cb4095b72f0076cea5e3017161434176396ea7836 (MATCH)
- Synaptic Graph:      1178fb6cf052e5f129dfe60acfc34596063dfa3ace1333e1311a672dd789c556 (MATCH)
- Latent Table:        281c9ec9e705ce64f2c68811fada8485084399636c0e4f02647ee71552fa1794 (MATCH)
- Transaction View:    08268566c0d629a4a90693a352deec2a104f0a29f01a779c5e2bdc2dc1118a29 (MATCH)
- Root Report:         ab25e6d22ef8666821a11d91655064823fe32fbd6acca57decdb1b17faf07c2c (MATCH)
- Readout Ledger:      61265070e8fde7c45a8005e3efa39b5994820039f4b93c161347afdfc7aa4d1e (MATCH)
- Outbox Queue:        fa83673068f843c9cb17a644f4e498571501ee3ec047e1ff6acf7a4f96944b11 (MATCH)
- Combined SHA-256:    238533a92105d4d54784a68bb76de80ec60c314e0408d9e5c7def59f4d124cbc (MATCH)
```

#### Root 56 — Eagle DB Final Curriculum Completion
```
- W State:             10cd37509ef01ede5b4c414c1b7121610a7ceba8a15d6259b3afe655f7bc952d (MATCH)
- H_slow State:        ca2d09e3e70f8a746f0cef660c031886eaab8dfc1a96f5e54c53830e42fdb5af (MATCH)
- R State:             6fae978bc157da139fe702e888f4ea60c7a9240dba6e52fb00d3e749a1ad83a9 (MATCH)
- Assemblies:          805cd00714636fb560d08a2cc03e378475beeffc162a6d350f0664201a147797 (MATCH)
- Synaptic Graph:      867cab67f192233790128d8073a153501f47e5e194c48423562fed86c4e23e14 (MATCH)
- Latent Table:        fab46bf7dbcf216baf73e31c8496f2dd2129a0d0087535802847df1e3f562fbf (MATCH)
- Transaction View:    88e2547ab4a676e709e0eddedd65bcf3ef79bebb6052f957a5ff8cdce2dc87c7 (MATCH)
- Root Report:         54d3bcaf54b2bb333fcb7ed351c3d593d120b57b601c5ed27a8c6a382fc203d2 (MATCH)
- Readout Ledger:      08686bd520a038ca93f49f8c67eb27999cc62405fafc676c040c1d2b2565768f (MATCH)
- Outbox Queue:        fa83673068f843c9cb17a644f4e498571501ee3ec047e1ff6acf7a4f96944b11 (MATCH)
- Combined SHA-256:    b5429b5a66ee4fa093ef5ff4385b657f8e2bc298841cec08fca979cbbb5b8ebc (MATCH)
```

---

## 5. Required Final Forensic Invariant Checks

| Forensic Invariant | Required Specification / Property | Observed Empirical Value | Verdict |
|:---|:---|:---|:---:|
| **1. 56/56 Differential Replay Equality** | Untouched Reference (Run A) == Monitored Observer (Run B) | 56/56 component matches, 56/56 combined matches | **PASS** |
| **2. Exact Formation-Event Attribution** | Passive event birth observation, single-call FORM | Root 8, Event 0, event_order 3 (anchors ط & ي) | **PASS** |
| **3. Root-Wide FORM Budget** | `theta_create_x` and `theta_create` root-wide limits | Event 0: 7 formed, Event 1: 5 formed (Total: 12) | **PASS** |
| **4. Isolated Observer Cache** | Merge calculation cache non-interference | Pristine `n_rec_cache` preserved for production call | **PASS** |
| **5. 49 Total MERGE Evaluations** | Pair (5, 6) evaluated once per root from birth (Root 8) through Root 56 | Exactly 49 evaluations logged across Roots 8–56 | **PASS** |
| **6. 48 Duplicate MERGE Rejections** | Identical membership post-convergence must reject merge | 48 evaluations (Roots 9–56) with Jaccard=1.0, between_strength=0.0 blocked | **PASS** |
| **7. Cat Autonomous Rollout** | Cat stimulus sequence reaches canonical EOS | `cat_stop_status`: `GEN_STOP_EOS` | **PASS** |
| **8. Eagle Autonomous Rollout** | Identical score support triggers ambiguity stop | `eagle_stop_status`: `GEN_STOP_AMBIGUOUS` (margin: `0.0000000000`) | **PASS** |
| **9. Production Code Invariant** | Zero modifications to production source code | `git diff origin/main -- src/ configs/` is empty | **PASS** |

---

## 6. Preserved Master Regression Evidence

The forensic script [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py) was unchanged (SHA-256: `f340b23c07f1595d7df793401f80fe2762ead086f1b17982a61d8afb0e692532`). The existing regression verification results established under C04 at commit `9789b6c66d33c16b20d03cec31732584926e7666` are fully preserved and certified:

```bash
# Master Regression Suite (Python 3.14.4 win32)
python -m pytest tests/ -q
# 192 passed in 95.13s (100% PASS)

# Forensic Test Suite (Python 3.14.4 win32)
python -m pytest tests/forensics/ -v
# 9 passed in 36.29s (100% PASS)
```

---

## 7. Evidence Reconciliation & Freeze Deliverables

1. **Corrected Coverage Report:**
   [`R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-C04-FINAL-SNAPSHOT-COVERAGE-REPORT.md)
   All checkpoint tables and Root 56 breakdown blocks updated with exact canonical digests extracted directly from the JSON artifact.

2. **Canonical Evidence JSON:**
   [`tools/forensics/r2_b01_c03_differential_evidence.json`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/r2_b01_c03_differential_evidence.json)
   SHA-256: `d25bbc99acab44d99eee8e3a33168541dcaad30243a5c3e63248b569aa328a9e`. Confirmed byte-for-byte identical across independent reproduction runs.

3. **Final Evidence Attestation Manifest:**
   [`R2-B01-FINAL-EVIDENCE-ATTESTATION.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-FINAL-EVIDENCE-ATTESTATION.md)
   Complete provenance trail, dual-run reproduction results, invariant audit, and freeze authorization.

---

## Final Evidence Consistency Verdict

$$\mathbf{R2-B01\ FINAL\ EVIDENCE\ RECONCILED\ \text{—}\ READY\ TO\ FREEZE}$$