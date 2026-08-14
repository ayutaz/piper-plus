"""TDD red — v10 学習信号 (S1 swap-SCL / SupCon 改良 / σ / LF / DINO) の契約テスト。

zero-shot v10 設計 (docs/design/zero-shot-v10-design.md §3) の学習信号系
5 要素の契約を実装に先行して固定する。red phase のため実装が存在せず
テストは失敗してよい (収集は必ず成功すること)。

実装者向け契約 (本テストが pin する API — 実装先は piper_train.vits.losses):

1. S1 swap-SCL (§3.1、ASCL 型):
   - ``build_same_language_permutation(batch_size, language_ids=None,
     speaker_ids=None, generator=None) -> (perm, valid_mask)``
     同一言語グループ内 roll (cyclic shift、shift ∈ [1, n-1]) で swap ペア
     permutation を作る純関数。
     * perm: LongTensor [B]。全体として arange(B) の permutation
     * 各行 i (valid) について language_ids[perm[i]] == language_ids[i] かつ
       perm[i] != i
     * 言語内 1 行のみ (singleton) の行は perm[i] == i / valid_mask[i] == False
       (損失から除外するための mask)
     * language_ids=None は全体を 1 グループ扱い (None のとき B を推定する
       材料が他にないため batch_size を第一引数に取る)
     * speaker_ids 指定時は同一話者ペアも valid=False (異話者 derangement)。
       同一話者 swap は z_p の中身の話者 = 目標話者となり swap-SCL の
       Goodhart 耐性 (§3.1) が崩れるため。None は従来挙動と bit 互換
     * generator (torch.Generator) 指定で決定論
   - ``swap_spk_ramp_weight(current_epoch, start_epoch, ramp_epochs) -> float``
     epoch < start → 0.0 / ramp 中 → (epoch - start) / ramp_epochs /
     start + ramp 以降 → 1.0。ramp_epochs=0 は step 関数 (start 以降 1.0)。
   - ``SynthesizerTrn.swap_scl_waveform(z_p, y_mask, ids_slice,
     speaker_embeddings=None, sid=None, lid=None) -> waveform [B, 1, seg]``
     z_p (forward の latents[1]) は **method 内部で detach** すること
     (ASCL の stop-gradient を lightning 側の detach に依存させない契約)。
     flow(z_p, y_mask, g=g_q, reverse=True) → ids_slice で slice →
     dec(z_swap_slice, g=g_q)。勾配は flow / dec / spk_proj に届き、
     enc_q (posterior) / enc_p には届かない。
   - CLI: ``--c-swap-spk`` (default 0.0) / ``--swap-spk-start-epoch`` (10) /
     ``--swap-spk-ramp-epochs`` (5)

2. SupCon 改良 (§3.2):
   - ``gather_speaker_loss_inputs(gen_embedding, ref_embedding,
     speaker_ids=None) -> (gen, ref, speaker_ids)``
     torch.distributed.nn.all_gather (勾配が通る方。素の
     torch.distributed.all_gather は勾配を切る既知 footgun) で全 rank 結合。
     dist 未初期化 / world_size == 1 なら no-op (入力そのまま返す)。
   - CLI: ``--spk-loss-gather`` (default off) /
     ``--spk-loss-temperature`` (default 0.07、v10 recipe は 0.1 を指定)
   - training_step_g の speaker_infonce_loss 呼び出しに hparams 経由で
     temperature が配線されること (source 検査で pin)

3. σ default 変更 (設計 doc F7): ``--spk-emb-noise-sigma`` default
   0.05 → 0.0。lightning の getattr fallback も 0.0。
   (v9 スクリプトは σ を明示指定しているため再現性は保たれる)

4. Latent Filling (§3.3、arXiv:2310.03538):
   - ``is_latent_filling_step(global_step, tau) -> bool``
     global_step を seed にした torch.Generator による決定論的判定
     (同 step 同結果 = 全 rank 一致、DDP divergence 防止)。tau=0 で常に False。
   - ``should_run_latent_filling_step(global_step, tau, d_update_interval=1)
     -> bool``  上記に「G 更新が走る step のみ」の gate を重ねた最終判定。
     D-only step (global_step % d_update_interval != 0) で LF が発動すると
     optimizer.step() ゼロ → global_step 凍結 → 全 batch が同一分岐の
     no-op を永久に取る決定論的ラッチになるため (lightning の LF gate は
     この関数を使い d_update_interval を配線すること — source 検査で pin)。
   - ``sample_latent_filling_lambda(n, generator=None) -> Tensor [n]``
     λ ~ Beta(0.5, 0.5) (arcsine 分布、U 字型)。
   - ``build_latent_filling_embeddings(speaker_embeddings, language_ids=None,
     speaker_ids=None, generator=None) -> s̃``  同一言語 (speaker_ids 指定時
     は異話者) 2 話者の λ 補間 (確率 0.5) or s + N(0, 1e-4) (確率 0.5)。
     ペアは perm ヘルパー流用。補間行は L2 再正規化 (unit-norm 不変条件)。
   - CLI: ``--latent-filling-tau`` (default 0.0 = 完全無効 = 既存挙動)

5. DINO 警告 (設計 doc F8): c_dino > 0 の VitsModel 構築 (学習セットアップ)
   時に 1 回だけ WARNING log (frozen CAM++/同一入力では慣性項に退化済み、
   v10 は c_dino=0 推奨)。
"""

