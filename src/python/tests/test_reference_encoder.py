"""Task 5R: 参照スペクトログラム encoder (F-mel) と容量対照 (Ccap) の TDD。

docs/design/zero-shot-reference-fusion-plan-2026-10-17.md §8.2 / §8.4:

* ``ReferenceSpecEncoder``: 参照発話の**線形振幅** spec ``[B, 513, T]`` を
  log 圧縮 → spectral MLP → Conv1dGLU×2 (mask 付き) → self-attention
  (key padding mask) → fp32 masked 時間平均 → zero-init Linear で
  ``[B, gin, 1]`` にする。
* ``CapacityControl``: 192 次元 CAM++ 埋め込みの MLP (最終層 zero-init)。
  追加パラメータ数を ``ReferenceSpecEncoder`` の ±5% に合わせる対照。
* 合流: ``g_spk = spk_proj(e) + reference_encoder(spec)`` (lang 成分には
  足さない)。zero-init なので初期状態の出力は旧モデルと bit 一致。

固定する契約:

* **既定 ``reference_conditioning="none"`` は旧モデルと bit 互換**
  (state_dict キー・重み・forward/infer 出力・CLI 既定値)。
* **zero-init 恒等**: ``ref_spec`` / ``capacity`` は初期状態で ``spk_proj``
  のみの出力と bit 一致し、``spk_proj`` への勾配も変えない。
* **mask の正しさ**: 末尾 padding の長さ・中身、batch 内の他行の参照は
  出力に影響しない。
* **異常系は明示エラー**: 長さ 0、形状違い、dtype 違い、NaN/Inf、
  負値 (log spec の取り違え)、参照の欠落、旧モデルへの参照入力。
"""

from __future__ import annotations

import math
import warnings

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.reference_encoder import (  # noqa: E402
    CapacityControl,
    ReferenceSpecEncoder,
    reference_spec_encoder_param_count,
)


SPEC_CHANNELS = 513
GIN = 64
N_VOCAB = 40

# padding / batch 独立性の許容誤差。mask が正しく効いていれば差は fp32 の
# 縮約順序 (GEMM のブロッキングが T や batch 構成で変わる) だけで生じる。
# 縮約長は最大 ~600 項 (spectral Linear 513 項・attention T 項)、各項は
# O(1) なので相対誤差の典型値は sqrt(600)·eps32 ≈ 3e-6。漏れがあれば
# O(1e-2) 以上の差が出る (下の pad 値は 1e3 倍の大きさにしてある)。
MASK_ATOL = 1e-5
MASK_RTOL = 1e-5


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _linear_spec(b: int, t: int, seed: int = 0, dtype=torch.float32):
    """``spectrogram_torch`` と同じ値域 (正の線形振幅) のダミー spec。"""
    gen = torch.Generator().manual_seed(seed)
    spec = torch.rand(b, SPEC_CHANNELS, t, generator=gen) * 3.0 + 1e-3
    return spec.to(dtype)


def _randomize_output(module: torch.nn.Module, seed: int = 99) -> None:
    """zero-init の最終層を非ゼロにする (経路を実際に通すテスト用)。"""
    gen = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        module.out.weight.copy_(
            torch.randn(module.out.weight.shape, generator=gen) * 0.1
        )
        module.out.bias.copy_(torch.randn(module.out.bias.shape, generator=gen) * 0.1)


def _encoder(seed: int = 0, gin: int = GIN, randomize: bool = True):
    torch.manual_seed(seed)
    enc = ReferenceSpecEncoder(SPEC_CHANNELS, gin)
    if randomize:
        _randomize_output(enc)
    enc.eval()
    return enc


def _build_synthesizer(seed: int = 1234, **overrides):
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(seed)
    kwargs: dict = {
        "n_vocab": N_VOCAB,
        "spec_channels": SPEC_CHANNELS,
        "segment_size": 16,
        "inter_channels": 32,
        "hidden_channels": 32,
        "filter_channels": 64,
        "n_heads": 2,
        "n_layers": 1,
        "kernel_size": 3,
        "p_dropout": 0.0,
        "resblock": "2",
        "resblock_kernel_sizes": (3,),
        "resblock_dilation_sizes": ((1, 2),),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 64,
        "upsample_kernel_sizes": (16, 16),
        "n_speakers": 4,
        "n_languages": 2,
        "gin_channels": GIN,
        "use_sdp": True,
        "prosody_dim": 0,
    }
    kwargs.update(overrides)
    model = SynthesizerTrn(**kwargs)
    model.eval()
    return model


def _speaker_embeddings(b: int = 2, seed: int = 3):
    gen = torch.Generator().manual_seed(seed)
    return torch.nn.functional.normalize(torch.randn(b, 192, generator=gen), dim=-1)


def _text(b: int = 2, n: int = 10, seed: int = 4):
    gen = torch.Generator().manual_seed(seed)
    x = torch.randint(1, N_VOCAB, (b, n), generator=gen)
    lengths = torch.full((b,), n, dtype=torch.long)
    return x, lengths


def _infer(model, ref=None, ref_len=None, b: int = 2, seed: int = 11):
    x, x_len = _text(b)
    emb = _speaker_embeddings(b)
    lid = torch.zeros(b, dtype=torch.long)
    kwargs = {}
    if ref is not None or ref_len is not None:
        kwargs = {"reference_spec": ref, "reference_spec_lengths": ref_len}
    torch.manual_seed(seed)
    with torch.no_grad():
        return model.infer(x, x_len, lid=lid, speaker_embeddings=emb, **kwargs)


def _load_legacy_weights(target, legacy) -> None:
    """legacy の重みを target に入れる。target 側の欠落は新設モジュールのみ。"""
    missing, unexpected = target.load_state_dict(legacy.state_dict(), strict=False)
    assert unexpected == []
    assert all(
        k.startswith(("reference_encoder.", "capacity_control.")) for k in missing
    ), missing


