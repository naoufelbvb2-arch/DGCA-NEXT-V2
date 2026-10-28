# DGCA v2 — Dynamic Core Reconstruction: CORE Specification

**Document ID:** `DGCA-DCR-CORE-SPEC`  
**Revision:** `v1.0.0-RC4.1` — integrated contextual learning + bounded native-assembly, hierarchical memory and hybrid autoregressive surface generation (proposed)  
**Date:** 2026-10-26  
**Status:** `RC4.1 DESIGN CANDIDATE — NOT FROZEN — NOT IMPLEMENTED — NOT EMPIRICALLY VERIFIED`  
**Companion document:** `DGCA_LLA_RC4_1.md`  
**Scope:** `LANGUAGE / INDEPENDENT_EXPOSURE / CONTEXTUAL_LEARNING / BOUNDED GENERATION (G1/G2)` with a mandatory unchanged `SINGLE_NEXT_EVENT` RC3.1 regression baseline; Vision/Audio and compositional G3 are not claimed.

> **Source and precedence.** This is a self-contained proposed integration of the frozen historical `DGCA-V2-CORE-LLA-SPEC v2.0.0` (C1–C5), DCR unified v0.9.0, and targeted overlays FFR01-C01, FFR02-C02, FFR03-C03, FFR04-C04. It does **not** retroactively unfreeze or modify historical documents. RC3 modifies four RC2 experimental design choices and is NOT a stable approved version. If this RC is approved after independent integrated review, this document and its companion are to be the **only two normative implementation documents** for the first lab. The companion owns learning/evidence; this one owns state, graph anatomy, event execution, context runtime, and retrieval. A discrepancy between them is a freeze blocker, not a choice left to the programmer.

## 0. Reading conventions and exact claims

- **MUST / MUST NOT / MAY** express *proposed implementation requirements*, not observed behavior.
- **LAB DEFAULT** is a fixed value for reproducible experiments, not proof of optimality. No per-example tuning is permitted.
- **DEFERRED** means not asserted by the first-lab contract; the implementation MUST report the limitation rather than silently emulate it.
- **Core** never receives evaluator labels `A/B/C/D/E`, semantic word IDs, ground-truth next-event labels as inference inputs, semantic embeddings, or backpropagated gradients. Letters in examples are *researcher notation*.
- **Separate empirical gates:** (i) neural next-event discrimination, (ii) native learned Assembly selection, (iii) internally materialized multi-event G1/G2 rollout with externally readout surfaces, and (iv) separately held-out compositional G3. No gate is inferred from another; G3 has no performance guarantee in RC4.
- **Research baseline:** RC3 introduces four explicit experimental architectural choices (retained in RC3.1), not verified successes: permanent physical context conjunction, contextual competition for next-step temporal drive, separated probe/consolidation windows, and bounded capacity-aware admission. **RC2 must be retained as an ablation**, not silently overwritten in a repository.
- **Review result on C04:** targeted text-level checks support correcting predecessor consolidation from one to **two selected P links**, and replacing root-dependent branch ownership with persistent, physically validated `OwnerID`. The corrected tests are incorporated below. This is a **focused specification review**, not an executed test or final freeze authorization.

## 1. Invariant network anatomy

### 1.1 Network, addressing, regions

- Total logical laboratory capacity `N=12,288`; regions `VISION`, `AUDIO`, `LANGUAGE`, `N_r=4096` each.
- Each region: `32 × 16 = 512` microcolumns, `8` cells/microcolumn.
- Cell address: `(region, mc_row, mc_col, slot)`; identity follows deterministically from this tuple. No arbitrary semantic labels.
- Microcolumn normalization uses the cell's own column. Local spatial vicinity: its own microcolumn plus orthogonally adjacent microcolumns, bounded at borders.
- Region constants (inherited; initial calibration):

| Region | `delta_A` | `gamma_A` | `beta` | `rho_target` |
|---|---:|---:|---:|---:|
| VISION | 0.50 | 0.90 | 1.00 | 0.020 |
| AUDIO | 0.35 | 0.85 | 1.00 | 0.025 |
| LANGUAGE | 0.20 | 0.80 | 0.80 | 0.030 |

- The first trial MUST NOT claim verified Audio/Vision encoders, asynchronous multi-modal timing, unrestricted stream continuity, or scale-up performance.

### 1.2 Dumb Cell contract

A cell carries only physical identity/administration, structural connectivity, and local numerical state. It has **no** word, context, concept, output-label, or task-role field. Legal states are derived: `UNCOMMITTED` iff `committed=false,A=0`; `DORMANT` iff `committed=true,A<theta_active`; `ACTIVE` iff `committed=true,A>=theta_active`.

| Category | Fields/constraints |
|---|---|
| Identity | `id, region, microcolumn, committed, committed_event` |
| Activity | `A, A_prev, A_hist[H_context]`, `last_referenced_event` |
| Homeostasis | `r_bar, g∈[0.70,1.40]` |
| Latent anatomy | `latent_neighborhood[24]`, `wiring_log` |
| Budgets | Outgoing `B_i=64` (RC3 experimental default; RC2 comparator `32`), cross-outgoing `B_i^x=12`, outgoing episodic `E_cap=4`, Assembly memberships `M_max=12` |
| Synapses | Stored separately under directed `(source,target,scope)`, **no self-links** |

`Cell` performs receive/integrate/activate/emit/adapt operations only through neighborhood-constrained laws. Eligibility/provenance, candidate ownership, and training comparisons are **not permanent semantic Cell fields**.

### 1.3 Latent neighborhood, eligibility, inverse index

Exactly **24** latent slots: `6 co-active intra`, `6 local`, `6 co-active inter` (3 per other region), `6 topographic` (3 per other region). Ordinary admissions use the historical highest coactive/intra, fixed local, inter coactive and deterministic topographic policies.

A directed synapse `i→j` is structurally eligible if **either** endpoint lists the other:

\[
D_{ij}=\mathbf1[j\in N(i)\lor i\in N(j)].
\]

Maintain `reverse_latent_index` transactionally. Fixed `local/topographic` slots are not recycled; coactive slots can recycle only when no live/protected bidirectional synapse or candidate pin needs them, with the original confirmation window. Recycling must maintain both forward and reverse representations and `wiring_log`. **Priority:** legal live-link protection > committed contextual pin > recycling of unprotected latent slot > ordinary pending link proposal. Candidate-pinned slots cannot be evicted (`RECYCLE_BLOCKED_CANDIDATE`).

**Capacity-aware rule (RC3):** for a new z, the already pinned `z`-side latent slot makes `D_iz=1` even when source `i` has no free latent slot; it does **not** bypass the source outgoing budget. The only mandatory outbound headroom checks are on actual unique directed proposed keys, including overlapping P/C roles. Do not count each role twice if one live identical directed key already exists.

**Contextual exception:** a context candidate `z` may use up to six `co-active intra` slots in strict **two predecessor (`P`), two current (`C`), two outcome (`Y`) roles**, chosen and reserved with the algorithm in §7. This is a change to the *selection policy*, **not** to the total 24 slots. Repeated physical cell IDs across role sets consume one physical slot; distinct intended synapse keys still consume distinct source-outbound claims. Cross-region roles use compatible cross slots/budgets; unsupported combinations are rejected, never force-fitted.

### 1.4 Directed synapse, legal scopes, and quality

- Key is exactly `(source_id,target_id,scope)`, `source != target`; opposite directions are independent.
- Scopes for this first lab: `LOCAL` same-region same-event `Δ=0`; `CROSS_TERRITORY` distinct-region same-event `Δ=0`; `ASSOCIATIVE` directed **next-event** transition `Δ=1` (same or cross region). Historical `H=5` is now a *context eligibility* horizon, not license for a `Δ=2…5` forward jump. Historical asynchronous cross-window `H_x=2` is **DEFERRED**.
- Link state is `CANDIDATE / EPISODIC_INDEXED / CONSOLIDATED`, with `S∈[0,1]`, evidence ledgers `E_ext,E_int`, total `E<=E_max=10`, distinct accepted external roots, time metadata and source/capacity bookkeeping. Detailed lawful creation, evidence, deadlines and consolidation live in the companion LLA document.
- Qualitative propagation is computed from real, live link strength/evidence (never from candidate metadata or outcome labels):

\[
Q_{ij}^{s}=d_{ij}^{s}S_{ij}^{s}(E_{ij}^{s}/E_{max}),\quad
 d_{ij}^{s}=\begin{cases}0.75&E_{int}>E_{ext}\\1&\text{otherwise.}\end{cases}
\]

`Q^T=Q^ASSOCIATIVE`; synchronous influence is supplied only by legal `LOCAL`/`CROSS_TERRITORY` links, counted once per directed key. **FIFR-B01 numerical closure:** neural propagation always uses `k_neural(LOCAL,0)=k_neural(CROSS_TERRITORY,0)=k_neural(ASSOCIATIVE,1)=1.0`; these factors multiply `A_source × Q` exactly once. **Evidence** has a *distinct* `k_evidence(LOCAL,0)=k_evidence(CROSS_TERRITORY,0)=1.0`, `k_evidence(ASSOCIATIVE,1)=0.7408182206817179` (LAB CONSTANT: rounded binary64 representation of `exp(-0.30)`). Illegal `(scope,Δ)` is rejected, not clamped. The threshold multiplier `1.15` for `theta_emit` is unrelated to either time factor. LLA §4.1 defines the same constants and uses `k_evidence` **only in q**, never in neural `Q` or `P_T/P_S/PredScore`.

## 2. Assembly and Context Attractor: distinct roles

An **Assembly** is a structural set of `3–16` committed cells supported by *mutually* consolidated `LOCAL/CROSS_TERRITORY` links. Directed `ASSOCIATIVE` edges do not create Assembly structural reciprocity. One specialized contextual cell `z` is **not** automatically an Assembly or an Attractor.

Historical assembly operations `MAINTAIN → GROW → FORM → MERGE/SPLIT` must continue to respect structural graph/role/size constraints: mutual support

\[
R_{ij}^{B}=\max\big(\min(Q_{ij}^{LOCAL},Q_{ji}^{LOCAL}),\;\omega_X\min(Q_{ij}^{CROSS},Q_{ji}^{CROSS})\big),\quad\omega_X=0.85.
\]

Inherited merge uses `Jaccard>=theta_merge=0.70`, between-Assembly strength `>=theta_ob=0.40`, cooldown `T_c=200`; split uses `theta_weak=0.15`, `theta_sep=0.10`, `N_min=6`, as applicable. **RC4 precedence:** the executable first-lab operators are defined in §2.0; the historical incomplete-operator exception applies only to unsupported multi-modal or out-of-scope structural operations. A legal Assembly fixture remains a readout unit test only and is never empirical evidence of native emergence.

### 2.0 RC4 executable Assembly operators (LANGUAGE first lab)

These definitions **supersede the RC3.1 `UNSPECIFIED_OPERATOR` exception for the exact RC4 cases described here**; they are design choices, not empirically validated Assembly formation. An Assembly is an identity-bearing **structural** object in W (not a Cell semantic role). It has `AssemblyID`, `region`, sorted unique `member_cell_ids`, `structural_generation`, `birth_close_serial`, `last_mutation_close_serial`, `last_merge_split_close_serial`, `status=LIVE|ARCHIVED`, and bounded idempotent membership/back-index bookkeeping. `AssemblyID` is a never-reused monotonically allocated integer in the region, assigned only on atomic END publication. No Assembly may contain a contextual candidate that has not COMPLETED and passed its legal binding checks. In first lab, all members must be committed LANGUAGE cells; mutual LOCAL links construct it. CROSS mutual edges are numerically defined but deferred for formation. For pair i != j, `R^B` is given above **from live CONSOLIDATED links only**; absent/illegal/nonconsolidated directed keys yield `R^B=0`.

\[
e_{ij}^{B}=\mathbf1[R_{ij}^{B}\ge\theta_A=0.10],\qquad
N_{rec}(x)=\{k\ne x:e_{xk}^{B}=1\},
\]
\[
d(x,A)=\sum_{j\in A\setminus\{x\}} e_{xj}^{B},\quad
D(x,A)=\begin{cases}d(x,A)/|A\setminus\{x\}|&|A\setminus\{x\}|>0\\0&\text{otherwise}\end{cases},
\]
\[
Spec(x,A)=\begin{cases}
\dfrac{\sum_{j\in A\setminus\{x\}}R_{xj}^{B}}{\sum_{k\in N_{rec}(x)}R_{xk}^{B}} &\sum_{k\in N_{rec}(x)}R_{xk}^{B}>0\\0&\text{otherwise}
\end{cases}.
\]

`Spec` is evaluated on committed, live reciprocal neighbors across the LANGUAGE region, not solely candidates near A; a member may belong to up to `M_max=12` assemblies. `K_min=3,K_max=16,d_min=2,rho_core=.70,rho_G=.50,sigma_G=.30,rho_keep=.35,sigma_keep=.20`. Define `CoreCoverage(A,t)=|{j in A: committed_before_event(j,t), A_j^+(t)>=theta_emit}|/|A|` for a live Assembly; otherwise zero. Define `M_A^fresh` by §2.1 (a distinct value: *average fresh activation*, not coverage). Both use actual event-time frozen R; no later post-close-created Assembly can claim a previously witnessed event as evidence.

**One deterministic END update, on frozen post-synapse evidence W***: execute the following exactly once per completed EXTERNAL LEARN root, in the listed order, with a shadow live set, sorted IDs and bounded local graph enumeration; a successful END may publish multiple changes but is atomic. Use **each** genuine event-time observation snapshot in the completed root, processed in ascending event_order, for FORM, never replayed/predicted-only/BOOTSTRAPPED/frontier-only cells; require `OBS_ELIGIBLE` or a COMPLETE externally derived witness (§6.1). Per-event frozen `A^+`, `F_step` and SIC input must be available from the OPEN journal. FORM uses the post-evidence graph W* for edge eligibility but no newly formed structure may claim it existed during those prior events. The phrase `MAINTAIN→GROW→FORM→MERGE/SPLIT` specifies one pass per stage; there is no iterate-to-convergence loop. A rejected proposal never allocates an ID or modifies W.

