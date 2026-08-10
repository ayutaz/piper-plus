#!/usr/bin/env python3
"""Detect numeric test-threshold relaxation in staged changes (goalpost moving).

Background (2026-08-10, docs/design/zero-shot-noise-root-cause-pqmf.md):
    PR #320 introduced a PQMF filter bank whose reconstruction SNR should have
    been ~60 dB but measured 7-8 dB due to an implementation bug. Instead of
    comparing against a reference implementation, the acceptance criterion was
    relaxed from "-90 dB residual aliasing" to "SNR > 5 dB" and the measured
    value was documented as the "theoretical limit". The mislabeled threshold
    survived 15 months and every MB-iSTFT model trained since carries audible
    aliasing noise that only surfaces in multi-speaker zero-shot synthesis.

This gate makes that failure mode loud: whenever a staged diff *weakens* a
numeric assertion threshold in a Python test file, the commit is blocked
unless the change carries an explicit justification marker.

Detected relaxation patterns (removed line vs added line in the same hunk,
matching once numbers are masked out):

    assert snr > 50          ->  assert snr > 5          # lower floor
    assert err < 1e-6        ->  assert err < 1e-3       # higher ceiling
    pytest.approx(x, abs=1e-6) -> pytest.approx(x, abs=1e-2)   # wider tolerance
    assertAlmostEqual(..., places=7) -> places=3               # fewer places

Escape hatch (required justification):
    Add a comment on (or within 2 lines above) the changed assertion:

        # threshold-relaxed: <why, including reference-implementation comparison>

    The justification must reference evidence, not convenience. Empty or
    whitespace-only justifications are rejected.

Scope: Python test files only (see TEST_FILE_RE). Non-test code and other
languages are out of scope.

Exit codes:
    0 -- no unjustified relaxation found
    1 -- at least one unjustified relaxation
"""

from __future__ import annotations

import re
import subprocess
import sys


TEST_FILE_RE = re.compile(
    r"(^|/)tests?/[^/]*\.py$|(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.py$"
)

# Comparison thresholds: capture (operator, number). Only numeric literals.
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
CMP_RE = re.compile(rf"([<>]=?)\s*({_NUM})\b")
# Tolerance kwargs: wider value = relaxation.
TOL_RE = re.compile(rf"\b(abs|rel|atol|rtol|tol|delta)\s*=\s*({_NUM})\b")
# assertAlmostEqual places: fewer places = relaxation.
PLACES_RE = re.compile(rf"\bplaces\s*=\s*({_NUM})\b")

JUSTIFICATION_RE = re.compile(r"#\s*threshold-relaxed:\s*(\S.*)$")

ASSERT_HINT_RE = re.compile(r"\bassert\b|\bapprox\b|assertAlmostEqual|assertGreater|assertLess")


def _mask_numbers(line: str) -> str:
    """Normalise an assertion line so removed/added versions pair up.

    Comments are stripped BEFORE masking — otherwise adding any trailing
    comment (even an empty justification marker) would change the pairing
    key and let the relaxation slip through unpaired.
    """
    code = re.sub(r"#.*$", "", line)
    return re.sub(_NUM, "§", re.sub(r"\s+", " ", code.strip()))


def _parse_hunks(diff_text: str):
    """Yield (file, [(kind, lineno_or_None, text), ...]) per hunk.

    kind is '-', '+', or ' ' (context). Line numbers are not tracked; hunk
    locality is all the pairing logic needs.
    """
    current_file = None
    hunk: list[tuple[str, str]] = []
    for raw in diff_text.splitlines():
        if raw.startswith("+++ b/"):
            # Flush the previous file's trailing hunk BEFORE switching files —
            # otherwise its lines leak into the next file's first hunk and
            # violations get attributed to the wrong path.
            if current_file and hunk:
                yield current_file, hunk
            hunk = []
            current_file = raw[6:]
        elif raw.startswith("@@"):
            if current_file and hunk:
                yield current_file, hunk
            hunk = []
        elif raw[:1] in ("-", "+", " ") and not raw.startswith(("---", "+++")):
            if current_file is not None:
                hunk.append((raw[:1], raw[1:]))
    if current_file and hunk:
        yield current_file, hunk


def _is_relaxed(old_line: str, new_line: str) -> bool:
    """True if new_line weakens any numeric threshold present in old_line."""
    for pattern, direction in ((CMP_RE, "cmp"), (TOL_RE, "tol"), (PLACES_RE, "places")):
        old_m = pattern.findall(old_line)
        new_m = pattern.findall(new_line)
        if not old_m or len(old_m) != len(new_m):
            continue
        for om, nm in zip(old_m, new_m):
            if direction == "cmp":
                op_old, val_old = om
                op_new, val_new = nm
                if op_old[0] != op_new[0]:
                    continue
                old_v, new_v = float(val_old), float(val_new)
                # `x > N`: smaller N is weaker. `x < N`: larger N is weaker.
                if op_old[0] == ">" and new_v < old_v:
                    return True
                if op_old[0] == "<" and new_v > old_v:
                    return True
            elif direction == "tol":
                if float(nm[1]) > float(om[1]):
                    return True
            elif direction == "places":
                if float(nm) < float(om):
                    return True
    return False


def _has_justification(hunk: list[tuple[str, str]], added_idx: int) -> str | None:
    """Return justification text if the added line (or up to 2 added/context
    lines directly above it) carries a non-empty threshold-relaxed marker."""
    for j in range(added_idx, max(-1, added_idx - 3), -1):
        kind, text = hunk[j]
        if kind == "-":
            continue
        m = JUSTIFICATION_RE.search(text)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def check_diff(diff_text: str) -> list[str]:
    violations: list[str] = []
    for path, hunk in _parse_hunks(diff_text):
        if not TEST_FILE_RE.search(path):
            continue
        removed = [
            (i, text) for i, (kind, text) in enumerate(hunk)
            if kind == "-" and ASSERT_HINT_RE.search(text)
        ]
        added = [
            (i, text) for i, (kind, text) in enumerate(hunk)
            if kind == "+" and ASSERT_HINT_RE.search(text)
        ]
        for ri, rtext in removed:
            rkey = _mask_numbers(rtext)
            for ai, atext in added:
                if _mask_numbers(atext) != rkey:
                    continue
                if not _is_relaxed(rtext, atext):
                    continue
                if _has_justification(hunk, ai):
                    continue
                violations.append(
                    f"{path}: threshold relaxed without justification:\n"
                    f"    - {rtext.strip()}\n"
                    f"    + {atext.strip()}"
                )
    return violations


def main() -> int:
    # encoding を明示: Windows の locale (cp932) では UTF-8 の diff (日本語
    # docstring 等) が UnicodeDecodeError になり stdout が None 化する
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U3", "--no-color"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout or ""
    violations = check_diff(diff)
    if violations:
        print("Test-threshold relaxation detected (goalpost moving guard):\n")
        for v in violations:
            print(v + "\n")
        print(
            "A numeric test threshold is being weakened. This is how the PQMF\n"
            "aliasing bug survived 15 months (acceptance -90dB was relaxed to\n"
            ">5dB and mislabeled 'theoretical limit' -- see\n"
            "docs/design/zero-shot-noise-root-cause-pqmf.md §4).\n\n"
            "Before relaxing a threshold you MUST compare against a reference\n"
            "implementation or first-principles bound. If the relaxation is\n"
            "genuinely correct, add on (or just above) the assertion:\n\n"
            "    # threshold-relaxed: <evidence, e.g. 'canonical impl X also\n"
            "    #   measures N dB under condition Y'>\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
