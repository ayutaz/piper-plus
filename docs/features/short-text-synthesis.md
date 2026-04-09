# Short Text Synthesis Quality Issue

## Overview

極端に短いテキスト (1-2文節程度) を入力すると、合成音声が崩れる (ノイズ・歪み) か、0秒の音声が出力される問題が報告されている。これは VITS アーキテクチャの構造的制限に起因する既知の問題であり、Piper 本家 ([rhasspy/piper#252](https://github.com/rhasspy/piper/issues/252)) や Coqui TTS ([coqui-ai/TTS#3451](https://github.com/coqui-ai/TTS/discussions/3451)) でも同様に報告されている。

### Reported Symptoms

| 入力テキスト | 症状 |
|-------------|------|
| 「こんにちは、世界！今日はいい天気ですね。」 | 正常に合成 |
| 「おはようございます。本日の会議は午後3時から始まります。」 | 正常に合成 |
| 「こんにちは、世界！」 | ノイズ・歪み |
| 「おはようございます。」 | ノイズ・歪み |
| 「こんにちは。」 | 0秒の音声 |
| 「おはよう。」 | 0秒の音声 |

- モデル: piper-plus-css10-ja-6lang
- Speaker ID やパラメータを変更しても改善しない

---

## Root Cause Analysis

### 1. Stochastic Duration Predictor の不安定性

VITS の推論パスでは、`StochasticDurationPredictor` が各音素の持続時間 (duration) を予測する。この予測器は reverse-mode flow を使用しており、内部でランダムノイズ (`noise_scale_w`, デフォルト 0.8) を注入する。

```
入力音素列 → TextEncoder → Duration Predictor → duration予測 → Decoder → 音声
```

短いシーケンスでは:
- **文脈情報が不足** — Self-Attention と畳み込みの受容野が十分に活用されない
- **ノイズの相対的影響が増大** — 音素数が少ないため、確率的変動が結果を大きく左右する
- **音素スキップ (phoneme skipping)** が発生しやすくなる

### 2. Duration 値が極端に小さくなるケース

Duration Predictor が各音素に対して非常に小さい値を予測した場合:

```python
# models.py L1017-1019
w = torch.exp(logw) * x_mask * length_scale
w_ceil = torch.ceil(w)
y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
```

- `clamp_min(..., 1)` により 0秒 (0フレーム) は防止される
- しかし `ceil(0.01) = 1` なので、全音素が最小 1 フレームに丸められることがある
- 例: 5音素 × 1フレーム = 5フレーム → HiFi-GAN で 5 × 256 = 1,280 サンプル → 22,050 Hz で **0.058秒** (人間には聞こえない)

### 3. HiFi-GAN Decoder の振る舞い

Decoder は ConvTranspose1d で 256 倍にアップサンプリングする (stride = 8 × 8 × 4)。

| 潜在フレーム数 | 出力サンプル数 | 秒数 (22,050 Hz) |
|--------------|-------------|-----------------|
| 1 | 256 | 0.012s |
| 2 | 2,048 | 0.093s |
| 5 | 1,280 | 0.058s |
| 10 | 2,560 | 0.116s |
| 50 | 12,800 | 0.581s |

極端に短い潜在フレーム数では、Decoder が意味のある波形を生成できない。

### 4. 現状の保護機構

| 機構 | 場所 | 効果 | 限界 |
|------|------|------|------|
| `clamp_min(y_lengths, 1)` | `models.py` L1019 | 0フレーム出力を防止 | 「極端に短い」は防げない |
| Interspersed PAD | 各ランタイム | 音素列を若干延長 | 多言語モデルのみ |
| 空チェック | Rust/C#/Go | 空入力を拒否 | 最小推奨長チェックなし |

### 5. ランタイム別の最小長チェック状況

| ランタイム | 空チェック | 最小長チェック | scales 動的調整 |
|----------|----------|-------------|---------------|
| Python | - | - | - |
| Rust | `phoneme_len == 0` → Error | - | - |
| C# | `Length == 0` → 空配列 | - | - |
| C++ | - | - | - |
| Go | `len == 0` → Error | - | - |

---

## Mitigation Strategies

根本解決は VITS アーキテクチャの制約上困難だが、以下の緩和策を組み合わせることで実用上の品質を改善できる。

### Strategy A: Silence Padding + Post-trim (推奨, 効果: 高)

音素列が閾値未満の場合にサイレンス音素を前後に挿入し、生成後に無音をトリムする。

**メリット**: モデル再学習不要、全ランタイムに適用可能、ユーザーから透過的
**デメリット**: トリム精度に依存、わずかな無音が残る可能性

```
[原文] → "こんにちは。"
[補正] → "......こんにちは。......"  (サイレンス音素を前後に追加)
[合成] → [silence][speech][silence]
[trim] → [speech]                    (前後の無音を除去)
```

**実装方針**:
- 各ランタイムの推論入口で `phoneme_ids` の長さを判定
- 閾値 (例: `MIN_PHONEME_IDS = 40`) 未満なら、BOS の直後と EOS の直前にポーズ音素を挿入
- 合成後にエネルギーベース VAD で先頭・末尾の無音をトリム
- 閾値はモデルの `config.json` に `min_phoneme_ids` として設定可能にする

### Strategy B: Dynamic Scales Adjustment (推奨, 効果: 中)

音素数が少ない場合に `noise_scale` と `noise_w` を自動的に下げ、Duration Predictor の確率的変動を抑制する。

**メリット**: 実装が簡単、モデル変更不要
**デメリット**: 確定的になりすぎると不自然な音声になる可能性

```python
# 音素数に応じたスケール調整の例
if len(phoneme_ids) < 40:
    ratio = len(phoneme_ids) / 40  # 0.0 ~ 1.0
    noise_scale = noise_scale * max(0.5, ratio)   # 0.667 → 0.33~0.667
    noise_w = noise_w * max(0.4, ratio)            # 0.8 → 0.32~0.8
```

### Strategy C: SSML `<break>` Auto-injection (効果: 中)

既存の SSML インフラを活用し、短いテキストの前後に `<break>` を自動挿入する。

**メリット**: 4ランタイム (Python/Rust/C#/Go) の既存 SSML パーサーをそのまま活用
**デメリット**: SSML 非対応のランタイム (C++/WASM) には適用不可

```xml
<!-- 自動変換 -->
<speak><break time="300ms"/>こんにちは。<break time="300ms"/></speak>
```

### Strategy D: Duration Minimum Clamp (効果: 高, 要モデル再エクスポート)

`models.py` の推論パスで各音素の最小持続時間を保証する。

**メリット**: 確実に短すぎる出力を防止
**デメリット**: ONNX モデルの再エクスポートが必要、既存配布モデルには適用不可

```python
# models.py L1017-1019 の修正案
w = torch.exp(logw) * x_mask * length_scale
w = torch.clamp_min(w, 1.0)  # 各音素最小 1 フレーム保証 (ceil 前)
w_ceil = torch.ceil(w)
y_lengths = torch.clamp_min(torch.sum(w_ceil, [1, 2]), 1).long()
```

### Strategy E: WebUI / API Level Warning (効果: 低, UX改善)

短いテキスト入力時にユーザーへ警告を表示する。

**メリット**: 実装が非常に簡単
**デメリット**: 問題自体は解決しない

---

## Recommended Approach

**Strategy A + B の組み合わせ** を推奨する。

1. 各ランタイムの推論入口で音素列の長さを判定
2. 閾値未満なら `noise_scale` / `noise_w` を自動低減 (Strategy B)
3. さらに短い場合はサイレンスパディング + 後処理トリム (Strategy A)
4. 閾値はモデルの `config.json` に `min_phoneme_ids` として設定可能にする

### Implementation Priority

| ランタイム | 優先度 | 理由 |
|----------|-------|------|
| Python | P0 | WebUI / OpenAI API で直接利用される |
| Rust | P1 | CLI / PyO3 バインディング経由で利用 |
| C# | P1 | Unity 統合経由で利用 |
| Go | P2 | HTTP サーバー経由で利用 |
| C++ | P2 | C API / libpiper_plus 経由で利用 |
| WASM | P3 | ブラウザ利用 |

---

## Prior Art

| プロジェクト | Issue | 対応状況 |
|------------|-------|---------|
| rhasspy/piper | [#252](https://github.com/rhasspy/piper/issues/252) | Open (未対応) |
| coqui-ai/TTS | [#3451](https://github.com/coqui-ai/TTS/discussions/3451) | `spec_segment_size` 縮小が提案されたが根本解決に至らず |
| coqui-ai/TTS | [#3031](https://github.com/coqui-ai/TTS/discussions/3031) | ノイズ・歪み問題の議論 |
| rhasspy/piper | [#296](https://github.com/rhasspy/piper/issues/296) | 単語スキップの報告 |

---

## Implementation Status

Strategy A (Silence Padding + Post-trim), B (Dynamic Scales), C (SSML `<break>` Auto-injection) の各ランタイムへの実装状況。

| ランタイム | Strategy A | Strategy B | Strategy C | テスト |
|----------|:---:|:---:|:---:|:---:|
| Python (runtime) | ✅ | ✅ | ✅ | ✅ |
| Python (infer_onnx) | ✅ | ✅ | N/A | ✅ |
| Rust | ✅ | ✅ | ✅ | ✅ |
| C# | ✅ | ✅ | ✅ | ✅ |
| Go | ✅ | ✅ | ✅ | ✅ |
| C++ | ✅ | ✅ | N/A | ✅ |
| WASM/JS | ✅ | ✅ | N/A | ✅ |

**凡例:** ✅ = 実装済み, - = 未実装, N/A = SSML 非対応のため対象外

> **Note:** C++, WASM/JS, infer_onnx は SSML パーサー未実装のため Strategy C は N/A。

---

## Configuration

設定仕様は `docs/spec/short-text-contract.toml` で定義。全ランタイムで同一パラメータを使用する。

主な設定項目:

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `min_phoneme_ids` | 40 | Silence Padding / Scales 調整の閾値 (音素数) |
| `padding.pause_token_id` | 0 | パディングに使用する音素 ID |
| `scales.noise_scale_min_ratio` | 0.5 | noise_scale の最小倍率 (Strategy B) |
| `scales.noise_w_min_ratio` | 0.4 | noise_w の最小倍率 (Strategy B) |
| `ssml_injection.silence_pad_ms` | 300 | SSML `<break>` 自動挿入時間 (Strategy C) |
| `trim.threshold_rms` | 0.01 | Post-trim の RMS 振幅閾値 (Strategy A) |

モデルの `config.json` に `min_phoneme_ids` を追加することで、モデルごとに閾値をカスタマイズ可能。

---

## User Guide

短テキスト合成で品質問題が発生した場合の回避策。

### 回避策 1: テキストの前後に文脈を追加

短いテキストの前後に句読点や文を追加することで、Duration Predictor の文脈情報を増やす。

```
# 短すぎる (品質低下の可能性)
こんにちは。

# 改善: 前後にテキストを追加
こんにちは。今日はいい天気ですね。
```

### 回避策 2: noise_scale / noise_w を手動で下げる

短いテキストでは確率的変動の影響が大きいため、手動でスケールを下げると安定する。

```bash
# Python
uv run python -m piper_train.infer_onnx \
  --model model.onnx --config config.json \
  --text "こんにちは。" \
  --noise-scale 0.3 --noise-w 0.4

# Rust
piper-plus --model model.onnx \
  --noise-scale 0.3 --noise-w 0.4 \
  "こんにちは。"
```

### 回避策 3: SSML の `<break>` を手動で使う

SSML 対応ランタイム (Python/Rust/C#/Go) では、`<break>` タグで前後に無音を挿入できる。

```xml
<speak>
  <break time="300ms"/>
  こんにちは。
  <break time="300ms"/>
</speak>
```

### モデルごとの推奨最小文字数

| モデル | 推奨最小文字数 | 備考 |
|--------|-------------|------|
| piper-plus-base (6lang) | 5文字以上 | 3文字以下でノイズ発生の可能性 |
| piper-plus-tsukuyomi | 5文字以上 | ファインチューニングモデル、ベースと同傾向 |
| CSS10 JA | 5文字以上 | 転移学習モデル |

> **Note:** 上記は目安。言語やテキスト内容により変動する。英語の場合は3単語以上が推奨。

---

## References

- [VITS: Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech](https://arxiv.org/abs/2106.06103) (Kim et al., 2021)
- [VITS2: Improving Quality and Efficiency of Single-Stage Text-to-Speech with Adversarial Learning and Architecture Design](https://arxiv.org/abs/2307.16430) (Kong et al., 2023)
