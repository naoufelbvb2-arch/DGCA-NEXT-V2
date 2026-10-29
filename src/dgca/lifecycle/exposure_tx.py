"""Atomic Exposure Transaction Lifecycle (BEGIN, EVENT, END, ABORT) and Read-Only Episodes.

Normative references:
- DGCA_CORE_RC4_1.md §9.1 (READ_ONLY_EPISODE contract and PredScore)
- DGCA_CORE_RC4_1.md §10.1 (Learning exposure lifecycle and FIFR-B06 LAB POLICY A)
- DGCA_CORE_RC4_1.md §10.2 (Canonical close order)
- DGCA_CORE_RC4_1.md §11 (Cold reset, snapshots, serialization, and reproducibility)
- DGCA_LLA_RC4_1.md §7 (Complete root/event execution contract for learning)
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class frozendict(dict):
    """Immutable mapping preserving standard dict interfaces (Core §10.2)."""

    def __setitem__(self, key: object, value: object) -> None:
        raise TypeError("frozendict is immutable")

    def __delitem__(self, key: object) -> None:
        raise TypeError("frozendict is immutable")

    def clear(self) -> None:
        raise TypeError("frozendict is immutable")

    def pop(self, *args: object, **kwargs: object) -> object:
        raise TypeError("frozendict is immutable")

    def popitem(self) -> tuple[object, object]:
        raise TypeError("frozendict is immutable")

    def setdefault(self, *args: object, **kwargs: object) -> object:
        raise TypeError("frozendict is immutable")

    def update(self, *args: object, **kwargs: object) -> None:
        raise TypeError("frozendict is immutable")

    def copy(self) -> frozendict:
        return self


@dataclass(frozen=True, slots=True)
class TransactionPublicationView:
    """Immutable, atomically-published transaction view (Core §10.2, R2-A01 Patch 4).

    A single pointer swap makes the entire state transition visible simultaneously.
    """

    W: WState
    completed_roots: frozendict[int, EndExposureReport]
    pending_outbox_by_root: frozendict[int, tuple[object, ...]]
    completed_roots_high_watermark: int
    active_exposure_id: int | None

from dgca.common.errors import DGCAError, ObservationError, StatusCode
from dgca.common.hashing import Region
from dgca.core.anatomy import SynapseKey, SynapseScope
from dgca.core.dynamics import (
    EventExecutionResult,
    K_R_PER_EVENT,
    compute_next_step_temporal_drive,
    execute_two_pass_event,
)
from dgca.core.latent_index import LatentNeighborhoodTable
from dgca.core.sic_v1 import SICProjectionResult, project_core_event_v1
from dgca.core.state import ExecutionMode, HSlowState, MachineState, WState
from dgca.encoder.decomposer import (
    EOS_CANONICAL_FEATURES,
    decompose_lexical_token,
    finalize_feature_bundle,
)
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
)
from dgca.encoder.segmenter import EOS_RAW_SURFACE
from dgca.lla.proposals import (
    LinkProposal,
    THETA_CREATE_CROSS,
    THETA_CREATE_DEFAULT,
    generate_event_link_proposals,
)
from dgca.lla.synapse_ledger import (
    ProposalApplicationOutcome,
    W_CONF_CONTEXT,
    W_CONF_ORDINARY,
    apply_root_proposals_to_shadow_w,
    prune_expired_candidate_synapses,
)
from dgca.lla.witness import ObservationScope, ObservationWitness


@dataclass(frozen=True, slots=True)
class CanonicalEnvelopeIdentity:
    """Immutable identity record for a peripheral surface envelope (Core §9.4, Encoder §4)."""

    raw_surface_nfc_utf8: str
    surface_sha256: bytes
    feature_bundle_digest: bytes
    canonical_features_copy: tuple[tuple[str, str], ...]
    marker: Marker

    @classmethod
    def from_envelope(cls, envelope: PeripheralSurfaceEnvelopeV1) -> CanonicalEnvelopeIdentity:
        return cls(
            raw_surface_nfc_utf8=envelope.raw_surface_nfc_utf8,
            surface_sha256=envelope.surface_sha256,
            feature_bundle_digest=envelope.feature_bundle_digest,
            canonical_features_copy=tuple(envelope.canonical_features_copy),
            marker=envelope.marker,
        )


@dataclass(frozen=True, slots=True)
class EventIdentityKey:
    """Comprehensive canonical identity covering both Core neural payload and peripheral envelope."""

    exposure_id: int | None
    event_order: int
    modality: Region
    origin: EventOrigin
    boundary: bool
    salience: str
    features: tuple[tuple[str, str], ...]
    feature_bundle_digest: bytes
    observation_scope: ObservationScope
    envelope_identity: CanonicalEnvelopeIdentity | None

    @classmethod
    def from_event(
        cls,
        core_event: CoreEventPayloadV1,
        *,
        observation_scope: ObservationScope,
        envelope: PeripheralSurfaceEnvelopeV1 | None = None,
    ) -> EventIdentityKey:
        return cls(
            exposure_id=core_event.exposure_id,
            event_order=core_event.event_order,
            modality=core_event.modality,
            origin=core_event.origin,
            boundary=core_event.boundary,
            salience=core_event.salience,
            features=tuple(core_event.features),
            feature_bundle_digest=core_event.feature_bundle_digest,
            observation_scope=observation_scope,
            envelope_identity=(
                CanonicalEnvelopeIdentity.from_envelope(envelope)
                if envelope is not None
                else None
            ),
        )


def validate_event_envelope_provenance(
    core_event: CoreEventPayloadV1,
    envelope: PeripheralSurfaceEnvelopeV1 | None,
    projection: SICProjectionResult,
    *,
    allow_headless_events: bool = False,
) -> None:
    """Validate mechanical provenance between raw surface envelope and Core neural event (R2-A01 Patch 1)."""
    # 1. Structural neural event precheck (independent of peripheral envelope - Correction C02)
    is_canonical_eos_features = (
        core_event.features == EOS_CANONICAL_FEATURES
        or any(feat[0].startswith("\x1fEOS") for feat in core_event.features)
    )
    if is_canonical_eos_features:
        if core_event.event_order == 0:
            raise ObservationError(
                "Canonical EOS event cannot be event_order 0 alone (empty exposure)",
                code=StatusCode.EMPTY_LEXICAL_EXPOSURE,
            )
        if core_event.boundary:
            raise ObservationError(
                "Canonical EOS event cannot have boundary=True",
                code=StatusCode.PROVENANCE_MARKER_MISMATCH,
            )

    # 2. Headless check
    if envelope is None:
        if not allow_headless_events:
            raise ObservationError(
                "Peripheral envelope is required for external language events (allow_headless_events=False)",
                code=StatusCode.PROVENANCE_ENVELOPE_MISSING,
            )
        return

    # 3. Modality validation for language peripheral envelope (Correction C01)
    if core_event.modality != Region.LANGUAGE:
        raise ObservationError(
            f"Language peripheral envelope requires Region.LANGUAGE, got {core_event.modality}",
            code=StatusCode.INVALID_OBSERVATION,
        )

    # 4. Raw surface string type, UTF-8 validity, NFC normalization, and SHA-256 integrity
    if not isinstance(envelope.raw_surface_nfc_utf8, str):
        raise ObservationError(
            f"Envelope raw_surface_nfc_utf8 must be str, got {type(envelope.raw_surface_nfc_utf8).__name__}",
            code=StatusCode.INVALID_OBSERVATION,
        )

    for ch in envelope.raw_surface_nfc_utf8:
        cp = ord(ch)
        if 0xD800 <= cp <= 0xDFFF:
            raise ObservationError(
                f"Lone surrogate U+{cp:04X} rejected in envelope surface",
                code=StatusCode.INVALID_OBSERVATION,
            )

    if not unicodedata.is_normalized("NFC", envelope.raw_surface_nfc_utf8):
        raise ObservationError(
            "Envelope raw_surface_nfc_utf8 is not canonical NFC",
            code=StatusCode.INVALID_OBSERVATION,
        )

    computed_surface_hash = hashlib.sha256(
        envelope.raw_surface_nfc_utf8.encode("utf-8")
    ).digest()
    if envelope.surface_sha256 != computed_surface_hash:
        raise ObservationError(
            "Envelope surface_sha256 does not match sha256(raw_surface_nfc_utf8)",
            code=StatusCode.INVALID_SURFACE_HASH,
        )

    # 3. Marker & reserved surface validation
    is_eos = (envelope.marker == Marker.EOS)
    if is_eos:
        if envelope.raw_surface_nfc_utf8 != EOS_RAW_SURFACE:
            raise ObservationError(
                f"Canonical EOS envelope raw surface must be {EOS_RAW_SURFACE!r}, got {envelope.raw_surface_nfc_utf8!r}",
                code=StatusCode.PROVENANCE_MARKER_MISMATCH,
            )
        if core_event.boundary:
            raise ObservationError(
                "Canonical EOS event cannot have boundary=True",
                code=StatusCode.PROVENANCE_MARKER_MISMATCH,
            )
        if core_event.event_order == 0:
            raise ObservationError(
                "Canonical EOS event cannot be event_order 0 alone (empty exposure)",
                code=StatusCode.EMPTY_LEXICAL_EXPOSURE,
            )
        raw_expected_features = EOS_CANONICAL_FEATURES
    elif envelope.marker == Marker.NONE:
        if "\x1f" in envelope.raw_surface_nfc_utf8:
            raise ObservationError(
                "Lexical token envelope contains reserved control characters",
                code=StatusCode.PROVENANCE_MARKER_MISMATCH,
            )
        try:
            raw_expected_features = decompose_lexical_token(envelope.raw_surface_nfc_utf8)
        except Exception as exc:
            raise ObservationError(
                f"Raw surface cannot be decomposed into valid lexical features: {exc}",
                code=StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH,
            ) from exc
    else:
        raise ObservationError(
            f"Unsupported envelope marker: {envelope.marker}",
            code=StatusCode.PROVENANCE_MARKER_MISMATCH,
        )

    # 4. Finalize canonical features and bundle digest using core_event.salience
    canonical_features, _, salience_u, expected_digest = finalize_feature_bundle(
        raw_expected_features,
        salience=core_event.salience,
        allow_reserved_control=is_eos,
    )

    if core_event.features != canonical_features:
        raise ObservationError(
            "CoreEventPayload features do not match canonical features derived from raw surface",
            code=StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH,
        )
    if envelope.canonical_features_copy != canonical_features:
        raise ObservationError(
            "Envelope canonical_features_copy does not match canonical features derived from raw surface",
            code=StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH,
        )
    if core_event.feature_bundle_digest != expected_digest:
        raise ObservationError(
            "CoreEventPayload feature_bundle_digest does not match digest of derived features",
            code=StatusCode.PROVENANCE_DIGEST_MISMATCH,
        )
    if envelope.feature_bundle_digest != expected_digest:
        raise ObservationError(
            "Envelope feature_bundle_digest does not match digest of derived features",
            code=StatusCode.PROVENANCE_DIGEST_MISMATCH,
        )
    if projection.feature_bundle_digest != expected_digest:
        raise ObservationError(
            "SIC projection feature_bundle_digest does not match digest of derived features",
            code=StatusCode.PROVENANCE_DIGEST_MISMATCH,
        )


class ExposureStatus(StrEnum):
    """Lifecycle state of an exposure transaction (Core §10.1)."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


