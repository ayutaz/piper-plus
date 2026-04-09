"""Tests for infer_onnx.resolve_config_path().

These tests verify ``resolve_config_path()`` directly -- the function that
resolves the config.json path for a given ONNX model with the following
fallback order:

  1. If --config is explicitly given, use that path directly.
  2. Otherwise, try {model}.onnx.json first (C++ CLI convention).
  3. Fall back to {model_dir}/config.json.
"""

import json
from pathlib import Path

import pytest

from piper_train.infer_onnx import resolve_config_path


@pytest.mark.unit
class TestConfigPathResolution:
    """Config パス解決ロジックのユニットテスト."""

    def test_onnx_json_preferred(self, tmp_path: Path):
        """model.onnx.json が存在する場合、config.json より優先される."""
        model = tmp_path / "model.onnx"
        model.touch()

        onnx_json = tmp_path / "model.onnx.json"
        onnx_json.write_text(json.dumps({}), encoding="utf-8")

        config_json = tmp_path / "config.json"
        config_json.write_text(json.dumps({}), encoding="utf-8")

        result = resolve_config_path(str(model), config=None)

        assert result == onnx_json
        assert result.exists()

    def test_fallback_to_config_json(self, tmp_path: Path):
        """model.onnx.json が存在しない場合、config.json にフォールバック."""
        model = tmp_path / "model.onnx"
        model.touch()

        config_json = tmp_path / "config.json"
        config_json.write_text(json.dumps({}), encoding="utf-8")

        result = resolve_config_path(str(model), config=None)

        assert result == config_json
        assert result.exists()

    def test_neither_exists(self, tmp_path: Path):
        """どちらの config も存在しない場合、返却パスは存在しない."""
        model = tmp_path / "model.onnx"
        model.touch()

        result = resolve_config_path(str(model), config=None)

        # ロジックは config.json パスを返すが、ファイルは存在しない
        assert result == tmp_path / "config.json"
        assert not result.exists()

    def test_explicit_config_overrides(self, tmp_path: Path):
        """--config を明示指定すると、フォールバックせずそのパスを使う."""
        model = tmp_path / "model.onnx"
        model.touch()

        # フォールバック先も配置しておく
        onnx_json = tmp_path / "model.onnx.json"
        onnx_json.write_text(json.dumps({}), encoding="utf-8")

        explicit = tmp_path / "custom" / "my_config.json"
        explicit.parent.mkdir(parents=True, exist_ok=True)
        explicit.write_text(json.dumps({}), encoding="utf-8")

        result = resolve_config_path(str(model), config=str(explicit))

        assert result == explicit
        assert result.exists()
        # model.onnx.json が存在しても選ばれないことを確認
        assert result != onnx_json
