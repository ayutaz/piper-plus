"""pytest plugin: record every skipped test for scripts/check_test_skips.py.

Loaded in CI through ``PYTEST_PLUGINS=piper_plus_skip_log`` with this
directory on ``PYTHONPATH`` (see .github/workflows/python-tests.yml). It
appends one JSON object per skipped test to the file named by
``PIPER_PLUS_SKIP_LOG``; every pytest run in a job appends to the same file.

The file is created when pytest starts, so an empty file means "tests ran
and nothing was skipped" and a missing file means the plugin never loaded.
An expected failure (``xfail``) is not a skip and is not recorded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


# pytest's rootdir, which node IDs are relative to (set in pytest_configure).
_state: dict[str, Path] = {}


def _log_path() -> Path | None:
    value = os.environ.get("PIPER_PLUS_SKIP_LOG")
    return Path(value) if value else None


def pytest_configure(config) -> None:
    _state["root"] = Path(config.rootpath)
    path = _log_path()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def _test_id(nodeid: str) -> str | None:
    """The node ID relative to the repository root (``GITHUB_WORKSPACE``).

    None for a test outside the repository, such as the inner run of a test
    that starts pytest in a temporary directory.
    """
    file_part, sep, rest = nodeid.partition("::")
    repo = Path(os.environ.get("GITHUB_WORKSPACE") or Path.cwd()).resolve()
    path = (_state.get("root", Path.cwd()) / file_part).resolve()
    try:
        return path.relative_to(repo).as_posix() + sep + rest
    except ValueError:
        return None


def _record(report) -> None:
    path = _log_path()
    if path is None or not report.skipped or hasattr(report, "wasxfail"):
        return
    longrepr = report.longrepr
    reason = longrepr[2] if isinstance(longrepr, tuple) else str(longrepr)
    if reason.startswith("Skipped: "):
        reason = reason[len("Skipped: ") :]
    test = _test_id(report.nodeid)
    if test is None:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"test": test, "reason": reason}, ensure_ascii=False) + "\n")


def pytest_runtest_logreport(report) -> None:
    _record(report)


def pytest_collectreport(report) -> None:
    # A module-level skip (pytest.importorskip, pytest.skip(allow_module_level=True))
    # skips the whole file at collection; it is recorded under the file's node ID.
    _record(report)
