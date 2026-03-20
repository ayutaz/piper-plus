# Go 推論バインディング 設計ドキュメント

Issue: [#260 feat: Go 推論バインディング](https://github.com/ayutaz/piper-plus/issues/260)

**ステータス: 実装完了 (Phase 1-5)** — 2026-03-21

## 概要

Go向けのTTS推論バインディング。サーバーサイド/マイクロサービス/CLIツール用途に最適化し、ONNX Runtime を直接利用して推論を行う。

### 技術仕様

| 項目 | 値 |
|---|---|
| 言語 | Go 1.26+ |
| ONNX Runtime | `yalue/onnxruntime_go` v1.27.0 経由 C API |
| CLI フレームワーク | `spf13/cobra` v1.10.2 |
| ビルドシステム | Go modules + Makefile |
| 配布 | Go module, Docker image (Alpine), シングルバイナリ |
| 対応プラットフォーム | Linux (x86_64, arm64), macOS (arm64), Windows (x86_64) |
| Execution Provider | CPU, CUDA, TensorRT, CoreML, DirectML |
| 対応言語 | 6言語 (ja, en, zh, es, fr, pt) |
| 総コード量 | 73ファイル, ~11,600行 (テスト含む) |
| テスト | 148 unit + 6 integration |

## 背景・モチベーション

- Go はクラウドネイティブ/サーバーサイド開発の主力言語 (Docker, Kubernetes, Terraform等)
- [LocalAI](https://github.com/mudler/LocalAI) が既に Piper を Go で統合しており、需要が実証済み
- `yalue/onnxruntime_go` が CUDA/TensorRT/CoreML/DirectML EP 対応で成熟 (MIT, 115+ commits)
- シングルバイナリ配布でデプロイが容易
- Go 1.26 の CGo 30% 高速化・Green Tea GC が ONNX 推論とストリーミング合成に直接恩恵

### Go 1.26 最適化の活用

本プロジェクトは Go 1.26 を最低バージョンとし、以下の最適化を積極的に活用する:

| Go 1.26 機能 | 活用場面 |
|---|---|
| **CGo オーバーヘッド 30% 削減** | `onnxruntime_go` の推論呼び出し毎に恩恵。テンソル生成・`Session.Run()`・結果取得の全 CGo パスが高速化 |
| **Green Tea GC (デフォルト有効)** | ストリーミング合成時の GC 停止時間 10-40% 削減。リアルタイムオーディオパイプラインのレイテンシ改善 |
| **スタック割り当て改善** | 推論毎に生成する一時スライス (phoneme_ids, scales, prosody) がヒープではなくスタックに割り当てられるケースが増加。GC 圧力低減 |
| **Experimental SIMD (`GOEXPERIMENT=simd`)** | 将来的にピーク正規化・リサンプリング・クロスフェード等の音声 DSP を SIMD 化する基盤 |
| **Container-aware GOMAXPROCS** (Go 1.25) | Docker/K8s での推論サーバー運用時に cgroup CPU 制限を自動認識 |
| **Iterators (`iter.Seq`)** (Go 1.23) | ストリーミング合成の文分割・チャンク処理、`slices.Chunk` によるバッチ処理 |
| **`structs.HostLayout`** (Go 1.23) | CGo 経由のデータ構造体で C ABI メモリレイアウトを保証 |
| **`encoding/binary.Encode/Append`** (Go 1.23) | WAV PCM サンプルのバイト列変換を io.Writer 不要で高速化 |

## アーキテクチャ

### 方針: Pure Go + ONNX Runtime

Issue 提案では `C++ コア → CGo Bridge → Go API` だが、既存の C++ コードに C API ラッパーが存在しないため、**Pure Go + `yalue/onnxruntime_go`** で ONNX Runtime を直接呼ぶ方式を採用する。これは Rust (`ort` crate) / C# (`Microsoft.ML.OnnxRuntime`) の実装方式と同じ。

```
Go Phonemizer → Phoneme IDs
                    ↓
            ONNX Runtime (via onnxruntime_go)
                    ↓
            float32 audio → int16 PCM → WAV
```

**`onnxruntime_go` の主な特徴:**

- TTS出力長が動的なため **`DynamicAdvancedSession`** を使用する（`AdvancedSession` は事前サイズ確定が必要で不適合）
- テンソル型: `int64`, `float32` 両方サポート済み（generics ベースの `Tensor[T]`）
- `ort.GetInputOutputInfo()` でモデル能力を自動検出可能
- `RunOptions.SetTerminate()` で推論キャンセル可能（`context.Context` と連携）
- Go 1.26 の **CGo 30% 高速化**により、テンソル生成・`Session.Run()`・結果取得の全 CGo パスが自動的に恩恵を受ける
- Go 1.26 の **Green Tea GC** により、ストリーミング合成中の GC 停止時間が 10-40% 削減され、リアルタイムオーディオ配信のレイテンシが改善

### ONNX Runtime 共有ライブラリ

`onnxruntime_go` は ONNX Runtime 共有ライブラリを**自動ダウンロードしない**。ユーザーまたは CI が配布する必要がある。

**配布方式:**

| 方式 | 用途 | 説明 |
|---|---|---|
| 手動ダウンロード | 開発者 | [ONNX Runtime Releases](https://github.com/microsoft/onnxruntime/releases) から OS 別にダウンロード |
| 環境変数 | 実行時 | `ONNX_RUNTIME_SHARED_LIBRARY_PATH` でライブラリパスを指定 |
| CI 自動ダウンロード | テスト | プラットフォーム別にダウンロード（後述） |
| Docker イメージ同梱 | 本番 | Alpine/Debian イメージにライブラリをコピー |

**プラットフォーム別ファイル:**

| OS | ファイル名 | アーカイブ |
|---|---|---|
| Linux x64 | `libonnxruntime.so` | `onnxruntime-linux-x64-{VER}.tgz` |
| Linux ARM64 | `libonnxruntime.so` | `onnxruntime-linux-aarch64-{VER}.tgz` |
| macOS ARM64 | `libonnxruntime.dylib` | `onnxruntime-osx-arm64-{VER}.tgz` |
| Windows x64 | `onnxruntime.dll` | `onnxruntime-win-x64-{VER}.zip` |

**初期化コード:**

```go
import ort "github.com/yalue/onnxruntime_go"

// プロセス起動時に1回だけ呼ぶ
func Init(libraryPath string) error {
    ort.SetSharedLibraryPath(libraryPath)
    return ort.InitializeEnvironment()
}

// プロセス終了時に1回だけ呼ぶ
func Shutdown() error {
    return ort.DestroyEnvironment()
}
```

### ディレクトリ構造

`go.mod` は `src/go/` 直下に配置し、冗長な `piper-plus/` ネストを回避する。`phonemize/` は循環依存防止のため `piperplus/` の sibling package とする。

```
src/go/
├── go.mod                         # module github.com/ayutaz/piper-plus/src/go
├── go.sum
├── Makefile                       # build/test/lint/docker/coverage
├── .golangci.yml                  # golangci-lint 設定
├── README.md                      # 包括的ドキュメント
├── piperplus/                     # package piperplus — コアライブラリ
│   ├── doc.go                     # godoc パッケージドキュメント
│   ├── init.go                    # ONNX Runtime Init()/Shutdown() ライフサイクル
│   ├── errors.go                  # 構造化エラー型 (5種 + sentinel 4種)
│   ├── config.go                  # VoiceConfig + config.json パーサー
│   ├── options.go                 # SynthesisRequest/Option, LoadOption (functional options)
│   ├── engine.go                  # OnnxEngine (DynamicAdvancedSession + 能力検出)
│   ├── voice.go                   # Voice API (LoadVoice, Close)
│   ├── synthesize.go              # Voice.Synthesize (phonemizer↔engine統合)
│   ├── wav.go                     # SynthesisResult + WAV 出力 (io.WriterTo)
│   ├── timing.go                  # phoneme タイミング (durations → 時刻変換)
│   ├── device.go                  # GPU デバイス選択 + EP 設定
│   ├── streaming.go               # AudioSink + ストリーミング合成 + クロスフェード
│   ├── text_splitter.go           # 文分割 (JA/ZH/EN 対応)
│   ├── pool.go                    # VoicePool (セッションプーリング)
│   ├── server.go                  # HTTP API サーバー (/synthesize, /health, /info)
│   ├── jsonl.go                   # JSONL 入力パーサー
│   ├── model_manager.go           # モデルダウンロード + キャッシュ管理
│   ├── testdata/                  # テストフィクスチャ (config.json 等)
│   └── *_test.go                  # ユニット + インテグレーションテスト
├── phonemize/                     # package phonemize — 6言語 Phonemizer
│   ├── doc.go                     # godoc パッケージドキュメント
│   ├── phonemizer.go              # Phonemizer インターフェース + PostProcessIDs
│   ├── pua.go                     # PUA 双方向マッピング (87 固定エントリ)
│   ├── unicode_detect.go          # Unicode 言語検出 (7段階優先度)
│   ├── multilingual.go            # マルチリンガル Phonemizer + EOSToken 追跡
│   ├── japanese.go                # 日本語 (G2P Engine + Kurihara + N変異)
│   ├── english.go                 # 英語 (CMU辞書 + ARPAbet→IPA)
│   ├── chinese.go                 # 中国語 (Pinyin→IPA + 声調変調)
│   ├── spanish.go                 # スペイン語 (規則ベース G2P, seseo)
│   ├── french.go                  # フランス語 (規則ベース G2P, 鼻母音)
│   ├── portuguese.go              # ポルトガル語 (規則ベース G2P, 鼻母音化)
│   ├── dict.go                    # カスタム辞書サポート
│   └── *_test.go                  # ユニットテスト
├── cmd/
│   └── piper-plus/                # CLI アプリケーション (cobra, 17フラグ)
│       └── main.go
├── docker/
│   ├── Dockerfile                 # Alpine multi-stage (ONNX Runtime 同梱)
│   └── .dockerignore
└── examples/
    ├── README.md
    ├── basic/main.go              # 基本テキスト→WAV 合成
    ├── server/main.go             # HTTP TTS サーバー
    ├── streaming/main.go          # ストリーミング合成
    ├── batch/main.go              # バッチ処理
    └── pool/main.go               # VoicePool 並行合成
```

**インポートパス:**
```go
import "github.com/ayutaz/piper-plus/src/go/piperplus"
import "github.com/ayutaz/piper-plus/src/go/phonemize"
```

**CLI インストール:**
```bash
go install github.com/ayutaz/piper-plus/src/go/cmd/piper-plus@latest
```

## ONNX モデル仕様

### 入力テンソル

| テンソル名 | 型 | Shape | 必須 | 説明 |
|---|---|---|---|---|
| `input` | int64 | `[1, phonemes]` | 必須 | Phoneme ID 列 |
| `input_lengths` | int64 | `[1]` | 必須 | Phoneme 列の長さ |
| `scales` | float32 | `[3]` | 必須 | `[noise_scale, length_scale, noise_w]` (1次元、バッチ次元なし) |
| `sid` | int64 | `[1]` | 条件付き | Speaker ID (multi-speaker or multilingual モデル) |
| `lid` | int64 | `[1]` | 条件付き | Language ID (multilingual モデル) |
| `prosody_features` | int64 | `[1, phonemes, 3]` | 条件付き | A1/A2/A3 prosody 値 |

### 出力テンソル

| テンソル名 | 型 | Shape | 説明 |
|---|---|---|---|
| `output` | float32 | `[1, 1, time]` | 生成音声 (float, 範囲 [-1.0, 1.0]) |
| `durations` | float32 | `[1, phonemes]` | 各 phoneme のデュレーション (hop_length 単位) |

### モデル能力の自動検出

`ort.GetInputOutputInfo()` で ONNX グラフの入出力テンソル名を取得し、モデルの能力を自動検出する（C++/Rust/C# 共通パターン）。検出結果に基づき、`DynamicAdvancedSession` に渡す入出力名リストを動的に構築する。

```go
type ModelCapabilities struct {
    HasSpeakerID      bool // "sid" 入力が存在
    HasLanguageID     bool // "lid" 入力が存在
    HasProsody        bool // "prosody_features" 入力が存在
    HasDurationOutput bool // "durations" 出力が存在
}

// GetInputOutputInfo でセッション作成前に検出
func detectCapabilities(modelPath string) (*ModelCapabilities, error) {
    inputs, outputs, err := ort.GetInputOutputInfo(modelPath)
    if err != nil {
        return nil, &ModelLoadError{Path: modelPath, Err: err}
    }
    return &ModelCapabilities{
        HasSpeakerID:      containsName(inputs, "sid"),
        HasLanguageID:     containsName(inputs, "lid"),
        HasProsody:        containsName(inputs, "prosody_features"),
        HasDurationOutput: containsName(outputs, "durations"),
    }, nil
}
```

### 入力テンソルの動的構築

モデル能力に応じて入力テンソルリストを動的に組み立てる:

```go
inputNames := []string{"input", "input_lengths", "scales"}
inputValues := []ort.Value{inputTensor, lengthsTensor, scalesTensor}

if caps.HasSpeakerID {
    inputNames = append(inputNames, "sid")
    inputValues = append(inputValues, sidTensor)
}
if caps.HasLanguageID {
    inputNames = append(inputNames, "lid")
    inputValues = append(inputValues, lidTensor)
}
if caps.HasProsody {
    // prosody_features がない場合はゼロ埋め
    inputNames = append(inputNames, "prosody_features")
    inputValues = append(inputValues, prosodyTensor)
}
```

### デフォルトパラメータ

| パラメータ | デフォルト値 | 説明 |
|---|---|---|
| `noise_scale` | 0.667 | 生成のランダム性 |
| `length_scale` | 1.0 | 発話速度 (低い=速い) |
| `noise_w` | 0.8 | Duration Predictor のノイズ |
| `sample_rate` | 22050 | 出力サンプルレート |
| `sentence_silence` | 0.2s | 文間の無音 |

### GPU デバイス選択

`onnxruntime_go` がサポートする EP を統一的なデバイス文字列で指定:

| デバイス文字列 | EP | プラットフォーム |
|---|---|---|
| `cpu` | CPUExecutionProvider | 全 OS |
| `cuda` / `cuda:0` | CUDAExecutionProvider | Linux, Windows |
| `tensorrt` / `tensorrt:0` | TensorRTExecutionProvider | Linux, Windows |
| `coreml` | CoreMLExecutionProvider | macOS |
| `directml` / `directml:0` | DirectMLExecutionProvider | Windows |
| `auto` | 利用可能な最高性能 EP を自動選択 | 全 OS |

CUDA/TensorRT EP が利用不可の場合は CPU に自動フォールバックする（エラーではなく警告ログ）。

## config.json フォーマット

モデルと共に配布される設定ファイル。パス解決順:

1. 明示的指定 (`--config`)
2. 環境変数 `PIPER_DEFAULT_CONFIG` (C++/C# 互換)
3. `{model}.onnx.json` (モデル隣接)
4. `{model_dir}/config.json`

### 全フィールド一覧

実際のテストモデル (`test/models/multilingual-test-medium.onnx.json`) から確認済み:

```json
{
  "dataset": "piper",
  "audio": {
    "sample_rate": 22050,
    "quality": "medium",
    "hop_size": 256
  },
  "espeak": {
    "voice": "multilingual"
  },
  "language": {
    "code": "multilingual"
  },
  "inference": {
    "noise_scale": 0.667,
    "length_scale": 1,
    "noise_w": 0.8
  },
  "phoneme_type": "multilingual",
  "phoneme_map": {},
  "phoneme_id_map": {
    "_": [0],
    "^": [1],
    "$": [2],
    " ": [3],
    "a": [10],
    "n": [57]
  },
  "num_symbols": 173,
  "num_speakers": 1,
  "speaker_id_map": {},
  "num_languages": 6,
  "language_id_map": {
    "ja": 0, "en": 1, "zh": 2,
    "es": 3, "fr": 4, "pt": 5
  },
  "piper_version": "1.5.4",
  "prosody_num_symbols": 11,
  "prosody_id_map": {"0": [0], "1": [1], "...": "..."}
}
```

### Go 構造体マッピング

```go
type VoiceConfig struct {
    // === 推論に必須 ===
    PhonemeIDMap   map[string][]int64       `json:"phoneme_id_map"`
    Audio          AudioConfig              `json:"audio"`
    Inference      InferenceConfig          `json:"inference"`
    PhonemeType    string                   `json:"phoneme_type"`    // "openjtalk", "bilingual", "multilingual", "espeak", "text"
    NumSpeakers    int                      `json:"num_speakers"`    // default: 1
    NumLanguages   int                      `json:"num_languages"`   // default: 1
    LanguageIDMap  map[string]int64         `json:"language_id_map,omitempty"`
    SpeakerIDMap   map[string]int64         `json:"speaker_id_map,omitempty"`

    // === オプション ===
    PhonemeMap         map[string]string    `json:"phoneme_map,omitempty"`       // phoneme 置換マップ
    NumSymbols         int                  `json:"num_symbols,omitempty"`
    ProsodyNumSymbols  int                  `json:"prosody_num_symbols,omitempty"`
    ProsodyIDMap       map[string][]int     `json:"prosody_id_map,omitempty"`

    // === メタデータ (推論に不使用) ===
    Dataset        string                   `json:"dataset,omitempty"`
    Espeak         *EspeakConfig            `json:"espeak,omitempty"`
    Language       *LanguageConfig          `json:"language,omitempty"`
    PiperVersion   string                   `json:"piper_version,omitempty"`
}

type AudioConfig struct {
    SampleRate int `json:"sample_rate"` // default: 22050
    Quality    string `json:"quality,omitempty"`
    HopSize    int    `json:"hop_size,omitempty"` // default: 256, タイミング計算に使用
}

type InferenceConfig struct {
    NoiseScale float32 `json:"noise_scale"` // default: 0.667
    LengthScale float32 `json:"length_scale"` // default: 1.0
    NoiseW     float32 `json:"noise_w"`      // default: 0.8
}

// NeedsSID: multi-speaker または multilingual の場合 true
func (c *VoiceConfig) NeedsSID() bool {
    return c.NumSpeakers > 1 || c.NumLanguages > 1
}

// NeedsLID: multilingual の場合 true
func (c *VoiceConfig) NeedsLID() bool {
    return c.NumLanguages > 1
}
```

## 推論パイプライン

### テキスト → 音声の全体フロー

```
テキスト入力
    ↓
[1. 言語検出] Unicode 文字範囲でセグメント分割
    ↓
[2. 音素化] 言語別 Phonemizer で phoneme 列に変換
    ↓
[3. ID 変換] phoneme_id_map で phoneme → ID に変換
    ↓
[4. 後処理] BOS (^) / EOS ($) / PAD (_) 挿入
    ↓
[5. テンソル構築] phoneme_ids, scales, sid, lid, prosody
    ↓
[6. ONNX 推論] DynamicAdvancedSession.Run()
    ↓
[7. 音声変換] float32 → int16 ピーク正規化
    ↓
[8. WAV 出力] 44バイト RIFF ヘッダー + PCM データ
```

### Phoneme ID 変換の詳細

```
入力 phonemes: ['a', 'n', 'a']

BOS/EOS + intersperse padding 適用後:
  ['^', '_', 'a', '_', 'n', '_', 'a', '_', '$']

phoneme_id_map で変換 (実際の ID 値):
  [1, 0, 10, 0, 57, 0, 10, 0, 2]
```

- `^` = BOS (ID: 1)
- `$` = EOS (ID: 2)
- `_` = PAD (ID: 0)
- 日本語の疑問文 EOS: `?!` (強調), `?.` (平叙), `?~` (確認) — PUA エンコードされる

**注意:** PAD 挿入時、既に PAD に対応する ID を持つ phoneme の後にはPADを挿入しない（Python `base.py` と同じロジック）。

### ピーク正規化 (float32 → int16)

全実装共通のアルゴリズム。Go 1.26 のスタック割り当て改善により一時バッファがヒープを回避しやすくなる。将来的には `GOEXPERIMENT=simd` の `Float32x4` / `Float32x8` ベクトル型で SIMD 化可能な設計にしておく:

```go
// スカラー実装 (Phase 2)
// Go 1.26 スタック割り当て改善: audioInt16 が短ければスタックに配置される
func peakNormalize(audioFloat []float32) []int16 {
    var peak float32
    for _, s := range audioFloat {
        if v := abs(s); v > peak {
            peak = v
        }
    }
    if peak < 0.01 {
        peak = 0.01
    }
    scale := float32(32767.0) / peak
    audioInt16 := make([]int16, len(audioFloat))
    for i, sample := range audioFloat {
        audioInt16[i] = int16(clamp(sample*scale, -32768, 32767))
    }
    return audioInt16
}
```

WAV PCM バイト列への変換は `encoding/binary.Append` (Go 1.23) を使用し、`io.Writer` のオーバーヘッドを回避:

```go
func pcmToBytes(samples []int16) []byte {
    buf := make([]byte, 0, len(samples)*2)
    for _, s := range samples {
        buf = binary.LittleEndian.AppendUint16(buf, uint16(s))
    }
    return buf
}
```

### Phoneme タイミング

`durations` 出力テンソルからフォネーム毎の開始・終了時刻を算出:

```go
const DefaultHopLength = 256

func DurationsToTiming(durations []float32, tokens []string, sampleRate, hopLength int) []PhonemeTimingInfo {
    frameToSec := float64(hopLength) / float64(sampleRate)
    var currentTime float64
    var timings []PhonemeTimingInfo
    for i, dur := range durations {
        d := math.Max(0, float64(dur)) // 負のデュレーションは0にクランプ
        durSec := d * frameToSec
        timings = append(timings, PhonemeTimingInfo{
            Phoneme:  tokens[i],
            Start:    currentTime,
            End:      currentTime + durSec,
            Duration: durSec,
        })
        currentTime += durSec
    }
    return timings
}
```

出力フォーマット: JSON, TSV (C#/Rust 互換)。PAD/BOS/EOS トークンは出力時にスキップ。

### WAV ファイルフォーマット

```
RIFF Header (12 bytes)
├── "RIFF" (4 bytes)
├── file size - 8 (4 bytes, little-endian)
└── "WAVE" (4 bytes)

fmt Chunk (24 bytes)
├── "fmt " (4 bytes)
├── chunk size = 16 (4 bytes)
├── audioFormat = 1 (PCM) (2 bytes)
├── numChannels = 1 (mono) (2 bytes)
├── sampleRate = 22050 (4 bytes)
├── byteRate = 44100 (4 bytes)
├── blockAlign = 2 (2 bytes)
└── bitsPerSample = 16 (2 bytes)

data Chunk (8 + data bytes)
├── "data" (4 bytes)
├── data size (4 bytes)
└── int16 PCM samples (variable)
```

## Phonemizer 設計

### インターフェース

```go
// Phonemizer はテキストを phoneme 列に変換する。
// 実装は goroutine-safe でなければならない（内部に mutable state を持たない）。
type Phonemizer interface {
    // テキストを phoneme 列 + prosody 情報に変換
    PhonemizeWithProsody(text string) (PhonemizeResult, error)

    // 言語コードを返す
    LanguageCode() string

    // テキストの主要言語を検出する
    DetectPrimaryLanguage(text string) string
}

// PhonemizeResult は音素化結果。EOS を返り値に含めることで
// MultilingualPhonemizer の mutable state (last_eos) 問題を回避する。
type PhonemizeResult struct {
    Tokens   []string
    Prosody  []ProsodyInfo
    EOSToken string // 動的 EOS ("$", "?!", "?.", "?~")
}

// PostProcessIDs は内部関数（インターフェースに含めない）。
// BOS/EOS/PAD 挿入は言語非依存のため、共通ヘルパーとして実装。
func PostProcessIDs(
    ids []int64,
    prosody []ProsodyInfo,
    eosToken string,
    idMap map[string][]int64,
) ([]int64, []ProsodyInfo)
```

### 対応言語

| 言語 | コード | 方式 | Pure Go | 参考実装 |
|---|---|---|---|---|
| 日本語 | ja | G2P Engine インターフェース (後述) | 部分的 | Rust: `japanese.rs` (1157行) |
| 英語 | en | CMU辞書 + G2Pアルゴリズム | Yes | Rust: `english.rs` (1327行) |
| 中国語 | zh | Pinyin ベース | Yes | Rust: `chinese.rs` (1325行) |
| スペイン語 | es | 規則ベース | Yes | Rust: `spanish.rs` (1474行) |
| フランス語 | fr | 規則ベース | Yes | Rust: `french.rs` (1657行) |
| ポルトガル語 | pt | 規則ベース | Yes | Rust: `portuguese.rs` (1435行) |

### 日本語 Phonemizer の実現可能性

日本語は6言語中**唯一** Pure Go で完全実装できない言語。OpenJTalk の NJD パイプライン（形態素解析 → アクセント句予測 → fullcontext ラベル生成、~10,000行の言語規則）の Go 移植は非現実的（6-12ヶ月規模）。

**推奨アプローチ: C# と同様のインターフェース抽象化 (ハイブリッド方式)**

```go
// JapaneseG2PEngine は fullcontext ラベル抽出のバックエンドを抽象化。
// C# の IJapaneseG2PEngine と同等のパターン。
type JapaneseG2PEngine interface {
    ExtractFullContext(text string) ([]FullContextLabel, error)
}
```

**Phase 1: サブプロセスバックエンド** — 同梱の `jpreprocess` バイナリをサブプロセスとして呼び出し fullcontext ラベルを取得。Pure Go を維持。

**Phase 2 (オプション): CGo バックエンド** — 既存の C API (`src/cpp/openjtalk_api.h` の `openjtalk_extract_fullcontext()`) を CGo で呼び出す。ビルドタグ `//go:build cgo && openjtalk` でゲート。

**Pure Go で実装可能な部分** (~400-500行、Rust `japanese.rs` から移植):
- fullcontext ラベル → phoneme 変換 (Kurihara method)
- 文脈依存 N phoneme バリアント (`N_m`, `N_n`, `N_ng`, `N_uvular`)
- 疑問文タイプ検出 (`?!`, `?.`, `?~`)
- PUA (Private Use Area) コードポイントマッピング
- A1/A2/A3 prosody 値抽出

### Unicode 言語検出

`MultilingualPhonemizer` はテキストの Unicode 文字範囲から言語を自動検出する:

| Unicode 範囲 | 言語 |
|---|---|
| ひらがな (U+3040-309F) / カタカナ (U+30A0-30FF) / カタカナ拡張 (U+31F0-31FF) | 日本語 |
| CJK統合漢字 (U+4E00-9FFF) / CJK互換漢字 (U+F900-FAFF) / CJK拡張A (U+3400-4DBF) | かな文脈あり→日本語 / なし→中国語 |
| CJK句読点 (U+3000-303F) | 日本語 |
| 全角ラテン文字 (U+FF21-FF5A) | 別途検出 (ラテン文字とは区別) |
| ラテン文字 (基本 + 拡張) | デフォルト言語 (通常は英語) |

**注意:** ハングル (U+AC00-D7AF) は Unicode 検出で認識するが、Go 実装では韓国語 Phonemizer を提供しない（6言語対応のため）。検出はエラー報告用。

**中性文字の吸収:** 空白、数字、ASCII句読点は先行セグメントの言語に吸収される。

**ラテン文字のフォールバック:** `language_id_map` に `"en"` がない場合、`"es"` → `"fr"` → `"pt"` → 最初の言語の順にフォールバック。

### PUA (Private Use Area) エンコード

複数文字の phoneme トークン (例: `?!`, `N_m`, `a:`) は Unicode PUA コードポイント (U+E000-U+E0FF) にマッピングする。`phoneme_id_map` のキーとして使用。双方向マッピングが必要:

- **TokenToChar**: `"?!" → '\uE016'` (Phonemizer → ID 変換時)
- **CharToToken**: `'\uE016' → "?!"` (タイミング出力時)

## エラーハンドリング

Go 1.13+ の `errors.Is` / `errors.As` に対応した構造化エラー型を定義:

```go
// モデルロードエラー
type ModelLoadError struct {
    Path string
    Err  error
}

// 推論エラー (空の phoneme_ids、テンソル構築失敗等)
type InferenceError struct {
    Msg string
    Err error
}

// config エラー (ファイル不在、パース失敗、必須フィールド欠落)
type ConfigError struct {
    Path string
    Err  error
}

// Phonemizer エラー (未知の phoneme、未対応言語)
type PhonemeError struct {
    Phoneme  string
    Language string
    Msg      string
}

// phoneme_id_map に ID が見つからない
type PhonemeIDNotFoundError struct {
    Token string
}

// Sentinel errors
var (
    ErrModelClosed       = errors.New("piperplus: voice is closed")
    ErrEmptyText         = errors.New("piperplus: empty text")
    ErrEmptyPhonemeIDs   = errors.New("piperplus: empty phoneme_ids")
    ErrUnsupportedLang   = errors.New("piperplus: unsupported language")
)
```

**入力バリデーション:** `Synthesize()` は空テキスト/空 phoneme_ids に対してエラーを返す。ONNX Runtime エラーは `InferenceError` でラップする。

## API 設計

### ONNX Runtime ライフサイクル

```go
// プロセス起動時 (main() 等)
if err := piperplus.Init(os.Getenv("ONNX_RUNTIME_SHARED_LIBRARY_PATH")); err != nil {
    log.Fatal(err)
}
defer piperplus.Shutdown()
```

### 基本使用

```go
voice, err := piperplus.LoadVoice(ctx, "model.onnx")
if err != nil {
    log.Fatal(err)
}
defer voice.Close() // io.Closer を実装、idempotent (sync.Once)

result, err := voice.Synthesize(ctx, "こんにちは",
    piperplus.WithLanguage("ja"),
)
if err != nil {
    log.Fatal(err)
}

// io.WriterTo を実装 — WAV ファイルに書き出し
f, _ := os.Create("output.wav")
defer f.Close()
result.WriteTo(f)
```

### SynthesisResult

```go
type SynthesisResult struct {
    Audio      []int16       // PCM samples (22050Hz, mono, 16bit)
    SampleRate int
    Duration   time.Duration // 音声の長さ
    InferTime  time.Duration // 推論にかかった時間
    Durations  []float32     // per-phoneme duration (nil if model doesn't output)
}

// io.WriterTo — WAV ヘッダー + PCM データを書き出し
func (r *SynthesisResult) WriteTo(w io.Writer) (int64, error)

// WriteWAV — WriteTo の便利ラッパー
func (r *SynthesisResult) WriteWAV(w io.Writer) error

// RawPCMReader — WAV ヘッダーなしの PCM バイト列 (aplay, ffmpeg 等に pipe)
func (r *SynthesisResult) RawPCMReader() io.Reader

// RTF — Real-Time Factor (InferTime / Duration)
func (r *SynthesisResult) RTF() float64

// AudioFloat32 — float32 正規化済み音声 [-1.0, 1.0] (カスタム後処理用)
func (r *SynthesisResult) AudioFloat32() []float32
```

### Functional Options

```go
type SynthesisOption func(*SynthesisOptions)

type SynthesisOptions struct {
    Language    string
    SpeakerID   int64
    NoiseScale  float32 // default: 0.667
    LengthScale float32 // default: 1.0
    NoiseW      float32 // default: 0.8
}

func WithLanguage(lang string) SynthesisOption
func WithSpeakerID(id int64) SynthesisOption
func WithNoiseScale(v float32) SynthesisOption
func WithLengthScale(v float32) SynthesisOption
func WithNoiseW(v float32) SynthesisOption

// LoadVoice 用 options
type LoadOption func(*LoadOptions)

func WithConfig(path string) LoadOption
func WithDevice(device string) LoadOption // "cpu", "cuda", "auto" 等
```

### 詳細設定

```go
result, err := voice.Synthesize(ctx, "Hello, how are you?",
    piperplus.WithLanguage("en"),
    piperplus.WithSpeakerID(20),
    piperplus.WithNoiseScale(0.667),
    piperplus.WithLengthScale(1.0),
)
```

### HTTP サーバー

```go
http.HandleFunc("/synthesize", func(w http.ResponseWriter, r *http.Request) {
    text := r.URL.Query().Get("text")
    lang := r.URL.Query().Get("lang")
    result, err := voice.Synthesize(r.Context(), text, piperplus.WithLanguage(lang))
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    w.Header().Set("Content-Type", "audio/wav")
    result.WriteWAV(w)
})
```

### ストリーミング合成

長文テキストを文単位で分割し、チャンクごとに音声を生成・出力:

```go
// io.Writer にストリーミング書き出し (文単位で逐次合成)
err := voice.SynthesizeStream(ctx, longText, w,
    piperplus.WithLanguage("ja"),
)
```

内部では `TextSplitter` で文分割 → 各文を合成 → `AudioSink` インターフェースで出力。チャンク境界ではクロスフェード処理を適用。

## 並行推論

### goroutine 安全性

ONNX Runtime の `Session.Run()` はスレッドセーフ（公式ドキュメント確認済み）。`Voice` を複数 goroutine で共有可能:

```go
var wg sync.WaitGroup
for _, text := range texts {
    wg.Add(1)
    go func(t string) {
        defer wg.Done()
        result, _ := voice.Synthesize(ctx, t, piperplus.WithLanguage("ja"))
        f, _ := os.Create(fmt.Sprintf("output_%s.wav", t))
        result.WriteTo(f)
        f.Close()
    }(text)
}
wg.Wait()
```

**重要な注意点:**

1. **テンソルは goroutine 毎に生成** — セッションは共有可能だがテンソル (`ort.Tensor`) は共有不可
2. **真の並列推論** — 単一セッションの `Run()` は内部でシリアライズされる場合がある。スループットが必要なら `VoicePool` を検討
3. **Phonemizer は stateless** — Rust の `Mutex<String> last_eos` パターンは採用しない。`PhonemizeResult.EOSToken` として返す純粋関数方式で競合を回避
4. **Voice.Close() の安全性** — `sync.Once` で idempotent 化。`Synthesize()` 実行中に `Close()` が呼ばれた場合はエラーを返す (`atomic.Bool` フラグ)

### VoicePool (Phase 4)

高スループットサーバー向けのセッションプール。`database/sql.DB` パターンを参考:

```go
pool, err := piperplus.NewVoicePool(ctx, "model.onnx", 4, // 4並行
    piperplus.WithDevice("cuda"),
)
defer pool.Close()

// セマフォで並行数を制限
result, err := pool.Synthesize(ctx, text, piperplus.WithLanguage("ja"))
```

### context.Context とキャンセル

`context.Context` は全パブリック関数の第1引数。ただし ONNX Runtime 推論は単一の C 呼び出しであり、**推論中のキャンセルは `RunOptions.SetTerminate()` 経由でのみ可能**:

```go
func (e *OnnxEngine) synthesize(ctx context.Context, req *SynthesisRequest) (*SynthesisResult, error) {
    if err := ctx.Err(); err != nil {
        return nil, err // 推論前チェック
    }

    runOpts := ort.NewRunOptions()
    defer runOpts.Destroy()

    // 別 goroutine でキャンセルを監視
    done := make(chan struct{})
    go func() {
        select {
        case <-ctx.Done():
            runOpts.SetTerminate() // ONNX Runtime に中断を通知
        case <-done:
        }
    }()
    defer close(done)

    return e.session.RunWithOptions(runOpts, inputs, outputs)
}
```

## CLI 設計

cobra ベースの CLI。C#/Rust CLI と同等のオプションを提供:

### 主要オプション

| オプション | 短縮 | デフォルト | 説明 |
|---|---|---|---|
| `--model` | `-m` | `$PIPER_DEFAULT_MODEL` | ONNX モデルパス |
| `--config` | `-c` | 自動検出 | config.json パス |
| `--text` | `-t` | — | 直接テキスト入力 |
| `--language` | — | `ja` | 言語コード (`ja`, `en`, `ja-en-zh-es-fr-pt` 等) |
| `--speaker` | `-s` | `0` | Speaker ID |
| `--output-file` | `-f` | 自動生成 | 出力 WAV パス (`-` で stdout) |
| `--output-dir` | `-d` | `.` | 出力ディレクトリ |
| `--noise-scale` | — | `0.667` | 生成ノイズ |
| `--length-scale` | — | `1.0` | 発話速度 |
| `--noise-w` | — | `0.8` | DP ノイズ |
| `--sentence-silence` | — | `0.2` | 文間無音 (秒) |
| `--device` | — | `cpu` | デバイス (`cpu`, `cuda`, `auto` 等) |
| `--streaming` | — | — | raw PCM int16 を stdout に出力 |
| `--output-timing` | — | — | タイミング出力ファイル |
| `--timing-format` | — | `json` | `json` or `tsv` |
| `--custom-dict` | — | — | カスタム辞書ファイル (カンマ区切り) |
| `--batch` | — | — | バッチ入力ファイル (1行1テキスト) |
| `--list-models` | — | — | 利用可能モデル一覧 |
| `--download-model` | — | — | モデルダウンロード |
| `--debug` | — | — | デバッグログ有効化 |

### 入力モード

1. **JSONL stdin** (デフォルト): `{"phoneme_ids": [...], "speaker_id": 0}` or `{"text": "...", "language": "ja"}`
2. **`--text` モード**: 直接テキスト → 自動音素化
3. **`--batch` モード**: テキストファイルから一括変換

### 環境変数

| 変数 | 用途 |
|---|---|
| `ONNX_RUNTIME_SHARED_LIBRARY_PATH` | ONNX Runtime ライブラリパス |
| `PIPER_DEFAULT_MODEL` | `--model` のフォールバック |
| `PIPER_DEFAULT_CONFIG` | `--config` のフォールバック |
| `PIPER_MODEL_DIR` | モデルキャッシュディレクトリ |
| `PIPER_GPU_DEVICE_ID` | GPU デバイス ID のフォールバック |

## モデル管理

### ダウンロード・キャッシュ

プラットフォーム別デフォルトキャッシュディレクトリ:

| OS | パス |
|---|---|
| Linux | `$XDG_DATA_HOME/piper-plus/models/` or `~/.local/share/piper-plus/models/` |
| macOS | `~/Library/Application Support/piper-plus/models/` |
| Windows | `%APPDATA%\piper-plus\models\` |

環境変数 `PIPER_MODEL_DIR` でオーバーライド可能。

### Voice カタログ

HuggingFace 上のモデルメタデータを含むビルトインカタログ + 外部 `voices.json` のマージ方式（C# `VoiceCatalog` と同等）。

## ロギング

Go 1.21+ の `log/slog` を使用。`*slog.Logger` を `LoadOption` で注入可能:

```go
voice, err := piperplus.LoadVoice(ctx, "model.onnx",
    piperplus.WithLogger(slog.Default()),
)
```

デフォルトでは ONNX Runtime 初期化、モデルロード、デバイスフォールバックをログ出力。推論パフォーマンス (RTF) はデバッグレベル。

## 実装フェーズ

### Phase 1: プロジェクト構造・ビルドシステム ✅ 完了

**コミット:** `1ea4091` — 17ファイル, +2,231行, 30テスト

- `src/go/go.mod` (Go 1.26, onnxruntime_go v1.27.0)
- `piperplus/init.go` — ONNX Runtime `Init()`/`Shutdown()` + `sync.Once` + 環境変数フォールバック
- `piperplus/errors.go` — 構造化エラー型 5種 + sentinel 4種
- `piperplus/config.go` — `VoiceConfig` + JSON パーサー + 4段階パス解決 + バリデーション + ヘルパーメソッド
- `piperplus/doc.go` — godoc ドキュメント
- `.github/workflows/go-ci.yml` — CI (unit-test 3OS + integration-test + lint)
- `piperplus/testdata/` — テストフィクスチャ 5ファイル

### Phase 2: コア推論エンジン ✅ 完了

**コミット:** `883254b` — 10ファイル, +1,859行, 35テスト (29 unit + 6 integration)

- `piperplus/engine.go` — `OnnxEngine` + `DynamicAdvancedSession` + `ModelCapabilities` 自動検出 + テンソル動的構築
- `piperplus/voice.go` — `LoadVoice` + `SynthesizeFromIDs` + `Close` (`sync.Once` + `atomic.Bool`)
- `piperplus/wav.go` — `SynthesisResult` + `io.WriterTo` + ピーク正規化 + PCM変換
- `piperplus/timing.go` — `DurationsToTiming` + JSON/TSV 出力
- `piperplus/device.go` — `ParseDevice` + EP 設定 (CUDA/CoreML/DirectML/TensorRT) + CPU 自動フォールバック
- `piperplus/options.go` — `SynthesisRequest` + `SynthesisOption` + `LoadOption` (functional options)
- `context.Context` キャンセル (`RunOptions.Terminate()`)

### Phase 3: Phonemizer ✅ 完了

**コミット:** `024976a` — 13ファイル, +3,251行, 28テスト

- `phonemize/phonemizer.go` — `Phonemizer` インターフェース + `PhonemizeResult` (EOSToken) + `PostProcessIDs`
- `phonemize/pua.go` — PUA 双方向マッピング 87固定エントリ (JA 29 + shared 2 + ZH 43 + KO 8 + ES/PT 2 + FR 3)
- `phonemize/unicode_detect.go` — Unicode 言語検出 7段階優先度 + `SegmentText`
- `phonemize/japanese.go` — `JapaneseG2PEngine` インターフェース + Kurihara method + N変異4種 + 疑問詞マーカー
- `phonemize/english.go` — CMU辞書 + ARPAbet→IPA 変換 + 機能語デストレス
- `phonemize/chinese.go` — Pinyin→IPA + 声調変調 (T3+T3, 一, 不) + 児化音 + 音節子音
- `phonemize/spanish.go` — 規則ベース G2P (seseo) + b/d/g 異音 + ストレス
- `phonemize/french.go` — 規則ベース G2P + 鼻母音 (ɛ̃/ɑ̃/ɔ̃) + 無音子音
- `phonemize/portuguese.go` — 規則ベース G2P + 鼻母音化 + t/d口蓋化 + coda l声化
- `phonemize/multilingual.go` — Unicode セグメント分割 + 言語別委譲 + EOSToken 追跡 (mutable state なし)

### Phase 4: サーバー・ツール統合 ✅ 完了

**コミット:** `6f809a6` — 20ファイル, +2,937行, 55テスト

- `piperplus/synthesize.go` — `Voice.Synthesize(text)` phonemizer↔engine 統合
- `cmd/piper-plus/main.go` — cobra CLI (17フラグ, 3入力モード: --text/--batch/JSONL stdin)
- `piperplus/streaming.go` — `AudioSink` + `SynthesizeStream` + クロスフェード
- `piperplus/text_splitter.go` — 文分割 (JA `。` / ZH `。` / EN `.!?` 対応)
- `piperplus/pool.go` — `VoicePool` セマフォベースセッションプーリング
- `piperplus/server.go` — HTTP API (`/synthesize` GET/POST + `/health` + `/info`)
- `piperplus/jsonl.go` — JSONL 入力パーサー (phoneme_ids + text 両対応)
- `piperplus/model_manager.go` — プラットフォーム別キャッシュ + ダウンロード + 検索
- `phonemize/dict.go` — カスタム辞書 (ファイルロード + Phonemizer ラッパー)

### Phase 5: 配布・ドキュメント ✅ 完了

**コミット:** `5697ee2` — 13ファイル, +1,303行

- `src/go/README.md` — 包括的ドキュメント (API Reference, CLI Usage, GPU, Docker, HTTP API)
- `docker/Dockerfile` — Alpine multi-stage (builder + runtime, ONNX Runtime 同梱)
- `Makefile` — build/test/lint/docker/coverage/install ターゲット
- `.golangci.yml` — golangci-lint 設定
- godoc 更新: `piperplus/doc.go` + `phonemize/doc.go`
- サンプルコード 5種: `examples/{basic,server,streaming,batch,pool}/main.go`

## CI/CD 設計

### ユニットテストとインテグレーションテストの分離

| ジョブ | ONNX Runtime | テストモデル | 内容 |
|---|---|---|---|
| `unit-test` | 不要 | 不要 | Phonemizer, config, WAV, Unicode検出, ID変換 |
| `integration-test` | 必要 | 必要 | ONNX推論、end-to-end合成 |
| `lint` | 不要 | 不要 | golangci-lint + go vet |

インテグレーションテストはビルドタグ `//go:build integration` でゲート。

### ワークフロー

```yaml
# .github/workflows/go-ci.yml
name: Go CI
on:
  pull_request:
    branches: [dev]
    paths:
      - 'src/go/**'
      - '.github/workflows/go-ci.yml'
  push:
    branches: [dev]
    paths:
      - 'src/go/**'
  workflow_call:  # ci.yml から呼び出し可能

env:
  ORT_VERSION: '1.21.0'

jobs:
  unit-test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-22.04, macos-latest, windows-latest]
        go-version: ['1.26']
    runs-on: ${{ matrix.os }}
    timeout-minutes: 15
    permissions:
      contents: read
    defaults:
      run:
        working-directory: src/go
    steps:
      - uses: actions/checkout@v4
        with:
          sparse-checkout: src/go
      - uses: actions/setup-go@v5
        with:
          go-version: ${{ matrix.go-version }}
      - run: go vet ./...
      - run: go test -v -race ./...

  integration-test:
    runs-on: ubuntu-22.04
    timeout-minutes: 15
    defaults:
      run:
        working-directory: src/go
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.26'
      - name: Cache ONNX Runtime
        uses: actions/cache@v4
        with:
          path: onnxruntime
          key: onnxruntime-linux-x64-${{ env.ORT_VERSION }}
      - name: Download ONNX Runtime
        run: |
          if [ ! -f onnxruntime/lib/libonnxruntime.so ]; then
            wget -q https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz
            tar xzf onnxruntime-linux-x64-${ORT_VERSION}.tgz
            mv onnxruntime-linux-x64-${ORT_VERSION} onnxruntime
          fi
        working-directory: .
      - run: go test -v -race -tags integration ./...
        env:
          ONNX_RUNTIME_SHARED_LIBRARY_PATH: ${{ github.workspace }}/onnxruntime/lib/libonnxruntime.so
          PIPER_TEST_MODEL: ${{ github.workspace }}/test/models/multilingual-test-medium.onnx

  lint:
    runs-on: ubuntu-22.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.26'
      - uses: golangci/golangci-lint-action@v4
        with:
          working-directory: src/go
```

`ci.yml` に `go-tests` ジョブとして `workflow_call` で統合。

## テストリソース

リポジトリ同梱のテストモデルを利用:

| ファイル | サイズ | 用途 |
|---|---|---|
| `test/models/multilingual-test-medium.onnx` | 38 MB | 6言語マルチリンガルモデル |
| `test/models/multilingual-test-medium.onnx.json` | 590行 | config.json |
| `test/models/cmudict_data.json` | — | 英語 CMU 辞書 (G2P) |
| `test/models/pinyin_single.json` | — | 中国語 Pinyin (単字) |
| `test/models/pinyin_phrases.json` | — | 中国語 Pinyin (語句) |

### テストカテゴリ

| カテゴリ | ビルドタグ | 内容 |
|---|---|---|
| ユニット | (なし) | Phonemizer, config パーサー, WAV, Unicode 検出, ID 変換, エラー型 |
| インテグレーション | `integration` | ONNX 推論, end-to-end 合成, タイミング出力 |
| パリティ | `integration` | Python 参照実装との phoneme_id 列一致確認 |

## 既存実装の参考ファイル

### Rust (最も近い構造)

| ファイル | 用途 |
|---|---|
| `src/rust/piper-core/src/engine.rs` | ONNX 推論エンジン |
| `src/rust/piper-core/src/voice.rs` | 高レベル Voice API |
| `src/rust/piper-core/src/config.rs` | config.json パーサー |
| `src/rust/piper-core/src/phonemize/` | Phonemizer 実装 (7言語) |
| `src/rust/piper-core/src/streaming.rs` | ストリーミング + AudioSink |
| `src/rust/piper-core/src/timing.rs` | Phoneme タイミング |
| `src/rust/piper-core/src/gpu.rs` | GPU デバイス選択 |
| `src/rust/piper-core/src/text_splitter.rs` | テキスト分割 |
| `src/rust/piper-core/src/batch.rs` | バッチ処理 |
| `src/rust/piper-core/src/model_download.rs` | モデルダウンロード |
| `src/rust/piper-core/src/error.rs` | エラー型 (17バリアント) |
| `src/rust/piper-cli/src/main.rs` | CLI |

### C#

| ファイル | 用途 |
|---|---|
| `src/csharp/PiperPlus.Core/Inference/PiperSession.cs` | ONNX 推論 |
| `src/csharp/PiperPlus.Core/Inference/PiperModel.cs` | モデルラッパー + 能力検出 |
| `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` | セッション作成 + CUDA フォールバック |
| `src/csharp/PiperPlus.Core/Inference/StreamingWriter.cs` | ストリーミング出力 |
| `src/csharp/PiperPlus.Core/Inference/TimingWriter.cs` | タイミング出力 |
| `src/csharp/PiperPlus.Core/Config/PiperConfig.cs` | config パーサー |
| `src/csharp/PiperPlus.Core/Config/ModelManager.cs` | モデルDL + キャッシュ |
| `src/csharp/PiperPlus.Core/Config/VoiceCatalog.cs` | Voice カタログ |
| `src/csharp/PiperPlus.Core/Phonemize/` | Phonemizer 実装 (6言語) |
| `src/csharp/PiperPlus.Core/Phonemize/CustomDictionary.cs` | カスタム辞書 |
| `src/csharp/PiperPlus.Cli/Program.cs` | CLI (30+ オプション) |

### C++ (オリジナル)

| ファイル | 用途 |
|---|---|
| `src/cpp/piper.cpp` | メイン推論パイプライン (~1900行) |
| `src/cpp/piper.hpp` | 公開 API 定義 |
| `src/cpp/phoneme_ids.hpp` | Phoneme ID 変換 |
| `src/cpp/wavfile.hpp` | WAV 出力 |
| `src/cpp/openjtalk_api.h` | OpenJTalk C API (CGo 候補) |

### Python

| ファイル | 用途 |
|---|---|
| `src/python/piper_train/infer_onnx.py` | ONNX 推論スクリプト |
| `src/python/piper_train/export_onnx.py` | ONNX エクスポート (入出力仕様の参照) |

## 実装サマリー

### 統計

| 指標 | 値 |
|---|---|
| 総ファイル数 | 73 |
| 総コード行数 | ~11,600 |
| ユニットテスト | 148 |
| インテグレーションテスト | 6 |
| パッケージ数 | 3 (`piperplus`, `phonemize`, `cmd/piper-plus`) |
| サンプルコード | 5 (basic, server, streaming, batch, pool) |
| 外部依存 | 2 (`yalue/onnxruntime_go`, `spf13/cobra`) |

### Go 実装 vs 他言語比較

| 機能 | Go | Rust | C# | C++ |
|---|---|---|---|---|
| ONNX 推論 | ✅ | ✅ | ✅ | ✅ |
| 6言語 Phonemizer | ✅ | ✅ (7言語) | ✅ | ✅ |
| ストリーミング | ✅ | ✅ | ✅ | ✅ |
| GPU (CUDA/CoreML/DirectML/TensorRT) | ✅ | ✅ | ✅ | ✅ |
| HTTP API サーバー | ✅ | — | — | — |
| セッションプーリング (VoicePool) | ✅ | — | — | — |
| CLI | ✅ (cobra) | ✅ (clap) | ✅ | ✅ |
| Docker イメージ | ✅ | — | — | — |
| カスタム辞書 | ✅ | ✅ | ✅ | — |
| モデルダウンロード/キャッシュ | ✅ | ✅ | ✅ | — |
| Phoneme タイミング | ✅ | ✅ | ✅ | — |
| context.Context キャンセル | ✅ | — | CancellationToken | — |
