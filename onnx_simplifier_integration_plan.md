# ONNX Simplifier統合計画

## 実装方針

### 1. 依存関係の追加
```bash
# requirements.txtに追加
onnxsim-prebuilt>=0.4.0  # ONNX model simplification
```

### 2. export_onnx.pyの拡張
```python
def simplify_onnx_model(onnx_path: Path, output_path: Path = None) -> None:
    """ONNXモデルを簡素化"""
    try:
        import onnx
        from onnxsim import simplify
        
        model = onnx.load(str(onnx_path))
        model_simp, check = simplify(model)
        
        if check:
            output_path = output_path or onnx_path
            onnx.save(model_simp, str(output_path))
            _LOGGER.info("Model simplified successfully: %s", output_path)
        else:
            _LOGGER.warning("Model simplification failed validation")
    except ImportError:
        _LOGGER.warning("onnxsim-prebuilt not installed, skipping simplification")
    except Exception as e:
        _LOGGER.error("Simplification failed: %s", e)
```

### 3. コマンドライン引数の追加
```python
parser.add_argument(
    "--simplify", 
    action="store_true", 
    help="Apply ONNX model simplification after export"
)
parser.add_argument(
    "--simplify-only",
    help="Only simplify existing ONNX model (path to .onnx file)"
)
```

### 4. 両方の変換方式への対応
- `export_onnx.py`: 一体型モデルの簡素化
- `export_onnx_streaming.py`: エンコーダー・デコーダー個別簡素化

## 期待される効果

1. **推論速度**: 5-15%の高速化
2. **メモリ使用量**: 計算グラフ最適化による削減
3. **デプロイメント**: 最適化されたモデルの配布

## リスク評価

- **低リスク**: オプション機能として実装
- **下位互換性**: 既存フローに影響なし
- **検証**: 簡素化後の出力品質確認が必要