# ---------------------------------------------------------------------------
# ReferenceSpecEncoder 単体
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReferenceSpecEncoderShapes:
    def test_output_shape_and_dtype(self):
        enc = _encoder()
        out = enc(_linear_spec(3, 20), torch.tensor([20, 7, 1]))
        assert out.shape == (3, GIN, 1)
        assert out.dtype == torch.float32

    def test_final_linear_is_zero_initialised(self):
        enc = _encoder(randomize=False)
        assert torch.count_nonzero(enc.out.weight) == 0
        assert torch.count_nonzero(enc.out.bias) == 0

    def test_zero_init_output_is_exactly_zero(self):
        enc = _encoder(randomize=False)
        out = enc(_linear_spec(2, 12), torch.tensor([12, 5]))
        assert torch.count_nonzero(out) == 0

    def test_output_depends_on_reference_content(self):
        """経路が生きている (定数出力に潰れていない) ことの確認。"""
        enc = _encoder()
        lengths = torch.tensor([16])
        a = enc(_linear_spec(1, 16, seed=1), lengths)
        b = enc(_linear_spec(1, 16, seed=2), lengths)
        assert (a - b).abs().max() > 1e-3

    def test_rejects_even_kernel_size(self):
        with pytest.raises(ValueError, match="kernel_size"):
            ReferenceSpecEncoder(SPEC_CHANNELS, GIN, kernel_size=4)

    def test_rejects_hidden_not_divisible_by_heads(self):
        with pytest.raises(ValueError, match="n_heads"):
            ReferenceSpecEncoder(SPEC_CHANNELS, GIN, hidden_channels=129, n_heads=2)

    def test_rejects_non_positive_gin(self):
        with pytest.raises(ValueError, match="gin_channels"):
            ReferenceSpecEncoder(SPEC_CHANNELS, 0)


@pytest.mark.unit
class TestReferenceSpecEncoderMasking:
    def test_padding_does_not_change_output(self):
        """末尾 padding の長さ (0 / 5 / 40 frame) と中身 (0 / 巨大値) を
        変えても有効 frame が同じなら出力は変わらない。"""
        enc = _encoder()
        valid = _linear_spec(1, 17, seed=5)
        lengths = torch.tensor([17])
        with torch.no_grad():
            base = enc(valid, lengths)
            for pad_len, pad_value in ((5, 0.0), (40, 0.0), (5, 1e3), (40, 1e3)):
                pad = torch.full((1, SPEC_CHANNELS, pad_len), pad_value)
                out = enc(torch.cat([valid, pad], dim=-1), lengths)
                torch.testing.assert_close(out, base, atol=MASK_ATOL, rtol=MASK_RTOL)

    def test_batch_rows_independent(self):
        """batch 内の他行の参照 (中身も長さも) が自分の行の出力に影響しない。"""
        enc = _encoder()
        spec_a = _linear_spec(2, 30, seed=6)
        spec_b = spec_a.clone()
        spec_b[1] = _linear_spec(1, 30, seed=7)[0] * 5.0
        with torch.no_grad():
            out_a = enc(spec_a, torch.tensor([21, 30]))
            out_b = enc(spec_b, torch.tensor([21, 9]))
        torch.testing.assert_close(out_b[0], out_a[0], atol=MASK_ATOL, rtol=MASK_RTOL)
        assert (out_b[1] - out_a[1]).abs().max() > 1e-3

    def test_batched_equals_individual(self):
        """batch=1 で個別に流した結果と、padding 付き batch=3 の各行が一致。"""
        enc = _encoder()
        lengths = [25, 1, 13]
        specs = [_linear_spec(1, n, seed=20 + i) for i, n in enumerate(lengths)]
        batch = torch.zeros(3, SPEC_CHANNELS, max(lengths))
        for i, s in enumerate(specs):
            batch[i, :, : s.shape[-1]] = s[0]
        with torch.no_grad():
            batched = enc(batch, torch.tensor(lengths))
            for i, s in enumerate(specs):
                single = enc(s, torch.tensor([lengths[i]]))
                torch.testing.assert_close(
                    batched[i], single[0], atol=MASK_ATOL, rtol=MASK_RTOL
                )


@pytest.mark.unit
class TestReferenceSpecEncoderBoundaries:
    def test_length_one_reference(self):
        """1 frame の参照は有限で、T=1 の入力と同じ値になる。"""
        enc = _encoder()
        spec = _linear_spec(1, 9, seed=8)
        with torch.no_grad():
            padded = enc(spec, torch.tensor([1]))
            exact = enc(spec[:, :, :1], torch.tensor([1]))
        assert torch.isfinite(padded).all()
        torch.testing.assert_close(padded, exact, atol=MASK_ATOL, rtol=MASK_RTOL)

    def test_full_length_without_padding(self):
        """長さ == T (padding なし) の行も通る (最大長の境界)。"""
        enc = _encoder()
        out = enc(_linear_spec(2, 12), torch.tensor([12, 12]))
        assert torch.isfinite(out).all()

    def test_long_fp16_reference_is_finite(self):
        """8000 frame (≈93 秒) の fp16 入力でも有限。fp32 module は入力を
        fp32 に上げてから log 圧縮するので、fp16 で丸めた同じ値を fp32 で
        渡した場合と bit 一致する。"""
        enc = _encoder()
        spec16 = _linear_spec(1, 8000, seed=9, dtype=torch.float16)
        lengths = torch.tensor([8000])
        with torch.no_grad():
            out16 = enc(spec16, lengths)
            out32 = enc(spec16.float(), lengths)
        assert torch.isfinite(out16).all()
        assert torch.equal(out16, out32)

    def test_long_reference_half_precision_module_is_finite(self):
        """module 自体を fp16 にしても 8000 frame で overflow しない
        (時間平均は fp32 で取る)。"""
        device = "cuda" if torch.cuda.is_available() else "cpu"
        enc = _encoder().half().to(device)
        spec16 = _linear_spec(1, 8000, seed=10, dtype=torch.float16).to(device)
        with torch.no_grad():
            out = enc(spec16, torch.tensor([8000], device=device))
        assert torch.isfinite(out).all()

    def test_small_magnitudes_are_floored_not_minus_inf(self):
        """振幅 0 (無音) は log(1e-5) に下限を取り -inf にならない。"""
        enc = _encoder()
        spec = torch.zeros(1, SPEC_CHANNELS, 6)
        out = enc(spec, torch.tensor([6]))
        assert torch.isfinite(out).all()


