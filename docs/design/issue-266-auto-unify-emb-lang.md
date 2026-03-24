# Issue #266: export_onnx で emb_lang 自動統一

## 概要

シングルスピーカー多言語モデルのONNXエクスポート時に、`emb_lang` の声質統一を自動化する。

**Issue**: https://github.com/ayutaz/piper-plus/issues/266

---

## 背景と問題

### 現状の2段階ワークフロー

多言語ベースモデル（571話者, 6言語）から単一話者（つくよみちゃん等）へ転移学習する場合、以下の2段階が必要:

1. **学習時**: `--resume-from-multispeaker-checkpoint` で全言語の `emb_lang` を保持（凍結DPが正しいconditioningを受け取るため）
2. **後処理（手動）**: ONNXエクスポート前に `emb_lang[0]` → `emb_lang[1:N]` にコピーして声質統一

### 問題点

ステップ2が手動のPythonスクリプト実行を必要とする:

```python
ckpt = torch.load("checkpoint.ckpt", map_location="cpu")
sd = ckpt["state_dict"]
emb_lang = sd["model_g.emb_lang.weight"]
emb_lang[1:] = emb_lang[0].unsqueeze(0).expand_as(emb_lang[1:])
torch.save(ckpt, "checkpoint-fixed.ckpt")
```

ドキュメント（CLAUDE.md, training-guide.md）に記載されているが、知らないユーザーにとって使いづらい。

---

## 調査結果

### 1. `export_onnx.py` の変更前の状態

| 項目 | 詳細 |
|------|------|
| ファイル | `src/python/piper_train/export_onnx.py` |
| 既存CLI引数 | `checkpoint`, `output`, `--debug`, `--simplify`, `--simplify-only`, `--stochastic/--no-stochastic`, `--no-fp16` |
| emb_lang処理 | **なし** |

**エクスポートフロー:**
```
checkpoint読込 → EMA適用(デコーダのみ) → weight_norm除去 → forward置換
  → torch.onnx.export() → ONNX簡略化(opt) → FP16変換
```

### 2. `emb_lang` の構造

| 項目 | 詳細 |
|------|------|
| 定義 | `nn.Embedding(n_languages, gin_channels=512)` |
| 場所 | `vits/models.py:847` |
| 条件 | `n_languages > 1` の場合のみ作成 |
| 使い方 | `_get_global_conditioning()` で `emb_g(sid) + emb_lang(lid)` として加算結合 |
| state dictキー | `model_g.emb_lang.weight` |
| EMA対象 | **対象外**（EMAはデコーダ `model_g.dec` のみ追跡） |

**`_get_global_conditioning()` の実装 (`models.py:849-870`):**
```python
def _get_global_conditioning(self, sid=None, lid=None):
    g = None
    if self.n_speakers > 1 and sid is not None:
        g = self.emb_g(sid).unsqueeze(-1)        # [batch, 512, 1]
    if self.n_languages > 1 and lid is not None:
        lang_emb = self.emb_lang(lid).unsqueeze(-1)  # [batch, 512, 1]
        g = (g + lang_emb) if g is not None else lang_emb
    return g
```

### 3. シングルスピーカー多言語モデルの判定

以下の条件で自動判定可能:

```python
num_speakers = model_g.n_speakers   # <= 1
num_languages = getattr(model_g, "n_languages", 1)  # > 1
is_single_speaker_multilingual = (num_speakers <= 1) and (num_languages > 1)
```

config.json からも判定可能:
- `num_speakers` フィールド（= 1）
- `num_languages` フィールド（> 1）
- `language_id_map` フィールドの存在

### 4. 学習時の `emb_lang` 処理 (`__main__.py:500-555`)

`--resume-from-multispeaker-checkpoint` 使用時:

1. `strict=False` でcheckpoint読込（`emb_g` は自動スキップ）
2. `emb_g_mean`（全話者の平均embedding）を全 `emb_lang` 行に加算（conditioning分布補正）
3. 全言語の `emb_lang` をそのまま保持（凍結DPが正しいconditioningを受け取るため）

**設計根拠**: 学習時にコピーすると凍結DPが誤った duration を予測する。エクスポート時のコピーが最も安全。

### 5. EMA との関係

| コンポーネント | EMA対象? | 備考 |
|--------------|---------|------|
| デコーダ (model_g.dec) | **YES** | HiFi-GAN vocoder |
| emb_lang | **NO** | グローバルconditioning |
| emb_g | **NO** | グローバルconditioning |
| Duration Predictor | **NO** | freeze-dpで凍結可能 |

→ emb_lang修正はEMA適用の前でも後でも問題なし。ただし `torch.onnx.export()` の前に行う必要がある。

### 6. FP16変換との関係

FP16変換はパイプラインの最終ステップ:

```
[emb_lang統一] → torch.onnx.export() → ONNX簡略化(opt) → FP16変換
```

emb_langの統一はPyTorchモデルのweightレベルで行うため、FP16変換より前。影響なし。

### 7. argparse パターン

コードベースで使用されている2つのパターン:

| パターン | 使用例 | 特徴 |
|---------|-------|------|
| `BooleanOptionalAction` | `--stochastic`, `--energy-vad` | `--flag` と `--no-flag` を自動生成 |
| `store_true` | `--no-fp16`, `--no-wavlm` | `--no-` prefix付きで無効化のみ |

**推奨**: `--unify-emb-lang` には `BooleanOptionalAction` を使用。

### 8. C#/Rust 推論エンジンへの影響

| エンジン | 影響 | 理由 |
|---------|------|------|
| C# (PiperSession.cs) | **なし** | `lid` をint64テンソルとしてONNX Runtimeに渡すだけ |
| Rust (engine.rs) | **なし** | 同上 |
| Python (infer_onnx.py) | **なし** | 同上 |

embedding lookupはONNXグラフ内部で処理される。emb_langの「値」が変わるだけで、インターフェース・テンソル形状は不変。

### 9. テスト構造

| ファイル | 行数 | 内容 |
|---------|------|------|
| `test_export_onnx.py` | 168 | deterministic/stochastic ONNX, EMAテスト |
| `conftest.py` | 319 | `mock_vits_model`, `temp_onnx_model` フィクスチャ |

新テストの追加方針:
- `conftest.py` の `mock_vits_model` を活用（`num_languages=2` で作成可能）
- `emb_lang` 統一前後のweight比較
- auto判定ロジックのテスト

---

## 提案する実装

### 新規CLI引数

```python
parser.add_argument(
    "--unify-emb-lang",
    action=argparse.BooleanOptionalAction,
    default=None,  # None = auto
    help="Unify emb_lang embeddings for single-speaker multilingual models. "
    "Default: auto (enabled when num_speakers <= 1 and num_languages > 1). "
    "Use --no-unify-emb-lang to disable.",
)
parser.add_argument(
    "--unify-emb-lang-source",
    type=int,
    default=0,
    help="Source language index for emb_lang unification (default: 0 = JA).",
)
```

### 実装フロー

```python
# export_onnx.py 内、VitsModel.load_from_checkpoint() の後、torch.onnx.export() の前

# 1. 自動判定
if args.unify_emb_lang is None:
    # auto: シングルスピーカー多言語モデルの場合のみ有効化
    should_unify = (num_speakers <= 1) and (num_languages > 1)
else:
    should_unify = args.unify_emb_lang

# 2. emb_lang 統一
if should_unify and num_languages > 1:
    source = args.unify_emb_lang_source
    assert 0 <= source < num_languages, f"--unify-emb-lang-source must be 0..{num_languages-1}"

    with torch.no_grad():
        emb_lang = model_g.emb_lang.weight  # [num_languages, gin_channels]
        source_emb = emb_lang[source].clone()
        for i in range(num_languages):
            if i != source:
                emb_lang[i].copy_(source_emb)

    _LOGGER.info(
        "Unified emb_lang: copied lang[%d] → lang[0:%d] (%d languages)",
        source, num_languages, num_languages,
    )
```

### 挿入位置

```
VitsModel.load_from_checkpoint()          ← 既存
  ↓
model_g = model.model_g                   ← 既存
num_speakers, num_languages 取得           ← 既存
  ↓
★ emb_lang 統一処理 (新規)                 ← ここに挿入
  ↓
EMA state 適用                            ← 既存（デコーダのみ、emb_langに影響なし）
  ↓
remove_weight_norm()                      ← 既存
  ↓
torch.onnx.export()                       ← 既存
  ↓
FP16変換                                  ← 既存
```

### テスト計画

1. **auto判定テスト**: `num_speakers=1, num_languages=2` → 自動有効化
2. **auto判定テスト**: `num_speakers=2, num_languages=2` → 自動無効化
3. **明示的有効化テスト**: `--unify-emb-lang` でマルチスピーカーでも有効化
4. **明示的無効化テスト**: `--no-unify-emb-lang` でシングルスピーカー多言語でも無効化
5. **source指定テスト**: `--unify-emb-lang-source 1` で英語基準のコピー
6. **weight検証**: 統一後に全言語のembeddingが同一であることを確認
7. **ONNX出力検証**: 統一後のモデルが正常にONNXエクスポートできることを確認

---

## 関連ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/export_onnx.py` | CLI引数追加 + emb_lang統一ロジック |
| `src/python/tests/test_export_onnx.py` | テスト追加 |
| `docs/guides/training/training-guide.md` | 手動ステップの記述を更新 |
| `CLAUDE.md` | 2段階方式の記述を更新 |
