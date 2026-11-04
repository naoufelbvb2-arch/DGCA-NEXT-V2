# DGCA NEXT V2 — EGCP E2b Experimental Report

## Bounded Witnessed Opportunity Allocation & Quarantined Learning

**Status:** COMPLETE — EMPIRICALLY VERIFIED — EXPERIMENTALLY PASSING  
**Branch:** `experiment/egcp-e2b-quarantined-learning`  
**Parent Baseline:** `experiment/r2-c01-cf05-contextual-latent-allocation` (`d8ee61aa5b973af130e2948f1499df631edb71cf`)  
**Frozen Production Main:** `f044c20b532f89749675120ffb1d8ada997e3a5e` (Strictly Unchanged)  
**Authoritative Specification:** EGCP v1.0 — E0–E2 Frozen Experimental Specification (RC2-C01 §4.3, §5.1, §5.2A)

---

## 1. Executive Summary

EGCP E2b establishes the physical, transactional, and learning infrastructure for **post-graduation contextual Y-growth** under strict quarantine.

Prior to E2b, CF05 restored physical latent eligibility across all 7 member cells of Assembly 6 (`حليب`), but completed contextual owners (such as `z=8320`) were forbidden from learning new temporal associative links to those targets post-graduation.

Under `EGCP_MODE = E2_GROWTH`, E2b implements bounded witnessed opportunity allocation and quarantined synaptic learning:
1. **Quarantined Allocation Compartment:** When a completed contextual owner witnesses a legal post-graduation opportunity to an unlinked latent target, proposals are intercepted at root closure into a dedicated pending compartment [`WState.egcp_pending_growth`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L465) using the [`EGCPPendingGrowthV1`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L303-L340) schema.
2. **P1 Quarantine Invariant:** Quarantined pending growth candidates accumulate genuine LLA evidence ($S, E_{\text{ext}}, \text{external\_count}$, confirmed roots), but contribute strictly **0.0** temporal associative drive across all execution modes (`LEARN`, `RETRIEVE`, `GENERATE`, scratch rollouts).
3. **Pillar 4 (Pending Anti-Recycling Protection):** Target cells reserved by pending growth candidates are shielded in [`w.get_protected_bidirectional_neighbors(cid)`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L550-L557), ensuring their latent slots cannot be recycled or evicted across subsequent exposures.
4. **Bounded Capacity & Candidate Caps:** Pending growth keys are accounted in [`w.unique_claimed_outgoing_keys(src_id)`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L569-L576), strictly enforcing the hard degree budget cap $B_i \le 64$ and a dedicated per-owner cap of $\le 8$ simultaneous pending candidates.
5. **State Transition to READY_FOR_PROMOTION:** Quarantined candidates transition from `PENDING_LEARNING` to `READY_FOR_PROMOTION` upon meeting the exact normative Core/LLA consolidation criteria ($S \ge 0.60, E/E_{\max} \ge 0.30, \text{external\_count} \ge 2$), preparing them for atomic structural promotion in E2c.

### Empirical Outcome
- **Quarantined Admission at Root 61:** Owner `8320` successfully admits all 6 unlinked Assembly 6 targets (`9951, 10345, 10903, 11220, 11463, 12066`) into `w.egcp_pending_growth` under state `PENDING_LEARNING`.
- **Zero Drive Leakage:** Emitted temporal drive from pending keys in all modes is strictly $0.0$.
- **Monotonic Evidence Progression:** Across 13 post-graduation S1 exposures (Roots 61..109), evidence mass accumulates monotonically from $E=0.160$ to $E=1.856$ ($S \approx 0.805$).
- **Consolidation & Promotion Readiness:** Continued exposure to S1 reaches $E \ge 3.015$ ($E/E_{\max} \ge 0.30, \text{count} \ge 22, S \ge 0.79$) and 100% of candidates transition to `READY_FOR_PROMOTION`.
- **Zero Live Contamination:** Live synapses outgoing from `8320` in `w.synapses` remain strictly invariant at 2 (`9319, 9325`). Zero unvetted live synapses are formed.
- **Probe Non-Interference:** Probes P2 (`ماء`), P3 (`تفاح`), and P4 (`ماء`) reproduce baseline autonomous generation trajectories identically.
- **Strict OFF Invariance:** When `EGCP_MODE = OFF`, `w.egcp_pending_growth` is empty and network snapshots match baseline bit-for-bit.

