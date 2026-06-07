"""Shared hypothesis configuration for the property-based fuzz tests.

Two profiles are registered:

* ``dev`` — fast feedback for local iteration (max_examples=50).
* ``ci``  — broader search; total time budget is enforced by the
  ``--hypothesis-profile=ci`` flag at the workflow level. Per-test
  ``max_examples`` is generous because individual targets are cheap
  (microsecond-scale Python calls).

Both profiles share ``deadline=None`` because the targets occasionally call
into regex/XML parsers whose worst-case latency is platform-dependent and
not what we are trying to measure.
"""

from __future__ import annotations

import sys
from pathlib import Path


try:
    from hypothesis import HealthCheck, Verbosity, settings

    _HAS_HYPOTHESIS = True
except ImportError:
    # hypothesis は fuzz 専用の optional dep (src/python/g2p[dev] / fuzz-smoke.yml で
    # install)。未インストール時はこのディレクトリの collection をスキップし、
    # repo-root の `pytest tests` 全体を ModuleNotFoundError で中断させない。
    _HAS_HYPOTHESIS = False
    collect_ignore_glob = ["test_*.py"]


# Ensure the source modules under test are importable without installing the
# packages — the fuzz CI job runs in a thin venv.
_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    _ROOT / "src" / "python" / "g2p",
    _ROOT / "src" / "python_run",
):
    if _p.is_dir():
        _path = str(_p)
        if _path not in sys.path:
            sys.path.insert(0, _path)


if _HAS_HYPOTHESIS:
    settings.register_profile(
        "dev",
        max_examples=50,
        deadline=None,
        verbosity=Verbosity.normal,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
    )

    settings.register_profile(
        "ci",
        max_examples=500,
        deadline=None,
        verbosity=Verbosity.normal,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
    )

    # Default profile used when running pytest without `--hypothesis-profile`.
    settings.load_profile("dev")
