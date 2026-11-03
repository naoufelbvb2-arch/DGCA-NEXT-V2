"""Apply EGCP E1 generic prediction preservation changes to src/dgca."""

from __future__ import annotations
import os

def patch_state_py():
    path = "src/dgca/core/state.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "class EGCPMode(StrEnum):" in content:
        print("state.py already patched")
        return

    # 1. Add EGCPMode
    target1 = '    LEARN = "LEARN"\n    REPLAY = "REPLAY"\n    RETRIEVE = "RETRIEVE"\n    GENERATE = "GENERATE"'
    repl1 = target1 + '\n\n\nclass EGCPMode(StrEnum):\n    """EGCP operational mode (DGCA-NEXT-V2-EGCP-SPEC §2.1).\n\n    OFF: frozen native Core/LLA behavior with exact historical mu and no EGCP state.\n    E1_PRESERVE_GENERIC: native contextual activation and positive links;\n        experimental generic associative drive preservation (mu_effective = 0).\n    """\n\n    OFF = "OFF"\n    E1_PRESERVE_GENERIC = "E1_PRESERVE_GENERIC"'
    assert target1 in content, "target1 not found in state.py"
    content = content.replace(target1, repl1, 1)

    # 2. Add egcp_mode to MachineState.__init__ and clone()
    target2 = """    def __init__(
        self,
        w: WState | None = None,
        r: RState | None = None,
        h_slow: HSlowState | None = None,
    ) -> None:
        self.W: WState = w if w is not None else WState()
        self.R: RState = r if r is not None else RState()
        self.H_slow: HSlowState = h_slow if h_slow is not None else HSlowState()

    def clone(self) -> MachineState:
        \"\"\"Create a complete isolated deep copy of (W, R, H_slow).\"\"\"
        return MachineState(
            w=self.W.clone(),
            r=self.R.clone(),
            h_slow=self.H_slow.clone(),
        )"""

    repl2 = """    def __init__(
        self,
        w: WState | None = None,
        r: RState | None = None,
        h_slow: HSlowState | None = None,
        egcp_mode: EGCPMode | str = EGCPMode.OFF,
    ) -> None:
        self.W: WState = w if w is not None else WState()
        self.R: RState = r if r is not None else RState()
        self.H_slow: HSlowState = h_slow if h_slow is not None else HSlowState()
        self.egcp_mode: EGCPMode = EGCPMode(egcp_mode)

    def clone(self) -> MachineState:
        \"\"\"Create a complete isolated deep copy of (W, R, H_slow).\"\"\"
        return MachineState(
            w=self.W.clone(),
            r=self.R.clone(),
            h_slow=self.H_slow.clone(),
            egcp_mode=self.egcp_mode,
        )"""
    assert target2 in content, "target2 not found in state.py"
    content = content.replace(target2, repl2, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched state.py")


def patch_context_gate_py():
    path = "src/dgca/core/context_gate.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "if EGCPMode(egcp_mode) == EGCPMode.E1_PRESERVE_GENERIC:" in content:
        print("context_gate.py already patched")
        return

    # Import EGCPMode
    target_import = "from dgca.core.state import ("
    repl_import = "from dgca.core.state import (\n    EGCPMode,"
    assert target_import in content, "target_import not found in context_gate.py"
    content = content.replace(target_import, repl_import, 1)

    # Update compute_directed_mu_ij
    target_fn = """def compute_directed_mu_ij(
    source_id: int,
    target_id: int,
    mu_prev_source_mask: dict[int, int],
    w: WState,
) -> int:
    \"\"\"Compute RC4.1 target-scoped temporal mask mu_ij(t-1) = mu_i(t-1) * 1[not ContextTarget(j, t)] (Core §5.2).

    Temporarily masks generic outgoing ASSOCIATIVE contribution to ordinary/non-contextual targets,
    while preserving mu_ij = 0 for every legitimate gated contextual target (including incomplete
    candidates and COMPLETE depth > 1 descendants).
    \"\"\"
    mu_i = mu_prev_source_mask.get(source_id, 0)
    if mu_i == 0:
        return 0
    if w.is_context_target(target_id):
        return 0
    return 1"""

    repl_fn = """def compute_directed_mu_ij(
    source_id: int,
    target_id: int,
    mu_prev_source_mask: dict[int, int],
    w: WState,
    *,
    egcp_mode: EGCPMode | str = EGCPMode.OFF,
) -> int:
    \"\"\"Compute RC4.1 target-scoped temporal mask mu_ij(t-1) = mu_i(t-1) * 1[not ContextTarget(j, t)] (Core §5.2).

    Under EGCP E1 (egcp_mode == EGCPMode.E1_PRESERVE_GENERIC):
    Effective directed suppression mask is 0 (generic ASSOCIATIVE attenuation disabled).
    Under legacy/default OFF (egcp_mode == EGCPMode.OFF):
    Retains exact frozen original mu_ij(t-1).
    \"\"\"
    if EGCPMode(egcp_mode) == EGCPMode.E1_PRESERVE_GENERIC:
        return 0

    mu_i = mu_prev_source_mask.get(source_id, 0)
    if mu_i == 0:
        return 0
    if w.is_context_target(target_id):
        return 0
    return 1"""
    assert target_fn in content, "target_fn not found in context_gate.py"
    content = content.replace(target_fn, repl_fn, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched context_gate.py")


def patch_dynamics_py():
    path = "src/dgca/core/dynamics.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "eff_egcp_mode = getattr(state, \"egcp_mode\", EGCPMode.OFF)" in content:
        print("dynamics.py already patched")
        return

    # Import EGCPMode
    target_import = "from dgca.core.state import ("
    repl_import = "from dgca.core.state import (\n    EGCPMode,"
    assert target_import in content, "target_import not found in dynamics.py"
    content = content.replace(target_import, repl_import, 1)

    # In compute_next_step_temporal_drive, accept egcp_mode and pass to compute_directed_mu_ij
    target_sig = """def compute_next_step_temporal_drive(
    state: MachineState,
    *,
    f_step_prev: frozenset[int],
    a_prev_by_cell: dict[int, float],
    mu_prev_source_mask: dict[int, int],
    mask_nonconsolidated: bool = False,
) -> tuple[dict[int, float], dict[int, list[tuple[int, float]]]]"""

    repl_sig = """def compute_next_step_temporal_drive(
    state: MachineState,
    *,
    f_step_prev: frozenset[int],
    a_prev_by_cell: dict[int, float],
    mu_prev_source_mask: dict[int, int],
    mask_nonconsolidated: bool = False,
    egcp_mode: EGCPMode | str | None = None,
) -> tuple[dict[int, float], dict[int, list[tuple[int, float]]]]"""
    assert target_sig in content, "target_sig not found in dynamics.py"
    content = content.replace(target_sig, repl_sig, 1)

    target_body = """    w = state.W
    contribs_by_target: dict[int, list[tuple[int, int, tuple[int, int, SynapseScope], float]]] = {}
    source_pairs_by_target: dict[int, list[tuple[int, float]]] = {}

    for src_id in sorted(f_step_prev):
        a_src = a_prev_by_cell.get(src_id, 0.0)
        if a_src <= 0.0:
            continue
        for key in w.outgoing_by_source.get(src_id, ()):
            _, tgt_id, scope = key
            if scope != SynapseScope.ASSOCIATIVE:
                continue
            syn = w.synapses[key]
            if mask_nonconsolidated and syn.state != SynapseState.CONSOLIDATED:
                continue
            q_val = syn.Q
            if q_val <= 0.0:
                continue
            mu_ij = compute_directed_mu_ij(src_id, tgt_id, mu_prev_source_mask, w)"""

    repl_body = """    w = state.W
    eff_egcp_mode = getattr(state, "egcp_mode", EGCPMode.OFF) if egcp_mode is None else EGCPMode(egcp_mode)
    contribs_by_target: dict[int, list[tuple[int, int, tuple[int, int, SynapseScope], float]]] = {}
    source_pairs_by_target: dict[int, list[tuple[int, float]]] = {}

    for src_id in sorted(f_step_prev):
        a_src = a_prev_by_cell.get(src_id, 0.0)
        if a_src <= 0.0:
            continue
        for key in w.outgoing_by_source.get(src_id, ()):
            _, tgt_id, scope = key
            if scope != SynapseScope.ASSOCIATIVE:
                continue
            syn = w.synapses[key]
            if mask_nonconsolidated and syn.state != SynapseState.CONSOLIDATED:
                continue
            q_val = syn.Q
            if q_val <= 0.0:
                continue
            mu_ij = compute_directed_mu_ij(src_id, tgt_id, mu_prev_source_mask, w, egcp_mode=eff_egcp_mode)"""
    assert target_body in content, "target_body not found in dynamics.py"
    content = content.replace(target_body, repl_body, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched dynamics.py")


def patch_readout_py():
    path = "src/dgca/core/readout.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "scratch_full.egcp_mode = EGCPMode(egcp_mode)" in content:
        print("readout.py already patched")
        return

    # Import EGCPMode
    target_import = "from dgca.core.state import ("
    repl_import = "from dgca.core.state import (\n    EGCPMode,"
    assert target_import in content, "target_import not found in readout.py"
    content = content.replace(target_import, repl_import, 1)

    target_fn = """def evaluate_full_vs_control_readout(
    state: MachineState,
    *,
    theta_read: float = THETA_READ,
    m_read: float = M_READ,
) -> ReadoutEvaluationResult:"""

    repl_fn = """def evaluate_full_vs_control_readout(
    state: MachineState,
    *,
    theta_read: float = THETA_READ,
    m_read: float = M_READ,
    egcp_mode: EGCPMode | str | None = None,
) -> ReadoutEvaluationResult:"""
    assert target_fn in content, "target_fn not found in readout.py"
    content = content.replace(target_fn, repl_fn, 1)

    target_clones = """    scratch_full = state.clone()
    scratch_ctrl = state.clone()"""

    repl_clones = """    scratch_full = state.clone()
    scratch_ctrl = state.clone()
    if egcp_mode is not None:
        scratch_full.egcp_mode = EGCPMode(egcp_mode)
        scratch_ctrl.egcp_mode = EGCPMode(egcp_mode)"""
    assert target_clones in content, "target_clones not found in readout.py"
    content = content.replace(target_clones, repl_clones, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched readout.py")


def patch_generator_py():
    path = "src/dgca/core/generator.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "egcp_mode=scratch_state.egcp_mode" in content:
        print("generator.py already patched")
        return

    # Import EGCPMode
    target_import = "from dgca.core.state import ExecutionMode, MachineState"
    repl_import = "from dgca.core.state import EGCPMode, ExecutionMode, MachineState"
    if target_import in content:
        content = content.replace(target_import, repl_import, 1)

    target_fn = """def generate_episode(
    state: MachineState,
    prompt_events: Sequence[CoreEventPayloadV1],
    ledger: SurfaceReadoutLedgerV1,
    *,
    max_steps: int = T_GEN_MAX,
    theta_read: float = THETA_READ,
    m_read: float = M_READ,
    override_winner_generation_by_step: dict[int, int] | None = None,
) -> GenerateEpisodeResult:"""

    repl_fn = """def generate_episode(
    state: MachineState,
    prompt_events: Sequence[CoreEventPayloadV1],
    ledger: SurfaceReadoutLedgerV1,
    *,
    max_steps: int = T_GEN_MAX,
    theta_read: float = THETA_READ,
    m_read: float = M_READ,
    override_winner_generation_by_step: dict[int, int] | None = None,
    egcp_mode: EGCPMode | str | None = None,
) -> GenerateEpisodeResult:"""
    if target_fn in content:
        content = content.replace(target_fn, repl_fn, 1)

    target_scratch = """    scratch_state = state.clone()
    scratch_state.R.reset_cold()"""

    repl_scratch = """    scratch_state = state.clone()
    scratch_state.R.reset_cold()
    if egcp_mode is not None:
        scratch_state.egcp_mode = EGCPMode(egcp_mode)"""
    assert target_scratch in content, "target_scratch not found in generator.py"
    content = content.replace(target_scratch, repl_scratch, 1)

    target_readout_call = """        readout_res = evaluate_full_vs_control_readout(
            scratch_state,
            theta_read=theta_read,
            m_read=m_read,
        )"""

    repl_readout_call = """        readout_res = evaluate_full_vs_control_readout(
            scratch_state,
            theta_read=theta_read,
            m_read=m_read,
            egcp_mode=scratch_state.egcp_mode,
        )"""
    assert target_readout_call in content, "target_readout_call not found in generator.py"
    content = content.replace(target_readout_call, repl_readout_call, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched generator.py")


def patch_exposure_tx_py():
    path = "src/dgca/lifecycle/exposure_tx.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "def set_egcp_mode(self, mode: EGCPMode | str) -> None:" in content:
        print("exposure_tx.py already patched")
        return

    # Import EGCPMode
    target_import = "from dgca.core.state import ExecutionMode, HSlowState, MachineState, WState"
    repl_import = "from dgca.core.state import EGCPMode, ExecutionMode, HSlowState, MachineState, WState"
    assert target_import in content, "target_import not found in exposure_tx.py"
    content = content.replace(target_import, repl_import, 1)

    # In ExposureTransactionManager.__init__
    target_init = """        enable_birth_time_grow: bool = False,
        enable_cross_clique_diversification: bool = False,
    ) -> None:"""

    repl_init = """        enable_birth_time_grow: bool = False,
        enable_cross_clique_diversification: bool = False,
        egcp_mode: EGCPMode | str = EGCPMode.OFF,
    ) -> None:"""
    assert target_init in content, "target_init not found in exposure_tx.py"
    content = content.replace(target_init, repl_init, 1)

    target_init_body = """        self.enable_birth_time_grow: bool = enable_birth_time_grow
        self.enable_cross_clique_diversification: bool = enable_cross_clique_diversification"""

    repl_init_body = """        self.enable_birth_time_grow: bool = enable_birth_time_grow
        self.enable_cross_clique_diversification: bool = enable_cross_clique_diversification
        self.egcp_mode: EGCPMode = EGCPMode(egcp_mode)
        self.state.egcp_mode = self.egcp_mode"""
    assert target_init_body in content, "target_init_body not found in exposure_tx.py"
    content = content.replace(target_init_body, repl_init_body, 1)

    # Add set_egcp_mode method
    target_method = """    def begin_exposure(self, exposure_id: int) -> OpenExposureJournal:"""

    repl_method = """    def set_egcp_mode(self, mode: EGCPMode | str) -> None:
        \"\"\"Configure EGCP mode at exposure boundary. Switching during OPEN root is forbidden.\"\"\"
        if self.open_journal is not None and self.open_journal.status == ExposureStatus.OPEN:
            raise ValueError("Switching EGCP_MODE during an OPEN exposure is forbidden.")
        self.egcp_mode = EGCPMode(mode)
        self.state.egcp_mode = self.egcp_mode

    def begin_exposure(self, exposure_id: int) -> OpenExposureJournal:"""
    assert target_method in content, "target_method not found in exposure_tx.py"
    content = content.replace(target_method, repl_method, 1)

    target_begin = """        # FIFR-B06 LAB POLICY A: capture immutable H_slow_BEGIN before any root-local adaptation
        h_begin = self.state.H_slow.clone()"""

    repl_begin = """        # FIFR-B06 LAB POLICY A: capture immutable H_slow_BEGIN before any root-local adaptation
        self.state.egcp_mode = self.egcp_mode
        h_begin = self.state.H_slow.clone()"""
    assert target_begin in content, "target_begin not found in exposure_tx.py"
    content = content.replace(target_begin, repl_begin, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched exposure_tx.py")


def patch_init_py():
    path = "src/dgca/core/__init__.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    target_imp = "from dgca.core.state import ("
    repl_imp = "from dgca.core.state import (\n    EGCPMode,"
    assert target_imp in content, "target_imp not found in __init__.py"
    content = content.replace(target_imp, repl_imp, 1)

    target_all = '    "ExecutionMode",'
    repl_all = '    "EGCPMode",\n    "ExecutionMode",'
    assert target_all in content, "target_all not found in __init__.py"
    content = content.replace(target_all, repl_all, 1)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Patched __init__.py")


if __name__ == "__main__":
    patch_state_py()
    patch_context_gate_py()
    patch_dynamics_py()
    patch_readout_py()
    patch_generator_py()
    patch_exposure_tx_py()
    patch_init_py()
    print("All E1 patches applied successfully!")
