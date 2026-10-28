"""Invariant Network Anatomy, Dumb Cell Contract, and Directed Synapse Quality.

Normative references:
- DGCA_CORE_RC4_1.md §1.1 (Network, addressing, regions)
- DGCA_CORE_RC4_1.md §1.2 (Dumb Cell contract)
- DGCA_CORE_RC4_1.md §1.4 (Directed synapse, legal scopes, and quality)
- DGCA_LLA_RC4_1.md §4.1 (FIFR-B01 numerical closure: k_neural vs k_evidence)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region
from dgca.common.numeric import validate_finite_binary64


@dataclass(frozen=True, slots=True)
class RegionParameters:
    """Calibrated regional dynamics constants (Core §1.1, §12)."""

    region: Region
    delta_a: float
    gamma_a: float
    beta: float
    rho_target: float
    theta_active_init: float = 0.20


REGION_PARAMS: dict[Region, RegionParameters] = {
    Region.VISION: RegionParameters(
        region=Region.VISION,
        delta_a=0.50,
        gamma_a=0.90,
        beta=1.00,
        rho_target=0.020,
        theta_active_init=0.20,
    ),
    Region.AUDIO: RegionParameters(
        region=Region.AUDIO,
        delta_a=0.35,
        gamma_a=0.85,
        beta=1.00,
        rho_target=0.025,
        theta_active_init=0.20,
    ),
    Region.LANGUAGE: RegionParameters(
        region=Region.LANGUAGE,
        delta_a=0.20,
        gamma_a=0.80,
        beta=0.80,
        rho_target=0.030,
        theta_active_init=0.20,
    ),
}

THETA_EMIT_FACTOR: float = 1.15
THETA_BIND_FACTOR: float = 1.20
THETA_MIN: float = 0.05
THETA_MAX: float = 0.60

G_MIN: float = 0.70
G_MAX: float = 1.40
G_INIT: float = 1.00
RHO_CELL_TARGET: float = 0.05
BETA_I: float = 0.05
ETA_I: float = 0.002
BETA_H: float = 0.05
ETA_H: float = 0.005
EPS_DEAD: float = 0.002

# Physical per-cell budgets (Core §1.2, §12)
DEFAULT_OUTGOING_BUDGET_B_I: int = 64  # RC3 lab default (RC2 comparator = 32)
CROSS_OUTGOING_BUDGET_B_I_X: int = 12
EPISODIC_OUTGOING_CAP: int = 4
MAX_ASSEMBLY_MEMBERSHIPS: int = 12
LATENT_SLOTS_PER_CELL: int = 24
H_CONTEXT: int = 5

# Evidence and quality constants (Core §1.4, LLA §4.1, §9)
E_MAX: float = 10.0
THETA_S: float = 0.60
THETA_E: float = 0.30
GAMMA_INT_DISCOUNT: float = 0.75
PHI_INT_CAP: float = 0.50

# FIFR-B01 exact stored binary64 literal for exp(-0.30)
K_EVIDENCE_ASSOCIATIVE_DELTA1: float = 0.7408182206817179


class CellState(StrEnum):
    """Derived physical state of a Dumb Cell (Core §1.2)."""

    UNCOMMITTED = "UNCOMMITTED"
    DORMANT = "DORMANT"
    ACTIVE = "ACTIVE"


def derive_cell_state(committed: bool, activity_a: float, theta_active: float) -> CellState:
    """Derive legal cell state strictly from commitment and numerical activity (Core §1.2).

    - UNCOMMITTED iff committed=False and A=0
    - DORMANT iff committed=True and A < theta_active
    - ACTIVE iff committed=True and A >= theta_active
    """
    val_a = validate_finite_binary64(activity_a)
    if not committed:
        if val_a != 0.0:
            raise DGCAError(
                StatusCode.INVALID_NUMERIC_VALUE,
                f"Uncommitted cell cannot have non-zero activity A={val_a}",
            )
        return CellState.UNCOMMITTED
    if val_a >= theta_active:
        return CellState.ACTIVE
    return CellState.DORMANT


@dataclass(slots=True)
class DumbCellView:
    """Physical view of a single Cell enforcing the Dumb Cell Contract (Core §1.2).

    Contains ONLY physical identity, commitment metadata, numerical activity, homeostasis,
    latent neighborhood slots, and budget parameters. Zero semantic or task-role fields exist.
    """

    id: int
    region: Region
    microcolumn: int
    committed: bool = False
    committed_event: int | None = None
    A: float = 0.0
    A_prev: float = 0.0
    A_hist: tuple[float, ...] = ()
    last_referenced_event: int | None = None
    r_bar: float = RHO_CELL_TARGET
    g: float = G_INIT
    latent_neighborhood: tuple[int | None, ...] = ()
    B_i: int = DEFAULT_OUTGOING_BUDGET_B_I
    B_i_cross: int = CROSS_OUTGOING_BUDGET_B_I_X
    E_cap: int = EPISODIC_OUTGOING_CAP
    M_max: int = MAX_ASSEMBLY_MEMBERSHIPS

    def state(self, theta_active: float) -> CellState:
        """Compute the derived CellState under the region's current theta_active."""
        return derive_cell_state(self.committed, self.A, theta_active)


