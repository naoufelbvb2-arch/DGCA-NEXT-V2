"""State Partition S_t = (W_t, R_t, H_t^slow), Mode Contracts, and R_cold Reset.

Normative references:
- DGCA_CORE_RC4_1.md §4 (State partition and modes)
- DGCA_CORE_RC4_1.md §6 & §6.1 (Temporal-frontier/provenance & typed physical support)
- DGCA_CORE_RC4_1.md §7.4–§7.7 (Candidate descriptors, StableBindingV2/V3, OwnerProfileV1/V2)
- DGCA_CORE_RC4_1.md §11 (Cold reset, snapshots, serialization, and reproducibility)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region, WitnessSourceKind
from dgca.core.anatomy import (
    CROSS_OUTGOING_BUDGET_B_I_X,
    DEFAULT_OUTGOING_BUDGET_B_I,
    DumbCellView,
    G_INIT,
    H_CONTEXT,
    REGION_PARAMS,
    RHO_CELL_TARGET,
    Synapse,
    SynapseKey,
    SynapseScope,
    SynapseState,
)
from dgca.core.latent_index import LatentNeighborhoodTable
from dgca.core.sic_v1 import CellAddress
from dgca.encoder.envelope import EventOrigin


class ExecutionMode(StrEnum):
    """Execution mode of the DGCA v2 machine (Core §4)."""

    LEARN = "LEARN"
    REPLAY = "REPLAY"
    RETRIEVE = "RETRIEVE"
    GENERATE = "GENERATE"


class ContributionLane(StrEnum):
    """Tagged causal contribution lanes per event (Core §6, LLA §2.2)."""

    DIRECT_OBSERVED = "DIRECT_OBSERVED"
    SPATIALLY_COMPLETED = "SPATIALLY_COMPLETED"
    PREDICTED = "PREDICTED"
    CONTEXT_MATCHED = "CONTEXT_MATCHED"
    BOOTSTRAPPED = "BOOTSTRAPPED"
    RESIDUAL = "RESIDUAL"
    ATTRACTOR = "ATTRACTOR"
    DERIVED_EXTERNAL_CONTEXT = "DERIVED_EXTERNAL_CONTEXT"
    DERIVED_RUNTIME_CONTEXT = "DERIVED_RUNTIME_CONTEXT"
    INTERNAL_SELECTED = "INTERNAL_SELECTED"
    READ_ONLY_OBSERVED = "READ_ONLY_OBSERVED"


class CandidatePhase(StrEnum):
    """Contextual candidate probation state machine phases (Core §7.4.1)."""

    WIRED = "WIRED"
    PROBE_INCOMING = "PROBE_INCOMING"
    LEARN_OUTCOME = "LEARN_OUTCOME"
    NO_PROBE_TEST = "NO_PROBE_TEST"
    COMPLETE = "COMPLETE"
    FAILED_OR_EXPIRED = "FAILED_OR_EXPIRED"


class BindingStatus(StrEnum):
    """Validity status of a contextual descriptor or StableBinding (Core §7.6)."""

    ACTIVE = "ACTIVE"
    STALE = "STALE"


class OwnerState(StrEnum):
    """Lifecycle state of an OwnerProfile in the persistent registry (Core §7.7)."""

    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    EXPIRED_VALIDATED = "EXPIRED_VALIDATED"
    EXPIRED_EMPTY = "EXPIRED_EMPTY"
    STALE = "STALE"


class AssemblyStatus(StrEnum):
    """Lifecycle status of a structural Assembly (Core §2.0)."""

    LIVE = "LIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(slots=True)
class Assembly:
    """Identity-bearing structural Assembly in W (Core §2.0)."""

    assembly_id: int
    region: Region
    member_cell_ids: tuple[int, ...]
    structural_generation: int = 1
    birth_close_serial: int = 0
    last_mutation_close_serial: int = 0
    last_merge_split_close_serial: int | None = None
    status: AssemblyStatus = AssemblyStatus.LIVE

    def __post_init__(self) -> None:
        self.member_cell_ids = tuple(sorted(set(self.member_cell_ids)))

    def clone(self) -> Assembly:
        return Assembly(
            assembly_id=self.assembly_id,
            region=self.region,
            member_cell_ids=self.member_cell_ids,
            structural_generation=self.structural_generation,
            birth_close_serial=self.birth_close_serial,
            last_mutation_close_serial=self.last_mutation_close_serial,
            last_merge_split_close_serial=self.last_merge_split_close_serial,
            status=self.status,
        )


@dataclass(frozen=True, slots=True)
class ParentContextRef:
    """Immutable parent contextual binding reference for depth > 1 hierarchy (Core §6.1, LLA §6.6)."""

    parent_z_cell_id: int
    parent_anchor_id: int
    parent_owner_seq: int
    parent_binding_generation: int
    depth: int


@dataclass(slots=True)
class ContextCandidateDescriptor:
    """Temporary structural descriptor for an incomplete contextual candidate z (Core §5.1, §7.4)."""

    z_cell_id: int
    anchor_id: int
    owner_seq: int
    p_sources: tuple[int, int]
    c_sources: tuple[int, int]
    y_targets: tuple[int, int]
    l_z_q6: int
    u_z_q6: int
    tau_ctx_q6: int
    anchor_source_set: frozenset[int]
    phase: CandidatePhase = CandidatePhase.WIRED
    probe_matches: int = 0
    consolidation_matches: int = 0
    age_events: int = 0
    admitted_root_id: int = 0
    depth: int = 1
    p_source_kinds: tuple[WitnessSourceKind, WitnessSourceKind] = (
        WitnessSourceKind.DIRECT,
        WitnessSourceKind.DIRECT,
    )
    parent_refs: dict[int, ParentContextRef] = field(default_factory=dict)
    status: BindingStatus = BindingStatus.ACTIVE

    @property
    def owner_id(self) -> tuple[int, int]:
        return (self.anchor_id, self.owner_seq)

    @property
    def reserved_synapse_keys(self) -> set[SynapseKey]:
        """All 6 intended directed synapse keys for the 2-P / 2-C / 2-Y roles."""
        keys: set[SynapseKey] = set()
        for p in self.p_sources:
            keys.add((p, self.z_cell_id, SynapseScope.ASSOCIATIVE))
        for c in self.c_sources:
            keys.add((c, self.z_cell_id, SynapseScope.LOCAL))
        for y in self.y_targets:
            keys.add((self.z_cell_id, y, SynapseScope.ASSOCIATIVE))
        return keys

    def clone(self) -> ContextCandidateDescriptor:
        return ContextCandidateDescriptor(
            z_cell_id=self.z_cell_id,
            anchor_id=self.anchor_id,
            owner_seq=self.owner_seq,
            p_sources=self.p_sources,
            c_sources=self.c_sources,
            y_targets=self.y_targets,
            l_z_q6=self.l_z_q6,
            u_z_q6=self.u_z_q6,
            tau_ctx_q6=self.tau_ctx_q6,
            anchor_source_set=self.anchor_source_set,
            phase=self.phase,
            probe_matches=self.probe_matches,
            consolidation_matches=self.consolidation_matches,
            age_events=self.age_events,
            admitted_root_id=self.admitted_root_id,
            depth=self.depth,
            p_source_kinds=self.p_source_kinds,
            parent_refs=dict(self.parent_refs),
            status=self.status,
        )


@dataclass(slots=True)
class StableBinding:
    """Permanent post-graduation binding StableBindingV2 (depth=1) or StableBindingV3 (depth>1) (Core §7.6)."""

    schema_version: int
    z_cell_id: int
    anchor_id: int
    owner_seq: int
    binding_generation: int
    p_keys: tuple[SynapseKey, SynapseKey]
    l_z_q6: int
    u_z_q6: int
    tau_ctx_q6: int
    c_keys: tuple[SynapseKey, ...]
    y_keys: tuple[SynapseKey, ...]
    anchor_source_set: frozenset[int]
    status: BindingStatus = BindingStatus.ACTIVE
    depth: int = 1
    p_source_kinds: tuple[WitnessSourceKind, WitnessSourceKind] = (
        WitnessSourceKind.DIRECT,
        WitnessSourceKind.DIRECT,
    )
    parent_refs: dict[int, ParentContextRef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version not in (2, 3):
            raise DGCAError(
                StatusCode.UNSUPPORTED_BINDING_SCHEMA,
                f"StableBinding schema_version must be 2 or 3, got {self.schema_version}",
            )
        if self.depth > 1 and self.schema_version != 3:
            raise DGCAError(
                StatusCode.UNSUPPORTED_BINDING_SCHEMA,
                "Depth > 1 contextual binding requires StableBindingV3 (schema_version=3)",
            )
        if self.depth == 1 and self.schema_version != 2:
            raise DGCAError(
                StatusCode.UNSUPPORTED_BINDING_SCHEMA,
                "Depth = 1 contextual binding requires StableBindingV2 (schema_version=2)",
            )

    @property
    def owner_id(self) -> tuple[int, int]:
        return (self.anchor_id, self.owner_seq)

    @property
    def p_sources(self) -> tuple[int, int]:
        return (self.p_keys[0][0], self.p_keys[1][0])

    @property
    def c_sources(self) -> tuple[int, ...]:
        return tuple(k[0] for k in self.c_keys)

    @property
    def y_targets(self) -> tuple[int, ...]:
        return tuple(k[1] for k in self.y_keys)

    def clone(self) -> StableBinding:
        return StableBinding(
            schema_version=self.schema_version,
            z_cell_id=self.z_cell_id,
            anchor_id=self.anchor_id,
            owner_seq=self.owner_seq,
            binding_generation=self.binding_generation,
            p_keys=self.p_keys,
            l_z_q6=self.l_z_q6,
            u_z_q6=self.u_z_q6,
            tau_ctx_q6=self.tau_ctx_q6,
            c_keys=self.c_keys,
            y_keys=self.y_keys,
            anchor_source_set=self.anchor_source_set,
            status=self.status,
            depth=self.depth,
            p_source_kinds=self.p_source_kinds,
            parent_refs=dict(self.parent_refs),
        )


@dataclass(frozen=True, slots=True)
class ContributionRecord:
    """Single tagged causal contribution lane entry for an event (Core §6, LLA §2.2)."""

    target_cell_id: int
    source_cell_id: int | None
    event_order: int
    lane: ContributionLane
    nonnegative_support: float
    witness_roots: tuple[int, ...] = ()
    step_id: int = 0


@dataclass(frozen=True, slots=True)
class TypedSupportRecord:
    """Per-cell, per-event immutable typed physical support (Core §6.1)."""

    cell_id: int
    event_order: int
    origin_kind: str
    o_train: float
    o_runtime: float
    q6_train: int
    q6_runtime: int
    depth: int = 0
    owner_id: tuple[int, int] | None = None
    binding_generation: int | None = None
    parent_proof_verified: bool = True


@dataclass(frozen=True, slots=True)
class EligibilityEntry:
    """Canonical temporal learning eligibility trace entry (LLA §3)."""

    cell_id: int
    a_eligible: float
    a_pass1: float
    in_e1_frontier: bool
    in_f_step: bool
    in_l_frontier: bool
    in_lx_frontier: bool
    event_order: int
    exposure_id: int | None
    origin_kind: str
    witness_id: tuple[int | None, int, bytes] | None


@dataclass(slots=True)
class AttractorRuntimeState:
    """Active CONTEXT_ATTRACTOR state hosted by a qualified Assembly in R (Core §2.1)."""

    assembly_id: int
    strength_c: float
    age: int = 0
    err: float = 0.0

    def clone(self) -> AttractorRuntimeState:
        return AttractorRuntimeState(
            assembly_id=self.assembly_id,
            strength_c=self.strength_c,
            age=self.age,
            err=self.err,
        )


class WState:
    """Durable structural graph state W_t (Core §4).

    Holds committed cells, 24-slot latent neighborhoods, synapses, Assemblies,
    contextual candidates, StableBindings, and capacity ledgers.
    """

    def __init__(
        self,
        *,
        outgoing_budget_b_i: int = DEFAULT_OUTGOING_BUDGET_B_I,
        cross_outgoing_budget_b_i_x: int = CROSS_OUTGOING_BUDGET_B_I_X,
    ) -> None:
        self.outgoing_budget_b_i: int = outgoing_budget_b_i
        self.cross_outgoing_budget_b_i_x: int = cross_outgoing_budget_b_i_x

        # cell_id -> committed_event_clock
        self.committed_cells: dict[int, int] = {}
        # cell_id -> last_referenced_event_clock
        self.last_referenced_event: dict[int, int] = {}

        self.latent_table: LatentNeighborhoodTable = LatentNeighborhoodTable()

        # Directed synapses keyed by (source_id, target_id, scope)
        self.synapses: dict[SynapseKey, Synapse] = {}
        self.outgoing_by_source: dict[int, set[SynapseKey]] = {}
        self.incoming_by_target: dict[int, set[SynapseKey]] = {}

        # Contextual candidate reservations: candidate z_cell_id -> set of reserved SynapseKeys
        self.reserved_keys_by_candidate: dict[int, set[SynapseKey]] = {}

        # Assemblies: assembly_id -> Assembly
        self.assemblies: dict[int, Assembly] = {}
        self.next_assembly_id: int = 1
        self.assemblies_by_member: dict[int, set[int]] = {}

        # Contextual candidates and graduated StableBindings (keyed by z_cell_id)
        self.context_candidates: dict[int, ContextCandidateDescriptor] = {}
        self.stable_bindings: dict[int, StableBinding] = {}

        # Persistent owner governance (Core §7.7, LLA §6.5):
        # anchor_id -> list of OwnerProfile ordered by owner_seq
        self.owner_profiles_by_anchor: dict[int, list[object]] = {}
        # anchor_id -> next never-reused owner_sequence_number (starts at 1)
        self.next_owner_seq_by_anchor: dict[int, int] = {}

        # Bounded contrast ledger (Core §7.1, LLA §6.1):
        # anchor_id -> list of ContrastEpisodeRecord (max 16 per anchor, TTL 2000 ext events)
        self.contrast_episodes_by_anchor: dict[int, list[object]] = {}

        # Monotonic counters
        self.completed_roots_high_watermark: int = 0
        self.completed_external_events_count: int = 0
        self.global_event_clock: int = 0
        self.close_serial: int = 0

    def clone(self) -> WState:
        """Return an isolated deep copy of WState for shadow transactions or scratch tests."""
        copy_w = WState(
            outgoing_budget_b_i=self.outgoing_budget_b_i,
            cross_outgoing_budget_b_i_x=self.cross_outgoing_budget_b_i_x,
        )
        copy_w.committed_cells = dict(self.committed_cells)
        copy_w.last_referenced_event = dict(self.last_referenced_event)
        copy_w.latent_table = self.latent_table.clone()

        for key, syn in self.synapses.items():
            copy_w.add_or_replace_synapse(syn.clone())

        copy_w.reserved_keys_by_candidate = {
            z_id: set(keys) for z_id, keys in self.reserved_keys_by_candidate.items()
        }
        copy_w.assemblies = {
            aid: asm.clone() for aid, asm in self.assemblies.items()
        }
        copy_w.next_assembly_id = self.next_assembly_id
        copy_w.assemblies_by_member = {
            cid: set(aids) for cid, aids in self.assemblies_by_member.items()
        }
        copy_w.context_candidates = {
            z_id: desc.clone() for z_id, desc in self.context_candidates.items()
        }
        copy_w.stable_bindings = {
            z_id: bind.clone() for z_id, bind in self.stable_bindings.items()
        }
        copy_w.owner_profiles_by_anchor = {
            aid: [prof.clone() if hasattr(prof, "clone") else prof for prof in profs]
            for aid, profs in self.owner_profiles_by_anchor.items()
        }
        copy_w.next_owner_seq_by_anchor = dict(self.next_owner_seq_by_anchor)
        copy_w.contrast_episodes_by_anchor = {
            aid: [ep.clone() if hasattr(ep, "clone") else ep for ep in eps]
            for aid, eps in self.contrast_episodes_by_anchor.items()
        }
        copy_w.completed_roots_high_watermark = self.completed_roots_high_watermark
        copy_w.completed_external_events_count = self.completed_external_events_count
        copy_w.global_event_clock = self.global_event_clock
        copy_w.close_serial = self.close_serial
        return copy_w

    def is_committed(self, cell_id: int) -> bool:
        """Return True if cell_id is already committed."""
        return cell_id in self.committed_cells

    def commit_cell(self, cell_id: int, event_clock: int) -> bool:
        """Commit cell_id at event_clock if not already committed. Returns True if newly committed."""
        if cell_id in self.committed_cells:
            return False
        self.committed_cells[cell_id] = event_clock
        self.last_referenced_event[cell_id] = event_clock
        self.latent_table.get_slots(cell_id)
        return True

    def add_or_replace_synapse(self, synapse: Synapse) -> None:
        """Insert or update a directed synapse and maintain adjacency indices."""
        key = synapse.key
        self.synapses[key] = synapse
        self.outgoing_by_source.setdefault(synapse.source_id, set()).add(key)
        self.incoming_by_target.setdefault(synapse.target_id, set()).add(key)

    def remove_synapse(self, key: SynapseKey) -> None:
        """Remove a directed synapse and update adjacency indices."""
        syn = self.synapses.pop(key, None)
        if syn is not None:
            if syn.source_id in self.outgoing_by_source:
                self.outgoing_by_source[syn.source_id].discard(key)
            if syn.target_id in self.incoming_by_target:
                self.incoming_by_target[syn.target_id].discard(key)

    def get_protected_bidirectional_neighbors(self, cell_id: int) -> set[int]:
        """Return all cells j that share a live synapse (cell_id -> j or j -> cell_id)."""
        neighbors: set[int] = set()
        for key in self.outgoing_by_source.get(cell_id, ()):
            neighbors.add(key[1])
        for key in self.incoming_by_target.get(cell_id, ()):
            neighbors.add(key[0])
        return neighbors

    def unique_claimed_outgoing_keys(self, source_id: int) -> set[SynapseKey]:
        """Return the union of live outgoing synapse keys and unique reserved candidate keys from source_id.

        Core §1.3 & §10.2 Capacity invariant:
        Do not count a role twice if a live identical directed key already exists.
        """
        claimed: set[SynapseKey] = set(self.outgoing_by_source.get(source_id, ()))
        for keys in self.reserved_keys_by_candidate.values():
            for k in keys:
                if k[0] == source_id:
                    claimed.add(k)
        return claimed

    def available_outgoing_headroom(self, source_id: int) -> int:
        """Return remaining outgoing synapse budget B_i for source_id."""
        used = len(self.unique_claimed_outgoing_keys(source_id))
        return max(0, self.outgoing_budget_b_i - used)

    def available_cross_outgoing_headroom(self, source_id: int) -> int:
        """Return remaining cross-region outgoing budget B_i^x for source_id."""
        claimed = self.unique_claimed_outgoing_keys(source_id)
        cross_used = sum(
            1
            for src, tgt, scope in claimed
            if scope == SynapseScope.CROSS_TERRITORY
            or CellAddress.from_global_id(src).region != CellAddress.from_global_id(tgt).region
        )
        return max(0, self.cross_outgoing_budget_b_i_x - cross_used)

    def is_contextual_cell(self, cell_id: int) -> bool:
        """Return True if cell_id is an incomplete contextual candidate or a graduated contextual owner."""
        return cell_id in self.context_candidates or cell_id in self.stable_bindings

    def is_context_target(self, cell_id: int) -> bool:
        """Evaluate ContextTarget(j, t+1) per RC4.1 (Core §5.2).

        j is a legally committed contextual candidate with an active, pinned P/C role descriptor
        or a COMPLETE contextual owner with a live StableBinding.
        """
        if cell_id not in self.committed_cells:
            return False
        cand = self.context_candidates.get(cell_id)
        if cand is not None:
            if (
                cand.phase != CandidatePhase.FAILED_OR_EXPIRED
                and cand.status == BindingStatus.ACTIVE
            ):
                return True
        bind = self.stable_bindings.get(cell_id)
        if bind is not None and bind.status == BindingStatus.ACTIVE:
            return True
        return False


class HSlowState:
    """Slow homeostatic state H_t^slow (Core §4, §5, §10.1)."""

    def __init__(self) -> None:
        self.r_bar: dict[int, float] = {}
        self.g: dict[int, float] = {}
        self.rho_bar_by_region: dict[Region, float] = {
            reg: params.rho_target for reg, params in REGION_PARAMS.items()
        }
        self.theta_active_by_region: dict[Region, float] = {
            reg: params.theta_active_init for reg, params in REGION_PARAMS.items()
        }

    def clone(self) -> HSlowState:
        """Return an isolated deep copy of HSlowState (used for H_slow_BEGIN capture & rollback)."""
        copy_h = HSlowState()
        copy_h.r_bar = dict(self.r_bar)
        copy_h.g = dict(self.g)
        copy_h.rho_bar_by_region = dict(self.rho_bar_by_region)
        copy_h.theta_active_by_region = dict(self.theta_active_by_region)
        return copy_h

    def get_r_bar(self, cell_id: int) -> float:
        return self.r_bar.get(cell_id, RHO_CELL_TARGET)

    def get_g(self, cell_id: int) -> float:
        return self.g.get(cell_id, G_INIT)

    def get_theta_active(self, region: Region) -> float:
        return self.theta_active_by_region[region]

    def get_theta_emit(self, region: Region) -> float:
        return 1.15 * self.theta_active_by_region[region]

    def get_theta_bind(self, region: Region) -> float:
        return 1.20 * self.theta_active_by_region[region]


class RState:
    """Volatile working neural activity state R_t (Core §4, §5, §6, §11)."""

    def __init__(self) -> None:
        self.A: dict[int, float] = {}
        self.A_prev: dict[int, float] = {}
        self.A_pass1: dict[int, float] = {}
        self.A_hist: dict[int, tuple[float, ...]] = {}

        self.E1_frontier: frozenset[int] = frozenset()
        self.L_frontier: frozenset[int] = frozenset()
        self.Lx_frontier: frozenset[int] = frozenset()
        self.F_step: frozenset[int] = frozenset()
        self.F_step_prev: frozenset[int] = frozenset()

        # Ephemeral contextual gate G_z^ctx(t) and frozen source routing mask mu_i(t)
        self.g_ctx_by_z: dict[int, int] = {}
        self.mu_source_mask: dict[int, int] = {}
        self.mu_prev_source_mask: dict[int, int] = {}
        self.context_diagnostics: list[StatusCode] = []

        # Active Attractors keyed by AssemblyID
        self.active_attractors: dict[int, AttractorRuntimeState] = {}

        # Per-event provenance and typed supports
        self.contribution_lanes: list[ContributionRecord] = []
        self.typed_supports_current: dict[int, TypedSupportRecord] = {}
        self.typed_supports_prev: dict[int, TypedSupportRecord] = {}

        # Bounded eligibility traces (window H_context = 5)
        self.eligibility_traces: dict[int, list[EligibilityEntry]] = {}
        self.step_index: int = 0

    def reset_cold(self) -> None:
        """Execute canonical R_cold reset (Core §11).

        Clears A/A_prev/A_hist, F_step, pass/learning frontiers, observational lanes,
        ordered-witness cache, eligibility traces, and active attractor strength/age/error.
        Never touches W or H_slow.
        """
        self.A.clear()
        self.A_prev.clear()
        self.A_pass1.clear()
        self.A_hist.clear()
        self.E1_frontier = frozenset()
        self.L_frontier = frozenset()
        self.Lx_frontier = frozenset()
        self.F_step = frozenset()
        self.F_step_prev = frozenset()
        self.g_ctx_by_z.clear()
        self.mu_source_mask.clear()
        self.mu_prev_source_mask.clear()
        self.context_diagnostics.clear()
        self.active_attractors.clear()
        self.contribution_lanes.clear()
        self.typed_supports_current.clear()
        self.typed_supports_prev.clear()
        self.eligibility_traces.clear()
        self.step_index = 0

    def clone(self) -> RState:
        """Return an isolated deep copy of RState for FULL/CONTROL or read-only rollouts."""
        copy_r = RState()
        copy_r.A = dict(self.A)
        copy_r.A_prev = dict(self.A_prev)
        copy_r.A_pass1 = dict(self.A_pass1)
        copy_r.A_hist = dict(self.A_hist)
        copy_r.E1_frontier = self.E1_frontier
        copy_r.L_frontier = self.L_frontier
        copy_r.Lx_frontier = self.Lx_frontier
        copy_r.F_step = self.F_step
        copy_r.F_step_prev = self.F_step_prev
        copy_r.g_ctx_by_z = dict(self.g_ctx_by_z)
        copy_r.mu_source_mask = dict(self.mu_source_mask)
        copy_r.mu_prev_source_mask = dict(self.mu_prev_source_mask)
        copy_r.context_diagnostics = list(self.context_diagnostics)
        copy_r.active_attractors = {
            aid: att.clone() for aid, att in self.active_attractors.items()
        }
        copy_r.contribution_lanes = list(self.contribution_lanes)
        copy_r.typed_supports_current = dict(self.typed_supports_current)
        copy_r.typed_supports_prev = dict(self.typed_supports_prev)
        copy_r.eligibility_traces = {
            cid: list(entries) for cid, entries in self.eligibility_traces.items()
        }
        copy_r.step_index = self.step_index
        return copy_r


class MachineState:
    """Complete DGCA v2 state S_t = (W_t, R_t, H_t^slow) (Core §4)."""

    def __init__(
        self,
        w: WState | None = None,
        r: RState | None = None,
        h_slow: HSlowState | None = None,
    ) -> None:
        self.W: WState = w if w is not None else WState()
        self.R: RState = r if r is not None else RState()
        self.H_slow: HSlowState = h_slow if h_slow is not None else HSlowState()

    def clone(self) -> MachineState:
        """Create a complete isolated deep copy of (W, R, H_slow)."""
        return MachineState(
            w=self.W.clone(),
            r=self.R.clone(),
            h_slow=self.H_slow.clone(),
        )

    def get_dumb_cell_view(self, cell_id: int) -> DumbCellView:
        """Construct a read-only DumbCellView for cell_id from (W, R, H_slow) (Core §1.2)."""
        addr = CellAddress.from_global_id(cell_id)
        committed = cell_id in self.W.committed_cells
        return DumbCellView(
            id=cell_id,
            region=addr.region,
            microcolumn=addr.microcolumn_index,
            committed=committed,
            committed_event=self.W.committed_cells.get(cell_id),
            A=self.R.A.get(cell_id, 0.0),
            A_prev=self.R.A_prev.get(cell_id, 0.0),
            A_hist=self.R.A_hist.get(cell_id, ()),
            last_referenced_event=self.W.last_referenced_event.get(cell_id),
            r_bar=self.H_slow.get_r_bar(cell_id),
            g=self.H_slow.get_g(cell_id),
            latent_neighborhood=self.W.latent_table.get_slots(cell_id),
            B_i=self.W.outgoing_budget_b_i,
            B_i_cross=self.W.cross_outgoing_budget_b_i_x,
        )
