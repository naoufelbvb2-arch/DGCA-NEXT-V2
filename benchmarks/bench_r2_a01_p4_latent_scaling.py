"""BENCH-R2-A01-P4: Latent Topology Scaling & Rollback Benchmark.

Measures:
- Small (300 cells), Medium (2,000 cells), High occupancy (12,288 cells).
- BEGIN snapshot latency, ABORT rollback latency, latent clone allocation cost.
- Peak memory usage, retained memory after explicit garbage collection.
- 1,000-cycle stress test distinguishing legitimate retained state from leaked objects.

Normative reference: DGCA NEXT V2 R2-A01 Patch 3 §8.
"""

from __future__ import annotations

import gc
import os
import statistics
import sys
import time
import tracemalloc
from typing import Any

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from dgca.common.hashing import TOTAL_CELL_COUNT
from dgca.core.latent_index import LatentNeighborhoodTable
from dgca.core.state import MachineState
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
)


def _populate_latent_table(table: LatentNeighborhoodTable, cell_count: int) -> None:
    """Populate table with cell_count materialized cells and sample coactive links."""
    for cid in range(cell_count):
        table.materialize_cell(cid)
        # Wire slot 0 (intra) and slot 12 (inter) where valid
        partner_intra = (cid + 1) % cell_count if cell_count > 1 else None
        partner_inter = (cid + 100) % cell_count if cell_count > 100 else None
        if partner_intra is not None and partner_intra != cid:
            table._set_coactive_slot(cid, 0, partner_intra, event_clock=1, reason="BENCH_INTRA")
        if partner_inter is not None and partner_inter != cid:
            table._set_coactive_slot(cid, 12, partner_inter, event_clock=1, reason="BENCH_INTER")


def benchmark_scale(cell_count: int, iterations: int = 50) -> dict[str, Any]:
    """Benchmark BEGIN snapshot, ABORT rollback, and clone allocation at a given scale."""
    gc.collect()

    state = MachineState()
    _populate_latent_table(state.W.latent_table, cell_count)

    # 1. Measure LatentNeighborhoodTable.clone() latency and allocation
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    clone_times: list[float] = []
    clones: list[LatentNeighborhoodTable] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        cl = state.W.latent_table.clone()
        t1 = time.perf_counter()
        clone_times.append(t1 - t0)
        clones.append(cl)

    snapshot_after = tracemalloc.take_snapshot()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Calculate average memory per clone
    mem_diff = sum(stat.size_diff for stat in snapshot_after.compare_to(snapshot_before, "lineno"))
    avg_clone_bytes = mem_diff / iterations if iterations > 0 else 0
    del clones
    gc.collect()

    # 2. Measure Transactional BEGIN and ABORT latencies
    tx = ExposureTransactionManager(state, auto_coactive_latent=False)

    begin_times: list[float] = []
    abort_times: list[float] = []

    for i in range(iterations):
        exp_id = 1000 + i
        t0 = time.perf_counter()
        tx.begin_exposure(exp_id)
        t1 = time.perf_counter()
        begin_times.append(t1 - t0)

        # Mutate 10 coactive links in OPEN root
        for m in range(min(10, cell_count)):
            target = (m + 50) % cell_count if cell_count > 50 else None
            if target is not None and target != m:
                state.W.latent_table._set_coactive_slot(m, 1, target, event_clock=exp_id, reason="MUT")

        t2 = time.perf_counter()
        status = tx.abort_exposure(exp_id)
        t3 = time.perf_counter()
        assert status == ExposureStatus.ABORTED
        abort_times.append(t3 - t2)

    return {
        "cells": cell_count,
        "iterations": iterations,
        "clone_latency_ms": {
            "mean": statistics.mean(clone_times) * 1000,
            "median": statistics.median(clone_times) * 1000,
            "std": statistics.stdev(clone_times) * 1000 if len(clone_times) > 1 else 0.0,
            "min": min(clone_times) * 1000,
            "max": max(clone_times) * 1000,
        },
        "begin_latency_ms": {
            "mean": statistics.mean(begin_times) * 1000,
            "median": statistics.median(begin_times) * 1000,
            "std": statistics.stdev(begin_times) * 1000 if len(begin_times) > 1 else 0.0,
            "min": min(begin_times) * 1000,
            "max": max(begin_times) * 1000,
        },
        "abort_latency_ms": {
            "mean": statistics.mean(abort_times) * 1000,
            "median": statistics.median(abort_times) * 1000,
            "std": statistics.stdev(abort_times) * 1000 if len(abort_times) > 1 else 0.0,
            "min": min(abort_times) * 1000,
            "max": max(abort_times) * 1000,
        },
        "avg_clone_bytes": avg_clone_bytes,
        "peak_mem_kb": peak_mem / 1024,
    }


