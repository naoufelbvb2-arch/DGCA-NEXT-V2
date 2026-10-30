# DGCA NEXT V2 — R2-B01-C02 INSTRUMENTATION INTEGRITY REPORT

## Forensic Instrumentation Non-Interference & Differential Replay Verification

- **Author:** Principal Scientific Verification Engineer, Deterministic Runtime Auditor, Neural Architecture Research Engineer
- **Date:** October 30, 2026
- **Investigation Branch:** `investigation/r2-b01-assembly-forensics`
- **Starting HEAD:** `fb211b41c4b646105f13152e1f346ac07483226a`
- **Frozen Main SHA:** `faf361b6b95de6287b466eb1dc524ea49c732635`
- **Normative References:**
  - `DGCA_CORE_RC4_1.md` §2.0 (Executable Assembly Operators: `MAINTAIN → GROW → FORM → MERGE/SPLIT`)
  - `DGCA_CORE_RC4_1.md` §9.4 (I/O Envelope, Readout Ledger & Structural Generation Invalidation)
  - `DGCA_LLA_RC4_1.md` §6.6, §8.2 & §8.3 (LG-T01, LG-T02, LG-T03, LG-T16)
- **Status:** **`R2-B01-C02 INSTRUMENTATION VERIFIED — AWAITING FINAL FORENSIC FREEZE`**

---

## 1. Executive Summary

Following the formal reconciliation in R2-B01-C01, independent source inspection identified an instrumentation-integrity defect in the standalone forensic script [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py). The initial forensic wrapper decomposed the root-level call to `_run_form_stage(w, h_slow, event_results, ...)` into separate per-event calls `_run_form_stage(w, h_slow, [ev], ...)`. 

This assignment resolved this defect by:
1. Eliminating the per-event call decomposition, ensuring `_run_form_stage()` executes **strictly once per completed root**, receiving the complete, unaltered original event sequence.
2. Implementing a purely passive, non-invasive execution tracer (via CPython `sys.settrace` and `linecache`) that samples local frame variables (`event_res.event_order`, `new_id`, `tri`) at the exact instant `formed_ids.append(new_id)` executes, without modifying any arguments, return values, control flow, or state mutations.
3. Conducting a **Mandatory Differential Replay** over 56 alternating exposure transactions comparing an untouched production reference (Run A) against the corrected instrumented observer (Run B).
4. Verifying 100% bit-for-bit equality across all 56 roots for:
   - Canonical `WState` digest (assemblies, synapses, fast state).
   - `HSlowState` digest (consolidation weights and slow dynamics).
   - Peripheral `SurfaceReadoutLedgerV1` state.
   - Root-end `AssemblyEndReport` diagnostics.
   - Outbox notification identities.
   - Autonomous multi-step generation outputs (`Cat: GEN_STOP_EOS`, `Eagle: GEN_STOP_AMBIGUOUS`).
5. Confirming empty formation sensitivity (Check A: exact diagnostic equivalence across zero-formation Roots 1–6) and root-wide formation cap preservation (Check B: `K_FORM_PER_END=12` strictly enforced across multi-event roots without per-event reset).
6. Preserving zero modifications to frozen production code (`src/dgca/`, `configs/`, or frozen tests).

---

## 2. Authoritative Baseline & Provenance

| Parameter | Value |
|:---|:---|
| Repository | `naoufelbvb2-arch/DGCA-NEXT-V2` |
| Investigation Branch | `investigation/r2-b01-assembly-forensics` |
| Authoritative Starting SHA | `fb211b41c4b646105f13152e1f346ac07483226a` |
| Frozen Main SHA | `faf361b6b95de6287b466eb1dc524ea49c732635` |
| Target Tool Modified | [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py) |
| Production Source Modifications | **0 lines** (all `src/dgca/` files remain byte-exact frozen) |

---

## 3. Exact Original Instrumentation Defect

In the initial implementation of [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py), the forensic wrapper intercepted `_run_form_stage()` via the following structure:

```python
# DEFECTIVE ORIGINAL WRAPPER (R2-B01 / R2-B01-C01)
def instrumented_run_form_stage(w, h_slow, event_results, preexisting_live_assemblies, n_rec_cache=None):
    all_formed = []
    # DEFECT: Decomposing root-level event_results into per-event stage executions
    for ev in event_results:
        formed = orig_run_form_stage(w, h_slow, [ev], preexisting_live_assemblies, n_rec_cache)
        for fid in formed:
            formation_records.append({"root": r, "event": ev.event_order, "id": fid})
        all_formed.extend(formed)
    return all_formed
```

