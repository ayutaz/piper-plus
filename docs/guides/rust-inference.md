# Piper-Plus Rust 推論実装ガイド

本ドキュメントは Piper-Plus の推論パイプラインを Rust で実装するための調査結果と設計方針をまとめたものです。

---

## 目次

1. [概要](#概要)
2. [現在の推論パイプライン分析](#現在の推論パイプライン分析)
3. [技術スタック](#技術スタック)
4. [先行事例](#先行事例)
5. [アーキテクチャ設計](#アーキテクチャ設計)
6. [日本語音素化の実装方針](#日本語音素化の実装方針)
7. [英語音素化の実装方針](#英語音素化の実装方針)
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
| `sid` | int64 | `[1]` | No | マルチスピーカー時の話者 ID |
| `prosody_features` | int64 | `[1, phoneme_length, 3]` | No | A1/A2/A3 プロソディ値 |

デフォルトスケール値: `noise_scale=0.667`, `length_scale=1.0`, `noise_scale_w=0.8`

#### 出力テンソル

| テンソル名 | 型 | 形状 | 説明 |
|-----------|-----|------|------|
| `output` | float32 | `[1, 1, audio_samples]` | 生音声 (-1.0 ~ 1.0) |
| `durations` | float32 | `[1, phoneme_length]` | 各音素のフレーム数 (オプション) |

### 推論に必要な外部ファイル

- **ONNX モデル** (`.onnx`) — 約 74MB (medium quality, 20 speakers)
- **config.json** — `phoneme_id_map`, `num_speakers`, `sample_rate` 等を含む

config.json 検出順序:
1. `--config` で明示指定
2. `{model}.onnx.json` (C++ CLI convention)
3. `{model_dir}/config.json`

### C++ 版と Python 版の機能差分

| 機能 | C++ | Python |
|------|-----|--------|
| ONNX 推論 | Yes | Yes |
| 日本語音素化 (OpenJTalk) | Yes | Yes |
| 英語音素化 (espeak-ng) | Yes | No (g2p-en) |
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
| WAV 出力 | `hound` | 3.5.1 | Apache-2.0 | 事実上の標準 |
| 音声再生 | `rodio` | 0.22.2 | MIT/Apache-2.0 | cpal 上位 API。ストリーミング対応 |
| CLI | `clap` | latest | MIT/Apache-2.0 | derive マクロで簡潔 |
| JSON | `serde` + `serde_json` | latest | MIT/Apache-2.0 | config.json / phoneme_id_map |
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
│           ├── english.rs       # CMU 辞書 + ルール
│           └── token_map.rs     # PUA マッピング (正準定義)
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

## 日本語音素化の実装方針

### 処理フロー

```
日本語テキスト
    |  jpreprocess (Pure Rust OpenJTalk)
    v
HTS fullcontext labels
    |  正規表現で音素 + A1/A2/A3 抽出
    v
生の音素列 + プロソディ情報
    |  栗原法: ^, $, ?, _, #, [, ] マーク挿入
    v
プロソディ付き音素列
    |  疑問詞マーカー: ?!, ?., ?~ (Issue #204)
    |  N 変異規則: N_m, N_n, N_ng, N_uvular (Issue #207)
    v
最終音素列
    |  PUA マッピング: 多文字 → U+E000-E01C
    v
phoneme_id_map で ID 変換
    |
    v
phoneme_ids: Vec<i64> + prosody_features: Vec<[i32;3]>
```

### 選択肢比較

| アプローチ | 利点 | 欠点 |
|-----------|------|------|
| **jpreprocess (推奨)** | Pure Rust。NAIST-JDIC 内蔵。jlabel で A1/A2/A3 型付きパース | pyopenjtalk-plus カスタムルールとの互換性要検証 |
| OpenJTalk C FFI | C++ 版と完全互換 | unsafe コード。ビルド複雑 |
| lindera/vibrato | Pure Rust | fullcontext label 非対応。A1/A2/A3 取得不可 |

### jpreprocess の使い方

```rust
use jpreprocess::*;

let config = SystemDictionaryConfig::Bundled(jpreprocess_naist_jdic::BUNDLED);
let jpreprocess = JPreprocess::with_dictionaries(config.load()?, None);
let labels = jpreprocess.extract_fullcontext("こんにちは")?;
// labels: Vec<String> in HTS format
// → 正規表現または jlabel で A1/A2/A3 パース
```

### 互換性の注意点

pyopenjtalk-plus には以下の独自 NJD ルールがある (`src/cpp/openjtalk_api.c`):
- `apply_original_rule_before_chaining()` — 動詞連用形・敬語等のアクセント調整
- `modify_acc_after_chaining()` — 後処理

jpreprocess がこれらを含むか要検証。差異がある場合は:
1. jpreprocess にパッチを当てる (MIT ライセンスで可能)
2. OpenJTalk C FFI にフォールバック

### PUA マッピングテーブル

Python (`token_mapper.py`)、C++ (`piper.cpp`) と同一テーブルを `token_map.rs` に正準定義:

```
a: → U+E000, i: → U+E001, u: → U+E002, e: → U+E003, o: → U+E004
cl → U+E005, ky → U+E006, kw → U+E007, ...
?! → U+E016, ?. → U+E017, ?~ → U+E018
N_m → U+E019, N_n → U+E01A, N_ng → U+E01B, N_uvular → U+E01C
```

将来的には共通 JSON テーブルに外出しし、3 言語から参照する形が望ましい。

### N 変異規則

| バリアント | 条件 | 例 |
|-----------|------|-----|
| `N_m` | m/b/p の前 (両唇音) | さんぽ |
| `N_n` | n/t/d/ts/ch の前 (歯茎音) | あんない |
| `N_ng` | k/g の前 (軟口蓋音) | ぎんこう |
| `N_uvular` | 語末/母音の前 (口蓋垂音) | ほん |

---

## 英語音素化の実装方針

### 処理フロー

```
英語テキスト
    |  CMU 辞書照合 + ルールベース OOV 処理
    v
ARPAbet 音素列
    |  ARPAbet → IPA 変換 + ストレスマーカー (ˈ/ˌ)
    v
IPA 音素列
    |  機能語ストレス除去
    |  単語間スペース / 句読点処理
    v
音素列 + プロソディ (a1=0, a2=stress, a3=word_phonemes)
    |  BOS/EOS/パディング挿入 (post_process_ids)
    v
phoneme_ids + prosody_features
```

### 選択肢

| アプローチ | 利点 | 欠点 |
|-----------|------|------|
| **CMU 辞書 + ルールベース (推奨)** | Pure Rust。GPL-free | OOV 語の精度がやや劣る |
| grapheme_to_phoneme + arpabet crate | OOV 対応あり | 2 クレート組み合わせ |
| espeak-ng FFI | 高精度・多言語 | **GPL-3.0 汚染リスク** |

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
- `config.json` パース (`phoneme_id_map`, `sample_rate`)
- phoneme_ids + input_lengths + scales テンソル構築
- sid / prosody_features オプション対応
- 16-bit PCM WAV 書き出し
- JSONL stdin 入力 (Python 互換)

**検証基準**: Python `infer_onnx.py` と同一 phoneme_ids で同一 WAV 出力

### Phase 2: 日本語音素化 — 3-4 週間

**目標**: テキスト → phoneme_ids + prosody_features の日本語パイプライン

- jpreprocess による fullcontext label 生成
- A1/A2/A3 抽出 + 栗原法 prosody マーク
- 疑問詞マーカー / N 変異規則
- PUA トークンマッピング
- カスタム辞書

### Phase 3: CLI 完成 — 3-4 週間

**目標**: テキスト → 音声の完全パイプライン + モデル管理

- `--text "テキスト"` 直接入力
- `--list-models` / `--download-model`
- 英語音素化 (CMU 辞書ベース)
- 言語レジストリ (trait + 動的ディスパッチ)

### Phase 4: 高度な機能

| サブフェーズ | 内容 | 工数 |
|------------|------|------|
| 4a | ストリーミング再生 (rodio + ringbuf) | 2 週間 |
| 4b | WASM 対応 (ort tract backend) | 3-4 週間 |
| 4c | GPU 推論 (CUDA/CoreML feature flag) | 1-2 週間 |
| 4d | PyO3 Python バインディング | 2-3 週間 |

### 工数サマリ

| フェーズ | 工数 | 累計 |
|---------|------|------|
| Phase 1: MVP | 2-3 週 | 2-3 週 |
| Phase 2: 日本語音素化 | 3-4 週 | 5-7 週 |
| Phase 3: CLI 完成 | 3-4 週 | 8-11 週 |
| Phase 4: 高度な機能 | 8-11 週 | 16-22 週 |

**Phase 1-3 で実用 CLI が完成 (約 2-3 ヶ月)**

---

## リスクと対策

### 技術的リスク

| リスク | 重大度 | 対策 |
|--------|-------|------|
| jpreprocess と pyopenjtalk-plus の出力差異 | 高 | ゴールデンテストで検証。差異時は OpenJTalk C FFI にフォールバック |
| 英語 G2P の精度 (g2p-en 比) | 中 | CMU 辞書で主要語カバー。後段で ML ベース G2P 検討 |
| PUA マッピングの 3 言語同期 | 中 | 共通 JSON テーブルに外出しし全言語から参照 |
| `ort` crate の API 安定性 | 低 | バージョンピン。v2 は production-ready |

### ライセンス互換性

全推奨クレートは MIT / Apache-2.0 で、Piper-Plus の MIT ライセンスと互換:

| 依存 | ライセンス | 互換性 |
|------|-----------|--------|
| ort | MIT/Apache-2.0 | OK |
| ONNX Runtime | MIT | OK |
| jpreprocess | MIT | OK |
| hound, clap, serde | MIT/Apache-2.0 | OK |
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

### Rust オーディオ

- [ruuda/hound](https://github.com/ruuda/hound) — WAV 読み書き
- [RustAudio/rodio](https://github.com/RustAudio/rodio) — 高レベルオーディオ再生
- [RustAudio/cpal](https://github.com/RustAudio/cpal) — 低レベルオーディオ
- [HEnquist/rubato](https://github.com/HEnquist/rubato) — リサンプリング
