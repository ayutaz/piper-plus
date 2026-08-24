"""piper_train.tools.eval_cer のユニットテスト。

v11 の教訓 (2026-08-25): SECS / comb-HNR / seen-ID はどれも「発話として
読めているか」を測らず、日本語として聞き取れないモデルが指標上は良好に
見えた。ASR ベースの CER を評価系に追加し、v11b では gate に昇格する。

ASR backend (transformers whisper) はテストでは transcribe_fn 差し替えで
分離する (score_utmos の torch.hub monkeypatch と同じ流儀)。
"""

import pytest

pytest.importorskip("numpy", reason="numpy required for eval_cer tests")


@pytest.mark.unit
class TestCer:
    """cer() 純関数 (編集距離 / 参照長)。"""

    def test_identity_is_zero(self):
        from piper_train.tools.eval_cer import cer

        assert cer("こんにちは", "こんにちは") == 0.0

    def test_single_substitution(self):
        from piper_train.tools.eval_cer import cer

        # 5 文字中 1 置換 → 0.2
        assert cer("こんにちは", "こんばちは") == pytest.approx(0.2)

    def test_deletion_and_insertion(self):
        from piper_train.tools.eval_cer import cer

        assert cer("こんにちは", "こんには") == pytest.approx(0.2)  # 1 削除
        assert cer("こんにちは", "こんにちはあ") == pytest.approx(0.2)  # 1 挿入

    def test_complete_mismatch_caps_at_one_or_more(self):
        from piper_train.tools.eval_cer import cer

        # 全置換は 1.0、参照より長い出鱈目は 1.0 を超えうる (clip しない)
        assert cer("あい", "かき") == pytest.approx(1.0)
        assert cer("あ", "かきくけこ") >= 1.0

    def test_empty_hypothesis(self):
        from piper_train.tools.eval_cer import cer

        assert cer("こんにちは", "") == pytest.approx(1.0)

    def test_empty_reference_raises(self):
        from piper_train.tools.eval_cer import cer

        with pytest.raises(ValueError):
            cer("", "こんにちは")


@pytest.mark.unit
class TestNormalizeText:
    """正規化: 句読点・空白・全半角差は CER に含めない。"""

    def test_punctuation_and_space_removed(self):
        from piper_train.tools.eval_cer import normalize_text

        assert normalize_text("こんにちは、今日は いい天気ですね。") == (
            "こんにちは今日はいい天気ですね"
        )

    def test_nfkc_fullwidth_unified(self):
        from piper_train.tools.eval_cer import normalize_text

        # 全角英数 → 半角、半角カナ → 全角 (NFKC)
        assert normalize_text("ＡＢＣ１２３") == "ABC123"
        assert normalize_text("ｱｲｳ") == "アイウ"

    def test_cer_uses_normalization(self):
        from piper_train.tools.eval_cer import cer

        assert cer("こんにちは、今日は。", "こんにちは 今日は") == 0.0


@pytest.mark.unit
class TestEvaluateClips:
    """evaluate_clips: transcribe_fn 注入で ASR 非依存に集計を検証。"""

    def test_aggregates_median_mean_and_per_file(self, tmp_path):
        from piper_train.tools.eval_cer import evaluate_clips

        wavs = []
        for tid in ("t0", "t1", "t2"):
            p = tmp_path / f"{tid}.wav"
            p.write_bytes(b"")  # transcribe_fn 注入のため中身は読まれない
            wavs.append(p)
        refs = {"t0": "こんにちは", "t1": "ありがとう", "t2": "さようなら"}
        fake = {
            str(wavs[0]): "こんにちは",  # CER 0.0
            str(wavs[1]): "ありがとお",  # 1/5 = 0.2
            str(wavs[2]): "",  # 1.0
        }

        result = evaluate_clips(
            [(p, refs[p.stem]) for p in wavs],
            transcribe_fn=lambda p: fake[str(p)],
        )

        assert result["per_file"]["t0"]["cer"] == pytest.approx(0.0)
        assert result["per_file"]["t1"]["cer"] == pytest.approx(0.2)
        assert result["per_file"]["t2"]["cer"] == pytest.approx(1.0)
        assert result["cer_median"] == pytest.approx(0.2)
        assert result["cer_mean"] == pytest.approx(0.4)
        assert result["n_clips"] == 3

    def test_transcript_recorded_for_inspection(self, tmp_path):
        """ASR 出力の生文字列を保存する (誤判定の目視検証用)。"""
        from piper_train.tools.eval_cer import evaluate_clips

        p = tmp_path / "t0.wav"
        p.write_bytes(b"")
        result = evaluate_clips(
            [(p, "こんにちは")], transcribe_fn=lambda _: "こんばんは"
        )
        assert result["per_file"]["t0"]["transcript"] == "こんばんは"