from __future__ import annotations

import logging
import re

import pytest


torch = pytest.importorskip("torch")

from torch.nn import functional as F  # noqa: E402

from piper_train.vits.losses import speaker_infonce_loss  # noqa: E402


_CLI_BASE = ["--dataset-dir", "/tmp/x", "--batch-size", "1"]


def _losses_attr(name: str):
    """未実装関数の lazy 取得 (収集時 crash を避け、実行時に fail させる)。"""
    from piper_train.vits import losses

    fn = getattr(losses, name, None)
    if fn is None:
        pytest.fail(
            f"piper_train.vits.losses.{name} が未実装 "
            "(v10 学習信号 TDD red — 本ファイル docstring の契約参照)"
        )
    return fn


def _parse_cli(extra=()):
    from piper_train.__main__ import create_parser

    return create_parser().parse_args([*_CLI_BASE, *extra])


def _grad_sum(module) -> float:
    return sum(
        float(p.grad.abs().sum()) for p in module.parameters() if p.grad is not None
    )


def _tiny_synthesizer():
    """勾配検証用の最小 SynthesizerTrn (test_scl_differentiable と同構成)。"""
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:  # pragma: no cover - env without training deps
        pytest.skip(f"Training dependencies not available: {e}")

    return SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=32,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=1,
        kernel_size=3,
        p_dropout=0.0,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=64,
        upsample_kernel_sizes=(16, 16),
        n_speakers=4,
        gin_channels=64,
        use_sdp=True,
        prosody_dim=16,
    )


def _run_tiny_forward(model, b=2):
    torch.manual_seed(0)
    t_text, t_frames = 20, 48
    x = torch.randint(1, 50, (b, t_text))
    x_lengths = torch.full((b,), t_text)
    y = torch.randn(b, 513, t_frames)
    y_lengths = torch.full((b,), t_frames)
    emb = F.normalize(torch.randn(b, 192), dim=-1)
    out = model(x, x_lengths, y, y_lengths, speaker_embeddings=emb)
    return out, emb


# ===========================================================================
# 1. S1 swap-SCL
# ===========================================================================