---

## 2. Architectural Implementation

### 2.1 State Schema & Compartmentalization

In [`src/dgca/core/state.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py):
- Added `EGCPGrowthState` (`PENDING_LEARNING`, `READY_FOR_PROMOTION`, `EXPIRED`, `REJECTED`).
- Added [`EGCPPendingGrowthV1`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L303-L340) dataclass preserving full physical and provenance metadata:
  ```python
  @dataclass(slots=True)
  class EGCPPendingGrowthV1:
      state_schema_version: int = 1
      owner_id: tuple[int, int] = (0, 0)
      owner_z_id: int = 0
      owner_binding_generation: int = 1
      owner_structural_revision_at_admission: int = 1
      key: SynapseKey = (0, 0, SynapseScope.ASSOCIATIVE)
      first_root_id: int = 0
      last_credited_root_id: int = 0
      accepted_root_count: int = 0
      max_last_root_opportunity_q6: int = 0
      unresolved_count_bounded: int = 0
      synapse: Synapse = field(default_factory=lambda: Synapse((0, 0, SynapseScope.ASSOCIATIVE)))
      state: EGCPGrowthState = EGCPGrowthState.PENDING_LEARNING
      admission_w_revision: int = 0
      reason_code: str = ""
  ```
- In [`WState`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L465): added `self.egcp_pending_growth: dict[SynapseKey, EGCPPendingGrowthV1] = {}` and `self.egcp_mode: EGCPMode = EGCPMode.OFF`. Deep copied in `WState.clone()`.

### 2.2 Proposal Interception & Evidence Accumulation

In [`src/dgca/lla/proposals.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lla/proposals.py#L227-L248):
- Completed contextual owners (`src_id in w.stable_bindings`) are authorized under `EGCPMode.E2_GROWTH` to generate next-event `ASSOCIATIVE` proposals to latent-eligible targets.
- For already-admitted pending growth candidates (`key in w.egcp_pending_growth`), evidence proposals are generated across all subsequent exposure roots even as homeostatic gain adjusts activation slightly below `theta_create`.

In [`src/dgca/lla/synapse_ledger.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lla/synapse_ledger.py#L170-L269):
- At root closure, [`apply_root_proposals_to_shadow_w`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lla/synapse_ledger.py#L124) intercepts proposals from completed owners to unlinked targets into `w_shadow.egcp_pending_growth`.
- Updates use native [`apply_weighted_synapse_update`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lla/synapse_ledger.py#L58-L122) arithmetic. When consolidation thresholds are met ($S \ge \text{THETA\_S}$, $E / E_{\max} \ge \text{THETA\_E}$, $\text{count} \ge 2$), candidate state transitions to `READY_FOR_PROMOTION`.
- Hard budgets are strictly enforced:
  - Source degree headroom: `w_shadow.available_outgoing_headroom(src_id) > 0` ($B_i \le 64$).
  - Per-owner pending candidate limit: `pending_count < 8`.

### 2.3 Pillar 4 Anti-Recycling Protection

In [`WState.get_protected_bidirectional_neighbors(cid)`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/state.py#L550-L557):
```python
if hasattr(self, "egcp_pending_growth"):
    for key, pending in self.egcp_pending_growth.items():
        if pending.state in (EGCPGrowthState.PENDING_LEARNING, EGCPGrowthState.READY_FOR_PROMOTION):
            if key[0] == cid:
                protected.add(key[1])
            elif key[1] == cid:
                protected.add(key[0])
```
Targets of active pending reservations cannot be evicted during coactive partner recycling.

### 2.4 Cold-Trial Isolation in Candidate Graduation

In [`src/dgca/lla/graduation_c04.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lla/graduation_c04.py#L272) and [`src/dgca/lla/contrast_ledger.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lla/contrast_ledger.py#L549):
- Candidate graduation cold trials explicitly evaluate temporal drive under `egcp_mode=EGCPMode.OFF` to test durable baseline path conformance, ensuring candidate `8320` graduates lawfully at Root 57 close into `StableBinding`.

---

## 3. Automated Test Verification Results

All tests run via pytest in the repository virtual environment:

### 3.1 Dedicated E2b Verification Suite (`test_egcp_e2b_verification.py`)

| Test ID | Test Name | Invariant Tested | Outcome | Time |
|---|---|---|---|---|
| E2B-T01 | `test_01_off_preservation_empty_quarantine` | Quarantined compartment empty and bit-for-bit baseline invariance under OFF | **PASSED** | ~18s |
| E2B-T02 | `test_02_p1_quarantine_invariant` | P1 Quarantine Invariant: temporal drive $P_j^T = 0.0$ in LEARN/RETRIEVE/GENERATE | **PASSED** | ~15s |
| E2B-T03 | `test_03_pillar4_anti_recycling_protection` | Pillar 4 protects pending targets from slot eviction across 50+ exposures | **PASSED** | ~45s |
| E2B-T04 | `test_04_pending_growth_allocation_and_evidence_accumulation` | Monotonic LLA evidence accumulation across S1 roots (13 confirmed roots) | **PASSED** | ~55s |
| E2B-T05 | `test_05_transition_to_ready_for_promotion` | State transition to `READY_FOR_PROMOTION` upon consolidation ($E \ge 3.0, S \ge 0.60$) | **PASSED** | ~45s |
| E2B-T06 | `test_06_bounded_capacity_and_candidate_caps` | Enforce degree budget $B_i \le 64$ and per-owner cap $\le 8$ pending reservations | **PASSED** | ~15s |
| E2B-T07 | `test_07_non_interference_p2_p3_p4` | Non-interference on canonical probes P2, P3, and P4 at Root 61 and Root 112 | **PASSED** | ~70s |
| **Total** | `tests/forensics/test_egcp_e2b_verification.py` | **7 / 7 PASSED (100%)** | **PASSED** | **265.09s** |

### 3.2 Regression Suites

- **CF05 Verification Suite:** `pytest tests/forensics/test_r2_c01_cf05_verification.py -v`: **7 / 7 PASSED** (251.69s).
- **Core Phase 6 Readout & Generation:** `pytest tests/test_phase6_readout_and_generation.py -v`: **7 / 7 PASSED** (0.63s).

---

## 4. Frozen Normative Compliance & Gates

1. **Production Main Immutability:** Production `main` (`f044c20b532f89749675120ffb1d8ada997e3a5e`) remains untouched.
2. **P1 Quarantine Invariant:** All post-graduation growth synapses reside strictly in `WState.egcp_pending_growth` and contribute 0.0 drive to neural activation.
3. **No Unapproved Structural Mutation:** `StableBinding.y_keys` and live `W.synapses` remain strictly invariant in E2b. No live growth links are promoted yet.
4. **No E3 Contrastive Suppression:** No beta attenuation or suppressive ledgers introduced.
5. **No Semantic Leakage:** Evaluation surfaces and probe answers are offline test evaluators only.

---

## 5. Next Phase: EGCP E2c (Structural V4 Growth & Atomic Promotion)

With E2b verified and all 6 Assembly 6 targets reaching `READY_FOR_PROMOTION`, the architecture is prepared for **EGCP E2c**:
1. Implement the **Growth Safety Contract (GSC)** at root close.
2. Form the new **V4 StableBinding schema** with appended `y_keys`.
3. Atomically transfer consolidated pending growth candidates from `W.egcp_pending_growth` into live `W.synapses`.
4. Verify genuine multi-target associative propagation from completed owner `8320` during autonomous generation of Probe P1 (`القط يشرب` $\to$ `حليب`).
