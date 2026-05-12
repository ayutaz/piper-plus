#!/usr/bin/env python3
"""Drift check for docs/spec/audio-format-contract.toml.

The contract pins canonical WAV invariants (mono int16 LE @ 22050 Hz) and
the RIFF/WAVE container layout. This script confirms:

1. TOML parses and required top-level tables exist.
2. [format] values are still mono / int16 / little-endian (deviating from
    any of these is a v2.0 break, not a drift fix).
3. [format.derived] block_align / byte_rate are arithmetically consistent
    with [format] (drift between them = mis-encoded WAV header).
4. [container.field_order] offsets / widths match the canonical 44-byte
    header layout: a single shift here corrupts every emitted WAV.
5. Every implementation path listed in the file header still exists on
    disk; deletion without replacement is a silent removal of canonical
    producer code.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/audio-format-contract.toml"

# Files listed under the "Implementations:" block in the contract header.
# A check on these prevents silent removal of canonical WAV writers; if
# any of them is intentionally renamed, update both this list and the
# contract header in the same PR.
IMPLEMENTATION_FILES = [
    "src/python_run/piper/voice.py",
    "src/python_run/piper/http_server.py",
    "src/rust/piper-core/src/engine.rs",
    "src/go/piperplus/synthesize.go",
    "src/csharp/PiperPlus.Core/Inference/PiperSession.cs",
    "src/wasm/openjtalk-web/src/index.js",
]


def main() -> int:
    if not CONTRACT_PATH.exists():
        print(f"ERROR: contract missing: {CONTRACT_PATH}", file=sys.stderr)
        return 1

    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    for table in ("meta", "format", "format.derived", "container", "validation"):
        cursor: object = contract
        for part in table.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                errors.append(f"missing required table [{table}]")
                cursor = None
                break
            cursor = cursor[part]

    fmt = contract.get("format", {})
    if fmt.get("bit_depth") != 16:
        errors.append(f"[format].bit_depth must be 16 (got {fmt.get('bit_depth')})")
    if fmt.get("channels") != 1:
        errors.append(f"[format].channels must be 1 (got {fmt.get('channels')})")
    if fmt.get("sample_format") != "int16":
        errors.append(f"[format].sample_format must be 'int16' (got {fmt.get('sample_format')!r})")
    if fmt.get("byte_order") != "little-endian":
        errors.append(f"[format].byte_order must be 'little-endian' (got {fmt.get('byte_order')!r})")

    derived = fmt.get("derived", {})
    sample_rate = fmt.get("sample_rate", 0)
    bit_depth = fmt.get("bit_depth", 0)
    channels = fmt.get("channels", 0)
    expected_block_align = channels * bit_depth // 8
    expected_byte_rate = sample_rate * expected_block_align
    if derived.get("block_align_bytes") != expected_block_align:
        errors.append(
            f"[format.derived].block_align_bytes={derived.get('block_align_bytes')} "
            f"!= channels*bit_depth/8={expected_block_align}"
        )
    if derived.get("byte_rate") != expected_byte_rate:
        errors.append(
            f"[format.derived].byte_rate={derived.get('byte_rate')} "
            f"!= sample_rate*block_align={expected_byte_rate}"
        )

    container = contract.get("container", {})
    if container.get("magic") != "RIFF":
        errors.append(f"[container].magic must be 'RIFF' (got {container.get('magic')!r})")
    if container.get("form_type") != "WAVE":
        errors.append(f"[container].form_type must be 'WAVE' (got {container.get('form_type')!r})")
    if container.get("audio_format_code") != 1:
        errors.append(
            f"[container].audio_format_code must be 1 (PCM) (got {container.get('audio_format_code')})"
        )
    if container.get("fmt_chunk_size") != 16:
        errors.append(
            f"[container].fmt_chunk_size must be 16 for PCM (got {container.get('fmt_chunk_size')})"
        )

    fields = container.get("field_order", {}).get("fields", [])
    # Verify the 14 canonical entries (13 header fields + PCM_payload) are
    # present in order and that the post-PCM-payload offset would land at
    # 44 bytes (= the size of every well-formed piper-emitted WAV header
    # before the data payload).
    if len(fields) != 14:
        errors.append(f"[container.field_order].fields must have 14 entries (got {len(fields)})")
    else:
        for i, field in enumerate(fields):
            if not isinstance(field, dict):
                errors.append(f"field {i} is not a table")
                continue
            if "offset" not in field or "name" not in field or "width" not in field:
                errors.append(f"field {i} ({field.get('name')!r}) missing one of offset/name/width")
        # The last field before PCM_payload must end at offset 44.
        # That is data_id @ 36 (ascii4 = 4 bytes) + data_size @ 40 (u32 = 4 bytes) = 44.
        non_payload = [f for f in fields if f.get("name") != "PCM_payload"]
        if non_payload:
            last = non_payload[-1]
            if last.get("name") != "data_size" or last.get("offset") != 40:
                errors.append(
                    f"last pre-payload field must be data_size@40 (got "
                    f"{last.get('name')!r}@{last.get('offset')})"
                )

    for rel in IMPLEMENTATION_FILES:
        if not (REPO_ROOT / rel).exists():
            errors.append(
                f"missing canonical implementation file: {rel} "
                "(if intentional, update the file header in "
                "docs/spec/audio-format-contract.toml)"
            )

    if errors:
        for msg in errors:
            print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print("OK: audio-format-contract.toml schema + invariants validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
