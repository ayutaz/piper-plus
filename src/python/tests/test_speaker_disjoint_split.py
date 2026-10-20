"""``--validation-split-by speaker``: train / val を話者単位で分ける。

発話単位の ``random_split`` では、同じ話者の発話が train と val の両方に入り、
cross_utt の参照も subset を跨ぐ (S3 smoke の実データで 297,746 件中 55,035 件)。
話者単位の分割では、1 人の話者の発話はすべて片側に入る。

固定する性質:

* どの話者も train と val の両方には現れない (複数言語に出る話者も 1 か所)。
* 言語ごとに、その言語の発話数 × ``validation_split`` 件以上になるまで話者を
  val へ移す。どの言語も最低 1 人は train に残す。
* 同じ seed なら同じ分割。``validation_split=0`` なら val は空。
* ``speaker_id`` が無い発話があれば ValueError (話者で分けられない)。
"""

from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.unit

pytest.importorskip("torch", reason="lightning module needs the train extra (torch).")

from piper_train.vits.lightning import speaker_disjoint_split  # noqa: E402


def _utts(spec):
    """``[(speaker_id, language_id, count), ...]`` → 発話の並び。"""
    out = []
    for speaker, language, count in spec:
        out.extend(
            SimpleNamespace(speaker_id=speaker, language_id=language)
            for _ in range(count)
        )
    return out


_SPEC = [
    (0, 0, 10),
    (1, 0, 12),
    (2, 0, 9),
    (3, 0, 11),
    (4, 0, 8),
    (5, 1, 20),
    (6, 1, 15),
    (7, 1, 25),
    (8, 2, 30),  # この言語は 1 人だけ
]


def _speakers(utts, indices):
    return {utts[i].speaker_id for i in indices}


def test_no_speaker_is_on_both_sides_and_every_row_is_assigned():
    utts = _utts(_SPEC)
    train, val = speaker_disjoint_split(utts, 0.2, seed=1234)
    assert sorted(train + val) == list(range(len(utts)))
    assert _speakers(utts, train).isdisjoint(_speakers(utts, val))
    assert val, "the fixture must put somebody into val"


def test_each_language_reaches_its_share_and_keeps_a_train_speaker():
    utts = _utts(_SPEC)
    train, val = speaker_disjoint_split(utts, 0.2, seed=1234)
    total = Counter(u.language_id for u in utts)
    in_val = Counter(utts[i].language_id for i in val)
    in_train = Counter(utts[i].language_id for i in train)
    for language in (0, 1):
        assert in_val[language] >= int(total[language] * 0.2)
        assert in_train[language] > 0
    # 1 人しかいない言語は val へ移さない
    assert in_val[2] == 0 and in_train[2] == 30


def test_stops_moving_speakers_once_the_share_is_reached():
    # 0.2 × 50 = 10 件。どの 1 人を先に移しても 8 件以上なので、2 人目で止まる
    utts = _utts(_SPEC[:5])
    _, val = speaker_disjoint_split(utts, 0.2, seed=7)
    assert len(_speakers(utts, val)) <= 2


def test_same_seed_same_split():
    utts = _utts(_SPEC)
    assert speaker_disjoint_split(utts, 0.2, seed=3) == speaker_disjoint_split(
        utts, 0.2, seed=3
    )


def test_zero_split_leaves_val_empty():
    utts = _utts(_SPEC)
    train, val = speaker_disjoint_split(utts, 0.0, seed=1)
    assert val == [] and train == list(range(len(utts)))


def test_speaker_in_two_languages_stays_on_one_side():
    # 話者 0 は言語 0 と言語 1 の両方に出る。言語ごとに独立に振ると漏れる
    utts = _utts([(0, 0, 6), (1, 0, 6), (2, 0, 6), (0, 1, 2), (3, 1, 6), (4, 1, 6)])
    for seed in range(20):
        train, val = speaker_disjoint_split(utts, 0.3, seed=seed)
        assert _speakers(utts, train).isdisjoint(_speakers(utts, val)), seed


def test_missing_speaker_id_is_rejected():
    utts = _utts([(0, 0, 3), (None, 0, 2)])
    with pytest.raises(ValueError, match="speaker_id"):
        speaker_disjoint_split(utts, 0.2, seed=1)


def test_cli_flag_defaults_to_utterance_and_accepts_speaker():
    from piper_train.__main__ import create_parser

    base = ["--dataset-dir", "/tmp/x", "--batch-size", "1"]
    parser = create_parser()
    assert parser.parse_args(base).validation_split_by == "utterance"
    args = parser.parse_args([*base, "--validation-split-by", "speaker"])
    assert args.validation_split_by == "speaker"
    with pytest.raises(SystemExit):
        create_parser().parse_args([*base, "--validation-split-by", "language"])
