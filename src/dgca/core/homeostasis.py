"""Slow Homeostatic Adaptation Laws for H_slow (Core §5, §10.1, §12).

Normative references:
- DGCA_CORE_RC4_1.md §5 (Slow adaptation equations for r_bar, g, rho_bar_r, theta_active_r)
- DGCA_CORE_RC4_1.md §10.1 (FIFR-B06 LAB POLICY A: H_slow_BEGIN capture and rollback on ABORT)
"""

from __future__ import annotations

from dgca.common.hashing import REGION_CELL_COUNT, Region
from dgca.common.numeric import clip_float64
from dgca.core.anatomy import (
    BETA_H,
    BETA_I,
    EPS_DEAD,
    ETA_H,
    ETA_I,
    G_MAX,
    G_MIN,
    REGION_PARAMS,
    RHO_CELL_TARGET,
    THETA_MAX,
    THETA_MIN,
)
from dgca.core.sic_v1 import CellAddress
from dgca.core.state import ExecutionMode, HSlowState, WState


def update_slow_homeostasis(
    h_slow: HSlowState,
    w: WState,
    a_plus_by_id: dict[int, float],
    *,
    committed_before_event: set[int],
    mode: ExecutionMode,
    active_regions: tuple[Region, ...] = (Region.LANGUAGE,),
) -> None:
    """Update slow homeostasis H_slow in-place after Pass 2 (Core §5).

    Strictly executes ONLY when mode == ExecutionMode.LEARN.
    Never re-evaluates prior event frontiers using the newly adapted thresholds.
    """
    if mode != ExecutionMode.LEARN:
        return

    # Capture pre-update regional thresholds used for the step's active indicator
    theta_active_pre = dict(h_slow.theta_active_by_region)
    active_count_by_region: dict[Region, int] = {reg: 0 for reg in Region}

    # 1. Per-cell firing EMA r_bar_j and intrinsic gain g_j for all committed cells
    for cell_id in sorted(committed_before_event):
        addr = CellAddress.from_global_id(cell_id)
        if addr.region not in active_regions:
            continue
        theta_r = theta_active_pre[addr.region]
        a_val = a_plus_by_id.get(cell_id, 0.0)
        is_active = 1.0 if a_val >= theta_r else 0.0
        if is_active > 0.0:
            active_count_by_region[addr.region] += 1

        old_r_bar = h_slow.get_r_bar(cell_id)
        new_r_bar = (1.0 - BETA_I) * old_r_bar + BETA_I * is_active
        h_slow.r_bar[cell_id] = new_r_bar

        old_g = h_slow.get_g(cell_id)
        new_g = clip_float64(old_g + ETA_I * (RHO_CELL_TARGET - new_r_bar), G_MIN, G_MAX)
        h_slow.g[cell_id] = new_g

    # 2. Regional firing rate EMA rho_bar_r and adaptive threshold theta_active_r
    for reg in active_regions:
        params = REGION_PARAMS[reg]
        rho_r_t = float(active_count_by_region[reg]) / float(REGION_CELL_COUNT)
        old_rho_bar = h_slow.rho_bar_by_region[reg]
        new_rho_bar = (1.0 - BETA_H) * old_rho_bar + BETA_H * rho_r_t
        h_slow.rho_bar_by_region[reg] = new_rho_bar

        diff = new_rho_bar - params.rho_target
        if abs(diff) > EPS_DEAD:
            sign = 1.0 if diff > 0.0 else -1.0
            old_theta = theta_active_pre[reg]
            new_theta = clip_float64(old_theta + ETA_H * sign, THETA_MIN, THETA_MAX)
            h_slow.theta_active_by_region[reg] = new_theta