@dataclass(slots=True)
class OpenExposureJournal:
    """Durable checkpoint journal for an currently OPEN learning exposure (Core §10.1, §11)."""

    exposure_id: int
    status: ExposureStatus
    h_slow_begin: HSlowState
    h_slow_event: HSlowState
    latent_table_begin: LatentNeighborhoodTable | None = None
    next_event_order: int = 0
    next_proposal_ordinal: int = 0
    last_event_remaining_k_r: int = K_R_PER_EVENT
    event_results: list[EventExecutionResult] = field(default_factory=list)
    observation_witnesses: list[ObservationWitness] = field(default_factory=list)
    staged_proposals: list[LinkProposal] = field(default_factory=list)
    peripheral_envelopes_by_order: dict[int, PeripheralSurfaceEnvelopeV1] = field(
        default_factory=dict
    )
    event_identities: dict[int, EventIdentityKey] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EndExposureReport:
    """Comprehensive atomic publication report returned by END_EXPOSURE (Core §10.2)."""

    exposure_id: int
    status: ExposureStatus
    events_processed: int
    proposal_outcomes: tuple[ProposalApplicationOutcome, ...]
    pruned_synapses: tuple[SynapseKey, ...]
    last_event_remaining_k_r: int
    diagnostics: tuple[StatusCode, ...]
    candidate_settlements: tuple[object, ...] = ()
    recruitments: tuple[object, ...] = ()
    assembly_report: object | None = None
    outbox_notifications: tuple[object, ...] = ()


