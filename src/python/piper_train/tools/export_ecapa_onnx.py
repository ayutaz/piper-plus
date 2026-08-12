#!/usr/bin/env python3
"""SpeechBrain ECAPA-TDNN (spkrec-ecapa-voxceleb, Apache-2.0) を ONNX 化する。

Why this exists (docs/design/zero-shot-v10-roadmap.md A-1a):
CAM++ 単独の SECS では SCL (CAM++ を学習信号に使用) の Goodhart 化を検知できない。
学習に一切関与しない held-out の第 2 encoder として ECAPA を ONNX 化し、
``eval_zs_secs --encoder2`` で並走させる。**ECAPA の SCL への組み込みは恒久禁止**
(roadmap 運用原則 2)。repo 同梱の speaker_encoder (ECAPA 実装) は学習済み重みが
存在しない (manifest pending) ため使わず、SpeechBrain の公開重みを用いる。

入出力契約:
    入力  fbank     [B, T, 80]  float32 — ``extract_speaker_embedding.
                    preprocess_audio`` の Kaldi fbank (自然対数スケール、CMN 済み)
    出力  embedding [B, 192]    float32 — L2 正規化済み

前処理互換性の調査結果 (この exporter の設計根拠):

SpeechBrain 側 (speechbrain/spkrec-ecapa-voxceleb hyperparams.yaml):
    Fbank(n_mels=80, sr=16k, n_fft=400, 25ms/10ms, **hamming 窓**, f_min=0,
    f_max=8000, triangular mel filter (HTK mel), **dB スケール** (10·log10,
    top_db=80 クランプ)) → InputNormalization(norm_type="sentence",
    std_norm=False) → ECAPA_TDNN(channels=[1024,...,3072], lin_neurons=192)

我々の preprocess_audio (CAM++ 用):
    torchaudio.compliance.kaldi.fbank(80 mel, 25ms/10ms, sr=16k) = **povey 窓**,
    pre-emphasis 0.97, remove_dc_offset, low_freq=20, **自然対数 (ln) スケール**
    → per-utterance mean subtraction (CMN)

差分と吸収方針:
    1. log スケール (ln vs 10·log10): 乗法差なので CMN では消えない。
       **graph 内で ×(10/ln10) ≈ ×4.3429 を適用して吸収**
    2. sentence-level mean norm: **graph 内に含める** (per-channel の時間平均を
       差引。preprocess_audio 側の CMN と冪等なので二重適用は無害)
    3. pre-emphasis 0.97 / povey vs hamming 窓 / mel filter エッジ (low_freq 20
       vs 0) の差: いずれも (ほぼ) 固定の per-channel ゲイン → log 域で加法定数
       → **2. の sentence CMN が吸収**。窓形状によるフレーム内ダイナミクスの
       微差のみ残るが 2 次的
    4. top_db=80 クランプ: 発話内最大値から -80dB 未満のフレームでのみ効く
       data 依存項。無音トリム済み入力ではほぼ発火しないため**吸収せず残差と
       して許容**

結論: **この exporter が出力する ONNX には preprocess_audio の fbank をそのまま
入力してよい** (ln→dB 変換 + sentence CMN を graph 内に含めているため)。
残差 (窓形状・クランプ) の影響は ``--verify-audio ref.wav`` で SpeechBrain
ネイティブ経路 (waveform → encode_batch) との cosine を実測して確認できる。

Usage:
    uv run --no-sync --with speechbrain \\
        python -m piper_train.tools.export_ecapa_onnx \\
        --output models/ecapa.onnx --verify-audio ref.wav

注意: speechbrain は重依存のためプロジェクト依存に追加しない (lazy import)。
初回実行は HF Hub から重みを DL するためネットワークが必要。CI テスト対象外。
"""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path

import numpy as np
import torch


_LOGGER = logging.getLogger(__name__)

DEFAULT_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"

# Kaldi fbank (自然対数) → SpeechBrain fbank (dB = 10·log10) のスケール換算係数
_LN_TO_DB = 10.0 / math.log(10.0)

_SPEECHBRAIN_HINT = (
    "speechbrain is required for this exporter but is not installed.\n"
    "Run it with an ephemeral dependency (do NOT add to pyproject.toml):\n"
    "    uv run --no-sync --with speechbrain \\\n"
    "        python -m piper_train.tools.export_ecapa_onnx --output ecapa.onnx"
)