@pytest.mark.unit
class TestBuildSameLanguagePermutation:
    """同一言語 roll permutation 純関数の契約。"""

    def test_same_language_and_no_self_mapping(self):
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 0, 1, 1, 2, 2, 2])
        g = torch.Generator().manual_seed(0)
        perm, valid = fn(8, language_ids=lang, generator=g)
        assert perm.shape == (8,)
        assert valid.shape == (8,)
        assert valid.dtype == torch.bool
        # 全言語 2 行以上 → 全行 valid
        assert bool(valid.all())
        for i in range(8):
            assert int(lang[perm[i]]) == int(lang[i]), (
                f"row {i}: 言語グループを跨ぐ swap は禁止 (cross-lingual swap は "
                "VC として高難度、design doc §3.1 ガード (a))"
            )
            assert int(perm[i]) != i, f"row {i}: perm[i] == i (swap になっていない)"

    def test_perm_is_full_permutation(self):
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 1, 1, 1, 2])
        g = torch.Generator().manual_seed(3)
        perm, _valid = fn(6, language_ids=lang, generator=g)
        assert torch.equal(torch.sort(perm).values, torch.arange(6))

    def test_singleton_language_row_masked_out(self):
        """言語内 1 行のみの行は valid_mask=False (損失から除外) + perm[i]==i。"""
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 1])
        g = torch.Generator().manual_seed(0)
        perm, valid = fn(3, language_ids=lang, generator=g)
        assert not bool(valid[2])
        assert int(perm[2]) == 2
        # サイズ 2 のグループは互いに swap するしかない
        assert bool(valid[0]) and bool(valid[1])
        assert int(perm[0]) == 1
        assert int(perm[1]) == 0

    def test_none_language_ids_is_single_group(self):
        """language_ids=None は全体 1 グループ (monolingual 学習)。"""
        fn = _losses_attr("build_same_language_permutation")
        g = torch.Generator().manual_seed(0)
        perm, valid = fn(4, language_ids=None, generator=g)
        assert bool(valid.all())
        for i in range(4):
            assert int(perm[i]) != i
        assert torch.equal(torch.sort(perm).values, torch.arange(4))

    def test_group_roll_structure(self):
        """グループ内は cyclic shift (roll)。shift はグループごとに一定で 0 以外。"""
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 0, 0, 0, 1, 1, 1])
        g = torch.Generator().manual_seed(7)
        perm, valid = fn(8, language_ids=lang, generator=g)
        assert bool(valid.all())
        # グループが連続 index なので roll は (perm[i] - i) % n が一定
        shifts_a = {(int(perm[i]) - i) % 5 for i in range(5)}
        assert len(shifts_a) == 1 and shifts_a != {0}
        shifts_b = {(int(perm[i]) - i) % 3 for i in range(5, 8)}
        assert len(shifts_b) == 1 and shifts_b != {0}

    def test_deterministic_with_seeded_generator(self):
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 0, 0, 1, 1, 1, 1])
        perm1, valid1 = fn(
            8, language_ids=lang, generator=torch.Generator().manual_seed(42)
        )
        perm2, valid2 = fn(
            8, language_ids=lang, generator=torch.Generator().manual_seed(42)
        )
        assert torch.equal(perm1, perm2)
        assert torch.equal(valid1, valid2)

    # -- speaker_ids (異話者 derangement、レビュー findings 対応) --

    def test_speaker_ids_exclude_same_speaker_pairs(self):
        """speaker_ids 指定時: valid 行の swap 相手は同一言語かつ **異話者**。

        speaker_ids を見ない perm は「別の行」しか保証せず、
        samples_per_speaker>1 の batch では swap 相手が同一話者になり得た
        (z_p の中身の話者 = 目標話者 → swap-SCL が通常 SCL に退化、
        design doc §3.1 の Goodhart 耐性の崩壊)。
        """
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 0, 0, 1, 1, 1, 1])
        spk = torch.tensor([7, 7, 8, 8, 1, 2, 1, 2])
        for seed in range(50):
            g = torch.Generator().manual_seed(seed)
            perm, valid = fn(8, language_ids=lang, speaker_ids=spk, generator=g)
            assert torch.equal(torch.sort(perm).values, torch.arange(8))
            assert bool(valid.all()), f"seed={seed}: 2 話者×2 発話なら全行 valid"
            for i in range(8):
                assert int(lang[perm[i]]) == int(lang[i]), (
                    f"seed={seed} row {i}: 言語グループを跨いだ"
                )
                assert int(spk[perm[i]]) != int(spk[i]), (
                    f"seed={seed} row {i}: 同一話者ペアが valid になっている"
                )
                assert int(perm[i]) != i

    def test_single_speaker_language_group_is_all_invalid(self):
        """言語グループ内が 1 話者のみ → 全行 valid=False + perm identity。

        language-balanced sampling + samples_per_speaker=4 で言語グループが
        1 話者の 4 発話だけになる典型 batch (findings の実測シナリオ:
        1000/1000 seed で同一話者ペアが valid だった) の修正を固定する。
        """
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 0, 0, 1, 1, 1, 1])
        spk = torch.tensor([7, 7, 7, 7, 1, 2, 1, 2])
        for seed in range(50):
            g = torch.Generator().manual_seed(seed)
            perm, valid = fn(8, language_ids=lang, speaker_ids=spk, generator=g)
            assert not bool(valid[:4].any()), (
                f"seed={seed}: 1 話者のみの言語グループが valid (退化 swap)"
            )
            assert torch.equal(perm[:4], torch.arange(4)), (
                f"seed={seed}: 1 話者グループの perm は identity のはず"
            )
            assert bool(valid[4:].all())
            for i in range(4, 8):
                assert int(spk[perm[i]]) != int(spk[i])

    def test_majority_speaker_marks_minimum_rows_invalid(self):
        """最大話者ブロック m > n/2 では同一話者ペアは理論最小 (2m-n 行)
        だけ発生し、それらのみ valid=False (perm は permutation を維持)。"""
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.zeros(4, dtype=torch.long)
        spk = torch.tensor([7, 7, 7, 8])  # m=3, n=4 → 同一話者ペア最小 2 行
        for seed in range(50):
            g = torch.Generator().manual_seed(seed)
            perm, valid = fn(4, language_ids=lang, speaker_ids=spk, generator=g)
            assert torch.equal(torch.sort(perm).values, torch.arange(4))
            assert int(valid.sum()) == 2, (
                f"seed={seed}: valid 行数 {int(valid.sum())} != 理論最大 2 (n - (2m-n))"
            )
            for i in range(4):
                if bool(valid[i]):
                    assert int(spk[perm[i]]) != int(spk[i])
            assert bool(valid[3]), "少数話者 (speaker 8) の行は常にペア可能"

    def test_speaker_ids_deterministic_and_none_is_legacy(self):
        fn = _losses_attr("build_same_language_permutation")
        lang = torch.tensor([0, 0, 0, 0, 1, 1, 1, 1])
        spk = torch.tensor([7, 7, 8, 8, 1, 2, 1, 2])
        p1, v1 = fn(
            8,
            language_ids=lang,
            speaker_ids=spk,
            generator=torch.Generator().manual_seed(42),
        )
        p2, v2 = fn(
            8,
            language_ids=lang,
            speaker_ids=spk,
            generator=torch.Generator().manual_seed(42),
        )
        assert torch.equal(p1, p2)
        assert torch.equal(v1, v2)
        # speaker_ids=None は従来 (cyclic shift) と bit 互換
        p_legacy, v_legacy = fn(
            8, language_ids=lang, generator=torch.Generator().manual_seed(42)
        )
        p_none, v_none = fn(
            8,
            language_ids=lang,
            speaker_ids=None,
            generator=torch.Generator().manual_seed(42),
        )
        assert torch.equal(p_legacy, p_none)
        assert torch.equal(v_legacy, v_none)