@pytest.mark.unit
class TestReferenceSpecEncoderErrors:
    def test_zero_length_reference_raises(self):
        enc = _encoder()
        with pytest.raises(ValueError, match="length"):
            enc(_linear_spec(2, 10), torch.tensor([10, 0]))

    def test_negative_length_raises(self):
        enc = _encoder()
        with pytest.raises(ValueError, match="length"):
            enc(_linear_spec(1, 10), torch.tensor([-3]))

    def test_empty_time_axis_raises(self):
        enc = _encoder()
        with pytest.raises(ValueError, match="length"):
            enc(torch.zeros(1, SPEC_CHANNELS, 0), torch.tensor([0]))

    def test_length_longer_than_spec_raises(self):
        enc = _encoder()
        with pytest.raises(ValueError, match="length"):
            enc(_linear_spec(1, 10), torch.tensor([11]))

    @pytest.mark.parametrize(
        ("make_spec", "make_lengths", "exc", "match"),
        [
            pytest.param(lambda s: s[0], lambda n: n, ValueError, "3-D", id="spec_2d"),
            pytest.param(
                lambda s: s[:, :80],
                lambda n: n,
                ValueError,
                "channels",
                id="spec_wrong_channels",
            ),
            pytest.param(
                lambda s: s,
                lambda n: n[:1],
                ValueError,
                "lengths",
                id="lengths_batch_mismatch",
            ),
            pytest.param(
                lambda s: s,
                lambda n: n.view(2, 1),
                ValueError,
                "lengths",
                id="lengths_2d",
            ),
            pytest.param(
                lambda s: s,
                lambda n: n.float(),
                TypeError,
                "lengths",
                id="lengths_float",
            ),
            pytest.param(
                lambda s: s,
                lambda n: n.int(),
                TypeError,
                "lengths",
                id="lengths_int32",
            ),
            pytest.param(
                lambda s: s.long(),
                lambda n: n,
                TypeError,
                "floating",
                id="spec_integer",
            ),
        ],
    )
    def test_shape_and_dtype_errors(self, make_spec, make_lengths, exc, match):
        """形状・dtype の取り違えは黙って broadcast せず明示エラー。"""
        enc = _encoder()
        spec = _linear_spec(2, 10)
        lengths = torch.tensor([10, 10])
        with pytest.raises(exc, match=match):
            enc(make_spec(spec), make_lengths(lengths))

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite_spec_raises(self, bad):
        enc = _encoder()
        spec = _linear_spec(1, 10)
        spec[0, 3, 4] = bad
        with pytest.raises(ValueError, match="finite"):
            enc(spec, torch.tensor([10]))

    def test_non_finite_in_padding_also_raises(self):
        """padding 内の NaN も 0 倍で消えないため受け付けない。"""
        enc = _encoder()
        spec = _linear_spec(1, 10)
        spec[0, 0, 9] = math.nan
        with pytest.raises(ValueError, match="finite"):
            enc(spec, torch.tensor([5]))

    def test_negative_values_raise(self):
        """線形振幅は非負。負値は log spec の取り違えとして拒否する。"""
        enc = _encoder()
        spec = torch.log(_linear_spec(1, 10))
        with pytest.raises(ValueError, match="linear magnitude"):
            enc(spec, torch.tensor([10]))


@pytest.mark.unit
class TestReferenceSpecEncoderGradient:
    def test_encoder_receives_gradient_after_steps(self):
        """step 0 は最終層 (zero-init) だけに勾配が届き、数 step で全層に届く
        (zero-init でも学習が始まる)。"""
        torch.manual_seed(0)
        enc = ReferenceSpecEncoder(SPEC_CHANNELS, GIN)
        enc.train()
        spec = _linear_spec(2, 24, seed=12)
        lengths = torch.tensor([24, 15])
        target = torch.randn(2, GIN, 1, generator=torch.Generator().manual_seed(1))
        opt = torch.optim.SGD(enc.parameters(), lr=0.1)

        def step():
            opt.zero_grad()
            loss = (enc(spec, lengths) - target).pow(2).mean()
            loss.backward()
            return loss

        step()
        upstream = [p for n, p in enc.named_parameters() if not n.startswith("out.")]
        assert enc.out.weight.grad.abs().sum() > 0
        assert all(p.grad is None or p.grad.abs().sum() == 0 for p in upstream)

        opt.step()
        losses = []
        for _ in range(3):
            losses.append(float(step().detach()))
            opt.step()
        for name, p in enc.named_parameters():
            assert p.grad is not None and p.grad.abs().sum() > 0, name
        assert losses[-1] < losses[0]


# ---------------------------------------------------------------------------
# host 同期 / export 中の検査省略 / autocast
# ---------------------------------------------------------------------------


def _count_cuda_syncs(fn) -> int:
    """``fn`` 実行中に CUDA の同期 (host 待ち) が起きた回数を数える。"""
    torch.cuda.synchronize()
    torch.cuda.set_sync_debug_mode("warn")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fn()
    finally:
        torch.cuda.set_sync_debug_mode(0)
    return sum("synchronizing" in str(w.message) for w in caught)


@pytest.mark.unit
class TestHostSync:
    """データ依存の入力検査は encoder 1 回につき host 同期 1 回にまとめる
    (Task 7R で forward / SCL / swap / telemetry から毎 step 呼ばれるため)。"""

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
    def test_encoder_forward_syncs_host_once(self):
        enc = _encoder().cuda()
        spec = _linear_spec(2, 50, seed=30).cuda()
        lengths = torch.tensor([50, 20]).cuda()
        with torch.no_grad():
            enc(spec, lengths)  # warm-up (初回の allocator 等を除外)
            n = _count_cuda_syncs(lambda: enc(spec, lengths))
        assert n == 1

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
    def test_capacity_forward_syncs_host_once(self):
        target = reference_spec_encoder_param_count(SPEC_CHANNELS, GIN)
        ccap = CapacityControl(192, GIN, target).cuda()
        emb = _speaker_embeddings(2).cuda()
        with torch.no_grad():
            ccap(emb)
            n = _count_cuda_syncs(lambda: ccap(emb))
        assert n == 1

    def test_masked_mean_without_check_matches_checked(self):
        """呼び出し側で長さ検査済みのときに使う ``check=False`` も同じ値。"""
        from piper_train.reference_frontend import masked_time_mean_fp32

        x = torch.randn(2, 4, 7, generator=torch.Generator().manual_seed(31))
        mask = torch.ones(2, 1, 7)
        mask[1, :, 3:] = 0.0
        assert torch.equal(
            masked_time_mean_fp32(x, mask, check=False),
            masked_time_mean_fp32(x, mask),
        )