### Manifested Side-Effects of the Defect:
1. **Formation Budget Reset:** `_run_form_stage()` initializes `formed_ids: list[int] = []` and enforces `len(formed_ids) >= K_FORM_PER_END: break` ($K_{\text{FORM\_PER\_END}} = 12$). In a multi-event root, decomposing into per-event invocations resets this budget to 12 for *each* event, potentially admitting up to $N_{\text{events}} \times 12$ assemblies instead of the legal ceiling of 12 for the entire root.
2. **Duplicate Diagnostics:** When no assemblies form and no live assemblies exist, `_run_form_stage()` appends `StatusCode.NO_RECIPROCAL_TRIANGLE` to diagnostics. In an empty root with 4 events (Roots 1–6), the per-event loop invoked `_run_form_stage()` 4 times, generating 4 duplicate `NO_RECIPROCAL_TRIANGLE` diagnostic codes instead of exactly 1 at root-close.
3. **Stage Ordering & State Coherence:** Decomposing root stages violated the frozen production execution contract where `_run_form_stage()` is a root-close consolidation step evaluated once after all events of the exposure transaction have finished streaming.

---

## 4. Corrected Observation Strategy: Non-Invasive Line Tracer

To eliminate all call decomposition and preserve 100% behavioral equivalence, the forensic tool was re-engineered with a purely passive, non-invasive line tracer:

### Implementation Mechanism:
1. **Single Root-Level Invocation:** `_run_form_stage(w, h_slow, event_results, preexisting_live_assemblies, n_rec_cache)` is invoked **exactly once per completed root**, receiving the entire, unaltered `event_results` list.
2. **Passive Line Trace Hook (`sys.settrace`):**
   ```python
   def _make_trace_lines(formed_in_call: list[dict[str, Any]]):
       def trace_lines(frame, event, arg):
           if event == "line" and frame.f_code.co_name == "_run_form_stage":
               line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
               if "formed_ids.append(new_id)" in line:
                   ev = frame.f_locals.get("event_res")
                   new_id = frame.f_locals.get("new_id")
                   tri = frame.f_locals.get("tri")
                   if ev is not None and new_id is not None:
                       formed_in_call.append({
                           "root_id": current_root_context,
                           "event_order": ev.event_order,
                           "action": "FORMED",
                           "assembly_id": new_id,
                           "members": list(tri) if tri else [],
                       })
           return trace_lines
       return trace_lines
   ```
3. **Scope and Safety Guarantees:**
   - Tracing is installed immediately before `orig_run_form_stage()` and uninstalled via `finally: sys.settrace(old_trace)`.
   - The trace function only inspects frame local variables (`event_res`, `new_id`, `tri`) at the exact source line where an assembly is committed.
   - It performs zero writes to frame locals, zero alterations to arguments, zero modifications to return values, and zero side-effects on random seeds or floating-point registers.

---

## 5. Mandatory Differential Replay Methodology

To mathematically prove non-interference, the standalone script executes two complete 56-root curriculum runs from identical initial conditions:

```
+-----------------------------------------------------------------------------+
|                               INITIAL STATE                                 |
| MachineState(), SurfaceReadoutLedgerV1(), ExposureTransactionManager()       |
+-----------------------------------------------------------------------------+
               |                                               |
               v                                               v
+-------------------------------+             +-------------------------------+
|             RUN A             |             |             RUN B             |
|  Untouched Production Reference|             |  Corrected Instrumented Observer|
|  - Zero monkeypatching        |             |  - Single-call _run_form_stage |
|  - Zero sys.settrace hooks    |             |  - Passive line tracer         |
|  - Pure frozen production     |             |  - Differential state recorder |
+-------------------------------+             +-------------------------------+
               |                                               |
               +-----------------------+-----------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |   CANONICAL DIGEST COMPARISON     |
                     |   - 56 Roots bit-for-bit equality |
                     |   - Diagnostics equality          |
                     |   - Final generator rollout match |
                     +-----------------------------------+
```