@pytest.mark.unit
class TestSwapSpkRampWeight:
    """weight = c_swap_spk * ramp の ramp 部分 (start から ramp_epochs で 0→1)。"""

    def test_before_start_is_zero(self):
        fn = _losses_attr("swap_spk_ramp_weight")
        assert float(fn(0, 10, 5)) == pytest.approx(0.0)
        assert float(fn(9, 10, 5)) == pytest.approx(0.0)

    def test_linear_during_ramp(self):
        fn = _losses_attr("swap_spk_ramp_weight")
        assert float(fn(10, 10, 5)) == pytest.approx(0.0)
        assert float(fn(11, 10, 5)) == pytest.approx(0.2)
        assert float(fn(12, 10, 5)) == pytest.approx(0.4)
        assert float(fn(14, 10, 5)) == pytest.approx(0.8)

    def test_after_ramp_is_one(self):
        fn = _losses_attr("swap_spk_ramp_weight")
        assert float(fn(15, 10, 5)) == pytest.approx(1.0)
        assert float(fn(100, 10, 5)) == pytest.approx(1.0)

    def test_zero_ramp_epochs_is_step_function(self):
        fn = _losses_attr("swap_spk_ramp_weight")
        assert float(fn(9, 10, 0)) == pytest.approx(0.0)
        assert float(fn(10, 10, 0)) == pytest.approx(1.0)


@pytest.mark.unit
class TestSwapSclCli:
    def test_defaults(self):
        args = _parse_cli()
        assert args.c_swap_spk == pytest.approx(0.0)
        assert args.swap_spk_start_epoch == 10
        assert args.swap_spk_ramp_epochs == 5

    def test_parse_custom_values(self):
        args = _parse_cli(
            [
                "--c-swap-spk",
                "0.5",
                "--swap-spk-start-epoch",
                "3",
                "--swap-spk-ramp-epochs",
                "2",
            ]
        )
        assert args.c_swap_spk == pytest.approx(0.5)
        assert args.swap_spk_start_epoch == 3
        assert args.swap_spk_ramp_epochs == 2


class TestSwapSclWaveform:
    """SynthesizerTrn.swap_scl_waveform の形状 + 勾配隔離 (tiny model)。"""

    def _swap_waveform(self, model, out, emb_q):
        if not hasattr(model, "swap_scl_waveform"):
            pytest.fail(
                "SynthesizerTrn.swap_scl_waveform が未実装 "
                "(S1 swap-SCL — 本ファイル docstring の契約参照)"
            )
        return model.swap_scl_waveform(
            out.latents[1],  # z_p (detach は method 内部で行う契約)
            out.y_mask,
            out.ids_slice,
            speaker_embeddings=emb_q,
        )

    def test_same_shape_as_forward_waveform(self):
        model = _tiny_synthesizer()
        out, emb = _run_tiny_forward(model)
        o_swap = self._swap_waveform(model, out, emb[[1, 0]])
        assert o_swap.shape == out.waveform.shape

    def test_gradients_reach_flow_dec_spk_proj_but_not_enc_q(self):
        """swap 損失の勾配経路 (ASCL stop-gradient 契約):

        flow reverse + dec FiLM + spk_proj (g_q) に話者勾配が届き、
        z_p の detach により enc_q (posterior) / enc_p には流れない。
        """
        model = _tiny_synthesizer()
        out, emb = _run_tiny_forward(model)
        o_swap = self._swap_waveform(model, out, emb[[1, 0]])
        loss = o_swap.pow(2).mean()
        loss.backward()

        assert _grad_sum(model.flow) > 0, (
            "flow に勾配が届いていない — flow reverse 経由で話者勾配を通すのが "
            "swap-SCL の核心 (design doc F2)"
        )
        assert _grad_sum(model.dec) > 0, "decoder に勾配が届いていない"
        assert _grad_sum(model.spk_proj) > 0, "spk_proj に勾配が届いていない (g_q 経由)"
        assert _grad_sum(model.enc_q) == 0, (
            "enc_q (posterior) に勾配が漏れている — z_p の detach が壊れている"
        )
        assert _grad_sum(model.enc_p) == 0, (
            "enc_p に勾配が漏れている — swap 経路は z_p 再利用のみのはず"
        )


# ===========================================================================
# 2. SupCon 改良 (gather + temperature)
# ===========================================================================


