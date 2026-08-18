"""S-2 Phase D go/no-go ツール (F0 シフト追従) の TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §6.4 検証 3。

判定ロジックは純関数 (``semitone_to_scale`` / ``follow_ratio`` /
``summarize``) に切り出してあるので、ckpt も GPU も無しで固定できる。
実合成部分は ``synthesize_shifted`` を小さなモデルで 1 回通して配線だけ確認する。

固定する契約:

* 追従率 = 実測 semitone 差 / 指令 semitone 差。完全追従で 1.0、無視で 0.0。
* **go 基準 0.8 は事前登録値**。ここを下げるのは「測ってから基準をいじる」
  ことなので、設計 doc の改訂を伴わなければならない。
* 評価は ``measure_prosody`` を **subprocess** で呼ぶ (学習プロセスに評価器を
  引き込まない)。
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.tools import f0_shift_ablation as abl  # noqa: E402


def test_semitone_to_scale():
    assert abl.semitone_to_scale(0.0) == pytest.approx(1.0)
    assert abl.semitone_to_scale(12.0) == pytest.approx(2.0)
    assert abl.semitone_to_scale(-12.0) == pytest.approx(0.5)
    assert abl.semitone_to_scale(2.0) == pytest.approx(1.122462, rel=1e-5)


def test_follow_ratio_is_one_for_perfect_tracking():
    base = 200.0
    measured = {
        -2.0: base * abl.semitone_to_scale(-2.0),
        0.0: base,
        2.0: base * abl.semitone_to_scale(2.0),
    }
    ratios = abl.follow_ratio(measured)
    assert ratios[2.0] == pytest.approx(1.0, abs=1e-6)
    assert ratios[-2.0] == pytest.approx(1.0, abs=1e-6)


def test_follow_ratio_is_zero_when_the_decoder_ignores_f0():
    """S-2 の失敗機序 (R1): 指令を変えても出力 F0 が動かない。"""
    measured = {-2.0: 200.0, 0.0: 200.0, 2.0: 200.0}
    ratios = abl.follow_ratio(measured)
    assert ratios[2.0] == pytest.approx(0.0)
    assert ratios[-2.0] == pytest.approx(0.0)


def test_follow_ratio_handles_partial_tracking():
    base = 200.0
    measured = {0.0: base, 2.0: base * abl.semitone_to_scale(1.0)}
    assert abl.follow_ratio(measured)[2.0] == pytest.approx(0.5, abs=1e-6)


def test_follow_ratio_without_a_usable_reference_returns_empty():
    assert abl.follow_ratio({2.0: 220.0}) == {}
    assert abl.follow_ratio({0.0: 0.0, 2.0: 220.0}) == {}


def test_summarize_applies_the_preregistered_go_threshold():
    assert abl.summarize({2.0: 0.9, -2.0: 0.85})["verdict"] == "go"
    assert abl.summarize({2.0: 0.05, -2.0: 0.02})["verdict"] == "no-go"
    # 境界値ちょうどは go (>= 判定)
    assert abl.summarize({2.0: 0.8})["verdict"] == "go"
    assert abl.summarize({})["verdict"] == "no-go"


def test_go_threshold_matches_the_design_document():
    """事前登録値 0.8 (設計 doc §6.4 検証 3) から動いていないこと。"""
    assert abl.GO_THRESHOLD == 0.8


def test_measurement_runs_measure_prosody_in_a_subprocess():
    """評価器は subprocess 越し (torch を積んだプロセスに引き込まない)。"""
    source = inspect.getsource(abl.measure_group_f0_median)
    assert "subprocess.run" in source
    assert "piper_train.tools.measure_prosody" in source
    # module import による直結が無いこと
    module_source = inspect.getsource(abl)
    assert "from piper_train.tools.measure_prosody import" not in module_source


def test_cli_help_is_printable_on_a_cp932_console():
    """``--help`` が Windows の cp932 コンソールで落ちない。

    argparse は help 文字列をそのまま stdout に書くため、em dash (U+2014) の
    ような cp932 非対応文字を入れると ``--help`` が UnicodeEncodeError で
    死ぬ (実際に踏んだ)。日本語自体は cp932 にあるので、記号だけ ASCII に
    留めれば足りる。
    """
    import re

    from piper_train.tools import extract_f0

    help_re = re.compile(r'help=\s*((?:"[^"]*"\s*|\'[^\']*\'\s*)+)')
    for module in (abl, extract_f0):
        source = inspect.getsource(module)
        for match in help_re.finditer(source):
            for ch in match.group(1):
                try:
                    ch.encode("cp932")
                except UnicodeEncodeError:
                    pytest.fail(
                        f"{module.__name__}: help text contains {ch!r}, which "
                        f"a cp932 console cannot print (--help would crash)"
                    )


def test_write_wav_roundtrip(tmp_path):
    import wave

    audio = np.sin(np.linspace(0, 20 * np.pi, 2000)).astype(np.float32) * 0.5
    path = tmp_path / "a.wav"
    abl.write_wav(path, audio, 22050)
    with wave.open(str(path)) as wf:
        assert wf.getframerate() == 22050
        assert wf.getnchannels() == 1
        assert wf.getnframes() == 2000


def test_synthesize_shifted_writes_one_wav_per_utterance(tmp_path):
    """配線確認: 小さな S-2 モデルで実際に合成して wav が出る。"""
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(0)
    model = SynthesizerTrn(
        n_vocab=40,
        spec_channels=513,
        segment_size=32,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=256,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.0,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        n_speakers=4,
        gin_channels=512,
        prosody_dim=0,
        use_f0_path=True,
    )
    model.eval()
    emb = np.random.default_rng(0).normal(size=192).astype(np.float32)
    emb /= np.linalg.norm(emb)

    abl.synthesize_shifted(
        model,
        [[1, 2, 3, 4, 5], [6, 7, 8]],
        emb,
        tmp_path / "shift",
        f0_scale=abl.semitone_to_scale(2.0),
        sample_rate=22050,
    )
    assert len(list((tmp_path / "shift").glob("*.wav"))) == 2