def _export_encoder(enc, path, spec, lengths):
    torch.onnx.export(
        enc,
        (spec, lengths),
        str(path),
        opset_version=17,
        input_names=["spec", "spec_lengths"],
        output_names=["delta"],
        dynamic_axes={
            "spec": {0: "batch", 2: "frames"},
            "spec_lengths": {0: "batch"},
            "delta": {0: "batch"},
        },
        dynamo=False,
    )


@pytest.mark.unit
class TestOnnxExportSkipsDataChecks:
    """ONNX trace 中はデータ依存の検査 (``bool(tensor)``) を飛ばす。走らせると
    trace 時の入力で分岐が定数として焼き込まれる (TracerWarning)。"""

    @pytest.fixture(scope="class")
    def exported(self, tmp_path_factory):
        pytest.importorskip("onnx", reason="onnx required")
        pytest.importorskip("onnxruntime", reason="onnxruntime required")
        enc = _encoder()
        path = tmp_path_factory.mktemp("ref_enc_onnx") / "ref_enc.onnx"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _export_encoder(enc, path, _linear_spec(1, 20, seed=32), torch.tensor([20]))
        return enc, path, caught

    def test_no_data_dependent_branch_is_traced(self, exported):
        _enc, _path, caught = exported
        traced = [
            str(w.message)
            for w in caught
            if issubclass(w.category, torch.jit.TracerWarning)
            and (
                "reference_encoder" in w.filename or "reference_frontend" in w.filename
            )
        ]
        assert traced == []

    def test_onnx_matches_torch_on_other_shapes(self, exported):
        """trace と異なる batch / frame 数 / 長さでも torch と一致 (検査や
        長さが定数として焼き込まれていない)。"""
        import onnxruntime

        enc, path, _caught = exported
        spec = _linear_spec(2, 37, seed=33)
        lengths = torch.tensor([37, 9])
        with torch.no_grad():
            expected = enc(spec, lengths).numpy()
        sess = onnxruntime.InferenceSession(
            str(path), providers=["CPUExecutionProvider"]
        )
        got = sess.run(None, {"spec": spec.numpy(), "spec_lengths": lengths.numpy()})[0]
        # ORT と torch の fp32 kernel 差 (縮約順序) のみ。MASK_ATOL と同じ根拠
        torch.testing.assert_close(
            torch.from_numpy(got),
            torch.from_numpy(expected),
            atol=MASK_ATOL,
            rtol=MASK_RTOL,
        )

    def test_eager_checks_still_raise_after_export(self, exported):
        enc, _path, _caught = exported
        with pytest.raises(ValueError, match="length"):
            enc(_linear_spec(1, 10), torch.tensor([0]))


