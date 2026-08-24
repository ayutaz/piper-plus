"""合成音声の明瞭度 (CER) 評価 — ASR 転写と参照テキストの文字誤り率。

v11 の教訓 (2026-08-25): SECS / comb-HNR / seen-ID はどれも「発話として
読めているか」を測らず、日本語として聞き取れないモデル (v11 ep9/19、学習量
不足) が指標上は良好に見えた。本ツールは ASR (transformers whisper、既存
依存のみ) の転写と参照テキストの CER を測り、v11b では gate に昇格する。

使い方 (listen_texts.txt 形式 = `tid<TAB>text` の tsv):

    python -m piper_train.tools.eval_cer \\
        --clips-dir <wav ディレクトリ (tid.wav)> \\
        --texts <texts.tsv> --json-out <out.json> \\
        [--asr-model openai/whisper-small] [--language ja]

CER は NFKC 正規化 + 句読点/空白除去後の文字編集距離 / 参照長。1.0 超は
clip しない (参照より長い出鱈目転写の検出力を残す)。
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import unicodedata
from pathlib import Path
from typing import Callable

_LOGGER = logging.getLogger(__name__)

# 句読点・記号・空白 (NFKC 後に除去)。ASR の表記揺れを CER に数えない。
_STRIP_CATEGORIES = ("P", "Z", "S")  # punctuation / separator / symbol


def normalize_text(text: str) -> str:
    """NFKC 正規化 + 句読点/空白/記号の除去。"""
    text = unicodedata.normalize("NFKC", text)
    return "".join(
        ch for ch in text if unicodedata.category(ch)[0] not in _STRIP_CATEGORIES
    )


def _levenshtein(a: str, b: str) -> int:
    """文字単位の編集距離 (挿入/削除/置換 = 1)。"""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(
                min(
                    prev[j] + 1,  # 削除
                    cur[j - 1] + 1,  # 挿入
                    prev[j - 1] + (ca != cb),  # 置換
                )
            )
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    """正規化後の文字誤り率 = 編集距離 / 参照長。参照が空なら ValueError。"""
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        raise ValueError("reference text is empty after normalization")
    return _levenshtein(ref, hyp) / len(ref)


def evaluate_clips(
    pairs: list[tuple[Path, str]],
    transcribe_fn: Callable[[Path], str],
) -> dict:
    """(wav, 参照テキスト) のリストを転写して CER を集計する。

    ``transcribe_fn`` は wav パス → 転写文字列。テストではここを差し替えて
    ASR 非依存に検証する (score_utmos の torch.hub monkeypatch と同じ流儀)。
    """
    per_file: dict[str, dict] = {}
    values: list[float] = []
    for wav, ref in pairs:
        hyp = transcribe_fn(wav)
        c = cer(ref, hyp)
        per_file[Path(wav).stem] = {"cer": c, "transcript": hyp, "reference": ref}
        values.append(c)
    return {
        "per_file": per_file,
        "cer_median": statistics.median(values),
        "cer_mean": statistics.fmean(values),
        "n_clips": len(values),
    }


def build_whisper_transcribe_fn(
    model_name: str = "openai/whisper-small",
    language: str = "ja",
) -> Callable[[Path], str]:
    """transformers の whisper pipeline で transcribe_fn を作る (CPU)。

    追加依存なし (transformers は train extras に既存)。モデルは初回に
    HF Hub から自動 DL される。
    """
    from transformers import pipeline  # noqa: PLC0415

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model_name,
        device=-1,
    )

    def transcribe(wav: Path) -> str:
        out = pipe(
            str(wav),
            generate_kwargs={"language": language, "task": "transcribe"},
        )
        return out["text"]

    return transcribe


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clips-dir", required=True, help="tid.wav のディレクトリ")
    ap.add_argument(
        "--texts", required=True, help="参照テキスト tsv (tid<TAB>text、listen_texts 形式)"
    )
    ap.add_argument("--json-out", help="集計 JSON の出力先")
    ap.add_argument("--asr-model", default="openai/whisper-small")
    ap.add_argument("--language", default="ja")
    args = ap.parse_args()

    refs: dict[str, str] = {}
    for line in Path(args.texts).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tid, text = line.split("\t", 1)
        refs[tid] = text

    pairs = []
    for wav in sorted(Path(args.clips_dir).glob("*.wav")):
        if wav.stem not in refs:
            _LOGGER.warning("参照テキストが無い wav をスキップ: %s", wav.name)
            continue
        pairs.append((wav, refs[wav.stem]))
    if not pairs:
        raise SystemExit(f"評価対象なし: {args.clips_dir}")

    transcribe = build_whisper_transcribe_fn(args.asr_model, args.language)
    result = evaluate_clips(pairs, transcribe)
    result["asr_model"] = args.asr_model
    result["language"] = args.language

    for tid, r in result["per_file"].items():
        _LOGGER.info("%s: CER %.3f | %s", tid, r["cer"], r["transcript"])
    print(
        f"cer median: {result['cer_median']:.3f} / mean: {result['cer_mean']:.3f} "
        f"(n={result['n_clips']}, asr={args.asr_model})"
    )

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
