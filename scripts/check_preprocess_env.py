#!/usr/bin/env python3
"""学習前処理を実行する環境 (GPU instance 等) の事前検証。

v8 dataset 再構築 (2026-08-01/02) で「環境不備が exit 0 の静かな成功として
通過し、数時間後の検証 gate まで気づけない」障害が 3 連発した。いずれも
前処理を走らせる **前** に数秒で検出できたもの:

  1. piper-plus-g2p が PyPI の古い版 (extended 8-lang inventory 欠落)
  2. NLTK data 未ダウンロード (g2p-en が全発話 LookupError)
  3. audio_norm cache reader/writer の形式不整合 (.npy を読めない)
  4. pyarrow 欠落 (parquet export が即死)

このスクリプトは前処理開始前に 1 回実行し、全チェック PASS を確認する。
リモート instance では:

    python /path/to/piper-plus/scripts/check_preprocess_env.py

Exit code: 0 = 全 PASS、1 = FAIL あり (前処理を開始してはならない)。
"""

from __future__ import annotations

import importlib
import sys


# Windows console (cp932) でも死なないよう UTF-8 に固定 (best-effort)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:  # pragma: no cover - very old Python
    pass

# ko=7 まで含む extended 8-lang inventory の契約シンボル数。
# piper-plus-g2p がローカル canonical (branch 同梱) であることの検証に使う。
# docs/spec/language-id-map-contract.toml (python_train =
# extended_language_id_map) と同期。変更時は両方更新すること。
EXPECTED_EXTENDED_SYMBOLS = 185
EXTENDED_LANG_KEY = "ja-en-zh-es-fr-pt-sv-ko"

_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def check_g2p_inventory() -> None:
    """piper-plus-g2p が extended 8-lang inventory を持つこと (バグ 1)。"""
    try:
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

        n = len(get_phoneme_id_map(EXTENDED_LANG_KEY))
        _check(
            "g2p extended inventory",
            n == EXPECTED_EXTENDED_SYMBOLS,
            f"symbols={n} (expected {EXPECTED_EXTENDED_SYMBOLS}; mismatch = "
            "stale PyPI piper-plus-g2p — install the repo-local package: "
            "pip install -e src/python/g2p[all])",
        )
    except Exception as e:  # noqa: BLE001
        _check("g2p extended inventory", False, f"{type(e).__name__}: {e}")


def check_en_phonemizer() -> None:
    """EN 音素化が実際に 1 発話通ること (バグ 2: NLTK data)。"""
    try:
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en"])
        ph, _ = p.phonemize_with_prosody("Hello world.")
        _check("EN phonemize (NLTK data)", len(ph) > 0, f"{len(ph)} phonemes")
    except Exception as e:  # noqa: BLE001
        _check(
            "EN phonemize (NLTK data)",
            False,
            f'{type(e).__name__} — fix: python -c "import nltk; '
            "[nltk.download(p) for p in ['averaged_perceptron_tagger_eng',"
            "'averaged_perceptron_tagger','cmudict','punkt']]\"",
        )


def check_ko_phonemizer(required: bool) -> None:
    """KO 音素化 (g2pk2 + mecab backend) が通ること。

    mecab-ko はローカル開発機 (特に Windows) に無いことが多いため、
    ko を前処理する環境でのみ ``--require-ko`` で必須化する。
    required=False で失敗した場合は WARN 止まり (exit code に影響しない)。
    """
    try:
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer().phonemize("안녕하세요")
        _check("KO phonemize (g2pk2/mecab)", len(ph) > 0, f"{len(ph)} phonemes")
    except Exception as e:  # noqa: BLE001
        detail = f"{type(e).__name__}: {e}"
        if required:
            _check("KO phonemize (g2pk2/mecab)", False, detail)
        else:
            print(
                f"[WARN] KO phonemize (g2pk2/mecab) -- {detail} "
                "(ko を前処理する場合は --require-ko で必須化)"
            )


def check_audio_norm_roundtrip() -> None:
    """audio_norm cache の write → read が両形式で成立すること (バグ 3)。"""
    import tempfile
    from pathlib import Path

    try:
        import torch

        from piper_train.norm_audio import (
            _atomic_npy_save,
            load_audio_norm_tensor,
        )

        with tempfile.TemporaryDirectory() as td:
            t = torch.rand(64)
            npy = Path(td) / "t.npy"
            _atomic_npy_save(t, npy)
            back = load_audio_norm_tensor(npy)
            pt = Path(td) / "t.pt"
            torch.save(t, pt)
            back2 = load_audio_norm_tensor(pt)
        ok = torch.equal(back, t) and torch.equal(back2, t)
        _check("audio_norm cache roundtrip (.npy/.pt)", ok)
    except Exception as e:  # noqa: BLE001
        _check(
            "audio_norm cache roundtrip (.npy/.pt)", False, f"{type(e).__name__}: {e}"
        )


def check_imports() -> None:
    """前処理 CLI が遅延 import する依存 (バグ 4: pyarrow 等)。"""
    for mod, why in [
        ("pyarrow.parquet", "export_libritts_r/cml_tts_from_parquet"),
        ("soundfile", "audio decode"),
        ("soxr", "resample"),
        ("onnxruntime", "CAM++ embedding"),
        ("torchaudio", "fbank"),
    ]:
        try:
            importlib.import_module(mod)
            _check(f"import {mod}", True)
        except ImportError as e:
            _check(f"import {mod}", False, f"needed by {why}: {e}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--require-ko",
        action="store_true",
        help="KO phonemize チェックを必須化 (ko を前処理する環境で指定)",
    )
    args = parser.parse_args()

    print("=== piper-plus preprocess environment check ===")
    check_imports()
    check_g2p_inventory()
    check_en_phonemizer()
    check_ko_phonemizer(required=args.require_ko)
    check_audio_norm_roundtrip()

    failed = [name for name, ok, _ in _RESULTS if not ok]
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(_RESULTS)}): {', '.join(failed)}")
        print("前処理を開始しないでください — 上記 FAIL を解消してから再実行。")
        return 1
    print(f"RESULT: ALL PASS ({len(_RESULTS)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
