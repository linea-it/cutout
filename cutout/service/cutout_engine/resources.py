"""Detect CPU/RAM limits and plan in-process parallelism for a cutout task.

The engine never oversubscribes the cgroup. Django settings are optional
overrides that are clamped to the detected container/host limits.

A future Slurm launcher can set the same values from SLURM_CPUS_PER_TASK
and the job memory allocation; this module does not submit jobs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("cutout")

_CGROUP_CPU_MAX = Path("/sys/fs/cgroup/cpu.max")
_CGROUP_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
_PROC_MEMINFO = Path("/proc/meminfo")

_MEMORY_RESERVE_FRACTION = 0.25
_PER_BAND_OVERHEAD_BYTES = 128 * 1024 * 1024
_OUTPUT_BYTES_PER_PIXEL = 64
_NATIVE_BYTES_PER_PIXEL = 8


@dataclass(frozen=True)
class ResourceLimits:
    cpus: int
    memory_bytes: int
    memory_budget_bytes: int


@dataclass(frozen=True)
class ExecutionPlan:
    cpus: int
    memory_budget_bytes: int
    concurrent_bands: int
    threads_per_wave: tuple[int, ...]
    estimated_band_bytes: int
    grid_ny: int
    grid_nx: int

    def threads_for_wave(self, wave_size: int) -> tuple[int, ...]:
        return tuple(split_threads(self.cpus, wave_size))


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _host_cpu_count() -> int:
    count = getattr(os, "process_cpu_count", os.cpu_count)()
    return max(int(count or 1), 1)


def read_cgroup_cpus() -> int:
    raw = _read_text(_CGROUP_CPU_MAX)
    if raw:
        parts = raw.split()
        if parts[0] != "max":
            quota = int(parts[0])
            period = int(parts[1]) if len(parts) > 1 else 100_000
            if quota > 0 and period > 0:
                return max(1, quota // period)
    return _host_cpu_count()


def _host_memory_bytes() -> int:
    raw = _read_text(_PROC_MEMINFO)
    if not raw:
        return 8 * 1024 * 1024 * 1024
    available = None
    total = None
    for line in raw.splitlines():
        if line.startswith("MemAvailable:"):
            available = int(line.split()[1]) * 1024
        elif line.startswith("MemTotal:"):
            total = int(line.split()[1]) * 1024
    return max(int(available or total or 8 * 1024 * 1024 * 1024), 1)


def read_cgroup_memory_bytes() -> int:
    raw = _read_text(_CGROUP_MEMORY_MAX)
    if raw and raw != "max":
        value = int(raw)
        if value > 0:
            return value
    return _host_memory_bytes()


def _django_setting(name: str, default: int) -> int:
    try:
        from django.conf import settings

        if not settings.configured:
            return default
        return int(getattr(settings, name, default))
    except Exception:
        return default


def detect_limits() -> ResourceLimits:
    cgroup_cpus = read_cgroup_cpus()
    cgroup_memory = read_cgroup_memory_bytes()
    auto_budget = max(int(cgroup_memory * (1.0 - _MEMORY_RESERVE_FRACTION)), 1)

    cpu_override = _django_setting("CUTOUT_PARALLEL_WORKERS", 0)
    cpus = cgroup_cpus if cpu_override <= 0 else min(cpu_override, cgroup_cpus)

    mem_override_mb = _django_setting("CUTOUT_TASK_MEMORY_BUDGET_MB", 0)
    if mem_override_mb > 0:
        budget = min(mem_override_mb * 1024 * 1024, auto_budget)
    else:
        budget = auto_budget

    return ResourceLimits(cpus=max(cpus, 1), memory_bytes=cgroup_memory, memory_budget_bytes=max(budget, 1))


def estimate_band_memory_bytes(
    ny: int,
    nx: int,
    n_tiles: int = 1,
    *,
    native_ny: int | None = None,
    native_nx: int | None = None,
) -> int:
    """Conservative peak for one band while tiles are processed sequentially.

    The output allowance covers accumulation arrays, WCS coordinate buffers,
    interpolation scratch and the final result. The native allowance covers
    one decoded source window at a time; tile count does not multiply it.
    """
    del n_tiles  # Tiles are deliberately sequential inside each band.
    output_pixels = max(int(ny) * int(nx), 1)
    native_pixels = max(int(native_ny or ny) * int(native_nx or nx), 1)
    return _OUTPUT_BYTES_PER_PIXEL * output_pixels + _NATIVE_BYTES_PER_PIXEL * native_pixels + _PER_BAND_OVERHEAD_BYTES


def split_threads(cpus: int, n: int) -> list[int]:
    workers = max(int(n), 1)
    total = max(int(cpus), 1)
    workers = min(workers, total)
    base = total // workers
    rem = total % workers
    return [base + (1 if i < rem else 0) for i in range(workers)]


def plan_band_execution(
    *,
    n_bands: int,
    ny: int,
    nx: int,
    n_tiles: int = 1,
    native_ny: int | None = None,
    native_nx: int | None = None,
    max_band_workers: int | None = None,
) -> ExecutionPlan:
    limits = detect_limits()
    if max_band_workers is None:
        max_band_workers = _django_setting("CUTOUT_RGB_BAND_WORKERS", 3)
    max_band_workers = max(int(max_band_workers), 1)

    estimated = estimate_band_memory_bytes(
        ny,
        nx,
        n_tiles,
        native_ny=native_ny,
        native_nx=native_nx,
    )
    max_by_mem = max(1, limits.memory_budget_bytes // max(estimated, 1))
    concurrent = min(max(int(n_bands), 1), max_band_workers, limits.cpus, max_by_mem)
    concurrent = max(1, concurrent)
    threads = tuple(split_threads(limits.cpus, concurrent))

    logger.info(
        "[resources] cpus=%s mem_bytes=%s budget_bytes=%s grid=%sx%s tiles=%s "
        "bands=%s concurrent=%s threads=%s est_band_bytes=%s",
        limits.cpus,
        limits.memory_bytes,
        limits.memory_budget_bytes,
        ny,
        nx,
        n_tiles,
        n_bands,
        concurrent,
        threads,
        estimated,
    )
    return ExecutionPlan(
        cpus=limits.cpus,
        memory_budget_bytes=limits.memory_budget_bytes,
        concurrent_bands=concurrent,
        threads_per_wave=threads,
        estimated_band_bytes=estimated,
        grid_ny=int(ny),
        grid_nx=int(nx),
    )
