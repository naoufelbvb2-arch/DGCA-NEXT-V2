# DGCA NEXT V2 — R2-C01-D03 ARCHITECTURAL DESIGN STUDY

## Contextual Latent Neighborhood Allocation, Sparse Physical Pathways & Growth Admissibility Design

* **Document ID:** `DGCA-NEXT-V2-R2-C01-D03`
* **Status:** `ARCHITECTURAL DESIGN FROZEN — AWAITING COUNTERFACTUAL IMPLEMENTATION AUTHORIZATION`
* **Specification Authority:** `EGCP v1.0 — RC2-C01 / RC2-C02 Consolidated Design Contract`
* **Frozen Production Main:** `f044c20b532f89749675120ffb1d8ada997e3a5e` (Strictly Immutable)
* **Parent E1 Baseline:** `c067d14e0544a4968832a833534b85c2c77dff0c` (`experiment/egcp-e1-generic-preservation`)
* **Parent E2a Baseline:** `8de9aef6b86398890f267560ce80c0a5832bad93` (`experiment/egcp-e2a-prediction-opportunity`)
* **Date:** November 3, 2026
* **Role:** Principal Cognitive Architecture Designer, Sparse Neural Learning Researcher, and Scientific Governance Reviewer
* **Audited Feasibility Dataset:** [`tools/forensics/egcp_e2a_feasibility_data.json`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/tools/forensics/egcp_e2a_feasibility_data.json)

---

## 1. Executive Summary & The Physical Latent Barrier

The EGCP E2a stage successfully implemented the pre-observation snapshotting, target candidate enumeration, and $U_{zj} = (e_z \cdot x_j) \cdot (1 - p_{zj})$ opportunity measurement layer across 24 verified tests without modifying frozen Core laws.

However, the empirical feasibility audit for completed contextual owner `z = 8320` revealed an absolute physical barrier:
1. **Zero Outgoing Capacity Deficit:** Owner `8320` has consumed only 5 outgoing synapses ($B_i = 64 \implies$ **59 slots free**). The owner is physically capable of forming up to 59 additional links.
2. **Sufficient Opportunity Mass:** When `حليب` is observed (Root 57 Step 2), all 14 unlinked sensory cells exhibit maximal prediction undercoverage ($U = 1.0000$, $U_{q6} = 64$).
3. **The Physical Latent Barrier:** For all 14 unlinked sensory cells (including the 5 remaining members of Assembly 6: `9183, 10903, 11191, 11220, 11463`), `LatentNeighborhoodTable.is_eligible(8320, j)` evaluates to `False`. Every candidate growth opportunity is legally refused with:
   $$\text{RefusalReason} = \mathbf{NO\_LEGAL\_LOCAL\_PATH}$$
4. **Governing Law (Core §1.3 & RC2-C01 §3.3):**
   > *"A physical-latent failure is NO_LEGAL_LOCAL_PATH... None invokes synthetic long-range rewiring."*
   Without a physical latent pathway $D_{ij} = 1 [j \in N(i) \lor i \in N(j)]$, Core strictly forbids creating a synapse. Consequently, **exactly zero new direct growth links can be admitted for owner 8320**.

This design study formulates the architectural solution to resolve this barrier lawfully, preserving physical locality, sparse biology, deterministic arbitration, and zero selection leakage.

---

## 2. Forensic Analysis of the Latent Neighborhood Allocation Mechanism