### Canonical Digest Construction
At the end of each root $r \in [1..56]$, an invariant canonical state digest is computed:
- **WState Digest:** Canonical JSON serialization of:
  - Assemblies: sorted `(id, sorted(members), generation, status, created_root, updated_root)`.
  - Synapses: sorted `(src, dst, S, E_ext, E_int)`.
  - Fast states: `V`, `U`, `A_plus`, `A_minus`, `r`, `rho` across all 12,288 cells.
- **HSlowState Digest:** Structural consolidation matrix elements $W^{\text{slow}}$ and adaptation vectors.
- **Diagnostics Digest:** Exact tuple of `StatusCode` enums emitted in `AssemblyEndReport`.
- **Ledger Digest:** Cumulative sequence of attested tokens, markers, and cell memberships.
- **Combined SHA-256:** Bit-exact SHA-256 over all state components.

---

## 6. Per-Root Differential Equality Results

The 56-root differential replay completed with **zero state divergences**:

$$\text{Root Digests Matching: } 56 / 56 \quad (100.0\% \text{ Bit-for-Bit State Equality})$$
$$\text{AssemblyEndReport Diagnostics Matching: } 56 / 56 \quad (100.0\% \text{ Diagnostic Equality})$$

### State and Ledger Digest Sampling Across Key Milestone Roots

| Root | Stimulus Branch | Run A (Reference) SHA-256 Digest | Run B (Instrumented) SHA-256 Digest | Equality | Diagnostics Match |
|:---:|:---|:---:|:---:|:---:|:---:|
| **Root 01** | AB (`القط يشرب حليب <EOS>`) | `c2a689b...` | `c2a689b...` | **EXACT MATCH** | `(NO_RECIPROCAL_TRIANGLE,)` |
| **Root 06** | DB (`النسر يشرب ماء <EOS>`)  | `f914b4e...` | `f914b4e...` | **EXACT MATCH** | `(NO_RECIPROCAL_TRIANGLE,)` |
| **Root 07** | AB (Birth Asm 1, 2)         | `7d1003a...` | `7d1003a...` | **EXACT MATCH** | `()` |
| **Root 08** | DB (Birth Asm 3, 4, 5, 6)   | `946a4e1...` | `946a4e1...` | **EXACT MATCH** | `()` |
| **Root 09** | AB (Structural Convergence) | `be1fbc6...` | `be1fbc6...` | **EXACT MATCH** | `()` |
| **Root 10** | DB (Membership Extension)   | `12fa099...` | `12fa099...` | **EXACT MATCH** | `()` |
| **Root 16** | DB (Final Assembly Birth)   | `3e8b091...` | `3e8b091...` | **EXACT MATCH** | `()` |
| **Root 56** | DB (Curriculum Termination) | `d79ab08...` | `d79ab08...` | **EXACT MATCH** | `()` |

---

## 7. Diagnostic-Equivalence & Formation Budget Sensitivity

### Check A: Empty Formation Sensitivity (Roots 1–6)
In Roots 1 through 6, no reciprocal triangles form and no live assemblies exist. The evaluation confirms that both Run A and Run B produce the exact same single diagnostic code at root close:

```
Root 01: Run A = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Run B = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Match = True
Root 02: Run A = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Run B = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Match = True
Root 03: Run A = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Run B = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Match = True
Root 04: Run A = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Run B = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Match = True
Root 05: Run A = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Run B = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Match = True
Root 06: Run A = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Run B = (StatusCode.NO_RECIPROCAL_TRIANGLE,) | Match = True
```
*Conclusion:* Empty formation diagnostic equivalence is 100% verified. The prior artifact of 4 duplicate codes per empty root is fully eliminated.

### Check B: Root-Wide Formation Cap Multi-Event Test
An isolated synthetic test state was created with 14 candidate reciprocal triangles partitioned across 2 events in a single root:
- Event 0: 7 candidate triangles.
- Event 1: 7 candidate triangles.
- Total candidates across root: 14.

**Observation under corrected observer:**
- Triangles formed in Event 0: 7.
- Triangles formed in Event 1: 5.
- Total formed assemblies: **12** (Cap: $K_{\text{FORM\_PER\_END}} = 12$).
- Root-wide cap strictly enforced without per-event reset: **TRUE**.

---

## 8. Revalidated Forensic Evidence & Attribution

Using the proven non-interfering passive observer, all principal findings of R2-B01 are re-verified with bit-exact certainty:

### 1. Passive Assembly Birth and Event Attribution (Root 8)
- **Assembly 3:** Born in **Root 8, Event 0** (`النسر`), seed `[8416, 8575, 8586]`.
- **Assembly 4:** Born in **Root 8, Event 1** (`يشرب`), seed `[9669, 11119, 12123]`.
- **Assembly 5:** Born in **Root 8, Event 3** (`<EOS>`), seed `[8834, 9209, 10570]`.
- **Assembly 6:** Born in **Root 8, Event 3** (`<EOS>`), seed `[10646, 10915, 11153]`.
- *Finding:* Directly observed via passive frame tracing. Assembly 5 and 6 births occurred in Event 3 from disjoint seed triangles within the unassigned emitter pool.

### 2. Post-Birth Structural Convergence (Roots 9–10)
- **Root 8:** Asm 5 = `[8834, 9209, 10570]`, Asm 6 = `[10646, 10915, 11153]`, $\text{Jaccard} = 0.0000$.
- **Root 9:** Both grow symmetrically to identical 8-cell memberships:
  $$\text{Members}(A_5) = \text{Members}(A_6) = [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116], \quad \text{Jaccard} = 1.0000$$
- **Root 10:** Both recruit cell `12117`:
  $$\text{Members}(A_5) = \text{Members}(A_6) = [8834, 9209, 10570, 10646, 10915, 11153, 11583, 12116, 12117]$$
- **Root 56:** Identical 9-cell membership remains stable through curriculum end.

### 3. MERGE Rejection Compliance (Roots 9–56)
- Evaluated across 49 consecutive roots.
- In every evaluation: $\text{Jaccard} = 1.0000$, $\text{excl\_a} = \emptyset$, $\text{excl\_b} = \emptyset$.
- Under `DGCA_CORE_RC4_1.md` §2.0 item 4:
  $$\text{between\_strength} = 0.0 < \Theta_{\text{OB}} (0.40)$$
- Blocked strictly by `SPEC_CONTRACT_EMPTY_EXCLUSIVE_SIDE_ZERO_BETWEEN_STRENGTH`.

### 4. Autonomous Readout Collision (Root 56)
- **Cat Branch Rollout:**
  $$[\text{'القط'}] \longrightarrow \text{'يشرب'} \longrightarrow \text{'حليب'} \longrightarrow \text{GEN\_STOP\_EOS}$$
  *Result:* Run A = `GEN_STOP_EOS` | Run B = `GEN_STOP_EOS` (100% Match).
- **Eagle Branch Rollout:**
  $$[\text{'النسر'}] \longrightarrow \text{'يشرب'} \longrightarrow \text{'ماء'} \longrightarrow \text{GEN\_STOP\_AMBIGUOUS}$$
  *Result:* Run A = `GEN_STOP_AMBIGUOUS` | Run B = `GEN_STOP_AMBIGUOUS` (100% Match).
- **Terminal Step Score Margin:**
  $$\text{Score}(A_5) = 0.2069442431, \quad \text{Score}(A_6) = 0.2069442431, \quad \Delta \text{Score} = 0.0000000000$$

---

## 9. Master Regression Results

The full regression test suites were executed on `investigation/r2-b01-assembly-forensics`:

### 1. Full Master Regression Suite
```bash
python -m pytest tests/ -q
```
**Outcome:** `192 passed` (100% PASS).

### 2. Forensic Test Suite
```bash
python -m pytest tests/forensics/ -v
```
**Outcome:** `9 passed` (100% PASS).

---

## 10. Confirmation of Zero Production Modifications

A comprehensive workspace status inspection confirms:
- **`src/dgca/`:** Zero files modified.
- **`configs/`:** Zero files modified.
- **`tests/`:** Zero files modified.
- All modifications are strictly restricted to:
  - [`tools/forensics/investigate_r2_b01_assembly_collision.py`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/investigate_r2_b01_assembly_collision.py)
  - [`R2-B01-ASSEMBLY-STRUCTURAL-FORENSIC-REPORT.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-ASSEMBLY-STRUCTURAL-FORENSIC-REPORT.md)
  - [`R2-B01-C02-INSTRUMENTATION-INTEGRITY-REPORT.md`](file:///C:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/R2-B01-C02-INSTRUMENTATION-INTEGRITY-REPORT.md)

---

## 11. Final Status

$$\mathbf{R2-B01-C02\ INSTRUMENTATION\ VERIFIED\ —\ AWAITING\ FINAL\ FORENSIC\ FREEZE}$$
