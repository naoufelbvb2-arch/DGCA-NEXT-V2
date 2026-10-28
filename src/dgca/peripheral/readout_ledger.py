"""Peripheral SurfaceReadoutLedgerV1 (Core §9.4, LLA §7.1).

Normative references:
- DGCA_CORE_RC4_1.md §9.3 & §9.4 (`SurfaceReadoutLedgerV1`, attestation rules, collision failure modes)
- DGCA_CORE_RC4_1.md §14 (`LG-T03`, `LG-T08`, `LG-T09`, `LG-T10`, `LG-T12`, `LG-T16`)
- DGCA_LLA_RC4_1.md §7.1 (Generation and readout invariants)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from dgca.common.errors import StatusCode
from dgca.encoder.envelope import Marker, PeripheralSurfaceEnvelopeV1
from dgca.peripheral.outbox import OutboxNotificationV1

# Normative attestation threshold across distinct completed external roots (Core §9.4, LG-T09)
MIN_ATTESTED_EXTERNAL_ROOTS: int = 2


@dataclass(slots=True)
class LedgerCandidateRow:
    """Single peripheral tuple candidate tracked for an (AssemblyID, structural_generation) key (Core §9.4)."""

    assembly_id: int
    structural_generation: int
    surface_utf8_nfc: str
    marker: Marker
    surface_sha256: bytes
    feature_bundle_digest: bytes
    envelope: PeripheralSurfaceEnvelopeV1
    confirmed_roots: set[int] = field(default_factory=set)

    @property
    def tuple_key(self) -> tuple[str, Marker, bytes]:
        return (self.surface_utf8_nfc, self.marker, self.feature_bundle_digest)

    @property
    def external_count(self) -> int:
        return len(self.confirmed_roots)

    @property
    def is_attested(self) -> bool:
        return len(self.confirmed_roots) >= MIN_ATTESTED_EXTERNAL_ROOTS

    def clone(self) -> LedgerCandidateRow:
        return LedgerCandidateRow(
            assembly_id=self.assembly_id,
            structural_generation=self.structural_generation,
            surface_utf8_nfc=self.surface_utf8_nfc,
            marker=self.marker,
            surface_sha256=self.surface_sha256,
            feature_bundle_digest=self.feature_bundle_digest,
            envelope=self.envelope,
            confirmed_roots=set(self.confirmed_roots),
        )


@dataclass(frozen=True, slots=True)
class ResolveReadoutResult:
    """Result of resolving peripheral readout for a winning (AssemblyID, structural_generation) (Core §9.4)."""

    status: StatusCode
    assembly_id: int
    structural_generation: int
    envelope: PeripheralSurfaceEnvelopeV1 | None
    external_count: int


class SurfaceReadoutLedgerV1:
    """Peripheral-only readout ledger keyed by (AssemblyID, structural_generation) (Core §9.4).

    Strictly outside Core W/H/R state:
    - Never consulted during neural competition (`ZERO_SELECTION_LEAKAGE`).
    - Consumes idempotent `END_EXPOSURE` outbox notifications.
    - Requires `external_count >= 2` across distinct completed external roots before attestation.
    - Explicitly detects multi-surface and same-surface/different-bundle collisions (`LG-T08`).
    """

    def __init__(self, *, available: bool = True) -> None:
        self.available: bool = available
        self._rows_by_asm_gen: dict[tuple[int, int], dict[tuple[str, Marker, bytes], LedgerCandidateRow]] = {}
        self._bundles_by_surface: dict[tuple[int, int, str, Marker], set[bytes]] = {}
        self._processed_outbox_keys: set[tuple[int, int, int, int, bytes, bytes]] = set()

    def clone(self) -> SurfaceReadoutLedgerV1:
        """Create an isolated snapshot of the ledger for read-only GENERATE_EPISODE sessions (Core §9.3)."""
        copy_ledger = SurfaceReadoutLedgerV1(available=self.available)
        for asm_key, row_map in self._rows_by_asm_gen.items():
            copy_ledger._rows_by_asm_gen[asm_key] = {
                t_key: row.clone() for t_key, row in row_map.items()
            }
        for surf_key, digests in self._bundles_by_surface.items():
            copy_ledger._bundles_by_surface[surf_key] = set(digests)
        copy_ledger._processed_outbox_keys = set(self._processed_outbox_keys)
        return copy_ledger

    def consume_outbox_notification(self, notif: OutboxNotificationV1) -> bool:
        """Idempotently consume an END_EXPOSURE outbox notification (Core §9.4, LG-T16).

        Returns True if the notification contributed a new root observation to the candidate row,
        or False if it was a duplicate notification / duplicate root for the same candidate row.
        """
        idem_key = notif.idempotency_key
        if idem_key in self._processed_outbox_keys:
            return False
        self._processed_outbox_keys.add(idem_key)

        asm_key = (notif.assembly_id, notif.structural_generation)
        row_map = self._rows_by_asm_gen.setdefault(asm_key, {})

        t_key = (
            notif.envelope.surface_utf8_nfc,
            notif.marker,
            notif.feature_bundle_digest,
        )
        surf_key = (
            notif.assembly_id,
            notif.structural_generation,
            notif.envelope.surface_utf8_nfc,
            notif.marker,
        )
        self._bundles_by_surface.setdefault(surf_key, set()).add(notif.feature_bundle_digest)

        row = row_map.get(t_key)
        if row is None:
            row = LedgerCandidateRow(
                assembly_id=notif.assembly_id,
                structural_generation=notif.structural_generation,
                surface_utf8_nfc=notif.envelope.surface_utf8_nfc,
                marker=notif.marker,
                surface_sha256=notif.surface_sha256,
                feature_bundle_digest=notif.feature_bundle_digest,
                envelope=notif.envelope,
                confirmed_roots={notif.root_id},
            )
            row_map[t_key] = row
            return True

        if notif.root_id in row.confirmed_roots:
            return False
        row.confirmed_roots.add(notif.root_id)
        return True

    def consume_outbox_batch(self, notifications: Sequence[OutboxNotificationV1]) -> int:
        """Consume a batch of outbox notifications and return the count of newly recorded root observations."""
        added = 0
        for notif in notifications:
            if self.consume_outbox_notification(notif):
                added += 1
        return added

    def get_candidate_rows(
        self, assembly_id: int, structural_generation: int
    ) -> tuple[LedgerCandidateRow, ...]:
        """Return all candidate rows tracked for `(assembly_id, structural_generation)`."""
        row_map = self._rows_by_asm_gen.get((assembly_id, structural_generation), {})
        return tuple(row_map.values())

    def resolve_readout(
        self,
        assembly_id: int,
        structural_generation: int,
        *,
        current_live_generation: int | None = None,
    ) -> ResolveReadoutResult:
        """Resolve peripheral readout for a winning `(assembly_id, structural_generation)` (Core §9.4).

        Failure modes:
        - `READOUT_UNAVAILABLE` if ledger is unavailable.
        - `GEN_STOP_STALE_ASSEMBLY` if `current_live_generation` is provided and differs from `structural_generation`.
        - `READOUT_UNKNOWN` if no row exists or the single candidate row has `external_count < 2`.
        - `READOUT_AMBIGUOUS` if `>= 2` distinct candidate tuples are attested (`external_count >= 2`).
        - `READOUT_AMBIGUOUS_PENDING` if 1 tuple is attested alongside `>= 1` pending conflicting tuple,
          or `>= 2` conflicting pending tuples exist (including same-surface / different-bundle collisions; LG-T08).
        """
        if not self.available:
            return ResolveReadoutResult(
                status=StatusCode.READOUT_UNAVAILABLE,
                assembly_id=assembly_id,
                structural_generation=structural_generation,
                envelope=None,
                external_count=0,
            )

        if (
            current_live_generation is not None
            and current_live_generation != structural_generation
        ):
            return ResolveReadoutResult(
                status=StatusCode.GEN_STOP_STALE_ASSEMBLY,
                assembly_id=assembly_id,
                structural_generation=structural_generation,
                envelope=None,
                external_count=0,
            )

        row_map = self._rows_by_asm_gen.get((assembly_id, structural_generation))
        if not row_map:
            return ResolveReadoutResult(
                status=StatusCode.READOUT_UNKNOWN,
                assembly_id=assembly_id,
                structural_generation=structural_generation,
                envelope=None,
                external_count=0,
            )

        rows = list(row_map.values())
        attested_rows = [r for r in rows if r.is_attested]
        pending_rows = [r for r in rows if not r.is_attested]

        if len(attested_rows) >= 2:
            return ResolveReadoutResult(
                status=StatusCode.READOUT_AMBIGUOUS,
                assembly_id=assembly_id,
                structural_generation=structural_generation,
                envelope=None,
                external_count=max(r.external_count for r in attested_rows),
            )

        if len(attested_rows) == 1:
            winner_row = attested_rows[0]
            surf_key = (
                assembly_id,
                structural_generation,
                winner_row.surface_utf8_nfc,
                winner_row.marker,
            )
            distinct_bundles_for_surface = self._bundles_by_surface.get(surf_key, set())
            if pending_rows or len(distinct_bundles_for_surface) > 1:
                return ResolveReadoutResult(
                    status=StatusCode.READOUT_AMBIGUOUS_PENDING,
                    assembly_id=assembly_id,
                    structural_generation=structural_generation,
                    envelope=None,
                    external_count=winner_row.external_count,
                )
            return ResolveReadoutResult(
                status=StatusCode.OK,
                assembly_id=assembly_id,
                structural_generation=structural_generation,
                envelope=winner_row.envelope,
                external_count=winner_row.external_count,
            )

        # Zero attested rows: check if multiple conflicting pending rows exist (LG-T08)
        if len(pending_rows) >= 2:
            return ResolveReadoutResult(
                status=StatusCode.READOUT_AMBIGUOUS_PENDING,
                assembly_id=assembly_id,
                structural_generation=structural_generation,
                envelope=None,
                external_count=max(r.external_count for r in pending_rows),
            )

        single_pending = pending_rows[0]
        return ResolveReadoutResult(
            status=StatusCode.READOUT_UNKNOWN,
            assembly_id=assembly_id,
            structural_generation=structural_generation,
            envelope=None,
            external_count=single_pending.external_count,
        )