1. `MAINTAIN`: visit AssemblyID ascending; repeatedly remove the **lowest physical cell_id** among members failing `d>=2,D>=rho_keep,Spec>=sigma_keep` on the current shadow set until no violation remains, or size<3; archive a subminimum Assembly. Never remove its underlying consolidated synapses. Each membership change increments structural_generation, invalidating prior ledger readout attestation until re-confirmed.
2. `GROW`: each still-live A in ascending AssemblyID, while |A|<16, enumerate distinct committed neighborhood nodes of its reciprocal members, not a whole-region scan; rank by `(-sum_{j in A}R_xj^B,cell_id)`. Inspect each once in that order; add if **on prospective A∪{x}** `d(x,A)>=2,D(x,A)>=.50,Spec(x,A)>=.30`, no invalidated existing member keep guards, and membership cap allows it. Do not add from a future event's observation; other members remain physically valid. Increment structural_generation on each addition.
3. `FORM`: for each event of the completed root, in chronological order, let `U_t` be ascending committed cells with externally grounded qualified fresh participation in **that** event, `A^+>=theta_emit`, not already covered by any *live* A with `CoreCoverage(A,t)>=.70`, and under M_max. Build the finite undirected eligible reciprocal graph on `U_t`. Enumerate triangles `(i<j<k)` in ascending lexicographic order via adjacency intersections (not `choose(N,3)` scans), requiring each vertex `d(vertex,{i,j,k})=2`, `D>=.70`, `Spec>=.30`, all 3 source cells otherwise legally eligible. The first valid triangle becomes a new size-3 Assembly, then continue over *remaining not-yet-assigned FORM vertices* with disjoint triangle seeds (overlap may arise from GROW in future closes). If no triangle, return `NO_RECIPROCAL_TRIANGLE`; this is a **valid laboratory failure**, not permission to synthesize reciprocal links or create an Assembly from a single contextual z. At most `K_FORM_PER_END=12` new assemblies **across all root events combined**; defer excess in deterministic event-order then seed-order without retroactive witness claims. This bounds search and publication.
4. `MERGE`: take live pairs `(A.id,B.id)` ascending, after GROW/FORM, **skipping any ID changed by MERGE/SPLIT within the last `T_c=200` completed external events**; with Jaccard of member sets ≥`theta_merge=.70`, `between_strength>=theta_ob=.40` where `between_strength = mean{R_ij^B:i∈A\B,j∈B\A}` (empty exclusive side ⇒0); require |union|≤16 and every proposed union member meets the MAINTAIN guards and membership limits. Merge into lower ID, archive higher ID, advance survivor generation; recompute pair list once from new shadow state and process each initial pair at most once. No old ID may remain a live readout key.
5. `SPLIT`: for each surviving live A size≥`N_min=6` after MERGE, skipping any ID edited by MERGE/SPLIT in the last `T_c=200` completed external events, enumerate all bipartitions `(L,R)` with both sides size≥3, with A's smallest member in L to avoid duplicates. Every member in each side must satisfy MAINTAIN guards and membership limits within that side; require all cross-pair supports `R_ij^B<=theta_weak=.15` and mean cross-support `<theta_sep=.10`. Choose `(mean_cross_support,sorted_L,sorted_R)` ascending; keep original ID for L, assign one new ID to R, increment L's generation; stop at **one split per original Assembly per END**. If no valid partition, retain. Exhaustive enumeration is bounded by K_max=16. Pre-commit validate every changed membership and reverse index; atomic rollback on any failure.

After these operations, a structurally modified Assembly ID/generation is **not** eligible for retroactive event-to-surface confirmation. Its next independent, externally witnessed event can begin a new attestation. Any `MERGE/SPLIT/ARCHIVE` invalidates an old matching ledger binding; loss of a printable surface must be reported, never resolved by fetching a historical archived Assembly ID. FORM depends on real reciprocal learning, which is a measurable unsolved experimental feasibility gate (§13), not a promised outcome.


### 2.1 Fresh-only Attractor update

Only a structurally qualified Assembly can host a `CONTEXT_ATTRACTOR`. On a real external event, compute a **separate scratch fresh pass** from frozen W/H, with `A_prev=0`, `P_T=0`, `sigma=0`, `bootstrap=0`; retain only current external SIC and its one synchronized LOCAL/CROSS propagation:

\[
A^{fresh,(1)}_j=\operatorname{clip}(\gamma_r g_j\mathcal N_j(X),0,1),
\quad E^{fresh,(1)}=\{i:A^{fresh,(1)}_i\ge\theta_{emit}\},
\]
\[
fresh_j=\operatorname{clip}(\gamma_r g_j\mathcal N_j(\operatorname{OR}(X,P_S^{fresh})),0,1).
\]

No external input ⇒ all `fresh_j=0`. Internal REPLAY or RETRIEVE without genuine new input never refreshes an Attractor. For a qualified Assembly `G`:

\[
M_G^{fresh}=|G|^{-1}\sum_{j\in G}fresh_j,\quad
C_G(t)=\begin{cases}0&\mathrm{collapse}\\\max(\rho_s C_G(t-1),M_G^{fresh}(t))&\text{otherwise,}\end{cases}
\]

with `rho_s=0.90`, `T_max=30`, admission from fresh `M_G>=theta_in=0.40` plus cohesion `theta_ctx_form=0.50`, and collapse on `HARD_BOUNDARY`, `age_G>=30`, or `err_G>Theta_err=1.50`. An ACTIVE Attractor ages once per processed event, including internal steps; fresh input **does not reset accumulated error**.

For externally complete comparable outcomes, obtain from frozen prior Attractor member emitters the one-step predictions `p_Gj=NoisyOR(A_i(prev)Q_ij^ASSOCIATIVE)` for `i∈G∩F_step(prev)`, eligible `p_Gj>=theta_pred=0.25`. On valid directly witnessed comparable `j`, use

\[
miss_G=\frac{\sum_{j\in J_G^{valid}}p_{Gj}(1-o_j)}{|J_G^{valid}|},\quad
err_G'=\min(\Theta_{err}+1,err_G+miss_G).
\]

When there is no valid comparable target, error remains unchanged. Newly activating attractors initialize `err=0, age=0`; observe collapse precedence boundary > age > error. Newly computed `C_G(t)` contributes **only to the next event's** `sigma`, never recursively to current-event `fresh` or activity. Sustained contextual state is an optional aid, not persistent knowledge storage.

## 3. SIC, canonical observation and event input

`Event(event_id,modality=LANGUAGE,features,raw_surface,root_type,boundary,salience)` is extended by canonical observed feature bytes, `exposure_id`, contiguous `event_order`, `observation_scope`, and explicit origin. For the first lab `raw_surface` is audit-only inside Core and is available only to the peripheral §9.4 I/O envelope; Core processes deterministic sparse orthographic features (characters/boundaries/local fragments) and a mechanical projection, **no dense semantic vectors**.

Each feature is projected with **four deterministic salts**:

\[
\Pi(f,LANGUAGE)=\{hash_k(f,LANGUAGE,s_k):k=1,2,3,4\},\quad
X_j=1-\prod_{f:j\in\Pi(f)}\left(1-\operatorname{clip}(sal\cdot u_f,0,1)\right).
\]

Canonicalize exactly as §3.1: normalize NFC, combine duplicate feature bytes, sort unique features by unsigned UTF-8 bytes, and use the explicit SHA-256 SIC-V1 projection and support rules. Reject invalid encoding, NaN/Inf, unsupported mode/region or malformed event order; do not use interpreter-randomized hash or change salts across save/load. Collision of external feature patterns in the **neural footprint** remains unresolved, not 'fixed' by evaluating hidden word labels. Witness attribution/training evidence belongs to companion LLA document.

### 3.1 FIFR-B04 — SIC-V1 byte-exact input and projection (LAB CONTRACT 01)

**This is a new, fixed first-laboratory decision, not an inherited historical salt or tokenizer.** First-lab callers supply *mechanical* `(feature_text, support)` values; deriving characters/boundaries/n-grams from raw surface text is **OUT OF SCOPE**. `raw_surface` is audit-only; the runtime MUST NOT infer semantic labels or silently tokenize it. Each `feature_text` is a Unicode scalar string normalized to **NFC**, encoded with strict UTF-8; reject lone surrogates and byte strings that are not valid UTF-8. Zero-length or >4096-byte normalized features are invalid. Equal NFC byte strings are one feature identity, including canonically equivalent strings.

**Input numbers:** `support` and `salience` MUST be finite decimal strings matching `0|1|0.[0-9]{1,6}|1.0{1,6}` (no exponent, plus/minus sign, NaN, Inf, or negative zero); normalize to unsigned integer millionths `u∈[0,1_000_000]` by right-padding the fractional part with zeroes. Default salience is exactly `1.000000`. For repeated *identical* normalized feature bytes, combine supports by exact decimal Noisy-OR `u*=1−∏(1−u_f)` then round **half-even** once to millionths. Sort unique normalized features by **raw unsigned UTF-8 byte order**. Multiply the merged support by salience using exact decimal arithmetic and half-even quantize to millionths **once** before projection. Zero-support features do not contribute. If the same feature maps to the same cell through multiple salts, count that feature once per cell. Across *different* features mapped to the same cell, aggregate their quantized supports by exact decimal Noisy-OR with one final half-even quantization to millionths. Thus external `X_j` is exactly `support_u32 / 1_000_000` converted to IEEE-754 binary64; its millionth integer is the authoritative direct witness and fingerprint value.

**Region bytes** `VISION=0x00`, `AUDIO=0x01`, `LANGUAGE=0x02`. For salt index `k=0,1,2,3`, 16-byte salts (literal lowercase hex) are:

```
s0=000102030405060708090a0b0c0d0e0f
s1=101112131415161718191a1b1c1d1e1f
s2=202122232425262728292a2b2c2d2e2f
s3=303132333435363738393a3b3c3d3e3f
```

Define `payload = ASCII("DGCA-SIC-V1") || 0x00 || region_u8 || salt_index_u8 || salt_16 || feature_length_u32_BE || normalized_feature_UTF8`. `SHA256(payload)` is computed byte-for-byte; interpret its **first 8 digest bytes as unsigned big-endian uint64**, reduce modulo `4096` to get the region-local cell index for that salt. Global cell ID is `4096*region_u8 + local_index`. Canonical inverse: `microcolumn_index=local_index//8`, `mc_row=microcolumn_index//16`, `mc_col=microcolumn_index%16`, `slot=local_index%8`. Do not rely on Python's or a platform's process-randomized hash. Preserve salt order k=0..3 for the four lookup results; use sorted **distinct** IDs when accumulating supports.

**Reference vectors (LANGUAGE; region-local IDs in salt order):**

| NFC feature | four indices | sorted distinct indices |
|---|---|---|
| `a` | `[1153,3989,414,3603]` | `[414,1153,3603,3989]` |
| `ab` | `[3449,2321,502,2081]` | `[502,2081,2321,3449]` |
| `é` (also decomposed `e` + combining acute) | `[1138,1220,3626,1003]` | `[1003,1138,1220,3626]` |
| `f617` | `[414,8,1843,2734]` | `[8,414,1843,2734]` |

With two distinct features `a:0.500000`, `f617:0.250000`, and salience `1.000000`, shared receiver `global_id=8192+414=8606` MUST have `X_fixed=625000`, while `a`-only receivers have `500000` and `f617`-only receivers `250000`. With a *repeated* `a` input `0.500000` plus `0.250000`, its four receivers also have `X_fixed=625000` (one merged feature, not two projection votes).

**Physical fingerprint serialization (FP-ROLE-V1):** `ASCII("DGCA-ROLE-V1") || 0x00 || role_u8 || item_count_u32_BE || items`, where `role: P=0,C=1,Y=2`, each item is `global_cell_id_u32_BE || direct_support_millionths_u32_BE`, with unique IDs strictly sorted ascending and no zero supports. Digest is SHA-256 of these exact bytes; no event/exposure ID enters the stable physical digest. For role=P and feature `a:0.500000`, the ascending global IDs `[8606,9345,11795,12181]` with `500000` each MUST give digest `6cce77c3fc8da8bed4973ec695b267c3430807001563606989f40a3fe383b337`. Stable multi-event owner profiles encode their role subrecords in fixed P,C,Y order, then length-prefix each (u32 BE) and hash the concatenation with prefix `ASCII("DGCA-OWNER-PROFILE-V1") || 0x00`; stored root numbers remain audit metadata, excluded from identity/equality.

**Numeric and sort contract:** neuron `A,S,E,Q,g,theta` computations use finite IEEE-754 **binary64**, round-to-nearest/ties-to-even, single-threaded stable operation order. No FMA contraction or non-specified parallel reduction; for Noisy-OR fold contributors in `(source_cell_id,scope_order,link_key)` ascending order (for feature-only OR use feature bytes ascending). All comparisons and ties used by learning/governance are on integer supports or on finite binary64 values quantized by taking the **exact binary64 rational value × 1,000,000 and rounding to nearest integer, ties-to-even** (do not round a shortest printed decimal representation first); tied quantized values break by stable physical IDs and predefined scope order `LOCAL<CROSS_TERRITORY<ASSOCIATIVE`. Persist binary64 values as canonical **8-byte big-endian IEEE-754** (normalize `−0.0` to `+0.0`, reject NaN/Inf) and all integers in fixed-width unsigned/signed big-endian formats; each persisted record uses `record_tag_u8 || schema_version_u8 || payload_length_u32_BE || payload`, and fields follow the order defined by its schema, never map iteration. Schemas of W/R/H and journal records must declare their fixed field order and version in code/test artifacts; **cross-platform bit-identical dynamic activity is not asserted**, but same-backend PRE/POST checks MUST be bit-identical and cross-platform physical fingerprints MUST match these vectors. SAVE/LOAD must preserve both values and record-ordering invariants.

