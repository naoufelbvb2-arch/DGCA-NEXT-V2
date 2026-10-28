"""24-Slot Latent Neighborhood, Bidirectional Eligibility D_ij, and Transactional Reverse Index.

Normative references:
- DGCA_CORE_RC4_1.md §1.3 (Latent neighborhood, eligibility, inverse index)
- DGCA_LLA_RC4_1.md §5 (LLA-T06 STALE_LATENT_ELIGIBILITY, LLA-T07 RECYCLE_BLOCKED_CANDIDATE)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import REGION_CELL_COUNT, TOTAL_CELL_COUNT, Region
from dgca.core.sic_v1 import CELLS_PER_MICROCOLUMN, MC_COLS, MC_ROWS, CellAddress

# Slot index ranges within the 24-slot latent_neighborhood array (Core §1.3):
# [0..5]   : 6 co-active intra (recyclable if unprotected)
# [6..11]  : 6 local (fixed deterministic spatial vicinity, never recycled)
# [12..17] : 6 co-active inter (3 per other region, recyclable if unprotected)
# [18..23] : 6 topographic (3 per other region, fixed deterministic, never recycled)
COACTIVE_INTRA_SLOTS: range = range(0, 6)
FIXED_LOCAL_SLOTS: range = range(6, 12)
COACTIVE_INTER_SLOTS: range = range(12, 18)
FIXED_TOPOGRAPHIC_SLOTS: range = range(18, 24)


@dataclass(frozen=True, slots=True)
class WiringLogEntry:
    """Audit log record of a latent neighborhood slot assignment or recycling event (Core §1.2, §1.3)."""

    event_clock: int
    owner_cell_id: int
    slot_index: int
    old_target_id: int | None
    new_target_id: int | None
    reason: str


def compute_fixed_local_neighbors(global_cell_id: int) -> tuple[int, int, int, int, int, int]:
    """Deterministically compute the 6 fixed local spatial vicinity slots (slots 6..11) for a cell.

    Core §1.1 & §1.3: Local spatial vicinity is the cell's own microcolumn plus orthogonally
    adjacent microcolumns, bounded at borders.
    """
    addr = CellAddress.from_global_id(global_cell_id)
    base_region_offset = int(addr.region) * REGION_CELL_COUNT
    candidates: list[int] = []

    # 1. Other slots in the cell's own microcolumn (in deterministic ascending slot delta order)
    for delta in range(1, CELLS_PER_MICROCOLUMN):
        other_slot = (addr.slot + delta) % CELLS_PER_MICROCOLUMN
        other_local = addr.microcolumn_index * CELLS_PER_MICROCOLUMN + other_slot
        candidates.append(base_region_offset + other_local)

    # 2. Orthogonally adjacent microcolumns (up, down, left, right), bounded at borders
    for d_row, d_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr = addr.mc_row + d_row
        nc = addr.mc_col + d_col
        if 0 <= nr < MC_ROWS and 0 <= nc < MC_COLS:
            adj_mc = nr * MC_COLS + nc
            adj_local = adj_mc * CELLS_PER_MICROCOLUMN + addr.slot
            candidates.append(base_region_offset + adj_local)

    # Take first 2 own-microcolumn peers + up to 4 orthogonal microcolumn peers (total 6 distinct)
    selected: list[int] = []
    # Prefer orthogonal neighbors + own-microcolumn neighbors to span local vicinity
    own_mc = candidates[:7]
    ortho_mc = candidates[7:]
    for cid in ortho_mc + own_mc:
        if cid != global_cell_id and cid not in selected:
            selected.append(cid)
            if len(selected) == 6:
                break
    return (
        selected[0],
        selected[1],
        selected[2],
        selected[3],
        selected[4],
        selected[5],
    )


def compute_fixed_topographic_neighbors(global_cell_id: int) -> tuple[int, int, int, int, int, int]:
    """Deterministically compute the 6 fixed cross-region topographic slots (slots 18..23, 3 per other region)."""
    addr = CellAddress.from_global_id(global_cell_id)
    other_regions = [r for r in (Region.VISION, Region.AUDIO, Region.LANGUAGE) if r != addr.region]
    selected: list[int] = []

    for other_reg in other_regions:
        base_offset = int(other_reg) * REGION_CELL_COUNT
        for k in range(3):
            target_slot = (addr.slot + k) % CELLS_PER_MICROCOLUMN
            target_local = addr.microcolumn_index * CELLS_PER_MICROCOLUMN + target_slot
            selected.append(base_offset + target_local)

    return (
        selected[0],
        selected[1],
        selected[2],
        selected[3],
        selected[4],
        selected[5],
    )


def _inter_region_slot_range(owner_region: Region, target_region: Region) -> range:
    """Return the 3 co-active inter slot indices (within 12..17) allocated to target_region."""
    other_regions = [r for r in (Region.VISION, Region.AUDIO, Region.LANGUAGE) if r != owner_region]
    if target_region not in other_regions:
        raise DGCAError(
            StatusCode.INVALID_OBSERVATION,
            f"Target region {target_region} is not a cross-region for {owner_region}",
        )
    idx = other_regions.index(target_region)
    start = 12 + idx * 3
    return range(start, start + 3)


class LatentNeighborhoodTable:
    """Manages the 24-slot latent neighborhoods, reverse index, and candidate pins for all cells (Core §1.3).

    Uses lazy materialization per cell so cloning and initialization remain fast while preserving
    exact 24-slot semantics for every cell 0..12287.
    """

    def __init__(self) -> None:
        # Maps cell_id -> 24-element list of (target_cell_id | None) for materialized cells
        self._slots_by_cell: dict[int, list[int | None]] = {}
        # Maps target_cell_id -> set of source_cell_ids explicitly listing target in co-active slots (0..5, 12..17)
        self._coactive_reverse_index: dict[int, set[int]] = {}
        # Maps (owner_cell_id, slot_index) -> set of pinning context candidate z_ids
        self._pinned_slots: dict[tuple[int, int], set[int]] = {}
        # Per-cell wiring audit log
        self._wiring_logs: dict[int, list[WiringLogEntry]] = {}

    def clone(self) -> LatentNeighborhoodTable:
        """Create an isolated deep copy of the latent neighborhood table."""
        copy_table = LatentNeighborhoodTable()
        copy_table._slots_by_cell = {
            cid: list(slots) for cid, slots in self._slots_by_cell.items()
        }
        copy_table._coactive_reverse_index = {
            tgt: set(srcs) for tgt, srcs in self._coactive_reverse_index.items() if srcs
        }
        copy_table._pinned_slots = {
            k: set(v) for k, v in self._pinned_slots.items() if v
        }
        copy_table._wiring_logs = {
            cid: list(entries) for cid, entries in self._wiring_logs.items()
        }
        return copy_table

    def _ensure_cell_materialized(self, cell_id: int) -> list[int | None]:
        """Materialize the 24-slot array for cell_id if not yet materialized."""
        if not (0 <= cell_id < TOTAL_CELL_COUNT):
            raise DGCAError(StatusCode.INVALID_OBSERVATION, f"Cell ID out of range: {cell_id}")
        slots = self._slots_by_cell.get(cell_id)
        if slots is None:
            slots = [None] * 24
            local_6 = compute_fixed_local_neighbors(cell_id)
            topo_6 = compute_fixed_topographic_neighbors(cell_id)
            for idx, target in enumerate(local_6):
                slots[6 + idx] = target
            for idx, target in enumerate(topo_6):
                slots[18 + idx] = target
            self._slots_by_cell[cell_id] = slots
        return slots

    def get_slots(self, cell_id: int) -> tuple[int | None, ...]:
        """Return the 24-slot tuple for cell_id."""
        return tuple(self._ensure_cell_materialized(cell_id))

    def get_wiring_log(self, cell_id: int) -> tuple[WiringLogEntry, ...]:
        """Return the wiring audit log for cell_id."""
        return tuple(self._wiring_logs.get(cell_id, ()))

    def forward_neighbors(self, cell_id: int) -> set[int]:
        """Return the set of all non-None target cell IDs in N(cell_id)."""
        slots = self._ensure_cell_materialized(cell_id)
        return {tgt for tgt in slots if tgt is not None}

    def reverse_neighbors(self, target_cell_id: int) -> set[int]:
        """Return all source cell IDs i such that target_cell_id in N(i).

        Combines the transactional coactive reverse index with deterministic fixed local/topographic inverses.
        """
        if not (0 <= target_cell_id < TOTAL_CELL_COUNT):
            raise DGCAError(StatusCode.INVALID_OBSERVATION, f"Cell ID out of range: {target_cell_id}")
        sources: set[int] = set(self._coactive_reverse_index.get(target_cell_id, ()))

        # Check local neighborhood candidates (same microcolumn + 4 orthogonal microcolumns)
        addr = CellAddress.from_global_id(target_cell_id)
        base_reg = int(addr.region) * REGION_CELL_COUNT
        candidate_sources: list[int] = []
        for s in range(CELLS_PER_MICROCOLUMN):
            cid = base_reg + addr.microcolumn_index * CELLS_PER_MICROCOLUMN + s
            if cid != target_cell_id:
                candidate_sources.append(cid)
        for d_row, d_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = addr.mc_row + d_row, addr.mc_col + d_col
            if 0 <= nr < MC_ROWS and 0 <= nc < MC_COLS:
                adj_mc = nr * MC_COLS + nc
                candidate_sources.append(base_reg + adj_mc * CELLS_PER_MICROCOLUMN + addr.slot)

        # Check topographic candidates across other regions (same microcolumn_index)
        for other_reg in (Region.VISION, Region.AUDIO, Region.LANGUAGE):
            if other_reg != addr.region:
                other_base = int(other_reg) * REGION_CELL_COUNT
                for s in range(CELLS_PER_MICROCOLUMN):
                    candidate_sources.append(other_base + addr.microcolumn_index * CELLS_PER_MICROCOLUMN + s)

        for src_id in candidate_sources:
            if target_cell_id in self.forward_neighbors(src_id):
                sources.add(src_id)

        return sources

    def is_eligible(self, source_id: int, target_id: int) -> bool:
        """Evaluate D_ij = 1[j in N(i) or i in N(j)] (Core §1.3)."""
        if source_id == target_id:
            return False
        slots_i = self._ensure_cell_materialized(source_id)
        if target_id in slots_i:
            return True
        slots_j = self._ensure_cell_materialized(target_id)
        return source_id in slots_j

    def is_slot_pinned(self, owner_cell_id: int, slot_index: int) -> bool:
        """Return True if (owner_cell_id, slot_index) is pinned by any active contextual candidate."""
        pins = self._pinned_slots.get((owner_cell_id, slot_index))
        return bool(pins)

    def _set_coactive_slot(
        self,
        owner_cell_id: int,
        slot_index: int,
        new_target_id: int | None,
        *,
        event_clock: int = 0,
        reason: str = "ADMIT",
    ) -> None:
        """Transactionally update a co-active slot (0..5 or 12..17), reverse index, and wiring log."""
        if slot_index not in COACTIVE_INTRA_SLOTS and slot_index not in COACTIVE_INTER_SLOTS:
            raise DGCAError(
                StatusCode.INVALID_OBSERVATION,
                f"Cannot modify fixed local/topographic slot {slot_index}",
            )
        if new_target_id == owner_cell_id:
            raise DGCAError(StatusCode.INVALID_OBSERVATION, "Self-slot assignment forbidden")

        slots = self._ensure_cell_materialized(owner_cell_id)
        old_target = slots[slot_index]
        if old_target == new_target_id:
            return

        if old_target is not None:
            # Remove from coactive reverse index if no other coactive slot of owner points to old_target
            slots[slot_index] = None
            still_listed = any(
                slots[idx] == old_target
                for idx in tuple(COACTIVE_INTRA_SLOTS) + tuple(COACTIVE_INTER_SLOTS)
            )
            if not still_listed and old_target in self._coactive_reverse_index:
                self._coactive_reverse_index[old_target].discard(owner_cell_id)
                if not self._coactive_reverse_index[old_target]:
                    del self._coactive_reverse_index[old_target]

        slots[slot_index] = new_target_id
        if new_target_id is not None:
            if new_target_id not in self._coactive_reverse_index:
                self._coactive_reverse_index[new_target_id] = set()
            self._coactive_reverse_index[new_target_id].add(owner_cell_id)

        if owner_cell_id not in self._wiring_logs:
            self._wiring_logs[owner_cell_id] = []
        self._wiring_logs[owner_cell_id].append(
            WiringLogEntry(
                event_clock=event_clock,
                owner_cell_id=owner_cell_id,
                slot_index=slot_index,
                old_target_id=old_target,
                new_target_id=new_target_id,
                reason=reason,
            )
        )

    def admit_or_recycle_coactive_partner(
        self,
        owner_cell_id: int,
        partner_cell_id: int,
        *,
        protected_bidirectional_neighbors: set[int] | None = None,
        pin_for_candidate_z: int | None = None,
        event_clock: int = 0,
        reason: str = "COACTIVE_ADMIT",
    ) -> int:
        """Assign partner_cell_id to a co-active slot of owner_cell_id (intra 0..5 or inter 12..17).

        Enforces Core §1.3 priority:
            legal live-link protection > committed contextual pin > recycling of unprotected slot.
        Raises DGCAError(StatusCode.RECYCLE_BLOCKED_CANDIDATE) if recycling is blocked by candidate pins.
        Returns the slot_index holding partner_cell_id.
        """
        if owner_cell_id == partner_cell_id:
            raise DGCAError(StatusCode.INVALID_OBSERVATION, "Cannot admit self to latent neighborhood")

        owner_reg = CellAddress.from_global_id(owner_cell_id).region
        partner_reg = CellAddress.from_global_id(partner_cell_id).region
        slot_range = (
            COACTIVE_INTRA_SLOTS
            if owner_reg == partner_reg
            else _inter_region_slot_range(owner_reg, partner_reg)
        )

        slots = self._ensure_cell_materialized(owner_cell_id)
        protected = protected_bidirectional_neighbors or set()

        # 1. Check if partner_cell_id is already present in one of the target slots
        for idx in slot_range:
            if slots[idx] == partner_cell_id:
                if pin_for_candidate_z is not None:
                    self._pinned_slots.setdefault((owner_cell_id, idx), set()).add(pin_for_candidate_z)
                return idx

        # 2. Look for an empty (None) slot in slot_range
        for idx in slot_range:
            if slots[idx] is None:
                self._set_coactive_slot(
                    owner_cell_id, idx, partner_cell_id, event_clock=event_clock, reason=reason
                )
                if pin_for_candidate_z is not None:
                    self._pinned_slots.setdefault((owner_cell_id, idx), set()).add(pin_for_candidate_z)
                return idx

        # 3. Try to recycle an unprotected, unpinned slot in slot_range
        saw_candidate_pin = False
        for idx in slot_range:
            occupant = slots[idx]
            if self.is_slot_pinned(owner_cell_id, idx):
                saw_candidate_pin = True
                continue
            if occupant is not None and occupant in protected:
                continue
            # Found recyclable unprotected slot
            self._set_coactive_slot(
                owner_cell_id, idx, partner_cell_id, event_clock=event_clock, reason=f"RECYCLE:{reason}"
            )
            if pin_for_candidate_z is not None:
                self._pinned_slots.setdefault((owner_cell_id, idx), set()).add(pin_for_candidate_z)
            return idx

        if saw_candidate_pin:
            raise DGCAError(
                StatusCode.RECYCLE_BLOCKED_CANDIDATE,
                f"Cannot recycle coactive slots of cell {owner_cell_id}: blocked by candidate pin",
            )
        raise DGCAError(
            StatusCode.STALE_LATENT_ELIGIBILITY,
            f"All coactive slots of cell {owner_cell_id} are protected by live synapses",
        )

    def pin_context_candidate_roles(
        self,
        z_cell_id: int,
        role_partner_ids: Iterable[int],
        *,
        protected_bidirectional_neighbors: set[int] | None = None,
        event_clock: int = 0,
    ) -> tuple[int, ...]:
        """Reserve and pin up to 6 co-active slots on contextual candidate z for its P/C/Y role partners.

        Core §1.3 Contextual exception:
        Repeated physical cell IDs across role sets consume one physical slot.
        """
        unique_partners: list[int] = []
        for pid in role_partner_ids:
            if pid not in unique_partners:
                unique_partners.append(pid)
        if len(unique_partners) > 6:
            raise DGCAError(
                StatusCode.NO_FEASIBLE_2_2_2_WITHIN_FRONTIER,
                f"Contextual candidate z={z_cell_id} cannot pin >6 unique role partners ({len(unique_partners)})",
            )

        pinned_indices: list[int] = []
        for pid in unique_partners:
            idx = self.admit_or_recycle_coactive_partner(
                z_cell_id,
                pid,
                protected_bidirectional_neighbors=protected_bidirectional_neighbors,
                pin_for_candidate_z=z_cell_id,
                event_clock=event_clock,
                reason="PIN_CONTEXT_CANDIDATE",
            )
            pinned_indices.append(idx)
        return tuple(pinned_indices)

    def release_candidate_pins(self, z_cell_id: int) -> None:
        """Release temporary candidate slot pins held by z_cell_id upon completion or expiration."""
        to_delete: list[tuple[int, int]] = []
        for key, z_set in self._pinned_slots.items():
            z_set.discard(z_cell_id)
            if not z_set:
                to_delete.append(key)
        for key in to_delete:
            del self._pinned_slots[key]