class SynapseScope(IntEnum):
    """Directed synapse scope ordered canonically: LOCAL < CROSS_TERRITORY < ASSOCIATIVE (Core §1.4, §3.1)."""

    LOCAL = 0
    CROSS_TERRITORY = 1
    ASSOCIATIVE = 2


class SynapseState(StrEnum):
    """Lifecycle state of a directed synapse (Core §1.4, LLA §4.4)."""

    CANDIDATE = "CANDIDATE"
    EPISODIC_INDEXED = "EPISODIC_INDEXED"
    CONSOLIDATED = "CONSOLIDATED"


SynapseKey = tuple[int, int, SynapseScope]


def get_k_neural(scope: SynapseScope | int, delta: int | None = None) -> float:
    """Return neural propagation factor k_neural(scope, delta) per FIFR-B01 (Core §1.4, LLA §4.1).

    Always 1.0 for legal (scope, delta) pairs:
    - (LOCAL, 0) -> 1.0
    - (CROSS_TERRITORY, 0) -> 1.0
    - (ASSOCIATIVE, 1) -> 1.0
    Illegal (scope, delta) is rejected, never clamped.
    """
    scope_enum = SynapseScope(scope)
    expected_delta = 1 if scope_enum == SynapseScope.ASSOCIATIVE else 0
    if delta is not None and delta != expected_delta:
        raise DGCAError(
            StatusCode.INVALID_OBSERVATION,
            f"Illegal (scope={scope_enum.name}, delta={delta}) for k_neural; expected delta={expected_delta}",
        )
    return 1.0


def get_k_evidence(scope: SynapseScope | int, delta: int | None = None) -> float:
    """Return evidence accumulation factor k_evidence(scope, delta) per FIFR-B01 (Core §1.4, LLA §4.1).

    - (LOCAL, 0) -> 1.0
    - (CROSS_TERRITORY, 0) -> 1.0
    - (ASSOCIATIVE, 1) -> 0.7408182206817179 (stored binary64 literal for exp(-0.30))
    Illegal (scope, delta) is rejected, never clamped.
    """
    scope_enum = SynapseScope(scope)
    expected_delta = 1 if scope_enum == SynapseScope.ASSOCIATIVE else 0
    if delta is not None and delta != expected_delta:
        raise DGCAError(
            StatusCode.INVALID_OBSERVATION,
            f"Illegal (scope={scope_enum.name}, delta={delta}) for k_evidence; expected delta={expected_delta}",
        )
    if scope_enum == SynapseScope.ASSOCIATIVE:
        return K_EVIDENCE_ASSOCIATIVE_DELTA1
    return 1.0


@dataclass(slots=True)
class Synapse:
    """Directed synapse stored under (source_id, target_id, scope) in W (Core §1.4, LLA §4.3–§5)."""

    key: SynapseKey
    S: float
    E_ext: float
    E_int: float = 0.0
    external_count: int = 1
    state: SynapseState = SynapseState.CANDIDATE
    created_event_id: int = 0
    created_exposure_id: int = 0
    last_external_event_id: int = 0
    last_evidence_root: int = 0
    candidate_deadline: int = 100
    internally_supported: bool = False
    confirmed_roots: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        src, tgt, scope = self.key
        if src == tgt:
            raise DGCAError(StatusCode.INVALID_OBSERVATION, f"Self-link forbidden: {self.key}")
        self.key = (int(src), int(tgt), SynapseScope(scope))
        self.S = validate_finite_binary64(self.S)
        self.E_ext = validate_finite_binary64(self.E_ext)
        self.E_int = validate_finite_binary64(self.E_int)
        self.internally_supported = self.E_int > self.E_ext

    @property
    def source_id(self) -> int:
        return self.key[0]

    @property
    def target_id(self) -> int:
        return self.key[1]

    @property
    def scope(self) -> SynapseScope:
        return self.key[2]

    @property
    def E(self) -> float:
        """Total bounded evidence mass E = min(E_max, E_ext + E_int) (LLA §4.3)."""
        total = self.E_ext + self.E_int
        return E_MAX if total >= E_MAX else total

    @property
    def discount_d(self) -> float:
        """Internal-support quality discount d_ij = 0.75 if E_int > E_ext else 1.0 (Core §1.4)."""
        return GAMMA_INT_DISCOUNT if self.E_int > self.E_ext else 1.0

    @property
    def Q(self) -> float:
        """Qualitative propagation weight Q_ij^s = d_ij * S_ij * (E_ij / E_max) (Core §1.4, LLA §4.1)."""
        return self.discount_d * self.S * (self.E / E_MAX)

    def clone(self) -> Synapse:
        """Return an isolated deep copy of this Synapse."""
        return Synapse(
            key=self.key,
            S=self.S,
            E_ext=self.E_ext,
            E_int=self.E_int,
            external_count=self.external_count,
            state=self.state,
            created_event_id=self.created_event_id,
            created_exposure_id=self.created_exposure_id,
            last_external_event_id=self.last_external_event_id,
            last_evidence_root=self.last_evidence_root,
            candidate_deadline=self.candidate_deadline,
            internally_supported=self.internally_supported,
            confirmed_roots=self.confirmed_roots,
        )