## 4. State partition and modes

The **complete** machine state is

\[
\mathcal S_t=(W_t,R_t,H_t^{slow}).
\]

| Partition | Contents | Persistence/ownership |
|---|---|---|
| `W` | committed cell & latent topology, reverse indices, synapses/evidence, Assemblies, candidate phases, pinned reservations, owner registries, confirmed-root journals, bounded contrast summaries, accepted external-profile governance | Durable/transactional; `RETRIEVE` never mutates |
| `R` | `A,A_prev,A_hist`, pass frontiers, `F_step`, context/Attractor activity, witness and contribution lanes, short eligibility traces, event-local staging | Mutable while running; reset cold at boundaries; checkpoint for restart |
| `H_slow` | `g,r_bar`, adaptive thresholds and region firing EMA | Persists across independent roots; frozen in REPLAY/RETRIEVE |

\[
R_{t+1}=F_{W_t,H_t^{slow}}(R_t,X_{t+1},m_{t+1}),\quad
W_{t+1}=\mathcal U(W_t,validated\ evidence, m),\quad
H_{t+1}^{slow}=\mathcal G(H_t^{slow},R_{t+1},m).
\]

These collective equations are induced by local Cell/Synapse operations and a bounded, **nonsemantic** transaction/governance layer; they are not a global reasoning network or Transformer.

| Mode | Activity R | Structural/evidence W | H_slow |
|---|---|---|---|
| `LEARN` | advances | admissible changes with real validated external evidence or legal nonsemantic admissions | adapts |
| `REPLAY` | advances | bounded internal evidence only under companion policy, **never external roots** | frozen |
| `RETRIEVE` | scratch/activity only | strictly unchanged | strictly unchanged |
| `GENERATE` | isolated read-only R session, bounded INTERNAL_SELECTED steps | strictly unchanged | strictly unchanged |

Mode and input-origin are independent fields. `GENERATE` is a read-only session mode, not a LEARN submode. A real input in RETRIEVE or prompt ingestion is a **runtime observation**, not an external training root. `GENERATE` holds one scratch R state for the entire rollout, while never mutating durable W, H_slow, assembly version, evidence, owner counter, peripheral ledger or caller R. `READ_ONLY_EPISODE` must not be implemented as `BEGIN_EXPOSURE(mode=RETRIEVE)`. `R` also holds each event's ephemeral contextual `G_ctx` and frozen next-step masking map `μ`; `W` retains only finite physically bound anchor source sets and stable owners, not predicted outcome labels.

## 5. Normal two-pass neural dynamics

Define `NoisyOR(z1,...,zk)=1−∏(1−z_i)` over valid `[0,1]` supports. All calculations use frozen pre-event W/H, with normal same-event two passes:

**Pass 1 (external and temporal from previous step):** The source-routing candidate mask `μ_i` is determined only after the **preceding event** has closed its two-pass neural computation; it is held frozen. The **per directed target** mask `μ_ij` is defined in §5.2. With no qualified contextual owner, every `μ_i=μ_ij=0` and the formula reduces exactly to RC2. This distinction is necessary to preserve higher-depth P→context links while attenuating generic next-event predictions.

\[
P_j^T(t)=1-\prod_{(i,j,ASSOC),i\in F^{step}_{t-1}}(1-[1-\mu_{ij}(t-1)]A_i(t-1)Q_{ij}^{ASSOC}),
\quad \sigma_j(t)=\rho_s\max_{G\ni j} C_G(t-1),
\]
\[
\hat D_j^{(1)}=NoisyOR(X_j,P_j^T,\sigma_j),\quad
D_j^{(1)}=\frac{\hat D_j^{(1)}}{1+\beta_r\overline{\hat D}^{(1)}_{col(j)}},
\]
\[
A_j^{(1)}=clip\big((1-\delta_r)A_j(t-1)+\gamma_r g_jD_j^{(1)},0,1\big).
\]

Freeze the pass-1 emission frontier `E_t^(1)={i committed: A_i^(1)>=theta_emit^(r)}` for **same-event** `LOCAL/CROSS` drive; this does **not** create a separate timeline event.

**Pass 2 (same-event completion and optional candidate-only probe):**

\[
P_j^S=1-\prod_{i\in E_t^{(1)},\ (i,j)\in LOCAL\cup CROSS}(1-A_i^{(1)}Q_{ij}^{S}),
\]
\[
\hat D_j^{(2)}=NoisyOR(X_j,P_j^T,P_j^S,\sigma_j),\quad
D_j^{(2)}=\frac{\hat D_j^{(2)}}{1+\beta_r\overline{\hat D}^{(2)}_{col(j)}},
\]
\[
A_j^{+}=clip\big((1-\delta_r)A_j(t-1)+\gamma_r g_jD_j^{(2)},0,1\big).
\]

The candidate-only permitted probe, when applicable in LEARN and **never** in RETRIEVE, changes only the candidate's raw second-pass drive as specified in §7.5 **before** pass-2 normalization. For a contextual z, first apply the permanent prior/current gate to raw pass-1 and pass-2 drives and to its residual output as in §5.1; probe amplification is admitted only inside that already-matching gate. Compute microcolumn means from these gated raw drives, never from ghost off-context z contributions. No ordinary cell receives a conjunction. **A physically owned contextual cell z, and only z, is subject to the permanent graph-local gate and source-routing law in §5.1–5.2**, even after graduation. The special operator uses already legal physical P/C keys and current/prior directly observed SIC supports—not hidden text labels, oracle outcomes or candidate-only probes. Learning frontier `L_t={j committed:A_j^+>=theta_active^r}` and cross-binding frontier `L_t^x={j∈L_t:A_j^+>=theta_bind^r}` are computed **after** pass 2. Slow adaptation uses inherited `r_bar/g` and adaptive regional threshold laws **only in LEARN**:

\[
\bar r_j\leftarrow(1-\beta_I)\bar r_j+\beta_I\mathbf1[A_j^+\ge\theta_{active}],\quad
 g_j\leftarrow clip(g_j+\eta_I(\rho_{cell}-\bar r_j),0.7,1.4),
\]
\[
\bar\rho_r\leftarrow (1-\beta_H)\bar\rho_r+\beta_H\rho_r(t),\quad
\theta_{active}^r\leftarrow clip\left(\theta_{active}^r+\eta_H\mathbf1[|\bar\rho_r-\rho_{target}^r|>\epsilon_{dead}]\operatorname{sign}(\bar\rho_r-\rho_{target}^r),\theta_{min},\theta_{max}\right).
\]

`theta_emit=1.15*theta_active`, `theta_bind=1.2*theta_active`. Do not update `H_slow` in read-only scratch FULL/CONTROL nor re-evaluate prior event scores using newly adapted thresholds.

### 5.1 RC3 — Permanent physical conjunction for contextual cells

**Scope and authority:** this is a *new experimental modification of F_W*, **not** an inference-time oracle and **not** a semantic Cell field. Ordinary cells retain the exact RC2 Noisy-OR laws. A cell becomes contextual only through a candidate structural descriptor, then a legal `StableBindingV2`; the same physical operator handles both stages. An expired, stale or released contextual cell MUST NOT spontaneously revert to an ungated generic temporal emitter. Stale bindings fail closed.

For a candidate, use its pinned 2-P/2-C physical role keys and **immutable admission-calibrated** `tau_ctx_q6(z)`; for a completed owner use **only** the consolidated physical keys and identical `tau_ctx_q6` retained in `StableBindingV2`. The candidate may be admitted only if the real root-comparison evidence in §7.3 establishes the physical predecessor-pair separation. Define `T_z(t-1)=min(o_{p0}(t-1),o_{p1}(t-1))` from **typed physical runtime supports** defined in §6.1: ordinary external SIC, read-only SIC, selected-internal SIC, or a COMPLETE no-probe context-derived P source. During training-calibration, only actual external-root witnesses (direct or causally derived COMPLETE sources) count; never a free prediction. Define `Q6(x)=roundTiesEven(1,000,000 × exactBinary64(x))`, consistent with §3.1. At candidate admission, from the two confirmed owned and all confirmed rival external predecessor witnesses used by the discriminator, record:

\[
L_z=\min_{r\in owned}Q6(T_z(r)),\quad U_z=\max_{r\in rival}Q6(T_z(r)),\quad m_P^{q6}=50,000.
\]
\[
L_z-U_z\ge 50,000,\quad tau_{ctx,q6}(z)=U_z+50,000\le L_z.
\]

`L_z`, `U_z` and `tau_ctx_q6` are **finite fixed integer physical support summaries**, computed once at accepted new candidate admission, written atomically into its temporary descriptor and copied unchanged into the final `StableBindingV2`. No subsequent root, phase, read-only test or observed Y may recalibrate these values. Missing calibration or impossible range ⇒ `INVALID_CONTEXT_THRESHOLD`, refuse admission / fail closed; no implicit default (`>0` is forbidden). At runtime, using only typed legally witnessed P support (§6.1) and the stored scalar `tau_ctx_q6`:

\[
G_z^{ctx}(t)=\mathbf1[\text{valid episode / no boundary}]
\mathbf1[Q6(T_z(t-1))\ge tau_{ctx,q6}(z)]
\mathbf1[\exists c\in C_z^{valid}:o_c(t)>0]
\mathbf1[\text{all mandatory physical binding keys legal}].
\]

The `P` witness support is from event `t−1`, never from residual, a free prediction, an evaluator's word ID, stored old exposure roots or a fresh rival comparison; C is from the physically SIC-encoded current input at event `t` (genuine EXTERNAL in LEARN, real READ_ONLY prompt or previously selected INTERNAL event in GENERATE). `C_z^{valid}` is the selected reserved set for an unfinished candidate and the consolidated retained C keys for COMPLETE. The completed binding requires both P and ≥1 C key consolidated; Y is *not* read as a gate input. This is an explicit, physically calibrated per-owner **admission constant**, superseding the old `>0` predecessor runtime condition and the generic ban on *undocumented* per-context thresholds in §12; it is not a hidden adaptive threshold. The calibration guarantees rejection of the **confirmed training rivals**, not unseen rival patterns. A newly observed ambiguous pattern remains an empirical failure/diagnostic, never permission to use evaluator labels or alter the threshold during RETRIEVE. Feature collisions cannot be disambiguated by semantic labels. The gate authorizes support, but **adds zero numerical neural drive**.

For any pass `k∈{1,2}` on a contextual cell, its ungated raw Noisy-OR output `hat_D_{z,base}^{(k)}` is changed to

\[
\hat D_z^{(k)}=G_z^{ctx}(t)\hat D_{z,base}^{(k)},\qquad
A_z^{(k)}=G_z^{ctx}(t)\,\operatorname{clip}((1-\delta_r)A_z(t-1)+\gamma_r g_z D_z^{(k)},0,1).
\]

Compute the microcolumn divisor **after** gating all contextual raw drives in that pass. `A_z^+` and the final step frontier are also gated: if `G=0`, z is inactive, cannot emit, and cannot offer its candidate probe as evidence. Direct SIC reception incidentally mapped to z is retained in observation provenance but **does not bypass this physical context restriction**; this is a declared first-lab capacity tradeoff. If `G=1`, the normal learned synaptic weights, evidence Q, homeostasis and Noisy-OR still determine its magnitude. Thus correct context **does not guarantee** `A_z>=theta_emit`; a missing P or C **does guarantee** no contextual z activity, even if C→z alone is strong. Probe is an *additional*, LEARN-only raw drive (§7.5), never a replacement for this permanent operator.

Use the same operator for candidate preflight and the post-retirement binding; `CONTEXT_GATE_BYPASS`, `MISSING_CONTEXT_SOURCE`, `STALE_CONTEXT_BINDING` are explicit diagnostics. It is forbidden to use the observed next event Y, a `ComparisonBranchKey`, saved training exposure ID or the evaluator's correct-label footprint to compute `G`.

### 5.2 RC3 — Physically scoped contextual priority at the **temporal source**

The hard no-negative-updates policy remains. A bare source B may have correct old generic B→C links. A matching completed contextual z must be able to prioritize its z→Y routes **without erasing B→C**. The following routing is applied *within* Core's `P_T`, **before** Noisy-OR and normalization, and therefore affects `PredScore`, FULL/CONTROL and all real neural activations consistently.

At the end of current event `t`, find `S_t={z: StableBinding ACTIVE, owner COMPLETE, G_z^{ctx}(t)=1, A_z^+(t)>=theta_emit, z∈F_step(t), at least one legal consolidated z→Y link}`. All tests use only W and legal current/prior typed SIC or derived contextual supports (§6.1), never a future outcome, surface text or comparator labels. If exactly **one** z qualifies, take it as the local contextual route; if zero, use the unchanged generic route. If two or more independent completed contextual owners qualify for the **same observed physical current anchor**, report `AMBIGUOUS_CONTEXT_OWNER` and use unchanged generic routing for that anchor (no nondeterministic winner, no label-guided choice). Different physically disjoint anchors are handled independently; a source appearing in more than one anchor is ambiguous and receives no suppression.

For the unique qualified z, its persisted `AnchorSourceSet` contains **all** directly observed current SIC receiver IDs of its two owned qualifying examples, unioned and sorted; at admission require the union cardinality ≤`ANCHOR_SOURCE_MAX=64`, otherwise `ANCHOR_CONTEXT_TOO_WIDE`. At runtime define `M_z(t)=AnchorSourceSet(z)∩{committed current-event SIC receivers emitting with EXTERNAL_DIRECT, READ_ONLY_OBSERVED or INTERNAL_SELECTED witness}`. Predicted-only or derived-only receivers never enter this anchor mask. This set includes observed B receivers even if they were not among the two selected C keys. In the *next* event's temporal `P_T`, define for each `i∈F_step(t)`:

\[
\mu_i(t)=\begin{cases}
1,&i\in M_z(t),\ i\ne z,\ i\text{ has ordinary ASSOCIATIVE source role},\text{ unique qualified owner};\\
0,&\text{otherwise}.
\end{cases}
\]

**RC4.1 target-scoped routing (normative):** `μ_i(t)` above remains a scalar *source/anchor match record*, **not** a directive to silence every outgoing synapse of i. Define `ContextTarget(j,t+1)` solely from the frozen W structural descriptor: j is a legally committed contextual candidate with an active, pinned P/C role descriptor or a COMPLETE contextual owner with a live `StableBinding`; either receives the permanent physical gate of §5.1. A contextual target is determined from structural keys and status only—not its expected Y, external word labels, or the future event outcome. Set, for each legal ASSOCIATIVE directed link i→j,

\[
\boxed{\mu_{ij}(t)=\mu_i(t)\,\mathbf1[\neg ContextTarget(j,t+1)]}.
\]

Thus `μ_ij=1` **temporarily masks** the generic outgoing ASSOCIATIVE contribution to an **ordinary/non-contextual target** for exactly the next event, but `μ_ij=0` for **every legitimate gated contextual target**, including incomplete legal candidates and COMPLETE depth>1 descendants. A depth-2 owner z2 receiving P sources `(z1, p1)` may still receive its valid p1→z2 input even when p1 is a directly witnessed anchor source masked by the qualified z1 for generic p1→Y routes. This exception changes only neural `P_T`; contextual target admission, predecessor witness provenance, G_ctx, two P-link consolidation, the within-root evidence policy and all source budgets remain mandatory and unchanged. It grants no new q, no new external root, no special activation energy, and no permission to bypass a failed contextual gate. If a target descriptor is stale/illegal, that target fails closed under §5.1 and cannot exploit this exception to emit. Apply the same μ_ij in LEARN, RETRIEVE, FULL/CONTROL, and GENERATE using the same prior frozen μ_i snapshot; do not recompute from a future outcome.

No W/S/E or root evidence changes and no reverse inhibitory link is invented. The qualifying contextual source z and unrelated physically disjoint sources are *never* source-masked. On an ambiguous owner, all affected μ=0 (fail-open neural prediction with a diagnostic, **not** a false specialization claim). If z fails the activity/structural gates, μ stays 0 and the old generic prediction remains. When C is observed without P, z gate=0 and no suppression occurs. The law is valid only for the first-lab **single current lexical event / one-step next-event** use case; broader simultaneous language streams and compositional overlap are DEFERRED. Comparisons with α<1, a learned confidence-gated α, and `B_i=32/128` are **versioned ablations**, not silently used here.

**Critical sequencing:** compute pass 1+2, gated z output and `F_step(t)` first; then compute and freeze `μ(t)` from the completed event. All `P_T(t+1)` and `PredScore` must use the same frozen source `μ_i(t)` and structurally computed directed-link `μ_ij(t)`, and a cold next-event test cannot recalculate μ from Y. Read-only preflight of an unfinished z may instantiate a *scratch-only hypothetical COMPLETE owner* with the consolidated binding, in order to test precisely the eventual μ behavior. This shadow simulation changes no owner status, W or external evidence.

## 6. Temporal-frontier/provenance: residual is not a new event

In addition to numeric activity, each event captures source-contribution lanes: `DIRECT_OBSERVED`, `SPATIALLY_COMPLETED`, `PREDICTED`, `CONTEXT_MATCHED`, `BOOTSTRAPPED`, `RESIDUAL`, `ATTRACTOR`. A cell may receive multiple lanes; the provenance record consists of **tagged contributions**, not a single overwritten label. None of these lane tags is a semantic concept.

- `DIRECT_OBSERVED`: actual SIC receiver stimulated now; eligible as observed F_step only if committed before the event and `A>=theta_emit`.
- `SPATIALLY_COMPLETED` alone: within-event completion; **not** a second external event, and no autonomous F_step by itself.
- `PREDICTED` alone: can change A, but cannot be re-labeled as a direct external witness or become a new observed F_step.
- `CONTEXT_MATCHED`: ordered actual predecessor and current positive witness sources; for contextual z requires the selected P pair to satisfy retained `tau_ctx_q6`, ≥1 retained C source, `A_z>=theta_emit`, no boundary and valid physical binding; LEARN probe-specific exception below. It qualifies a *new contextual* F_step without creating external evidence automatically.
- `BOOTSTRAPPED` by itself cannot establish a witness; `RESIDUAL` and `ATTRACTOR` by themselves never create a new observed event.
- `NEW_SELECTED_INTERNAL` is **disabled** for first-lab single-next-event tests. RC3 physical `G_z^{ctx}` must be enforced even for a cell with DIRECT_OBSERVED reception; no off-context contextual `F_step` is permitted. A valid contextual source is never evidence of Y unless the later actual Y is externally witnessed.

\[
F_t^{step}=\{j:committed_j\land A_j^+\ge\theta_{emit}^{r_j}\land(NEW\_OBSERVED_j\lor NEW\_CONTEXT\_MATCH_j)\}.
\]

`P_T(next)` uses only `F_step(t)` with the **already frozen RC3 temporal source mask μ(t)**, NOT all currently above-threshold residual cells. A valid LEARN probe-supported z in **any incomplete state** `WIRED/PROBE_INCOMING/LEARN_OUTCOME/NO_PROBE_TEST` may enter the B step frontier if the ordered external owned-pair witness satisfies the calibrated `G_ctx` and z was already committed; this is a narrow participation rule **without** external evidence credit by itself. In `NO_PROBE_TEST` the probe remains ON for genuine OPEN LEARN events but is unconditionally OFF for the isolated END-time no-probe scratch preflight and all RETRIEVE events. No backward rewriting of `F_step` or the event activation state after root close.

### 6.1 RC4 typed physical support and derived contextual witness

This contract **supersedes direct-SIC-only P eligibility solely for depth>1 contextual admission and inference**. Every step carries per-cell, per-event immutable support lanes with distinct origin kinds: `EXTERNAL_DIRECT` (genuine OPEN LEARN external SIC), `READ_ONLY_OBSERVED` (real SIC replay/prompt, no learning), `INTERNAL_SELECTED` (generation SIC materialized after a neural winner), `DERIVED_EXTERNAL_CONTEXT` (COMPLETE contextual z emitted on a causal chain of genuine external events), and `DERIVED_RUNTIME_CONTEXT` (same for read-only/generation, possibly descending from internal selection). All of these are distinct from `PREDICTED_ONLY`, `RESIDUAL`, `SPATIALLY_COMPLETED`, `ATTRACTOR` and `BOOTSTRAPPED`, which **cannot** become a new observed source by relabeling. Each event step has one canonical origin, physical SIC bundle digest if applicable, step index, root/session ID and boundary flag. For a contextual source z, record its persisted COMPLETE `OwnerID/StableBinding` reference, frozen `A_z^+`, the actual preceding/current qualifying causal parent source references and integer depth; no evaluation Y or training surface enters support.

- `o_i^{train}(t)` is `X_ext(i,t)>0` only for committed-before-event genuine `EXTERNAL_DIRECT` sensory receivers; it is **zero** for INTERNAL/READ_ONLY. For a COMPLETE contextual z, `o_z^{train}(t)=Q6(A_z^+(t))/1e6` iff it legally emitted in `F_step(t)` without probe, `G_ctx=1`, its entire bounded parent chain is traceable to the **same OPEN external root's actual ordered observations** and contains no INTERNAL/REPLAY/prediction-only link, and binding is live. Call this `DERIVED_CONTEXT_WITNESS` for **P-role participation only**; it creates **no independent external event or external evidence root**.
- `o_i^{runtime}(t)` is the canonical SIC input support for an externally supplied read-only prompt *or* already selected `INTERNAL_SELECTED` SIC event (not a `FULL` prediction alone). A COMPLETE contextual source z receives `o_z^{runtime}=Q6(A_z^+)/1e6` iff its contextual gate fired and all runtime parent witnesses were legally observed/selected in chronological order; call this `DERIVED_RUNTIME_CONTEXT`. Otherwise supports are zero. All support values are Q6-quantized as in §3.1; never choose a semantic word ID to resolve a collision.
- `depth(i)=0` for sensory source; at accepted admission `depth(z)=1+max(depth(p):p is a selected P contextual source)`, with missing contextual parents interpreted as zero. `MAX_CHAIN_DEPTH=8`; reject depth>8, any duplicate/ancestral cycle, any parent not COMPLETE at **admission**, or stale underlying parent bindings. Depth and parent `OwnerID/StableBinding` generation are stored in context-governance W, **not** Cell semantic fields. A legal child's runtime match fails closed when any necessary bound parent's structural validity fails. Depth is fixed; no in-place promotion of an existing owner from depth 1 to 2.
- **No double promotion:** a z derived from two real upstream events remains *one* derived physical P source in the next event, never two independent root confirmations, and cannot be treated as DIRECT_OBSERVED. `V_ext` is decided by LLA on the **single actual completed external root** witnessing current outcome Y, and accepted q remains one maximum per link/key/root. Derived support does not let ROOT-like counters increase, nor does it allow z training when its parent required a learning probe. In GENERATE, all q_ext/q_int and structural learning remain exactly zero even if synthetic runtime support opens a context gate.
- `F_step(t)` admits fresh `NEW_OBSERVED_EXTERNAL`, `NEW_OBSERVED_READ_ONLY`, `NEW_SELECTED_INTERNAL`, or `NEW_DERIVED_CONTEXT` **only with actual supporting typed event provenance and normal emission**. A derived candidate still under PROBE may enter ordinary first-depth learning frontier under §7.5, but **cannot serve as a parent P in a new context** until COMPLETE and independently no-probe valid.

**Causality:** A z at event t can use sources from t−1 only; at t its current C sources must be genuinely observed EXTERNAL in LEARN, or `READ_ONLY_OBSERVED/INTERNAL_SELECTED` in read-only GENERATE. Nested parents refer to earlier finished events, not future Y. The full causal history need not be serialized as a growing event list: persist finite physical owner parent dependencies and keep a session-local proof path of at most depth 8, resetting it at HARD_BOUNDARY. If the proof is missing, fail closed `DERIVED_PROVENANCE_UNVERIFIED` rather than inferring from a large A value.


## 7. Contextual recruitment, provisional wiring, and retained ownership

### 7.1 Decision: repeated real contrast and reuse failure

A local `anchor` is a bounded physical current-event population (not a word). A bounded contrast ledger holds at most `16` observed examples per anchor, `TTL=2000` external events, comparing witnessed predecessor `P`, current `C`, next outcome `Y`, root IDs and comparable coverage. It is a finite *discovery aid*, not long-term neural knowledge. Compare weighted observed neural footprints:

\[
d(U,V)=1-\frac{\sum_i\min(U_i,V_i)}{\sum_i\max(U_i,V_i)},
\quad d(0,0)=0,\ d(0,V)=1 \text{ if }V\ne0,
\]
\[
c_{ext}=\min(1,n_1/2,n_2/2)\,v_{coverage},\quad \nu_{ctx}=c_{ext}d_Pd_Y.
\]

Lab discovery gates: each branch has ≥2 independent completed observed roots, comparable complete next-event coverage, `d_P>=.40`, `d_Y>=.40`, `nu_ctx>=.30`, and evidence of **failure to separate** after two further qualified learning opportunities per branch using a read-only cold-run PredScore (see §9.2). A different result once is not sufficient; an unresolved collision is not a valid contrast. If W already separates branches by `m_reuse=.05`, **reuse existing links; do not recruit**. If ledger evidence expires before a decision, return unresolved, never guess.

### 7.2 Canonical discovery, branch selection, no duplicate owners

A `ComparisonBranchKey` is the temporal comparison key `(anchor, canonical typed P/C/Y physical witness footprint digests, earliest qualifying completed root and order)` and is valid only for **temporary discovery/order**, **not** permanent identity. Contrast pairs are sorted by the lexicographically ordered pair of comparison keys; attempt both still-failing branches in that canonical order, subject to one shared capacity ledger. Same branch in multiple pairs gets one candidate attempt, not duplicate z allocations. A branch with completed matching binding is reused.

Before **any** new contextual admission, call the persistent **`ResolveOwner`** defined in §7.7; no candidate is admitted based solely on a newly different `ComparisonBranchKey` after ledger turnover. Statuses are `REUSE`, `NEW_ELIGIBLE`, `UNRESOLVED_BRANCH_MATCH`, `STALE_OWNER_BINDING`, `OWNER_REGISTRY_CONFLICT`, `OWNER_REGISTRY_CAPACITY`, and inherited explicit deferral/failure. Unresolved/aliased/stale profiles **prohibit speculative duplicate admission**.

### 7.3 Candidate/source selection: deterministic capacity-aware bounded 2/2/2 (RC3)

At `END_EXPOSURE` after link evidence publication into a single shadow snapshot, form role pools C/Y from **actual, directly witnessed SIC receiver supports**; for P only, include those directly witnessed SIC receivers **plus RC4 externally grounded, already COMPLETE, no-probe contextual sources in prior F_step** as defined in §6.1. Every P candidate source must have two independent owned completed-root witnesses and comparable confirmed-rival supports. A contextual source that first becomes COMPLETE in this same END is NOT retrospectively eligible. Require ≥2 committed legal sources per role. For P/C, discard any source lacking at least one usable **new directed outgoing** slot under current live links + pinned/shadow claims; where overlap consumes two separate source keys, the final triple must have room for both. Do **not** discard a candidate because its own latent slots are full if z may list that source: `D_iz` is bidirectionally admitted and reverse index validated. Rank remaining P/C by `(−independent_root_count,−support,−available_outgoing_headroom,cell_id)`, retaining top **8 feasible** per role; rank Y by evidence/root counts because z→Y debits z, not Y. Filtering saturated P/C sources **before** truncating to 8 prevents popular exhausted receivers from hiding viable alternatives. No weak/unwitnessed source may be selected solely for spare capacity.

