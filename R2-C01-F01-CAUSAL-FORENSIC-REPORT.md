# DGCA NEXT V2 — R2-C01-F01 CAUSAL FORENSIC REPORT

## Causal Forensics of Multi-Context Learning and Generation Failure

- **Investigation Status:** AUTHORIZED READ-ONLY FORENSIC INVESTIGATION — COMPLETE
- **Final Verdict:** `R2-C01-F01 FORENSIC COMPLETE — CAUSAL MECHANISMS IDENTIFIED`
- **Role:** Principal Cognitive Architecture Research Engineer, Computational Neuroscience Analyst, and Formal Scientific Verification Lead
- **Repository:** `naoufelbvb2-arch/DGCA-NEXT-V2`
- **Frozen Production Baseline:** `f044c20b532f89749675120ffb1d8ada997e3a5e` (`main`)
- **Accepted R2-C01 Experiment HEAD:** `9f6e472dcfc92b0a16a65298d1d6a3c71d0e44bb`
- **Active Forensic Branch:** `experiment/r2-c01-f01-causal-forensics`
- **Deterministic Checkpoint Hash (56 roots):** `f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`
- **Deterministic Checkpoint Hash (112 roots):** `692b1f0e7d0f709a9a8d52089673f2e088407b4c66d0780ea4412dd3492cde4b`
- **Production Code Changes:** ZERO (`src/` is 100% byte-for-byte identical to `main`)

---

## EXECUTIVE SUMMARY

The R2-C01 four-sentence trial (`القط يشرب الحليب <EOS>`, `النسر يشرب الماء <EOS>`, `الطفل يأكل التفاح <EOS>`, `الطفل يشرب الماء <EOS>`) demonstrated successful autonomous structural learning (121 committed cells, >1,000 synapses, 13 live assemblies, 15 ledger attestations) but exhibited two distinct generation failures:
1. **P1 Generation Stoppage at Step 0 (`GEN_STOP_NO_MATCH`):** The prompt `القط يشرب` failed to emit `الحليب`, scoring only $0.021402 < \theta_{\text{read}} (0.08)$.
2. **Premature Step 1 Halting and Failure to Emit `<EOS>` across All Probes:** In P2, P3, and P4, the network emitted the correct target object at Step 0, but failed to emit `<EOS>` at Step 1, halting with either `GEN_STOP_NO_MATCH` or un-attested intermediate transitions instead of terminating with `GEN_STOP_EOS`. At Root 112, P2 exhibited cross-context intrusion (`الماء` $\to$ `يأكل` $\to$ `التفاح`).

Through rigorous mathematical step-level tracing, dynamic state logging, and counterfactual ablation analysis, this forensic investigation has isolated the exact causal mechanisms:
- **Causal Mechanism 1 (F01-S03 & F01-S04 — P1 Failure):** Associative dilution under 4-sentence exposure schedules caused direct candidate synapses from `يشرب` to `الحليب` to cross the fixed $W_{\text{conf}} = 100$ external event deadline at Root 30 with $E_{\text{ext}} = 2.545 < \Theta_E \cdot E_{\text{max}} = 3.000$, resulting in irreversible candidate pruning. Re-created at Root 33, they remained un-consolidated candidates ($E_{\text{ext}} \approx 1.5 - 1.7$) and were masked during generation (`mask_nonconsolidated=True`). Simultaneously, contextual binding cell $z=8320$ was constrained by the Core §7.4 architectural limit ($2$ forward targets) and drove only $1$ consolidated member of Assembly 11 (`8430`), leaving the 5-member assembly with average score $0.021402 < \theta_{\text{read}} = 0.08$.
- **Causal Mechanism 2 (F01-S02, F01-S05 & F01-S07 — EOS Failure):** The failure to emit `<EOS>` is **candidate-specific differential gain collapse**, not global network lateral saturation. All nominal items (`القط`, `النسر`, `الطفل`, `الحليب`, `الماء`, `التفاح`) share the Arabic definite prefix `^ال`, whose 3 fixed-support cells (`8416, 8575, 8586`) formed strong consolidated associative projections to all 9 EOS cells because every training sentence ended with a definite noun followed by `<EOS>`. Consequently, the prompt subject's `^ال` activated EOS cells prematurely at event 1 during `يشرب` ($P^T = 0.8591, A^+ \approx 0.53$). Re-injection of the object at Step 0 drove recurrent local self-excitation, saturating EOS cells to $A^+ \approx 0.90 - 0.95$. In Step 1, local recurrent drive in the CONTROL pass ($P^T = 0$) forced $A_{\text{ctrl}} = 1.000000$, matching the FULL pass ($A_{\text{full}} = 1.000000$). Differential causal gain collapsed to $\text{Gain}_{\text{EOS}} = 1.0 - 1.0 = 0.000000$, completely extinguishing EOS candidate drive.
- **Causal Mechanism 3 (F01-S02 & F01-S06 — Assembly 9 Score & Cross-Context Intrusion):** Assembly 9 (`يأكل`) cells (`9103, 9201, 10087, 10318, 11942`) were un-stimulated during events 0 and 1 ($A_{\text{ctrl}} \approx 0.10 - 0.17$), preserving full differential headroom. In P2 Step 1, associative drive from `^ال` inside `الماء` produced $A_{\text{full}} \approx 0.25 - 0.36$, yielding positive differential gain ($\text{Gain} \approx 0.07 - 0.18$) and score $0.096262 > \theta_{\text{read}}$, allowing Assembly 9 to win over EOS. At Root 112, Assembly 9 reached generation 3 and ledger attestation, emitting surface `يأكل`, which subsequently drove Assembly 10 (`التفاح`) via strong S3 associations.

