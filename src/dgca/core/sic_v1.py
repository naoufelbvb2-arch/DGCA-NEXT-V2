"""Layer 2: SIC-V1 Byte-Exact Projection Gate and Cell Addressing (Core §1.1, §3, §3.1).

Normative references:
- DGCA_CORE_RC4_1.md §1.1 (Network, addressing, regions)
- DGCA_CORE_RC4_1.md §3.1 (FIFR-B04 — SIC-V1 byte-exact input and projection)
- DGCA_LLA_RC4_1.md §2.1 (ObservationWitness and CELL_FEATURE_ALIAS)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import unicodedata

from dgca.common.errors import ObservationError, StatusCode
from dgca.common.hashing import (
    REGION_CELL_COUNT,
    TOTAL_CELL_COUNT,
    Region,
    Role,
    compute_feature_bundle_digest,
    compute_fp_role_v1,
    sic_v1_project_feature,
)
from dgca.common.numeric import (
    DEFAULT_SALIENCE_STR,
    clip_float64,
    format_support_millionths,
    millionths_to_binary64,
    noisy_or_millionths,
    parse_support_millionths,
    scale_by_salience_millionths,
)
from dgca.encoder.envelope import CoreEventPayloadV1

MC_ROWS: int = 32
MC_COLS: int = 16
MICROCOLUMNS_PER_REGION: int = 512
CELLS_PER_MICROCOLUMN: int = 8


@dataclass(frozen=True, slots=True)
class CellAddress:
    """Deterministic physical cell address (Core §1.1, §3.1).

    No semantic labels exist on a cell; identity follows strictly from (region, mc_row, mc_col, slot).
    """

    global_id: int
    region: Region
    local_index: int
    microcolumn_index: int
    mc_row: int
    mc_col: int
    slot: int

    @classmethod
    def from_global_id(cls, global_id: int) -> CellAddress:
        """Construct CellAddress from global_id in [0, 12287]."""
        if not isinstance(global_id, int) or isinstance(global_id, bool) or not (0 <= global_id < TOTAL_CELL_COUNT):
            raise ObservationError(f"Global cell ID out of bounds [0, {TOTAL_CELL_COUNT - 1}]: {global_id!r}")
        region_u8 = global_id // REGION_CELL_COUNT
        local_index = global_id % REGION_CELL_COUNT
        return cls.from_local_index(Region(region_u8), local_index)

    @classmethod
    def from_local_index(cls, region: Region | int, local_index: int) -> CellAddress:
        """Construct CellAddress from region and region-local index in [0, 4095] (Core §3.1)."""
        region_enum = Region(region)
        if not isinstance(local_index, int) or isinstance(local_index, bool) or not (0 <= local_index < REGION_CELL_COUNT):
            raise ObservationError(f"Local cell index out of bounds [0, {REGION_CELL_COUNT - 1}]: {local_index!r}")
        global_id = int(region_enum) * REGION_CELL_COUNT + local_index
        mc_idx = local_index // CELLS_PER_MICROCOLUMN
        mc_row = mc_idx // MC_COLS
        mc_col = mc_idx % MC_COLS
        slot = local_index % CELLS_PER_MICROCOLUMN
        return cls(
            global_id=global_id,
            region=region_enum,
            local_index=local_index,
            microcolumn_index=mc_idx,
            mc_row=mc_row,
            mc_col=mc_col,
            slot=slot,
        )

    @classmethod
    def from_coordinates(
        cls,
        region: Region | int,
        mc_row: int,
        mc_col: int,
        slot: int,
    ) -> CellAddress:
        """Construct CellAddress from (region, mc_row, mc_col, slot)."""
        if not (0 <= mc_row < MC_ROWS):
            raise ObservationError(f"mc_row out of bounds [0, 31]: {mc_row}")
        if not (0 <= mc_col < MC_COLS):
            raise ObservationError(f"mc_col out of bounds [0, 15]: {mc_col}")
        if not (0 <= slot < CELLS_PER_MICROCOLUMN):
            raise ObservationError(f"slot out of bounds [0, 7]: {slot}")
        mc_idx = mc_row * MC_COLS + mc_col
        local_index = mc_idx * CELLS_PER_MICROCOLUMN + slot
        return cls.from_local_index(region, local_index)


@dataclass(frozen=True, slots=True)
class FeatureProjectionDetail:
    """Projection trace for a single unique normalized feature in SIC-V1."""

    feature_nfc: str
    feature_utf8: bytes
    merged_support_u: int
    scaled_support_u: int
    salt_order_local_indices: tuple[int, int, int, int]
    sorted_distinct_local_indices: tuple[int, ...]
    sorted_distinct_global_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SICProjectionResult:
    """Authoritative output of SIC-V1 projection for a single event (Core §3.1, LLA §2.1)."""

    region: Region
    salience_u: int
    salience_str: str
    feature_bundle_digest: bytes
    feature_details: tuple[FeatureProjectionDetail, ...]
    # Sorted ascending by global_cell_id; only positive supports (X_fixed > 0)
    x_fixed_by_global_id: dict[int, int]
    x_float_by_global_id: dict[int, float]
    # Cells that received contributions from >= 2 distinct features in this event
    aliased_global_cell_ids: tuple[int, ...]

    @property
    def sorted_direct_items(self) -> tuple[tuple[int, int], ...]:
        """Return strictly ascending (global_cell_id, X_fixed) pairs for FP-ROLE-V1."""
        return tuple(sorted(self.x_fixed_by_global_id.items()))

    def role_fingerprint_v1(self, role: Role | int) -> bytes:
        """Compute the 32-byte FP-ROLE-V1 SHA-256 digest for this projection's direct receivers."""
        return compute_fp_role_v1(role, self.sorted_direct_items)