Enumerate ≤`choose(8,2)^3=21,952` pair triples per z in P/C/Y rank-index order. Enforce the selected-P conjunction's **Q6** witnessed separation `L_z-U_z>=50,000` (the exact `m_P=.05` lab margin) against the confirmed rival external examples, with each P source support recorded as typed DIRECT or fully verified DERIVED_EXTERNAL_CONTEXT (§6.1), compute and provisionally reserve `tau_ctx_q6=U_z+50,000` for the selected pair, all 2/2/2 legal unique keys, six z-side `co-active intra` slots (physical role overlaps consume one slot), source outgoing claims, candidate protection and region scope. Candidate z physical search radius is **own anchor microcolumn plus Manhattan distance ≤2** (bounded at edges), searching radius 1 first then radius 2, stable `(radius,distance,committed_slots,cell_id)` order. Existing committed or protected z is excluded. This is a declared local frontier expansion, not a whole-network free search.

If no feasible option, report `NO_DISCRIMINATIVE_PREDECESSOR_WITHIN_FRONTIER`, `SOURCE_OUTGOING_CAPACITY`, `NO_FREE_CONTEXT_CELL` or `NO_FEASIBLE_2_2_2_WITHIN_FRONTIER` according to the first failed necessary gate, with per-gate counts. Enforce the **64-outgoing** first-lab budget in each source and in the atomic shadow ledger; CROSS cap remains 12. New z is admitted at END only from the *completed root's last EVENT remaining K_R* allowance (`K_R=12`), never retroactively. `ANCHOR_SOURCE_MAX=64` for retained current physical receivers is checked before OwnerID allocation. This changes neither the immutable 24-slot anatomy nor canonical SIC hashing.


### 7.4 Immutable role sets and probation stages

For accepted z, reserve exactly two distinct physical prior-event P=(p0,p1), two C=(c0,c1), two Y=(y0,y1). At depth>1 the P pair may contain COMPLETE contextual parents, and its stable binding must also persist each parent OwnerID/generation and source-type tag; `StableBindingV3` extends V2 and uses the same Q6 threshold triple. At depth=1 the exact RC3.1 V2 physical semantics remain valid; no automatic schema migration or silent reinterpretation is allowed. Roles are physical directed temporal link positions (−1,0,+1), **not** semantic word tags or Cell fields. Keep immutable role keys until COMPLETE or terminal governance.

States remain `WIRED → PROBE_INCOMING → LEARN_OUTCOME → NO_PROBE_TEST → COMPLETE`, plus `FAILED_OR_EXPIRED`. RC3 **separates two clocks**: `probe_matches` (maximum **8** qualified completed roots while WIRED/PROBE_INCOMING) and `consolidation_matches` (maximum **32** qualified completed roots after first entry to LEARN_OUTCOME). A total candidate age `age_events≤240` counts all events in completed roots after admission. These counters are separate; neither clock is reset by a transient phase failure, recovery or retry. The fixed `W_conf_context=240` confirmation deadline on candidate-owned links covers the whole contextual probation; the generic noncontextual candidate deadline remains 100. No candidate receives 8 *total lifetime* root opportunities anymore.

A **qualified owned root** is a completed, independent external exposure *after* admission containing the two selected P either directly witnessed or (only for depth>1) COMPLETE derived-external witnessed in event P **with `Q6(min(P supports))>=tau_ctx_q6(z)`**, ≥1 selected C directly witnessed at the subsequent event B, no collision or boundary, and z already committed before B. Positive-but-subthreshold P support may be a valid generic external observation but is **not** a qualified owned contextual root or candidate-clock match. Each such root contributes at most one to the appropriate clock, **including** failed activation or missing outcome. A root with no qualifying P/B counts only toward age. ABORT/RETRIEVE/REPLAY do not advance these counters. At END, phase/counters/expiration settle atomically from a single post-evidence frozen W*; no temporary read-only run contributes evidence.

#### 7.4.1 RC3 exact transition and expiration order

| From | END guard | On pass | On fail |
|---|---|---|---|
| `WIRED` | qualified root, z genuinely emits under LEARN-only probe, valid accepted P→z or C→z incoming evidence | `PROBE_INCOMING` | remain; consume a probe match |
| `PROBE_INCOMING` | qualified root, real z in B `F_step`, next-event actual observed Y yields accepted z→Y evidence | `LEARN_OUTCOME` and **start** consolidation clock at zero for **subsequent** completed roots | remain; consume probe match |
| `LEARN_OUTCOME` | durable two P + ≥1 C + ≥1 Y in W* | `NO_PROBE_TEST`, immediately perform scratch preflight | remain; consume a consolidation match on qualifying root |
| `NO_PROBE_TEST` | durable binding still legal; **END scratch only**, probe forcibly OFF for `NORMAL_W` and `CONSOLIDATED_W` owned/rival/B-only, shadow COMPLETE routing, and PRE/POST retirement equivalence | atomically `COMPLETE`, retain binding & release probe metadata | remain in `NO_PROBE_TEST`; classify `NO_PROBE_INSUFFICIENT_DRIVE` / `NO_PROBE_FAIL`, `DURABILITY_PENDING`, or `RETIREMENT_SEMANTICS_DRIFT`; next genuine LEARN root can still use temporary probe |
| `COMPLETE` / `FAILED_OR_EXPIRED` | later event | no further phase transitions | idempotent |

A qualifying root consumed **while entering** LEARN_OUTCOME is charged only to the probe clock; only future qualifying roots charge consolidation. A candidate already in LEARN_OUTCOME may enter NO_PROBE_TEST and COMPLETE in the **same** END, journaling both ordered transitions. Earlier WIRED/PROBE_INCOMING cannot jump multiple edges in one END. If the first NO_PROBE_TEST fails (for example, at `E=3.0` with insufficient learned Q), **do not terminally fail, disable the production LEARN probe, or revert the clock**. Remain in `NO_PROBE_TEST` and allow the **next genuinely qualified OPEN LEARN root** to use the temporary probe for real B-step emission and subsequently witnessed Y learning (§7.5 / LLA §6.3). After its independent accepted evidence changes W*, END reruns a separate **zero-probe** scratch test; a repeated scratch test with unchanged W* cannot restart it. These later roots count against the same remaining 32-match consolidation and 240-event age limits. ABORT, REPLAY or RETRIEVE never increment them.

**Expiration after evidence and attempted legal test:** if not COMPLETE, `probe_matches>=8` while in WIRED/PROBE_INCOMING; or `consolidation_matches>=32` in LEARN_OUTCOME/NO_PROBE_TEST; or `age_events>=240` ⇒ `FAILED_OR_EXPIRED`. The limiting last root is usable before expiry. Note the *transition root* that enters LEARN_OUTCOME is exempt from the probe-cap expiration just met if it was successful: this prevents successful outcome acquisition at the 8th root from being discarded. Even if a candidate reaches a cap before the mass threshold, it is an explicit **bounded empirical failure**, not evidence of model impossibility. Release only unprotected claims; retain legal consolidated knowledge and the finite owner governance to prevent duplicate enrollment.

**Required conformance:** 8 genuine discovery matches can establish the z→Y path but cannot automatically consolidate four links; at `A_source=A_target=.5`, q_ASSOC≈.185205 and 17 independent valid roots would reach `E≥3` **if the link is actually created**. A 32-root consolidation window permits this illustrative trajectory, but does not promise it. Candidate q still obeys one accepted contribution per root/key, all physical thresholds and deadline limits.


### 7.5 LEARN-only Bootstrap inside the permanent gate

Probe is **not** the contextual gate and is **not** present in RETRIEVE or a COMPLETED owner. Given actual witnessed predecessor supports and current B support, define

\[
T_z^{probe}=\min(o_{p0}(t-1),o_{p1}(t-1)),\qquad
C_z^{probe}=1-\prod_{c\in C_z}(1-o_c(t)),\qquad
G_z^{probe}=T_z^{probe}C_z^{probe}.
\]

Inside a valid `G_z^{ctx}(t)=1` and an OPEN genuine LEARN event with `phase∈{WIRED,PROBE_INCOMING,LEARN_OUTCOME,NO_PROBE_TEST}` and `z` already committed before B, and **only** in that production learning event:

\[
\hat D_{z,probe}^{(2)}=1-(1-\hat D_{z,base}^{(2)})(1-\eta_b G_z^{probe}),\quad\eta_b=1.
\]

When `G_ctx=0`, set the effective raw and residual output to zero; **do not** multiply in an unauthorized probe. All other ordinary cells retain their Noisy-OR rule. The probe may seed z to permit first genuine z→Y *learning evidence* on a later witnessed next event, but can never count as external proof by itself. For **all** END scratch no-probe testing (including while phase remains `NO_PROBE_TEST`), PRE/POST scratch, RETRIEVE/REPLAY and after COMPLETE, retain `G_ctx` and remove only this additive probe term. A failing scratch preflight MUST NOT silently switch OFF the probe in later genuine learning roots. Genuine consolidated input synapses must carry sufficient Q for z to pass `theta_emit`; a gate pass alone supplies no energy. Core §5.1 therefore prevents false B-only specialization, but **does not guarantee** correct-branch emission without probe; failing activation yields `NO_PROBE_INSUFFICIENT_DRIVE`.


### 7.6 C04 durable role binding and graduation: **two P links required**

`LEGAL_CONSOLIDATED(k,W*)` means the exact live directed key is `CONSOLIDATED`, meets `S>=theta_S`, `E/E_max>=theta_E`, has ≥2 *distinct accepted* external roots, valid source/target prior commitment and Δ/scope, still satisfies current latent eligibility and all source budgets. For frozen **post-evidence/pre-new-admission** `W*`:

\[
P2_DURABLE=LC(p0\to z,ASSOC)\land LC(p1\to z,ASSOC),
\]
\[
C_DURABLE=\exists c\in C_z:LC(c\to z,LOCAL),\quad
Y_DURABLE=\exists y\in Y_z:LC(z\to y,ASSOC),
\]
\[
DURABLE_PATH=P2_DURABLE\land C_DURABLE\land Y_DURABLE\land SAME\_OWNED\_WITNESSED\_BRANCH.
\]

**Never graduate on only one consolidated predecessor.** Retain at least one physically consolidated, selected C and Y; selected P **both** must be consolidated. A consolidated link with no qualified actual owned-branch source witness does not count. New candidate admission and same-root birth cannot count as past evidence.

`COMPLETE` additionally requires probe OFF, legal context matching (`both P, ≥1 retained C`), no-probe successful *owned*, all confirmed rival and `B-only` trials, `A_z(owned)>=theta_emit`, `A_z(rival),A_z(B-only)<theta_active`, and next-event correct-vs-alternative neural margin `>=m_reuse=.05`, both with `NORMAL_W` and `CONSOLIDATED_W` (candidate-only provisional synapses masked in latter). **The last margin runs in a scratch-only hypothetical COMPLETE owner for the candidate being evaluated**, so the same §5.2 temporal masking that would be active after retirement is tested *before* graduation; ordinary production owners and their W are not modified. If the contextual source cannot emit with consolidated W, this test fails and no owner is activated artificially. No outcome label is inserted into inference.

**Mandatory pre-retirement equivalence:** create a `StableBindingV2` for purely DIRECT-P depth-1 or a `StableBindingV3` for depth>1 derived-P **from the actual LC keys** in W*, retaining `(p0→z,p1→z)` in fixed order, the immutable `L_z,U_z,tau_ctx_q6` integer support-calibration triple in that order immediately after the two P IDs in its version-2 canonical payload, and *all selected consolidated* C→z and z→Y keys (at least one each); also store physical role offsets, binding generation, scoped revision fingerprints, status `ACTIVE/STALE`, `OwnerID`, z and anchor IDs. `schema_version=2` is mandatory for depth-1 bindings; `schema_version=3` for derived contexts additionally retains P kind and exact parent OwnerID, anchor, structural binding generation and depth, with the **same** calibration triple. Any unsupported version or missing parent is `UNSUPPORTED_BINDING_SCHEMA`, never silently loaded as complete. In **isolated PRE/POST scratch clones**, PRE retains temporary candidate data, POST has temporary candidate-only phase/probe/role metadata retired and uses *only* the declared legal V2/V3 completed StableBinding; both share the same real legal W. Run owned/rival/B-only cold READ_ONLY episodes in `NORMAL_W` and `CONSOLIDATED_W`, probe OFF, comparing `CTX_RUNTIME`, `G_ctx`, `tau_ctx_q6`, `μ`, `F_step`, `A_z` and neural `PredScore` **bit-identically**. A failure returns `RETIREMENT_SEMANTICS_DRIFT` and leaves candidate pending. Only an atomic root-close can set `COMPLETE`, persist binding, reconcile reservations and retire temporary metadata. A later invalid P/C/Y key makes binding `STALE` and disables contextual emission; it must never fall back to expired candidate metadata.

### 7.7 C04 persistent branch ownership across ledger expiration

- **Temporary identity:** `ComparisonBranchKey` (includes old completed exposure IDs) defines discovery order **only**.
- **Permanent identity:** `OwnerID=(anchor_id,owner_sequence_number)`, with an atomic never-reused per-anchor counter allocated **only on accepted new candidate admission**, independent of training root IDs or words.
- **Finite `OwnerProfileV1` (depth 1) or typed `OwnerProfileV2` (derived P):** bounded physical `AnchorSourceSet` (≤64 directly observed current SIC receiver IDs from two qualifying owned samples; union fixed at admission, not a Y lookup), `OwnerID`, anchor, z, state `ACTIVE/COMPLETE/EXPIRED_VALIDATED/EXPIRED_EMPTY/STALE`; fixed P/C/Y selected physical cells/keys; **two** compact confirmed completed-root observed role-support profiles (top eight per P/C/Y role, fixed numeric serialization; V2 tags P kind and parent scope/ID/generation from LLA §6.6), full observed footprint digests, collision-diagnostic feature digests, audited original root provenance (not part of equality), and a stable binding reference/generation. Retain while protected knowledge or active candidate exists. Profile count charged against finite actual committed contextual candidate resources; no unbounded root history.