@pytest.mark.unit
class TestSupConGather:
    def test_noop_without_dist(self):
        """dist 未初期化なら入力をそのまま返す (world_size==1 no-op)。"""
        fn = _losses_attr("gather_speaker_loss_inputs")
        assert not torch.distributed.is_initialized()
        gen = torch.randn(4, 192)
        ref = torch.randn(4, 192)
        sids = torch.tensor([7, 7, 8, 8])
        out_gen, out_ref, out_sids = fn(gen, ref, sids)
        assert torch.equal(out_gen, gen)
        assert torch.equal(out_ref, ref)
        assert torch.equal(out_sids, sids)

    def test_noop_passes_none_speaker_ids_through(self):
        fn = _losses_attr("gather_speaker_loss_inputs")
        gen = torch.randn(2, 192)
        ref = torch.randn(2, 192)
        _out_gen, _out_ref, out_sids = fn(gen, ref, None)
        assert out_sids is None

    def test_noop_preserves_gradient_flow(self):
        """gather を挟んでも gen 側の勾配が切れないこと。

        (実装が torch.distributed.nn.all_gather を使うべき理由 — 素の
        dist.all_gather は勾配を切る。単一プロセスでは no-op passthrough が
        勾配を保つことを pin する)
        """
        fn = _losses_attr("gather_speaker_loss_inputs")
        gen = torch.randn(4, 192, requires_grad=True)
        ref = torch.randn(4, 192)
        out_gen, _out_ref, _ = fn(gen, ref, None)
        out_gen.sum().backward()
        assert gen.grad is not None
        assert float(gen.grad.abs().sum()) > 0

    def test_cli_spk_loss_gather_default_off(self):
        args = _parse_cli()
        assert args.spk_loss_gather is False
        args = _parse_cli(["--spk-loss-gather"])
        assert args.spk_loss_gather is True

    def test_cli_spk_loss_temperature_default(self):
        args = _parse_cli()
        assert args.spk_loss_temperature == pytest.approx(0.07)
        args = _parse_cli(["--spk-loss-temperature", "0.1"])
        assert args.spk_loss_temperature == pytest.approx(0.1)

    def test_temperature_wired_into_speaker_infonce_call(self):
        """training_step_g の speaker_infonce_loss 呼び出しに
        hparams の spk_loss_temperature が渡ること (source 検査で pin)。"""
        import inspect

        from piper_train.vits import lightning as lightning_mod

        src = inspect.getsource(lightning_mod)
        windows = [
            src[m.end() : m.end() + 500]
            for m in re.finditer(r"speaker_infonce_loss\(", src)
        ]
        assert windows, "speaker_infonce_loss の呼び出しが見つからない"
        assert any(
            "temperature" in w and "spk_loss_temperature" in w for w in windows
        ), (
            "speaker_infonce_loss に temperature=hparams.spk_loss_temperature "
            "が配線されていない (v10 recipe は 0.1 を指定するため CLI からの "
            "配線が必須)"
        )

    def test_infonce_temperature_parameter_changes_loss(self):
        """(既存挙動の sanity pin) temperature が実際に損失値へ効くこと。"""
        g = torch.Generator().manual_seed(0)
        ref = F.normalize(torch.randn(4, 192, generator=g), dim=-1)
        gen = F.normalize(torch.randn(4, 192, generator=g), dim=-1)
        loss_default = speaker_infonce_loss(gen, ref, temperature=0.07)
        loss_hot = speaker_infonce_loss(gen, ref, temperature=0.5)
        assert float(loss_default) != pytest.approx(float(loss_hot), abs=1e-6)


# ===========================================================================
# 3. σ default 変更 (F7)
# ===========================================================================


@pytest.mark.unit
class TestSpkEmbNoiseSigmaDefault:
    def test_cli_default_is_zero(self):
        """--spk-emb-noise-sigma default 0.05 → 0.0 (設計 doc F7:
        文献値 σ=1e-4 の 500 倍で破壊的、Latent Filling に置換)。"""
        args = _parse_cli()
        assert args.spk_emb_noise_sigma == pytest.approx(0.0)

    def test_explicit_sigma_still_parses(self):
        """v9 再現スクリプト (σ 明示指定) の互換を維持。"""
        args = _parse_cli(["--spk-emb-noise-sigma", "0.05"])
        assert args.spk_emb_noise_sigma == pytest.approx(0.05)

    def test_lightning_getattr_fallback_is_zero(self):
        """lightning の getattr fallback も 0.0 (古い hparams からの resume で
        noise が復活しないこと)。"""
        import inspect

        from piper_train.vits import lightning as lightning_mod

        src = inspect.getsource(lightning_mod)
        assert re.search(
            r"getattr\(\s*self\.hparams,\s*['\"]spk_emb_noise_sigma['\"]\s*,"
            r"\s*0(\.0)?\s*\)",
            src,
        ), "spk_emb_noise_sigma の getattr fallback が 0.0 になっていない"
        assert not re.search(r"['\"]spk_emb_noise_sigma['\"]\s*,\s*0\.05", src), (
            "spk_emb_noise_sigma の fallback 0.05 が残っている (F7 違反)"
        )


# ===========================================================================
# 4. Latent Filling
# ===========================================================================


@pytest.mark.unit
class TestLatentFillingCli:
    def test_default_tau_is_zero(self):
        args = _parse_cli()
        assert args.latent_filling_tau == pytest.approx(0.0)

    def test_parse_custom_tau(self):
        args = _parse_cli(["--latent-filling-tau", "0.25"])
        assert args.latent_filling_tau == pytest.approx(0.25)