@pytest.mark.unit
class TestBf16Autocast:
    """学習既定 (bf16-mixed) 相当の autocast 下でも有限で、時間平均は fp32。"""

    def test_encoder_output_is_finite_under_bf16_autocast(self):
        enc = _encoder()
        with torch.no_grad(), torch.autocast("cpu", dtype=torch.bfloat16):
            out = enc(_linear_spec(2, 2000, seed=34), torch.tensor([2000, 700]))
        assert torch.isfinite(out.float()).all()

    def test_pooled_features_are_fp32_under_bf16_autocast(self):
        enc = _encoder()
        with torch.no_grad(), torch.autocast("cpu", dtype=torch.bfloat16):
            pooled = enc.pooled_features(
                _linear_spec(2, 2000, seed=35), torch.tensor([2000, 700])
            )
        assert pooled.dtype == torch.float32
        assert pooled.shape == (2, enc.hidden_channels)
        assert torch.isfinite(pooled).all()

    def test_model_infer_with_ref_spec_is_finite_under_bf16_autocast(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        _randomize_output(model.reference_encoder)
        with torch.autocast("cpu", dtype=torch.bfloat16):
            out = _infer(model, _linear_spec(2, 300, seed=36), torch.tensor([300, 120]))
        assert torch.isfinite(out.audio.float()).all()

    def test_model_forward_with_ref_spec_is_finite_under_bf16_autocast(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        _randomize_output(model.reference_encoder)
        x, x_len = _text(2)
        with torch.no_grad(), torch.autocast("cpu", dtype=torch.bfloat16):
            out = model(
                x,
                x_len,
                _linear_spec(2, 40, seed=37),
                torch.tensor([40, 33]),
                lid=torch.tensor([0, 1]),
                speaker_embeddings=_speaker_embeddings(2),
                reference_spec=_linear_spec(2, 300, seed=38),
                reference_spec_lengths=torch.tensor([300, 120]),
            )
        assert torch.isfinite(out.waveform.float()).all()


# ---------------------------------------------------------------------------
# CapacityControl
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCapacityControl:
    def test_capacity_control_param_count_within_5pct(self):
        """gin=512 で F-mel encoder と追加パラメータ数が ±5% 以内。"""
        target = reference_spec_encoder_param_count(SPEC_CHANNELS, 512)
        ccap = CapacityControl(192, 512, target)
        n = sum(p.numel() for p in ccap.parameters())
        assert abs(n - target) / target <= 0.05

    def test_param_count_helper_matches_instantiated_encoder(self):
        enc = ReferenceSpecEncoder(SPEC_CHANNELS, 512)
        assert reference_spec_encoder_param_count(SPEC_CHANNELS, 512) == sum(
            p.numel() for p in enc.parameters()
        )

    @pytest.mark.parametrize("gin", [64, 256, 512])
    def test_param_count_within_5pct_across_gin(self, gin):
        target = reference_spec_encoder_param_count(SPEC_CHANNELS, gin)
        n = sum(p.numel() for p in CapacityControl(192, gin, target).parameters())
        assert abs(n - target) / target <= 0.05

    def test_unreachable_target_raises(self):
        """hidden=1 でも ±5% に入らない小さすぎる target は明示エラー。"""
        with pytest.raises(ValueError, match="target_params"):
            CapacityControl(192, 512, 100)

    def test_output_shape_and_zero_init(self):
        target = reference_spec_encoder_param_count(SPEC_CHANNELS, GIN)
        ccap = CapacityControl(192, GIN, target)
        out = ccap(_speaker_embeddings(3))
        assert out.shape == (3, GIN, 1)
        assert torch.count_nonzero(out) == 0
        assert torch.count_nonzero(ccap.out.weight) == 0
        assert torch.count_nonzero(ccap.out.bias) == 0

    @staticmethod
    def _non_finite_embedding(value: float):
        bad = _speaker_embeddings(2)
        bad[1, 0] = value
        return bad

    @pytest.mark.parametrize(
        ("make_input", "exc", "match"),
        [
            pytest.param(
                lambda: torch.randn(2, 256), ValueError, "192", id="wrong_dim"
            ),
            pytest.param(lambda: torch.randn(192), ValueError, "2-D", id="1d"),
            pytest.param(
                lambda: torch.ones(2, 192, dtype=torch.long),
                TypeError,
                "floating",
                id="integer",
            ),
            pytest.param(
                lambda: TestCapacityControl._non_finite_embedding(math.nan),
                ValueError,
                "finite",
                id="nan",
            ),
            pytest.param(
                lambda: TestCapacityControl._non_finite_embedding(math.inf),
                ValueError,
                "finite",
                id="inf",
            ),
        ],
    )
    def test_input_errors(self, make_input, exc, match):
        target = reference_spec_encoder_param_count(SPEC_CHANNELS, GIN)
        ccap = CapacityControl(192, GIN, target)
        with pytest.raises(exc, match=match):
            ccap(make_input())

    def test_receives_gradient_after_steps(self):
        torch.manual_seed(0)
        target_params = reference_spec_encoder_param_count(SPEC_CHANNELS, GIN)
        ccap = CapacityControl(192, GIN, target_params)
        emb = _speaker_embeddings(4)
        target = torch.randn(4, GIN, 1, generator=torch.Generator().manual_seed(2))
        opt = torch.optim.SGD(ccap.parameters(), lr=0.1)
        for _ in range(3):
            opt.zero_grad()
            (ccap(emb) - target).pow(2).mean().backward()
            opt.step()
        opt.zero_grad()
        (ccap(emb) - target).pow(2).mean().backward()
        for name, p in ccap.named_parameters():
            assert p.grad is not None and p.grad.abs().sum() > 0, name


# ---------------------------------------------------------------------------
# SynthesizerTrn 配線
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSynthesizerBackwardCompat:
    def test_none_keeps_state_dict_keys(self):
        legacy = _build_synthesizer()
        explicit = _build_synthesizer(reference_conditioning="none")
        assert list(explicit.state_dict()) == list(legacy.state_dict())
        assert not hasattr(explicit, "reference_encoder")
        assert not hasattr(explicit, "capacity_control")

    def test_none_matches_legacy_output(self):
        """同じ seed で構築した旧構成と none 明示は重みも infer 出力も bit 一致。"""
        legacy = _build_synthesizer()
        explicit = _build_synthesizer(reference_conditioning="none")
        for (k, a), (_, b) in zip(
            legacy.state_dict().items(), explicit.state_dict().items(), strict=True
        ):
            assert torch.equal(a, b), k
        assert torch.equal(_infer(legacy).audio, _infer(explicit).audio)

    def test_new_modules_do_not_perturb_existing_init(self):
        """新設モジュールは最後に作るので、同じ seed なら既存パラメータの
        初期値は none と bit 一致 (旧 recipe との比較で seed をずらさない)。"""
        legacy = _build_synthesizer()
        for mode in ("ref_spec", "capacity"):
            model = _build_synthesizer(reference_conditioning=mode)
            state = model.state_dict()
            for k, v in legacy.state_dict().items():
                assert torch.equal(state[k], v), (mode, k)

    def test_legacy_state_dict_loads_strictly_into_none(self):
        legacy = _build_synthesizer(seed=1)
        model = _build_synthesizer(seed=2, reference_conditioning="none")
        model.load_state_dict(legacy.state_dict(), strict=True)
        assert torch.equal(_infer(legacy).audio, _infer(model).audio)

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="reference_conditioning"):
            _build_synthesizer(reference_conditioning="mel")

    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_requires_multi_speaker_model(self, mode):
        """spk_proj がない単一話者モデルでは足し先がないため明示エラー。"""
        with pytest.raises(ValueError, match="spk_proj"):
            _build_synthesizer(n_speakers=1, reference_conditioning=mode)


# 変更前 commit 04ea2380 (参照条件付け導入前) の infer 出力 golden。
# 生成手順: ``git worktree add <scratch> 04ea2380`` した旧コードを sys.path 先頭に
# 置き、``_build_synthesizer()`` (seed 1234) と ``_infer`` と同じ入力 (text seed 4、
# emb seed 3、lid 全 0、infer 直前 seed 11) で ``infer`` を実行した値。
# 生成環境 (Windows 11, torch 2.11.0+cu128, CPU) では旧コードと本変更後の
# コードで音声 bytes が bit 一致した (sha256 61765d146a71fe7e…2277fd9d)。
# ただし CPU の fp32 演算は ISA / BLAS 実装で縮約順序が変わり bit 再現は
# プラットフォーム間で保証されないため、hash ではなく値で比較する。
_GOLDEN_SHAPE = (2, 1, 3328)
_GOLDEN_Y_LENGTHS = [13, 13]
_GOLDEN_SUM = 62.31959165678336
_GOLDEN_ABS_SUM = 420.4944654734186
_GOLDEN_SQ_SUM = 42.27266740710808
# audio[b, 0, 100:108] (b = 0, 1)
_GOLDEN_SAMPLES_100_108 = [
    [
        -0.07412818819284439,
        -0.03989451751112938,
        0.033815648406744,
        0.037872906774282455,
        0.05449952557682991,
        -0.050742194056510925,
        -0.022165365517139435,
        0.02704748511314392,
    ],
    [
        -0.09182760864496231,
        -0.011942571960389614,
        0.016872482374310493,
        0.04263908416032791,
        0.05760480836033821,
        -0.02202727273106575,
        -0.021223029121756554,
        0.009205429814755917,
    ],
]
# 許容誤差: 同じ fp32 graph のプラットフォーム差は演算ごとに相対 ~1e-6、
# 数十層を経ても |audio| <= 0.3 に対し絶対 1e-5 程度。既定経路の退行
# (初期化順・RNG 消費・条件付けの変化) は出力全体が別物になり O(1e-2) 以上
# ずれる (golden 作成時に 1 行の lid を 0→1 にしただけで総和が 10% 動いた)
# ので、標本は atol 1e-4、総和 (6656 標本) は rtol 1e-4 で十分に分離する。
_GOLDEN_SAMPLE_ATOL = 1e-4
_GOLDEN_SUM_RTOL = 1e-4


@pytest.mark.unit
class TestPreChangeGolden:
    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param({}, id="implicit"),
            pytest.param({"reference_conditioning": "none"}, id="none"),
        ],
    )
    def test_none_infer_matches_pre_change_golden(self, overrides):
        """既定 / none の infer 出力が変更前 commit の golden と一致する。"""
        model = _build_synthesizer(**overrides)
        out = _infer(model)
        audio = out.audio.double()
        assert tuple(out.audio.shape) == _GOLDEN_SHAPE
        assert out.y_mask.sum(dim=(1, 2)).long().tolist() == _GOLDEN_Y_LENGTHS
        torch.testing.assert_close(
            out.audio[:, 0, 100:108],
            torch.tensor(_GOLDEN_SAMPLES_100_108),
            atol=_GOLDEN_SAMPLE_ATOL,
            rtol=0,
        )
        for value, golden in (
            (audio.sum(), _GOLDEN_SUM),
            (audio.abs().sum(), _GOLDEN_ABS_SUM),
            ((audio * audio).sum(), _GOLDEN_SQ_SUM),
        ):
            assert float(value) == pytest.approx(golden, rel=_GOLDEN_SUM_RTOL)