def benchmark_1000_cycles_stress() -> dict[str, Any]:
    """Execute 1,000 consecutive BEGIN -> OPEN -> ABORT cycles to verify zero leak of latent topology."""
    gc.collect()
    state = MachineState()
    _populate_latent_table(state.W.latent_table, cell_count=500)

    initial_materialized = len(state.W.latent_table._slots_by_cell)
    initial_reverse_targets = len(state.W.latent_table._coactive_reverse_index)

    tx = ExposureTransactionManager(state, auto_coactive_latent=False)

    tracemalloc.start()
    gc.collect()
    mem_before, _ = tracemalloc.get_traced_memory()

    cycle_times: list[float] = []

    for i in range(1, 1001):
        t0 = time.perf_counter()
        tx.begin_exposure(i)
        # Mutate coactive links ensuring target != owner
        t_target0 = (i % 490) + 10
        t_target1 = ((i + 1) % 490) + 10
        state.W.latent_table._set_coactive_slot(0, 1, t_target0, event_clock=i, reason="STRESS")
        state.W.latent_table._set_coactive_slot(1, 1, t_target1, event_clock=i, reason="STRESS")
        status = tx.abort_exposure(i)
        t1 = time.perf_counter()
        assert status == ExposureStatus.ABORTED
        cycle_times.append(t1 - t0)

    gc.collect()
    mem_after, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    final_materialized = len(state.W.latent_table._slots_by_cell)
    final_reverse_targets = len(state.W.latent_table._coactive_reverse_index)

    # Legitimate retained growth in Manager: aborted_roots dict stores exposure_id -> h_slow_begin
    retained_aborted_roots_count = len(tx.aborted_roots)
    assert retained_aborted_roots_count == 1000

    # ZERO unintended latent topology growth:
    assert final_materialized == initial_materialized, "Materialized cells count drifted!"
    assert final_reverse_targets == initial_reverse_targets, "Reverse index entries drifted!"

    return {
        "cycles": 1000,
        "total_time_s": sum(cycle_times),
        "mean_cycle_ms": statistics.mean(cycle_times) * 1000,
        "median_cycle_ms": statistics.median(cycle_times) * 1000,
        "p99_cycle_ms": sorted(cycle_times)[int(0.99 * len(cycle_times))] * 1000,
        "mem_before_kb": mem_before / 1024,
        "mem_after_kb": mem_after / 1024,
        "peak_mem_kb": peak_mem / 1024,
        "retained_aborted_roots_count": retained_aborted_roots_count,
        "latent_materialized_cells": final_materialized,
        "latent_reverse_index_targets": final_reverse_targets,
    }


def run_full_benchmark() -> None:
    print("=" * 70)
    print("DGCA NEXT V2 — R2-A01 PATCH 3: LATENT TOPOLOGY BENCHMARK (BENCH-R2-A01-P4)")
    print("=" * 70)

    scales = [
        ("Small", 300, 50),
        ("Medium", 2000, 30),
        ("High Occupancy", TOTAL_CELL_COUNT, 10),
    ]

    for name, cells, iters in scales:
        print(f"\nEvaluating Scale: {name} ({cells} cells, {iters} iterations)...")
        res = benchmark_scale(cells, iterations=iters)
        print(f"  Clone Latency: {res['clone_latency_ms']['mean']:.3f} ms (±{res['clone_latency_ms']['std']:.3f} ms)")
        print(f"  BEGIN Latency: {res['begin_latency_ms']['mean']:.3f} ms (±{res['begin_latency_ms']['std']:.3f} ms)")
        print(f"  ABORT Latency: {res['abort_latency_ms']['mean']:.3f} ms (±{res['abort_latency_ms']['std']:.3f} ms)")
        print(f"  Alloc Size per Clone: {res['avg_clone_bytes'] / 1024:.2f} KB")
        print(f"  Peak Memory: {res['peak_mem_kb']:.2f} KB")

    print("\n" + "-" * 70)
    print("Executing 1,000 Consecutive BEGIN -> OPEN -> ABORT Cycles Stress Test...")
    stress_res = benchmark_1000_cycles_stress()
    print(f"  Total 1,000 Cycles Time: {stress_res['total_time_s']:.3f} s")
    print(f"  Mean Cycle Latency: {stress_res['mean_cycle_ms']:.3f} ms")
    print(f"  P99 Cycle Latency:  {stress_res['p99_cycle_ms']:.3f} ms")
    print(f"  Initial vs Final Materialized Cells: {stress_res['latent_materialized_cells']} (Exact Match, 0 drift)")
    print(f"  Initial vs Final Reverse Targets:    {stress_res['latent_reverse_index_targets']} (Exact Match, 0 drift)")
    print(f"  Retained History Records: {stress_res['retained_aborted_roots_count']} aborted roots (Lawful Transaction Log)")
    print(f"  Peak Traced Memory: {stress_res['peak_mem_kb']:.2f} KB")
    print("=" * 70)
    print("BENCH-R2-A01-P4 COMPLETE — ZERO LATENT LEAK VERIFIED")
    print("=" * 70)


if __name__ == "__main__":
    run_full_benchmark()
