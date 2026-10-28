# DGCA NEXT V2 — R1-F02-C01 FORMAL CORRIGENDUM ADDENDUM

**Document Version:** 1.0  
**Audit Stage:** R1-F02-C01 Evidence Correction  
**Author:** Independent Scientific Verification Engineer  
**Baseline Commit:** `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`  
**Base Audit Commit:** `87ef197ee0f8183ba6e7ceb94b701b73e1a0bc56`  
**Current Branch:** `audit/r1-f02-c01-eos-verification`

---

## 1. PERSISTENCE IMPLEMENTATION STATUS (R1-B03)

### Discrepancy
In the concluding Arabic conversational summary of stage R1-F02, the narrative stated:
> *"مع تحقق الحفظ الدائم على القرص واسترجاعه بنجاح"* (with durable persistence on disk and reload successfully verified).

This statement directly contradicted both the committed audit report (`R1-F02-EVIDENCE-CLOSURE-REPORT.md`) and the machine-readable manifest (`r1_f02_manifest.json`), which classified cross-process persistence as `NOT_IMPLEMENTED`.

### Formal Correction
1. Complete cross-process durable persistence is **NOT IMPLEMENTED** in the production codebase.
2. Specifically, `dgca.common.serialization` implements individual record packing primitives (`pack_binary64_be`, `pack_record_envelope`), but does NOT implement `serialize_machine_state`, `deserialize_machine_state`, or `save_checkpoint`.
3. Test `tests/forensics/test_f01_cold_start_and_persistence.py::test_f01_persistence_not_implemented` explicitly confirms that full state serialization fns do not exist.
4. No production cross-process disk save/restart/reload experiment has been or can be run until finding R1-B03 is remediated in R2.

---

## 2. GITHUB REPOSITORY BRANCH PROTECTION

### Discrepancy
Previous audit summaries described the remote `main` branch as "protected".

### Formal Correction
1. Direct inspection via GitHub REST API (`GET /repos/naoufelbvb2-arch/DGCA-NEXT-V2/branches/main`) returns:
   ```json
   "protected": false
   ```
2. The remote `main` branch does not have server-side GitHub branch protection rules enabled.
3. The integrity of `main` (pinned at `31721fd1ba7559b72d9fe11f037ea0c0d1e91ed2`) has been preserved solely through strict client-side auditor discipline and the exclusive use of isolated audit branches (`audit/r1-f01-forensic-verification`, `audit/r1-f02-evidence-closure`, `audit/r1-f02-c01-eos-verification`).

---

## 3. READOUT SELECTIVITY & NEGATIVE CONTROL SCOPE

### Clarification
In Task 4 of R1-F02, a negative control test on "ماء" against Assembly 5 ("حليب") yielded a score of `0.000000`.

### Formal Scope Limitation
1. The `0.000000` score demonstrates effective mutual orthogonality between the two training phrases (`القط يشرب حليب` vs `النسر يشرب ماء`) under the specific feature sets produced by the Encoder.
2. This single negative control does **NOT** establish a general mathematical proof of zero false-selection risk across arbitrary sentences, out-of-vocabulary terms, or overlapping lexical assemblies.
3. No new readout formula (e.g., modifying $|G|$ normalization or relaxing $P_T(c) > 0$) has been approved. All production equations remain strictly frozen as mandated.

---

## 4. SCIENTIFIC MANIFEST PROVENANCE

### Correction & Policy
1. The machine-readable manifest `r1_f02_c01_manifest.json` is generated **100% programmatically** via the experiment execution runner `scratch/generate_c01_manifest.py`.
2. No numbers or statuses were copied manually between reports.
3. All telemetry in the manifest is directly traceable to pytest assertions and live runtime execution objects.

---

## 5. NATURAL VS CANONICAL ASSEMBLY CHECKPOINTS (ROOTS 34, 56, 80)

Complete checkpoint capture across both training curricula resolves the previous reporting gap:

### Curriculum A: Natural Learning Without EOS (`append_eos=False`)
- **Root 34:** 9 LIVE assemblies. `EXACT_STRUCTURAL_DUPLICATE = 0`. Parallel sub-cliques for "يشرب" (1, 3), "حليب" (5, 8), "ماء" (7, 9).
- **Root 56:** 9 LIVE assemblies. `EXACT_STRUCTURAL_DUPLICATE = 0`. Same structural sub-clique topology.
- **Root 80:** 9 LIVE assemblies. `EXACT_STRUCTURAL_DUPLICATE = 0`. Sub-cliques maintained; no exact duplicates.

### Curriculum B: Canonical Learning With EOS (`append_eos=True`)
- **Root 34:** 12 LIVE assemblies. `EXACT_STRUCTURAL_DUPLICATE = 1` pair:
  - Assembly 5 & Assembly 6 share identical members: `(8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117)`.
  - Both born at root 8, both at generation 7, both attested to `Marker.EOS`.
- **Root 56:** 12 LIVE assemblies. Duplicate pair (5, 6) survives merge cooldown and continues identical evolution.
- **Root 80:** 12 LIVE assemblies. Duplicate pair (5, 6) persists as LIVE in `state.W`.
- **Causal Impact:** This exact structural duplicate pair causes an identical score tie ($0.206944$) during rollout on the eagle branch, triggering `StatusCode.GEN_STOP_AMBIGUOUS` (finding R1-M01 confirmed in natural canonical learning).