# Optional hook signature for Phase 4/5/6 END_EXPOSURE extensions:
# (w_pre_close, w_shadow, h_slow, open_journal, diagnostics_list) -> None
EndExposureHook = Callable[
    [WState, WState, HSlowState, OpenExposureJournal, list[StatusCode]],
    None,
]


def _update_coactive_latent_neighborhoods_for_event(
    w: WState,
    curr_event: EventExecutionResult,
    prev_event: EventExecutionResult | None,
    protected_in_open_root: set[tuple[int, int]],
) -> None:
    """Populate co-active latent neighborhood slots (0..5 intra, 12..17 inter) for active cells (Core §1.3, Encoder §2.1).

    Follows Core §1.3 priority:
        legal live-link protection > committed contextual pin > open-root proposal protection > unprotected slot.
    Ranks same-event L_t peers and prior-event F_step(t-1) peers by (-activity, cell_id) so that
    Tier-0 (F0) cells deterministically win top co-active intra slots of one another.
    """
    active_curr = sorted(
        curr_event.l_frontier & curr_event.obs_eligible_cells,
        key=lambda cid: (-curr_event.a_plus_by_cell.get(cid, 0.0), cid),
    )
    active_prev = (
        sorted(
            prev_event.f_step & prev_event.obs_eligible_cells,
            key=lambda cid: (-prev_event.a_plus_by_cell.get(cid, 0.0), cid),
        )
        if (prev_event is not None and not curr_event.boundary)
        else []
    )

    top_curr_clique = active_curr[:4]
    secondary_curr_clique = active_curr[4:]

    for cid in active_curr:
        if w.is_contextual_cell(cid):
            # Contextual cells manage their 6 co-active intra slots via §7.3 2/2/2 pinning
            continue

        protected = w.get_protected_bidirectional_neighbors(cid) | {
            partner for src, partner in protected_in_open_root if src == cid
        }

        # Partition top-4 F0 clique from secondary sub-lexical peers so F0 cells maintain high Spec(x, A) >= 0.20
        peer_pool = top_curr_clique if cid in top_curr_clique else secondary_curr_clique
        same_event_limit = 3 if active_prev else 6
        same_peers = [p for p in peer_pool if p != cid][:same_event_limit]
        prev_peers = [p for p in active_prev if p != cid and p not in same_peers][:3]
        desired_partners = same_peers + prev_peers

        for partner_id in desired_partners:
            if w.latent_table.is_eligible(cid, partner_id):
                protected_in_open_root.add((cid, partner_id))
                protected_in_open_root.add((partner_id, cid))
                continue
            try:
                w.latent_table.admit_or_recycle_coactive_partner(
                    cid,
                    partner_id,
                    protected_bidirectional_neighbors=protected,
                    event_clock=w.global_event_clock,
                    reason="ORDINARY_COACTIVE",
                )
                protected.add(partner_id)
                protected_in_open_root.add((cid, partner_id))
                protected_in_open_root.add((partner_id, cid))
            except DGCAError:
                # If all co-active slots are protected or pinned, skip without error
                continue