@pytest.mark.unit
class TestLatentFillingStepGate:
    def test_tau_zero_never_triggers(self):
        """τ=0 で完全無効 = 既存挙動と同一 (default)。"""
        fn = _losses_attr("is_latent_filling_step")
        assert not any(bool(fn(step, 0.0)) for step in range(500))

    def test_tau_one_always_triggers(self):
        fn = _losses_attr("is_latent_filling_step")
        assert all(bool(fn(step, 1.0)) for step in range(100))

    def test_deterministic_per_step(self):
        """同 step 同結果 (global_step seed) — 全 rank 一致が DDP の生命線。"""
        fn = _losses_attr("is_latent_filling_step")
        seq1 = [bool(fn(step, 0.25)) for step in range(300)]
        seq2 = [bool(fn(step, 0.25)) for step in range(300)]
        assert seq1 == seq2

    def test_trigger_frequency_close_to_tau(self):
        fn = _losses_attr("is_latent_filling_step")
        hits = sum(bool(fn(step, 0.25)) for step in range(4000))
        rate = hits / 4000
        assert 0.19 < rate < 0.31, f"LF 発動率 {rate:.3f} が τ=0.25 から乖離"


@pytest.mark.unit
class TestLatentFillingGUpdateGate:
    """LF × d_update_interval>=2 の決定論的ラッチ防止 (レビュー findings)。

    PL manual optimization の global_step は optimizer.step() 回数。D-only
    step (update_generator=False) で LF が発動すると G/D どちらの step も
    走らず global_step が凍結し、G-update 判定と LF 判定 (共に global_step
    の純関数) が以降の全 batch で同一分岐を取る silent no-op ラッチになる。
    should_run_latent_filling_step は LF を G 更新 step に限定して構造的に
    これを排除する。
    """

    def test_d_only_steps_never_trigger_lf(self):
        fn = _losses_attr("should_run_latent_filling_step")
        for dui in (2, 3, 4):
            for step in range(200):
                if step % dui != 0:
                    assert not bool(fn(step, 1.0, dui)), (
                        f"D-only step {step} (d_update_interval={dui}) で LF が"
                        "発動 — optimizer.step() ゼロの no-op ラッチ経路"
                    )

    def test_interval_one_matches_base_gate(self):
        """d_update_interval=1 (CLI default) では従来判定と同一。"""
        fn = _losses_attr("should_run_latent_filling_step")
        base = _losses_attr("is_latent_filling_step")
        for step in range(300):
            assert bool(fn(step, 0.25, 1)) == bool(base(step, 0.25))

    def test_g_update_steps_follow_base_gate(self):
        fn = _losses_attr("should_run_latent_filling_step")
        base = _losses_attr("is_latent_filling_step")
        for step in range(0, 300, 2):
            assert bool(fn(step, 0.25, 2)) == bool(base(step, 0.25))

    def test_no_latch_under_optimizer_step_accounting(self):
        """training_step の optimizer step 会計をシミュレートし、全 batch で
        global_step が必ず前進する (増分 0 のラッチが不在) ことを固定する。

        増分則 (lightning.training_step): LF step = G のみ +1 / 通常 step =
        G+D で +2 / D-only step = D のみ +1。旧実装 (is_latent_filling_step
        を d_update_interval と独立に判定) では dui=2, τ=0.25 で最初の LF
        step 後に global_step が奇数化 → D-only step で LF 判定が当たった
        瞬間に増分 0 の永久ループへ入っていた。
        """
        fn = _losses_attr("should_run_latent_filling_step")
        for dui in (1, 2, 3):
            gs = 0
            for _ in range(2000):
                update_g = gs % dui == 0
                lf = bool(fn(gs, 0.5, dui))
                assert not (lf and not update_g), (
                    f"dui={dui} gs={gs}: G 更新なし step で LF 発動 (ラッチ)"
                )
                if lf:
                    gs += 1  # G のみ (LF は D 更新 skip)
                elif update_g:
                    gs += 2  # G + D
                else:
                    gs += 1  # D のみ
            assert gs >= 2000

    def test_d_update_interval_wired_into_lightning_gate(self):
        """training_step_g の LF gate に d_update_interval が配線されている
        こと (source 検査 pin — 配線を外す mutation はラッチを復活させる)。"""
        import inspect

        from piper_train.vits import lightning as lightning_mod

        src = inspect.getsource(lightning_mod)
        windows = [
            src[m.end() : m.end() + 300]
            for m in re.finditer(r"should_run_latent_filling_step\(", src)
        ]
        assert windows, (
            "lightning が should_run_latent_filling_step を呼んでいない "
            "(is_latent_filling_step 直呼びは D-only step との重なりで "
            "no-op ラッチになる)"
        )
        assert any("d_update_interval" in w for w in windows), (
            "LF gate に d_update_interval が配線されていない — D-only step "
            "で LF が発動し global_step が凍結する no-op ラッチが復活する"
        )