`ResolveOwner(anchor,new_branch,confirmed_rivals,frozen_W)` executes **before any allocation**:

1. If partial/uncomparable support, feature alias/collision or missing qualified roots → `UNRESOLVED_BRANCH_MATCH`.
2. Examine **all owner profiles under this anchor**, ordered by `OwnerID` (not full network scan). Find exact physical witnessed P/C/Y footprint digest **including typed derived P source references and stable parent binding identity when present** plus bounded support equality, excluding known collisions; one exact match → `REUSE(OwnerID)` except `STALE` → `STALE_OWNER_BINDING`; >1 → `OWNER_REGISTRY_CONFLICT`.
3. For nonexact profiles, test physical overlap: both new predecessor roots positively support both owner's selected P sources and ≥1 retained C; with compatible witnessed Y → `REUSE` (or conflict/stale as above). If physically overlapping but Y conflicts → `UNRESOLVED_BRANCH_MATCH`, NOT new allocation.
4. A truly new owner is eligible only if the **two-direction** externally grounded direct-or-derived P-pair discrimination between its two new witnesses and **every relevant retained owner** exceeds `m_P=.05` using C03's bounded supports, *and* the fresh P pair has already passed the bounded 2/2/2 feasibility test, *and* contrast/reuse failure/coverage/capacity gates pass. Unclear or overlapping cases return unresolved, never guess. Status `NEW_ELIGIBLE` is permission to **attempt** admission, not evidence that it succeeded.
5. For owners `ACTIVE,COMPLETE,EXPIRED_VALIDATED,EXPIRED_EMPTY,STALE`, registry capacity and permitted states must be checked; stale cannot authorize a duplicate. `EXPIRED_VALIDATED` preserves correct knowledge and blocks automatic duplicate admission; `EXPIRED_EMPTY` retry is **not automatic** and is deferred to an explicit separately versioned policy. No owner ID is recycled.

Temporary contrast observations may expire after `TTL=2000`, cap `16/anchor`; persistent physical owner profiles and `StableBindingV2` do **not** expire merely because that diagnostic ledger expires. All profile writes, index writes, owner counter increments and root-completion markers occur in the same atomic close. On SAVE/LOAD and crash/retry, repeated branch roots must resolve to the **same OwnerID** or explicit conservative unresolved status—never a silent duplicate allocation. The persistent owner profile is *training governance only*: in forward RETRIEVE there is **no branch-to-output lookup**, no stored expected Y used to generate an answer. Read-only runtime may check validated physical `StableBindingV2` to qualify contextual provenance, but **real neural drive always comes from synapses**.

## 8. Context runtime matching is NOT external training evidence

Define distinct contracts:

- `OBS_DIRECT(j,t)`: actual SIC stimulus positive at receiver, even if it is still uncommitted. `OBS_ELIGIBLE(j,t)` additionally requires commitment before event start, and supplies the relevant observed learning/frontier gate. No competing outcome comparison is needed to witness first A/B; per-cell feature alias is diagnostic, not a semantic assertion.
- `CTX_EVENT_MATCH(z,t)`: actual ordered observed predecessor then current witnesses inside one OPEN LEARN root, z already committed, both selected P with legal DIRECT or (for depth>1) externally grounded COMPLETE-derived witnesses **and their pair Q6 support at least `tau_ctx_q6`**, and ≥1 C directly positive; participation and probe phase handled under §7.5. It can qualify runtime behavior, **not** evidence without LLA's separate `V_ext`.
- `CTX_RUNTIME(z,t)`: analogous ordered typed physical P pair (direct SIC or legally derived context, including from already INTERNAL_SELECTED events inside GENERATE) **meeting the retained calibrated `tau_ctx_q6`** and ≥1 **retained consolidated** C source in a `READ_ONLY_EPISODE` without open learning root; checks `A_z_normal>=theta_emit`, legal completed `StableBindingV2` and no crossing boundary. The permanent `G_ctx` is a necessary source-level operator for **both** production LEARN and RETRIEVE, and `CTX_RUNTIME` additionally checks A and the legal binding; it never activates z merely from descriptor metadata. It does **not** inject activity or grant external credit.
- `V_ext`: distinct external training **link** predicate defined by companion LLA; in RETRIEVE it is always zero.

`CTX_RUNTIME` in NORMAL and CONSOLIDATED read-only diagnostics for an incomplete candidate may consult its *temporarily pinned* P/C roles for diagnosis (probe OFF); production-style completed runtime must use **only** the physically consolidated retained descriptor. Prediction-only synthetic B does not count as observed B, and archived old exposure IDs do not substitute for replay of actual SIC features.

## 9. Read-only sessions and prediction measurement

### 9.1 `READ_ONLY_EPISODE` contract

Separate ephemeral session (not an exposure/root ID) with frozen W/H, `R_cold`, ordered actual canonical SIC inputs, `SEALED_FEATURE_REPLAY` or `FRESH_FEATURE_INPUT`, no dynamic admisssions, no learning/evidence updates, no slow adaptation, no probe, no candidate/owner mutation. `SEALED_FEATURE_REPLAY` verifies feature digests and physically replays features; it does not resurrect old training activity. Caller R is untouched; on error discard scratch only.

For P/B branch test: start R_cold; apply P then B, no Y. Save snapshot after B. Compute the **next-step drive** from B's `F_step` with the previously frozen **μ(B)** temporal source mask from §5.2; do not re-evaluate the owner using evaluator Y:

\[
PredScore_W(Y|P,B)=|Y|^{-1}\sum_{j\in Y}P_j^T(next),
\]

where `Y` is an **evaluator-only observed footprint**, never supplied as current input nor looked up by Core. If empty/aliased/noncomparable → `UNRESOLVED`, not invented success. Correct score minus alternative must be `>=m_reuse=.05`. This test measures *neural prediction*; it does not require Assembly formation.

### 9.2 FULL vs CONTROL causal next-event readout

From the **identical** post-B W/H/R scratch checkpoint, advance one internal step X=0:

- `FULL`: normal one-step `P_T` from B's F_step.
- `CONTROL`: set **only** `P_T=0`, preserve identical residual, microcolumn normalization, synchronous propagation and attrator influence. Both are read-only, with no `NEW_SELECTED_INTERNAL`.

\[
gain_j=\max(A_j^{FULL}-A_j^{CONTROL},0),\quad eligibleNext_j=\mathbf1[P_j^T>0\land gain_j>0].
\]

For existing fully legal consolidated Assembly G:

\[
score_{next}(G)=|G|^{-1}\sum_{j\in G} eligibleNext_j\,gain_j.
\]

Rank descending, tie by Assembly ID. Initial `theta_read=.08`, `m_read=.04`; accept iff top score `>=theta_read` and separation `>=m_read`; otherwise `NO_MATCH` or `AMBIGUOUS`; no legal Assemblies ⇒ `NO_ASSEMBLY`. This readout is a *measurement/selection diagnostic*, **not an internal suppressive winner-take-all or a multi-event generator**. A correct neural PredScore without a legal output Assembly is not a native-output success.

### 9.3 RC4 GENERATE_EPISODE and causally safe materialization

`GENERATE_EPISODE` is a **read-only** episode/session (not an OPEN external training exposure), over scratch R initialized `R_cold` once at entry; W/H_slow/owner metadata/evidence and the peripheral ledger are frozen for the *whole* rollout. A session begins with ≥1 genuinely supplied canonical SIC prompt events processed in order with `READ_ONLY_OBSERVED` origin, forming F_step/μ/context gates and frozen Attractor states from actual prompt input. W generation is read-only; scratch R advances; caller R remains untouched. No PROBE, Replay, admissions, q, external roots, H updates, Assembly construction, or ledger writes. Generation is `LANGUAGE` only, `T_gen_max=32` accepted internal events, `MAX_CHAIN_DEPTH=8`. A session-wide snapshot of all Assembly IDs/generations and immutable ledger rows is taken before any selection.

For each step t: (1) from post-event t snapshot, call §9.2 FULL/CONTROL **without feeding candidate text or Y**, retaining the frozen μ(t); (2) rank **all live legal Assemblies** (members in W, >=3, all consolidated reciprocal links); require top `score_next>=theta_read=.08` and top-minus-second `>=m_read=.04` (one candidate ⇒ compare to score 0). If none/ambiguous return `GEN_STOP_NO_MATCH` / `GEN_STOP_AMBIGUOUS`; tie by immutable AssemblyID only for deterministic ranking, **not to waive margin**. (3) Call peripheral `ResolveReadout(top_AssemblyID, exact structural_generation)` **after selection**; it must return one unambiguous attested `(surface, canonical_SIC_feature_bundle, marker)` for this exact ID/generation or generation ends with `GEN_STOP_READOUT_UNKNOWN|GEN_STOP_READOUT_AMBIGUOUS|GEN_STOP_STALE_ASSEMBLY`. Never choose a lower neural rank because it is printable. (4) If marker is `EOS`, stop with `GEN_STOP_EOS` **before** injecting it as a new lexical event; EOS is an explicit learned terminal lexical event's peripheral output marker, not `HARD_BOUNDARY` and not a new training exposure. (5) Otherwise instantiate the stored byte-identical normalized mechanical feature bundle through the **same SIC-V1 projection**, creating `X_int` exactly once with event origin `INTERNAL_SELECTED`, not `EXTERNAL_DIRECT`. No surface string, expected answer or ledger metadata is passed into Core neural scoring; only post-selected mechanical features enter its next event. The ledger's role is *peripheral lexical realization plus canonical event re-encoding*, not semantic reasoning. This is a declared **hybrid** closed-loop generator, not purely neural synthesis of unseen words.

**No-double-count rule**: `X_int` is a selected, already predicted event, so on its event step t+1 zero the previous-step `P_T,j(t+1)` **only for targets j with `X_int,j>0`**; leave `P_T` intact for all other targets, especially contextual cells z needing learned predecessor P→z associations. Compute both neural passes from this single `X_int` and the modified `P_T`, **never** inject `A_j^FULL` as a second `X` or as a second current drive. The full readout was a *scratch comparison*, not an event and not a state update; discard its R before materialization. This targeted mask is `P_T_debit_selected` and is applied once before Noisy-OR, **after** frozen source mask μ(t). It avoids OR-duplicating directly materialized receiver support; it does not pretend that an internally generated event constitutes new independent evidence. In a prompt or a real externally observed event, this mask is OFF (original RC3.1 dynamics unchanged). If SIC projection unexpectedly stimulates a contextual z, its permanent contextual gate still applies.

**Source authority:** these INTERNAL_SELECTED SIC receiver supports may open runtime C/P gates and join `F_step` with `NEW_SELECTED_INTERNAL`; prior COMPLETE contextual sources may become `DERIVED_RUNTIME_CONTEXT` at later steps (§6.1). `V_ext=0` and `V_int=0` unconditionally; internal generation must not increment external_count, q, candidate clocks, Assemble formation, OwnerID, or peripheral attestation. Numeric R dynamics, μ recomputation and finite attractor aging are otherwise normal. If an internal event fails to yield a legal fresh frontier, stop `GEN_STOP_EMPTY_FRONTIER` rather than fall back to obsolete predicted-only frontier or reuse cached surface.

Terminate on: EOS, no neural match, neural ambiguity, unknown/ambiguous/stale surface, empty frontier, repeated **exact** pair `(winner_AssemblyID,winner_generation,canonical_sorted_F_step_IDs)` on **two consecutive accepted selections** (`GEN_STOP_LOOP_DETECTED`), MAX 32 (`GEN_STOP_MAX_LEN`), or invalid parent context (`GEN_STOP_CONTEXT_INVALID`). Each emitted lexical surface is reported with step, winner ID/generation, neural score/margin, readout status, SIC bundle digest and provenance (internal), but no training evidence. HARD_BOUNDARY resets R only **after** termination. Snapshot and journal semantics guarantee deterministic replay within the declared backend.

### 9.4 RC4 Peripheral SurfaceReadoutLedgerV1 (outside W and LLA)

A separate, **peripheral** durable table maps structural `(AssemblyID,structural_generation)` to observed canonical UTF-8 surfaces **and** the exact canonical mechanical SIC feature bundle submitted with that surface, optionally a registered `EOS` marker. `raw_surface` remains audit-only to Core; the peripheral layer captures it at input and stores it alongside the submitted canonical feature bytes, not a reconstructed tokenizer output. A raw text string alone is **insufficient** to re-create the first-lab feature bundle (§3.1), so storing both is mandatory for feedback. Ledger data may contain user-provided text and must follow applicable data retention/privacy rules; this is not a semantic embedding or internal language model. A public `AssemblyID` is an opaque structural identifier, not an encoder token ID.

At a completed real external LEARN root, emit an idempotent post-commit notification for each event **where the Assembly existed LIVE before that event** and at that event `CoreCoverage(A,t)>=rho_core=.70`, `M_A^fresh(t)>=theta_in=.40`, normal emitted activity witnessed with genuine EXTERNAL_DIRECT SIC, and exact surface/feature-bundle digest pairs were supplied. Do not assign a surface to an Assembly created at this END using its earlier event activation; no backdating. A ledger row gains **one confirmation per distinct completed external root**, not per replay/event repetition, and becomes `ATTESTED` only after `external_count>=2` for the **same** `(assembly_id,generation,surface_UTF8,feature_bundle_digest,EOS-marker)` tuple. Readout accepts a single attested tuple per assembly-generation; if zero ⇒ `READOUT_UNKNOWN`, if ≥2 distinct surface/bundle/marker tuples have independent accepted confirmations ⇒ `READOUT_AMBIGUOUS`; if any observed conflict from other surfaces/bundles exists but is not yet resolved by two independent roots, use `READOUT_AMBIGUOUS_PENDING` rather than silently assuming uniqueness. Never pick one surface by frequency when collisions remain. The tuple must be byte-reproduced in SIC-V1 when used in GENERATE.