class ExposureTransactionManager:
    """Manages atomic BEGIN_EXPOSURE, EVENT, END_EXPOSURE, and ABORT_EXPOSURE transactions (Core §10, LLA §7)."""

    def __init__(
        self,
        state: MachineState,
        *,
        theta_create: float = THETA_CREATE_DEFAULT,
        theta_create_x: float = THETA_CREATE_CROSS,
        w_conf: int = W_CONF_ORDINARY,
        w_conf_context: int = W_CONF_CONTEXT,
        auto_coactive_latent: bool = True,
        enable_context_pipeline: bool = True,
        enable_assembly_pipeline: bool = True,
        min_additional_opportunities: int = 0,
        readout_ledger: object | None = None,
        allow_headless_events: bool = False,
    ) -> None:
        self.state: MachineState = state
        self.theta_create: float = theta_create
        self.theta_create_x: float = theta_create_x
        self.w_conf: int = w_conf
        self.w_conf_context: int = w_conf_context
        self.auto_coactive_latent: bool = auto_coactive_latent
        self.enable_context_pipeline: bool = enable_context_pipeline
        self.enable_assembly_pipeline: bool = enable_assembly_pipeline
        self.min_additional_opportunities: int = min_additional_opportunities
        self.readout_ledger: object | None = readout_ledger
        self.allow_headless_events: bool = allow_headless_events

        self.open_journal: OpenExposureJournal | None = None
        self._publication_view = TransactionPublicationView(
            W=state.W,
            completed_roots=frozendict(),
            pending_outbox_by_root=frozendict(),
            completed_roots_high_watermark=state.W.completed_roots_high_watermark,
            active_exposure_id=None,
        )
        self.aborted_roots: dict[int, HSlowState] = {}
        self._protected_open_root_pairs: set[tuple[int, int]] = set()
        self._end_exposure_hooks: list[EndExposureHook] = []
        self._fault_injection_point: str | None = None

    @property
    def publication_view(self) -> TransactionPublicationView:
        return self._publication_view

    @property
    def completed_roots(self) -> frozendict[int, EndExposureReport]:
        return self._publication_view.completed_roots

    @property
    def pending_outbox_by_root(self) -> frozendict[int, tuple[object, ...]]:
        return self._publication_view.pending_outbox_by_root

    @property
    def status(self) -> ExposureStatus:
        if self.open_journal is not None:
            return ExposureStatus.OPEN
        return ExposureStatus.CLOSED

    def has_pending_outbox(self, exposure_id: int | None = None) -> bool:
        """Check whether pending outbox notifications exist."""
        if exposure_id is None:
            return len(self._publication_view.pending_outbox_by_root) > 0
        return exposure_id in self._publication_view.pending_outbox_by_root

    def pending_outbox_count(self, exposure_id: int | None = None) -> int:
        """Return the count of pending outbox notifications."""
        if exposure_id is None:
            return sum(
                len(batch) for batch in self._publication_view.pending_outbox_by_root.values()
            )
        batch = self._publication_view.pending_outbox_by_root.get(exposure_id)
        return len(batch) if batch else 0

    def assert_outbox_ready(self, exposure_id: int | None = None) -> None:
        """Raise ObservationError if pending outbox notifications remain unconsumed."""
        if self.has_pending_outbox(exposure_id):
            if exposure_id is not None:
                count = self.pending_outbox_count(exposure_id)
                msg = f"Pending outbox notifications ({count}) remain unconsumed for root {exposure_id}"
            else:
                total = self.pending_outbox_count()
                roots = sorted(self._publication_view.pending_outbox_by_root.keys())
                msg = f"Pending outbox notifications ({total}) remain unconsumed across roots {roots}"
            raise ObservationError(msg, code=StatusCode.OUTBOX_DELIVERY_PENDING)

    def reconcile_outbox(
        self,
        exposure_id: int | None = None,
        ledger: object | None = None,
    ) -> int:
        """Explicitly dispatch pending outbox notifications outside read-only execution.

        Idempotent; clears roots from the pending view on success.
        """
        target_ledger = ledger if ledger is not None else self.readout_ledger
        if target_ledger is None:
            return 0

        roots = (
            [exposure_id]
            if exposure_id is not None
            else sorted(self._publication_view.pending_outbox_by_root.keys())
        )
        delivered = 0
        for rid in roots:
            batch = self._publication_view.pending_outbox_by_root.get(rid)
            if not batch:
                continue
            if hasattr(target_ledger, "consume_outbox_batch"):
                delivered += target_ledger.consume_outbox_batch(batch)

            new_pending = dict(self._publication_view.pending_outbox_by_root)
            new_pending.pop(rid, None)
            self._publication_view = TransactionPublicationView(
                W=self._publication_view.W,
                completed_roots=self._publication_view.completed_roots,
                pending_outbox_by_root=frozendict(new_pending),
                completed_roots_high_watermark=self._publication_view.completed_roots_high_watermark,
                active_exposure_id=self._publication_view.active_exposure_id,
            )
        return delivered

    def register_end_exposure_hook(self, hook: EndExposureHook) -> None:
        """Register a post-evidence shadow transaction hook (used by Phase 4/5/6 operators)."""
        self._end_exposure_hooks.append(hook)

    def begin_exposure(self, exposure_id: int) -> OpenExposureJournal:
        """Execute atomic BEGIN_EXPOSURE(root) (Core §10.1, LLA §7 rule 1).

        - Retry of an already-OPEN root with the same exposure_id does NOT reset twice.
        - Otherwise requires status == CLOSED and strictly increasing exposure_id.
        - Atomically captures H_slow_BEGIN (FIFR-B06 LAB POLICY A) and resets R to R_cold.
        """
        if not isinstance(exposure_id, int) or isinstance(exposure_id, bool) or exposure_id <= 0:
            raise ObservationError(f"exposure_id must be a positive integer, got {exposure_id!r}")

        if self.open_journal is not None:
            if self.open_journal.exposure_id == exposure_id:
                # Core §10.1: Retry OPEN root does not reset twice
                return self.open_journal
            raise ObservationError(
                f"Cannot BEGIN_EXPOSURE({exposure_id}) while root {self.open_journal.exposure_id} is OPEN"
            )

        if (
            exposure_id <= self.state.W.completed_roots_high_watermark
            or exposure_id <= self._publication_view.completed_roots_high_watermark
            or exposure_id in self.completed_roots
            or exposure_id in self.aborted_roots
        ):
            raise ObservationError(
                f"Root ID {exposure_id} is not strictly increasing (watermark={self._publication_view.completed_roots_high_watermark})"
            )

        # FIFR-B06 LAB POLICY A: capture immutable H_slow_BEGIN before any root-local adaptation
        h_begin = self.state.H_slow.clone()
        # R2-A01 Patch 3: capture immutable LatentNeighborhoodTable at BEGIN
        latent_begin = self.state.W.latent_table.clone()
        self.state.R.reset_cold()
        self._protected_open_root_pairs.clear()

        self.open_journal = OpenExposureJournal(
            exposure_id=exposure_id,
            status=ExposureStatus.OPEN,
            h_slow_begin=h_begin,
            h_slow_event=h_begin.clone(),
            latent_table_begin=latent_begin,
            next_event_order=0,
            next_proposal_ordinal=0,
            last_event_remaining_k_r=K_R_PER_EVENT,
        )
        self._publication_view = TransactionPublicationView(
            W=self._publication_view.W,
            completed_roots=self._publication_view.completed_roots,
            pending_outbox_by_root=self._publication_view.pending_outbox_by_root,
            completed_roots_high_watermark=self._publication_view.completed_roots_high_watermark,
            active_exposure_id=exposure_id,
        )
        return self.open_journal

    def process_event(
        self,
        core_event: CoreEventPayloadV1,
        *,
        observation_scope: ObservationScope = ObservationScope.COMPLETE_NEXT_EVENT,
        allow_candidate_probe: bool = True,
        peripheral_envelope: PeripheralSurfaceEnvelopeV1 | None = None,
    ) -> EventExecutionResult:
        """Process a single contiguous EVENT(order=0..n-1) inside an OPEN exposure (Core §10.1, LLA §7 rule 2).

        - Recovery of an already processed event_order returns the checkpointed result without re-adapting H_slow.
        - Event 0 always enforces boundary = True.
        - Stages LINK_PROPOSALs in open_journal without mutating W synapse evidence (S, E_ext, external_count).
        """
        if self.open_journal is None:
            raise ObservationError("Cannot process EVENT when no exposure is OPEN")
        journal = self.open_journal

        # Validate event order (Correction C03)
        order = core_event.event_order
        if isinstance(order, bool) or not isinstance(order, int):
            raise ObservationError(
                f"event_order must be a genuine int, got {type(order).__name__} ({order!r})",
                code=StatusCode.INVALID_OBSERVATION,
            )
        if order < 0:
            raise ObservationError(
                f"event_order must be non-negative, got {order}",
                code=StatusCode.INVALID_OBSERVATION,
            )
        if order > journal.next_event_order:
            raise ObservationError(
                f"Out-of-order event_order {order}; expected {journal.next_event_order}",
                code=StatusCode.INVALID_OBSERVATION,
            )

        if core_event.exposure_id is not None and core_event.exposure_id != journal.exposure_id:
            raise ObservationError(
                f"Event exposure_id {core_event.exposure_id} does not match OPEN root {journal.exposure_id}"
            )
        if core_event.origin != EventOrigin.EXTERNAL_DIRECT:
            raise ObservationError(
                f"OPEN learning exposure requires EXTERNAL_DIRECT origin, got {core_event.origin}"
            )

        # 1. Project SIC-V1 (stateless mathematical projection)
        projection = project_core_event_v1(core_event)

        # 2. Strict Pre-Execution Provenance Validation (runs on ALL events, including retries)
        validate_event_envelope_provenance(
            core_event,
            peripheral_envelope,
            projection,
            allow_headless_events=self.allow_headless_events,
        )

        current_identity = EventIdentityKey.from_event(
            core_event,
            observation_scope=observation_scope,
            envelope=peripheral_envelope,
        )

        # 3. Crash/retry idempotency & conflict detection
        if core_event.event_order < journal.next_event_order:
            recorded_identity = journal.event_identities[core_event.event_order]

            # Detect a forbidden change in provenance channel
            if (recorded_identity.envelope_identity is None) != (current_identity.envelope_identity is None):
                raise ObservationError(
                    "Cannot alter provenance channel on event retry (headless <-> enveloped)",
                    code=StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION,
                )

            # Compare accepted event identity
            if current_identity != recorded_identity:
                raise ObservationError(
                    f"Conflicting event identity on retry for event_order {core_event.event_order}",
                    code=StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT,
                )

            # Return cached result only for exact equality (zero side-effects)
            return journal.event_results[core_event.event_order]

        if core_event.event_order != journal.next_event_order:
            raise ObservationError(
                f"Non-contiguous event_order {core_event.event_order}; expected {journal.next_event_order}"
            )

        # Core §10.1 & LLA §7 rule 1: first event boundary flag is normalized True
        effective_boundary = True if core_event.event_order == 0 else core_event.boundary

        witness = ObservationWitness.from_projection(
            projection,
            exposure_id=journal.exposure_id,
            event_order=core_event.event_order,
            origin=core_event.origin,
            scope=observation_scope,
        )

        # Snapshot pre-event H_slow for proposal y_positive calculation (before event's slow adaptation)
        h_slow_pre_event = self.state.H_slow.clone()

        # 2. Execute two-pass neural dynamics
        ev_result = execute_two_pass_event(
            self.state,
            projection.x_fixed_by_global_id,
            projection.x_float_by_global_id,
            mode=ExecutionMode.LEARN,
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=effective_boundary,
            exposure_id=journal.exposure_id,
            event_order=core_event.event_order,
            feature_bundle_digest=projection.feature_bundle_digest,
            allow_candidate_probe=allow_candidate_probe,
            admit_uncommitted_sensory=True,
            k_r_budget=K_R_PER_EVENT,
        )

        prev_event = journal.event_results[-1] if journal.event_results else None
        prev_prev_event = journal.event_results[-2] if len(journal.event_results) >= 2 else None

        # 3. Populate ordinary co-active latent slots if enabled
        if self.auto_coactive_latent:
            _update_coactive_latent_neighborhoods_for_event(
                self.state.W,
                ev_result,
                prev_event,
                self._protected_open_root_pairs,
            )

        # 4. Generate and stage LINK_PROPOSALs in the OPEN journal
        new_proposals, next_ord = generate_event_link_proposals(
            ev_result,
            prev_event,
            prev_prev_event,
            self.state.W,
            h_slow_pre_event,
            theta_create=self.theta_create,
            theta_create_x=self.theta_create_x,
            starting_ordinal=journal.next_proposal_ordinal,
        )

        journal.observation_witnesses.append(witness)
        journal.event_results.append(ev_result)
        journal.event_identities[core_event.event_order] = current_identity
        journal.staged_proposals.extend(new_proposals)
        if peripheral_envelope is not None:
            journal.peripheral_envelopes_by_order[core_event.event_order] = peripheral_envelope
        journal.next_proposal_ordinal = next_ord
        journal.next_event_order += 1
        journal.last_event_remaining_k_r = max(
            0, K_R_PER_EVENT - len(ev_result.newly_committed_sensory_cells)
        )
        journal.h_slow_event = self.state.H_slow.clone()

        return ev_result

    def abort_exposure(self, exposure_id: int) -> ExposureStatus:
        """Execute atomic ABORT_EXPOSURE (Core §10.1, LLA §7 rule 4, FIFR-B06 LAB POLICY A).

        - Restores H_slow = H_slow_BEGIN atomically.
        - Discards pending link proposals and uncommitted root staging.
        - Resets working R to R_cold.
        - Lawful sensory cell commitments in W.committed_cells remain.
        - Duplicate ABORT for the same root is idempotent status-only and never overwrites later roots.
        """
        if exposure_id in self.aborted_roots:
            # Core §10.1: Duplicate ABORT request for the same root is idempotent status-only
            return ExposureStatus.ABORTED
        if exposure_id in self.completed_roots:
            raise ObservationError(f"Cannot ABORT already COMPLETED root {exposure_id}")
        if self.open_journal is None or self.open_journal.exposure_id != exposure_id:
            raise ObservationError(f"Root {exposure_id} is not currently OPEN")

        journal = self.open_journal
        # FIFR-B06 LAB POLICY A: restore exact H_slow_BEGIN
        self.state.H_slow = journal.h_slow_begin.clone()
        # R2-A01 Patch 3: restore exact LatentNeighborhoodTable at BEGIN
        if journal.latent_table_begin is not None:
            self.state.W.latent_table = journal.latent_table_begin.clone()
        self.state.R.reset_cold()
        self._protected_open_root_pairs.clear()

        self.aborted_roots[exposure_id] = journal.h_slow_begin.clone()
        new_watermark = max(
            self.state.W.completed_roots_high_watermark,
            self._publication_view.completed_roots_high_watermark,
            exposure_id,
        )
        self.state.W.completed_roots_high_watermark = new_watermark
        self._publication_view = TransactionPublicationView(
            W=self._publication_view.W,
            completed_roots=self._publication_view.completed_roots,
            pending_outbox_by_root=self._publication_view.pending_outbox_by_root,
            completed_roots_high_watermark=new_watermark,
            active_exposure_id=None,
        )
        self.open_journal = None
        return ExposureStatus.ABORTED

    def end_exposure(self, exposure_id: int) -> EndExposureReport:
        """Execute atomic END_EXPOSURE in canonical close order (Core §10.2, LLA §7 rule 3).

        - Idempotent if exposure_id was already COMPLETED (crash/retry safety, LLA-T15).
        - Executes all updates on an isolated shadow W* before swapping into state.W atomically.
        """
        if exposure_id in self.completed_roots:
            return self.completed_roots[exposure_id]
        if exposure_id in self.aborted_roots:
            raise ObservationError(f"Cannot END already ABORTED root {exposure_id}")
        if self.open_journal is None or self.open_journal.exposure_id != exposure_id:
            raise ObservationError(f"Root {exposure_id} is not currently OPEN")
        if not self.open_journal.event_results:
            raise ObservationError(f"Cannot END_EXPOSURE({exposure_id}) with zero processed events")

        # FP-01 Fault Injection Gate
        if self._fault_injection_point == "FP_01":
            raise RuntimeError("Injected fault at FP-01: candidate/assembly preparation failure")

        journal = self.open_journal
        w_pre_close = self.state.W.clone()
        w_shadow = self.state.W.clone()
        diagnostics: list[StatusCode] = []

        # Step 1 & 2 & 3 (Core §10.2): Reduce proposals by (link_key, root) and apply to w_shadow
        outcomes, prop_diags = apply_root_proposals_to_shadow_w(
            journal.staged_proposals,
            w_pre_close,
            w_shadow,
            w_conf=self.w_conf,
            w_conf_context=self.w_conf_context,
        )
        diagnostics.extend(prop_diags)

        # Advance completed external events count and close serial on w_shadow
        w_shadow.completed_external_events_count += len(journal.event_results)
        w_shadow.close_serial += 1
        w_shadow.completed_roots_high_watermark = max(
            w_shadow.completed_roots_high_watermark,
            self._publication_view.completed_roots_high_watermark,
            exposure_id,
        )

        # Prune expired unpinned candidate synapses
        pruned_keys = prune_expired_candidate_synapses(w_shadow)

        # Step 3 & 4 (Core §10.2): Contextual candidate settlement, graduation, contrast discovery & recruitment
        accepted_keys = {
            out.proposal.link_key for out in outcomes if out.status == StatusCode.OK
        }
        settlements: list[object] = []
        recruitments: list[object] = []
        if self.enable_context_pipeline:
            from dgca.lla.candidate_fsm import execute_contextual_close_pipeline

            cand_res, rec_res, ctx_diags = execute_contextual_close_pipeline(
                w_shadow,
                self.state.H_slow,
                journal.event_results,
                journal.observation_witnesses,
                accepted_keys,
                exposure_id=exposure_id,
                remaining_k_r=journal.last_event_remaining_k_r,
                discover_and_recruit=True,
                min_additional_opportunities=self.min_additional_opportunities,
            )
            settlements.extend(cand_res)
            recruitments.extend(rec_res)
            diagnostics.extend(ctx_diags)

        # Step 5 (Core §10.2 & §2.0): Bounded Assembly MAINTAIN -> GROW -> FORM -> MERGE -> SPLIT
        asm_report: object | None = None
        if self.enable_assembly_pipeline:
            from dgca.core.assembly import execute_assembly_end_pipeline

            asm_report = execute_assembly_end_pipeline(
                w_shadow,
                self.state.H_slow,
                journal.event_results,
            )

        # Step 5.1 (Core §7.6, §11 & R2-A01 Patch 2): Transactional settlement of stale bindings on w_shadow
        from dgca.core.context_gate import validate_and_refresh_stable_binding
        from dgca.core.state import BindingStatus
        for z_id, binding in sorted(w_shadow.stable_bindings.items()):
            if binding.status == BindingStatus.ACTIVE:
                ok, stale_code = validate_and_refresh_stable_binding(
                    binding, w_shadow, mutate=True
                )
                if not ok:
                    diagnostics.append(stale_code)

        # Execute registered post-evidence shadow hooks (e.g. Phase 6 peripheral outbox)
        for hook in self._end_exposure_hooks:
            hook(w_pre_close, w_shadow, self.state.H_slow, journal, diagnostics)

        # FP-02 Fault Injection Gate
        if self._fault_injection_point == "FP_02":
            raise RuntimeError("Injected fault at FP-02: outbox batch construction failure")

        # Build idempotent peripheral outbox notifications for pre-existing LIVE assemblies (no backdating)
        outbox_notifs: tuple[object, ...] = ()
        if journal.peripheral_envelopes_by_order:
            from dgca.peripheral.outbox import build_end_exposure_outbox_notifications

            outbox_notifs = tuple(
                build_end_exposure_outbox_notifications(
                    exposure_id,
                    w_shadow,
                    self.state.H_slow,
                    journal.event_results,
                    journal.peripheral_envelopes_by_order,
                    preexisting_live_assemblies=tuple(w_pre_close.assemblies.values()),
                )
            )

        journal.status = ExposureStatus.COMPLETED
        report = EndExposureReport(
            exposure_id=exposure_id,
            status=ExposureStatus.COMPLETED,
            events_processed=len(journal.event_results),
            proposal_outcomes=tuple(outcomes),
            pruned_synapses=tuple(pruned_keys),
            last_event_remaining_k_r=journal.last_event_remaining_k_r,
            diagnostics=tuple(diagnostics),
            candidate_settlements=tuple(settlements),
            recruitments=tuple(recruitments),
            assembly_report=asm_report,
            outbox_notifications=outbox_notifs,
        )

        new_completed = dict(self._publication_view.completed_roots)
        new_completed[exposure_id] = report

        new_pending = dict(self._publication_view.pending_outbox_by_root)
        if outbox_notifs:
            new_pending[exposure_id] = outbox_notifs

        new_high_watermark = max(
            self._publication_view.completed_roots_high_watermark,
            w_shadow.completed_roots_high_watermark,
            exposure_id,
        )
        w_shadow.completed_roots_high_watermark = new_high_watermark

        new_view = TransactionPublicationView(
            W=w_shadow,
            completed_roots=frozendict(new_completed),
            pending_outbox_by_root=frozendict(new_pending),
            completed_roots_high_watermark=new_high_watermark,
            active_exposure_id=None,
        )

        # Step 6: Atomic Publication Point (single pointer swap)
        self._publication_view = new_view
        self.state.W = new_view.W
        self._protected_open_root_pairs.clear()
        self.open_journal = None

        # Step 7: Post-Commit Peripheral Dispatch Phase
        if self._fault_injection_point == "FP_03":
            logger.warning(
                "Injected fault at FP-03: post-commit peripheral dispatch deferred for root %d",
                exposure_id,
            )
        elif self.readout_ledger is not None and outbox_notifs:
            try:
                if hasattr(self.readout_ledger, "consume_outbox_batch"):
                    self.readout_ledger.consume_outbox_batch(outbox_notifs)  # type: ignore[attr-defined]
                # Delivery succeeded; remove from pending queue
                pending_after = dict(self._publication_view.pending_outbox_by_root)
                pending_after.pop(exposure_id, None)
                self._publication_view = TransactionPublicationView(
                    W=self._publication_view.W,
                    completed_roots=self._publication_view.completed_roots,
                    pending_outbox_by_root=frozendict(pending_after),
                    completed_roots_high_watermark=self._publication_view.completed_roots_high_watermark,
                    active_exposure_id=self._publication_view.active_exposure_id,
                )
            except Exception as exc:
                # Root remains COMPLETED. W remains committed. Batch remains in pending view.
                logger.warning(
                    "Peripheral dispatch deferred for root %d: %s", exposure_id, exc
                )

        return report