@pytest.mark.unit
class TestLatentFillingLambda:
    def test_beta_half_half_shape(self):
        """λ ~ Beta(0.5, 0.5) (arcsine 分布): mean 0.5 / var 0.125 /
        U 字型 (両端に質量が寄る — uniform や単峰分布と識別)。"""
        fn = _losses_attr("sample_latent_filling_lambda")
        g = torch.Generator().manual_seed(0)
        lam = fn(4000, generator=g)
        assert lam.shape == (4000,)
        assert float(lam.min()) >= 0.0
        assert float(lam.max()) <= 1.0
        assert float(lam.mean()) == pytest.approx(0.5, abs=0.05)
        var = float(lam.var())
        assert 0.10 < var < 0.15, (
            f"var={var:.4f} — Beta(0.5,0.5) は 0.125 (uniform 0.083 / "
            "Beta(2,2) 0.05 とは区別される)"
        )
        tail_mass = float(((lam < 0.1) | (lam > 0.9)).float().mean())
        assert 0.32 < tail_mass < 0.50, (
            f"tail mass={tail_mass:.3f} — arcsine 分布なら ~0.41 "
            "(uniform は 0.2、二点分布は 1.0)"
        )

    def test_deterministic_with_seeded_generator(self):
        fn = _losses_attr("sample_latent_filling_lambda")
        lam1 = fn(64, generator=torch.Generator().manual_seed(5))
        lam2 = fn(64, generator=torch.Generator().manual_seed(5))
        assert torch.equal(lam1, lam2)


@pytest.mark.unit
class TestBuildLatentFillingEmbeddings:
    def test_same_language_constraint_and_shape(self):
        """s̃ は同一言語話者の span 内 (補間ペアが言語グループを跨がない)。

        基底ベクトル埋め込み (row i = e_i) を使うと、補間 branch でも
        noise branch (σ=1e-4) でも他言語行の基底成分はほぼ 0 のはず。
        """
        fn = _losses_attr("build_latent_filling_embeddings")
        emb = torch.eye(192)[:4]  # rows: e0, e1, e2, e3 (unit norm)
        lang = torch.tensor([0, 0, 1, 1])
        for seed in range(5):  # 補間/noise 両 branch を確率的にカバー
            g = torch.Generator().manual_seed(seed)
            s_tilde = fn(emb, language_ids=lang, generator=g)
            assert s_tilde.shape == emb.shape
            # lang 0 の行 (0,1) に lang 1 の基底 (dim 2,3) 成分が混入しない
            assert float(s_tilde[:2, 2:4].abs().max()) < 0.05, (
                f"seed={seed}: lang 0 行に lang 1 成分が混入 (言語跨ぎ補間)"
            )
            assert float(s_tilde[2:, 0:2].abs().max()) < 0.05, (
                f"seed={seed}: lang 1 行に lang 0 成分が混入 (言語跨ぎ補間)"
            )

    def test_perturbs_input(self):
        """補間 (λ) or noise (σ=1e-4) — どちらの branch でも s̃ != s。"""
        fn = _losses_attr("build_latent_filling_embeddings")
        emb = F.normalize(torch.randn(4, 192), dim=-1)
        lang = torch.tensor([0, 0, 0, 0])
        g = torch.Generator().manual_seed(0)
        s_tilde = fn(emb, language_ids=lang, generator=g)
        assert not torch.equal(s_tilde, emb)

    def test_deterministic_with_seeded_generator(self):
        fn = _losses_attr("build_latent_filling_embeddings")
        emb = F.normalize(torch.randn(4, 192), dim=-1)
        lang = torch.tensor([0, 0, 1, 1])
        s1 = fn(emb, language_ids=lang, generator=torch.Generator().manual_seed(9))
        s2 = fn(emb, language_ids=lang, generator=torch.Generator().manual_seed(9))
        assert torch.equal(s1, s2)

    def test_interpolation_branch_preserves_unit_norm(self):
        """補間 branch の s̃ は L2 unit-norm (再正規化必須、レビュー findings)。

        直交単位ベクトル 2 本の λ 補間は正規化なしでは norm =
        √(λ² + (1-λ)²) < 1 (λ=0.5 で 1/√2 ≈ 0.71) となり、パイプライン
        全体が保つ「spk_proj 入力は unit-norm」不変条件を破る (σ-noise
        経路の加算後 renormalize ガードと同型の magnitude 不一致 →
        spk_proj 発散の既知事故経路)。noise branch (σ=1e-4) の norm 偏差は
        ~1e-4 なので許容 1e-3 で両 branch を同時に検査できる。
        """
        fn = _losses_attr("build_latent_filling_embeddings")
        emb = torch.eye(192)[:4]  # 直交 unit ベクトル
        lang = torch.tensor([0, 0, 0, 0])
        interp_hit = False
        for seed in range(20):
            g = torch.Generator().manual_seed(seed)
            s_tilde = fn(emb, language_ids=lang, generator=g)
            norms = s_tilde.norm(dim=-1)
            assert float((norms - 1.0).abs().max()) < 1e-3, (
                f"seed={seed}: s̃ の norm が unit から乖離: {norms.tolist()}"
            )
            # 補間が発火した行 = 基底 2 成分が有意に混合された行
            interp_hit = interp_hit or bool((s_tilde > 0.05).sum() > 4)
        assert interp_hit, "20 seed で補間 branch が一度も発火していない (検査が空)"

    def test_speaker_ids_route_same_speaker_group_to_noise_branch(self):
        """speaker_ids 指定で 1 話者のみのグループは補間せず noise branch
        (同一話者補間は ≒恒等で LF の摂動が希釈される — レビュー findings)。"""
        fn = _losses_attr("build_latent_filling_embeddings")
        emb = torch.eye(192)[:4]
        lang = torch.tensor([0, 0, 0, 0])
        spk_same = torch.tensor([5, 5, 5, 5])
        for seed in range(20):
            g = torch.Generator().manual_seed(seed)
            s_tilde = fn(emb, language_ids=lang, speaker_ids=spk_same, generator=g)
            assert float((s_tilde - emb).abs().max()) < 1e-2, (
                f"seed={seed}: 同一話者しかいないのに補間が発火している"
            )
        # 対照: 異話者がいれば補間は発火する (検査が空でないこと)
        spk_diff = torch.tensor([5, 6, 5, 6])
        mixed = False
        for seed in range(20):
            g = torch.Generator().manual_seed(seed)
            s_tilde = fn(emb, language_ids=lang, speaker_ids=spk_diff, generator=g)
            mixed = mixed or float((s_tilde - emb).abs().max()) > 0.05
        assert mixed, "異話者ありで補間 branch が一度も発火しない (配線が死んでいる)"


