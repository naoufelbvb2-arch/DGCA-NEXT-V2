"""END_EXPOSURE Peripheral Outbox Notification Contract (Core §9.4, LLA §7.1).

Normative references:
- DGCA_CORE_RC4_1.md §9.4 (`SurfaceReadoutLedgerV1` and idempotent END_EXPOSURE outbox contract)
- DGCA_CORE_RC4_1.md §14 (`LG-T03`, `LG-T08`, `LG-T09`, `LG-T16`)
- DGCA_LLA_RC4_1.md §7.1 (Generation and readout invariants)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dgca.common.hashing import Region
from dgca.core.assembly import (
    RHO_CORE,
    THETA_FRESH_ADMIT,
    compute_core_coverage,
    compute_m_fresh,
)
from dgca.core.dynamics import EventExecutionResult
from dgca.core.state import Assembly, AssemblyStatus, HSlowState, WState
from dgca.encoder.envelope import EventOrigin, Marker, PeripheralSurfaceEnvelopeV1


@dataclass(frozen=True, slots=True)
class OutboxNotificationV1:
    """Idempotent peripheral outbox notification emitted after END_EXPOSURE commit (Core §9.4)."""

    root_id: int
    event_order: int
    assembly_id: int
    structural_generation: int
    surface_sha256: bytes
    feature_bundle_digest: bytes
    marker: Marker
    envelope: PeripheralSurfaceEnvelopeV1

    @property
    def idempotency_key(self) -> tuple[int, int, int, int, bytes, bytes]:
        """Exact idempotency key per Core §9.4:
        (root_id, event_order, AssemblyID, structural_generation, surface_sha256, feature_bundle_digest).
        """
        return (
            self.root_id,
            self.event_order,
            self.assembly_id,
            self.structural_generation,
            self.surface_sha256,
            self.feature_bundle_digest,
        )


def build_end_exposure_outbox_notifications(
    exposure_id: int,
    w_post_close: WState,
    h_slow: HSlowState,
    event_results: Sequence[EventExecutionResult],
    peripheral_envelopes_by_order: Mapping[int, PeripheralSurfaceEnvelopeV1],
    *,
    preexisting_live_assemblies: Sequence[Assembly],
) -> tuple[OutboxNotificationV1, ...]:
    """Construct idempotent END_EXPOSURE peripheral outbox notifications (Core §9.4, LG-T03, LG-T09).

    Normative rules:
    1. Only external events with origin == EXTERNAL_DIRECT that have a matching
       PeripheralSurfaceEnvelopeV1 are eligible.
    2. Only Assemblies that ALREADY existed LIVE before the root's events with the exact same
       `structural_generation` AND remain LIVE with that exact `structural_generation` in
       `w_post_close` can receive external attestation (`no backdating` of newly formed or
       mutated assemblies in the same root; Core §9.4, LG-T03, LG-T16).
    3. Assembly A must satisfy both:
         CoreCoverage(A, e_t) >= theta_cov (0.70)
         M_fresh(A, e_t) >= theta_fresh (0.40)
    """
    preexisting_by_id: dict[int, int] = {
        asm.assembly_id: asm.structural_generation
        for asm in preexisting_live_assemblies
        if asm.status == AssemblyStatus.LIVE and asm.region == Region.LANGUAGE
    }

    eligible_assemblies: list[Assembly] = []
    for asm_id, pre_gen in sorted(preexisting_by_id.items()):
        post_asm = w_post_close.assemblies.get(asm_id)
        if (
            post_asm is not None
            and post_asm.status == AssemblyStatus.LIVE
            and post_asm.region == Region.LANGUAGE
            and post_asm.structural_generation == pre_gen
        ):
            eligible_assemblies.append(post_asm)

    if not eligible_assemblies:
        return ()

    notifications: list[OutboxNotificationV1] = []
    for ev in event_results:
        if ev.origin != EventOrigin.EXTERNAL_DIRECT:
            continue
        envelope = peripheral_envelopes_by_order.get(ev.event_order)
        if envelope is None:
            continue
        ev_digest = getattr(ev, "feature_bundle_digest", None)
        if ev_digest is not None and envelope.feature_bundle_digest != ev_digest:
            continue

        for asm in eligible_assemblies:
            cov = compute_core_coverage(asm, ev, h_slow)
            if cov < RHO_CORE:
                continue
            mfresh = compute_m_fresh(asm, ev)
            if mfresh < THETA_FRESH_ADMIT:
                continue

            notifications.append(
                OutboxNotificationV1(
                    root_id=exposure_id,
                    event_order=ev.event_order,
                    assembly_id=asm.assembly_id,
                    structural_generation=asm.structural_generation,
                    surface_sha256=envelope.surface_sha256,
                    feature_bundle_digest=envelope.feature_bundle_digest,
                    marker=envelope.marker,
                    envelope=envelope,
                )
            )

    return tuple(notifications)
