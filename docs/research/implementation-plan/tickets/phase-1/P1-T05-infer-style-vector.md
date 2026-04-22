# P1-T05: infer.py に style_vector 推論統合

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 未着手 |
| 優先度 | 中 |
| Claude Code 工数 | 15〜30分 |
| 依存チケット | P1-T01, P1-T04 |
| 後続チケット | P1-T06 |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

`src/python/piper_train/infer.py` に style_vector 推論機能を追加する。CLI から `--style-vector` (npy/pt ファイルパス or inline text) で指定された style vector を読み込み、SynthesizerTrn.infer へ渡す。

GPU device 対応は既存の推論パスに合わせて差分として取り込む。fork 準拠の `_style_vector_to_tensor()` ヘルパーを同ファイル内に実装。

**対象はあくまで PyTorch 推論 (`infer.py`) であり、ONNX 推論 (`infer_onnx.py`) は Phase 2 で対応**。

### 1.2 ゴール (Definition of Done)

- [ ] `_style_vector_to_tensor()` helper が実装されている (npy/pt/inline 対応)
- [ ] argparse に `--style-vector` オプションが追加されている
- [ ] 推論ループで `model.infer(..., style_vector=style_vector)` が呼ばれている
- [ ] style_vector が指定されない場合は None または zeros を渡し、既存挙動と一致 (`style_vector_dim=0` モデルで regression なし)
- [ ] GPU device 整合 (style_vector が `cuda` デバイスに transfer される)
- [ ] `_style_vector_to_tensor()` が不正なパスで明示的な例外を出す (FileNotFoundError or ValueError)
- [ ] `python -m piper_train.infer --help | grep style-vector` で表示確認

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/infer.py` (修正、+25 行想定)

### 2.2 実装手順

1. Fork commit `314b3355` の `infer.py` 差分を取得
2. `_style_vector_to_tensor(value: str | Path | None, device, dtype)` helper を実装
   - None → None を返す (model 側で zeros fallback)
   - `.npy` → `np.load → torch.from_numpy`
   - `.pt` / `.pth` → `torch.load(map_location=device)`
   - inline (カンマ区切り数値) → `torch.tensor([...])` で parse (オプション、fork 実装確認)
   - unknown 拡張子 → `ValueError`
3. device/dtype を合わせて transfer
4. argparse に `--style-vector` (type=str, default=None) を追加
5. 推論ループで `style_vector=_style_vector_to_tensor(args.style_vector, device, dtype)` を計算し、`model.infer(..., style_vector=style_vector)` へ渡す
6. 複数発話を処理する場合は style_vector を batch 次元に broadcast (`.unsqueeze(0)`) するか、同じ vector を使うか挙動を明示

### 2.3 コード例 (phase-0-1.md §1.4 Patch 6 相当)

```python
from pathlib import Path
import numpy as np
import torch

def _style_vector_to_tensor(
    value: str | None,
    device: torch.device,
    dtype: torch.dtype = torch.float32,
) -> torch.Tensor | None:
    """Load style vector from .npy / .pt / inline string."""
    if value is None or value == "":
        return None
    path = Path(value)
    if path.suffix == ".npy":
        arr = np.load(path)
        tensor = torch.from_numpy(arr)
    elif path.suffix in (".pt", ".pth"):
        tensor = torch.load(path, map_location=device)
    elif "," in value:
        # Inline comma-separated values
        tensor = torch.tensor([float(v) for v in value.split(",")])
    else:
        raise ValueError(
            f"Unsupported style vector format: {value}. "
            f"Expected .npy, .pt, .pth, or comma-separated values."
        )
    return tensor.to(device=device, dtype=dtype)


# argparse 追加
parser.add_argument("--style-vector", type=str, default=None,
                    help="Style vector (.npy/.pt path or comma-separated values)")

# 推論ループ (抜粋)
style_vector = _style_vector_to_tensor(args.style_vector, device)
if style_vector is not None and style_vector.dim() == 1:
    style_vector = style_vector.unsqueeze(0)  # Add batch dim

with torch.no_grad():
    audio = model.infer(
        phoneme_ids=phoneme_ids,
        phoneme_ids_lengths=phoneme_ids_lengths,
        speaker_ids=speaker_ids,
        language_ids=language_ids,
        style_vector=style_vector,  # 追加
        ...
    )