class TestLatentFillingConsistencyGradient:
    def test_lfcl_gradient_reaches_spk_proj(self, tmp_path):
        """LFCL = 1 - cos(scl_encoder(y_hat), s̃) の勾配が spk_proj に届く。

        LF step は recon/mel/KL/GAN を skip し LFCL のみで G を更新するため、
        s̃ 条件付け経路 (spk_proj) に勾配が通ることが唯一の学習信号になる。
        """
        pytest.importorskip("torchaudio")
        build = _losses_attr("build_latent_filling_embeddings")
        from piper_train.speaker_encoder.campplus_torch import (
            CAMPPlus,
            DifferentiableCamPPEncoder,
        )

        model = _tiny_synthesizer()
        torch.manual_seed(0)
        b, t_text, t_frames = 2, 20, 48
        x = torch.randint(1, 50, (b, t_text))
        x_lengths = torch.full((b,), t_text)
        y = torch.randn(b, 513, t_frames)
        y_lengths = torch.full((b,), t_frames)
        emb = F.normalize(torch.randn(b, 192), dim=-1)
        g = torch.Generator().manual_seed(0)
        s_tilde = build(emb, language_ids=torch.tensor([0, 0]), generator=g)

        out = model(x, x_lengths, y, y_lengths, speaker_embeddings=s_tilde)

        weights = tmp_path / "campplus_random.bin"
        torch.save(CAMPPlus(embedding_size=192).state_dict(), weights)
        encoder = DifferentiableCamPPEncoder(str(weights), source_sr=22050)

        emb_gen = encoder(out.waveform.squeeze(1).float())
        lfcl = (1.0 - F.cosine_similarity(emb_gen, s_tilde, dim=-1)).mean()
        lfcl.backward()

        assert _grad_sum(model.spk_proj) > 0, (
            "LFCL の勾配が spk_proj に届いていない — LF step の学習信号が 存在しない"
        )


# ===========================================================================
# 5. DINO 廃止警告 (F8)
# ===========================================================================


def _make_vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover - env without training deps
        pytest.skip(f"Training dependencies not available: {e}")

    kwargs = {
        "num_symbols": 97,
        "num_speakers": 4,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 4,
        "learning_rate": 2e-4,
        "use_wavlm_discriminator": False,
    }
    kwargs.update(overrides)
    return VitsModel(**kwargs)


def _dino_warning_records(caplog):
    return [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING
        and r.name.startswith("piper_train")
        and "dino" in r.getMessage().lower()
    ]


@pytest.mark.unit
class TestDinoDeprecationWarning:
    """設計 doc F8: DINO は frozen CAM++/同一入力/拡張なしで慣性項に退化済み。
    c_dino > 0 のまま学習を始めるユーザに 1 回だけ警告する。"""

    def _fire_train_start_hooks(self, model):
        # 実装位置は構築時 (推奨) か train 開始 hook のどちらでもよい
        for hook in ("on_fit_start", "on_train_start"):
            try:
                getattr(model, hook)()
            except Exception:  # noqa: BLE001 - hook が trainer 前提でも許容
                pass

    def test_warns_exactly_once_when_c_dino_positive(self, caplog):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            model = _make_vits_model(c_dino=0.5)
            if not _dino_warning_records(caplog):
                self._fire_train_start_hooks(model)
        records = _dino_warning_records(caplog)
        assert len(records) == 1, (
            f"c_dino>0 の警告が {len(records)} 回 (期待 1 回) — "
            "F8: DINO 退化済み、v10 は c_dino=0 推奨の警告が必要"
        )

    def test_no_warning_when_c_dino_zero(self, caplog):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            model = _make_vits_model(c_dino=0.0)
            self._fire_train_start_hooks(model)
        assert _dino_warning_records(caplog) == []
