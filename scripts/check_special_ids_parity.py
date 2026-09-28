#!/usr/bin/env python3
"""PAD / BOS / EOS must be skipped by every runtime (issue #697).

`docs/spec/phoneme-timing-contract.toml` `[calculation.special_ids]` says ids
0 / 1 / 2 advance the timing cursor but produce no entry. Before that section
existed the runtimes split 4-2 -- python / rust / go / js emitted entries for
them, csharp / cpp did not -- so the same model and the same text produced
different entry counts depending on which runtime you called. Consumers
(lip-sync, subtitles, forced alignment) then had to know which runtime they
were talking to in order to interpret the output.

Two implementations satisfy the contract and both are in the tree:

  skip_during_walk   csharp / cpp -- advance the cursor, emit nothing
  filter_after_walk  python / rust / go / js -- walk everything, then remove

This gate checks, per runtime:

  1. the special-id set is spelled out as exactly PAD / BOS / EOS,
  2. the production CALL SITE exists -- for `filter_after_walk` runtimes the
     helper is useless unless the synthesis path actually invokes it,
  3. a named test covers it.

Check 2 is the one that matters, and it is written to fail on deletion rather
than on a rename: each pattern pins an argument, not a bare identifier. A
pattern that matched only the function name would also match its definition,
so deleting the single call from the CLI would leave this gate green -- the
exact vacuity that shipped in `check_reverse_map_parity.py`'s first version.

Exit codes: 0 = every runtime skips them, 1 = at least one does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs/spec/phoneme-timing-contract.toml"

# Per runtime:
#   decl      -- (file, list of substrings that must all appear) the id set
#   call_site -- (file, substring) the production path that applies the policy.
#                MUST include an argument so it cannot match a definition.
#   test      -- (file, substring) a named test for the behaviour
RUNTIMES: dict[str, dict[str, tuple[str, object]]] = {
    "python": {
        "impl": "filter_after_walk",
        "decl": (
            "src/python_run/piper_plus/timing.py",
            ["SPECIAL_PHONEME_IDS: frozenset[int] = frozenset({0, 1, 2})"],
        ),
        "call_site": (
            "src/python_run/piper_plus/voice.py",
            "if pid in _SPECIAL_PHONEME_IDS:",
        ),
        "test": (
            "src/python_run/tests/test_phoneme_timing.py",
            "def test_special_phoneme_ids_are_exactly_pad_bos_eos(",
        ),
    },
    "rust": {
        "impl": "filter_after_walk",
        "decl": (
            "src/rust/piper-core/src/timing.rs",
            ["SPECIAL_PHONEME_IDS: [i64; 3] = [0, 1, 2]", "fn is_special_phoneme_id"],
        ),
        "call_site": (
            "src/rust/piper-cli/src/main.rs",
            "drop_special_id_entries(&mut timing,",
        ),
        "test": (
            "src/rust/piper-core/src/timing.rs",
            "fn special_id_set_is_exactly_pad_bos_eos(",
        ),
    },
    "go": {
        "impl": "filter_after_walk",
        "decl": (
            "src/go/piperplus/timing.go",
            ["SpecialPhonemeIDs = [3]int64{0, 1, 2}", "func IsSpecialPhonemeID"],
        ),
        "call_site": (
            "src/go/cmd/piper-plus/main.go",
            "DropSpecialIDEntries(timing,",
        ),
        "test": (
            "src/go/piperplus/timing_test.go",
            "func TestIsSpecialPhonemeID_IsExactlyPadBosEos(",
        ),
    },
    "js": {
        "impl": "filter_after_walk",
        "decl": (
            "src/wasm/openjtalk-web/src/timing.js",
            ["SPECIAL_PHONEME_IDS = new Set([0, 1, 2])"],
        ),
        "call_site": (
            "src/wasm/openjtalk-web/src/index.js",
            "dropSpecialIdEntries(timing,",
        ),
        "test": (
            "src/wasm/openjtalk-web/test/js/test-phoneme-timing.js",
            "dropSpecialIdEntries (contract [calculation.special_ids])",
        ),
    },
    # csharp / cpp skip during the walk: the "call site" IS the walk, so the
    # pinned string is the branch itself rather than a helper invocation.
    "csharp": {
        "impl": "skip_during_walk",
        "decl": (
            "src/csharp/PiperPlus.Core/Inference/TimingWriter.cs",
            ["PAD=0, BOS=1, EOS=2"],
        ),
        "call_site": (
            "src/csharp/PiperPlus.Core/Inference/TimingWriter.cs",
            "id is 0 or 1 or 2",
        ),
        "test": (
            "src/csharp/PiperPlus.Core.Tests/TimingWriterTests.cs",
            "PAD=0, BOS=1, EOS=2 are special and skipped by CalculateTiming.",
        ),
    },
    "cpp": {
        "impl": "skip_during_walk",
        "decl": (
            "src/cpp/timing_helpers.hpp",
            ["PAD (0), BOS (1) and EOS (2)"],
        ),
        "call_site": (
            "src/cpp/timing_helpers.hpp",
            "if (id == 0 || id == 1 || id == 2) {",
        ),
        "test": (
            "src/cpp/tests/test_timing_helpers.cpp",
            "TEST(TimingHelpers, SkipsPadBosEosButStillAdvancesTheCursor)",
        ),
    },
}

# The contract keys this gate exists to enforce. If the section is renamed or
# the policy is inverted, the gate must fail rather than keep policing a rule
# nobody declares any more.
CONTRACT_REQUIREMENTS = [
    "\n[calculation.special_ids]\n",
    "ids = [0, 1, 2]",
    "emits_entry = false",
    "advances_cursor = true",
    'position_invariant = "surviving_entries_keep_walk_positions"',
    'allowed_implementations = ["skip_during_walk", "filter_after_walk"]',
]


def _read(rel: str) -> str | None:
    path = REPO_ROOT / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    contract = _read(str(CONTRACT.relative_to(REPO_ROOT)))
    if contract is None:
        failures.append(f"contract missing: {CONTRACT}")
    else:
        for needle in CONTRACT_REQUIREMENTS:
            if needle not in contract:
                failures.append(
                    f"contract: [calculation.special_ids] no longer declares "
                    f"{needle.strip()!r}"
                )

    for runtime, checks in sorted(RUNTIMES.items()):
        for kind in ("decl", "call_site", "test"):
            rel, needle = checks[kind]
            source = _read(rel)
            if source is None:
                failures.append(f"{runtime}/{kind}: file not found: {rel}")
                continue
            needles = needle if isinstance(needle, list) else [needle]
            for one in needles:
                if one not in source:
                    failures.append(f"{runtime}/{kind}: {rel} lacks {one!r}")

    # Anti-vacuity: a typo in every pattern would also produce zero failures on
    # a tree that has lost the feature entirely, so assert the table itself is
    # populated and that each call_site pattern carries an argument (a bare
    # identifier would match the definition too).
    if len(RUNTIMES) < 6:
        failures.append(
            f"gate covers only {len(RUNTIMES)} runtimes; all 6 must be listed"
        )
    for runtime, checks in sorted(RUNTIMES.items()):
        impl = checks["impl"]
        decl_file, _ = checks["decl"]
        call_file, needle = checks["call_site"]
        needle = str(needle)
        if impl == "filter_after_walk":
            # The helper and its call must live in different files. Otherwise
            # the pattern could be satisfied by the helper's own definition,
            # and deleting the production call would leave this gate green.
            if call_file == decl_file:
                failures.append(
                    f"{runtime}/call_site: {call_file} also declares the id "
                    f"set, so the pattern may be matching the definition"
                )
            # When the pattern names a function, it must also pass an
            # argument -- `helper(` alone matches `fn helper(` too. Patterns
            # that are not calls (python's `in` membership test) are already
            # covered by the file-difference check above.
            if "(" in needle and re.search(r"\(\s*\)?$", needle):
                failures.append(
                    f"{runtime}/call_site: pattern {needle!r} passes no "
                    f"argument, so it could match the definition"
                )
        elif impl == "skip_during_walk":
            # The branch IS the call site, so it has to name all three ids.
            if not all(str(i) in needle for i in (0, 1, 2)):
                failures.append(
                    f"{runtime}/call_site: pattern {needle!r} does not name "
                    f"all of PAD/BOS/EOS, so it cannot be the skip branch"
                )
        else:
            failures.append(f"{runtime}: unknown impl {impl!r}")

    if failures:
        print("PAD/BOS/EOS skip parity: FAIL")
        for line in failures:
            print(f"  - {line}")
        print()
        print("Contract: docs/spec/phoneme-timing-contract.toml")
        print("          [calculation.special_ids]")
        return 1

    print(f"PAD/BOS/EOS skip parity: OK ({len(RUNTIMES)} runtimes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
