---
name: check-runtime-parity
description: 推論パスの canonical Python (`export_onnx.py` / `vits/models.py:VitsModel.infer`) を変更した PR で、6 ランタイム (Python runtime / Rust / Go / C# / C++ / WASM) の inference path が追随しているかを git diff で確認。PR #391 (Python のみ speaker_embedding 修正) → PR #443 (4 ランタイム + docker 2 個に同じバグ発見) の silent regression を防ぐ。
disable-model-invocation: true
allowed-tools: Bash(git diff *) Bash(git status *) Bash(grep *) Bash(ls *)
---

<!-- editorconfig-checker-disable-file -->

# ランタイム推論 parity チェック

`src/python/piper_train/export_onnx.py` か `src/python/piper_train/vits/models.py`
の `VitsModel.infer` (ONNX グラフ入出力定義) を変更した PR で、他 5 ランタイムの
inference path も同じ変更を反映しているかを **PR 提出前に** 確認する。

## 何をチェックするか

PR #391 → PR #443 の事故パターン:

- PR #391 は Python ランタイムだけ `speaker_embedding` 形状を修正
- 他 5 ランタイム (Rust / Go / C# / C++ / WASM 推論) は古い形状のまま放置
- PR #443 で気付くまで **silent regression** 状態

このパターンを検出するため、**カノニカルファイル** が触られている PR で
他ランタイムの inference path も同 PR で触れているかを確認する:

| Canonical (Python) | 対応する他ランタイム file |
|---|---|
| `src/python/piper_train/export_onnx.py` | (ONNX export 自体は Python 専用、ただし出力スキーマを変える場合は下記の loader も更新必要) |
| `src/python/piper_train/vits/models.py:VitsModel.infer` | `src/python_run/piper/voice.py` (Python runtime) |
| ONNX グラフ入出力名 (`speaker_embedding` / `prosody_features` / `language_id`) | `src/rust/piper-core/src/engine.rs` (Rust) |
| 同上 | `src/go/piperplus/synth.go` (Go) |
| 同上 | `src/csharp/PiperPlus.Core/Inference/PiperSession.cs` (C#) |
| 同上 | `src/cpp/piper_plus.cpp` (C++) |
| 同上 | `src/wasm/openjtalk-web/src/index.js` または piper-wasm (WASM) |

## 実行手順

### 1. canonical ファイルが触られているか確認

```bash
CANONICAL_TOUCHED=$(git diff --name-only origin/dev...HEAD | \
  grep -E '^(src/python/piper_train/(export_onnx|vits/models)\.py)$')

if [ -z "$CANONICAL_TOUCHED" ]; then
  echo "canonical inference file は変更されていない — このチェックは skip 可"
  exit 0
fi

echo "Canonical 変更検出: $CANONICAL_TOUCHED"
```

### 2. 他 6 ランタイムの inference path も触られているか確認

```bash
RUNTIME_FILES=(
  "src/python_run/piper/voice.py"
  "src/rust/piper-core/src/engine.rs"
  "src/go/piperplus/synth.go"
  "src/csharp/PiperPlus.Core/Inference/PiperSession.cs"
  "src/cpp/piper_plus.cpp"
  "src/wasm/openjtalk-web/src/index.js"
)

echo "=== 他ランタイム inference path の touch 状況 ==="
for f in "${RUNTIME_FILES[@]}"; do
  if git diff --name-only origin/dev...HEAD | grep -q "^${f}$"; then
    echo "  TOUCHED  $f"
  else
    echo "  UNTOUCHED $f  ← 追随必要かもしれない"
  fi
done
```

### 3. ONNX 入出力名の変更ならスキーマ検査も走らせる

`speaker_embedding` / `prosody_features` / `language_id` 等の入出力名を追加・
削除・改名した場合は以下も実行:

```bash
# ONNX 入力契約の検査 (PR #443 で導入)
python scripts/check_onnx_inputs.py --strict

# 既存 parity gate
python scripts/check_voice_catalog_parity.py
python scripts/check_inference_input_contract.py
```

### 4. 必要なら他ランタイムを touch する PR を分割

UNTOUCHED な runtime が多いなら、**1 PR で全 6 ランタイムを揃える** か、
**「Python canonical → 他ランタイム追随」を 1 issue でリンク** にする。
silent regression を残さない。

## 確認すべき事項

- [ ] canonical Python の変更が ONNX 入出力グラフに影響する変更か (形状 / 名前 /
      dtype の変更) を把握
- [ ] 影響あるなら他 6 ランタイム inference path も同 PR で更新したか
- [ ] `scripts/check_onnx_inputs.py --strict` が pass
- [ ] `scripts/check_voice_catalog_parity.py` が pass
- [ ] `scripts/check_inference_input_contract.py` が pass
- [ ] PR description に「Python canonical 修正 + N 他ランタイム追随」を明記

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| canonical を触ったが他 runtime は触れていない | 「ONNX グラフは変えていない (内部リファクタのみ)」なら OK。グラフを変えたら他 runtime も追随必要 |
| `check_onnx_inputs.py --strict` が fail | 出力モデルの入出力 ports が `docs/spec/inference-input-contract.toml` と drift |
| 他 runtime を全部触るのが大きすぎる | Python と Rust/Go の 3 ランタイムだけ先に揃え、C# / C++ / WASM は follow-up PR を issue 化 |

## 関連ドキュメント

- [inference-input-contract.toml](docs/spec/inference-input-contract.toml)
- [model-resolution.md](docs/reference/model-resolution.md)
- [PR #391 / #443 の経緯] — silent regression の参考事例
