# Piper-Plus Rust 推論実装ガイド

本ドキュメントは Piper-Plus の推論パイプラインを Rust で実装するための調査結果と設計方針をまとめたものです。

---

## 目次

1. [概要](#概要)
2. [現在の推論パイプライン分析](#現在の推論パイプライン分析)
3. [技術スタック](#技術スタック)
4. [先行事例](#先行事例)
5. [アーキテクチャ設計](#アーキテクチャ設計)
6. [多言語対応](#多言語対応)
7. [言語別音素化の実装方針](#言語別音素化の実装方針)
8. [音声出力](#音声出力)
9. [パフォーマンス評価](#パフォーマンス評価)
10. [WASM/ブラウザ対応](#wasmブラウザ対応)
11. [ロードマップ](#ロードマップ)
12. [リスクと対策](#リスクと対策)
13. [参考リンク](#参考リンク)

---

## 概要

Piper-Plus の推論を Rust で実装することで、以下のメリットが得られる:

- **メモリ安全性**: ownership system によるコンパイル時保証
- **ビルド・配布の簡素化**: `cargo build` 一発、シングルバイナリ配布
- **クロスコンパイル容易**: `cargo build --target <triple>` で対応
- **PyO3 による Python バインディング**: C++ より容易に Python 高速化ライブラリを提供
- **crates.io 公開**: `cargo add piper-plus` でライブラリとして利用可能

ONNX Runtime 推論自体のパフォーマンスは C++ と同等 (同じ FFI 経由)。Python 比では 3-5x 高速、メモリ 60-80% 削減。

---

## 現在の推論パイプライン分析

### 全体フロー

```
テキスト入力
    |
    v
[言語別 Phonemizer (レジストリ経由)]
    |
    v
音素列 + プロソディ情報 (A1/A2/A3)
    |
    v
[phoneme_id_map で ID 変換]
    |
    v
phoneme_ids (Vec<i64>) + prosody_features (Vec<[i32;3]>)
    |
    v
[ONNX モデル推論]
    |
    v
float32 audio → int16 PCM → WAV 出力
```

### ONNX モデル入出力

#### 入力テンソル

| テンソル名 | 型 | 形状 | 必須 | 説明 |
|-----------|-----|------|------|------|
| `input` | int64 | `[1, phoneme_length]` | Yes | 音素 ID 列 |
| `input_lengths` | int64 | `[1]` | Yes | 音素列の長さ |
| `scales` | float32 | `[3]` | Yes | `[noise_scale, length_scale, noise_scale_w]` |
| `sid` | int64 | `[1]` | No | マルチスピーカー or 多言語モデル時の話者 ID |
| `lid` | int64 | `[1]` | No | 多言語モデル時の言語 ID (`num_languages > 1`) |
| `prosody_features` | int64 | `[1, phoneme_length, 3]` | No | A1/A2/A3 プロソディ値 |

デフォルトスケール値: `noise_scale=0.667`, `length_scale=1.0`, `noise_scale_w=0.8`

**テンソル順序** (ONNX グラフの入力順):
1. `input` → 2. `input_lengths` → 3. `scales` → 4. `sid` (条件付き) → 5. `lid` (条件付き) → 6. `prosody_features` (条件付き)

**条件判定**:
- `sid`: `num_speakers > 1` OR `num_languages > 1` のとき必須
- `lid`: `num_languages > 1` のとき必須
- `prosody_features`: `prosody_dim > 0` のとき必須

#### 出力テンソル

| テンソル名 | 型 | 形状 | 説明 |
|-----------|-----|------|------|
| `output` | float32 | `[1, 1, audio_samples]` | 生音声 (-1.0 ~ 1.0) |
| `durations` | float32 | `[1, phoneme_length]` | 各音素のフレーム数 (オプション) |

### 推論に必要な外部ファイル

- **ONNX モデル** (`.onnx`) — 約 74MB (medium quality, 20 speakers)
- **config.json** — `phoneme_id_map`, `num_speakers`, `sample_rate` 等を含む
- **辞書データ** (言語別) — CMU 辞書 (EN, 3.7MB), pypinyin 辞書 (ZH, 2.6MB)

config.json 検出順序:
1. `--config` で明示指定
2. `{model}.onnx.json` (C++ CLI convention)
3. `{model_dir}/config.json`

### config.json のスキーマ (多言語対応)

```json
{
  "audio": { "sample_rate": 22050 },
  "num_speakers": 571,
  "num_symbols": 173,
  "phoneme_type": "multilingual",
  "phoneme_id_map": { "^": [1], "_": [0], "a": [15], ... },
  "num_languages": 6,
  "language_id_map": {
    "ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5
  },
  "prosody_num_symbols": 11,
  "prosody_id_map": { "0": [0], "1": [1], ... }
}
```

`phoneme_type` の値:
- `"openjtalk"` — 日本語単言語 (BOS/EOS inline, パディングなし)
- `"bilingual"` — JA+EN バイリンガル (97 シンボル)
- `"multilingual"` — N 言語 (173 シンボル, インタースパースパディングあり)

### C++ 版と Python 版の機能差分

| 機能 | C++ | Python |
|------|-----|--------|
| ONNX 推論 | Yes | Yes |
| 日本語音素化 (OpenJTalk) | Yes | Yes |
| 英語音素化 (CMU 辞書) | Yes | Yes (g2p-en) |
| 中国語音素化 (pypinyin 辞書) | Yes | Yes |
| 韓国語音素化 (Hangul 分解) | Yes | Yes |
| スペイン語音素化 (ルールベース) | Yes | Yes |
| フランス語音素化 (ルールベース) | Yes | Yes |
| ポルトガル語音素化 (ルールベース) | Yes | Yes |
| Unicode 言語自動検出 | Yes | Yes |
| 多言語コードスイッチング | Yes | Yes |
| プロソディ (A1/A2/A3) | Yes | Yes |
| カスタム辞書 | Yes | No |
| ストリーミング推論 | Yes | No |
| phoneme timing 出力 | Yes | No |
| モデルダウンロード | Yes | Yes |
| `--text` 直接入力 | Yes | Yes |

---

## 技術スタック

### 推奨クレート

| 用途 | クレート | バージョン | ライセンス | 選定理由 |
|------|---------|-----------|-----------|---------|
| ONNX 推論 | `ort` | >=2.0 | MIT/Apache-2.0 | piper-rs 等で VITS 推論実績。全 ONNX op 対応。GPU 対応 |
| 日本語音素化 | `jpreprocess` | latest | MIT | Pure Rust OpenJTalk 互換。A1/A2/A3 取得可能 |
| ラベルパース | `jlabel` | latest | MIT | HTS fullcontext label の型付きパース |
| 中国語ピンイン | `pinyin` | latest | MIT | 漢字→ピンイン変換 (385K+ DL) |
| 韓国語 Hangul | `hangul` | latest | MIT | Hangul 音節→jamo 分解 |
| 英語辞書 | `cmudict-fast` | latest | MIT | CMU 発音辞書ルックアップ |
| WAV 出力 | `hound` | 3.5.1 | Apache-2.0 | 事実上の標準 |
| 音声再生 | `rodio` | 0.22.2 | MIT/Apache-2.0 | cpal 上位 API。ストリーミング対応 |
| CLI | `clap` | latest | MIT/Apache-2.0 | derive マクロで簡潔 |
| JSON | `serde` + `serde_json` | latest | MIT/Apache-2.0 | config.json / phoneme_id_map |
| 正規表現 | `regex` | latest | MIT/Apache-2.0 | fullcontext label パース、G2P ルール |
| エラー (lib) | `thiserror` | latest | MIT/Apache-2.0 | ライブラリ層のエラー型定義 |
| エラー (bin) | `anyhow` | latest | MIT/Apache-2.0 | CLI 層のエラーハンドリング |
| ログ | `tracing` | latest | MIT | spdlog 相当 |
| HTTP | `reqwest` | latest | MIT/Apache-2.0 | モデルダウンロード |
| リサンプリング | `rubato` | 0.11.0 | MIT | 22050Hz → デバイス SR 変換 (任意) |

### ONNX Runtime ライブラリ比較

| ライブラリ | VITS 実績 | GPU | Pure Rust | WASM | 推奨度 |
|-----------|----------|-----|-----------|------|--------|
| **`ort`** | piper-rs, sbv2-api | CUDA/CoreML/DirectML | No (C++ FFI) | No | **第一推奨** |
| **`rten`** | Piper 動作確認済 | No | Yes | Yes | 組み込み/WASM 向け |
| `tract` | 未確認 | No | Yes | Yes | 代替選択肢 |
| `burn` | 未確認 | WGPU | Yes | Yes | 将来有望 |
| `candle` | 未確認 | CUDA/Metal | Yes | Yes | TTS 向きではない |

---

## 先行事例

### Piper TTS の Rust 実装

| プロジェクト | GitHub | アプローチ | 特徴 |
|------------|--------|----------|------|
| **piper-rs** | thewh1teagle/piper-rs | ort + espeak-rs | 最多 DL (10,000+)。CLI あり |
| **piper-tts-rust** | aspicho/piper-tts-rust | ort + BART G2P | espeak-ng 排除。Piper-Plus と同方向性 |
| **sonata** | mush42/sonata | ort + モジュラー | model/synth/grpc/c-api/python 分離 |
| **piper-tts-rs** | WrldEngine/piper-tts-rs | C++ FFI | Piper C++ ライブラリの直接バインディング |
| **rten Discussion #504** | rhasspy/piper | Pure Rust (ONNX Runtime 不要) | 2MB バイナリ。1.3x 遅い程度 |

### 参考になる設計パターン

- **sonata** のモジュラー構成: `sonata-model` / `sonata-synth` / `sonata-grpc` / `libsonata` / `sonata-python`
- **piper-tts-rust** の espeak-ng フリー設計: Piper-Plus の g2p-en 方針と同方向
- **pocket-tts** (Candle ベース): Pure Rust、WASM 対応、Python 比 3.1x 高速

---

## アーキテクチャ設計

### ディレクトリ構成

```
src/rust/
├── Cargo.toml                 (workspace root)
├── piper-core/                # 推論エンジン + 音素化 (ライブラリ)
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── error.rs            # thiserror 定義
│       ├── config.rs           # config.json / phoneme_id_map
│       ├── engine.rs           # ort ONNX 推論
│       ├── audio.rs            # WAV 出力 / PCM 変換
│       ├── model_catalog.rs    # voices.json カタログ + DL
│       └── phonemize/
│           ├── mod.rs           # Phonemizer trait + レジストリ
│           ├── japanese.rs      # jpreprocess ベース
│           ├── english.rs       # CMU 辞書 + ARPAbet→IPA
│           ├── chinese.rs       # pypinyin 辞書 + ピンイン→IPA + 声調サンドヒ
│           ├── korean.rs        # Hangul 分解 + jamo→IPA
│           ├── spanish.rs       # ルールベース G2P
│           ├── french.rs        # ルールベース G2P
│           ├── portuguese.rs    # ルールベース G2P
│           ├── multilingual.rs  # 多言語コードスイッチング + Unicode 言語検出
│           └── token_map.rs     # PUA マッピング (89 固定エントリ, 正準定義)
├── piper-cli/                 # CLI バイナリ
│   ├── Cargo.toml
│   └── src/
│       └── main.rs
├── piper-ffi/                 # C FFI 層 (Python/Swift/Kotlin 等)
│   ├── Cargo.toml
│   ├── src/
│   │   └── lib.rs
│   └── piper.h                # cbindgen 生成
└── piper-server/              # HTTP/gRPC サーバ (将来)
    ├── Cargo.toml
    └── src/
        └── main.rs
```

### 主要トレイト

```rust
/// 言語固有の音素化
pub trait Phonemizer: Send + Sync {
    fn phonemize_with_prosody(
        &self, text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError>;

    /// 言語固有の phoneme_id_map を返す (None なら config.json のものを使用)
    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap>;

    /// BOS/EOS/パディング挿入。JA は no-op、他言語はデフォルト実装を使用
    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>);

    fn language_code(&self) -> &str;
}

/// ONNX 推論エンジン
pub trait TTSEngine: Send + Sync {
    fn synthesize(&self, request: &SynthesisRequest) -> Result<SynthesisResult, PiperError>;
    fn capabilities(&self) -> &ModelCapabilities;
}

/// オーディオ出力先
pub trait AudioOutput: Send {
    fn write_samples(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError>;
    fn finalize(&mut self) -> Result<(), PiperError>;
}
```

### 高レベル API

```rust
pub struct PiperVoice {
    config: VoiceConfig,
    engine: OnnxEngine,
    phonemizer: Box<dyn Phonemizer>,
}

impl PiperVoice {
    pub fn load(model_path: &Path, config_path: &Path) -> Result<Self, PiperError>;
    /// 多言語モデルでは language_id を自動検出 (Unicode 範囲ベース)
    pub fn synthesize_text(&self, text: &str, speaker_id: Option<i64>) -> Result<SynthesisResult, PiperError>;
    pub fn text_to_wav_file(&self, text: &str, output: &Path, speaker_id: Option<i64>) -> Result<SynthesisResult, PiperError>;
    pub fn synthesize_streaming(&self, text: &str, speaker_id: Option<i64>, chunk_callback: impl FnMut(&[i16])) -> Result<SynthesisResult, PiperError>;
}
```

### エラーハンドリング

ライブラリ層 (`piper-core`) は `thiserror` で型付きエラー、CLI 層は `anyhow` でラップ。

```rust
#[derive(Error, Debug)]
pub enum PiperError {
    #[error("config file not found: {path}")]
    ConfigNotFound { path: String },
    #[error("model load failed: {0}")]
    ModelLoad(#[from] ort::Error),
    #[error("unsupported language: {code}")]
    UnsupportedLanguage { code: String },
    #[error("unknown phoneme: {phoneme}")]
    UnknownPhoneme { phoneme: String },
    #[error("inference failed: {0}")]
    Inference(#[from] ort::Error),
    #[error("audio output error: {0}")]
    AudioOutput(#[from] std::io::Error),
}
```

---

## 多言語対応

PR #218 で 7 言語 (JA/EN/ZH/KO/ES/FR/PT) の GPL-free G2P が実装された。Rust 推論でも全言語をサポートする必要がある。

### 対応言語一覧

| 言語 | コード | G2P 方式 | Python 依存 | 外部データ | 推定 Rust 行数 |
|------|--------|---------|------------|-----------|---------------|
| 日本語 | `ja` | OpenJTalk | pyopenjtalk | NAIST-JDIC 辞書 | ~500 |
| 英語 | `en` | CMU 辞書 + ARPAbet→IPA | g2p-en | `cmudict_data.json` (3.7MB) | ~500-700 |
| 中国語 | `zh` | pypinyin 辞書 + ピンイン→IPA | pypinyin | `pinyin_single.json` + `pinyin_phrases.json` (2.6MB) | ~700-900 |
| 韓国語 | `ko` | Hangul 分解 + jamo→IPA | g2pk2 | なし | ~300-500 |
| スペイン語 | `es` | ルールベース | なし | なし | ~700-900 |
| フランス語 | `fr` | ルールベース | なし | なし | ~1000-1300 |
| ポルトガル語 | `pt` | ルールベース | なし | なし | ~800-1000 |

### Unicode 言語検出 (UnicodeLanguageDetector)

多言語モデルではテキストを言語セグメントに分割し、言語別 Phonemizer に委譲する。

**検出優先順位:**
1. ひらがな/カタカナ (U+3040-30FF, U+31F0-31FF) → `ja`
2. ハングル (U+AC00-D7AF) → `ko`
3. CJK 漢字 (U+4E00-9FFF) → かな文脈あり: `ja` / なし: `zh`
4. Latin 文字 → `default_latin_language` (en/es/fr/pt から選択)
5. 中立文字 (数字/句読点) → 前セグメントを継承

```rust
pub struct UnicodeLanguageDetector {
    languages: HashSet<String>,
    default_latin_lang: String,
}

impl UnicodeLanguageDetector {
    pub fn detect_char(&self, ch: char, context_has_kana: bool) -> Option<&str>;
    pub fn segment_text(&self, text: &str) -> Vec<LangSegment>;
}

pub struct LangSegment {
    pub lang: String,
    pub text: String,
}
```

### 言語 ID と自動プロモーション

多言語モデル (`num_languages > 1`) で単一言語 (`--language ja`) を指定した場合、自動的に `MultilingualPhonemizer` に昇格してインタースパースパディングを適用する:

```rust
fn auto_promote_language(language: &str, language_id_map: &HashMap<String, i64>) -> String {
    if language == "ja" && language_id_map.len() > 1 && !language.contains('-') {
        // ja → "en-es-fr-ja-pt-zh" のような正規化コンボに昇格
        let mut langs: Vec<&str> = language_id_map.keys().map(|s| s.as_str()).collect();
        langs.sort();
        langs.join("-")
    } else {
        language.to_string()
    }
}
```

### プロソディ情報 (A1/A2/A3) の言語別セマンティクス

全言語で `ProsodyInfo { a1, a2, a3 }` を共有するが、値の意味が異なる:

| 言語 | a1 | a2 | a3 |
|------|-----|-----|-----|
| **JA** | アクセント核相対位置 (-4~+N) | モーラ位置 (1-based) | アクセント句内総モーラ数 |
| **ZH** | 声調 (1-5, PUA tone markers から抽出) | 単語内の音節位置 | 単語の音節数 |
| **EN** | 0 (固定) | ストレスレベル (0/1/2) | 単語内の音素数 |
| **ES/PT** | 0 (固定) | ストレスレベル (0/2) | 単語内の音素数 |
| **FR** | 0 (固定) | 語末母音=2, 他=0 | 単語内の音素数 |
| **KO** | 0 (固定) | 0 (固定) | 0 (固定) |

**注意**: 多言語モデルの学習時、プロソディは日本語のみ有効 (`prosody_language_ids={0}`)。他言語のプロソディはゼロマスクされる。

### post_process_ids の言語別動作

| phoneme_type | BOS/EOS | インタースパースパディング |
|--------------|---------|--------------------------|
| `openjtalk` (JA 単言語) | inline (phonemize 内で挿入) | なし |
| `bilingual` / `multilingual` | base class が追加 | あり (音素間に `_`=ID 0 を挿入) |

JA 単言語モデルの `post_process_ids()` は no-op。多言語モデルでは JA も昇格されパディングが適用される。

### PUA マッピングテーブル (全 89 エントリ)

Python (`token_mapper.py`)、C++ (各 `*_phonemize.cpp`) と同一テーブルを `token_map.rs` に正準定義。**学習済みモデルの重みに依存するため、変更不可。**

| 範囲 | 数 | 言語 | 内容 |
|------|-----|------|------|
| U+E000-E004 | 5 | JA | 長母音 (a:, i:, u:, e:, o:) |
| U+E005 | 1 | JA | cl (促音) |
| U+E006-E015 | 16 | JA | パラタル子音 (ky, kw, gy, ..., ry) |
| U+E016-E018 | 3 | JA | 疑問詞マーカー (?!, ?., ?~) |
| U+E019-E01C | 4 | JA | N 変異 (N_m, N_n, N_ng, N_uvular) |
| U+E01D | 1 | ES | rr (トリル) |
| U+E01E | 1 | ZH/FR | y_vowel (前舌丸め母音) |
| U+E020-E04A | 43 | ZH | 送気/反舌/複合韻母、声調マーカー (tone1-5) |
| U+E04B-E052 | 8 | KO | 濃音 (p͈,t͈,k͈,s͈,t͈ɕ)、未放出終声 (k̚,t̚,p̚) |
| U+E054-E055 | 2 | ES/PT | 破擦音 (tʃ, dʒ) |
| U+E056-E058 | 3 | FR | 鼻母音 (ɛ̃, ɑ̃, ɔ̃) |

動的割り当ては `U+E059` 以降。

---

## 言語別音素化の実装方針

### 推奨戦略: C++ 実装の直接移植

C++ G2P コード (PR #218) は Python との出力パリティが検証済みのため、最もリスクが低い。

### 日本語 (JA)

```
テキスト → jpreprocess (fullcontext labels) → A1/A2/A3 抽出
→ 栗原法 prosody マーク → N 変異規則 → PUA マッピング → phoneme_ids
```

| アプローチ | 利点 | 欠点 |
|-----------|------|------|
| **jpreprocess (推奨)** | Pure Rust。NAIST-JDIC 内蔵 | pyopenjtalk-plus カスタムルールとの互換性要検証 |
| OpenJTalk C FFI | C++ 版と完全互換 | unsafe コード。ビルド複雑 |

N 変異規則: `N_m` (m/b/p前), `N_n` (n/t/d前), `N_ng` (k/g前), `N_uvular` (語末/母音前)

### 英語 (EN)

```
テキスト → CMU 辞書照合 + OOV フォールバック → ARPAbet → IPA
→ 機能語ストレス除去 → BOS/EOS/パディング → phoneme_ids
```

- CMU 辞書 (123K 語, Public Domain) を JSON で読み込み
- ARPAbet→IPA 変換 + 文脈依存ルール (`AA+R→ɑːɹ`, `ER1→ɜː`)
- 機能語ストレス除去 (97 語: a, the, are, you 等)
- **espeak-ng は使用禁止 (GPL-3.0)**

### 中国語 (ZH)

```
テキスト → pypinyin 辞書照合 (多音字フレーズマッチング) → ピンイン正規化
→ 声調サンドヒ (T3+T3, 一, 不) → ピンイン→IPA → 儿化処理 → phoneme_ids
```

- 単文字辞書 (8.1K 文字) + フレーズ辞書 (8.5K フレーズ) を JSON で読み込み
- 声調サンドヒ 4 規則: T3+T3→T2, 一+T4→T2, 一+T1/T2/T3→T4, 不+T4→T2
- 声調マーカーは PUA (U+E046-E04A)

### 韓国語 (KO)

```
テキスト → Hangul 音節分解 (数学的: code - 0xAC00) → 初声/中声/終声
→ jamo→IPA テーブル → liaison 規則 → phoneme_ids
```

- Hangul 分解は純粋な算術演算 (外部データ不要)
- 初声 19 + 中声 21 + 終声 28 の IPA テーブル
- C++ 版では g2pk2 の音韻規則は未実装 (liaison のみ)

### スペイン語 (ES) / フランス語 (FR) / ポルトガル語 (PT)

全てルールベース G2P (外部依存なし、Pure Rust で直接実装):

| 言語 | 主要ルール | C++ 行数 |
|------|----------|---------|
| ES | seseo (c/z→s), 文脈依存 b/d/g→β/ð/ɣ, ストレス規則 | 815 |
| FR | 鼻母音, 無音末尾子音, -tion/-ille パターン, リエゾン | 1196 |
| PT | 鼻母音, coda-l→w, t/d 口蓋化, r の多型 (ɾ/ʁ) | 1004 |

---

## 音声出力

### WAV ファイル出力

`hound` crate で 22050Hz / 16bit PCM / モノラルを書き出す:

```rust
let spec = hound::WavSpec {
    channels: 1,
    sample_rate: 22050,
    bits_per_sample: 16,
    sample_format: hound::SampleFormat::Int,
};
let mut writer = hound::WavWriter::create(path, spec)?;
for sample in audio_i16 {
    writer.write_sample(sample)?;
}
```

### リアルタイム再生

`rodio` で `Source` トレイトを実装し、リングバッファ経由でストリーミング再生:

```
[推論スレッド] → ringbuf → [rodio Source] → スピーカー
                    ↓
              [hound WavWriter] → WAV ファイル (並行保存)
```

### float32 → int16 変換

C++ 版と同様のピーク正規化:

```rust
fn audio_float_to_int16(audio: &[f32]) -> Vec<i16> {
    let max_val = audio.iter().map(|x| x.abs()).fold(0.01f32, f32::max);
    let scale = 32767.0 / max_val;
    audio.iter()
        .map(|x| (x * scale).clamp(-32768.0, 32767.0) as i16)
        .collect()
}
```

---

## パフォーマンス評価

### Rust vs Python

| 観点 | 改善 | 備考 |
|------|------|------|
| ONNX 推論速度 | 3-5x 高速 | Python overhead 排除 |
| テキスト前処理 | 3-50x 高速 | CPU バウンド処理 |
| メモリ使用量 | 60-80% 削減 | GC なし |
| 並行処理 | GIL なし (12x+ スループット) | 真の並列処理 |
| Docker イメージ | 10-100x 小さい | scratch ベース可 |

### Rust vs C++

| 観点 | 比較 | 備考 |
|------|------|------|
| ONNX 推論速度 | 同等 | 同じ FFI |
| 前処理速度 | 同等 | 両言語ともネイティブ |
| メモリ安全性 | Rust が優位 | コンパイル時保証 |
| ビルド容易性 | Rust が優位 | Cargo vs CMake |
| クロスコンパイル | Rust が優位 | ターゲット指定のみ |

---

## WASM/ブラウザ対応

### 現状

現在の `src/wasm/openjtalk-web/` は JavaScript ベースで成熟した実装:
- onnxruntime-web (WASM/WebGPU フォールバック)
- AudioWorklet / ScriptProcessor / HTMLAudio
- IndexedDB キャッシュ
- ストリーミング再生

### Rust WASM の選択肢

| アプローチ | バイナリサイズ | GPU | 推論速度 |
|-----------|-------------|-----|---------|
| onnxruntime-web (現行 JS) | 8-15MB | WebGPU | 基準 |
| Rust + tract (CPU) | 1.5-3MB | No | 1.3x 遅い |
| Rust + wonnx (WebGPU) | 2-4MB | WebGPU | 要検証 |

### 結論

現時点では Rust WASM 移行は非推奨。現行 JS 実装が成熟しており、onnxruntime-web の WebGPU バックエンドが最も実用的。

将来的に `ort` の tract バックエンドが VITS モデルを完全サポートした場合、ネイティブ CLI と Web で推論コード共有が可能になる。

---

## ロードマップ

### Phase 1: 最小推論 (MVP) — 2-3 週間

**目標**: phoneme_ids 直接入力 → ONNX 推論 → WAV 出力

- `ort` による ONNX セッション管理
- `config.json` パース (`phoneme_id_map`, `sample_rate`, `language_id_map`, `phoneme_type`)
- phoneme_ids + input_lengths + scales テンソル構築
- sid / lid / prosody_features オプション対応 (多言語モデル含む)
- `phoneme_type` による動作分岐判定 (`openjtalk` / `bilingual` / `multilingual`)
- 16-bit PCM WAV 書き出し (ピーク正規化)
- JSONL stdin 入力 (Python 互換)
- `--device auto|cpu|gpu` デバイス選択

**検証基準**: Python `infer_onnx.py` と同一 phoneme_ids で同一 WAV 出力

### Phase 2: 日本語音素化 — 3-4 週間 ✅

**目標**: テキスト → phoneme_ids + prosody_features の日本語パイプライン

- jpreprocess による fullcontext label 生成
- A1/A2/A3 抽出 (正規表現: `/A:([\d-]+)\+`, `\+([0-9]+)\+`, `\+([0-9]+)/`)
- 栗原法 prosody マーク (`^`, `$`, `?`, `_`, `#`, `[`, `]`)
- 疑問詞マーカー (`?!`, `?.`, `?~` — Issue #204)
- N 変異規則 (`N_m`, `N_n`, `N_ng`, `N_uvular` — Issue #207)
- PUA トークンマッピング (89 固定エントリ)
- カスタム辞書 (JSON 形式、正規表現マッチ)
- **`post_process_ids` は no-op** (BOS/EOS/パディングは phonemize 内で inline 処理)

**実装済み (Phase 2):**
- `phonemize/japanese.rs` — JapanesePhonemizer (jpreprocess ベース)
  - fullcontext label → 音素抽出 + 栗原法 prosody マーク
  - A1/A2/A3 プロソディ値抽出
  - 疑問詞マーカー (?!, ?., ?~)
  - N 変異規則 (N_m, N_n, N_ng, N_uvular)
  - PUA トークンマッピング
- `phonemize/custom_dict.rs` — カスタム辞書 (JSON v1.0/v2.0)
- `phonemize/phoneme_converter.rs` — トークン→ID変換
- `voice.rs` — PiperVoice 高レベル API (テキスト→音声)
- CLI: `--text`, `--language`, `--custom-dict` オプション追加
- `token_map.rs` — PUA マッピングを Python token_mapper.py と完全一致に修正

### Phase 3: 多言語 G2P + CLI — 5-7 週間 ✅

**目標**: 7 言語対応 + テキスト → 音声の完全パイプライン

**CLI 機能:**
- `--text "テキスト"` 直接入力
- `--language ja-en-zh` 多言語指定 (単一言語/コンボ両対応)
- `--list-models` / `--download-model`
- config.json フォールバック検出 (`--config` > `.onnx.json` > `config.json`)

**英語 G2P** (~700 行):
- CMU 辞書 (123K 語) JSON ロード + ルックアップ
- ARPAbet→IPA 変換 + 文脈依存ルール (`AA+R→ɑːɹ`, `ER1→ɜː`, `ER0→ɚ`)
- 機能語ストレス除去 (97 語)
- OOV フォールバック: 形態論的接尾辞剥離 (-ing, -ed, -s, -er, -ly, -est)
- `post_process_ids`: BOS + インタースパースパディング + EOS

**中国語 G2P** (~900 行):
- pypinyin 辞書 (単文字 8.1K + フレーズ 8.5K) JSON ロード
- 多音字フレーズマッチング (最長一致)
- ピンイン正規化 (y/w プレフィクス除去、v→ü)
- 声調サンドヒ 4 規則 (T3+T3, 一, 不)
- ピンイン→IPA 変換 (声母 21 + 韻母 45+)
- 儿化 (erhua) 処理
- プロソディ: a1=声調(1-5), a2=音節位置, a3=単語内音節数

**韓国語 G2P** (~500 行):
- Hangul 音節分解 (算術: `(code - 0xAC00) / (21*28)`, etc.)
- 初声 19 + 中声 21 + 終声 28 の IPA テーブル
- 基本 liaison (連音化) 規則

**スペイン語 G2P** (~900 行):
- ルールベース (seseo: c/z→s, 文脈依存 b/d/g→β/ð/ɣ)
- ストレス規則 (アクセント記号 + 語末判定)
- 機能語ストレス除去 (30+ 語)

**フランス語 G2P** (~1300 行, 最も複雑):
- 鼻母音 (ɛ̃, ɑ̃, ɔ̃), 無音末尾子音, -tion/-ille パターン
- 前舌丸め母音 (ø, œ, y_vowel), 半母音 (ɥ)
- リエゾン, 例外辞書 (ville, mille 等)

**ポルトガル語 G2P** (~1000 行):
- 鼻母音 (ã, ẽ, ĩ, õ, ũ), coda-l→w, t/d 口蓋化
- r の多型 (語頭/coda: ʁ, 母音間: ɾ)

**多言語基盤:**
- Unicode 言語検出 (`UnicodeLanguageDetector`)
- テキストセグメンテーション (言語別に分割して各 Phonemizer に委譲)
- 言語レジストリ (trait + 動的ディスパッチ + 正規化キャッシング)
- 言語自動プロモーション (JA → 多言語モデル時にパディング適用)
- 非 JA 言語のプロソディ計算 (`computeNonJaProsody` 相当)

**実装済み (Phase 3):**
- `phonemize/english.rs` — EnglishPhonemizer (CMU辞書 + ARPAbet→IPA)
- `phonemize/chinese.rs` — ChinesePhonemizer (pypinyin辞書 + ピンイン→IPA + 声調サンドヒ)
- `phonemize/korean.rs` — KoreanPhonemizer (Hangul分解 + jamo→IPA)
- `phonemize/spanish.rs` — SpanishPhonemizer (ルールベース G2P)
- `phonemize/french.rs` — FrenchPhonemizer (ルールベース G2P)
- `phonemize/portuguese.rs` — PortuguesePhonemizer (ルールベース G2P)
- `phonemize/multilingual.rs` — UnicodeLanguageDetector + MultilingualPhonemizer
  - Unicode言語検出、テキストセグメンテーション、BOS/EOS/インタースパースパディング
- `voice.rs` — Bilingual/Multilingual phoneme type 対応

### Phase 4: 高度な機能

| サブフェーズ | 内容 | 工数 |
|------------|------|------|
| 4a | ストリーミング再生 (rodio + ringbuf + クロスフェード) | 2 週間 |
| 4b | phoneme timing 出力 (JSON/TSV, duration テンソルから抽出) | 1 週間 |
| 4c | WASM 対応 (ort tract backend) | 3-4 週間 |
| 4d | GPU 推論 (CUDA/CoreML feature flag) | 1-2 週間 |
| 4e | PyO3 Python バインディング | 2-3 週間 |

### 工数サマリ

| フェーズ | 工数 | 累計 |
|---------|------|------|
| Phase 1: MVP (ONNX 推論) | 2-3 週 | 2-3 週 |
| Phase 2: 日本語音素化 ✅ | 3-4 週 | 5-7 週 |
| Phase 3: 多言語 G2P + CLI ✅ | 5-7 週 | 10-14 週 |
| Phase 4: 高度な機能 | 9-12 週 | 19-26 週 |

**Phase 1-3 で 7 言語対応の実用 CLI が完成 (約 2.5-3.5 ヶ月)**

---

## リスクと対策

### 技術的リスク

| リスク | 重大度 | 対策 |
|--------|-------|------|
| jpreprocess と pyopenjtalk-plus の出力差異 | 高 | ゴールデンテストで検証。差異時は OpenJTalk C FFI にフォールバック |
| 7 言語 G2P の Python/C++ との出力パリティ | 高 | C++ 実装を直接移植 (出力パリティ検証済み)。言語別ゴールデンテスト |
| PUA マッピングの Python/C++/Rust 同期 | 高 | 89 固定エントリを `token_map.rs` に正準定義。CI でクロス言語検証 |
| フランス語 G2P の複雑さ (1200 行) | 中 | C++ 版を忠実に移植。例外辞書を JSON で管理 |
| 英語 OOV 語の精度 | 中 | CMU 辞書で 95-98% カバー。形態論的接尾辞剥離でフォールバック |
| `ort` crate の API 安定性 | 低 | バージョンピン。v2 は production-ready |

### ライセンス互換性

全推奨クレートは MIT / Apache-2.0 で、Piper-Plus の MIT ライセンスと互換:

| 依存 | ライセンス | 互換性 |
|------|-----------|--------|
| ort | MIT/Apache-2.0 | OK |
| ONNX Runtime | MIT | OK |
| jpreprocess | MIT | OK |
| CMU Pronouncing Dictionary | Public Domain | OK |
| pypinyin 辞書データ | MIT | OK |
| hound, clap, serde | MIT/Apache-2.0 | OK |
| pinyin, hangul crate | MIT | OK |
| OpenJTalk (C) | Modified BSD | OK |
| **espeak-ng** | **GPL-3.0** | **非互換 — 使用しないこと** |

---

## 参考リンク

### Rust ONNX

- [pykeio/ort](https://github.com/pykeio/ort) — Rust ONNX Runtime バインディング (公式推奨)
- [ort ドキュメント](https://ort.pyke.io/)
- [robertknight/rten](https://github.com/robertknight/rten) — Pure Rust ONNX 推論 (Piper 動作実績あり)
- [sonos/tract](https://github.com/sonos/tract) — Pure Rust ONNX (Sonos 商用利用)

### Piper Rust 実装

- [thewh1teagle/piper-rs](https://github.com/thewh1teagle/piper-rs) — 最多 DL の Piper Rust バインディング
- [aspicho/piper-tts-rust](https://github.com/aspicho/piper-tts-rust) — espeak-ng フリーの Rust 実装
- [mush42/sonata](https://github.com/mush42/sonata) — モジュラー Rust TTS エンジン
- [rhasspy/piper Discussion #504](https://github.com/rhasspy/piper/discussions/504) — Pure Rust Piper 推論

### 日本語音素化

- [jpreprocess/jpreprocess](https://github.com/jpreprocess/jpreprocess) — Pure Rust OpenJTalk 互換
- [jpreprocess/jlabel](https://github.com/jpreprocess/jlabel) — HTS label パーサ

### 多言語 G2P

- [pinyin crate](https://crates.io/crates/pinyin) — 漢字→ピンイン変換 (385K+ DL)
- [hangul crate](https://crates.io/crates/hangul) — Hangul 音節分解
- [cmudict-fast](https://github.com/BenjaminHinchliff/cmudict-fast) — CMU 発音辞書ルックアップ
- [voirs-g2p](https://crates.io/crates/voirs-g2p) — 多言語 G2P (Beta, MIT)
- [lngcnv](https://crates.io/crates/lngcnv) — 英語/スペイン語 IPA 変換

### Rust オーディオ

- [ruuda/hound](https://github.com/ruuda/hound) — WAV 読み書き
- [RustAudio/rodio](https://github.com/RustAudio/rodio) — 高レベルオーディオ再生
- [RustAudio/cpal](https://github.com/RustAudio/cpal) — 低レベルオーディオ
- [HEnquist/rubato](https://github.com/HEnquist/rubato) — リサンプリング