@pytest.mark.unit
class TestSynthesizerZeroInit:
    def test_zero_init_ref_spec_matches_legacy_output(self):
        legacy = _build_synthesizer()
        model = _build_synthesizer(reference_conditioning="ref_spec")
        _load_legacy_weights(model, legacy)
        ref = _linear_spec(2, 30, seed=13)
        ref_len = torch.tensor([30, 18])
        assert torch.equal(_infer(model, ref, ref_len).audio, _infer(legacy).audio)

    def test_zero_init_capacity_matches_legacy_output(self):
        legacy = _build_synthesizer()
        model = _build_synthesizer(reference_conditioning="capacity")
        _load_legacy_weights(model, legacy)
        assert torch.equal(_infer(model).audio, _infer(legacy).audio)

    def test_zero_init_forward_matches_legacy(self):
        """学習 forward (MAS・slice を含む) も初期状態は旧モデルと bit 一致。"""
        legacy = _build_synthesizer()
        model = _build_synthesizer(reference_conditioning="ref_spec")
        _load_legacy_weights(model, legacy)
        x, x_len = _text(2)
        y = _linear_spec(2, 40, seed=14)
        y_len = torch.tensor([40, 33])
        emb = _speaker_embeddings(2)
        lid = torch.tensor([0, 1])
        ref = _linear_spec(2, 25, seed=15)
        ref_len = torch.tensor([25, 11])
        with torch.no_grad():
            torch.manual_seed(5)
            out_legacy = legacy(x, x_len, y, y_len, lid=lid, speaker_embeddings=emb)
            torch.manual_seed(5)
            out_ref = model(
                x,
                x_len,
                y,
                y_len,
                lid=lid,
                speaker_embeddings=emb,
                reference_spec=ref,
                reference_spec_lengths=ref_len,
            )
        assert torch.equal(out_ref.waveform, out_legacy.waveform)
        assert torch.equal(out_ref.ids_slice, out_legacy.ids_slice)

    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_spk_proj_gradient_unchanged_at_init(self, mode):
        """zero-init の加算は spk_proj への勾配を変えない (bit 一致)。"""
        legacy = _build_synthesizer()
        model = _build_synthesizer(reference_conditioning=mode)
        _load_legacy_weights(model, legacy)
        emb = _speaker_embeddings(2)
        lid = torch.tensor([0, 1])
        z = torch.randn(2, 32, 12, generator=torch.Generator().manual_seed(6))
        kwargs = {}
        if mode == "ref_spec":
            kwargs = {
                "reference_spec": _linear_spec(2, 20, seed=16),
                "reference_spec_lengths": torch.tensor([20, 8]),
            }

        def spk_proj_grads(m, **kw):
            m.zero_grad()
            g = m._get_global_conditioning(None, lid, speaker_embeddings=emb, **kw)
            o, _ = m.dec(z, g=g)
            o.pow(2).mean().backward()
            return [p.grad.clone() for p in m.spk_proj.parameters()]

        for a, b in zip(
            spk_proj_grads(legacy), spk_proj_grads(model, **kwargs), strict=True
        ):
            assert torch.equal(a, b)