def _normalize_sic_feature(raw_feature: str | bytes) -> tuple[str, bytes]:
    """Validate strict UTF-8, reject lone surrogates, normalize to NFC, and verify byte length in [1, 4096]."""
    if isinstance(raw_feature, bytes):
        try:
            text = raw_feature.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ObservationError(f"Invalid UTF-8 bytes in SIC feature: {exc}") from exc
    elif isinstance(raw_feature, str):
        for ch in raw_feature:
            cp = ord(ch)
            if 0xD800 <= cp <= 0xDFFF:
                raise ObservationError(f"Lone surrogate U+{cp:04X} rejected in SIC feature")
        text = raw_feature
    else:
        raise ObservationError(f"Invalid feature type: {type(raw_feature).__name__}")

    nfc_text = unicodedata.normalize("NFC", text)
    utf8_bytes = nfc_text.encode("utf-8")
    if len(utf8_bytes) == 0 or len(utf8_bytes) > 4096:
        raise ObservationError(
            f"Normalized SIC feature byte length {len(utf8_bytes)} outside [1, 4096]"
        )
    return nfc_text, utf8_bytes


def project_sic_v1(
    features: Sequence[tuple[str | bytes, str]],
    *,
    salience: str = DEFAULT_SALIENCE_STR,
    region: Region | int = Region.LANGUAGE,
) -> SICProjectionResult:
    """Execute byte-exact SIC-V1 feature normalization, deduplication, and 4-salt projection (Core §3.1).

    Supports both Layer 1 Encoder bundles and direct RAW_FEATURE_PASS_THROUGH test vectors.
    """
    region_enum = Region(region)
    salience_u = parse_support_millionths(salience, error_code=StatusCode.INVALID_OBSERVATION)
    if not features:
        raise ObservationError("SIC-V1 requires at least one feature pair")

    # 1. Normalize features to NFC and group identical UTF-8 byte strings
    grouped: dict[bytes, tuple[str, list[int]]] = {}
    for raw_feat, support_str in features:
        nfc_feat, utf8_bytes = _normalize_sic_feature(raw_feat)
        u = parse_support_millionths(support_str, error_code=StatusCode.INVALID_OBSERVATION)
        if utf8_bytes not in grouped:
            grouped[utf8_bytes] = (nfc_feat, [u])
        else:
            grouped[utf8_bytes][1].append(u)

    # 2. Sort unique normalized features by raw unsigned UTF-8 byte order
    sorted_feat_bytes = sorted(grouped.keys())

    # 3. Merge duplicate supports via exact decimal Noisy-OR (half-even once),
    #    then scale by salience (half-even once) and project across salts k=0..3
    base_offset = int(region_enum) * REGION_CELL_COUNT
    bundle_features_for_digest: list[tuple[bytes, int]] = []
    feature_details: list[FeatureProjectionDetail] = []
    cell_contributors: dict[int, list[int]] = {}

    for utf8_bytes in sorted_feat_bytes:
        nfc_feat, u_list = grouped[utf8_bytes]
        merged_u = u_list[0] if len(u_list) == 1 else noisy_or_millionths(u_list)
        bundle_features_for_digest.append((utf8_bytes, merged_u))
        scaled_u = scale_by_salience_millionths(merged_u, salience_u)

        salt_indices, sorted_distinct_local = sic_v1_project_feature(utf8_bytes, region_enum)
        sorted_distinct_global = tuple(base_offset + idx for idx in sorted_distinct_local)

        feature_details.append(
            FeatureProjectionDetail(
                feature_nfc=nfc_feat,
                feature_utf8=utf8_bytes,
                merged_support_u=merged_u,
                scaled_support_u=scaled_u,
                salt_order_local_indices=salt_indices,
                sorted_distinct_local_indices=sorted_distinct_local,
                sorted_distinct_global_ids=sorted_distinct_global,
            )
        )

        # Core §3.1: Zero-support features do not contribute.
        # If the same feature maps to the same cell through multiple salts, count that feature once per cell.
        if scaled_u > 0:
            for global_id in sorted_distinct_global:
                if global_id not in cell_contributors:
                    cell_contributors[global_id] = [scaled_u]
                else:
                    cell_contributors[global_id].append(scaled_u)

    # 4. Aggregate across different features mapped to the same cell via exact decimal Noisy-OR
    x_fixed_by_global_id: dict[int, int] = {}
    x_float_by_global_id: dict[int, float] = {}
    aliased_ids: list[int] = []

    for global_id in sorted(cell_contributors.keys()):
        contrib_list = cell_contributors[global_id]
        if len(contrib_list) > 1:
            aliased_ids.append(global_id)
        final_u = contrib_list[0] if len(contrib_list) == 1 else noisy_or_millionths(contrib_list)
        if final_u > 0:
            x_fixed_by_global_id[global_id] = final_u
            x_float_by_global_id[global_id] = millionths_to_binary64(final_u)

    bundle_digest = compute_feature_bundle_digest(salience_u, bundle_features_for_digest)
    return SICProjectionResult(
        region=region_enum,
        salience_u=salience_u,
        salience_str=format_support_millionths(salience_u),
        feature_bundle_digest=bundle_digest,
        feature_details=tuple(feature_details),
        x_fixed_by_global_id=x_fixed_by_global_id,
        x_float_by_global_id=x_float_by_global_id,
        aliased_global_cell_ids=tuple(aliased_ids),
    )


