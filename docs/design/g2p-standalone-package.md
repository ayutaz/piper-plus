# G2P 独立パッケージ化 調査レポート

> 調査日: 2026-03-31

> **ステータス: 全 Phase 実装完了 (2026-04-01)**
> - Phase 0 (Python MVP): ✅ 完了
> - Phase 1 (全言語): ✅ 完了
> - Phase 2 (Rust crate): ✅ 完了
> - Phase 3 (JS/WASM): ✅ 完了

Piper Plus の G2P (Grapheme-to-Phoneme) コンポーネントを、他の TTS システムから利用しやすい独立パッケージとして切り出す構想の調査結果。

---

## 背景

多くの OSS TTS が eSpeak-ng (GPL-3.0) に依存しており、ライセンス問題・ビルド困難・日本語非対応といった課題を抱えている。Piper Plus は eSpeak-ng を使わず 6 言語の G2P を 4 つのランタイム (Python / C# / Rust / JS-WASM) で独自実装しており、これを独立パッケージとして提供する需要があるか調査した。

---

## 1. 需要分析

### 1.1 需要の 4 軸

| 軸 | 根拠 |
|----|------|
| **GPL 回避** | eSpeak-ng / phonemizer (GPL-3.0) は商用 TTS の最大障壁。Coqui TTS, StyleTTS 2, GPT-SoVITS 等の Issues で繰り返し問題に。Kokoro は Misaki を独自開発して脱却済み |
| **マルチ言語統一 API** | gruut (MIT) がこのポジションを狙ったがメンテナンス停滞。6 言語以上をカバーするライセンスクリーンな G2P は空白地帯 |
| **日本語 G2P** | pyopenjtalk は C++ ビルド依存が重い (Windows / ARM Mac でトラブル多発)。WASM / ブラウザで動く日本語 G2P の選択肢がほぼない |
| **デプロイ容易性** | Windows での eSpeak-ng ビルド失敗が最頻出 Issue。pip install だけで動く G2P への需要が高い |

### 1.2 主要 TTS の G2P 実装状況

| TTS フレームワーク | G2P 方式 | ライセンス問題 | 日本語対応 |
|-------------------|---------|--------------|-----------|
| VITS / VITS2 | eSpeak-ng | GPL 汚染 | なし |
| Coqui TTS | eSpeak-ng (phonemizer 経由) | GPL 汚染 | 限定的 |
| StyleTTS 2 | eSpeak-ng | GPL 汚染 | なし |
| Fish Speech | 言語別独自実装 | クリーン | あり |
| GPT-SoVITS | eSpeak-ng + pypinyin + pyopenjtalk | GPL 混在 | あり |
| Kokoro | Misaki (Apache-2.0) | クリーン | あり (2025~) |
| MeloTTS | eSpeak-ng + 言語別 | GPL 汚染 | 限定的 |
| **Piper Plus** | **独自実装 (MIT)** | **クリーン** | **あり (高品質)** |

### 1.3 競合状況

| 競合 | 対応言語数 | ライセンス | ランタイム | 状態 |
|------|-----------|----------|-----------|------|
| **Misaki** (Kokoro) | 2 (EN + JA) | Apache-2.0 | Python のみ | 活発、ただし言語少 |
| **gruut** | ~20 | MIT | Python のみ | メンテナンス停滞 (2022~) |
| **phonemizer** | eSpeak-ng 依存 | GPL-3.0 | Python のみ | GPL のため商用不可 |
| **deep-phonemizer** | 数言語 | MIT | Python のみ | ニューラルベースで重い |
| **Piper Plus G2P** | **6** | **MIT / Apache** | **Python / C# / Rust / WASM** | 活発 |

### 1.4 差別化ポイント

1. **6 言語 (JA, EN, ZH, ES, FR, PT) + ライセンスクリーン**: Misaki (2 言語) や gruut (JA なし) に対して明確な優位性
2. **4 ランタイム実装**: サーバー (Python/Rust)、デスクトップ (C#)、ブラウザ (WASM) の全デプロイ先をカバー。唯一無二
3. **日本語 G2P の品質**: OpenJTalk ベースの prosody features (A1/A2/A3)、文脈依存 N 音素変異 (N_m/N_n/N_ng/N_uvular)、疑問詞マーカー拡張
4. **実戦検証済み**: 508,187 発話の多言語学習で使用・検証されたプロダクション品質
5. **C++ / eSpeak-ng ビルド不要**: Pure Python / Pure Rust / Pure C# で動作

### 1.5 想定ユーザー層

| ユーザー層 | 規模感 | 主なニーズ |
|-----------|--------|-----------|
| マルチリンガル TTS 開発者 | 中 (数百~数千人) | eSpeak-ng 置き換え、統一 API |
| 日本語 TTS 開発者 | 中 (国内中心) | pyopenjtalk 代替、ビルド不要 |
| 商用 TTS 製品開発者 | 小~中 | GPL 回避、組み込み可能なライセンス |
| ブラウザ TTS 開発者 | 小~中 (成長中) | WASM 対応 G2P、オフライン TTS |
| TTS 研究者 | 中 | 再現性のある多言語音素化 |

---

## 2. アーキテクチャ現状分析

### 2.1 プラットフォーム別結合度

| プラットフォーム | コード量 | 推論との結合度 | 独立パッケージ化 | 推定工数 |
|----------------|---------|-------------|----------------|---------|
| **Python** | ~300 LOC | 低 | 容易 | 1-2 週 |
| **Rust** | ~11,200 LOC | 低 | 容易 | 1-2 週 |
| **C#** | ~3,500 LOC | 低 | 容易 | 2-3 週 |
| **JS/WASM** | ~16,000 LOC | **高** | 困難 | 3-4 週 |

### 2.2 Python (`src/python/piper_train/phonemize/`)

**現状**: G2P コンポーネントは piper_train の他モジュール (学習、推論、データセット準備) に依存していない。既にほぼ独立。

**API**:
```python
from piper_train.phonemize.registry import get_phonemizer
phonemizer = get_phonemizer("ja")
tokens, prosody = phonemizer.phonemize_with_prosody(text)
```

**切り出しに必要な作業**:
- パッケージメタデータ (pyproject.toml) の整備
- 言語別の optional 依存整理 (pyopenjtalk, g2p-en, pypinyin 等)
- `custom_dict.py` のパス依存を相対パス化

### 2.3 Rust (`src/rust/piper-core/src/phonemize/`)

**現状**: `config::PhonemeIdMap` と `error::PiperError` への最小限の依存のみ。feature flag (`#[cfg(feature = "japanese")]`) で言語別にオプション化済み。

**API**:
```rust
let (tokens, prosody) = phonemizer.phonemize_with_prosody(text)?;
```

**切り出しに必要な作業**:
- `PhonemeIdMap` 型を軽量型に変更
- `PiperError` を汎用 Error trait に変更
- 新 crate `piper-g2p` を作成し既存コードを移動

### 2.4 C# (`src/csharp/PiperPlus.Core/Phonemize/`)

**現状**: G2P エンジンがインターフェース分離済み (`IJapaneseG2PEngine`, `IEnglishG2PEngine` 等)。ONNX 推論との結合度は低い。

**API**:
```csharp
var phonemizer = new JapanesePhonemizer(engine);
var (tokens, prosody) = phonemizer.PhonemizeWithProsody(text);
```

**切り出しに必要な作業**:
- `PiperPlus.Core.Mapping` への依存を分離
- G2P エンジン実装を独立アセンブリ化
- NuGet パッケージ (`PiperPlus.Phonemize`) の設定

### 2.5 JS/WASM (`src/wasm/openjtalk-web/src/`)

**現状**: `SimpleUnifiedPhonemizer` クラスは概念的に独立だが、OpenJTalk WASM 初期化・辞書ダウンロード・IndexedDB キャッシュ・推論パイプラインと強く結合。

**切り出しに必要な作業**:
- `SimpleUnifiedPhonemizer` を独立クラスに分離
- OpenJTalk WASM 初期化を外部注入可能に
- `DictManager` の分離
- `PiperPlus.synthesize()` を `phonemize()` / `synthesize()` / `text_to_speech()` に分割

---

## 3. 依存ライセンス分析

### 3.1 GPL 汚染リスク: **ゼロ**

全依存が MIT / Apache-2.0 / BSD-3-Clause。商用利用・プロプライエタリ化ともに可能。

### 3.2 Python 依存

| パッケージ | ライセンス | 対象言語 | G2P 切り出し時 |
|-----------|----------|---------|--------------|
| `pyopenjtalk-plus` / `pyopenjtalk` | BSD-3-Clause | JA | 必須 |
| `g2p-en` (>=2.1.0) | Apache-2.0 | EN | 必須 |
| `pypinyin` (>=0.50) | MIT | ZH | 必須 |
| `g2pk2` (>=0.0.3) | Apache-2.0 | KO | 必須 |
| (なし -- ルールベース) | - | ES, FR, PT | 外部依存なし |

### 3.3 C# 依存

| パッケージ | バージョン | ライセンス |
|-----------|-----------|----------|
| `DotNetG2P` | 1.8.0 | Apache-2.0 |
| `DotNetG2P.MeCab` | 1.8.0 | Apache-2.0 |
| `DotNetG2P.English` | 1.8.0 | Apache-2.0 |
| `DotNetG2P.Chinese` | 1.7.0 | Apache-2.0 |
| `DotNetG2P.Spanish` | 1.7.0 | Apache-2.0 |
| `DotNetG2P.French` | 1.7.0 | Apache-2.0 |
| `DotNetG2P.Portuguese` | 1.7.0 | Apache-2.0 |

### 3.4 Rust 依存

| Crate | ライセンス | 用途 |
|-------|----------|------|
| `jpreprocess` 0.9 | MIT | JA 前処理 (OpenJTalk 互換) |
| `regex` 1 | Apache-2.0 OR MIT | 正規表現 |

### 3.5 JS/WASM 依存

| コンポーネント | ライセンス | 形態 |
|-------------|----------|------|
| OpenJTalk | BSD-3-Clause | WASM 静的リンク |
| HTS Engine API | BSD-3-Clause | WASM 内包 |
| MeCab | BSD-3-Clause | WASM 内包 |
| NAIST-jdic | BSD-3-Clause | 実行時ダウンロード |
| `onnxruntime-web` | MIT | peerDependency |

---

## 4. 推奨ロードマップ

### Phase 1: Python + Rust (最優先)

| 項目 | 内容 |
|------|------|
| **目標** | `piper-g2p` (PyPI) + `piper-g2p` (crates.io) を公開 |
| **工数** | 2-3 週 |
| **効果** | 最も需要の高い Python / Rust ユーザーをカバー |

**Python パッケージ構成案**:
```
piper-g2p
├── piper_g2p/
│   ├── __init__.py        # get_phonemizer(), list_languages()
│   ├── base.py            # Phonemizer ABC, ProsodyInfo
│   ├── registry.py        # 言語レジストリ
│   ├── japanese.py
│   ├── english.py
│   ├── chinese.py
│   ├── korean.py
│   ├── spanish.py
│   ├── portuguese.py
│   ├── french.py
│   ├── multilingual.py
│   ├── token_mapper.py
│   └── *_id_map.py
└── pyproject.toml         # 言語別 optional deps
```

**Rust crate 構成案**:
```
piper-g2p
├── src/
│   ├── lib.rs             # Phonemizer trait, registry
│   ├── japanese.rs
│   ├── english.rs
│   ├── chinese.rs
│   ├── korean.rs
│   ├── spanish.rs
│   ├── portuguese.rs
│   ├── french.rs
│   ├── multilingual.rs
│   └── token_map.rs
└── Cargo.toml             # feature flags per language
```

### ~~Phase 2: C# NuGet パッケージ~~ → 対象外

DotNetG2P (NuGet) が既に独立 G2P パッケージとして公開済みのため不要。

### Phase 2: JS/WASM リファクタリング (旧 Phase 3)

| 項目 | 内容 |
|------|------|
| **目標** | G2P レイヤーを推論パイプラインから分離、`@piper-plus/g2p` として公開 |
| **工数** | 3-4 週 |
| **効果** | ブラウザ TTS 開発者をカバー |

### 合計工数: 約 5-7 週 (C# 対象外により削減)

Phase 1 (Python + Rust) だけで最大のインパクトを得られるため、段階的リリースを推奨。

---

## 5. 結論

- **需要**: GPL 回避、マルチ言語統一 API、日本語 G2P、デプロイ容易性の 4 軸で明確に存在
- **競合優位性**: 6 言語 x 4 ランタイム x ライセンスクリーン x 日本語高品質は唯一無二のポジション
- **実現可能性**: Python / Rust は既にアーキテクチャ上ほぼ独立しており、切り出し工数は小さい
- **ライセンスリスク**: ゼロ (全依存が MIT / Apache-2.0 / BSD-3-Clause)
- **推奨**: Phase 1 (Python + Rust) から着手し、需要を検証しながら段階的に展開