**Atomic boundary across separate stores:** END publishes W and root COMPLETED first; notification contains `(root_id,event_order,assembly_id,generation,surface_hash,feature_bundle_digest,marker)` plus immutable feature/surface envelope through a durable outbox. The peripheral ledger consumes it idempotently by exact key; duplicate/crashed notifications cannot create a second root confirmation. Ledger failure **does not roll back** already committed neural learning; generation returns `READOUT_UNAVAILABLE` until a reproducible outbox catch-up reconciles. The ledger is immutable/frozen for an active generation episode. On Assembly membership mutation, MERGE, SPLIT or ARCHIVE, the old generation attestation is invalid for the new generation; new confirmations are required. Any peripheral status can be inspected **only after** Core has finished winner selection; neither W dynamics, μ, candidate learning, `score_next`, nor ranking of G candidates may read surfaces, readout counts, or their outcome flags. This is a hard `ZERO_SELECTION_LEAKAGE` invariant; peripheral feedback of the **already chosen** SIC bundle into the next read-only event is allowed and fully provenance-tagged, not hidden semantic selection.


### 9.4.1 RC4.1 — Assembly birth-to-attestation training budget (diagnostic, not a fixed count)

For a newly observed lexical surface in a genuinely cold, uncommitted LANGUAGE network, **three non-retroactive stages** are required before a printable native readout exists: (a) commitment of SIC receivers in an accepted external root (uncommitted cells cannot supply same-root link evidence); (b) actual formation and consolidation of a **reciprocal three-cell LOCAL triangle** and `FORM` publication at END; (c) **two distinct later external completed roots** in which that exact `LIVE AssemblyID/structural_generation` already existed **before each witnessed event** and satisfies both `CoreCoverage>=rho_core=.70` and `M_A^fresh>=theta_in=.40`, with one identical surface/bundle/marker tuple and no unresolved conflict. Multiple repeats within a single external root yield at most one confirmation. Training-time `raw_surface` cannot be used to infer this readiness.

**No universal 9–11-root guarantee exists.** Let `T` be a prospective legal 3-cell triangle and `E(T)` its **six directed LOCAL links**. Under the first-lab no-Replay baseline, an idealized readiness lower bound is `1 + N_triangle + 2` independent roots, where `N_triangle` is the number of *post-commitment* qualified roots needed until **every** directed link in `E(T)` has `E_ext>=3`, `S>=.60`, `external_count>=2`, and legal structural/latent status. For each key e, `E_ext,e=min(10, sum_r q_e,r)` using **at most one accepted maximum q per completed root**; a root contributes `q_e,r=0` if coactivity/eligibility fails. The actual requirement also includes `R_ij^B>=theta_A=.10` on all three pairs, valid specificity/coverage, capacity and stable membership generation. There may be **no finite** `N_triangle` if these requirements cannot be met: report the actual blocker (`NO_RECIPROCAL_TRIANGLE`, missing evidence/eligibility, low fresh coverage, membership mutation or readout ambiguity). A previously committed word or pre-existing triangle changes the starting bound. Distinct vocabulary items cannot borrow evidence roots without qualifying their own physical links; repetitions within one root never count as multiple independent confirmations.

**Worked root-count comparator only (not performance prediction):** if all six links repeatedly have equal post-normalization endpoint activity a, legal `LOCAL` q≈a² and no lost root or reconfiguration, `N_triangle≈ceil(3/a²)`; a=.45 ⇒ 15 qualifying post-commitment roots (idealized total ≥18), a=.60 ⇒ 9 (total ≥12), a=.70 ⇒ 7 (total ≥10), a=.80 ⇒ 5 (total ≥8). At a=.45 coactivity `.2025` barely passes the RC3 `.20` creation floor; a smaller value may not create links at all. `support=.60` does **not** by itself guarantee `A^+>=.45`: gamma, microcolumn normalization, adaptation, local connectivity and independent witness conditions still determine activity. A reciprocal triangle is **not guaranteed** by SIC projecting four cells per feature because adjacency/candidate-link geometry may prevent any three mutually linked cells from forming. The root budget is planning instrumentation for Gate C, never an implicit change to Core or LLA thresholds.

## 10. Event lifecycle, atomic publication, exposure isolation

### 10.1 Learning exposure lifecycle

`CLOSED → BEGIN_EXPOSURE(root) → OPEN → EVENT(0..n−1) → END_EXPOSURE → CLOSED`, or `ABORT_EXPOSURE → CLOSED`.

- Root IDs strictly increasing and never reused after COMPLETED/ABORTED. `BEGIN_EXPOSURE` **atomically** enforces a hard `R_cold` reset *before* event 0, regardless of an optional first-event boundary flag. Preserve W and H_slow; set next order=0 and OPEN checkpoint. No R carryover between independent roots. Retry OPEN root does not reset twice. **FIFR-B06 LAB POLICY A:** capture `H_slow_BEGIN` (all per-cell `g,r_bar`, region EMA and threshold fields) in the same durable BEGIN transaction **before any root-local adaptation**. OPEN EVENT checkpoints retain both this immutable BEGIN image and current adapted `H_slow_EVENT`.
- In OPEN: process contiguous order; atomically commit each event's R progress and legal **sensory cell** admissions, stage link proposals / eligibility / candidate counter changes to that root, but **no `E_ext`, `S`, `external_count` from that root** yet. No other root/REPLAY/RETRIEVE interleaving.
- ABORT: discard root proposals, staged candidate-phase and contrast changes; restore/reset R; mark ABORTED. Already lawful sensory commitment may remain; no aborted-root link evidence credited. **Restore exactly `H_slow=H_slow_BEGIN`** as part of the same atomic ABORT status/write (new conservative LAB POLICY A), even if valid root EVENTs had adapted H_slow. A failed atomic ABORT leaves OPEN with its last checkpoint, and a retry performs one restore; it cannot retain a half-rolled-back threshold. Retain adaptation only on successfully COMPLETED roots. An aborted root may leave permitted sensory admissions in W, but no H_slow effect. Duplicate ABORT request for the same root is idempotent status-only and must not restore an older image over later roots.
- END: reduce each link/root to at most one accepted q,y, validate latent and capacity on fixed pre-close snapshot, allocate ordinary links, update phase/durable paths and owner/profile resolutions, admit candidates if eligible under last-event K_R allowance, update W/ledgers/journals/indices/reservations, mark root COMPLETED **in one atomic transaction**. Only then may REPLAY run.

### 10.2 Canonical close order

1. Freeze latest committed W with root pending journal and valid event snapshots; reduce positive evidence by `(link_key,root)` taking **max q with paired y**, earliest event-order tie. Negative updates are **disabled** for all scopes in first lab; contradictory signs in a future variant would be neutralized for that root/key.
2. For first creation, require valid event-time and closure-time latent eligibility (`D_event=1 AND D_close=1`), correct scope/commitment/coactivity `theta_create`, source budgets and witnessed target. Arbitrated ordinary proposals use `(priority_class,-coactivity,-q,source_id,target_id,scope_order)` with contextual reservations first, in one shadow ledger. Recycled ordinary unprotected pair may fail `STALE_LATENT_ELIGIBILITY`; protected candidate pins may not be recycled.
3. Apply accepted root evidence/S/E and consolidation in post-evidence shadow W; update existing candidates' learning phase, requirements and no-probe checks, then **graduate** if all §7.6 conditions pass. PRE/POST scratch tests use this frozen post-evidence/pre-new-admission W.
4. Discover newly confirmed contrasts; call `ResolveOwner` for **all retained matching owners** before resource allocation; process canonical both-branch ordering, update same shadow owner index/claim ledger to prevent duplicates, admit only `NEW_ELIGIBLE` when 2/2/2 feasibility, discrimination and last-event K_R capacity hold. Failed admission does not consume OwnerID or cells.
5. In the same W shadow transaction, run the bounded Assembly `MAINTAIN→GROW→FORM→MERGE/SPLIT` operators of §2.0 **after link consolidation and contextual candidate/owner resolution**. These operators cannot create synapses or retrospective surface witnesses. Stage an idempotent post-commit peripheral readout outbox for only the live Assembly versions that existed and legally activated **during** witnessed event-time snapshots (§9.4); newly FORM-ed or changed-at-END generations receive no historical confirmation.
6. Commit entire accepted close: synapses, evidence, consolidated flags, owner/binding governance, reverse latent, reservations, candidate phases, Assembly identities/generations/memberships, contrast ledger, journals/outbox/root status and appropriate R advancement. If close fails, discard scratch and retry against updated consistent snapshot. The system observes **either pre-close or post-close** state, never a mix.

**Capacity invariant:** live source-outgoing links + unique reserved future directed keys <=64 in RC3; cross <=12; protected latent slots counted once per physical cell. When reserved key becomes actual live link, transfer capacity claim, don't double debit. A separate event `END_EXPOSURE` does not create extra K_R.

## 11. Cold reset, snapshots, serialization, and reproducibility

- `R_cold`: clear A/A_prev/A_hist, F_step, pass/learning frontiers, current observational lanes, ordered-witness cache, eligibility traces and active attractor strength/age/error; **do not erase W or H_slow**.
- Checkpoint/open root includes `pending_root_proposals`, `next_event_order`, exposure state, event progress and candidate-root staging **and immutable `H_slow_BEGIN` together with most recent `H_slow_EVENT`**. Recovery of OPEN replays from the last committed EVENT checkpoint and MUST NOT recapture BEGIN or apply one event's adaptation twice; ABORT recovery restores H_slow_BEGIN and atomically marks ABORTED, while END recovery is all pre/post closure. If crash occurred before BEGIN publication, there is no OPEN root or checkpoint. Save/load must preserve OwnerProfile, StableBinding, owner counters, inverse latent, reservations and root COMPLETED/ABORTED high-watermark.
- C04 binding integrity: if a necessary P/C/Y consolidated key becomes non-live/illegal, set descriptor `STALE` transactionally and disallow runtime CTX match; unrelated global W version changes trigger scoped validation, not spurious invalidation.
- Configuration hash, the exact §3.1 SIC-V1 salts/serialization contract, deterministic numeric quantization/sort order, seed, source SHA and code SHA must be captured. Identical frozen state + canonical input produces identical read-only output at supported numerical precision; tests should distinguish expected bitwise comparisons (same runtime/backend) from cross-platform tolerance comparisons.
- No inferred success from report writing: all test IDs are **expected**, not executed results.

## 12. Core parameter registry and inheritance

| Name | Laboratory value / rule | Class |
|---|---|---|
| `N,N_r`, microcolumns | 12,288 / 4,096; 32×16×8 per region | inherited shape |
| `delta_A` (V,A,L) | .50/.35/.20 | inherited CAL |
| `gamma_A` (V,A,L) | .90/.85/.80 | inherited CAL |
| `beta` (V,A,L) | 1.0/1.0/.80 | inherited CAL |
| `rho_target` (V,A,L) | .020/.025/.030 | inherited CAL |
| `theta_active_init LANGUAGE` | .20, bounded [.05,.60] | LAB DEFAULT |
| `theta_emit`,`theta_bind` | 1.15×,1.20× region theta_active | inherited fixed factors |
| `B_i`,`B_i^x`,`M_max`,`E_cap` | 64, 12, 12, 4 | 64 = RC3 lab change (32 RC2 baseline) |
| `latent slots` | 6 intra / 6 local / 6 inter / 6 topographic | inherited |
| `context z radius` | Manhattan 1 then 2 from anchor; deterministic; no global search | RC3 LAB |
| `ANCHOR_SOURCE_MAX` | 64 observed physical receiver IDs per owner anchor union | RC3 LAB |
| `context matching` | binary `G_ctx` requires Q6(min(two observed P))≥per-owner immutable `tau_ctx_q6=U_z+50,000` with `L_z-U_z≥50,000`; ≥1 observed legal C; never Y | RC3.1 F_W |
| `context temporal source masking` | `μ=1` on matched current generic anchor emitters iff unique qualified COMPLETE z | RC3 F_W |
| `K_R`; `K_sensory/K_context` | 12 per event; nominal 8/4 transferable | inherited + LAB DEFAULT |
| `H_context` | 5 | LAB from inherited H |
| `theta_admit` | external X > `eps_p=1e-6` | LAB DEFAULT |
| `dP_min,dY_min,nu_ctx_min` | .40,.40,.30 | LAB DEFAULT |
| `m_reuse,m_P` | .05,.05 | LAB DEFAULT |
| `contrast ledger` | 16 per anchor, TTL=2000 external events | LAB DEFAULT |
| `selected role pools` | top 8 per P/C/Y, exactly 2 sources per role | LAB DEFAULT |
| `eta_b`, probe discovery, consolidation, age | 1.0,8 matched roots,32 matched roots,240 completed-root events | RC3 LAB |
| `W_conf_context` | 240 external events for candidate-owned links; generic `W_conf=100` | RC3 LAB |
| `theta_read,m_read` | .08,.04 | LAB DEFAULT |
| `rho_s,T_max,Theta_err` | .90,30,1.50 | inherited |
| `theta_ctx_form,theta_in` | .50,.40 | inherited |
| `theta_pred` | .25 | inherited CAL |
| `k_neural`, `k_evidence` for LOCAL/CROSS Δ0 | 1.0, 1.0 | FIFR-B01 LAB fixed |
| `k_neural`, `k_evidence` for ASSOC Δ1 | 1.0, 0.7408182206817179 | FIFR-B01 LAB fixed |
| `SIC schema`, supports, fingerprint | `SIC-V1`, SHA-256/4 fixed salts, decimal millionths, binary64 | FIFR-B04 LAB fixed |
| `candidate phase machine` | §7.4.1: 8 probe matches, 32 further consolidation matches, 240 completed-root external events | RC3 LAB |
| `ABORT H_slow` | exact BEGIN checkpoint rollback (Policy A) | FIFR-B06 LAB fixed |
| `beta_I,eta_I,rho_cell` | .05,.002,.05 | inherited CAL |
| `beta_H,eta_H,eps_dead` | .05,.005,.002 | inherited CAL |
| `theta_min,theta_max` | .05,.60 | inherited fixed bounds |
| `theta_S,theta_E,E_max` | .60,.30,10 | companion evidence registry |
| `K_min,K_max; theta_merge,theta_ob` | 3,16; .70,.40 | inherited Assembly constraints |
| `theta_weak,theta_sep,N_min,T_c` | .15,.10,6,200 | inherited Assembly constraints |