@dataclass(frozen=True, slots=True)
class ReadOnlyEpisodeResult:
    """Result of a standalone READ_ONLY_EPISODE execution (Core §9.1)."""

    event_results: tuple[EventExecutionResult, ...]
    next_step_pt_by_cell: dict[int, float]
    final_f_step: frozenset[int]
    final_mu_source_mask: dict[int, int]


def run_read_only_episode(
    state: MachineState,
    events: Sequence[CoreEventPayloadV1],
    *,
    mask_nonconsolidated_candidate_links: bool = False,
) -> ReadOnlyEpisodeResult:
    """Execute an isolated READ_ONLY_EPISODE on a scratch R_cold clone (Core §9.1, LLA-T16).

    - Frozen W, H_slow, and caller R are strictly untouched.
    - No dynamic admissions, no learning/evidence updates, no slow adaptation, no probe.
    - Computes the post-last-event one-step temporal drive P_T(next) with frozen mu(last).
    """
    if not events:
        raise ObservationError("READ_ONLY_EPISODE requires at least one event")

    scratch_state = MachineState(
        w=state.W,  # read-only reference; never mutated when mode == RETRIEVE
        r=state.R.clone(),
        h_slow=state.H_slow.clone(),
    )
    scratch_state.R.reset_cold()

    results: list[EventExecutionResult] = []
    for idx, ev in enumerate(events):
        proj = project_core_event_v1(ev)
        res = execute_two_pass_event(
            scratch_state,
            proj.x_fixed_by_global_id,
            proj.x_float_by_global_id,
            mode=ExecutionMode.RETRIEVE,
            origin=EventOrigin.READ_ONLY_OBSERVED,
            boundary=(idx == 0 or ev.boundary),
            exposure_id=None,
            event_order=idx,
            feature_bundle_digest=proj.feature_bundle_digest,
            allow_candidate_probe=False,
            mask_nonconsolidated_candidate_links=mask_nonconsolidated_candidate_links,
            admit_uncommitted_sensory=False,
        )
        results.append(res)

    last_res = results[-1]
    next_pt, _ = compute_next_step_temporal_drive(
        scratch_state,
        f_step_prev=last_res.f_step,
        a_prev_by_cell=scratch_state.R.A,
        mu_prev_source_mask=last_res.mu_source_mask,
        mask_nonconsolidated=mask_nonconsolidated_candidate_links,
    )
    return ReadOnlyEpisodeResult(
        event_results=tuple(results),
        next_step_pt_by_cell=next_pt,
        final_f_step=last_res.f_step,
        final_mu_source_mask=last_res.mu_source_mask,
    )


def compute_pred_score(
    next_step_pt_by_cell: dict[int, float],
    evaluator_target_cells: Sequence[int] | set[int] | frozenset[int],
) -> tuple[StatusCode, float]:
    """Compute PredScore_W(Y | P, B) = |Y|^-1 * sum_{j in Y} P_j^T(next) (Core §9.1).

    Y is an evaluator-only observed footprint, never supplied as current input nor looked up by Core.
    If Y is empty -> (StatusCode.UNRESOLVED, 0.0).
    """
    target_set = sorted(set(evaluator_target_cells))
    if not target_set:
        return StatusCode.UNRESOLVED, 0.0
    total_pt = sum(next_step_pt_by_cell.get(cid, 0.0) for cid in target_set)
    return StatusCode.OK, total_pt / float(len(target_set))