@pytest.mark.unit
class TestSynthesizerReferencePath:
    def _trained_like(self, mode="ref_spec"):
        model = _build_synthesizer(reference_conditioning=mode)
        _randomize_output(
            model.reference_encoder if mode == "ref_spec" else model.capacity_control
        )
        return model

    def test_ref_spec_adds_to_speaker_component_only(self):
        """g_spk = spk_proj(e) + reference_encoder(spec)、g_lang は不変。"""
        model = self._trained_like()
        emb = _speaker_embeddings(2)
        lid = torch.tensor([0, 1])
        ref = _linear_spec(2, 20, seed=17)
        ref_len = torch.tensor([20, 9])
        with torch.no_grad():
            g, g_spk, g_lang = model._get_global_conditioning(
                None,
                lid,
                speaker_embeddings=emb,
                return_components=True,
                reference_spec=ref,
                reference_spec_lengths=ref_len,
            )
            expected_spk = model.spk_proj(emb).unsqueeze(-1) + model.reference_encoder(
                ref, ref_len
            )
            expected_lang = model.emb_lang(lid).unsqueeze(-1)
        torch.testing.assert_close(g_spk, expected_spk, atol=0, rtol=0)
        torch.testing.assert_close(g_lang, expected_lang, atol=0, rtol=0)
        torch.testing.assert_close(g, expected_spk + expected_lang, atol=0, rtol=0)

    def test_capacity_adds_mlp_of_embedding(self):
        model = self._trained_like("capacity")
        emb = _speaker_embeddings(2)
        with torch.no_grad():
            g_spk = model._get_speaker_condition(emb)
            expected = model.spk_proj(emb).unsqueeze(-1) + model.capacity_control(emb)
        torch.testing.assert_close(g_spk, expected, atol=0, rtol=0)

    def test_reference_changes_infer_output(self):
        """学習後相当 (非ゼロ最終層) では参照の違いが infer 出力に届く。"""
        model = self._trained_like()
        ref_len = torch.tensor([20, 20])
        a = _infer(model, _linear_spec(2, 20, seed=18), ref_len)
        b = _infer(model, _linear_spec(2, 20, seed=19), ref_len)
        n = min(a.audio.shape[-1], b.audio.shape[-1])
        assert (a.audio[..., :n] - b.audio[..., :n]).abs().max() > 1e-4

    def test_reference_changes_forward_output(self):
        model = self._trained_like()
        x, x_len = _text(1)
        y = _linear_spec(1, 40, seed=20)
        y_len = torch.tensor([40])
        emb = _speaker_embeddings(1)
        ref_len = torch.tensor([20])
        outs = []
        for seed in (21, 22):
            torch.manual_seed(7)
            with torch.no_grad():
                outs.append(
                    model(
                        x,
                        x_len,
                        y,
                        y_len,
                        speaker_embeddings=emb,
                        reference_spec=_linear_spec(1, 20, seed=seed),
                        reference_spec_lengths=ref_len,
                    ).waveform
                )
        assert (outs[0] - outs[1]).abs().max() > 1e-5

    def test_infer_padding_does_not_change_audio(self):
        """モデル経由でも参照の末尾 padding は出力を変えない。"""
        model = self._trained_like()
        ref = _linear_spec(2, 20, seed=23)
        ref_len = torch.tensor([20, 14])
        padded = torch.cat([ref, torch.full((2, SPEC_CHANNELS, 30), 7.0)], dim=-1)
        a = _infer(model, ref, ref_len).audio
        b = _infer(model, padded, ref_len).audio
        assert a.shape == b.shape
        # g の差は MASK_ATOL 程度。decoder を通しても O(1e-4) を超えない
        # (漏れがあれば g が O(1e-1) 動き出力は O(1e-2) 以上変わる)。
        torch.testing.assert_close(a, b, atol=1e-4, rtol=0)

    def test_scl_and_swap_helpers_accept_reference(self):
        """SCL re-forward / swap-SCL も同じ参照を通せる (Task 7R の配線先)。"""
        model = self._trained_like()
        x, x_len = _text(1)
        y = _linear_spec(1, 40, seed=24)
        y_len = torch.tensor([40])
        emb = _speaker_embeddings(1)
        ref = _linear_spec(1, 20, seed=25)
        ref_len = torch.tensor([20])
        kw = {"reference_spec": ref, "reference_spec_lengths": ref_len}
        with torch.no_grad():
            out = model(x, x_len, y, y_len, speaker_embeddings=emb, **kw)
            z, z_p = out.latents[0], out.latents[1]
            a = model.scl_waveform_detached_z(
                z, out.ids_slice, speaker_embeddings=emb, **kw
            )
            b = model.swap_scl_waveform(
                z_p, out.y_mask, out.ids_slice, speaker_embeddings=emb, **kw
            )
        assert a.shape == out.waveform.shape
        assert b.shape == out.waveform.shape
        with pytest.raises(ValueError, match="reference_spec"):
            model.scl_waveform_detached_z(z, out.ids_slice, speaker_embeddings=emb)