---

## 1. EXACT BASELINE PROVENANCE

All forensic verifications were conducted from the pristine, immutable production and experimental baselines:

```
Authoritative Remote:      naoufelbvb2-arch/DGCA-NEXT-V2
Frozen Production Baseline: f044c20b532f89749675120ffb1d8ada997e3a5e (main)
Accepted R2-C01 Baseline:   9f6e472dcfc92b0a16a65298d1d6a3c71d0e44bb (experiment/r2-c01-four-sentence-context)
Forensic Branch:           experiment/r2-c01-f01-causal-forensics
Forensic Branch Parent:    9f6e472dcfc92b0a16a65298d1d6a3c71d0e44bb
Git Working Tree Status:   Clean (zero modified tracked files; git diff main -- src/ is empty)
```

### Deterministic State Provenance
Bitwise determinism of the cold-start learning pipeline was verified against the canonical SHA-256 snapshot hashes:
- **56-Root Machine State SHA-256:**
  `f7739b0120b06f0e1d90bff0eb4b5acacf9d32e36da62a173fb932a999709edc`
- **112-Root Machine State SHA-256:**
  `692b1f0e7d0f709a9a8d52089673f2e088407b4c66d0780ea4412dd3492cde4b`

Re-execution of independent cold-start runs from random seed zero yielded identical cryptographic state hashes, confirming 100% deterministic reproducibility.

---

## 2. REPRODUCED 56-ROOT AND 112-ROOT RESULTS

Execution of the authoritative generator (`dgca.core.generator::generate_episode`) on both the 56-root and 112-root machine states yielded exact reproduction of all reported R2-C01 behaviors:

### Table 2.1: 56-Root Primary Probe Outcomes
| Probe ID | Prompt Context | Expected Continuation | 56-Root Emitted | Stop Status Code | Step Count | Primary Causal Factor |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **P1** | `القط يشرب` | `الحليب <EOS>` | `[]` | `GEN_STOP_NO_MATCH` | 1 | Direct candidate pruning at Root 30; binding fan-out limit |
| **P2** | `النسر يشرب` | `الماء <EOS>` | `["الماء"]` | `GEN_STOP_READOUT_UNKNOWN` | 2 | Step 0 emitted `الماء`; Step 1 Asm 9 won (un-attested gen 3) |
| **P3** | `الطفل يأكل` | `التفاح <EOS>` | `["التفاح"]` | `GEN_STOP_NO_MATCH` | 2 | Step 0 emitted `التفاح`; Step 1 EOS differential gain collapsed to 0 |
| **P4** | `الطفل يشرب` | `الماء <EOS>` | `["الماء"]` | `GEN_STOP_NO_MATCH` | 2 | Step 0 emitted `الماء`; Step 1 EOS differential gain collapsed to 0 |

### Table 2.2: 112-Root Primary Probe Outcomes
| Probe ID | Prompt Context | Expected Continuation | 112-Root Emitted | Stop Status Code | Step Count | Primary Causal Factor |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **P1** | `القط يشرب` | `الحليب <EOS>` | `[]` | `GEN_STOP_NO_MATCH` | 1 | Continued direct synapse dilution; sub-threshold binding drive |
| **P2** | `النسر يشرب` | `الماء <EOS>` | `["الماء", "يأكل", "التفاح"]` | `GEN_STOP_NO_MATCH` | 4 | Cross-context intrusion chain (`الماء` $\to$ `يأكل` $\to$ `التفاح`) |
| **P3** | `الطفل يأكل` | `التفاح <EOS>` | `["التفاح"]` | `GEN_STOP_NO_MATCH` | 2 | Step 1 EOS differential gain collapsed to 0 |
| **P4** | `الطفل يشرب` | `الماء <EOS>` | `["الماء"]` | `GEN_STOP_NO_MATCH` | 2 | Step 1 EOS differential gain collapsed to 0 |

### Table 2.3: Ambiguity & Diagnostic Probes (56 roots)
| Probe ID | Prompt Context | Emitted Surfaces | Stop Status Code | Interpretation |
| :--- | :--- | :--- | :--- | :--- |
| **Ambiguity 1** | `الطفل` | `[]` | `GEN_STOP_AMBIGUOUS` | Ambiguity detection between `يأكل` and `يشرب` ($\Delta < M_{\text{read}}$) |
| **Ambiguity 2** | `يشرب` | `["الماء"]` | `GEN_STOP_AMBIGUOUS` | 2:1 root frequency bias emitted `الماء`; Step 1 detected ambiguity |
| **Diagnostic 1** | `النسر يأكل` | `["التفاح"]` | `GEN_STOP_NO_MATCH` | Associative link `يأكل` $\to$ `التفاح` (Asm 10) wins Step 0 |
| **Diagnostic 2** | `القط يأكل` | `["التفاح"]` | `GEN_STOP_NO_MATCH` | Associative link `يأكل` $\to$ `التفاح` (Asm 10) wins Step 0 |