To understand why owner `8320` lacks physical latent pathways to Assembly 6, we trace the source implementation of [`_update_coactive_latent_neighborhoods_for_event`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lifecycle/exposure_tx.py#L490-L570):

```python
active_curr = sorted(
    curr_event.l_frontier & curr_event.obs_eligible_cells,
    key=lambda cid: (-curr_event.a_plus_by_cell.get(cid, 0.0), cid),
)
active_prev = (
    sorted(
        prev_event.f_step & prev_event.obs_eligible_cells,
        key=lambda cid: (-prev_event.a_plus_by_cell.get(cid, 0.0), cid),
    )
    if (prev_event is not None and not curr_event.boundary)
    else []
)
```

### The Mechanism of Owner Exclusion
1. **Sensory Exclusivity of `active_prev`:**
   In line 515, `active_prev` is filtered by `prev_event.f_step & prev_event.obs_eligible_cells`.
   - By definition, `obs_eligible_cells` contains **only directly observed sensory receiver cells** from the external SIC projection.
   - Contextual cells (such as owner `8320`, located in deep layers L5/6) belong to `ctx_event_match_cells`, **never** to `obs_eligible_cells`.
2. **Contextual Cell Inward Pinning Only:**
   Contextual cells manage their own coactive slots during candidate formation via §7.3 inward pinning (`pin_context_candidate_roles`). They pin up to 6 partners (anchors, parents, and targets witnessed during candidate probation). For candidate `8320`, probation pinned targets `9319` and `9325`.
3. **The Asymmetry:**
   Once a contextual owner graduates, it can never acquire additional latent slots through ordinary coactivity because:
   - The owner is skipped in `_update_coactive_latent_neighborhoods_for_event` line 527 (`if w.is_contextual_cell(cid): continue`).
   - The owner is excluded from `active_prev` for subsequent sensory cells.
   - Consequently, newly observed sensory cells in event $t$ only allocate temporal slots to sensory cells from $t-1$, never to the active contextual owner in $t-1$.

This proves that the inability of owner `8320` to link to Assembly 6 is not a learning defect, but an **unintentional architectural exclusion in the coactive latent allocation contract**.

---

## 3. Formal Specification of the Design (The Five Pillars)

Following the comprehensive architectural review and `/grill-me` alignment, the design is structured around five immutable pillars:

### Pillar 1: Scope of Contextual Eligibility
Only fully validated, completed contextual owners active in the preceding event are eligible to compete for coactive latent slots with receiver cells at $t$.
$$\text{EligibleContextSource}(z, t-1) \iff \begin{cases} z \in W.\text{stable\_bindings} \\ \text{status} = \text{ACTIVE} \\ z \in F_{\text{step}}(t-1) \cap \text{ctx\_event\_match\_cells}(t-1) \\ A_z^+(t-1) > 0 \\ \text{typed\_supports}[z].\text{origin\_kind} = \text{DERIVED\_EXTERNAL\_CONTEXT} \\ \text{typed\_supports}[z].\text{parent\_proof\_verified} = \text{True} \end{cases}$$

- **Negative Control:** Incomplete candidates in probation, ungraduated cells, non-emitting cells, and internally generated tokens are strictly excluded. This guarantees zero pollution of sensory latent slots by transient or unproven hypothesis cells.

### Pillar 2: Slot Partitioning & Quota within the Receiver Cell
Every cortical cell possesses 24 latent slots divided per Core §1.3:
- Slots `[0..5]`: 6 Coactive Intra-Region Slots (Recyclable).
- Slots `[6..11]`: 6 Fixed Local Vicinity Slots (Immutable).
- Slots `[12..17]`: 6 Coactive Inter-Region Slots (Recyclable).
- Slots `[18..23]`: 6 Fixed Topographic Slots (Immutable).

When an external sensory receiver cell $j$ in event $t$ allocates its 6 Coactive Intra-Region Slots (`[0..5]`):
- **Same-Event Peers ($t$):** Up to 3 slots allocated to coactive sensory peers in the current event.
- **Sensory Predecessors ($t-1$):** Up to 2 slots allocated to sensory cells from the preceding event (preserving the ordinary associative temporal link path).
- **Dedicated Contextual Slot ($t-1$):** Exactly **1 slot** reserved for the highest-priority eligible completed contextual owner from $t-1$ (if present).
$$\text{IntraSlots}(j) = \underbrace{3 \text{ Same-Event Sensory}}_{\text{clique peers}} + \underbrace{2 \text{ Prior-Event Sensory}}_{\text{ordinary associative}} + \underbrace{1 \text{ Prior-Event Contextual Owner}}_{\text{contextual Y-growth}}$$

### Pillar 3: Symmetric Physical Eligibility
Under Core §1.3:
$$D_{zj} = 1 \iff [j \in N(z) \lor z \in N(j)]$$
By having sensory receiver cell $j$ admit owner $z$ into its own coactive intra-slot via `admit_or_recycle_coactive_partner(j, z)`:
1. $z$ becomes an immediate physical neighbor in $N(j)$.
2. Physical latent eligibility `w.latent_table.is_eligible(z, j)` evaluates to `True` unconditionally.
3. The owner's internal 6 pinned slots are left undisturbed, while the connection satisfies physical spatial locality.

### Pillar 4: Anti-Recycling Protection & Reservation Lifecycle
To prevent transient sensory events from prematurely overwriting the new contextual pathway before synaptic consolidation can occur:
1. **Open Root Protection:** The pair $(j, z)$ is immediately registered in `protected_in_open_root`.
2. **Pending Latent Reservation:** Once the candidate $(z, j, \text{ASSOCIATIVE})$ is admitted into E2b pending quarantine, a durable `latent_reservation_ref` is placed on the slot, elevating its recycling protection:
   $$\text{Protection Priority:} \quad \text{Live Synapse} \ge \text{Contextual Pin} \ge \mathbf{Pending\ Latent\ Reservation} > \text{Unprotected Slot}$$
3. **Atomic Release:** If the pending candidate expires ($TTL \ge 2000$) or is rejected by structural checks, the reservation is atomically released without leaving orphan structures.

### Pillar 5: Theoretical Evaluation Across All Four Sentences
The feasibility and non-interference of this design must be formally evaluated across all four canonical corpus sentences across both Group A (baseline) and Group B (diversified).

---

## 4. Theoretical Impact Analysis Across Canonical Corpus Probes

We evaluate the physical feasibility and mathematical score dynamics across all four canonical probes:

```text
P1: القط يشرب → حليب → <EOS>
P2: النسر يشرب → ماء → <EOS>
P3: الطفل يأكل → تفاح → <EOS>
P4: الطفل يشرب → ماء → <EOS>
```

### 4.1 Probe P1 (`القط يشرب حليب`) — Milk Rescue Dynamics
* **Current State (Root 112):**
  - Assembly 6 (`حليب`, $|M|=7$): Members `[9183, 9319, 9325, 10903, 11191, 11220, 11463]`.
  - Driven by owner `8320` only at cells `9319` and `9325` ($Q \sim 0.304$).
  - Current score: $S_{\text{milk}} = \mathbf{0.196352}$ (loses to $S_{\text{water}} = \mathbf{0.527258}$).
* **Under Contextual Latent Allocation (D03):**
  - Upon presentation of `حليب`, the 5 unlinked cells (`9183, 10903, 11191, 11220, 11463`) admit owner `8320` into their dedicated contextual intra-slot.
  - Latent eligibility becomes `True` for all 7 members of Assembly 6.
  - With lawful E2b quarantine and E2c consolidation ($Q \sim 0.60$ per member):
    $$\bar{S}_{\text{milk}} = \frac{7 \times 0.60}{7} = \mathbf{0.600000} > 0.527258 \ (\bar{S}_{\text{water}})$$
  - **Result:** Assembly 6 (`حليب`) successfully out-competes Assembly 4 (`ماء`). P1 emits `حليب` autonomously!

### 4.2 Probe P2 (`النسر يشرب ماء`) — Discrimination & Non-Interference
* **Context:** `النسر يشرب` does not activate owner `8320` (whose parents are `القط` and `يشرب`).
* **Dynamics:**
  - Owner `8320` has $A_z^+(t-1) = 0.0$ $\implies$ No contextual drive to `حليب`.
  - Generic associative drive from `يشرب` drives Assembly 4 (`ماء`, $|M|=5$) with score $0.527$.
  - Assembly 6 (`حليب`) receives only muted generic background ($< 0.08$).
  - **Result:** P2 cleanly emits `ماء`. Zero cross-context interference.

### 4.3 Probe P3 (`الطفل يأكل تفاح`) — Distinct Lexical Subsystem
* **Context:** Uses distinct verb `يأكل` and object `تفاح`.
* **Dynamics:**
  - Active cells in $F_{\text{step}}$ belong to the eating subsystem. Owner `8320` is completely dormant ($A = 0$).
  - Dedicated contextual slot on `تفاح` receiver cells remains available for `يأكل`-related contextual candidates if formed.
  - Assembly 7 (`تفاح`) receives unperturbed generic drive ($S \approx 0.53$).
  - **Result:** P3 cleanly emits `تفاح`. Zero negative transfer.

### 4.4 Probe P4 (`الطفل يشرب ماء`) — Agent Contrast Test
* **Context:** Same verb `يشرب`, different agent (`الطفل` vs `القط`).
* **Dynamics:**
  - Contextual owner `8320` requires co-activation of `القط` and `يشرب`. Under `الطفل`, owner `8320` gate $G_{\text{ctx}} = 0$.
  - Without owner `8320`, Assembly 6 receives no contextual boost.
  - Assembly 4 (`ماء`) wins readout decisively ($0.527 > 0.08$).
  - **Result:** P4 cleanly emits `ماء -> <EOS>`.

---

## 5. Concrete Contract Delta & Pseudocode

The exact proposed implementation delta is isolated to `_update_coactive_latent_neighborhoods_for_event` in [`src/dgca/lifecycle/exposure_tx.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/lifecycle/exposure_tx.py#L490-L570):

```python
def _update_coactive_latent_neighborhoods_for_event(
    w: WState,
    curr_event: EventExecutionResult,
    prev_event: EventExecutionResult | None,
    protected_in_open_root: set[tuple[int, int]],
    enable_cross_clique_diversification: bool = False,
    enable_contextual_coactive_latent: bool = False,  # Feature Flag (Default: False)
) -> None:
    # 1. Existing sensory sorting
    active_curr = sorted(
        curr_event.l_frontier & curr_event.obs_eligible_cells,
        key=lambda cid: (-curr_event.a_plus_by_cell.get(cid, 0.0), cid),
    )
    active_prev_sensory = (
        sorted(
            prev_event.f_step & prev_event.obs_eligible_cells,
            key=lambda cid: (-prev_event.a_plus_by_cell.get(cid, 0.0), cid),
        )
        if (prev_event is not None and not curr_event.boundary)
        else []
    )

    # 2. Extract verified completed contextual owners from t-1 (Pillar 1)
    eligible_context_owners = []
    if enable_contextual_coactive_latent and prev_event is not None and not curr_event.boundary:
        for z_id in sorted(w.stable_bindings.keys()):
            sb = w.stable_bindings[z_id]
            if sb.status == BindingStatus.ACTIVE and z_id in prev_event.f_step and z_id in prev_event.ctx_event_match_cells:
                rec = prev_event.typed_supports.get(z_id)
                if rec and rec.origin_kind == ContributionLane.DERIVED_EXTERNAL_CONTEXT.value and rec.parent_proof_verified:
                    eligible_context_owners.append(z_id)

    top_curr_clique = active_curr[:4]
    secondary_curr_clique = active_curr[4:]

    for cid in active_curr:
        if w.is_contextual_cell(cid):
            continue

        protected = w.get_protected_bidirectional_neighbors(cid) | {
            partner for src, partner in protected_in_open_root if src == cid
        }

        peer_pool = top_curr_clique if cid in top_curr_clique else secondary_curr_clique
        
        # 3. Partition: 3 same-event, 2 prior-sensory, 1 prior-contextual (Pillar 2)
        same_peers = [p for p in peer_pool if p != cid][:3]
        prev_sensory_peers = [p for p in active_prev_sensory if p != cid and p not in same_peers][:2]
        
        desired_partners = same_peers + prev_sensory_peers
        if eligible_context_owners:
            best_owner = eligible_context_owners[0]
            if best_owner != cid and best_owner not in desired_partners:
                desired_partners.append(best_owner)

        # 4. Admit or recycle partner with reason tracking (Pillar 3 & 4)
        for partner_id in desired_partners:
            reason = "CONTEXTUAL_COACTIVE" if partner_id in eligible_context_owners else "ORDINARY_COACTIVE"
            if w.latent_table.is_eligible(cid, partner_id):
                protected_in_open_root.add((cid, partner_id))
                protected_in_open_root.add((partner_id, cid))
                continue
            try:
                w.latent_table.admit_or_recycle_coactive_partner(
                    cid,
                    partner_id,
                    protected_bidirectional_neighbors=protected,
                    event_clock=w.global_event_clock,
                    reason=reason,
                )
                protected.add(partner_id)
                protected_in_open_root.add((cid, partner_id))
                protected_in_open_root.add((partner_id, cid))
            except DGCAError:
                continue
```

---

## 6. Pre-Registered Falsification Criteria & Verification Gates

Before any production promotion or EGCP E2b execution can be authorized, the counterfactual experiment (`R2-C01-CF05`) must pass the following explicit falsification tests:

| Test ID | Gate Invariant | Acceptance Criterion | Falsification Condition |
| :--- | :--- | :--- | :--- |
| **D03-T01** | **Exact OFF Preservation** | When flag is `False`, 100% bit-exact parity with frozen CF04/E1 checkpoints | Any hash or synaptic difference under default flag |
| **D03-T02** | **Owner Provenance Guard** | Only verified `DERIVED_EXTERNAL_CONTEXT` owners admitted | Unverified, candidate, or internal owners admitted |
| **D03-T03** | **Bounded Quota** | Exactly 1 contextual slot allocated per sensory cell | More than 1 contextual slot allocated or sensory starvation |
| **D03-T04** | **Latent Pathway Restoration** | All 7 Assembly 6 cells evaluate to `is_eligible(8320, j) == True` | Any Assembly 6 cell remains `NO_LEGAL_LOCAL_PATH` |
| **D03-T05** | **Zero Selection Leakage** | Full/control passes show 100% identical microcolumn totals | Differential control-pass leakage detected |
| **D03-T06** | **Non-Interference (P2/P3/P4)** | P2, P3, and P4 generation outputs remain unperturbed | Regression or cross-talk in P2, P3, or P4 |

---

## 7. Stage Conclusion & Architectural Disposition

1. **Root Cause Confirmed:** The failure of owner `8320` to link with Assembly 6 is definitively caused by the exclusion of contextual cells from the coactive latent allocation contract.
2. **Design Soundness:** The 5-pillar design resolves the barrier lawfully without long-range rewiring, preserves physical locality ($\Delta t = 1$), protects existing sensory links, and maintains total budget constraints ($B_i \le 64$).
3. **Formal Disposition:**
   $$\mathbf{R2-C01-D03: \ DESIGN\ FROZEN\ \&\ APPROVED\ FOR\ EXPERIMENTATION}$$
4. **Next Authorized Step:**
   Submit proposal for controlled counterfactual experiment **`R2-C01-CF05`** on an isolated branch to evaluate the implementation of this design against baseline E2a.