```

完全な fork diff は `gh api "repos/yusuke-ai/piper-plus/commits/314b3355"` で取得。

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`infer.py` 修正)
  - 変更量が小さいため 1 エージェントで完遂
- **Review Agent**: 1 名 (Claude Code、既存 `infer.py` / `infer_onnx.py` との構造差異確認)
  - `infer_onnx.py` 側は Phase 2 で別途対応するため、本チケットでは触らない

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| 修正済み infer.py | `src/python/piper_train/infer.py` |
| `_style_vector_to_tensor` helper | `infer.py` 内 (private) |

**提供範囲外**:
- `infer_onnx.py` への統合 (Phase 2 で ONNX 側対応として実装)
- C++/Rust/C#/Go/WASM などの他ランタイム対応 (Phase 2)
- Style bank からの query (Phase 3)

## 5. テスト項目

### 5.1 Unit テスト (P1-T06 で実装)

- `test_style_vector_to_tensor_npy`: .npy ファイルから読み込み成功
- `test_style_vector_to_tensor_pt`: .pt ファイルから読み込み成功
- `test_style_vector_to_tensor_inline`: カンマ区切り文字列から parse
- `test_style_vector_to_tensor_none`: None 入力で None 出力
- `test_style_vector_to_tensor_invalid_raises`: 不正フォーマットで ValueError

### 5.2 E2E テスト (本チケットのスモーク)

- `python -m piper_train.infer --help | grep style-vector` でヘルプ表示確認
- 既存 6lang モデル (`style_vector_dim=0`) で `--style-vector` 未指定時の推論が動くこと (regression check)
- `echo '{"phoneme_ids": [1, 8, 5, 39, 3, 2]}' | python -m piper_train.infer --model ... ` 基本パスが壊れていないこと

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **既存モデルでの引数互換**: `style_vector_dim=0` モデル (現行 6lang) で `--style-vector` 指定時、SynthesizerTrn 側で ignore されるか明示エラーかの挙動。fork 実装に準拠
- **batch 次元の扱い**: 1 発話ずつ推論する場合は `.unsqueeze(0)` で batch dim 追加必要。複数発話をまとめる場合は同じ style_vector を broadcast
- **device/dtype mismatch**: CUDA model に CPU tensor を渡すと実行時エラー。`.to(device, dtype)` を確実に呼ぶ
- **inline 記法の安全性**: `","` 区切り文字列のパースで float 変換失敗時の ValueError を明示
- **fork との差異**: fork が GPU device 対応に追加修正を入れていれば、本家の既存 GPU 対応状況に合わせて調整

### 6.2 レビュー項目

- [ ] `_style_vector_to_tensor` が npy/pt/inline を正しく扱える
- [ ] `--style-vector` 未指定時は既存挙動と等価 (regression なし)
- [ ] device/dtype が model と一致
- [ ] エラーメッセージが明示的 (ファイル未存在、形式不明)
- [ ] `infer_onnx.py` に影響を与えていない (Phase 2 で別途対応)
- [ ] batch 次元の扱いが docstring で明記

## 7. 一から作り直すとしたら

- **代替案 A**: `--style-vector` ではなく `--style-vector-path` と `--style-vector-inline` を分離
  - メリット: 入力タイプが明示的、parsing ロジックが単純化
  - デメリット: CLI オプション数増、fork との diff 増加
- **代替案 B**: inline 記法を廃止し、ファイル指定のみに制限
  - メリット: パース安全性向上
  - デメリット: デバッグ時の手軽さ喪失
- **代替案 C**: Style bank 統合を早期に導入 (`--style-key EMOTION` で bank から選択)
  - メリット: ユーザフレンドリ
  - デメリット: Phase 3 の Style bank 仕様に依存、Phase 1 スコープ外

**採用理由**: fork 実装との diff 最小化、ユーザのデバッグ時の柔軟性維持 (inline 記法)。代替案 A は Phase 2 以降で他ランタイム対応時に再検討。

## 8. 後続タスクへの連絡事項

- **P1-T06 へ**: `_style_vector_to_tensor` は private ヘルパーだがテストから `from piper_train.infer import _style_vector_to_tensor` で import 可能にすること
- **Phase 2 へ (ONNX 推論)**: `infer_onnx.py` / `infer.py` (ランタイム側) / 他ランタイム (C++/Rust/C#/Go/WASM) に同等機能を追加する必要あり。本チケットの `_style_vector_to_tensor` のロジックを参考にすること
- **Phase 3 へ (Style bank)**: Style bank (`emotion` → `vector` の mapping JSON) からの query を `--style-key` CLI として追加予定。その際、本チケットの `--style-vector` と共存させる

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- phase-0-1.md §1.2-F `src/python/piper_train/infer.py`
- phase-0-1.md §1.4 Patch 6: `infer.py`
- Phase 2 計画: `docs/research/implementation-plan/phase-2.md` (ONNX 側統合予定)
- Phase 3 計画: `docs/research/implementation-plan/phase-3-4.md` (Style bank 予定)