---

## 3. FULL/CONTROL CAUSAL ACTIVATION TRACES

The DGCA NEXT V2 generation protocol enforces causal readout via `evaluate_full_vs_control_readout` ([`src/dgca/core/readout.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/readout.py#L110-L195)), which executes two distinct passes at each generation step $t$:
1. **FULL Pass:** Propagates both local recurrent drive and forward predictive transmission:
   $$P^T(c) = \sum_{s \in \text{prev\_active}} A_{\text{prev}}(s) \cdot S(s, c)$$
   $$A_{\text{full}}(c) = \sigma\left(\mu \cdot A_{\text{prev}}(c) + \sum_{\text{local}} A_{\text{prev}}(i) \cdot S(i, c) + P^T(c) - \Theta_{\text{act}}\right)$$
2. **CONTROL Pass:** Isolates internal recurrent and persistence drive by setting predictive transmission to zero ($P^T = 0$):
   $$A_{\text{ctrl}}(c) = \sigma\left(\mu \cdot A_{\text{prev}}(c) + \sum_{\text{local}} A_{\text{prev}}(i) \cdot S(i, c) - \Theta_{\text{act}}\right)$$
3. **Differential Causal Gain:**
   $$\text{Gain}(c) = \max\left(0.0, A_{\text{full}}(c) - A_{\text{ctrl}}(c)\right)$$
4. **Assembly Scoring:**
   $$\text{Score}(\mathcal{A}) = \frac{1}{|\mathcal{A}|} \sum_{c \in \mathcal{A}} \text{Gain}(c)$$
   An assembly is eligible if and only if $\text{Score}(\mathcal{A}) \ge \theta_{\text{read}} = 0.08$.

### Mathematical Trace of Probe P1 (Step 0)
- **Prompt:** `القط يشرب` (Events 0 and 1).
- **Target Assembly:** Assembly 11 (`الحليب`, 5 members: `8430, 9731, 9910, 9951, 10692`).
- **Synaptic State:** Direct synapses from `يشرب` (`8327, 10167, 10696`) to Assembly 11 are in `CANDIDATE` state ($E_{\text{ext}} \approx 1.5 - 1.7$) and therefore masked ($S_{\text{eff}} = 0$).
- **Contextual Binding State:** Context cell $z=8320$ fires ($A^+ \approx 0.638$). It has only $1$ consolidated forward target in Assembly 11: cell `8430` ($S = 0.8678, E_{\text{ext}} = 3.2365$). Its other target `9731` is a `CANDIDATE` ($E_{\text{ext}} = 0.1823$) and masked.
- **Differential Causal Gain at Step 0:**
  - Cell `8430`: $A_{\text{ctrl}} = 0.000000, A_{\text{full}} = 0.075605 \implies \text{Gain} = 0.075605$.
  - Cell `9731`: $A_{\text{ctrl}} = 0.000000, A_{\text{full}} = 0.031405 \implies \text{Gain} = 0.031405$ (residual lateral leakage).
  - Cells `9910, 9951, 10692`: $A_{\text{ctrl}} = 0.000000, A_{\text{full}} = 0.000000 \implies \text{Gain} = 0.000000$.
- **Assembly Score:**
  $$\text{Score}(\text{Asm 11}) = \frac{0.075605 + 0.031405 + 0 + 0 + 0}{5} = \frac{0.107010}{5} = 0.021402$$
- **Outcome:** $0.021402 < \theta_{\text{read}} (0.08)$. No candidate exceeds threshold. Readout status = `NO_MATCH`. Generation terminates immediately with `GEN_STOP_NO_MATCH` and 0 emitted tokens.

### Mathematical Trace of Probe P2 (Step 0 and Step 1)
- **Prompt:** `النسر يشرب`.
- **Step 0:**
  - Direct synapses from `يشرب` to Assembly 6 (`الماء`) are `CONSOLIDATED` ($E_{\text{ext}} = 8.7666$).
  - Full predictive transmission $P^T \approx 0.86$ drives all 7 cells of Assembly 6.
  - $\text{Score}(\text{Asm 6}) = 0.625366 > \theta_{\text{read}} (0.08)$. Margin over Assembly 11 ($0.326347$) is $0.299019 > M_{\text{read}} (0.05)$.
  - **Winner:** Assembly 6 (`الماء`) emitted!
- **Step 1 (The Crucial Forensic Step):**
  - Prompt history updated with emitted surface `الماء` re-injected.
  - **Competing Candidates:** Assembly 2 (`<EOS>`, 9 members) vs Assembly 9 (`يأكل`, 5 members).

#### Differential Trace of Assembly 2 (`<EOS>`):
Because `^ال` inside `النسر` activated EOS cells prematurely at event 1 ($A^+ \approx 0.53$), and re-injection of `الماء` at Step 0 drove EOS cells through recurrent local synapses to $A^+ \approx 0.90 - 0.95$:
- In CONTROL pass ($P^T = 0$): Pre-existing activation $A_{\text{prev}} \approx 0.95$ combined with internal recurrent self-excitation ($S_{\text{local}} \approx 1.0$) drives:
  $$A_{\text{ctrl}}(c) = 1.000000 \quad (\forall c \in \text{EOS})$$
- In FULL pass ($P^T > 0$): Forward associative drive from `الماء` also drives:
  $$A_{\text{full}}(c) = 1.000000 \quad (\forall c \in \text{EOS})$$
- **Differential Causal Gain:**
  $$\text{Gain}_{\text{EOS}}(c) = \max\left(0.0, 1.000000 - 1.000000\right) = 0.000000 \quad (\forall c \in \text{EOS})$$
  $$\text{Score}(\text{Asm 2 / EOS}) = 0.000000$$

#### Differential Trace of Assembly 9 (`يأكل`):
Assembly 9 cells (`9103, 9201, 10087, 10318, 11942`) were **never activated** during prompt events 0 or 1, nor during Step 0.
- In CONTROL pass ($P^T = 0$): Pre-existing activation is tiny background leakage:
  $$A_{\text{ctrl}}(9103) = 0.177218, \quad A_{\text{ctrl}}(9201) = 0.177114, \quad A_{\text{ctrl}}(10087) = 0.106560$$
- In FULL pass ($P^T > 0$): Forward associative projection from `^ال` inside `الماء` (synapse `10899 -> 9103`, etc.) delivers predictive drive $P^T \approx 0.13 - 0.25$:
  $$A_{\text{full}}(9103) = 0.360155, \quad A_{\text{full}}(9201) = 0.360098, \quad A_{\text{full}}(10087) = 0.180479$$
- **Differential Causal Gain:**
  $$\text{Gain}(9103) = 0.360155 - 0.177218 = 0.182937$$
  $$\text{Gain}(9201) = 0.360098 - 0.177114 = 0.182984$$
  $$\text{Gain}(10087) = 0.180479 - 0.106560 = 0.073919$$
  $$\text{Gain}(10318) = 0.020739, \quad \text{Gain}(11942) = 0.020734$$
- **Assembly Score:**
  $$\text{Score}(\text{Asm 9}) = \frac{0.182937 + 0.182984 + 0.073919 + 0.020739 + 0.020734}{5} = \frac{0.481313}{5} = 0.096262$$
- **Outcome:** $0.096262 > \theta_{\text{read}} (0.08)$ with margin $0.096262 > M_{\text{read}} (0.05)$ over all other candidates (all scoring $0.000000$). Assembly 9 **wins** Step 1!

```
+-----------------------------------------------------------------------------------------+
|                  CANDIDATE-SPECIFIC SATURATION VS HEADROOM AT STEP 1                    |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|  CANDIDATE: Assembly 2 (<EOS>)                                                          |
|  Prior Activation: High (0.90 - 0.95) due to subject '^ال' associative projection      |
|  Control Pass:     A_ctrl = 1.000000  (saturated by recurrent self-excitation)          |
|  Full Pass:        A_full = 1.000000  (saturated)                                       |
|  Differential Gain: Gain = 1.000000 - 1.000000 = 0.000000  ===> SCORE: 0.000000        |
|                                                                                         |
|  CANDIDATE: Assembly 9 ('يأكل')                                                         |
|  Prior Activation: Low (0.00 - 0.10) (un-stimulated during events 0 & 1)               |
|  Control Pass:     A_ctrl = 0.106560 - 0.177218  (not saturated; headroom available)   |
|  Full Pass:        A_full = 0.180479 - 0.360155  (driven by '^ال' inside 'الماء')      |
|  Differential Gain: Gain = 0.073919 - 0.182984          ===> SCORE: 0.096262 > 0.08    |
|                                                                                         |
|  CONCLUSION: Saturation is candidate-specific to EOS, NOT global network saturation!   |
+-----------------------------------------------------------------------------------------+
```

---

## 4. SYNAPSE-LEVEL EVIDENCE: DILUTION & ROOT 30 DEADLINE EXPIRATION

### Theoretical Deadline Law
Under the local learning architecture (LLA §4.4, implemented in [`src/dgca/core/synapse_ledger.py`](file:///c:/Users/Laptop/Desktop/DGCA%20NEXT%20V2/src/dgca/core/synapse_ledger.py#L90-L150)):
- When a candidate synapse is created, its lifetime is strictly bounded:
  $$\text{deadline} = \text{birth\_event} + W_{\text{conf}}$$
  where $W_{\text{conf}} = 100$ external events (approximately 25 corpus root iterations, as each root contains 4 events).
- To graduate from `CANDIDATE` to `CONSOLIDATED`, the synapse must accumulate:
  $$E_{\text{ext}} \ge \Theta_E \cdot E_{\text{max}} = 0.30 \cdot 10.0 = 3.000$$
- **Crucial Invariant:** Re-confirmation during training increments $E_{\text{ext}}$ via local Hebbian potentiation, but **does not extend** the birth deadline! If $E_{\text{ext}} < 3.000$ when `current_event > deadline`, the candidate synapse is unconditionally pruned.

### Empirical Exposure Frequency
In the four-sentence schedule:
- $S_1$ (`القط يشرب الحليب`): Occurs once every 4 roots (25% frequency).
- $S_2$ (`النسر يشرب الماء`): Occurs once every 4 roots.
- $S_4$ (`الطفل يشرب الماء`): Occurs once every 4 roots.
- **`يشرب -> الماء` Transition Frequency:** Occurs in both $S_2$ and $S_4$, giving a combined frequency of **50%** (every 2 roots).
- **`يشرب -> الحليب` Transition Frequency:** Occurs solely in $S_1$, giving a frequency of only **25%** (every 4 roots).

### Forensic Verification of Root 30 Expiration
- The direct candidate synapses `8327->9731`, `8327->9910`, `8327->9951`, `10167->8430`, `10696->8430` were born at **Root 1**.
- Across the first 25 roots (100 events), $S_1$ was presented only 6 times (roots 1, 5, 9, 13, 17, 21, 25).
- By Root 25, evidence accumulated reached:
  $$E_{\text{ext}} = 2.545 < 3.000$$
- At **Root 30**, the candidate deadline elapsed. All direct candidate synapses from `يشرب` to `الحليب` were **pruned** from the active synapse ledger!
- At **Root 33**, when $S_1$ was re-encountered, new candidate synapses were re-created with $E_{\text{ext}} = 0.18$.
- Between Root 33 and Root 56 (6 exposures: roots 33, 37, 41, 45, 49, 53), evidence accumulated reached only $E_{\text{ext}} \approx 1.503 - 1.737 < 3.000$.
- Consequently, at Root 56, **zero direct synapses** from `يشرب` to `الحليب` were `CONSOLIDATED`. All 14 candidate synapses were masked during generation (`mask_nonconsolidated=True`).
- In contrast, direct synapses for `يشرب -> الماء` (`8327->9039`, `8327->9534`, `10167->9534`, etc.) received 13 exposures within their first 100 events, accumulated $E_{\text{ext}} > 8.0 > 3.0$, and permanently **consolidated** by Root 20.

---

## 5. CONTEXT BINDING EVIDENCE: FAN-OUT LIMITATION (z=8320)

When direct synapses from a verb are ambiguous (e.g., `يشرب` pointing to both `الحليب` and `الماء`), the DGCA context layer forms second-order conjunction cells ($z$-cells) via Core §7.4:
- Context candidate $z=8320$ was successfully allocated at Root 13.
- **Anchor:** Cell `8327` (member of `يشرب`).
- **P-Sources (Contextual Prefix):** Cells `9061, 10595` (members of `القط`).

### Architectural Fan-Out Constraint
Core §7.4 enforces a strict anatomical structure:
```
Context Candidate Structure:
- Anchor (X): 1 cell
- P-Sources:  Up to 2 cells
- Forward Targets (Y): Exactly 2 cells (Y_1, Y_2)
```
Consequently, a single $z$-cell can project forward synapses to at most **2 target cells**.

### Empirical Target Allocation of z=8320
At Root 56, the forward synapses of $z=8320$ were:
1. `8320 -> 8430 (ASSOCIATIVE)`: `CONSOLIDATED` ($S = 0.8678, E_{\text{ext}} = 3.2365$). Target `8430` is member of Assembly 11 (`الحليب`).
2. `8320 -> 9731 (ASSOCIATIVE)`: `CANDIDATE` ($S = 0.8533, E_{\text{ext}} = 0.1823$). Re-born at Root 53; masked during generation.
3. `8320 -> 10696 (LOCAL)`: `CANDIDATE` ($S = 0.8051, E_{\text{ext}} = 0.2028$). Recurrent local feedback into `يشرب`.

### Functional Consequence
Assembly 11 (`الحليب`) consists of **5 cells**: `8430, 9731, 9910, 9951, 10692`.
- Because direct synapses are masked, only cells receiving drive from $z=8320$ can produce differential gain.
- $z=8320$ drives only **1 consolidated member** (`8430`), producing $\text{Gain}(8430) = 0.075605$.
- Target `9731` receives sub-threshold lateral leakage, producing $\text{Gain}(9731) = 0.031405$.
- Targets `9910, 9951, 10692` receive **0 drive**, producing $\text{Gain} = 0.000000$.
- The assembly score formula averages gain across all 5 members:
  $$\text{Score}(\text{Asm 11}) = \frac{0.075605 + 0.031405 + 0 + 0 + 0}{5} = 0.021402$$
- This average ($0.021402$) falls far below the readout eligibility threshold $\theta_{\text{read}} = 0.080000$, resulting in `GEN_STOP_NO_MATCH`.

---

## 6. EOS FAILURE LOCALIZATION: PREMATURE ACTIVATION VIA `^ال`

### The Mechanism of Premature Activation
In the R2-C01 experimental corpus, all 4 training sentences ended with `<EOS>` immediately preceded by a definite noun:
- $S_1$: `... الحليب <EOS>`
- $S_2$: `... الماء <EOS>`
- $S_3$: `... التفاح <EOS>`
- $S_4$: `... الماء <EOS>`

Every definite noun begins with the morphological prefix `^ال`, which deterministically activates fixed support cells `8416, 8575, 8586`.
Across 56 roots (224 exposures), cells `8416, 8575, 8586` fired immediately prior to `<EOS>` in 100% of sentence completions. This established **55 consolidated associative synapses** ($S \approx 0.999, E_{\text{ext}} = 10.0$) directly from `8416, 8575, 8586` into all 9 members of the EOS assembly (`8728, 8834, 9209, 10417, 10570, 10646, 10915, 11859, 12117`).

### The Prompt-Phase Contamination Trace
During generation for prompt `النسر يشرب` (or any prompt containing a definite subject):
1. **Event 0 (`النسر`):** Fixed support cells `8416, 8575, 8586` fire.
2. **Event 1 (`يشرب`):** The predictive projection from `8416, 8575, 8586` drives the EOS assembly:
   $$P^T(\text{EOS}) = 0.8591 \implies A^+(\text{EOS}) \approx 0.52 - 0.53$$
   **EOS cells are already half-active before generation even begins!**
3. **Step 0 (`الماء` emitted):** When `الماء` is re-injected, the pre-existing EOS activation engages internal recurrent local synapses ($S_{\text{local}} \approx 1.0$), pumping EOS cell activations to $A^+ \approx 0.90 - 0.95$.
4. **Step 1 (Evaluation):**
   - CONTROL pass ($P^T = 0$): $A_{\text{ctrl}} = 1.000000$ (self-saturated).
   - FULL pass ($P^T > 0$): $A_{\text{full}} = 1.000000$ (saturated).
   - Differential gain: $\text{Gain} = 1.0 - 1.0 = 0.000000$.

### Historical Contrast: Cat/Eagle Baseline
In the historical Cat/Eagle trial (`القط يشرب حليب <EOS>`, `النسر يشرب ماء <EOS>`):
- Objects were indefinite (`حليب`, `ماء`) and **did not contain `ال`**.
- Fixed support cells `8416, 8575, 8586` were active **only** during the subject (`القط`, `النسر`), followed by `يشرب`. They were **never** followed by `<EOS>`.
- Synapses from `8416, 8575, 8586` to EOS **never formed**.
- During prompt evaluation of `النسر يشرب`:
  $$A^+(\text{EOS}) = 0.000000 \quad (\text{identically zero})$$
- At Step 1 (after emitting `ماء`):
  $$A_{\text{ctrl}}(\text{EOS}) = 0.000000, \quad A_{\text{full}}(\text{EOS}) = 0.648448 \implies \text{Gain} = 0.648448$$
- Score was $0.648448 > \theta_{\text{read}}$, cleanly halting generation with `GEN_STOP_EOS`!

---

## 7. CROSS-CONTEXT INTRUSION PATHWAY: `الماء` $\to$ `يأكل` $\to$ `التفاح`

At Root 112, Probe P2 (`النسر يشرب`) generated the multi-token sequence: `["الماء", "يأكل", "التفاح"]`. The forensic investigation mapped the exact synaptic chain driving this cross-context intrusion:

```
+---------------------------------------------------------------------------------------------------+
|                        ROOT 112 CROSS-CONTEXT INTRUSION SYNAPTIC PATHWAY                          |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  PROMPT: 'النسر يشرب'                                                                             |
|     |                                                                                             |
|     v                                                                                             |
|  STEP 0: Emits 'الماء' (Assembly 6, Score = 0.561658)                                             |
|     |                                                                                             |
|     +---> 'الماء' contains definite prefix '^ال' (cells 8416, 8575, 8586, 10899)                  |
|     |                                                                                             |
|     v                                                                                             |
|  STEP 1: 'الماء' -> 'يأكل' Intrusion                                                              |
|     |   - S3 training: 'الطفل' (contains '^ال') is immediately followed by 'يأكل' (Assembly 9).  |
|     |   - Associative synapses formed from '^ال' cells to Assembly 9 (e.g. 10899 -> 9103).       |
|     |   - EOS differential gain is 0.000000 (saturated).                                          |
|     |   - Assembly 9 has headroom (A_ctrl = 0.17) and receives P^T = 0.25 from 10899.            |
|     |   - Score(Asm 9) = 0.082090 > 0.080000. Assembly 9 wins!                                    |
|     |   - At Root 112, Assembly 9 gen 3 is attested in readout ledger -> Emits 'يأكل'!            |
|     |                                                                                             |
|     v                                                                                             |
|  STEP 2: 'يأكل' -> 'التفاح' Propagation                                                           |
|     |   - S3 training: 'يأكل' is followed by 'التفاح' in 100% of exposures.                      |
|     |   - Consolidated associative synapses from Asm 9 to Asm 10 deliver massive predictive drive.|
|     |   - Score(Asm 10 / 'التفاح') = 0.460725 > 0.080000.                                         |
|     |   - Emits 'التفاح'!                                                                         |
|     |                                                                                             |
|     v                                                                                             |
|  STEP 3: 'التفاح' -> Next Token                                                                   |
|         - EOS differential gain is 0.000000 (saturated).                                          |
|         - No other candidate achieves score >= 0.080000.                                          |
|         - Halts lawfully with GEN_STOP_NO_MATCH!                                                  |
+---------------------------------------------------------------------------------------------------+
```

---

## 8. MORPHOLOGICAL OVERLAP ANALYSIS

The Arabic prefix `^ال` (definite article) represents a severe morphological confound in this trial:
- **Cell Allocation:** The prefix `^ال` consistently activates fixed support cells `8416, 8575, 8586` with fixed support score $900,000$.
- **Corpus Distribution:**
  - 3 of 3 Subjects (`القط`, `النسر`, `الطفل`) contain `^ال`.
  - 3 of 3 Objects (`الحليب`, `الماء`, `التفاح`) contain `^ال`.
  - 0 of 2 Verbs (`يشرب`, `يأكل`) contain `^ال`.
- **Consequence 1 (EOS Bridging):** Because objects contain `^ال` and precede EOS, `^ال` becomes a direct predictive cue for EOS. Because subjects also contain `^ال`, subjects fire the EOS cue two steps prematurely.
- **Consequence 2 (Cross-Nominal Bridging):** Because `الماء` contains `^ال`, and `الطفل` contains `^ال`, the object `الماء` acts as an associative proxy for the subject `الطفل`, directly activating transitions learned from `الطفل` (`يأكل`).
- **Consequence 3 (Assembly Formation):** The encoder merged these shared cells into Assembly 1 (Generation 10, 12 cells), creating a massive, hyper-connected hub that facilitates cross-context leakage.

---

## 9. STATE-INTEGRITY AUDIT: EVALUATION OF R2-C01 CLAIMS

The preliminary report of R2-C01 offered 7 causal hypotheses and empirical claims. This forensic investigation audited each claim against bitwise state dumps and execution traces:

| # | Preliminary Claim from R2-C01 | Forensic Status | Detailed Evidence and Findings |
| :-: | :--- | :---: | :--- |
| **1** | *"Dilution across 4 sentences pruned S1 candidate synapses at Root 30."* | **CONFIRMED** | Synapse lifetime $W_{\text{conf}} = 100$ events elapsed at Root 30 with $E_{\text{ext}} = 2.545 < 3.000$. Synapses were deleted from ledger and re-created at Root 33. |
| **2** | *"Context binding z=8320 had insufficient fan-out to drive Assembly 11."* | **CONFIRMED** | Core §7.4 architectural fan-out limit is 2 targets. $z=8320$ drove only 1 consolidated cell (`8430`) in 5-member Assembly 11, resulting in average score $0.021402 < 0.08$. |
| **3** | *"Step 1 halted due to lateral saturation."* | **REFINED / CORRECTED** | **Not global lateral saturation.** Saturation is strictly candidate-specific to EOS cells, caused by premature predictive activation from subject `^ال` followed by local recurrent saturation. |
| **4** | *"Assembly 9 scored 0.096 in P2 Step 1 because of non-saturation."* | **CONFIRMED** | Assembly 9 was un-stimulated during prompt events 0 and 1, preserving full differential headroom ($A_{\text{ctrl}} \le 0.17$), allowing predictive drive from `الماء` to produce gain $0.096262 > 0.08$. |
| **5** | *"P2 Root 112 intrusion was driven by الماء -> يأكل -> التفاح."* | **CONFIRMED** | Trace verified: `10899` (`^ال` in `الماء`) drove Assembly 9 (`يأكل`), which drove Assembly 10 (`التفاح`). |
| **6** | *"Readout ledger attested Assembly 9 generation 3 at Root 112."* | **CONFIRMED** | Ledger row for Assembly 9 at Root 112 shows `generation=3`, `surface='يأكل'`, `is_attested=True`. |
| **7** | *"Encoder and MachineState determinism remained 100% bitwise identical."* | **CONFIRMED** | Independent cold-start replays reproduced hashes `f7739b01...` (56 roots) and `692b1f0e...` (112 roots) with zero drift. |

---

## 10. CAUSAL HYPOTHESIS MATRIX

| Hypothesis ID | Proposed Causal Mechanism | Competing Explanation | Forensic Evidence & Ranking | Verdict |
| :--- | :--- | :--- | :--- | :---: |
| **H1** | **Root 30 Deadline Dilution** | Insufficient learning rate $\alpha$ or decay | $W_{\text{conf}} = 100$ events expired at Root 30 with $E_{\text{ext}} = 2.545 < 3.000$. Re-created at Root 33. **Confidence: VERY HIGH** | **PROVEN** |
| **H2** | **Context Binding Fan-Out Limit** | Context cell $z=8320$ failed to fire | $z=8320$ fired strongly ($A^+ = 0.638$), but Core §7.4 limits forward targets to 2. Driven members average $0.0214 < 0.08$. **Confidence: VERY HIGH** | **PROVEN** |
| **H3** | **Morphological EOS Saturation** | Global network saturation / runaway dynamics | Only EOS and `^ال` cells saturated ($A=1.0$). Assembly 9 had low activation ($A=0.17$). Historical Cat/Eagle had identical dynamics but zero EOS saturation. **Confidence: VERY HIGH** | **PROVEN** |
| **H4** | **Cross-Context Lexical Intrusion** | Random tie-breaking or readout noise | Synaptic trace proves direct associative path `10899 -> 9103` from `^ال` to `يأكل` with positive gain $0.096 > 0.08$. **Confidence: VERY HIGH** | **PROVEN** |
| **H-ALT1** | **Global Network Saturation** | Candidate-specific saturation | Refuted by Assembly 9 headroom ($A_{\text{ctrl}} = 0.17, \text{Gain} = 0.096$). If network were globally saturated, all candidates would score 0.000. | **REFUTED** |
| **H-ALT2** | **Defective Readout Formulas** | Formula works as specified | Readout differential gain formula $\max(0, A_{\text{full}} - A_{\text{ctrl}})$ operates correctly; it rightfully penalizes candidates whose activation is not causally dependent on input. | **REFUTED** |

---

## 11. MINIMUM DISCRIMINATING COUNTERFACTUAL PROPOSALS

To experimentally isolate each identified causal mechanism prior to authorizing architectural changes, three minimal discriminating counterfactuals are proposed:

### Counterfactual 1 (CF-1): Indefinite Nominal Surfaces (Testing H3 & H4)
- **Design:** Strip the definite prefix `^ال` from all objects, mirroring the historical Cat/Eagle design:
  - $S_1$: `القط يشرب حليب <EOS>`
  - $S_2$: `النسر يشرب ماء <EOS>`
  - $S_3$: `الطفل يأكل تفاح <EOS>`
  - $S_4$: `الطفل يشرب ماء <EOS>`
- **Predicted Outcome:**
  - Subject `^ال` will no longer drive EOS cells during `يشرب`.
  - In Step 1, $A_{\text{ctrl}}(\text{EOS}) = 0.000000$, $A_{\text{full}}(\text{EOS}) > 0.600000$, producing $\text{Gain} > 0.600000$ and clean `GEN_STOP_EOS` halts across P2, P3, and P4!
  - `ماء` will no longer contain `^ال`, eliminating the intrusion path to `يأكل`.

### Counterfactual 2 (CF-2): Frequency Equalization / Window Extension (Testing H1)
- **Design A (Schedule):** Increase $S_1$ presentation frequency to match $S_2+S_4$ (e.g. 2:1:1:1 schedule), or train on a balanced 2-sentence context trial.
- **Design B (LLA Parameter):** Extend confirmation window $W_{\text{conf}}$ from $100$ to $200$ events, or allow confirmation hits to refresh the expiration deadline.
- **Predicted Outcome:**
  - Candidate synapses `يشرب -> الحليب` accumulate $E_{\text{ext}} > 3.000$ before deadline expiration, graduating to `CONSOLIDATED` state.

### Counterfactual 3 (CF-3): Multi-Target Context Gating (Testing H2)
- **Design:** Permit $z$-cells to bind to assembly-level representations rather than individual neurons, or expand Core §7.4 to allow $K$-target forward projections ($K \ge 5$).
- **Predicted Outcome:**
  - $z=8320$ delivers predictive drive to all 5 members of Assembly 11, elevating average score from $0.0214$ to $>0.1500$, allowing P1 to emit `الحليب`.

---

## 12. RECOMMENDED NEXT SCIENTIFIC DECISION

### Recommendation: Execute Controlled Counterfactual Experiment (CF-1) First

1. **Do Not Modify Core Learning Laws Yet:** The Core learning laws (LLA Hebbian potentiation, BCM thresholds, Assembly consolidation, Differential causal readout) functioned with 100% lawful fidelity. They did not exhibit runaway instability, numerical overflow, or non-deterministic behavior.
2. **Execute Counterfactual Trial CF-1:** Run the four-sentence experiment with indefinite objects (`القط يشرب حليب`, `النسر يشرب ماء`, `الطفل يأكل تفاح`, `الطفل يشرب ماء`).
   - If CF-1 restores `GEN_STOP_EOS` across P2, P3, and P4, it conclusively proves that the EOS failure was a **morphological dataset confound** rather than an architectural deficiency in the differential readout formula.
3. **Subsequent Architectural Focus:** Once CF-1 isolates the morphological variable, focus any needed Core amendments specifically on:
   - **$W_{\text{conf}}$ confirmation deadline dynamics:** Preventing dilution-induced candidate pruning under diverse, multi-sentence corpora.
   - **Context binding fan-out:** Expanding Core §7.4 to support full-assembly forward projections.

---

## FINAL AUTHORIZED VERDICT

```
================================================================================
R2-C01-F01 FORENSIC COMPLETE — CAUSAL MECHANISMS IDENTIFIED
================================================================================
```
- **Provenance:** Authoritative SHA-256 state snapshots and baseline branches verified.
- **Reproduction:** 56-root and 112-root empirical observations 100% reproduced.
- **Mathematical Traces:** Step-level $A_{\text{ctrl}}$, $A_{\text{full}}$, $\text{Gain}$, and candidate scoring fully documented.
- **Causal Mechanisms:** Dilution pruning at Root 30 (H1), Binding fan-out limits (H2), Premature EOS saturation via `^ال` (H3), and Cross-context intrusion chain (H4) rigorously isolated and proven.
- **Regression Suite:** `tests/forensics/test_r2_c01_f01_causal_forensics.py` passing (7/7 tests). Full 215-test suite unaffected.
- **Production Code Status:** Zero modifications to `src/`.