class EcapaOnnxWrapper(torch.nn.Module):
    """Kaldi ln-fbank [B, T, 80] → L2 正規化 embedding [B, D]。

    graph 内で吸収する前処理差 (モジュール docstring 参照):
    - ``ln_to_db=True``: ×(10/ln10) で ln → dB スケール変換
    - sentence-level mean norm (SpeechBrain InputNormalization(norm_type=
      "sentence", std_norm=False) 相当。入力が CMN 済みでも冪等で無害)
    """

    def __init__(self, embedding_model: torch.nn.Module, ln_to_db: bool = True):
        super().__init__()
        self.embedding_model = embedding_model
        self.ln_to_db = ln_to_db

    def forward(self, fbank: torch.Tensor) -> torch.Tensor:
        x = fbank
        if self.ln_to_db:
            x = x * _LN_TO_DB
        x = x - x.mean(dim=1, keepdim=True)
        emb = self.embedding_model(x)  # [B, 1, D]
        emb = emb.squeeze(1)
        return torch.nn.functional.normalize(emb, p=2.0, dim=-1)


def load_speechbrain_classifier(source: str, savedir: str | Path):
    """SpeechBrain EncoderClassifier を lazy import で読み込む。"""
    try:
        # speechbrain >= 1.0 の推奨 import 位置
        from speechbrain.inference.speaker import (  # noqa: PLC0415 — lazy import
            EncoderClassifier,
        )
    except ImportError:
        try:
            # speechbrain < 1.0 fallback
            from speechbrain.pretrained import (  # noqa: PLC0415 — lazy import
                EncoderClassifier,
            )
        except ImportError as e:
            raise SystemExit(_SPEECHBRAIN_HINT) from e

    _LOGGER.info("loading SpeechBrain model: %s (savedir=%s)", source, savedir)
    return EncoderClassifier.from_hparams(
        source=source, savedir=str(savedir), run_opts={"device": "cpu"}
    )


def export_ecapa_onnx(
    classifier,
    output: str | Path,
    opset: int = 17,
    ln_to_db: bool = True,
) -> EcapaOnnxWrapper:
    """ECAPA embedding model を wrapper 込みで ONNX export する。"""
    embedding_model = classifier.mods.embedding_model.eval()
    wrapper = EcapaOnnxWrapper(embedding_model, ln_to_db=ln_to_db).eval()

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 300, 80, dtype=torch.float32)
    with torch.no_grad():
        out = wrapper(dummy)
    _LOGGER.info("embedding dim: %d", out.shape[-1])

    torch.onnx.export(
        wrapper,
        (dummy,),
        str(output),
        input_names=["fbank"],
        output_names=["embedding"],
        dynamic_axes={
            "fbank": {0: "batch", 1: "frames"},
            "embedding": {0: "batch"},
        },
        opset_version=opset,
    )
    _LOGGER.info("exported: %s (%.1f MB)", output, output.stat().st_size / 1e6)
    return wrapper


def verify_export(
    wrapper: EcapaOnnxWrapper, onnx_path: str | Path, threshold: float = 0.999
) -> float:
    """torch wrapper と ONNX の出力 cosine 一致を自己検証する (export 忠実性)。

    可変フレーム長 + batch 次元でランダム fbank (CMN 済み ln スケール相当) を
    流し、行ごとの cosine の最小値を返す。threshold 未満なら RuntimeError。
    """
    import onnxruntime  # noqa: PLC0415 — lazy import (推論時のみ必要)

    session = onnxruntime.InferenceSession(
        str(onnx_path), providers=["CPUExecutionProvider"]
    )
    rng = np.random.default_rng(0)
    worst = 1.0
    for batch, frames in ((1, 173), (2, 300), (1, 512)):
        fbank = (rng.standard_normal((batch, frames, 80)) * 2.0).astype(np.float32)
        with torch.no_grad():
            torch_out = wrapper(torch.from_numpy(fbank)).numpy()
        onnx_out = session.run(None, {"fbank": fbank})[0]
        for i in range(batch):
            denom = np.linalg.norm(torch_out[i]) * np.linalg.norm(onnx_out[i])
            cos = float(np.dot(torch_out[i], onnx_out[i]) / max(denom, 1e-12))
            worst = min(worst, cos)
        _LOGGER.info(
            "verify_export: batch=%d frames=%d worst-so-far cosine=%.6f",
            batch,
            frames,
            worst,
        )
    if worst < threshold:
        raise RuntimeError(
            f"ONNX export verification failed: worst cosine {worst:.6f} < "
            f"{threshold} (torch vs onnxruntime)"
        )
    _LOGGER.info("verify_export OK: worst cosine %.6f >= %.3f", worst, threshold)
    return worst


