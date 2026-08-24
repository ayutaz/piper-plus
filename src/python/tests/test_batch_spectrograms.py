"""Tests for piper_train.tools.batch_spectrograms save/tally behaviour.

``_save_spec`` はかつて ``tempfile.mkstemp`` を cleanup ブロックの内側で呼んで
いたため、mkstemp 自体が失敗する (ENOSPC / EACCES / 親ディレクトリ不在) と
``except`` 節で ``tmp_path`` が未束縛となり ``UnboundLocalError`` が本来の例外を
覆い隠していた。さらに全失敗を無言で握り潰していたため、1 件も書けていない
状態でも ``processed=N`` と報告され得た。

本ファイルは以下を pinning する:

- happy path: ``.spec.pt`` が FP16 で書かれ、``.tmp`` が残らない
- ``mkstemp`` 失敗: ``UnboundLocalError`` にならず False + warning
- ``torch.save`` 失敗: tmp が掃除され False + warning
- ``run()``: save 失敗を processed ではなく skipped に計上する

GPU / ``torch.cuda`` は不要 (device="cpu" で動作)。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


pytest.importorskip("torch", reason="torch required for batch_spectrograms")
pytest.importorskip("tqdm", reason="tqdm required for batch_spectrograms")

import torch  # noqa: E402

from piper_train.tools import batch_spectrograms as bs  # noqa: E402


def _write_audio_pt(path: Path, n_samples: int = 4096) -> None:
    """1-D のダミー波形を .pt として書き出す。"""
    torch.save(torch.zeros(n_samples), str(path))


# ---------------------------------------------------------------------------
# _save_spec: happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_save_spec_writes_fp16_spec(tmp_path):
    pt_path = tmp_path / "utt001.pt"
    pt_path.touch()
    spec = torch.ones(513, 7)

    assert bs._save_spec((str(pt_path), spec)) is True

    spec_path = tmp_path / "utt001.spec.pt"
    assert spec_path.exists()
    loaded = torch.load(str(spec_path), weights_only=True, map_location="cpu")
    assert loaded.dtype == torch.float16
    assert loaded.shape == (513, 7)
    # 中間 .tmp は replace 済みで残らない
    assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# _save_spec: mkstemp 失敗 (UnboundLocalError 回帰ガード)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_save_spec_mkstemp_failure_returns_false(tmp_path, monkeypatch, caplog):
    def _boom(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(bs.tempfile, "mkstemp", _boom)

    pt_path = tmp_path / "utt002.pt"
    with caplog.at_level(logging.WARNING, logger=bs.__name__):
        # 修正前はここで UnboundLocalError('tmp_path') が送出されていた
        result = bs._save_spec((str(pt_path), torch.ones(4, 4)))

    assert result is False
    assert not (tmp_path / "utt002.spec.pt").exists()
    assert "utt002.spec.pt" in caplog.text
    assert "No space left on device" in caplog.text


@pytest.mark.unit
def test_save_spec_missing_parent_dir_returns_false(tmp_path, caplog):
    """親ディレクトリ不在でも例外を漏らさず False を返す。"""
    pt_path = tmp_path / "missing" / "utt003.pt"

    with caplog.at_level(logging.WARNING, logger=bs.__name__):
        result = bs._save_spec((str(pt_path), torch.ones(4, 4)))

    assert result is False
    assert "utt003.spec.pt" in caplog.text


# ---------------------------------------------------------------------------
# _save_spec: torch.save 失敗
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_save_spec_torch_save_failure_cleans_tmp(tmp_path, monkeypatch, caplog):
    def _boom(*args, **kwargs):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(bs.torch, "save", _boom)

    pt_path = tmp_path / "utt004.pt"
    with caplog.at_level(logging.WARNING, logger=bs.__name__):
        result = bs._save_spec((str(pt_path), torch.ones(4, 4)))

    assert result is False
    assert not (tmp_path / "utt004.spec.pt").exists()
    # mkstemp が作った空 tmp は unlink 済み
    assert list(tmp_path.glob("*.tmp")) == []
    assert "disk exploded" in caplog.text


# ---------------------------------------------------------------------------
# run(): save 失敗の集計
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_counts_saved_files_as_processed(tmp_path, caplog):
    for i in range(2):
        _write_audio_pt(tmp_path / f"utt{i}.pt")

    with caplog.at_level(logging.INFO, logger=bs.__name__):
        bs.run(str(tmp_path), batch_size=2, device="cpu", io_workers=2)

    assert (tmp_path / "utt0.spec.pt").exists()
    assert (tmp_path / "utt1.spec.pt").exists()
    assert "processed=2  skipped=0" in caplog.text


@pytest.mark.unit
def test_run_counts_save_failures_as_skipped(tmp_path, monkeypatch, caplog):
    for i in range(2):
        _write_audio_pt(tmp_path / f"utt{i}.pt")

    monkeypatch.setattr(bs, "_save_spec", lambda args: False)

    with caplog.at_level(logging.INFO, logger=bs.__name__):
        bs.run(str(tmp_path), batch_size=2, device="cpu", io_workers=2)

    # 1 件も書けていないので processed=0 (修正前は processed=2 と過大報告)
    assert "processed=0  skipped=2" in caplog.text