All remaining inherited assembly parameter values (`theta_A=.10,d_min=2,rho_core=.70,rho_G=.50,sigma_G=.30,rho_keep=.35,sigma_keep=.20`) apply where their operator definitions are actually specified. No hidden default or **uncontracted** per-context threshold adjustment is allowed: the sole explicitly fixed per-owner P-pair `tau_ctx_q6` is governed by §§5.1,7.3 and is never recalibrated after admission. **If an operator lacks an executable definition, report `UNSPECIFIED_OPERATOR` and treat the corresponding native Assembly claim as outside the frozen first-lab baseline, rather than inventing it.**

### 12.1 RC4 added first-lab generation parameters and status

| Parameter | RC4 proposed LAB default | Authority/notes |
|---|---|---|
| `Assembly structural edge` | `theta_A=.10`, live *reciprocal consolidated* LOCAL links | §2.0, not associative |
| `Assembly size/degree` | `K_min=3,K_max=16,d_min=2,M_max=12` | §2.0 finite |
| `Assembly density/specificity` | `rho_core=.70,rho_G=.50,sigma_G=.30,rho_keep=.35,sigma_keep=.20` | §2.0 normalized definitions |
| `Assembly merge/split` | `theta_merge=.70,theta_ob=.40,theta_weak=.15,theta_sep=.10,N_min=6,T_c=200` | §2.0 deterministic one-pass; cooldown blocks re-edit of same IDs until 200 completed external events |
| `K_FORM_PER_END` | 12 | RC4 bounding choice |
| `MAX_CHAIN_DEPTH` | 8 (sensory=0, new contextual=1+max(P parental depth)) | §6.1, LLA §6.6 |
| `Generation length` | `T_gen_max=32`, early EOS/no-match/ambiguity/loop stop | §9.3 |
| `Readout thresholds` | `theta_read=.08,m_read=.04` (unchanged) | only legal Assemblies |
| `Ledger attestation` | ≥2 **independent EXTERNAL** completed roots after assembly generation existed live before event, on exact surface + feature bundle + EOS marker | §§9.4–9.4.1; no fixed 9–11 total-root claim |
| `P_T_debit_selected` | zero P_T only on SIC receivers actually present in selected X_int | §9.3 read-only only |
| `OwnerProfileV2/StableBindingV3` | depth>1 with typed P source and persisted context-parent ID/generation | §6.1; first-depth V2 remains legal |

**No source-derived proof is claimed for the NEW RC4 parameters or operators.** They are candidate experimental definitions to be audited and tested. RC3.1 first-lab single-event regression remains unchanged when GENERATE, nested contextual learning and native assembly operators are toggled OFF in a versioned comparator.


## 13. Mandatory Core validation and expected status codes

| Test/gate | Required observation / failure response |
|---|---|
| Cold independent roots | r1 A/B/C followed by r2 D/B/E starts from same `R_cold`, never leaks r1 P into r2 |
| First sensory commitment | an uncommitted X receiver may be admitted but cannot give prior same-event learning evidence |
| Two-pass determinism | frozen W/R/H and event reproduces same A^(1), A^+, per-lane support |
| Residual timeline | old A remains in R but is not re-issued as fresh `F_step` on B without qualification |
| Contextual wire capacity | 2/2/2 claims are legal in both latent directions and **64** source outgoing budget; source selection filters exhausted P/C *before* top-eight clipping; no double debit |
| RC3.1 calibrated conjunction | In cold owned P/B z may emit from learned Q; cold B-only and **admission-confirmed** rival with partially positive P supports gate z to zero without probe; threshold is bit-stable through SAVE/LOAD |
| RC4.1 directed contextual routing | Frozen `μ_i` attenuates generic ASSOCIATIVE targets only via `μ_ij=μ_i·1[not ContextTarget(j)]`; preserves higher-depth contextual P inputs while generic B→C is masked for one step; W and evidence untouched |
| RC3.1 consolidation clocks | 8 discovery matches, then up to 32 additional consolidation matches, 240 completed-root external events total; after NO_PROBE_INSUFFICIENT_DRIVE, live LEARN probe stays available and no-probe scratch stays OFF; no duplicate counting or replay clock inflation |
| RC3 capacity scaling | compare 32/64/128 as separate configurations, measure P/C pool failures, 64-source AnchorSourceSet gate and local radius-2 candidate search |
| C04 two-P graduation | p0/p1 both consolidated; one C and one Y consolidated; PRE/POST removal identical |
| C04 TTL owner stability | roots 10/11 and 2500/2501 same physical branch: same OwnerID or conservative unresolved, never silent duplicate |
| Distinct owners | both-direction P discrimination among bounded retained profiles required before NEW |
| Crash/retry | one atomic close, one OwnerID and one accepted external root, no half-index state |
| Read-only episode | actual SIC replay or fresh observation, W/H/caller R unchanged, no probe |
| FULL/CONTROL | only temporal drive differs; causal next gain excludes old B residual |
| Native Assembly | new RC4 formation attempts from real reciprocal consolidated LOCAL triangles, deterministic maintain/grow/form/merge/split and live IDs; `NO_RECIPROCAL_TRIANGLE` or `NO_ASSEMBLY` is a genuine report, not replaced by labels/fixtures |
| Hierarchical witness | a COMPLETE no-probe z emitted at event t qualifies a typed DERIVED_EXTERNAL P for t+1 only when every causal ancestor has real OPEN external provenance; any probe-only/REPLAY/INTERNAL contribution yields zero external q; 8-level bound enforced |
| RC4 internal materialization | only the highest neurally selected Assembly can request one unambiguous peripheral SIC bundle; no label/ledger lookup before ranking; targeted P_T selected-receiver debit; no `FULL` activation injection; strict W/H evidence immutability over ≥5 steps |
| RC4.1 Assembly readiness | commitment root precedes local triangle evidence; no q retroactivity; FORM at END cannot count for attestation; two later independent witnessed roots required for exact unmutated generation; inspect six directed edge q and geometry instead of assuming 9–11 roots |
| RC4 readout and identity | two distinct completed roots required per exact Assembly ID/generation + surface + bundle; formation at END cannot credit earlier event; collision/merge/split/restart yield no guessed text |
| RC4 EOS/composition | EOS is chosen as learned lexical output before termination, separate from HARD_BOUNDARY; unseen G3 syntactic combinations tested on held-out examples and separately reported, never inferred from G1/G2 |
| Stale/legacy binding | any required physical key illegal or threshold calibration missing ⇒ `STALE_OWNER_BINDING` / `INVALID_CONTEXT_THRESHOLD`; `StableBindingV1` legacy encoding is `UNSUPPORTED_BINDING_SCHEMA`, no fallback |
| FIFR-B01 factor | one `A=.8,Q=.3` ASSOCIATIVE link ⇒ `P_T=.24`; `A_target=.6` ext witnessed ⇒ `q=.3555927459272246` |
| FIFR-B02 Replay | REPLAY off baseline; declared on-comparator ⇒ `ω=.25`, example `q_ASSOC=.08889818648180615`, E_ext and ext count unchanged |
| FIFR-B03 creation | SAME event Pass1 `.40`, final source `.80`, target `.50` ⇒ creation coactivity `.40` (when Pass1 eligible), not `.20` |
| FIFR-B04 SIC | exact four-cell SHA-256 vectors, Unicode NFC equality, shared receiver X_fixed=625000 and fixed role fingerprint |
| FIFR-B05 phases | completed qualified failing z consumes one opportunity; ABORT consumes none; only durable full no-probe PRE/POST pass can COMPLETE; endcap tests run before expiration |
| FIFR-B06 rollback | BEGIN–EVENT adapt–ABORT restores H_slow_BEGIN; crash/retry equivalent; legal sensory admission may remain |

## 14. Scope, traceability, focused C04 review outcome, and freeze gate

**Source ancestry (SHA-256):** historical original `6535ce7a4aad54a24a2c15c0a2560e4211c11066876c11b65d2469d40d90a33d`; unified v0.9.0 `89dca119392a9e7598e663b8c1ea9b0d2b80fa9b3bdc349957a2a6497427e06f`; C01 `b3e23d77bc28d0f2895982a4fa3031e73251be6b925aac4d1d4edc30808cc887`; C02 `7b41c3f3c31715fdf407a7f12aaa94207efcb997db2debed633415828f725fdf`; C03 `a9d7d922c7d025a377df7d61d52ec876185ebda18d089e4f5841f37dfcf974d1`; C04 `04f3673d8d55ee88fd545283c93a1a2f3e63e9d8716474578c9e84540d0ff8f4`.

**C04 focused FFR-05 textual disposition (not an independent implementation test):**

| Earlier blocker | Review of correction | Narrow result |
|---|---|---|
| FFR04-B01: one durable P vs two-P runtime match | C04 fixes `P2_DURABLE`, persists both physical P keys, mandates PRE/POST retirement equivalence and save/load/stale checks | **Addressed in consolidated candidate contract** |
| FFR04-B02: root-ID-bound BranchKey duplicate after ledger TTL | C04 adds non-recycled `OwnerID`, bounded OwnerProfile and fail-closed ResolveOwner, with atomic admission | **Addressed in consolidated candidate contract** |

**Remaining explicit limitations, NOT hidden as successes:** unbounded long continuous streams; negative error correction (off); Audio/Vision cross-event timing; empirical success of bounded RC4 multi-event language generation; proof that permanent gate plus learned Noisy-OR supplies enough owned-context energy; ability to consolidate inside the new 32-root window; native Assembly emergence/readout (operators are now mathematically specified but not shown attainable through local learning); degradation under SIC collisions; generalization outside seen branches; resource exhaustion; owner-identity matching under severe noise (must fail unresolved).


**RC3 context redesign (new LAB proposal, not an approved historical law):** §5.1 hard binary contextual gate on physical P/C witness and live role keys; §5.2 one-step unique-owner generic temporal source mask, preserving W and no negative learning; §7.4 separate 8-probe and 32-consolidation opportunities; §7.3 feasibility-first P/C pools, source outgoing 64 and radius-2 local frontier. This candidate is explicitly **NOT FROZEN**. A strong P/B conjunction is a necessary *selectivity* repair; its sustained output activity, full C/E score margin and scalable resource efficiency remain empirical gates.

**FIFR-01 in-place correction set (LAB-CONTRACT-01, RC2):** the formerly unresolved factors `κ_scope(Δ)` (split into `k_neural` and `k_evidence`), `ω_root`/Replay policy, coactivity source timing, SIC serialization and numeric convention, candidate phase transitions, and ABORT/H_slow rollback now have explicit fixed first-lab decisions in these **same two companion documents**. These are **new lab choices**, not claims about original historical frozen laws, and have not been executed or independently freeze-approved. RC4 supplies explicit executable Assembly `D/Spec/CoreCoverage` operators in Core §2.0; their feasibility under genuinely learned mutual LOCAL connectivity remains unproven. Consequently a successful **focused** C04 review is not automatically a successful **full** integrated freeze review.


**RC3.1 user-review closure (three narrowly targeted repairs):** (1) removed the obsolete 8/200 `candidate transition guards` registry row; (2) made genuine LEARN probe eligibility explicitly include an incomplete candidate in `NO_PROBE_TEST` while all END scratch and RETRIEVE checks remain probe-free; (3) replaced the `>0` runtime predecessor gate by the frozen, physically calibrated Q6 margin check. These are **proposed contract repairs**, not runtime-test PASS or Final Freeze. Validation IDs `LLA-T36..T41` are required.

**Release gate:** independent review of **these two integrated documents together** for numerical/transactional ambiguities; then `implementation-contract freeze` only if clean. Subsequently build test fixture dynamics, zero-knowledge contextual learning, cold read-only neural separation, scope/budget/save-load/crash tests, ablations, retention and resource scaling. Theoretical consistency never substitutes for actual training results.


**RC4.1 targeted integration:** §5/§5.2 now preserves legitimate higher-depth ASSOCIATIVE incoming paths under source-anchored μ; §9.4.1 makes the post-commit triangle plus post-birth ledger readiness an explicit measured Gate C dependency, not a fixed curriculum guarantee. Test designs reside in LLA `LG-T15` and `LG-T16`. The revision is **NOT FROZEN** and no real learning/generation tests have been executed.

**RC4 candidate release boundary:** the added G1 (retained multi-event sequences) / G2 (depth≤8 contextual continuation) design can be implemented and falsified; it is not a language fluency or novel compositional G3 proof. A fail-closed peripheral decoder makes lexical rendering possible for witnessed events only. This is a proposed integration, NOT an implementation-contract freeze; the companion LLA is co-normative and both must pass another focused integrated review.

**Exact RC3.1 baseline SHA-256 inputs:** `DGCA_CORE_RC3_1.md` = `5e87c5a44405e6ba5804f138d835b2d443d2e5e45171cdc3fdce86ee92036727`; `DGCA_LLA_RC3_1.md` = `9ad619ccd55f05bc9d3c9fe02365f1921bfbebe8dc383b578bcea639d790237c`. RC4 uses these as immutable source candidates; no historical frozen law was silently revised.