def verify_against_native(
    classifier, onnx_path: str | Path, wav_path: str | Path
) -> float:
    """前処理互換性の実測: 我々の fbank 経路 vs SpeechBrain ネイティブ経路。

    - ours: preprocess_audio (Kaldi ln fbank + CMN) → ONNX (graph 内で dB 変換
      + sentence CMN) → embedding
    - native: waveform → classifier.encode_batch (SpeechBrain Fbank + norm)

    戻り値は両 embedding の cosine (informational — 残差 (窓形状等) を含むため
    1.0 にはならない。経験的に >0.98 なら SECS 用途で実用上等価)。
    """
    import onnxruntime  # noqa: PLC0415 — lazy import
    import soundfile as sf  # noqa: PLC0415 — lazy import

    from piper_train.extract_speaker_embedding import (  # noqa: PLC0415 — lazy import
        extract_embedding,
        preprocess_audio,
    )

    # ours: Kaldi fbank → ONNX
    session = onnxruntime.InferenceSession(
        str(onnx_path), providers=["CPUExecutionProvider"]
    )
    fbank = preprocess_audio(wav_path)
    ours = extract_embedding(session, fbank)

    # native: waveform → SpeechBrain pipeline
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        import soxr  # noqa: PLC0415 — lazy import

        audio = soxr.resample(audio, sr, 16000, quality="HQ")
    wav_tensor = torch.from_numpy(np.ascontiguousarray(audio)).unsqueeze(0)
    with torch.no_grad():
        native = classifier.encode_batch(wav_tensor).squeeze().numpy()
    native = native / max(float(np.linalg.norm(native)), 1e-12)

    cos = float(np.dot(ours, native))
    _LOGGER.info(
        "verify_against_native (%s): cosine ours-vs-native = %.6f",
        wav_path,
        cos,
    )
    if cos < 0.98:
        _LOGGER.warning(
            "cosine %.4f < 0.98: preprocessing residual larger than expected; "
            "inspect the input audio (silence? clipping?) before trusting SECS",
            cos,
        )
    return cos


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="piper_train.tools.export_ecapa_onnx",
        description="SpeechBrain ECAPA-TDNN を SECS 並走用に ONNX 化する",
    )
    parser.add_argument("--output", required=True, help="出力 ONNX パス")
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"SpeechBrain model source (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--savedir",
        help="SpeechBrain 重みのキャッシュ先 (default: <output>/.speechbrain_cache)",
    )
    parser.add_argument("--opset", type=int, default=17, help="ONNX opset version")
    parser.add_argument(
        "--no-ln-to-db",
        action="store_true",
        help=(
            "graph 内の ln→dB スケール変換を無効化 (SpeechBrain 式 dB fbank を"
            "直接入力する場合のみ。preprocess_audio の fbank を使うなら不要)"
        ),
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="export 後の torch vs ONNX cosine 自己検証をスキップ",
    )
    parser.add_argument(
        "--verify-threshold",
        type=float,
        default=0.999,
        help="自己検証の最小 cosine (default: 0.999)",
    )
    parser.add_argument(
        "--verify-audio",
        help=(
            "実音声 wav で SpeechBrain ネイティブ経路との cosine を実測 "
            "(前処理互換性の確認、informational)"
        ),
    )
    args = parser.parse_args(argv)

    output = Path(args.output)
    savedir = (
        Path(args.savedir) if args.savedir else output.parent / ".speechbrain_cache"
    )

    classifier = load_speechbrain_classifier(args.source, savedir)
    wrapper = export_ecapa_onnx(
        classifier, output, opset=args.opset, ln_to_db=not args.no_ln_to_db
    )

    if not args.skip_verify:
        verify_export(wrapper, output, threshold=args.verify_threshold)
    if args.verify_audio:
        verify_against_native(classifier, output, args.verify_audio)

    _LOGGER.info(
        "done. use with: python -m piper_train.tools.eval_zs_secs --encoder2 %s ...",
        output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