def project_core_event_v1(core_event: CoreEventPayloadV1) -> SICProjectionResult:
    """Project a CoreEventPayloadV1 through SIC-V1 and verify its feature_bundle_digest."""
    res = project_sic_v1(
        core_event.features,
        salience=core_event.salience,
        region=core_event.modality,
    )
    if res.feature_bundle_digest != core_event.feature_bundle_digest:
        raise ObservationError(
            "CoreEventPayloadV1 feature_bundle_digest does not match canonical SIC-V1 digest"
        )
    return res


@dataclass(frozen=True, slots=True)
class ColdSimulationResult:
    """Result of cold Pass-1 / Pass-2 activity simulation for a projected event (Encoder §3, ENC-T07)."""

    d1_by_global_id: dict[int, float]
    a1_by_global_id: dict[int, float]
    a_plus_by_global_id: dict[int, float]
    e1_frontier_global_ids: tuple[int, ...]
    min_a1: float
    min_pairwise_coactivity: float


def simulate_cold_language_event(
    projection: SICProjectionResult,
    *,
    gamma_a: float = 0.80,
    beta: float = 0.80,
    theta_active: float = 0.20,
    theta_emit_factor: float = 1.15,
    g_default: float = 1.00,
) -> ColdSimulationResult:
    """Simulate a cold event (A_prev=0, P_T=0, P_S=0, sigma=0) under LANGUAGE parameters (Core §5, Encoder §3).

    Used to verify ENC-T07 (all projected cells achieve A_j^(1) >= theta_emit = 0.23 and
    pairwise A_i^+ * A_j^+ >= theta_create = 0.20).
    """
    theta_emit = theta_active * theta_emit_factor

    # Group raw drives hat_D^(1) = X_j by microcolumn
    mc_sums: dict[int, float] = {}
    for global_id, x_val in projection.x_float_by_global_id.items():
        addr = CellAddress.from_global_id(global_id)
        mc_sums[addr.microcolumn_index] = mc_sums.get(addr.microcolumn_index, 0.0) + x_val

    d1_by_id: dict[int, float] = {}
    a1_by_id: dict[int, float] = {}
    a_plus_by_id: dict[int, float] = {}
    e1_frontier: list[int] = []

    for global_id in sorted(projection.x_float_by_global_id.keys()):
        x_val = projection.x_float_by_global_id[global_id]
        addr = CellAddress.from_global_id(global_id)
        mc_mean = mc_sums[addr.microcolumn_index] / float(CELLS_PER_MICROCOLUMN)
        d1 = x_val / (1.0 + beta * mc_mean)
        a1 = clip_float64(gamma_a * g_default * d1, 0.0, 1.0)
        d1_by_id[global_id] = d1
        a1_by_id[global_id] = a1
        # In a cold network with no prior consolidated LOCAL/CROSS links, P_S = 0 so A^+ = A^(1)
        a_plus_by_id[global_id] = a1
        if a1 >= theta_emit:
            e1_frontier.append(global_id)

    a_values = list(a_plus_by_id.values())
    min_a1 = min(a_values) if a_values else 0.0

    pairwise_products: list[float] = []
    ids = sorted(a_plus_by_id.keys())
    for idx_i in range(len(ids)):
        for idx_j in range(idx_i + 1, len(ids)):
            pairwise_products.append(a_plus_by_id[ids[idx_i]] * a_plus_by_id[ids[idx_j]])
    min_coactivity = min(pairwise_products) if pairwise_products else 0.0

    return ColdSimulationResult(
        d1_by_global_id=d1_by_id,
        a1_by_global_id=a1_by_id,
        a_plus_by_global_id=a_plus_by_id,
        e1_frontier_global_ids=tuple(e1_frontier),
        min_a1=min_a1,
        min_pairwise_coactivity=min_coactivity,
    )


def compute_weighted_footprint_distance(
    u_footprint: dict[int, int | float],
    v_footprint: dict[int, int | float],
) -> float:
    """Compute weighted neural footprint distance d(U, V) (Core §7.1, LLA §6.1, Encoder §3).

    Formula:
        d(U, V) = 1 - sum_i min(U_i, V_i) / sum_i max(U_i, V_i)
        d(0, 0) = 0.0; d(0, V) = 1.0 if V != 0
    """
    all_keys = sorted(set(u_footprint.keys()) | set(v_footprint.keys()))
    sum_min = 0.0
    sum_max = 0.0
    for k in all_keys:
        u_val = float(u_footprint.get(k, 0.0))
        v_val = float(v_footprint.get(k, 0.0))
        if u_val < 0.0 or v_val < 0.0:
            raise ObservationError("Footprint supports must be non-negative")
        sum_min += min(u_val, v_val)
        sum_max += max(u_val, v_val)

    if sum_max == 0.0:
        return 0.0
    return 1.0 - (sum_min / sum_max)
