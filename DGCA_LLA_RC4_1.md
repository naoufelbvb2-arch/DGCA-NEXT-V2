# DGCA v2 — Dynamic Core Reconstruction: LLA Specification

**Document ID:** `DGCA-DCR-LLA-SPEC`  
**Revision:** `v1.0.0-RC4.1` — proposed integration with derived witnesses, executable Assembly formation, and bounded hybrid autoregressive generation  
**Date:** 2026-10-26  
**Status:** `RC4.1 DESIGN CANDIDATE — NOT FROZEN — NOT IMPLEMENTED — NOT EMPIRICALLY VALIDATED`  
**Companion:** `DGCA_CORE_RC4_1.md`  
**Scope:** LANGUAGE local learning plus first-lab neural next-event regression, **conditional RC4 hierarchical (max depth 8) and native Assembly learning**, and read-only G1/G2 generation; semantic/compositional G3 remains empirical and unproven.

> **Authority.** This is a self-contained proposed integration of historical LLA v2.0 (C1–C5), the DCR unified v0.9.0, and corrective overlays C01, C02, C03 and C04. If finally accepted, **only this document plus its Core companion** should be handed to implementation. All old variants are traceability sources, not competing runtime rulebooks. No code, trainable model, native generation capability or empirical result is asserted by this paper. RC3 is a new architecture **review candidate**, not a freeze-approved bugfix; preserve RC2 separately for clean ablations.

## 0. Design objective and safety invariants

The Learning Algorithm (`LLA_DCR`) adapts physical directed synapses by local witnessed coactivity and bounded delayed eligibility, without Backpropagation, semantic token IDs, gradient propagation through a network, or invented labels. The baseline target demonstration is **learning and retaining context-dependent next-event predictions** (researcher notation `A→B→C` versus `D→B→E`).

- Every cell is dumb. Every synaptic update refers to actual cell IDs, source/target scope, time, and witnessed provenance.
- **Neural activity is not external evidence.** A prediction may drive A but does not prove occurrence.
- No retroactive learning for cells first committed at an event's end, or for a context candidate created after a completed observation root.
- Within the first lab, **all negative synapse updates are disabled**: `NEGATIVE_UPDATES_ENABLED=false` for `LOCAL`, `CROSS_TERRITORY`, and `ASSOCIATIVE`. The network may be unable to suppress wrong outputs; this is an experimental outcome, not license to change the rule silently.
- A candidate's temporary conjunction `PROBE` is a **bootstrapping activation**, never an evidence root. The RC3 **permanent binary physical P/C gate** (Core §5.1) remains in no-probe inference and does not supply activation energy. Learned normal synapses must independently sustain activity in cold tests.
- A uniquely matching COMPLETE owner may temporarily mask generic temporal B-anchor contributions (Core §5.2), without demoting, deleting or negatively updating old B→C evidence. Only the next real neural propagation is modulated; labels and expected Y never select the route.
- C04 correction is normative **within this review candidate**: both selected predecessor links must consolidate before a contextual candidate may become `COMPLETE`; root-dependent comparison IDs are not permanent ownership IDs.
- `RETRIEVE` must freeze W/H_slow and all evidence/candidate/owner metadata. Read-only feature input is not external training.

## 1. Dependencies on the Core companion

Only exact cell identity, committed-before-event, source/target activity, `A^(1)`, `A^+`, `F_step`, canonical SIC direct support, `R_cold`, scopes, frozen W/H and latent/budget gates are consumed from Core. The two documents share these definitions:

| Object | Exact responsibility |
|---|---|
| `Cell`, `Synapse`, `Assembly` | Core graph/schema, directed scopes and physical budgets |
| `EvidenceWitness`, `V_ext`, `LINK_PROPOSAL`, candidate phases | This LLA paper (witness data may be stored in Core's transactional metadata) |
| `F_step`, pass 1 / pass 2, `G_ctx`, `μ`, `CTX_RUNTIME` | Core dynamics; evidence eligibility requires separate LLA certification |
| `OwnerProfileV1/V2`, `StableBindingV2/V3` | Core governance/physical binding; V2/V3 typed hierarchy defined with LLA §6.6; LLA counts only legally consolidated source links |
| `BEGIN_EXPOSURE`, `END_EXPOSURE`, `ABORT_EXPOSURE` | Core transaction lifecycle; this paper defines root aggregation and synapse changes |
| `READ_ONLY_EPISODE` | Core scratch inference; no evidence updates under any circumstances |
| `GENERATE_EPISODE` | Core scratch G1/G2 rollout; internal SIC steps are never external roots nor evidence |
| `DERIVED_CONTEXT_WITNESS` | COMPLETE no-probe contextual predecessor with externally traced lineage, Core §6.1; LLA authorizes only P-role learning source, not independent root |
| `AssemblyID/SurfaceReadoutLedgerV1` | Core structural objects and peripheral rendering, respectively; LLA never reads a surface/ledger at inference or for q |

First lab synapse scope semantics: `LOCAL/CROSS_TERRITORY Δ=0`, `ASSOCIATIVE Δ=1`, context history `H_context=5`. All cross-event multi-lag spatial/cross synapses remain deferred. RC4 defines **bounded read-only multi-event self-generation** in Core §9.3; no learned data is generated from that self-rollout.

## 2. Event observation, witness and provenance model

### 2.1 Witness record and direct-support distinction

Before neural propagation for a valid external event, canonicalize the **actual** SIC feature multiset and salts, compute `X_ext[j]` and store an immutable local witness:

```text
ObservationWitness {
  witness_id = (exposure_id, event_order, canonical_feature_digest)
  direct_sources: sorted (cell_id -> X_ext[cell_id])
  feature_digest, SIC_salts/config digest, origin=EXTERNAL
  scope: COMPLETE_NEXT_EVENT | PARTIAL | UNSPECIFIED
  status: VALID | INVALID
}
```

`OBS_DIRECT(j,t)` is true iff this is a valid, real external event, `j` is a projected receiver and `X_ext(j,t)>0`. It does **not** require a comparator or a second outcome to exist, and can hold for a still-uncommitted cell. `OBS_ELIGIBLE(j,t)=OBS_DIRECT(j,t) AND committed_before(j,t)`. Only OBS_ELIGIBLE can provide valid directly observed learning/frontier participation. Malformed encodings, non-finite supports or invalid feature normalization yield `INVALID_OBSERVATION`.

Multiple observed features may project to one receiver: keep `CELL_FEATURE_ALIAS` diagnostic; do not attribute a unique word meaning. **Contrast evaluation** is separate:

```text
DISTINGUISHABLE(Y1,Y2):
    require comparable, completed, externally witnessed outcome footprints
    if no comparator -> NOT_EVALUATED_NO_COMPARATOR
    if inadequate coverage -> UNRESOLVED_COVERAGE
    if same neural direct footprints, different canonical observed features
           -> UNRESOLVED_COLLISION
    if same neural footprints and same observed features -> NO_CONTRAST
    otherwise compute weighted dY and apply declared contrast gates
```

A witnessed receiver's direct stimulation is not proof that a complete text pattern has a unique neural representation. Evaluator feature labels never add a missing discriminator to Core.

### 2.2 Tagged contribution lanes

Record causal lanes per **contribution**, not just one label per target cell:

`DIRECT_OBSERVED`, `SPATIALLY_COMPLETED`, `PREDICTED`, `CONTEXT_MATCHED`, `BOOTSTRAPPED`, `RESIDUAL`, `ATTRACTOR`, `DERIVED_EXTERNAL_CONTEXT`, `DERIVED_RUNTIME_CONTEXT`, `INTERNAL_SELECTED`, `READ_ONLY_OBSERVED`. All have typed origin and event indices; DERIVED is never silently promoted to DIRECT.

Each contribution contains `(target_cell_id,source_cell_id|NONE,event_order,lane,nonnegative_support,witness_roots,step_id)`. A cell may simultaneously receive direct and predicted support; keep both tagged. Pass-2 completion may increase `A^+` but cannot rewrite a predicted/spatially completed contribution as direct observation. Predicted-only, residual-only, attractor-only and probe-only contributions cannot independently provide external proof.

### 2.3 Context witness, runtime versus learning

For an **uncompleted** candidate z in LEARN, `ContextWitness(z,t)` can be valid only when z was committed before current event, actual predecessor/current external events are strictly ordered within the same OPEN exposure, both selected P sources have lawful same-root external direct SIC support or, for depth>1, a fully traced **COMPLETE no-probe DERIVED_EXTERNAL_CONTEXT** support and `Q6(min(P supports))>=tau_ctx_q6(z)` at predecessor step, ≥1 of selected C has direct current support, z actually participates at the learning threshold, and its probe (if active) uses only those witnessed sources. One-source predicted support is insufficient.

For a **completed** z, the persistent role binding requires two *consolidated* physical P→z keys plus at least one consolidated C→z and one consolidated z→Y. Runtime recognition `CTX_RUNTIME` checks the real current read-only observations and normal activity; it **does not** grant an evidence root. In READ_ONLY mode the old sealed external observation may be replayed as **features** for inputs, never as a reopened training transaction. `CTX_RUNTIME ⇒ V_ext` is forbidden.

### 2.4 Exact positive external link validation

Let `Verified(j,t)` be `OBS_ELIGIBLE(j,t)` OR a **valid** actual `ContextWitness(j,t)` participating in a matching current event, or (source-only ASSOCIATIVE previous step) `DERIVED_EXTERNAL_CONTEXT(j,t)` where j is already COMPLETE and its physical lineage is no-probe validated (§6.6); it is never generalized from any SPATIALLY_COMPLETED cell. Let `ActiveEligible(j,t)` require `committed_before(j,t)` and final `A_j^+(t)>=theta_active^(r_j)`.

For link `k=(i,j,scope)`, first reject if `mode!=LEARN`, no **OPEN external exposure**, malformed/unverified relevant witnesses, invalid scope/region, wrong source/target commitment timing, missing required coactivity or outdated structural eligibility. Then:

| Scope | Necessary and sufficient positive **source/target witness** conditions (in addition to universal checks) |
|---|---|
| `LOCAL` | `region(i)=region(j)`, source and target current event `t`, `Verified(i,t) && Verified(j,t) && ActiveEligible(j,t)` |
| `CROSS_TERRITORY` | different regions; same current event `t`; original cross-bind frontiers; `Verified(i,t) && Verified(j,t) && ActiveEligible(j,t)` |
| `ASSOCIATIVE` | event `t-1→t` within same OPEN root; `i∈F_step(t-1)`, `Verified(i,t-1) && Verified(j,t) && ActiveEligible(j,t)`, with any depth>1 derived source i additionally checked under §6.6 |

`V_ext(k,t)=1` only if all these conditions are satisfied and both endpoints were already committed before their respective learning events. If a needed comparator or source cannot be resolved, return `UNVERIFIED`, submit **no** positive or negative evidence. In RETRIEVE/REPLAY always `q_ext=0` regardless of activity.

**External temporal abstraction is permitted:** a witnessed contextual z (including an already COMPLETE higher-level derived source) may be an ASSOCIATIVE source to an observed outcome `y`; z need not receive a SIC bit directly if its ordered physical context observation and actual activation are verified. No candidate born at end of prior root is given retroactive evidence for that root.

## 3. Eligibility traces and canonical temporal learning

The earlier neural history remains in runtime R as bounded recent activations, while learning eligibility preserves source time and provenance:

\[
\mathcal E_i(t)=\{(a_i^{eligible}(s),s,exposure\_id,origin\_kind,witness\_id): t-H_{context}<s\le t\}.
\]

`H_context=5` in first lab, bounded by HARD_BOUNDARY and exposure closure. A transient scalar proposal (`e_i←max(λ_e e_i,a_i)`) is **not** sufficient on its own because it loses event provenance; an implementation may compress entries only if time/source/root/distinctness are exactly preserved. Do not fill records for events preceding a cell's commitment.

- Same-event `LOCAL/CROSS_TERRITORY` candidate edges use `Δ=0`; the **Pass-2 prediction source** is `A_i^(1)(t)`, but the **single fixed creation/evidence coactivity convention** is `LINK_PROPOSAL.a_source=A_i^+(t)`, `a_target=A_j^+(t)`, `create_coactivity=A_i^+(t)×A_j^+(t)` (both from the same frozen **final Pass-2** event snapshot). A normal same-event source **MUST** additionally be in the frozen Pass-1 emitter frontier `E_t^(1)`; CROSS also requires inherited cross-bind frontier eligibility for source and target. Merely having large final source A cannot substitute for E_t^(1). This is the new FIFR-B03 lab decision and is **not** the Pass-2 neural propagation activity.
- `ASSOCIATIVE` next-event edges use `Δ=1`, eligible preceding `F_step` source at `t-1`, target at `t`, with no boundary and identical OPEN exposure. `LINK_PROPOSAL.a_source=A_i^+(t−1)` **captured from the prior event when F_step was frozen**, `a_target=A_j^+(t)` from the current final Pass 2, and `create_coactivity` is their product. Do not recompute prior A from residual activity at current t or at END; store these exact sampled binary64 numbers in the OPEN root's event journal. Same-event proposal activity is also recorded at its original event and never recomputed at root-close.
- Earlier history `1<Δ<=5` is retained for *context discovery and candidate source selection*, not converted directly to a synapse with a hidden lag field or a forward A→C jump.
- `F_step` must reflect newly supported event participation, not mere residual `A_prev>=theta_emit`.

## 4. Link-local evidence mathematics

### 4.1 Quality, local prediction and positive evidence

**FIFR-B01/B02 numerical closure — new LAB-CONTRACT-01 choices, not inherited approved values.** There are TWO separate factors, never an overloaded `κ`:

| Legal scope/Δ | `k_neural` (propagation / PredScore) | `k_evidence` (q only) |
|---|---:|---:|
| `LOCAL, Δ=0` | `1.0` | `1.0` |
| `CROSS_TERRITORY, Δ=0` | `1.0` | `1.0` |
| `ASSOCIATIVE, Δ=1` | `1.0` | `0.7408182206817179` |

`0.7408182206817179` is a **stored binary64 literal** chosen for this lab as the rounded value of `exp(−0.30)`; do **not** evaluate `exp` on each call or apply it to neural propagation. Illegal scope/Δ pairs reject. Accordingly, for an **existing** link:

\[
Q_{ij}^{s}=d_{ij}S_{ij}(E_{ij}/E_{max}),\qquad
p_{ij}^{s}(\Delta)=A_i^{prop}(\Delta)Q_{ij}^{s}k_{neural}(s,\Delta).
\]

For LOCAL/CROSS, `A_i^prop=A_i^(1)(t)` (same-event); for ASSOCIATIVE, `A_i^prop=A_i^+(t−1)` **only when i belonged to frozen F_step(t−1)**. Core `P_S`, `P_T`, `PredScore` are Noisy-OR aggregates of exactly these `p` values, with `k_neural=1.0`; there is **no additional time decay**. In a new not-yet-materialized link, `Q=0` and **no** neural propagation exists, while a valid latent pair can still form a learning proposal.

**Root-weight / Replay table, first laboratory:**

| Mode / event origin | `ω_root` used in q | Ledger | External count |
|---|---:|---|---|
| `LEARN`, real validated `EXTERNAL` exposure | `1.0` | `E_ext` | +1 at most per completed root/key |
| `REPLAY`, internally recalled event derived from prior real root, only in declared replay comparison | `ω_P × ω_R = 0.50 × 0.50 = 0.25` **once** | `E_int` | 0 |
| `RETRIEVE`, any runtime observation | `0` | none | 0 |
| synthetic/internal event inside `LEARN` without real external root | `0` for external evidence; internal updates **disabled** | none | 0 |

**Default first-lab baseline is `REPLAY_ENABLED=false`, `R_max_effective=0`;** the only permitted Replay trial is a separate declared comparator with `REPLAY_ENABLED=true`, historical schedule `N_ext=10`, `R_max=3`, and the fixed `0.25` combined internal evidence weight. `ω_P` and `ω_R` are both **multipliers exactly once** on internal Replay q, never alternatives and never reapplied by the evidence store or scheduler; `φ=.50` caps the internal ledger, and `γ_int=.75` is the **distinct** later neural quality discount, not another multiplier on q. Replay uses the same legal scope/time `k_evidence` factor and never creates independent external roots. This explicit policy supersedes vague prior discount prose.

For a valid source/target proposal, define

\[
q_{ij}^{raw}=\omega_{root}D_{ij}A_i^{learn}(\Delta)A_j^+(t)k_{evidence}(s,\Delta),
\]
\[
y_{ij}^{positive}=clip\left(\theta_S+(1-\theta_S)\frac{A_j^+(t)-\theta_{active}^{r_j}}{1-\theta_{active}^{r_j}},\theta_S,1\right).
\]

`A_i^learn=A_i^+(t)` for LOCAL/CROSS and `A_i^learn=A_i^+(t−1)` from the frozen prior F_step snapshot for ASSOCIATIVE. Do **not** substitute `A_i^(1)` in q or link creation. Apply `q_ext=q_raw` only if `V_ext(i,j,scope,t)=1` in real LEARN; otherwise q_ext is zero. In REPLAY any allowed q credits only internal evidence (and the replay comparator never passes `V_ext`). For `D=1`, prior activity `0.8`, target final `0.6`, valid EXTERNAL root, `q_LOCAL=0.48` while `q_ASSOC=0.3555927459272246` (using stored time factor). Given an **existing** link with `Q=0.3`, prior source `A=0.8` produces temporal neural contribution **`p_ASSOC=0.24`**, not `0.177796...`. The Replay comparator's corresponding associative evidence is `0.08889818648180615`; any other q or P value is nonconforming.

**Negative updates off:** `q_negative=0` for *all* scopes. The RC4.1 target-scoped mask `μ_ij=μ_i × 1[not ContextTarget(j)]` (Core §5.2) is applied **only as a factor in neural temporal propagation to ordinary targets**, never to legitimate gated contextual candidates/owners and never directly in q, y, E, S, external counts, `V_ext` or proposal eligibility. The original source-only `μ_i` remains a frozen anchor-match record, not a blanket suppression of outgoing associative links. It may **indirectly** change future q through the resulting genuinely computed neuronal activity; that is ordinary causal forward dynamics, not a negative synaptic update. All positive evidence still requires the same independent external witnesses and provenance. A predicted E absent from observed C is NOT external evidence for E, and absence without a qualified context must never erase valid B→C from an unrelated branch. A future revision must implement `MatchedContext`, comparable complete coverage and target-miss semantics before enabling negative learning.

### 4.2 Within-root evidence reduction, paired target and sign conflicts

All validated proposals for `(link_key,exposure_id)` remain staged in an OPEN root. On `END_EXPOSURE`, sort by `(−q,event_order,proposal_ordinal)` and choose **one** positive proposal with maximum `q`, along with its **paired y**; *do not* separately maximize y. For example `q1=.20,q2=.50` in one root contributes `.50`, not `.70`. Record the accepted single external root count once.

A future mixed positive/negative mode would cancel both signs for the same key/root (`CONFLICT_NEUTRALIZED`), with no S/E/count update; in current first lab negative proposals never exist. An unresolved or rejected proposal gives zero q and zero count. OPEN or ABORTED roots do not count, and duplicate delivery of a COMPLETED root is invalid. `Replay` cannot create a distinct independent external confirmation from its source root.

### 4.3 Weighted update and bounded dual evidence ledgers

For existing link with valid accepted `q>0, y∈[0,1]`, pre-update `E=E_ext+E_int`, the inherited strength update is:

\[
\boxed{S'=\frac{ES+qy}{E+q}},\quad\lambda_{learn}=\frac{q}{E+q}.
\]

When initial `E=0`, first creation instead initializes `S=y` and `E_ext=min(E_max,q)`; never divide by zero. For external evidence (`q_ext=q,q_int=0`) or internal Replay (`q_int=q,q_ext=0`), update:

\[
E_{ext}'=\min(E_{max},E_{ext}+q_{ext}),\quad
E_{int}'=\min(\varphi E_{max},E_{int}+q_{int}),
\]
\[
E_{int}''=\min(E_{int}',E_{max}-E_{ext}'),\quad
E'=E_{ext}'+E_{int}''\le E_{max}.
\]

`φ=.50` initially. External evidence gets priority when total saturates; the internal ledger is truncated if needed. Saturated `E` remains the **effective** weighting mass for later S updates; continued valid external exposures can adjust S but do not produce unbounded mass or fake root counts. Set `internally_supported=(E_int''>E_ext')`, making future Q discount `γ_int=.75`. Root count is a number of **accepted distinct completed external roots**, not equal to E. One root can add evidence mass but at most **one** confirmation for that link.

### 4.4 Consolidation, episodic support and lifetime

- New positive legal link `CANDIDATE`, with `external_count=1`, `S=y`, `E_int=0`, positive first-root evidence and deadline `W_conf=100` events.
- `CONSOLIDATED` iff `S>=theta_S=.60`, `E/E_max>=theta_E=.30`, `external_count>=2`, plus valid live scope/commitment/latent/capacity. Two roots are **necessary but not sufficient**; with `E_max=10`, mass threshold is 3.
- If later the source laws permit S below `theta_demote=λ theta_S=.80×.60=.48`, demotion back to `CANDIDATE` is considered under inherited rules; first-lab positive-only targets `>=theta_S` will typically not generate this through positive updates alone. Any legal protection or demotion must be traceable to valid evidence and structural constraints, not silent deletion.
- After each `N_ext=10` external events (historical schedule), at most `R_max=3` internal Replay events may support eligible external-rooted candidate links, if Replay is enabled in a declared trial configuration. They run only after exposure closure, never while OPEN. The replay comparison applies `omega_P=.50 × omega_R=.50` **once as one q multiplier**, as mandated by §4.1; `phi=.50` is only the internal-ledger cap and `gamma_int=.75` applies only to later propagation quality, with no repeat discount. Scheduling priority:

\[
Priority(e)=S_e(1-E_e/E_{max})\exp[-\alpha_{rec}(t-t_{last\_ext}(e))],\quad\alpha_{rec}=.05.
\]

- An eligible Replay-supported candidate can be `EPISODIC_INDEXED` with window `W_episodic=2000`, subject to per-cell outgoing `E_cap=4` and network cap `G_cap=floor(.10×committedCells)`; eviction chooses lowest priority with deterministic key tie. No Replay can raise `external_count` or satisfy two independent external roots.
- Expiration/pruning may release **unprotected/unused** capacity, never delete an otherwise legal consolidated knowledge link merely to free a candidate resource. `W_conf=100` for ordinary links and `W_conf_context=240` completed-root external events for candidate-owned P/C/Y links, while `W_episodic=2000` remains unchanged. Contextual special deadline attaches to the exact reserved link keys at their first creation, terminates when the owner completes/expires and never grants indefinite extension or retroactive learning. The 240-event ownership limit is distinct from the 8/32 qualified-root limits.

## 5. First creation from latent pair: exact legal transition

**FIFR-B03 single source activity convention (applies equally to creation and q):**

| Link scope | Required source gating | `a_source` recorded | `a_target` recorded | `create_coactivity` | Neural propagation source (different contract) |
|---|---|---|---|---|---|
| LOCAL Δ0 | source in frozen `E_t^(1)`; valid direct/context witness | `A_i^+(t)` final | `A_j^+(t)` final | product of final A's | `A_i^(1)(t)` |
| CROSS Δ0 | source in frozen `E_t^(1)` and both endpoints meet cross-bind rules | `A_i^+(t)` final | `A_j^+(t)` final | product of final A's | `A_i^(1)(t)` |
| ASSOCIATIVE Δ1 | source in **prior** frozen `F_step(t−1)`, no boundary | `A_i^+(t−1)` saved from previous EVENT | `A_j^+(t)` final current EVENT | product of saved prior and current final | `A_i^+(t−1)` |

The event journal stores `source_event_order`, `a_source`, `a_target`, frozen frontier membership and timestamp, `create_coactivity` and q, with no recomputation at END even if H_slow or thresholds adapted meanwhile. For example, `A_i^(1)=0.40,A_i^+=0.80,A_j^+=0.50,theta_create=.20`: LOCAL creation uses `.80×.50=.40` and passes **only if** i belonged to Pass-1 `E_t^(1)`; `.40×.50=.20` is **neural-propagation support**, not the creation gate. If i did not meet E_t^(1), the proposal fails despite `.40` final coactivity. RC3 lowers `theta_create` from `.30` to `.20` only for legal directly witnessed LOCAL/ASSOC pairs, **not** CROSS and not the active frontier; this permits `.50×.50=.25`, while `.40×.40=.16` still fails. A lower creation threshold is not a fabricated positive witness.

A nonexisting synapse is **not** materialized at an arbitrary coactivation event. Create a `LINK_PROPOSAL` in the OPEN root's persisted staging journal, then apply it only at END root-close.

```text
LINK_PROPOSAL {
  link_key=(source,target,scope), exposure_id, event_order,
  a_source, a_target, create_coactivity, q_raw, y_positive,
  exact witness and lane proof, event-time latent proof,
  intended candidate reservation claim, proposal_ordinal
}
```

Necessary checks (a failure emits a named diagnostic, never a partial link):

1. `source != target`; both committed **before** their respective source and target learning events.
2. Legal scope/region and `Δ` (`LOCAL/CROSS=0`, `ASSOC=1`) and no intervening HARD_BOUNDARY.
3. `D_event=1` (latent neighborhood either direction at event snapshot), `V_ext=1`, eligible final target and source frontier per scope, `q_raw>0`.
4. Creation coactivity meets inherited per-scope threshold: `create_coactivity=a_source × a_target >=theta_create=.20` (`LOCAL/ASSOC`, **RC3 LAB**; RC2 `.30` comparator) or `>=theta_create_x=.39` (`CROSS`). The coactivity gate is **not** equal to q; do not mix them.
5. At `END_EXPOSURE`, recheck `D_close=1` from the single frozen pre-close W snapshot (unprotected latent recycling can invalidate it), plus commitment, scope, source outgoing capacity (`B_i=64`, RC3), cross capacity (`B_i^x=12`), and current pinned claims. For z source selection, prefilter exhausted candidate P/C before first-eight role pooling and try bounded radius-2 anchor cells as Core §7.3; otherwise valid evidence from highly frequent feature receivers can be blocked by saturated first-eight choices. If false: `STALE_LATENT_ELIGIBILITY`; no link, no E, no count.
6. Apply root-maximum reduction and canonical arbitration across proposals sorted by `(priority_class,-create_coactivity,-q,source_id,target_id,scope_order)`, `priority_class=0` for valid contextual pinned claim, else 1. One **shadow ledger** includes live outgoing links and unique reservations. Capacity arbitration is deterministic; source outbound limit `64`, cross limit `12`, episodic quota and global K_R unaffected.

When first accepted root wins, initialize exactly:

```text
Synapse {
 key=(i,j,scope); S=y; E_ext=min(E_max,q); E_int=0;
 E=E_ext; external_count=1; state=CANDIDATE;
 created_event_id=winning_event; created_exposure_id=root;
 last_external_event_id=winning_event; last_evidence_root=root;
 candidate_deadline=event_clock+W_conf; internally_supported=false;
 confirmed_roots/journal=the one accepted root
}
```

The directed link is visible to neural dynamics **only after** the entire END close commits. A reserved intended link converted to a live link transfers its capacity claim instead of double-consuming capacity. A still-pending proposal alone has no right to block legal recycling. If a new z is admitted at this same close, no link involving its previous phantom activation may be created from this root; z must participate in later OPEN exposures.

## 6. Context-dependent structural learning and probation

### 6.1 Reuse-first novelty evidence

Root-close may compare up to `16` qualified observed P/C/Y episodes per affected physical anchor, TTL `2000` external events. Compare weighted observed neural footprints using:

\[
d_w(U,V)=1-\frac{\sum_i\min(U_i,V_i)}{\sum_i\max(U_i,V_i)},\quad
 d_w(0,0)=0,\ d_w(0,V)=1\ (V\ne0).
\]

Define `c_ext=min(1,n1/2,n2/2)*coverage`, `nu_ctx=c_ext*d_P*d_Y`. Lab gates: at least 2 independently completed witnesses for **each** contrasting branch, `d_P>=.40`, `d_Y>=.40`, `nu_ctx>=.30`, comparison coverage complete and comparable; no unresolved neural SIC footprint collision. A context deviation alone, a prediction miss alone or one anomalous result does not justify recruitment.

Run read-only counterfactual `PredScore` with frozen W/H, new cold R, P then B observed through SIC, **never Y as neural input**; immediately after B compute P_T next and compare evaluator-only correct/alternative outcome footprints. A true *separation failure* requires latest **two additional qualified opportunities per branch** to fail `correct−alternative>=m_reuse=.05` under current frozen W. Missing comparator, incomplete outcomes, exhausted ledger or noise ambiguities ⇒ `UNRESOLVED` and zero recruitment, never guessed novelty.

### 6.2 Canonical owned branch selection and capacity-aware source admission (RC3)

Temporary `ComparisonBranchKey` may contain observed physical P/C/Y digests plus earliest root numbers for comparison ordering, but it is never permanent identity. A persistent `OwnerID` with bounded `OwnerProfileV1`/`StableBindingV2` for depth 1 or typed `OwnerProfileV2`/`StableBindingV3` for derived depth>1 controls reuse; a new comparator after TTL turnover MUST resolve to existing owner or fail unresolved, never silently duplicate. Both verified failing branches are attempted in canonical physical key order, without semantic labels.

For a new z, choose exactly 2 committed direct-witness P sources, 2 C sources and 2 observed outcome Y targets. Collect genuine supported candidates from completed qualifying external roots, filter P/C whose **new unique outgoing** claims have zero headroom (RC3 `B_i=64`) before choosing the top eight, rank remaining by independent roots/support/headroom/physical ID, and enumerate legal triples in bounded canonical rank-index order. Outcome Y receiver capacity is not debited; z→Y debits z. Existing same-key edges/reservations are not charged twice; P/C overlap requiring different directed keys consumes both. Exact physical roles are not words.

For P-pair require the **same numeric calibration as Core §5.1**, using legally traced external predecessor supports (DIRECT or no-probe DERIVED_EXTERNAL) and global canonical `Q6` quantization:

\[
T_z^{witness}=\min(o_{p0}(P),o_{p1}(P)),\quad L_z=\min_{owned}Q6(T_z),\quad U_z=\max_{confirmed\ rival}Q6(T_z),
\]
\[
L_z-U_z\ge 50,000=Q6(m_P),\qquad tau_{ctx,q6}(z)=U_z+50,000\le L_z.
\]

Two completed owned witness roots and the confirmed competing contrast witnesses are required. `tau_ctx_q6`, `L_z`, `U_z` are immutable physical integer statistics at accepted admission; they are copied into `StableBindingV2` or `StableBindingV3` exactly and are never inferred from Y labels, updated during inference, or populated by missing-rival defaults. The runtime gate uses only observed P supports and the stored threshold; its support test is NOT the obsolete `>0` rule. A new unseen rival may fail this admission-only separation; never silently change the threshold or claim generalization.

Also validate latent bidirectional D at event and close, six candidate z slots, protected claims, physical region scopes, and available capacity under one shadow ledger. Search at Manhattan radius ≤2 from a real current anchor, radius 1 first; reject with explicit capacity/contrast/frontier diagnostics rather than expanding silently. Store a bounded `AnchorSourceSet` of **all direct current observed receiver IDs** in the two owned qualifying examples (≤64 unique IDs), exclusively to scope source-temporal suppression on a **unique** later completed context. It is *never* a predicted Y lookup and may not be used in external q. A new z is admitted only at END within the last real EVENT remaining K_R, with no retroactive proposal or activity.


### 6.3 LEARN-only candidate probe, permanence and separated evidence clocks (RC3)

The Core §7.4.1 finite phase machine is authoritative: `WIRED→PROBE_INCOMING→LEARN_OUTCOME→NO_PROBE_TEST→COMPLETE`, otherwise `FAILED_OR_EXPIRED`. Permanent `G_z^{ctx}` from Core §5.1 requires **two qualified typed predecessor P witnesses (direct SIC or COMPLETE derived externally grounded) whose quantized minimum meets the immutable admission-calibrated `tau_ctx_q6(z)`, and ≥1 actual external SIC-observed current selected C at B in LEARN**, with physically legal role keys; it gates neural drive to zero when context is absent **in every mode**, including no-probe COMPLETE. The gate contributes **zero excitation**. For owned P/B in LEARN before completion, a separate temporary `PROBE` supplies:

\[
T_z^{probe}=\min(o_{p0}(P),o_{p1}(P)),\quad
C_z^{probe}=1-\prod_{c\in C_z}(1-o_c(B)),\quad
\hat D_{z,probe}^{(2)}=1-(1-\hat D_{z,base}^{(2)})(1-\eta_b T_z^{probe}C_z^{probe}),\quad \eta_b=1.
\]

Only in `G_ctx=1`, an **OPEN genuine LEARN event** with `phase∈{WIRED,PROBE_INCOMING,LEARN_OUTCOME,NO_PROBE_TEST}`, and with z committed before B does this extra drive exist. In particular, an unsuccessful first `NO_PROBE_TEST` at low Q leaves the candidate in that state **with probe ENABLED on subsequent real qualifying LEARN roots**, permitting real source/target activity and new Y-witnessed `q` until the original finite consolidation and age caps; the phase is not rolled back and the counters are not reset. The zero-probe test itself always runs in an isolated **END scratch clone**, with `PROBE=OFF` even though the production LEARN root of the same candidate used it. `RETRIEVE`, `REPLAY`, PRE/POST scratch, an already COMPLETE/EXPIRED candidate, and any READ_ONLY diagnostic cannot use probe. Missing real Y witness ⇒ no z→Y q, regardless of probe. No `V_ext` comes from the probe itself. Actual z emission plus real witnessed **next** Y can provide a lawful new z→Y associative proposal and, separately, P→z and C→z proposals. Probe OFF means remove this **additional** raw excitation, not the graph-local permanent G gate. Thus B-only cannot falsely activate z; true AB still MUST demonstrate enough learned Q to cross `theta_emit` without probe or yield `NO_PROBE_INSUFFICIENT_DRIVE`.

**Two clocks, one finite age:** `probe_matches≤8` completed qualified P/B roots only until LEARN_OUTCOME begins; `consolidation_matches≤32` additional completed qualified roots after entering LEARN_OUTCOME; `age_events≤240` external events from all completed roots after z admission, including nonmatching. The root entering LEARN_OUTCOME is probe-phase, not first consolidation match. Generic `W_conf=100` does not expire candidate-owned contextual links before their separate fixed `W_conf_context=240`; both windows are rooted at first creation and never reset on retry. Each root may contribute q **once per link**, regardless of phase or count. The 32 match cap is not a promise of consolidation.

**Feasibility illustration (EXTERNAL, ASSOCIATIVE, A_source=A_target=.50):** `create_coactivity=.25≥theta_create=.20`; `q=.5×.5×.7408182206817179=.1852045551704295`; therefore `ceil(3/q)=17` independent maximal eligible root contributions to reach `E≥3`, versus **8** old total matches. At `.45`, creation product `.2025` is legal and 32 accepted roots would yield E≈4.80, but any missing witness, target activity, source F_step or structural legality can invalidate that optimistic count. The source/target activity and y strength still must meet `S>=.60` and the two-root condition.

At END: settle evidence and the finite transition table **first**, allow a fresh **zero-probe scratch** test on the last budgeted qualifying root, then expire when probe match cap (if still in discovery), consolidation match cap (if in outcome/testing), or total age cap is reached. `NO_PROBE_INSUFFICIENT_DRIVE` is a nonterminal failed preflight: later real owned LEARN roots still receive temporary probe, may create one fresh Y-witnessed q per root/key and advance E, and then may retry zero-probe scratch only when W* changes; no scratch activity is credited. An unsuccessful new Y outcome never becomes the correct label for a future read-only inference; the comparator is held outside Core. No adaptive deadline extension or acceptance based on training success labels is legal.


### 6.4 **C04 corrected graduation: BOTH P, ≥1 C, ≥1 Y**

For exact directed key k, define `LC(k,W*)` iff a live legal consolidated synapse at post-evidence/pre-new-admission frozen W* meets **all**: S/E thresholds, ≥2 independent external accepted roots, source/target commitment, same-event/one-step legality, latent predicate, proper source budget and positive witness in the owned branch.

\[
DURABLE\_PATH_{C04}(z)=LC(p0\to z,ASSOC)\land LC(p1\to z,ASSOC)
\land\left[\bigvee_{c\in C_z}LC(c\to z,LOCAL)\right]
\land\left[\bigvee_{y\in Y_z}LC(z\to y,ASSOC)\right]
\land SAME\_OWNED\_WITNESSED\_BRANCH.
\]

**Do NOT** use C03's obsolete `≥1 P` rule. The two selected predecessors are indispensable to the documented `CTX_RUNTIME` conjunction even if a temporary read-only trial happens to pass with one. Do not secretly require both C/Y links to consolidate; their inherited threshold is **one each**.

`COMPLETE` requires `phase=NO_PROBE_TEST`, durable path, and pass of all owned/rival/B-only cold tests in **both** configurations:

- `NORMAL_W`: ordinary no-probe neural dynamics.
- `CONSOLIDATED_W`: masks every nonconsolidated candidate-owned P/C/Y link.

Both must pass owned z `A>=theta_emit`, rival/B-only z `A<theta_active`, correct-vs-alternative next neural PredScore margin `>=.05`. **Critically**, in scratch no-probe tests create a nonpublished **hypothetical COMPLETE owner** with the exact proposed consolidated binding, enabling the same permanent G gate and next-step `μ` source masking that would apply after graduation; otherwise the candidate could never test its post-graduation contextual priority. This is a shadow readout/temporal simulation, not permission to generate training evidence or mutate W. These diagnostic runs must not mutate caller state, W/H, evidence roots, or phase counters.

Before retiring candidate-only probe/phase/role metadata, construct **StableBindingV2 (`schema_version=2`, direct depth-1) or StableBindingV3 (`schema_version=3`, derived higher-level) from exact currently legal consolidated physical keys**, with **both P** keys in fixed order, **the same immutable `L_z,U_z,tau_ctx_q6` integer triple** immediately after P IDs in its canonical binding payload, and all currently consolidated selected C/Y keys (at least one each), role offsets, owner reference and scoped link fingerprint. A legacy `StableBindingV1` without the threshold fields, or a typed higher-level binding improperly stored as V2, cannot be loaded as an active RC3.1 context (`UNSUPPORTED_BINDING_SCHEMA`). In isolated PRE/POST scratch copies of the **same** W*, retire only candidate-only metadata in POST; replay identical cold P/B cases through both NORMAL/CONSOLIDATED settings with probe OFF. `CTX_RUNTIME`, `G_ctx`, `tau_ctx_q6`, `μ`, relevant `F_step`, `A_z` and neural `PredScore` must be **bit-identical** before and after retirement. Else `RETIREMENT_SEMANTICS_DRIFT`, remain `DURABILITY_PENDING`. A link invalidated later ⇒ binding `STALE`, no candidate-only fallback and no contextual output from stale binding.

### 6.5 Owner dedup after 2000-event contrast TTL

`OwnerProfileV1` (direct) or V2 (derived typed P) retains bounded two completed-root externally grounded witness profiles (top-eight P/C/Y receiver supports and full footprint digests, plus a bounded immutable `AnchorSourceSet` of ≤64 directly observed current SIC receiver IDs (union of two qualifying C witnesses) for graph-local temporal routing), fixed physical selected role keys, candidate z, anchor, owner status and binding reference. It persists while candidate active/complete or validated partial knowledge requires protection; the *short* contrast ledger can expire separately. Every OwnerID is never recycled, and capacity is bounded by actual contextual-candidate/retained-partial-knowledge cells.

At root-close `ResolveOwner` scans **only** the anchor's finite registered profiles in canonical owner order, not whole W. First attempt exact actual observed footprint+physical role equality (root ID never part of equivalence), then positive physical P/C role overlap with outcome-coverage compatibility; ambiguous multiple/stale/aliased matches return explicit unresolved/stale. A **new** owner may be approved only after the two-direction predecessor-pair discrimination check with both witness samples against **every relevant** retained owner, and all normal novelty, failed reuse, bounded top-eight feasibility and capacity gates. If knowledge exists but is partial (`EXPIRED_VALIDATED`) return review-required, not duplicate. `EXPIRED_EMPTY` retry policy is deferred and cannot auto-admit. Outcome digests are **governance/test witnesses only**, never a `branch→Y` neural output mapping.

All OwnerID allocation, profile/index publication, candidate admission, link updates, claimed slots and completed root marker occur in the **same atomic root-close shadow transaction**. Same root re-delivery or crash/retry cannot allocate a second owner.

### 6.6 RC4 derived-external provenance and higher-level context learning

Core §6.1 owns typed witness creation, causal parent references, depth and inference support; LLA owns the **strict additional evidence gate**. The baseline `OBS_DIRECT/OBS_ELIGIBLE` definition is **not changed**; `DERIVED_EXTERNAL_CONTEXT` is a **distinct** valid previous-event ASSOCIATIVE source only (never a new SIC direct observation). For selected P source `p`:

```text
EligibleExternalP(p, root, t_prev):
    if OBS_ELIGIBLE(p, t_prev): return DIRECT and witnessed X_ext
    if p is COMPLETE contextual source and live StableBinding V2/V3:
        require parent context gate true at t_prev, no probe contribution
        require p emitted in frozen F_step(t_prev) above theta_emit
        require its recursive parents completed valid ordered events
                inside this very OPEN external root (max depth 8)
        reject any INTERNAL_SELECTED, REPLAY, PREDICTED_ONLY,
                BOOTSTRAPPED, RESIDUAL-only or missing root trace
        return DERIVED_EXTERNAL_CONTEXT and Q6(A_p^+)/1e6
    else: return INVALID
```

At `END_EXPOSURE`, compare eligible P candidates using the actual typed numeric support and previously frozen events; a new depth>1 z can be admitted **only if every contextual parent source was COMPLETE *before admission* and is never learned from future data in this root**. Retain provenance kind (DIRECT / DERIVED), `parent_OwnerID`, `parent_binding_generation`, DAG depth, and per-role physical IDs in immutable governance bindings: use `OwnerProfileV2/StableBindingV3` if any P is derived, and keep V1/V2 contracts for pure direct depth-1. The role footprint used for owner comparison must encode typed source kind and parent binding generation (`FP-ROLE-V2`) in a new domain separated SHA-256 digest. Define canonical bytes for this RC4 new digest exactly as:

```text
ASCII("DGCA-ROLE-V2") || 0x00 || role_u8 || item_count_u32_BE || records sorted cell_id ascending
record = global_cell_id_u32_BE || support_millionths_u32_BE
       || kind_u8 (DIRECT=0, DERIVED_EXTERNAL_CONTEXT=1)
       || parent_anchor_global_cell_id_u32_BE (0 for DIRECT)
       || parent_owner_counter_u64_BE (0 for DIRECT)
       || parent_binding_generation_u32_BE (0 for DIRECT)
```

`role=P/C/Y` uses historical role bytes `0/1/2`. For C/Y only DIRECT observations are allowed and kind=0. This v2 encoding supersedes v1 for any mixed predecessor pool, and root/session IDs are **never** placed into stable footprint identity. Distinct parent `OwnerID`s are scoped by anchor; the record therefore includes parent anchor and sequence number as separate fixed-width fields. All DIRECT source parent fields are zero; nonzero DERIVED fields must match the live parent binding. The standard owner-record SHA-256 domain becomes `"DGCA-OWNER-PROFILE-V2\0"`, and items retain the fixed order P,C,Y. Changing a parent binding generation makes the descendant fail closed (not learn on a different referent). Do not attempt automatic V1→V2 migration on saved knowledge. Candidate branch comparison is from *actual* externally witnessed direct/derived physical activity, never from raw_surface, an internal generated event, a surface ledger or ground-truth Y during inference.

Each higher-order link's `V_ext` still requires **actual** ordered external current-event B/Y from one OPEN independent root, correct scope Δ=1, real source activation, valid role eligibility, legal D/budgets and only one maximal accepted q per `(link_key,exposure_id)`. The recursive proof does **not** multiply q, invent extra independent roots, or allow source link creation without `theta_create`. Externally observed outcomes Y alone may validate the result; **internal generator outputs never do**. `MAX_CHAIN_DEPTH=8` bounds hierarchy; no Δ>1 synapse is created. A failed prerequisite is `DERIVED_PROVENANCE_UNVERIFIED`, `PARENT_NOT_COMPLETE`, `CONTEXT_CHAIN_DEPTH_EXCEEDED`, `PARENT_BINDING_STALE` or `CONTEXT_CHAIN_CYCLE`, not an automatically substituted direct witness.

**One additional RC4 learning constraint:** formation/confirmation of Assembly structures uses only genuinely externally grounded emitters and consolidated reciprocal `LOCAL` links (Core §2.0). LLA MUST NOT create, reinforce or fake a reciprocal link merely to pass an Assembly threshold; each direction needs its own valid same-event proposal, local source pass-1 emission and target eligible witness, evidence mass and two external roots. If the source eligibility rules never create a valid reciprocal triangle, return `NO_RECIPROCAL_TRIANGLE` and mark native Assembly/G1 generation empirically blocked, rather than spawning fixture Assemblies. This is a measured core research risk.


## 7. Complete root/event execution contract for learning

1. `BEGIN_EXPOSURE` requires CLOSED and strictly new monotonically increasing root ID. It atomically clears working activity, history, Attractors, F_step, eligibility and prior-root witnesses to `R_cold` **before** event 0. It does **not** reset learned W or slow H. **FIFR-B06 LAB POLICY A:** atomically persist an immutable full `H_slow_BEGIN` checkpoint before the first event alongside the root OPEN marker; subsequent EVENTs may adapt current H_slow but cannot overwrite this baseline. Optional first-event hard-boundary flag is normalized true. No continuous stream carrying context across independent roots in this lab.
2. Each `EVENT(order=0,1,2,...)` uses a frozen W/H/R snapshot, validates true external SIC input, computes observation witness, normal two-pass activation, optional legal candidate probe, F_step/provenance and local eligibility/proposals. Admit uncommitted direct sensory receivers **only at end of their event** within K_R; such receivers do not enter same-event learning. Event progress, sensory commitment and pending root journal publish as atomic checkpoints; no externally credited S/E/count until END.
3. `END_EXPOSURE`: canonical link/root maximum reduction; event/close latent proof, scope, first creation, outgoing claims and evidence settlement; update candidate phase/durability on one post-evidence W*; run independent read-only scratch checks; discover contrasts and `ResolveOwner`, admit any legal candidates within last event's **remaining** K_R budget; publish all accepted changes and `COMPLETED` marker atomically. END itself is **not a new event** and does not provide a free K_R allotment.
4. `ABORT_EXPOSURE`: atomically restore **exactly** `H_slow_BEGIN`, mark ABORTED, discard pending link evidence, uncommitted candidate/root-comparison changes and current root temporary claims, and reset working R. Prior lawful per-event sensory admissions in W MAY remain; no H_slow adaptation from an aborted root may remain. Any crash before ABORT commit recovers OPEN with its last event checkpoint **and the immutable BEGIN image**, allowing exactly one idempotent restore; a duplicate ABORT must never overwrite adaptations of later completed roots. ABORT cannot affect valid knowledge from previously closed roots.
5. Crash while OPEN must restore exact last event checkpoint with next order and staged proposals. Crash during END must restore either all pre-close or all post-close state, with no half-candidate/half-root. A duplicate COMPLETED/ABORTED root cannot be reopened as a new observation.
6. No internal REPLAY/RETRIEVE while an external root is OPEN. `READ_ONLY_EPISODE` consumes actual feature input, has no training exposure_id, no evidence and no change to caller state.

### 7.1 RC4 learning/generation separation and readout evidence

RC4 `GENERATE_EPISODE` is **not** an `END_EXPOSURE` and has no external `exposure_id`. It may consume a frozen neural winner's peripheral attested surface and original canonical mechanical SIC feature bundle only **after** neural winner selection (Core §§9.3–9.4), and must inject it as `INTERNAL_SELECTED`, never an `EXTERNAL` witness. Under `GENERATE`, set `V_ext=0`, `q_ext=q_int=0`, `external_count_delta=0`; do not create links, admit/recruit cells, alter context owner states, evidence, `H_slow`, Assembly graph/ID/generation, or peripheral witness counts. No newly generated event may later be replayed as an independent true training root. The selection FULL/CONTROL is scratch-only and never a second event; source sensory input on an INTERNAL_SELECTED event suppresses its **own** temporal target contribution exactly once via `P_T_debit_selected` (Core §9.3), without suppressing the legal incoming contextual temporal path.

Peripheral attestation receives **one** immutable `END_EXPOSURE`-published outbox notification per eligible `(root,event,preexisting LIVE assembly ID + generation, surface,bundle,marker)`, keyed idempotently; evidence for this association is a separate **peripheral** two-independent-external-root confirmation, **not** E_ext and **not** an associative synapse. New or structurally modified Assemblies cannot claim already processed event observations. An ambiguous association (`surface` collision or conflicting SIC bundles) remains ambiguous; Core/LLA are prohibited from consulting the association to choose a neural Assembly. EOS is a learnable lexical output with an explicit peripheral marker, not a zero-cost `HARD_BOUNDARY` evidence event.

This integration offers a **hybrid** event-level rollout G1/G2 under finite attested lexical coverage. It does **not** define general productive G3 role substitution or encode arbitrary previously unseen words as outputs. The evaluation must distinguish exact training-sequence reproduction from a withheld novel composition; no success claim of composition may be made solely from long autoregressive rollout.


## 8. Tests and reproducible failure gates

### 8.1 Formal contract counterexamples (expected, **not executed**)

| ID | Setup | Required result |
|---|---|---|
| LLA-T01 | First observed A on uncommitted receivers | Admission possible; no same-event positive learning from newborn cell |
| LLA-T02 | A/B direct witnesses with no C/E comparator | Legal direct positive witnessed relation; `NOT_EVALUATED_NO_COMPARATOR` only for contrast |
| LLA-T03 | Different observed C/E with identical neural SIC footprint | `UNRESOLVED_COLLISION`; no fabricated contrast specialty |
| LLA-T04 | Prediction-only E alongside externally observed C | External proof for E=0, valid proof for C only if relation truly qualifies |
| LLA-T05 | Two q proposals `.20,.50` same link/root | One q=`.50` with paired y; one accepted external confirmation |
| LLA-T06 | Provisional link lost D_close by latent recycling | `STALE_LATENT_ELIGIBILITY`, no q/E/root count accepted |
| LLA-T07 | Contextual pinned latent slot under recycling | `RECYCLE_BLOCKED_CANDIDATE` |
| LLA-T08 | Candidate only one selected P→z consolidated | `DURABILITY_PENDING`, no COMPLETE, even if current no-probe score succeeds |
| LLA-T09 | Both P, ≥1 selected C, ≥1 selected Y consolidated; PRE/POST scratch identical | Candidate eligible for atomic COMPLETE only after all other gates |
| LLA-T10 | Candidate no-probe NORMAL passes but CONSOLIDATED-only fails | Pending/expiry, never declare durable success |
| LLA-T11 | Contrast ledger expires; repeated same physical observed branch with new roots | Same OwnerID via ResolveOwner or explicit unresolved, **no duplicate z** |
| LLA-T12 | Two distinct branch owners support same new branch | `OWNER_REGISTRY_CONFLICT` or unresolved; no guessed new owner |
| LLA-T13 | BEGIN new root with residual previous Attractor and A_hist | Full cold isolation before event 0 |
| LLA-T14 | Root aborted after staged evidence | No S/E/count, H_slow exactly restored from BEGIN, previously lawful sensory admissions remain |
| LLA-T15 | Crash/retry at END | Identical W, OwnerIDs, accepted roots and reservations, one atomic commit |
| LLA-T16 | READ_ONLY P/B, no root open | Legitimate context runtime from actual features; no q/ext/root creation |
| LLA-T17 | Negative target miss in first lab | No negative update at any scope, even if target was expected |
| LLA-T18 | Replay same external experience multiple times | E_int allowed only by policy; E_ext and independent external_count unchanged |
| LLA-T19 | A=.8, Q=.3 ASSOC prior F_step, A_target=.6 real external | p=.24, q=.3555927459272246; never multiply `k_evidence` into p |
| LLA-T20 | Replay comparator enabled for same source/target | ω=.25 exactly once; q=.08889818648180615, external_count unchanged; baseline Replay off |
| LLA-T21 | Same-event source Pass1=.40, final=.80, target final=.50 | coactivity=.40 (subject to Pass1 gate), not `.20`; END uses staged activity |
| LLA-T22 | New candidate WIRED, first qualifying root emits but no Y | transition to PROBE_INCOMING only if incoming q accepted; opportunity consumed; no skipped phase |
| LLA-T23 | Candidate reaches age=239; a completed last root brings age=240 | settle evidence/valid tests before age expiration; else FAILED_OR_EXPIRED |
| LLA-T24 | OPEN root modifies g/threshold then ABORT | exact H_slow_BEGIN rollback, no root q, crash/retry idempotent |
| LLA-T25 | strong C→z without P; cold B-only | `G_ctx=0`, contextual `A_z=0`, no z F_step, no μ; B generic path remains |
| LLA-T26 | exact owned P/B and consolidated P/C/Y, probe off | `G_ctx=1`; z activation is weight-dependent; must exceed theta_emit or report `NO_PROBE_INSUFFICIENT_DRIVE` |
| LLA-T27 | completed unique z for DB; generic B→C remains strong | μ=1 on observed B anchor sources for next one-step P_T, B→C W evidence unchanged; require E-vs-C margin |
| LLA-T28 | B alone, same W/H, no owner match | μ=0; original B→C response preserved; no negative update |
| LLA-T29 | two matching different owners same current anchor | `AMBIGUOUS_CONTEXT_OWNER`, μ=0, no arbitrary semantic winner |
| LLA-T30 | A_src=A_tgt=.50 on LOCAL/ASSOC proposal | create product .25 passes θ_create=.20; q_ASSOC=.18520455517; mass E≥3 needs ≥17 independent roots |
| LLA-T31 | first 8 roots yield valid z→Y; next 17 valid consolidation roots | not expired solely by old eight-root cap; possible E≥3 (test other guards independently) |
| LLA-T32 | top-eight P candidates saturated at 64 but next candidates have headroom | filter saturated before rank truncation; choose legal alternative or explicit capacity refusal |
| LLA-T33 | z candidate own microcolumn/radius1 full but radius2 has feasible slot | deterministic radius-2 search; validate all D/protected budgets |
| LLA-T34 | feature receiver has 64 live outgoing and appears in P/C | cannot exceed B_i; no destructive release; `SOURCE_OUTGOING_CAPACITY` if no feasible alternative |
| LLA-T35 | preflight owner shadow before COMPLETE and after retirement | bit-identical G, immutable tau_ctx_q6, μ, A_z, F_step and P_T/PredScore under frozen W/H |
| LLA-T36 | selected P pair has `L_owned=.80`, `U_rival=.20`, `m_P=.05`, rival supports both positive | `tau_ctx_q6=250000`; owned G=1, rival G=0; no name/outcome comparator at runtime |
| LLA-T37 | admitted P pair exact boundary `L=250000`, `U=200000` (Q6), m_P=50000 | legally admitted with `tau=250000`; owned `>=` passes, rival fails; deterministic ties and SAVE/LOAD |
| LLA-T38 | `NO_PROBE_TEST` fails initially with E=3, insufficient drive; next independent owned OPEN LEARN P/B/Y | z retains live LEARN probe, Y-witnessed q/E can increase; END scratch OFF; no double count; old 32/240 caps unchanged |
| LLA-T39 | failing NO_PROBE_TEST followed only by read-only/replay/missing Y | zero probe/evidence in read-only; replay never external; missing Y never credits z→Y |
| LLA-T40 | save/load or PRE/POST without RC3.1 threshold triple, or legacy StableBindingV1 record | `INVALID_CONTEXT_THRESHOLD` or `UNSUPPORTED_BINDING_SCHEMA`; never silently use predecessor `>0` gate |
| LLA-T41 | rival P supports positive but below stored `tau_ctx_q6`, repeated while owner in LEARN | not a qualified owned root; no candidate clock advance or context probe; ordinary witnessed learning independent of z may still occur |

### 8.2 Required *empirical* program milestones, not paper claims

**Gate A — unit and transaction:** canonical SIC, same-root q,y aggregation, exact scopes, source budgets, candidate source selection, OwnerProfile and StableBinding persistence, crash/rollback and read-only immutability.

**Gate B — isolated mechanism:** small fixture network with known legal directed links; observe two-pass, new-event F_step and AB/DB separation; also known-legal Assembly fixture for causal-gain readout (not spontaneous Assembly claim).

**Gate C — learn from zero:** first LANGUAGE lab starts without hand-coded AB/DB→Y links; train multiple **independent external roots** for `AB→C` and `DB→E`, including separate roots for new SIC sensory commitments, observation confirmation, candidate admission, and candidate probation. Record first legal q and root IDs for each critical P→z, C→z, z→Y. Run C04 two-P/no-probe and cold retrieval. Compare correct/alternate neural `PredScore` and wrong activations. Report all failure statuses.

**Gate C / RC4.1 native-surface readiness subgate (measurement, no threshold tuning):** Track the earliest accepted `receiver_commit_root`, first legal proposal root for each of the **six directed LOCAL edges** of a prospective triangle, per-key `(q_root_max,E_ext,S,external_count,coactivity,latent_status)`, `assembly_birth_root`, every `assembly_generation` change, and the first two later eligible `attestation_root` IDs. Require same post-birth LIVE generation and identical surface/feature/marker tuple for both confirmations, with event-time `CoreCoverage>=.70` and fresh `M_A>=.40` witnessed for each. Use `N_local≈ceil(3/a²)` only as an idealized constant-activity lower-bound comparator for LOCAL links with valid external evidence and q≈a²: at a=.45, .60, .70, .80 the respective **post-commitment** link-consolidation counts are 15, 9, 7, 5, with best-case **cold-start totals** at least 18, 12, 10, 8 roots after adding one commitment and two later attestation roots. `support=.60` is not a proof of `.45` final activity, and a legal 3-cell mutual triangle is not guaranteed by four SIC projections or by root repetition. If no triangle forms, report `NO_RECIPROCAL_TRIANGLE` and inspect geometry, directed reciprocal link creation and capacity before adjusting curriculum. If the Assembly mutates after its birth, new generation attestation starts again; if a surface collision appears, do not certify readout. These are experimental observables, **not** additional normative root-count caps or a performance promise.

**Gate D — ablation and comparison:** original DGCA v2 activation baseline versus DCR, probe disabled vs enabled, z-path disabled vs present, fresh-attractor vs no attractor, replay on/off, verified witness vs unsafe activity-based evidence in an isolated research test; compare learning speed, capacity/recruitment, old-knowledge retention and resource costs. Do **not** quietly modify normative model mid-trial to obtain success.

**Gate E — generalization:** unseen combinations, same-outcome branches, contradictory branches, longer contexts, missing inputs, SIC collisions and budget saturation. Declare scope limitations for autonomously generated long text and native Assembly output.

Every run stores configuration and numeric precision, SIC salt digest, random seed, baseline source SHA, implementation commit SHA, full accepted/aborted exposure journal high-watermark and a reproducible metrics manifest. Contract-level PASS is NOT empirical Core PASS.

### 8.3 RC4 mandatory acceptance / falsification tests (NOT executed)

| ID | Given / action | Required result |
|---|---|---|
| `LG-T01` | two committed source cells have reciprocal LOCAL CONSOLIDATED edges to third, all triangle pairs R≥.10, fresh witnessed emission | only a legal size-3 Assembly may FORM; deterministic ID and reverse membership; otherwise `NO_RECIPROCAL_TRIANGLE` |
| `LG-T02` | only one direction of each triangle link has consolidated, or candidate links are not consolidated | zero native Assemblies; no fabricated reciprocal completion or fixture success |
| `LG-T03` | mutate Assembly membership, merge/split or restart twice | old ledger generation cannot render the new Assembly; outbox notifications are idempotent, IDs not reused |
| `LG-T04` | z1 completed and emitted without probe on true external P/B; z2 chooses z1 as P and then sees external Y | typed DERIVED_EXTERNAL may qualify P but exactly one true external root/q credit per key; no hidden Y/source IDs |
| `LG-T05` | z1 emitted only from LEARN probe, or from a predicted-only/replay/internal-generated event | no DERIVED_EXTERNAL; no higher z recruitment or E_ext update |
| `LG-T06` | depth 8 child tries to spawn ninth-level context; stale parent ID/generation or cycle | reject specified code, never fallback to DIRECT |
| `LG-T07` | selected best Assembly G outputs SIC receiver j whose prior P_Tj>0 | X_int,j applied once, P_Tj zero on selected receiver only, legal P_T→context z preserved; no repeated FULL activity injection |
| `LG-T08` | two same-surface/different-bundle events or two surfaces attach to same Assembly | no ungrounded winner text; return READOUT_AMBIGUOUS(_PENDING) |
| `LG-T09` | after independent text root confirms G only once or G formed same END | UNKNOWN; second *later* independent witnessed root required |
| `LG-T10` | GENERATE with 5 uniquely decodable legal Assembly steps then EOS | ordered 5 surfaces, correct read-only provenance, no W/H/ledger mutation, independent EOS termination |
| `LG-T11` | generated trace enters repeated winner/frontier pair twice consecutively or exceeds 32 accepted steps | deterministic loop/length stop, never infinite generation |
| `LG-T12` | winner G not readout-attested but runner-up is printable | STOP UNKNOWN rather than selecting lower rank via lexical lookup |
| `LG-T13` | context source z1 activations are direct-only/but wrong prior event order, or synthetic matched source during LEARN | no higher-level witness and no external q; unverified provenance error |
| `LG-T14` | training unseen combination held out entirely | report G3 compositional score separately from G1/G2; do not infer G3 from memorized rollout |
| `LG-T15` | Depth-1 z1 uniquely matches W1/W2, so `μ_p1=1` for direct W2 source p1; a legal depth-2 contextual z2 with `(z1,p1)` as prior P has a live incoming p1→z2 ASSOCIATIVE key; concurrently generic p1→Y exists | next event `μ_p1,Y=1`, `μ_p1,z2=0`; P_T to generic Y is suppressed while the **normal physical** p1 contribution to z2 remains, gated by z2's own G_ctx. Same result in LEARN and scratch FULL/CONTROL; no q/W mutation |
| `LG-T16` | Cold word starts with uncommitted SIC receivers; directed LOCAL triangle E per edge accrues q=.2025, .36, .49, or .64 independently per complete root; track FORM then the next distinct roots | do not assume fixed 9–11 roots: idealized post-commitment N=15/9/7/5 and minimal cold totals 18/12/10/8, respectively, only if all six edges, eligibility, S, shape, exact generation and fresh coverage remain valid. Newly formed assembly receives 0 birth-root attestations and needs 2 later independent roots; absent triangle yields `NO_RECIPROCAL_TRIANGLE` instead of fabricated readout |


## 9. Full evidence and candidate parameter registry

| Parameter | Value / meaning | Status |
|---|---|---|
| `E_max`, `theta_S`, `theta_E` | 10.0, 0.60, 0.30 | inherited CAL |
| `lambda` for demote | 0.80; `theta_demote=.48` | inherited factor |
| `theta_create`, `theta_create_x` | .20, .39 | .20 RC3 LAB; .30 original comparator; cross unchanged |
| `theta_pred`, `eps_p` | .25, 1e-6 | inherited CAL |
| `K_R` | 12 new Cells per event; nominal 8 sensory / 4 contextual transferable | inherited + LAB |
| `theta_R` | .30 original novelty threshold (not identical to DCR `nu_ctx_min`) | inherited CAL |
| `H_context` | 5; `ASSOC` forward Δ fixed to 1 | modified first lab |
| `E_cap,G_cap` | 4 outgoing episodic / floor(.10×committed) network | inherited |
| `W_conf`, `W_conf_context`, `W_episodic` | 100 ordinary, 240 contextual candidate-owned, 2000 episodic external events | 240 RC3 LAB |
| `omega_P,omega_R,phi, gamma_int` | .50,.50,.50,.75 | inherited constants; combined policy FIFR-B02 |
| `ω_root(EXTERNAL LEARN)` | 1.0 | FIFR-B02 LAB |
| `ω_root(REPLAY)` | .25 = .50×.50 exactly once; REPLAY OFF by default | FIFR-B02 LAB |
| `k_neural(LOCAL/CROSS/ASSOC)` | 1.0/1.0/1.0 at legal Δ | FIFR-B01 LAB |
| `k_evidence(LOCAL/CROSS/ASSOC)` | 1.0/1.0/0.7408182206817179 | FIFR-B01 LAB |
| `LINK_PROPOSAL` activity sources | final/final for same-event; frozen prev-final/current-final for ASSOC | FIFR-B03 LAB |
| `SIC/float/fingerprint` | Core §3.1 SIC-V1, decimal millionths, SHA256, big-endian record encoding | FIFR-B04 LAB |
| `candidate transition guards` | Core §7.4.1; END-only transitions, **8 qualified discovery roots + up to 32 further qualified consolidation roots + 240 completed-root external events**; failed NO_PROBE_TEST leaves production LEARN probe available until completion/expiry | RC3.1 LAB |
| `ABORT slow-state policy` | H_slow restored to BEGIN checkpoint atomically | FIFR-B06 LAB |
| `N_ext,R_max,alpha_rec` | 10,3,.05 | inherited CAL |
| `n_branch_min`, `predecessor_witness_count` | 2 per branch | LAB |
| `dP_min,dY_min,nu_ctx_min` | .40,.40,.30 | LAB |
| `m_reuse,m_P` | .05,.05 | LAB |
| `contrast ledger` | 16 qualified comparisons/anchor, TTL 2000 ext events | LAB |
| `role pools` | first 8 **feasible** P/C after outbound headroom filtering; first 8 witnessed Y; bounded enumeration | RC3 LAB |
| `source outgoing B_i`, candidate search | 64 (32 RC2 comparator), anchor Manhattan ≤2 | RC3 LAB |
| `AnchorSourceSet` | union of current witnessed owner receiver IDs, maximum 64 | RC3 LAB |
| `G_ctx`, `μ_i`, `μ_ij` | Core §5.1–5.2 calibrated P gate; `μ_ij=μ_i·1[not ContextTarget(j)]` preserves legal depth>1 gated context target inputs; generic one-step suppression only; no evidence multiplier | RC4.1 LAB |
| `selected_role_count` | exactly 2 P, 2 C, 2 Y | LAB |
| `hierarchical P provenance` | direct SIC or COMPLETE no-probe DERIVED_EXTERNAL P from same actual OPEN root, max depth=8 | RC4 LAB |
| `FP-ROLE-V2/StableBindingV3` | typed direct/derived source, physical parent OwnerID/generation and depth | RC4 LAB; v2 context-only |
| `Assembly creation` | Core §2.0 reciprocal CONSOLIDATED LOCAL triangle, ≥3 and ≤16 members; cap 12 FORM/END | RC4 LAB |
| `GENERATION` | readonly max 32 events, neural-first readout, targeted selected-SIC P_T debit, no learning | RC4 LAB |
| `SurfaceReadoutLedgerV1` | ≥2 roots exact AssemblyID/generation + UTF8 surface + submitted SIC bundle, EOS typed; fail closed on ambiguity | RC4 peripheral |
| `probe eta_b`, discovery, consolidation, total age | 1.0, 8 qualified roots, 32 further qualified roots, 240 completed-root ext events; LEARN probe available through NO_PROBE_TEST, scratch OFF | RC3.1 LAB |
| `OwnerProfile` | exactly 2 compact qualifying completed-root witness profiles; bounded by actual contextual candidate cells | C04 integrated |
| `StableBindingV2` | schema_version=2, both selected consolidated P, ≥1 consolidated C/Y, immutable `(L_z,U_z,tau_ctx_q6)`; legacy V1 rejected | RC3.1 + C04 integrated |
| `root provenance` | strictly increasing nonrecycled independent `exposure_id`; explicit BEGIN/END/ABORT | C01/C02 |
| `NEGATIVE_UPDATES_ENABLED` | false all scopes | C01 first-lab supersession |

Any unspecified tuning parameter MUST be explicitly versioned with the experiment configuration, not supplied ad hoc to force correct C/E output.

## 10. Focused C04 review, precedence, open proof obligations

### 10.1 Review of the two FFR-04 blockers

**FFR04-B01** was an internal mismatch: C03's runtime required **two** witnessed predecessor sources but C03's graduation permitted **one** consolidated predecessor link. C04's stricter `P2_DURABLE`, retained descriptor and PRE/POST exact same-snapshot equivalence remove that mismatch **as a written rule**. Necessary validation `LLA-T08,T09,T10` is unexecuted.

**FFR04-B02** was root-ID-bound branch dedup that failed after TTL turnover. C04's persistent `OwnerID`, finite `OwnerProfileV1`, fail-closed `ResolveOwner`, and atomic owner allocation remove **root ID as stable identity**. The logic still deliberately fails conservatively (`UNRESOLVED_BRANCH_MATCH`) under unresolved collisions/partial witnesses. Required `LLA-T11,T12,T15` is unexecuted.

**Targeted static disposition:** both named C04 repairs are *integrated as coherent candidates*, not empirically proven. **Full final freeze depends on an independent cross-document review** of these two new integrated normative documents; previous documents alone remain nonfrozen.

### 10.2 Explicit residual boundaries

- **No automatic Assembly guarantee:** RC4 NOW supplies explicit `MAINTAIN/GROW/FORM/MERGE/SPLIT` operator definitions in Core §2.0, but still does **not** prove that real LLA dynamics produce a reciprocal consolidated triangle, that the assemblies map uniquely to lexical events, or that a generated surface is correct. These are separate empirical gates, not decisions a programmer can skip or fake.
- **No guaranteed learning success:** strict two-P evidence, 8-match discovery then 32-match consolidation, latent/64-outgoing caps and weak first-root Q may still prevent durable z; failure is reported, not patched via silent threshold adjustment.
- **No negative corrective learning** first lab; branching B can produce false predictions. No backpropagation; no evidence that local LLA alone matches mature Transformers or generalizes linguistically.
- **Unresolved SIC ambiguity** remains physically indistinguishable to Core. No repair by labels or semantic dictionary.
- **Permanent ownership is bounded governance, not semantic memory:** it must not become an evaluator outcome lookup at inference. Noise can produce unresolved branch ownership and block new allocations.
- **RC3.1 baseline neural retrieval vs RC4 generation:** `NEW_SELECTED_INTERNAL` is disabled in standalone READ_ONLY single-next tests, but enabled only inside bounded, no-learning RC4 `GENERATE_EPISODE` with required peripheral attestation and G1/G2 tests. No unbounded free-form or G3 success claim.
- **REPLAY** may be tested as a separate declared condition; no internal root can satisfy `external_count>=2` by itself.
- **Numerical reproducibility:** the first lab now fixes byte-exact SIC and fingerprint encoding in Core §3.1 and numeric time/weight policies in LLA §4.1. Implementations must reproduce the published vectors before experiment execution; identical-mode bitwise PRE/POST checks remain local to a fixed runtime/backend, not a universal cross-platform floating-point guarantee.


### 10.4 FIFR-01 numerical and execution corrections (LAB-CONTRACT-01, RC2)

The six previously blocking decisions were made at **RC2 and remain normative within these two RC4 documents**, as **new first-lab experimental contract choices**, not historical frozen facts: `k_neural/k_evidence` exact constants (§4.1 and Core §1.4), `ω_root`/Replay policy (§4.1/4.4), event-time activity for link creation (§3/5), byte-exact SIC and canonical numeric records (Core §3.1), complete candidate finite-state transitions (Core §7.4.1 with LLA §6.3), and BEGIN/ABORT H_slow checkpoint rollback (Core §10.1 and LLA §7). No programmer may substitute a different choice without a separately versioned experiment. These corrections are written directly into the two normative **review-candidate** artifacts, with **no new overlay spec**. Their formal verification and empirical success are still untested, and **no Final Freeze is claimed until user review**.

### 10.3 Historical source fingerprints

| Source | SHA-256 |
|---|---|
| Original `LLA-&-L2.txt` (`DGCA-V2-CORE-LLA-SPEC v2.0.0`) | `6535ce7a4aad54a24a2c15c0a2560e4211c11066876c11b65d2469d40d90a33d` |
| DCR unified v0.9.0 | `89dca119392a9e7598e663b8c1ea9b0d2b80fa9b3bdc349957a2a6497427e06f` |
| FFR01-C01 | `b3e23d77bc28d0f2895982a4fa3031e73251be6b925aac4d1d4edc30808cc887` |
| FFR02-C02 | `7b41c3f3c31715fdf407a7f12aaa94207efcb997db2debed633415828f725fdf` |
| FFR03-C03 | `a9d7d922c7d025a377df7d61d52ec876185ebda18d089e4f5841f37dfcf974d1` |
| FFR04-C04 | `04f3673d8d55ee88fd545283c93a1a2f3e63e9d8716474578c9e84540d0ff8f4` |

## 11. Integrated two-document acceptance checklist

The freeze reviewer MUST verify these two documents on the **same** corpus/configuration: no stale C03 single-P graduation; no root-ID-based stable owner keys; no `ContextWitness` read-only requiring OPEN root; direct witness does not require comparator; no latent creation without revalidation; first-lab negatives off; no forward Δ>1; no training Y leaked into cold rollout; no probe retained at COMPLETE; no counters/adaptation under RETRIEVE; source budgets and root-dedup preserve save/retry; result neural PredScore separated from native Assembly status.

**RC3.1 user-review closure:** the stale 8/200 parameter row is eliminated; LEARN probe continues through failed `NO_PROBE_TEST` while scratch inference remains off; physical P support compares against immutable Q6 threshold, with V2 persistent binding schema. All `LLA-T36..T41` expected tests are **not executed**.

RC4.1-specific freeze checks: source `μ_i` MUST be interpreted as directed `μ_ij` for temporal propagation, preserving legal higher-context targets; Gate C curriculum must measure rather than assume lexical readout readiness. RC4-specific freeze checks: no erroneous promotion of DERIVED to OBS_DIRECT; no self-evidence generated from internal predictions; no omitted typed parent OwnerID/generation in depth>1; live Assembly requires genuine reciprocal consolidation and bounded deterministic lifecycle; ledger never affects neural winner ranking; single selected SIC input is not OR-counted twice; EOS does not imitate HARD_BOUNDARY; novel G3 outcomes are separately labelled.

If any blocker remains, mark both `NOT FROZEN` and write exact corrections **inside these same two docs**; do not revive fragmented overlay files as simultaneous normative authorities. A clean contract review would permit only a **first-lab implementation-contract freeze**, not a claim of real learning or language generation.


**RC4 scientific qualification:** all RC4 Assembly, hierarchy and G1/G2 generation contracts are proposed mechanics, not validated behavior. A two-document design may be coherent yet fail to form reciprocal triangles, confirm readable surface bindings, preserve contexts over multiple events or learn compositional generalization. Report each failure; keep `RC4 — NOT FROZEN` pending user integrated review and empirical tests.

**Exact RC3.1 baseline SHA-256 inputs:** Core = `5e87c5a44405e6ba5804f138d835b2d443d2e5e45171cdc3fdce86ee92036727`; LLA = `9ad619ccd55f05bc9d3c9fe02365f1921bfbebe8dc383b578bcea639d790237c`. This RC4 is a proposed successor, not a mutation of those source artifacts.