@pytest.mark.unit
class TestSynthesizerReferenceErrors:
    def test_missing_reference_spec_raises(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        with pytest.raises(ValueError, match="reference_spec"):
            _infer(model)
        with pytest.raises(ValueError, match="reference_spec"):
            _infer(model, ref=None, ref_len=torch.tensor([10, 10]))

    def test_missing_reference_lengths_raises(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        with pytest.raises(ValueError, match="reference_spec_lengths"):
            _infer(model, ref=_linear_spec(2, 10), ref_len=None)

    def test_missing_speaker_embeddings_raises_for_ref_spec(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        with pytest.raises(ValueError, match="speaker_embeddings"):
            model._get_speaker_condition(
                None,
                reference_spec=_linear_spec(1, 10),
                reference_spec_lengths=torch.tensor([10]),
            )

    def test_reference_spec_on_legacy_model_raises(self):
        """none (旧モデル) に参照を渡したら黙って捨てずに明示エラー。"""
        model = _build_synthesizer()
        with pytest.raises(ValueError, match="reference_conditioning"):
            _infer(model, _linear_spec(2, 10), torch.tensor([10, 10]))
        with pytest.raises(ValueError, match="reference_conditioning"):
            _infer(model, None, torch.tensor([10, 10]))

    def test_reference_spec_on_capacity_model_raises(self):
        """capacity は spec を使わない。渡されたら黙って捨てずに明示エラー。"""
        model = _build_synthesizer(reference_conditioning="capacity")
        with pytest.raises(ValueError, match="reference_conditioning"):
            _infer(model, _linear_spec(2, 10), torch.tensor([10, 10]))

    def test_reference_batch_mismatch_raises(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        with pytest.raises(ValueError, match="batch"):
            _infer(model, _linear_spec(3, 10), torch.tensor([10, 10, 10]))

    def test_reference_zero_length_raises_through_model(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        with pytest.raises(ValueError, match="length"):
            _infer(model, _linear_spec(2, 10), torch.tensor([10, 0]))

    def test_reference_channel_mismatch_raises_through_model(self):
        model = _build_synthesizer(reference_conditioning="ref_spec")
        with pytest.raises(ValueError, match="channels"):
            _infer(model, torch.rand(2, 80, 10) + 0.1, torch.tensor([10, 10]))

    def test_custom_reference_spec_channels(self):
        model = _build_synthesizer(
            reference_conditioning="ref_spec", reference_spec_channels=257
        )
        _randomize_output(model.reference_encoder)
        out = _infer(model, torch.rand(2, 257, 10) + 0.1, torch.tensor([10, 6]))
        assert torch.isfinite(out.audio).all()


# ---------------------------------------------------------------------------
# telemetry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTelemetry:
    def test_telemetry_includes_reference_term(self):
        from piper_train.vits.telemetry import collect_modulation_telemetry

        model = _build_synthesizer(reference_conditioning="ref_spec")
        _randomize_output(model.reference_encoder)
        emb = _speaker_embeddings(2)
        lid = torch.tensor([0, 1])
        ref = _linear_spec(2, 20, seed=26)
        ref_len = torch.tensor([20, 12])
        metrics = collect_modulation_telemetry(
            model,
            emb,
            lid=lid,
            reference_spec=ref,
            reference_spec_lengths=ref_len,
        )
        with torch.no_grad():
            g_spk = model._get_speaker_condition(emb, ref, ref_len)
        expected = float(g_spk.squeeze(-1).float().norm(dim=-1).mean())
        assert metrics["telemetry/g_spk_norm"] == pytest.approx(expected, rel=1e-6)

    def test_telemetry_default_unchanged_for_legacy(self):
        from piper_train.vits.telemetry import collect_modulation_telemetry

        model = _build_synthesizer()
        emb = _speaker_embeddings(2)
        metrics = collect_modulation_telemetry(model, emb, lid=torch.tensor([0, 1]))
        with torch.no_grad():
            expected = float(model.spk_proj(emb).float().norm(dim=-1).mean())
        assert metrics["telemetry/g_spk_norm"] == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# CLI / lightning 配線
# ---------------------------------------------------------------------------


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": 2,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 4,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


@pytest.mark.unit
class TestCliAndLightningWiring:
    def test_cli_default_is_none(self):
        assert _parse_train_args().reference_conditioning == "none"

    @pytest.mark.parametrize("mode", ["none", "ref_spec", "capacity"])
    def test_cli_accepts_modes(self, mode):
        args = _parse_train_args(("--reference-conditioning", mode))
        assert args.reference_conditioning == mode

    def test_cli_rejects_unknown_mode(self):
        with pytest.raises(SystemExit):
            _parse_train_args(("--reference-conditioning", "mel"))

    def test_lightning_default_has_no_reference_modules(self):
        model = _vits_model()
        assert model.hparams.reference_conditioning == "none"
        assert model.model_g.reference_conditioning == "none"
        assert not hasattr(model.model_g, "reference_encoder")
        assert not hasattr(model.model_g, "capacity_control")

    def test_lightning_ref_spec_reaches_model(self):
        """hparam → SynthesizerTrn の統合点 pin (resume / export は hparams
        から VitsModel を再構築する)。spec の周波数 bin は filter_length 由来。"""
        model = _vits_model(reference_conditioning="ref_spec")
        assert model.hparams.reference_conditioning == "ref_spec"
        enc = model.model_g.reference_encoder
        assert enc.spec_channels == model.hparams.filter_length // 2 + 1

    def test_lightning_capacity_reaches_model(self):
        model = _vits_model(reference_conditioning="capacity")
        assert hasattr(model.model_g, "capacity_control")
        assert not hasattr(model.model_g, "reference_encoder")

    def test_dino_teacher_stays_spk_proj_copy(self):
        """DINO の teacher/student は spk_proj 同士の比較のまま (参照項は
        DINO の対象外 = 新経路に追加損失を足さない)。"""
        model = _vits_model(reference_conditioning="ref_spec")
        teacher_keys = set(model.spk_proj_teacher.state_dict())
        assert teacher_keys == set(model.model_g.spk_proj.state_dict())

    def test_checkpoint_round_trip_restores_mode(self, tmp_path):
        try:
            from piper_train.vits.lightning import VitsModel
        except ImportError as e:  # pragma: no cover
            pytest.skip(f"Training dependencies not available: {e}")
        model = _vits_model(reference_conditioning="capacity")
        path = tmp_path / "m.ckpt"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "hyper_parameters": dict(model.hparams),
                "pytorch-lightning_version": "2.0.0",
            },
            path,
        )
        restored = VitsModel.load_from_checkpoint(str(path), dataset=None)
        assert restored.hparams.reference_conditioning == "capacity"
        for k, v in model.model_g.capacity_control.state_dict().items():
            assert torch.equal(restored.model_g.capacity_control.state_dict()[k], v)

    @pytest.mark.parametrize(
        ("mode", "submodule"),
        [
            ("none", None),
            ("ref_spec", "reference_encoder"),
            ("capacity", "capacity_control"),
        ],
    )
    def test_cli_args_build_model_end_to_end(self, mode, submodule):
        """CLI → ``dict_args = vars(args)`` → ``VitsModel(**dict_args)``
        (``__main__.main`` と同じ受け渡し) で flag がモデルまで届く。"""
        try:
            from piper_train.vits.lightning import VitsModel
        except ImportError as e:  # pragma: no cover
            pytest.skip(f"Training dependencies not available: {e}")
        args = _parse_train_args(("--no-wavlm", "--reference-conditioning", mode))
        dict_args = vars(args)
        # main() と同じ写像 (--no-wavlm と MB-iSTFT の固定 upsample 構造)
        dict_args["use_wavlm_discriminator"] = False
        dict_args["upsample_rates"] = (4, 4)
        dict_args["upsample_kernel_sizes"] = (16, 16)
        torch.manual_seed(0)
        model = VitsModel(
            num_symbols=97,
            num_speakers=2,
            num_languages=2,
            sample_rate=22050,
            dataset=None,
            **dict_args,
        )
        assert model.hparams.reference_conditioning == mode
        assert model.model_g.reference_conditioning == mode
        present = {
            name
            for name in ("reference_encoder", "capacity_control")
            if hasattr(model.model_g, name)
        }
        assert present == ({submodule} if submodule else set())

    def test_cli_choices_match_model_modes(self):
        from piper_train.__main__ import create_parser
        from piper_train.vits.models import REFERENCE_CONDITIONING_MODES

        action = next(
            a for a in create_parser()._actions if a.dest == "reference_conditioning"
        )
        assert tuple(action.choices) == REFERENCE_CONDITIONING_MODES

    def test_old_hparams_without_key_default_to_none(self):
        """旧 ckpt の hparams (キーなし) からの再構築は none = 旧挙動。"""
        model = _vits_model()
        old = {k: v for k, v in model.hparams.items() if k != "reference_conditioning"}
        old.pop("num_symbols")
        old.pop("num_speakers")
        old.pop("num_languages")
        rebuilt = _vits_model(**old)
        assert rebuilt.model_g.reference_conditioning == "none"
        assert list(rebuilt.model_g.state_dict()) == list(model.model_g.state_dict())
