"""Sandbox execution of fenced code blocks classified as ``executable``.

Scope (v1): bash + python runners. The other 4 canonical languages
(rust / csharp / go / wasm) flow through here as ``runner_unsupported``
results — the framework is wired up so a follow-up PR can add their
runners without touching the orchestration. Together bash + python
cover ~95% of executable blocks in the current audit snapshot.

Two execution modes:

* ``"syntax"`` (default) — invoke ``bash -n`` / ``python -m py_compile``
  to parse the block without running it. Catches syntax errors and
  unfinished heredocs while leaving destructive operations (``rm``,
  ``curl``, network calls) alone. Safe to enable in PR base CI.
* ``"real"`` — actually run the block in a subprocess with a per-block
  timeout. Required ``--actually-run`` opt-in so a generic gate run
  doesn't surprise-execute someone's tutorial. ``set -euo pipefail`` is
  injected so multi-line bash blocks don't silently swallow mid-pipe
  failures.

Both modes capture stdout/stderr (tailed) and per-block duration.
Snapshot stability comes from status counts, not message text.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


# Result codes for a single execution attempt.
EXEC_PASS = "pass"
EXEC_FAIL = "fail"
EXEC_TIMEOUT = "timeout"
EXEC_RUNNER_UNSUPPORTED = "runner_unsupported"
EXEC_RUNNER_MISSING = "runner_missing"


@dataclass(frozen=True)
class ExecResult:
    """Outcome of running one fenced block."""

    block_hash: str
    file: str
    line_start: int
    language: str
    status: str
    exit_code: int | None
    duration_sec: float
    stdout_tail: str
    stderr_tail: str
    runner: str


def _tail(text: str, max_lines: int = 20) -> str:
    """Last ``max_lines`` lines of ``text`` (trimmed to keep logs sane)."""
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def _run_subprocess(
    cmd: list[str],
    *,
    timeout_sec: int,
    stdin: str | None = None,
) -> tuple[int | None, str, str, float, bool]:
    """Shell out to ``cmd``; return ``(exit, stdout, stderr, duration, timed_out)``.

    Returns ``exit=None`` when the subprocess timed out.
    """
    import time

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        return (
            None,
            (
                exc.stdout.decode("utf-8", "replace")
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")
            ),
            (
                exc.stderr.decode("utf-8", "replace")
                if isinstance(exc.stderr, bytes)
                else (exc.stderr or "")
            ),
            elapsed,
            True,
        )
    elapsed = time.perf_counter() - start
    return proc.returncode, proc.stdout, proc.stderr, elapsed, False


def _bash_body_with_safety(body: str) -> str:
    """Prepend ``set -euo pipefail`` unless the block leads with ``set -...``.

    The heuristic is intentionally narrow: only an explicit ``set -``
    flag combination in the first 10 lines skips the injection. The
    author's ``set +e`` does NOT skip injection — it gets prepended after
    our ``set -euo pipefail`` and ends up disabling ``-e`` only (``-u``
    and ``pipefail`` stay active). That matches the v1 contract: we
    surface mid-pipe failures unless the author has already enabled
    pipefail themselves.

    A future "opt out fully" knob would need a richer parser (e.g.
    recognise ``# noinject`` directive); not in v1.
    """
    head = "\n".join(body.splitlines()[:10])
    if "set -" in head:
        return body
    return "set -euo pipefail\n" + body


def _classify_subprocess(
    exit_code: int | None,
    out: str,
    err: str,
    duration: float,
    *,
    timed_out: bool,
) -> tuple[str, int | None, str, str, float]:
    if timed_out:
        return EXEC_TIMEOUT, exit_code, out, err, duration
    if exit_code == 0:
        return EXEC_PASS, exit_code, out, err, duration
    return EXEC_FAIL, exit_code, out, err, duration


def run_bash(
    block_body: str,
    *,
    timeout_sec: int = 30,
    mode: str = "syntax",
) -> tuple[str, int | None, str, str, float]:
    if mode == "syntax":
        # `bash -n` parses but does not execute. Heredoc / quote
        # errors / unclosed blocks surface here without touching the
        # filesystem or network.
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sh", delete=False, encoding="utf-8"
        ) as f:
            f.write(block_body)
            script_path = f.name
        try:
            exit_code, out, err, duration, timed_out = _run_subprocess(
                ["bash", "-n", script_path],
                timeout_sec=timeout_sec,
            )
        finally:
            Path(script_path).unlink(missing_ok=True)
        return _classify_subprocess(
            exit_code,
            out,
            err,
            duration,
            timed_out=timed_out,
        )

    # mode == "real" — runs the block. Requires --actually-run upstream.
    safe_body = _bash_body_with_safety(block_body)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, encoding="utf-8"
    ) as f:
        f.write(safe_body)
        script_path = f.name
    try:
        exit_code, out, err, duration, timed_out = _run_subprocess(
            ["bash", script_path],
            timeout_sec=timeout_sec,
        )
    finally:
        Path(script_path).unlink(missing_ok=True)
    return _classify_subprocess(
        exit_code,
        out,
        err,
        duration,
        timed_out=timed_out,
    )


def run_python(
    block_body: str,
    *,
    timeout_sec: int = 60,
    mode: str = "syntax",
) -> tuple[str, int | None, str, str, float]:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(block_body)
        script_path = f.name
    try:
        if mode == "syntax":
            # `python -m py_compile` raises SyntaxError but never executes.
            exit_code, out, err, duration, timed_out = _run_subprocess(
                [sys.executable, "-m", "py_compile", script_path],
                timeout_sec=timeout_sec,
            )
        else:
            exit_code, out, err, duration, timed_out = _run_subprocess(
                [sys.executable, script_path],
                timeout_sec=timeout_sec,
            )
    finally:
        Path(script_path).unlink(missing_ok=True)
    return _classify_subprocess(
        exit_code,
        out,
        err,
        duration,
        timed_out=timed_out,
    )


Runner = Callable[..., tuple[str, int | None, str, str, float]]

RUNNERS: dict[str, Runner] = {
    "bash": run_bash,
    "python": run_python,
}


def execute_block(
    *,
    block_hash: str,
    file: str,
    line_start: int,
    language: str,
    body: str,
    timeout_sec: int,
    mode: str = "syntax",
) -> ExecResult:
    """Execute a single block and return a structured result.

    ``mode`` is ``"syntax"`` (default — parse only) or ``"real"``
    (actually run, opt-in via the caller's ``--actually-run`` flag).
    """
    runner = RUNNERS.get(language)
    if runner is None:
        return ExecResult(
            block_hash=block_hash,
            file=file,
            line_start=line_start,
            language=language,
            status=EXEC_RUNNER_UNSUPPORTED,
            exit_code=None,
            duration_sec=0.0,
            stdout_tail="",
            stderr_tail=f"no runner for language={language!r}",
            runner=language,
        )

    try:
        status, exit_code, out, err, duration = runner(
            body,
            timeout_sec=timeout_sec,
            mode=mode,
        )
    except FileNotFoundError as exc:
        return ExecResult(
            block_hash=block_hash,
            file=file,
            line_start=line_start,
            language=language,
            status=EXEC_RUNNER_MISSING,
            exit_code=None,
            duration_sec=0.0,
            stdout_tail="",
            stderr_tail=f"runner binary not found: {exc.filename}",
            runner=language,
        )

    return ExecResult(
        block_hash=block_hash,
        file=file,
        line_start=line_start,
        language=language,
        status=status,
        exit_code=exit_code,
        duration_sec=round(duration, 3),
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
        runner=language,
    )


def shell_quote_argv(argv: list[str]) -> str:
    """Echo-friendly representation of an argv list for log lines."""
    return " ".join(shlex.quote(a) for a in argv)
