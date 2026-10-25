#!/usr/bin/env python3
"""Pre-release validator for ``phoneme_id_map`` keys (PUA contract).

C++ runtime (``src/cpp/piper.cpp:configPhonemeCodepoint``) は config の
``phoneme_id_map`` の key を 1 codepoint として読む。 例外は公開済み config
が持つ raw IPA の 3 key (``ɔɪ`` / ``œ̃`` / ``ɐ̃``) だけで、 これらは pua.json の
PUA codepoint に読み替える。 それ以外の multi-codepoint key は load 時に
``Unknown multi-codepoint phoneme`` で落ちる。 本 script は同じ規則で config を
検査する:

  * 1 codepoint の key           … OK
  * raw alias (contract の 3 key) … OK。 ただし同じ config に対応する PUA key
                                    があり ID が違えば NG (C++ は
                                    ``Conflicting phoneme ID aliases`` で落ちる)
  * それ以外の multi-codepoint    … NG

raw alias の一覧は ``docs/spec/pua-contract.toml`` の
``[invariants.config_keys].raw_aliases``、 codepoint は pua.json から読む。
C++ 側の一覧との一致は ``tests/scripts/test_check_config_phoneme_keys.py`` が
検査する。

Usage:
  check_config_phoneme_keys.py <config.json> ...   # 指定した config
  check_config_phoneme_keys.py --repo              # git 管理下の全 config
  check_config_phoneme_keys.py --distributed       # MODEL_ALIASES の HF 配布 config

``--distributed`` は取得に失敗した model を skip せず失敗として数える
(以前の inline 検査は取得失敗を WARN で skip し、 その model を検査しないまま
緑になり得た)。 一時的な失敗に備えて数回 retry する。

Exit codes:
  0 -- 全 config が C++ で load できる key だけを持つ
  1 -- load できない key / 取得できない config がある
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "spec" / "pua-contract.toml"
PUA_JSON = REPO_ROOT / "src" / "python" / "g2p" / "piper_plus_g2p" / "data" / "pua.json"
MODEL_RESOLVER = REPO_ROOT / "src" / "python_run" / "piper_plus" / "api" / "_model_resolver.py"

FETCH_ATTEMPTS = 3
FETCH_TIMEOUT_S = 30


def _hex(token: str) -> str:
    return "+".join(f"U+{ord(c):04X}" for c in token)


def load_raw_aliases() -> dict[str, int]:
    """Raw multi-codepoint key -> PUA codepoint, as the C++ reader resolves it."""
    contract = tomllib.loads(CONTRACT.read_text(encoding="utf-8"))
    names = contract["invariants"]["config_keys"]["raw_aliases"]
    entries = json.loads(PUA_JSON.read_text(encoding="utf-8"))["entries"]
    codepoints = {e["token"]: int(e["codepoint"], 16) for e in entries}
    missing = [n for n in names if n not in codepoints]
    if missing:
        raise SystemExit(f"raw_aliases not in pua.json: {[_hex(n) for n in missing]}")
    return {n: codepoints[n] for n in names}


def check_phoneme_id_map(pid_map: dict, aliases: dict[str, int]) -> list[str]:
    problems = []
    for key, ids in pid_map.items():
        if len(key) == 1:
            continue
        if key not in aliases:
            problems.append(f"unknown multi-codepoint key {key!r} ({_hex(key)})")
            continue
        pua = chr(aliases[key])
        if pua in pid_map and pid_map[pua] != ids:
            problems.append(
                f"raw key {key!r} ({_hex(key)}) has IDs {ids} but its PUA key "
                f"U+{aliases[key]:04X} has {pid_map[pua]}"
            )
    return problems


def repo_configs(root: Path = REPO_ROOT) -> list[Path]:
    """Every git-tracked JSON file whose top level has a phoneme_id_map."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "*.json"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    configs = []
    for rel in filter(None, out.split("\0")):
        path = root / rel
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("phoneme_id_map"), dict):
            configs.append(path)
    return configs


def distributed_urls() -> list[str]:
    """HF config URLs for MODEL_ALIASES, at each alias's pinned revision."""
    spec = importlib.util.spec_from_file_location("_model_resolver", MODEL_RESOLVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    urls: list[str] = []
    for alias in mod.MODEL_ALIASES.values():
        rev = alias.get("revision", "main")
        url = f"https://huggingface.co/{alias['repo_id']}/resolve/{rev}/{alias['config_file']}"
        if url not in urls:
            urls.append(url)
    return urls


def _fetch(url: str) -> dict:
    last: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_S) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — every failure is retried, then reported
            last = e
            if attempt + 1 < FETCH_ATTEMPTS:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"could not fetch after {FETCH_ATTEMPTS} attempts: {last}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("configs", nargs="*", type=Path)
    parser.add_argument("--repo", action="store_true", help="check every git-tracked config")
    parser.add_argument("--distributed", action="store_true", help="check the HF configs")
    args = parser.parse_args(argv)
    if not (args.configs or args.repo or args.distributed):
        parser.error("give config paths, --repo or --distributed")

    aliases = load_raw_aliases()
    sources: list[tuple[str, object]] = [(str(p), p) for p in args.configs]
    if args.repo:
        found = repo_configs()
        if not found:
            print("FAIL: no git-tracked config with a phoneme_id_map was found")
            return 1
        sources += [(p.relative_to(REPO_ROOT).as_posix(), p) for p in found]
    if args.distributed:
        sources += [(u, u) for u in distributed_urls()]

    failed = 0
    for label, src in sources:
        try:
            if isinstance(src, Path):
                data = json.loads(src.read_text(encoding="utf-8"))
            else:
                data = _fetch(src)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL: {label}: {e}")
            failed += 1
            continue
        pid_map = data.get("phoneme_id_map")
        # 空の map は repo 内の異常系 fixture (Go の invalid_empty_phoneme_map.json)
        # にはあり得るが、 配布 config では壊れた config なので失敗にする。
        if not isinstance(pid_map, dict) or (not pid_map and not isinstance(src, Path)):
            print(f"FAIL: {label}: no phoneme_id_map")
            failed += 1
            continue
        problems = check_phoneme_id_map(pid_map, aliases)
        raw = sorted(_hex(k) for k in pid_map if k in aliases)
        if problems:
            failed += 1
            print(f"FAIL: {label}")
            for p in problems:
                print(f"  {p}")
        else:
            note = f", raw aliases {raw}" if raw else ""
            print(f"OK: {label} ({len(pid_map)} keys{note})")

    if failed:
        print(
            f"\n{failed} config(s) failed. The C++ runtime rejects these keys "
            "(src/cpp/piper.cpp:configPhonemeCodepoint). Regenerate the config "
            "with PUA-encoded keys (`python -m piper_train.update_model_config "
            "<cfg>`); a distributed config must also be re-pushed to HuggingFace."
        )
        return 1
    print(f"\nAll {len(sources)} config(s) OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
