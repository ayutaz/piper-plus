#!/usr/bin/env python3
"""Build a lightweight MB-iSTFT-VITS2 ONNX fixture with speaker_embedding.

The fixture is used by integration tests across runtimes (Rust / C++ /
C# / E2E docker) to verify that the Issue #426 zero-embedding + mask=0
fallback works against a real ort::Session — unit tests can only assert
the input list, not the actual tensor feed semantics.

Why a custom fixture instead of `test/models/multilingual-test-medium.onnx`?
The existing test model does NOT declare speaker_embedding / mask inputs
(it predates PR #320). To exercise the fallback path we need a graph
that lists these as required inputs.

Output: `tests/fixtures/mb_istft_speaker_embedding/model.onnx`

Run:
    uv run python tests/fixtures/mb_istft_speaker_embedding/build_fixture.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch


# Allow running from repo root: append src/python so piper_train is importable.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "src" / "python"))


def build_speaker_embedding_fixture(output_path: Path) -> Path:
    """Export a tiny MB-iSTFT-VITS2 graph with speaker_embedding inputs.

    Size target: ~1-3 MB so the fixture can live in-tree without LFS.
    """
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(42)

    gin_channels = 64
    # spk_proj expects canonical 192-dim CAM++ embeddings (see
    # SynthesizerTrn.__init__: nn.Linear(192, gin_channels)). The dimension
    # is fixed by the architecture, so the fixture must match.
    spk_emb_dim = 192

    # Minimal MB-iSTFT-VITS2: small inter/hidden/filter dims, 2 upsample
    # stages, 1 layer encoder transformer.
    model = SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=8192,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.1,
        resblock="1",
        resblock_kernel_sizes=[3, 7, 11],
        resblock_dilation_sizes=[[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        upsample_rates=[4, 4],
        upsample_initial_channel=64,
        upsample_kernel_sizes=[16, 16],
        n_speakers=2,
        gin_channels=gin_channels,
        use_sdp=True,
        prosody_dim=0,
    )
    model.eval()
    model.onnx_export_mode = True
    if hasattr(model, "dp"):
        model.dp.onnx_export_mode = True
    with torch.no_grad():
        model.dec.remove_weight_norm()

    # Dummy inputs to drive the trace. Single-batch is enough for the
    # tests we run (none of the runtimes batch > 1 today).
    dummy_len = 8
    sequences = torch.randint(0, 50, (1, dummy_len), dtype=torch.long)
    seq_lengths = torch.LongTensor([dummy_len])
    scales = torch.FloatTensor([0.0, 1.0, 0.8])
    sid = torch.LongTensor([0])
    spk_emb = torch.zeros(1, spk_emb_dim, dtype=torch.float32)
    # speaker_embedding_mask is accepted for ONNX-input-schema compat with
    # runtimes that still feed it (Issue #426). After PR #222 emb_g was
    # removed and all speaker conditioning flows through spk_proj, so the
    # mask is effectively unused — a zero embedding fed through spk_proj
    # still produces a valid (deterministic) g vector.
    spk_mask = torch.zeros(1, 1, dtype=torch.int64)

    def infer_forward(
        text, text_lengths, scales_t, sid_t, speaker_embedding, speaker_embedding_mask
    ):
        from piper_train.vits import commons

        # scales_t[0] (noise_scale) is unused on this deterministic trace.
        length_scale = scales_t[1]
        noise_scale_w = scales_t[2]

        # emb_g was removed in PR #222; all speaker conditioning now goes
        # through spk_proj (2-layer MLP, 192 -> gin_channels). sid_t and
        # speaker_embedding_mask are still declared as ONNX inputs (the
        # runtimes -- Rust / C++ / C# / Python -- continue to feed them
        # for the Issue #426 schema), but they no longer affect the output.
        # We touch them in a value-preserving no-op so the tracer keeps
        # them as graph inputs instead of pruning them.
        g = model.spk_proj(speaker_embedding).unsqueeze(-1)  # (batch, gin, 1)
        _noop = (sid_t.float().sum() * 0.0) + (
            speaker_embedding_mask.float().sum() * 0.0
        )
        g = g + _noop

        x, m_p, logs_p, x_mask = model.enc_p(text, text_lengths, g=g)
        x_dp = model._prepare_prosody_input(x, x_mask, None)
        logw = model.dp(x_dp, x_mask, g=g, reverse=True, noise_scale=noise_scale_w)
        w = torch.exp(logw) * x_mask * length_scale
        durations = w.squeeze(1)
        w_ceil = torch.ceil(w)
        y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
        y_mask = torch.unsqueeze(
            commons.sequence_mask(y_lengths, y_lengths.max()), 1
        ).type_as(x_mask)
        attn_mask = torch.unsqueeze(x_mask, 2) * torch.unsqueeze(y_mask, -1)
        attn = commons.generate_path(w_ceil, attn_mask)
        m_p = torch.matmul(attn.squeeze(1), m_p.transpose(1, 2)).transpose(1, 2)
        _ = torch.matmul(attn.squeeze(1), logs_p.transpose(1, 2)).transpose(1, 2)
        z_p = m_p  # deterministic — no sampling
        z = model.flow(z_p, y_mask, g=g, reverse=True)
        o = model.dec((z * y_mask), g=g)
        return o, durations

    model.forward = infer_forward

    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        (sequences, seq_lengths, scales, sid, spk_emb, spk_mask),
        str(output_path),
        opset_version=15,
        input_names=[
            "input",
            "input_lengths",
            "scales",
            "sid",
            "speaker_embedding",
            "speaker_embedding_mask",
        ],
        output_names=["output", "durations"],
        dynamic_axes={
            "input": {0: "batch_size", 1: "phonemes"},
            "input_lengths": {0: "batch_size"},
            "sid": {0: "batch_size"},
            "speaker_embedding": {0: "batch_size"},
            "speaker_embedding_mask": {0: "batch_size"},
            "output": {0: "batch_size", 2: "time"},
            "durations": {0: "batch_size", 1: "phonemes"},
        },
        verbose=False,
        dynamo=False,
    )

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {output_path} ({size_mb:.2f} MB)")
    return output_path


def write_config(path: Path) -> None:
    """Emit a minimal piper-format config.json next to the .onnx.

    Shared by all runtime integration tests (Python infer_onnx CLI,
    Rust, C++ piper.cpp, C# PiperSession). num_speakers=2 mirrors the
    fixture's emb_g layer.
    """
    import json

    # phoneme_id_map keys MUST be single Unicode codepoints — the C++
    # runtime (`src/cpp/piper.cpp`) stores them as `char32_t` and rejects
    # multi-codepoint keys ("Phonemes must be one codepoint (phoneme id
    # map)"). Python/Rust/C# are stricter than C++ here, so using
    # single-char keys keeps the fixture interoperable with every runtime.
    #
    # Layout: id 0/1/2/3 are the conventional PAD / BOS / EOS / blank
    # tokens; ids 4-49 map to ASCII letters a..z, A..T.
    phoneme_id_map = {
        "_": [0],
        "^": [1],
        "$": [2],
        "#": [3],
    }
    for i in range(4, 50):
        # 'a' = 0x61 + 0, ..., 'z' = 0x61 + 25 = 0x7A
        # 'A' = 0x41, ..., 'T' = 0x41 + 19 — gives 26 + 20 = 46 symbols.
        offset = i - 4
        if offset < 26:
            ch = chr(0x61 + offset)  # a..z
        else:
            ch = chr(0x41 + (offset - 26))  # A..T
        phoneme_id_map[ch] = [i]

    cfg = {
        "audio": {"sample_rate": 22050},
        "phoneme_type": "raw",
        "phoneme_id_map": phoneme_id_map,
        "num_symbols": 50,
        "num_speakers": 2,
        "speaker_id_map": {"default": 0, "second": 1},
        "language_map": {},
        "espeak": {"voice": "en-us"},
        "inference": {
            "noise_scale": 0.667,
            "length_scale": 1.0,
            "noise_w": 0.8,
        },
    }
    path.write_text(json.dumps(cfg, indent=2))
    print(f"Wrote {path}")


def main() -> int:
    output_dir = Path(__file__).resolve().parent
    output_path = output_dir / "model.onnx"
    build_speaker_embedding_fixture(output_path)
    write_config(output_dir / "model.onnx.json")

    # Sanity-check the graph with onnx + onnxruntime so a broken fixture
    # cannot land in tree silently.
    import onnx

    model = onnx.load(str(output_path))
    onnx.checker.check_model(model)
    input_names = {i.name for i in model.graph.input}
    expected = {
        "input",
        "input_lengths",
        "scales",
        "sid",
        "speaker_embedding",
        "speaker_embedding_mask",
    }
    assert input_names == expected, (
        f"fixture input set mismatch: got {input_names}, want {expected}"
    )
    print(f"  inputs: {sorted(input_names)}")

    import onnxruntime as ort

    session = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    runtime_inputs = {i.name for i in session.get_inputs()}
    assert runtime_inputs == expected, (
        f"runtime input set mismatch: got {runtime_inputs}, want {expected}"
    )
    print("  ort load OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
