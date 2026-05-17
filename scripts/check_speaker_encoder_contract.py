#!/usr/bin/env python3
"""Drift check for docs/reference/speaker-encoder-contract.md.

The contract is markdown (not TOML) so this gate verifies what can be
checked without parsing prose: that the canonical fixture exists and
that every runtime listed for layer 1 (mel parity) and layer 2 (E2E
cosine gate) ships its referenced test file. Layer 2 tests are
intentionally opt-in (skip when fixture lacks the `e2e_cosine_gate`
block or env var is unset), so existence — not pass — is the gate.

A silent rename / deletion of a per-runtime test would cause the
contract to claim parity coverage that no longer exists.

Checks:

1. The canonical layer-1 fixture exists and contains a top-level
    `hann_window`, `mel_filterbank`, and at least one named test case
    (sine_440Hz / sine_1000Hz / multitone / resample_48k_to_16k).
2. All 6 layer-1 test files referenced by the markdown table exist.
3. All 6 layer-2 test files referenced by the markdown table exist.
4. If the fixture has an `e2e_cosine_gate` block, it declares a
    non-empty 256-dim expected embedding and a finite cosine_threshold
    in (0, 1].
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from platform_utils import force_utf8_output

force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/reference/speaker-encoder-contract.md"
LAYER1_FIXTURE = REPO_ROOT / "test/fixtures/speaker_encoder_golden.json"

LAYER1_TESTS = [
    "test/generate_speaker_encoder_golden.py",
    "src/rust/piper-core/tests/test_speaker_encoder_golden.rs",
    "src/go/piperplus/speaker_encoder_test.go",
    "src/csharp/PiperPlus.Core.Tests/SpeakerEncoderTests.cs",
    "src/wasm/openjtalk-web/test/js/test-speaker-encoder-golden.js",
    "src/cpp/tests/test_speaker_encoder_golden.cpp",
]

LAYER2_TESTS = [
    "test/test_speaker_encoder_e2e.py",
    "src/rust/piper-core/tests/test_speaker_encoder_e2e.rs",
    "src/go/piperplus/speaker_encoder_e2e_test.go",
    "src/csharp/PiperPlus.Core.Tests/SpeakerEncoderE2ETests.cs",
    "src/wasm/openjtalk-web/test/js/test-speaker-encoder-e2e.js",
    "src/cpp/tests/test_speaker_encoder_e2e.cpp",
]

# The contract's prose lists four deterministic test cases (sine 440Hz,
# sine 1000Hz, multitone, resample 48k→16k); the fixture stores them as
# a list of objects without enforcing canonical IDs. We only require the
# count here so a silent drop of one case (regression) is caught.
EXPECTED_CASES_COUNT = 4


def main() -> int:
    errors: list[str] = []

    if not CONTRACT_PATH.exists():
        errors.append(f"contract missing: {CONTRACT_PATH.relative_to(REPO_ROOT)}")

    if not LAYER1_FIXTURE.exists():
        errors.append(
            f"layer 1 golden fixture missing: {LAYER1_FIXTURE.relative_to(REPO_ROOT)} "
            "— regenerate via test/generate_speaker_encoder_golden.py"
        )
    else:
        try:
            fixture = json.loads(LAYER1_FIXTURE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"layer 1 fixture failed to parse: {exc}")
            fixture = {}

        for required in ("hann_window", "mel_filterbank"):
            if required not in fixture:
                errors.append(f"layer 1 fixture missing top-level key: {required!r}")

        test_cases = fixture.get("test_cases", [])
        if not isinstance(test_cases, list):
            errors.append(
                f"layer 1 fixture 'test_cases' must be a list of objects "
                f"(got {type(test_cases).__name__})"
            )
        elif len(test_cases) != EXPECTED_CASES_COUNT:
            errors.append(
                f"layer 1 fixture has {len(test_cases)} test case(s); "
                f"contract pins {EXPECTED_CASES_COUNT} canonical cases — "
                "if intentional, bump EXPECTED_CASES_COUNT and the "
                "speaker-encoder-contract.md table together"
            )

        gate = fixture.get("e2e_cosine_gate")
        if gate is not None:
            expected_emb = gate.get("expected_embedding", {})
            dim = expected_emb.get("dim")
            values = expected_emb.get("values", [])
            if dim != 256:
                errors.append(
                    f"e2e_cosine_gate.expected_embedding.dim must be 256 (got {dim})"
                )
            if not isinstance(values, list) or len(values) != 256:
                errors.append(
                    f"e2e_cosine_gate.expected_embedding.values must be 256 floats "
                    f"(got length {len(values) if isinstance(values, list) else 'non-list'})"
                )
            threshold = gate.get("cosine_threshold")
            try:
                t = float(threshold) if threshold is not None else None
            except (TypeError, ValueError):
                t = None
            if t is None or not (0.0 < t <= 1.0):
                errors.append(
                    f"e2e_cosine_gate.cosine_threshold must be in (0, 1] (got {threshold!r})"
                )

    for rel in LAYER1_TESTS:
        if not (REPO_ROOT / rel).exists():
            errors.append(
                f"layer 1 test file missing (deletion = silent removal of mel parity): {rel}"
            )

    for rel in LAYER2_TESTS:
        if not (REPO_ROOT / rel).exists():
            errors.append(
                f"layer 2 test file missing (deletion = silent removal of E2E gate scaffold): {rel}"
            )

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print(
        f"OK: speaker-encoder-contract.md — "
        f"{len(LAYER1_TESTS)} layer-1 test files, {len(LAYER2_TESTS)} layer-2 scaffolds verified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
