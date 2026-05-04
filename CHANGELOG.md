# Changelog

All notable changes to piper-plus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### iOS shared-lib を xcframework として配布開始 (Issue #377)

iOS 利用シナリオ (Dart FFI / Godot / Swift / SPM) に対応する xcframework 配布を成立させた。device (arm64) + simulator (arm64+x86_64 universal) の両 slice を含む。

- 新 artifact: `libpiper_plus-ios-v${VERSION}.xcframework.zip` (device slice + simulator universal slice)
- **`piper_plus.xcframework` は static archive** — Xcode では **"Do Not Embed"** で取り込む (リンクのみ)。`onnxruntime.xcframework` は dynamic framework のため **"Embed & Sign"** が必須
- 利用者ガイド: [`docs/guides/ios-integration.md`](docs/guides/ios-integration.md) (Dart / Godot / Swift 横断、トラブルシューティング、App Store 提出チェックリスト含む)
- Swift プロジェクト向け手順: [`examples/swift/README.md`](examples/swift/README.md)

#### Swift `import PiperPlus` を有効化する `module.modulemap` 同梱

- xcframework の各 slice の `Headers/` に `module.modulemap` を CMake で自動生成して同梱
- Swift consumer は `import PiperPlus` で `piper_plus.h` の C API surface 全体にアクセス可能
- 仕様: 非 framework 形式の `module PiperPlus { umbrella header "piper_plus.h" export * module * { export * } }`

#### Swift Package Manager マニフェスト (`Package.swift`) を repo 直下に配置

- consumer は `Package.swift` 一行 (`from: "1.13.0"`) のみで `import PiperPlus` 利用可能 — ORT は wrapper target 経由で **transitive 解決**される
- 内部構造: Swift `target` (`PiperPlus`、`@_exported import PiperPlusBinary` で C API を再エクスポート) + `binaryTarget` (`PiperPlusBinary`、xcframework.zip 参照) + `dependencies: [onnxruntime-swift-package-manager]`
- `platforms: [.iOS(.v15)]` のみ宣言 (macOS / visionOS / Mac Catalyst slice は v1.13.0 では無し、M5 候補)
- メンテナがリリースタグ push **前** に `Package.swift` の version + checksum を `dev` 上で手動更新する運用 (sherpa-onnx 方式、`Package.swift` 冒頭コメントに手順記載)
- リリース時に `release` ジョブが Package.swift の checksum が placeholder ("0000...") でないこと、および xcframework zip の SHA-256 と一致することを CI ガード

#### iOS shared-lib 取得経路を Microsoft 公式 CDN に切替

ONNX Runtime の旧 GitHub Releases zip は Microsoft が配布チャネルを CocoaPods/SPM/CDN に一本化したため削除されており、v1.11.0 以降 `Build iOS arm64` ジョブが連続失敗していた。**release ジョブの巻き添えで Linux/Windows/macOS/Android shared-lib も Releases に上がっていなかった問題を解消**。

- curl URL を `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${VERSION}.zip` に変更
- sha256 検証ステップ追加 (1.17.0 = `1623e1150507d9e5...db871`)
- CDN zip は Mach-O dylib のみで static `.a` 不在のため、利用者は `Embed & Sign Frameworks` で組込

#### `PrivacyInfo.xcprivacy` informational reference を xcframework に同梱

- xcframework root に空の Privacy Manifest (`NSPrivacyTracking=false`、3 配列空) を配置
- **注意:** Apple App Store の Privacy Manifest スキャナは `*.framework` bundle root の `PrivacyInfo.xcprivacy` を読む。static archive xcframework のルート配置は **informational reference のみ** — consumer app target で `PrivacyInfo.xcprivacy` を別途用意する必要あり
- 推奨 declaration テンプレートと Required Reason API カテゴリ (SystemBootTime / FileTimestamp / DiskSpace) を [`docs/guides/ios-integration.md`](docs/guides/ios-integration.md#app-store-submission-checklist) に記載

#### iOS リンクエラー検出 CI ガード

- `release-shared-lib.yml` の `Verify symbol resolution` を 2 段階チェックに強化
  - ORT-prefix 系 (`_Ort*` 等) の未解決 → fail (ORT version drift 検出)
  - project-internal 系 (`_piper_plus_*`, `_openjtalk_*`, `__ZN<N>piper`) の未解決 → fail (iOS 除外バグ検出)
- desktop-only TU を iOS で除外して呼び出し側だけ残るバグ (例: `openjtalk_phonemize.cpp` から `openjtalk_is_available` を呼ぶ場合) を CI で検出

### Limitations (v1.13.0 iOS xcframework)

| Item | Status | Notes |
|------|--------|-------|
| ONNX Runtime bundling | ✗ | xcframework に同梱されない。SPM 経由なら transitive 解決、それ以外は consumer が CocoaPods / 手動 DL で取得 + Embed & Sign |
| OpenJTalk 辞書 (日本語 TTS 必須) | ✗ | App Sandbox で auto-DL 不可。consumer app が `open_jtalk_dic_utf_8-1.11/` を bundle に同梱して `dict_dir` で渡す ([guide](docs/guides/ios-integration.md#step-4-japanese-tts-only-bundle-the-openjtalk-dictionary)) |
| macOS / Mac Catalyst slice | ✗ | M5 候補 — 現状 xcframework は iOS のみ。`Package.swift` も `platforms: [.iOS(.v15)]` のみ |
| visionOS / tvOS / watchOS slice | ✗ | M5 候補 — ORT visionOS 対応待ち |
| `.dSYM` for crash symbolication | ✗ | xcframework binary は stripped、別 issue 追跡 |
| App Extension / App Clip | ✗ | piper-plus + ORT (~35 MB) が 32 MB / 10 MB 制限を超過 |
| Privacy Manifest 自動スキャン | ✗ | static archive xcframework は Apple スキャナの読取り対象外、consumer app target に追加要 |
| C++ symbol leak (ODR) | ⚠ | `fmt::` / `spdlog::` / `piper::` symbols は static archive に export される。他 C++ 静的ライブラリと衝突する場合は Other Linker Flags に `-Wl,-load_hidden,...libpiper_plus.a` を追加 |

### Deprecated

#### `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (device-only、`.framework` 同梱 tar.gz)

- v1.13.0 では新 xcframework.zip と並行配布 (移行期間)
- **v1.14.0 で削除予定** — `libpiper_plus-ios-v${VERSION}.xcframework.zip` への移行を推奨
- v1.13.0 の `release-shared-lib.yml` は tar.gz 生成時に `::warning::` を出力するため利用者が deprecation を即時認識可能

### Fixed

- iOS / Linux / Windows / macOS / Android shared-lib リリースパイプラインを復旧 (Issue #377、v1.11.0 以降の停止)
  - `release` ジョブの `needs:` が `build-ios` 失敗で全 OS artifact のアップロードを止めていた

### Security

- `release-shared-lib.yml` の workflow-level permissions を `contents: read` に縮小、`release` ジョブのみ `contents: write` を opt-in
- tag validator の regex を `^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$` に anchored 化 (例: `1.0.0-malicious$(rm)` 形のタグ injection を拒否)

## [1.12.0] - 2026-05-04

### Changed (Breaking)

#### Decoder を MB-iSTFT-VITS2 に統一 (HiFi-GAN Generator 削除)

VITS の Decoder を **MB-iSTFT (Multi-Band inverse STFT) + PQMF** に完全に置き換え、HiFi-GAN `Generator` クラスを削除。`upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x` で従来と同じ総倍率を維持しつつ Decoder 計算量を削減し、CPU 推論を **2.21x 高速化** (Mean infer 168.2ms → 76.2ms, RTF 0.066 → 0.037, 100 phoneme p50)。ONNX 互換 iSTFT は DFT 行列方式 (`OnnxISTFT`) で `F.conv_transpose1d` に展開し opset 15 で動作。出力形状 `[B, 1, T]` を維持しているため、C#/Rust/Go/WASM/C++ ランタイム は変更不要 (既存 HiFi-GAN ONNX も推論側は引き続き動作)。`--quality high` も MB-iSTFT で対応 (resblock="1" + 512ch + (4,4) upsample)。

**Breaking changes:**
- `--mb-istft` フラグは廃止 (常に有効)。
- `Generator` クラス削除 — 既存 HiFi-GAN `.ckpt` からの学習再開・FT は不可。MB-iSTFT 対応の base モデル (`piper-plus-base`) と追加モデル (`piper-plus-tsukuyomi-chan` 等) を本マージ時に再公開。
- `_check_decoder_architecture_compatibility` 削除 (不要になったため)。
- `mb_istft` hparam 削除。

**保持される CLI:**
- `--c-sub-stft` (sub-band STFT loss 重み, デフォルト 1.0)
- `--sub-stft-fft-sizes` / `--sub-stft-hop-sizes` / `--sub-stft-win-sizes`

**学習済みモデル:** 6lang MB-iSTFT 75 epoch ベース + つくよみちゃん MB-iSTFT 500 epoch FT。
**実装:** `vits/mb_istft.py`, `vits/stft_onnx.py`, `vits/stft_loss.py`。Issue #268, PR #320。

#### `PiperVoice.phonemize()` の戻り値セマンティック変更

戻り値**型** `list[list[str]]` は v1.11.0 から変更ないが、**意味論が変わった**:

- **v1.11.0 以前**: 入力テキスト全体を 1 つの phoneme シーケンスとして音素化し、常に **1 要素** のリスト (`[whole_text_phonemes]`) を返していた。
- **v1.12.0 以降**: 入力テキストを終止符で文単位に分割し、文ごとに音素化して **N 要素** のリストを返す。SSML (`<speak>...`) 入力は単一ユニットとして構造保持。

**影響を受ける呼び出しパターン:**
- `phonemes_list = voice.phonemize(text); ids = voice.phonemes_to_ids(phonemes_list[0])` のように **`[0]` で固定アクセスしている既存コードは複数文を渡すと壊れる** (1 文目のみ処理されることになる)。
- 全文を一括処理したい場合は `for phonemes in voice.phonemize(text): ids = voice.phonemes_to_ids(phonemes)` に書き換える、または事前に `text` を 1 文に絞る。

**移行ガイド:** `docs/migration/v1.11-to-v1.12.md` 参照。
**実装:** `src/python_run/piper/voice.py:phonemize()` (#367)

### Added

#### 全7ランタイムで短テキスト合成品質改善 (Strategy A/B/C)

短テキスト (1-2文節) 合成時のノイズ・歪み・0秒出力問題に対する緩和策を全7ランタイム (Python/Rust/C#/C++/Go/JS-WASM/CLI) に並列実装。VITS の構造的制限 (rhasspy/piper#252) に起因する既知問題を解消。Silence Padding + Post-trim (Strategy A)、Dynamic Scales Adjustment (Strategy B)、SSML `<break>` Auto-injection (Strategy C, SSML対応4ランタイムのみ) を組み合わせる。設定仕様: `docs/spec/short-text-contract.toml` (#337)

#### Voice Cloning + SSML + Wyoming Docker 統合 (#331)

- **Voice Cloning**: 5ランタイム (Rust/C#/Go/WASM/C++) に Speaker Encoder (ECAPA-TDNN) + `speaker_embedding` テンソル対応を統合。参照音声から話者特徴を抽出し、未知話者の声質で TTS 合成可能。
- **SSML 基本サポート**: `<speak>`, `<break>`, `<prosody rate="...">` を Python/Rust/C#/Go の 4 ランタイムで実装 (W3C SSML サブセット準拠、Python 62 / Rust 39 / C# 59 / Go 67 テスト)。
- **MOS ベンチマークツール**: サンプル生成、PESQ/STOI 等メトリクス計算、調査フォーム生成 (`tools/benchmark/`)。
- **iOS/Android ビルド CI**: libpiper_plus のモバイルクロスコンパイル (iOS arm64 + Android arm64-v8a/armeabi-v7a/x86_64)。
- **Wyoming Docker**: HA 統合用の Docker Compose 環境 + ガイド (`docker/wyoming/`, `docs/guides/home-assistant.md`)。
- **モデル投稿ガイド**: `CONTRIBUTING_MODELS.md` + GitHub Issue テンプレート。

#### 汎用 Colab ファインチューニングノートブック (#324)

LJSpeech 形式 (`wavs/` + `metadata.csv`) のカスタムデータセットで piper-plus モデルをファインチューニング可能な汎用 Colab ノートブックを追加。事前学習済みベースモデル (6lang/つくよみちゃん等) からの転移学習に対応。

#### Python ランタイム ストリーミング文単位分割 (新規)

[Zenn スクラップ (kun432 氏)](https://zenn.dev/kun432/scraps/cddbfcd75b8b34) で指摘された「Python ランタイムだけ `synthesize_stream_raw()` に文単位分割が無く、HTTP `?streaming=true` でも単一チャンクで返ってしまう」問題を解消。

**新規モジュール:**
- `piper.text_splitter` (`src/python_run/piper/text_splitter.py`)
  - `split_sentences(text) -> list[str]` — 終止符 `.`/`!`/`?`/`。`/`！`/`？` および直後の閉じ括弧 (`」 』 ） ］ 】 ｣ ” ’ »` 等) を扱う
  - Rust `piper-core/src/streaming.rs::split_sentences` と同等の挙動 (post-consume 戦略)

**PiperVoice 修正:**
- `phonemize()` が複数文の入力を文ごとに音素化し `list[list[str]]` を **N 要素** で返すよう変更 (v1.11 までは常に 1 要素) — **挙動が破壊的に変わるため上記 "Changed (Breaking)" セクション参照**
- SSML (`<speak>...`) は単一ユニットとして扱い構造保持
- 既存呼び出し側 (`synthesize_stream_raw` / `synthesize_with_timing`) は無修正で複数チャンク化が動作

**互換性:**
- HTTP `?streaming=true` (PR #361 の FastAPI `StreamingResponse`) も真のチャンク配信になる
- `phonemize()` を直接呼んでいる外部コードは戻り値の要素数前提を見直す必要あり

**設定仕様:**
- `docs/spec/text-splitter-contract.toml` の Implementations 一覧に Python 実装を追加
- 終止符 6/7、閉じ括弧 14/14 (Rust と同状態、U+FF0E は spec 通り未対応)

**テスト:**
- `tests/test_text_splitter.py` (18 件) — Rust テストスイートを移植
- `tests/test_voice_streaming.py` (8 件) — `synthesize_stream_raw()` の文単位 yield と SSML ハンドリング

**関連:** PR #367 (続編元: PR #361 FastAPI 移行)

#### Python ランタイム Phoneme Timing 機能 (新規)

Python ランタイムに完全な phoneme timing 出力機能を追加。VITS Duration Predictor から音素ごとの開始時刻・終了時刻・継続時間を抽出し、JSON/TSV/SRT 形式で出力可能。

**新規モジュール:**
- `piper.timing` モジュール (`src/python_run/piper/timing.py`)
  - `PhonemeTimingInfo`, `TimingResult` データクラス
  - `durations_to_timing()`, `timing_to_json/tsv/srt()`, `timing_to_json_compact()`
  - `build_phoneme_id_reverse_map()` (PUA char 対応)

**PiperVoice 拡張:**
- `synthesize_with_timing(text, wav_file=None, ...) -> tuple[bytes, TimingResult | None]`
- `has_duration_output` プロパティ (モデル対応判定)
- `_synthesize_ids_core()` 内部メソッド (durations 取得 + original_phoneme_ids 保持)

**HTTP エンドポイント:**
- `POST/GET /api/phoneme-timing` (FastAPI、`format=json|tsv` 対応)
- `language` / `language_id` クエリパラメータで多言語対応

**設定:**
- `PiperConfig.hop_size` フィールド追加 (デフォルト 256、`config.json` の `audio.hop_size` から読込)

**互換性:**
- Rust/Go/C++/C# の既存実装と byte-for-byte 互換
- 既存の `synthesize()`, `synthesize_stream_raw()`, `synthesize_ids_to_raw()` API は完全な後方互換性を維持

**テスト:**
- `tests/test_phoneme_timing.py` (44 テスト)
- `tests/test_voice_timing.py` (22 テスト)
- `tests/test_http_timing.py` (14 テスト)
- `tests/test_config_fallback.py` に hop_size テスト 5 件追加

### Removed

- 死んだコード `src/python_run/piper/espeak_phonemizer.py` を削除 (piper-plus は推論時に espeak-ng に依存しない)
- Python ランタイムから HTS voice 依存を完全除去 (#342) — Python は pyopenjtalk-plus パスのみ。C++/Go/Rust/WASM の OpenJTalk バックエンドは引き続き利用
- Unity UPM を削除し関連ドキュメント整理 (#341)

### Changed

- HTTP server を Flask から **FastAPI に移行**、`?streaming=true` で `StreamingResponse` による真のチャンク配信に対応 (#361)
- Go Docker — Debian 化 + ORT 修正 + OpenJTalk 日本語 G2P + `serve` サブコマンド対応 (#332, #334)

### Fixed

- 短文「こんにちは。」が「あこんにちはた」と崩壊する問題を修正 (C++ ランタイム、UTF-8 コードポイントベースの文分割への置換 + 終止符直後の閉じ括弧を消費するロジック) (#363, #347, #348)
- Wyoming HA 統合エラー + Docker g2p import + リリース配布を解決 (#362)
- Go Dockerfile を `TARGETARCH` で arm64 対応 (multi-arch ビルド) (#366)
- WavLM Discriminator: safetensors 未公開モデルに合わせて `use_safetensors=False` に変更 (#353)
- Dependabot セキュリティアラート対応 (低リスク 7 件 + 高リスク 4 件) (#352, #364)
- テスト品質監査 — 全 18 件の再実装テスト修正 + 本番コード改善 (#338)
- C++ テスト全実行化 + 表面化した 11 テスト不具合修正 (#340)
- CI `changes` ジョブに checkout ステップを追加 (#339)
- crates.io 公開順序を修正 (#327)
- Pages デプロイを `dev` ブランチに限定 (#328)

### Documentation

- README の「30秒で試す」を OS 別ワンライナー化 + CLI バイナリ選択ガイド追加 (#360)
- 監査結果に基づくドキュメント全面同期 (v1.11.0 以降の差分を一括反映) (#368)
- エコシステム調査に基づく認知度・コントリビューション改善 (#329)
- npm 公開に伴うバージョン表記更新 (#330)

### Chore

- GitHub Actions runner を `ubuntu-24.04` に、Docker base を Debian trixie に更新 (#373)
- .NET 全プロジェクトを `net10.0` LTS に直接移行 (#374)
- EOL ランタイム (Node 18, Python 3.8) を更新 (#370)
- Node.js バージョンを 24 LTS に統一 (#345)
- MB-iSTFT 公開用 ckpt 変換スクリプトを復活 + `.gitignore` 補完 (#369)
- black を 26.3.1 へ更新 (Dependabot #145, #146) (#365)
- Claude Code hooks + skills で開発ワークフロー自動化 (#350)

### Tests
- 196 → 212 passed (リグレッション 0 件)

## [1.11.0] - 2026-04-06

### Added
- OpenAI 互換 TTS API エンドポイント追加 — `/v1/audio/speech` で既存の OpenAI クライアントから利用可能 (#321)
- C API 共有ライブラリ — opaque handle + ストリーミング + 配布パッケージ + FFI サンプル (#309)
- Go 推論バインディング — 6言語 G2P・ONNX 推論・CLI・サーバー (#260, #270)
- piper-g2p 独立 G2P パッケージ (Python + Rust + JS/WASM) (#300)
- 韓国語 G2P 対応 — C#・Go・npm/WASM 実装 + ドキュメント更新 (#299)
- スウェーデン語 G2P 対応 — 全プラットフォーム実装 (#297)
- WASM G2P — ES/FR/PT/ZH 実装 + テスト 841 件 (#316)
- WebUI: entrypoint 自動モデル DL — `PIPER_MODEL` 環境変数で起動時取得 (#313)
- README 多言語化 — 7言語追加 (KO/ES/PT/DE/RU/SV/HI) (#310)

### Changed
- CPU 推論 Tier 2 Quick Wins — warmup/cache/JA phonemize 全実装統一 (#318)
- dynamic_block_base + メモリアリーナ/パターン — 全実装統一 (#317)
- ONNX Runtime SessionOptions 最適化 — 全実装間で設定統一 (#315)
- コールドスタート最適化 — 初回発話レイテンシ ~2s → ~300ms (Rust/C#/WASM) (#302)
- WASM/npm パッケージ最適化 — 辞書外部化・feature gate・CI 改善 (#301)

### Fixed
- WebUI: NLTK tagger データ追加 — 英語推論の LookupError 解消 (#314)
- セキュリティ脆弱性対応 — Dependabot アラート 17 件解消 (#311)
- npm: config.json フォールバック追加 — HuggingFace 404 解消 (#304)
- Dependabot セキュリティアラート対応 — Python/Rust 依存更新 (#298)

### Documentation
- npm インストール手順追加 + NVDA リンク更新 (#293)
- npm バージョン参照を 0.1.1 に更新 (#292)
- 完了済みチケット削除 + ドキュメント誤記修正 (#312)
- 完了済み WASM G2P チケット・計画文書を削除 (#319)

### Chore
- 不要ドキュメント・壊れたデモ・WIP ワークフロー削除 (#303)

## [1.10.0] - 2026-03-28

### Changed
- PyPI パッケージ名を `piper-tts-plus` から `piper-plus` に変更 — 全レジストリ (npm, crates.io, NuGet) で名前統一 (#289)
  - `pip install piper-plus` でインストール可能に
  - 旧パッケージ `piper-tts-plus` はスタブリリースで `piper-plus` へリダイレクト予定

### Fixed
- npm: DictManager の辞書ダウンロードを GitHub Releases (r9y9/open_jtalk) に統一 — Rust/C#/C++ と同一ソース (#288)
  - 旧: HuggingFace 個別ファイル (404 エラー) → 新: tar.gz 一括 DL + SHA-256 検証 + DecompressionStream 展開
  - voice ファイル (mei_normal.htsvoice) を HuggingFace `piper-plus-base` にアップロード
  - PiperPlus._init() が DictManager.loadDictionary() + IndexedDB キャッシュを使用するように修正
  - SimpleUnifiedPhonemizer にプリロード済みデータ受け取り対応 (dictData/voiceData)
  - npm パッケージ v0.1.1 としてリリース

## [1.9.0] - 2026-03-28

### Added
- npm パッケージ `piper-plus` v0.1.0 — ブラウザ内で完全オフラインの多言語 TTS (JA/EN/ZH/ES/FR/PT) を提供 (#285)
  - OpenJTalk WASM (JA)、SimpleEnglishPhonemizer (EN)、キャラクタベース (ZH/ES/FR/PT)
  - `onnxruntime-web` による ONNX 推論、eSpeak-ng 不使用 (GPL リスク回避)
  - `PiperPlus`, `ModelManager`, `DictManager`, `AudioResult` 高レベル API
  - HuggingFace モデル自動 DL + IndexedDB キャッシュ
  - 282 テスト、CI (`npm-publish.yml`)
- PyPI パッケージ (`piper-tts-plus`) にプロジェクト説明 (README.md) を追加 (#286)

## [1.8.2] - 2026-03-24

### Added
- `export_onnx` で `emb_lang` 自動統一 (`--unify-emb-lang` / `--no-unify-emb-lang`) — シングルスピーカー多言語モデルで自動有効化 (#266, #279)
- `export_onnx` に `--unify-emb-lang-source N` オプション追加 (ソース言語インデックス指定)
- `docs/design/issue-266-auto-unify-emb-lang.md` 設計ドキュメント追加
- `emb_lang` 自動統一のユニットテスト7件 + ONNX統合テスト2件 (`test_export_onnx.py`)
- テスト用マルチリンガルモデルフィクスチャ追加 (`conftest.py`)

### Fixed
- `preprocess.py` の Windows 互換性修正 — `_HAS_SIGALRM` ガードで `signal.SIGALRM` 未対応プラットフォームでのクラッシュを回避 (#282)
- `preprocess.py` で `--timeout-seconds` が SIGALRM 未対応時にサイレント no-op になる問題に警告ログ追加

### Changed
- CLAUDE.md, training-guide.md を Issue #266 の自動 emb_lang 統一に合わせて更新
- `export_onnx` のドキュメントに `--simplify`, `--debug` オプションを追加
- `.gitignore` に `datasets/`, `models/`, `__pycache__/` 追加
- `pyproject.toml` に `VERSION` ファイルの package-data 設定追加

## [1.8.1] - 2026-03-22

### Fixed
- PyPI パッケージ (`piper-tts-plus`) の日本語音素化が空結果を返す致命的バグを修正
  - HTS ラベルパーシングを学習側と同じ正規表現ベースに書き換え (Kurihara method)
- `piper.__version__` が wheel インストール時に `"unknown"` を返す問題を修正
- wheel に `tests/` パッケージが含まれていた問題を修正

### Added
- EN/ZH/ES/FR/PT の phonemizer を runtime パッケージに追加 (6言語マルチリンガル対応)
- `MultilingualPhonemizer` (Unicode ベース言語自動検出 + ルーティング) を追加
- N バリアント規則・疑問詞マーカーを runtime 側に追加 (学習側と一致)
- 6言語統合テスト (`test_multilingual_integration.py`)
- CI: `python-tests.yml` に runtime テストステップ追加 (3 OS)
- CI: `dev-build-all.yml` に wheel ビルド後の6言語スモークテスト追加

### Changed
- `token_mapper.py` を全87エントリの多言語 PUA マッピングに更新
- `voice.py` を `piper_train` 不要のローカル `MultilingualPhonemizer` に切り替え
- `pyopenjtalk-plus>=0.4`, `g2p-en>=2.1.0`, `pypinyin>=0.50` を依存関係に追加

## [1.8.0] - 2026-03-22

### Added

#### C# (.NET) CLI
- モデル名/エイリアス自動解決 + 未ダウンロード時自動ダウンロード (`--model tsukuyomi`)
- `[[ phoneme ]]` インライン音素記法サポート
- カスタム辞書の大小文字分離・単語境界マッチング (C++パリティ)
- デフォルト辞書自動読み込み (`data/dictionaries/`)
- DotNetG2P + DotNetG2P.MeCab による日本語G2P
- DotNetG2P.English による英語G2P
- 中国語PUAマッピング + トーンマーカー修正
- `lid` (言語ID) テンソル対応
- OpenJTalk辞書自動ダウンロード (`DictionaryManager`)
- ストリーミング文分割 (`TextSplitter`)
- カスタム辞書 JSON v1/v2 形式対応
- NuGet パッケージ公開準備 (PiperPlus.Core, PiperPlus.Cli v0.1.0)

#### Rust CLI
- モデル名/エイリアス自動解決 + 自動ダウンロード (`find_model`, `resolve_model_path`)
- `--download-model` / `--model-dir` オプション追加
- `--quiet`, `--test-mode`, `--output-raw` オプション追加
- `--sentence-silence`, `--phoneme-silence` オプション追加
- `--list-models` 言語フィルタ (`--list-models ja`)
- カスタム辞書CLI統合 (テキスト/バッチ/ストリーミング全パス)
- 環境変数サポート (PIPER_DEFAULT_MODEL, PIPER_DEFAULT_CONFIG, PIPER_MODEL_DIR)
- naist-jdic をデフォルトfeatureに変更 (辞書バンドル)
- PyO3 0.22→0.23 アップグレード
- crates.io パッケージ公開準備 (piper-plus, piper-plus-cli v0.1.0)

#### CI/CD
- Rust CLIバイナリビルド (PR時3OS、リリース時5ターゲット)
- NuGet/crates.io 自動publishジョブ
- GitHub Actions を Node.js 24 対応バージョンに全面更新
- CI concurrencyグループ追加
- ARM64 QEMU DNS修正

#### 全言語共通
- `--output-file` 省略時に `output.wav` デフォルト出力
- Python モデルカタログ・ダウンロード機能追加

### Fixed
- C# ONNX推論の `lid` テンソル未送信バグ修正
- C# 中国語音素マッピング修正 (「你好」3 IDs → 15 IDs、「你好，今天天气很好。」3 IDs → 51 IDs)
- Rust 多言語推論で各言語に正しいPhonemizerを使用するよう修正
- Rust JA辞書未発見時のPassthroughPhonemizerフォールバック追加
- C# CLI統合テストの global.json rollForward修正
- C# テストのstderrレースコンディション修正
- リリースアーティファクト名衝突解消 (C#/Rust)

### Changed
- Rustクレート名: piper-core→piper-plus, piper-cli→piper-plus-cli
- C#/Rust バージョンはPyPIと独立管理 (v0.1.0)

## [1.7.0] - 2026-03-18

### 🚀 Major Features

#### Added
- **GPL-free 6言語マルチリンガルTTS** — 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語の学習パイプライン + C++ G2P。espeak-ng (GPL) 不要で6言語推論が可能 (#218)
- **WebブラウザTTS高速化基盤** — ベンチマーク・キャッシュ・WebGPU・ストリーミング対応。全97テストパス (#246)
- **C++ CLI UX大幅改善** — `--text`による直接テキスト入力、`--list-models`/`--download-model`によるモデル管理、`--version`表示 (#244)
- **C++/Python音素化パイプライン同期** — プロソディマーク挿入・文脈依存Nバリアント・疑問詞マーカー・BOS/EOS制御をC++に実装。OpenJTalkフロントエンドをpyopenjtalk-plus Cライブラリに統一。fullcontext完全一致を達成 (#229)
- **Docker テスト強化・推論テスト統合** — 8テキスト比較テスト(8/8 PASS)、python-inferenceとwebui統合、CI回帰テスト (#230)
- **ONNXエクスポートFP16デフォルト化** — `export_onnx`でFP16変換をデフォルト適用し、モデルサイズを約50%削減。`--no-fp16`フラグで無効化可能。LayerNormalization/Sigmoid/SoftmaxはFP32を維持し数値安定性を確保 (#239)

#### Changed
- **全ONNXモデルをFP16に統一 + モデル参照を6lang版に更新** — テストモデル・HuggingFace Spacesモデルを6lang FP16版に統一し、モデルカタログ(piper_plus_voices.json)を6lang版に更新。モデルサイズ約50%削減（77MB→39MB） (#256)
- CMake ExternalProjectをpyopenjtalk-plus PyPI sdistベースに統一（全プラットフォーム共通）
- OpenJTalkをスタンドアロンバイナリから静的ライブラリリンクに変更
- `openjtalk_dictionary_manager.c`にバイナリ相対パスでの辞書検索を追加
- ブランディング統一: "Piper TTS" → "piper-plus" (#232)

### 🎯 Performance

- **ORT SessionOptions最適化** — ONNX Runtimeのセッションオプション調整で10-15%速度向上 (#250)
- **WebUI ONNXセッションキャッシュ** — セッション再利用により83%高速化 (#242)

### 🔧 Improvements

#### Fixed
- **C++マルチリンガルphonemizerの全6言語動作修正** — JA以外の5言語(EN/ZH/ES/FR/PT)が動作しない問題を修正。辞書ファイル(CMU/pypinyin)をビルド成果物に同梱し、辞書検索パスを3段階探索(モデルDir→exe相対→環境変数)に拡充。`--language`指定でラテン文字言語の検出精度向上、辞書未ロード時のgraceful degradation対応 (#254)
- **config.jsonフォールバック検索の統一** — 全コンポーネントで一貫したconfig検索ロジック (#243)
- **Windows学習互換性** — Windows環境での学習パイプライン修正 + prosodyモデル置換 (#232)
- **Dockerビルドトリガー修正** — トリガーブランチをdevに修正 (#228)
- **HuggingFace Spacesデプロイ修正** — Python API呼び出しに変更 (#224)
- ExternalProject並列ダウンロードのレースコンディション修正
- `phoneme_ids.cpp`の`interspersePad=false`パスで未知phonemeによるクラッシュを防止
- CIテストをM1.5のアーキテクチャ変更(静的リンク)に適合

### 📚 Documentation
- **CLAUDE.md大幅リファクタリング** — 6言語対応完了に伴い約60%削減 (#252)
- **ユーザビリティ改善ドキュメント** — クイックスタート再構成・Windows対応ガイド追加 (#241)
- **ドキュメント全面整理・README刷新** (#225)
- READMEにバッジ追加 & 事前学習済みモデルセクション追加 (#217)

### 🧹 Maintenance
- ルートPythonスクリプト整理 (#231)
- Docker環境全面整理・CPU化 (#221)
- 未使用workflow整理 & Python最低バージョン3.11化 (#227)
- Gradio 6.9.0更新 (#226)

## [1.6.0] - 2026-02-11

### 🚀 Major Features

#### Added
- **FP16 Mixed Precisionデフォルト化** + マルチスピーカーモデル修正 (#195)
  - 学習速度2-3倍向上、GPUメモリ約50%削減
  - デフォルトで有効 (`--precision 16-mixed`)
- **OpenJTalk A1/A2/A3 prosody values** の抽出・活用 (#196)
  - Duration Predictorへの韻律情報注入
  - `--prosody-dim 16` でデフォルト有効
- **WavLM Discriminator** (#198, #212)
  - WavLMベースの知覚品質判別器
  - デフォルトで有効（学習時のみ使用、推論に影響なし）
  - FP16 Mixed Precision対応済み
- **GPL-free 英語G2P** - g2p-en (Apache-2.0) ベース (#213)
  - espeak-ng/piper-phonemize (GPL) なしで英語推論が可能
  - ストレスマーカー、機能語処理、文脈依存変換対応
- **Phonemizer ABC + 言語レジストリ** (#215)
  - 抽象基底クラスによるif/elif分岐の解消
  - 新言語追加が容易なプラグイン構造
- **疑問詞マーカー拡張 + 文脈依存「ん」バリアント** (#204, #207, #210)
  - 強調疑問 (`?!`)、平叙疑問 (`?.`)、確認疑問 (`?~`) の区別
  - 後続音に応じた「ん」の発音バリアント (N_m, N_n, N_ng, N_uvular)

#### Changed
- **デフォルト辞書の拡充** — 誤読防止エントリ追加 (#208)

### 🔧 Improvements

#### Fixed
- **ONNXエクスポートで常にdurationsを出力** (#209, #211)
- **英語G2P espeak-ng互換性の改善** (#214)

## [1.5.5] - 2025-09-25

### 🔧 Improvements

#### Fixed
- **Windows環境での日本語TTS文字化け問題** を修正 (#185)
- **Windows PowerShellビルドエラー** 修正 + ワークフローリファクタリング (#182)
- **ARMv7ビルド失敗の修正** + デバッグ機能追加 (#184)

### 📦 Build System

#### Added
- **piper-phonemize-bundled パッケージ** — クロスプラットフォームwheel対応 (#189)
- **ARMビルド用Dockerfile** の追加 (#183)

#### Changed
- PyPIリリースバージョン形式制限の削除 (#190)
- 動的VERSIONファイル更新対応 (dev/pre-release builds) (#191)
- リリースワークフローのバージョン検証順序修正 (#192)

## [1.5.2] - 2025-09-18

### 🚀 Major Features

#### Added
- **Windows版日本語音声合成の完全サポート** (#180)
  - OpenJTalkバイナリをWindows版リリースに含める
  - naist-jdic辞書（40MB）を全プラットフォームに自動同梱
  - Windows環境での日本語TTSが追加設定なしで動作

### 🔧 Improvements

#### Fixed
- **Windows環境でのパス処理の改善**
  - スペースを含むパスでの実行問題を解決
  - 8.3形式短縮パス名の自動使用
  - 一時ファイル処理の最適化

### 📦 Build System

#### Changed
- **CI/CDワークフローの強化**
  - 全プラットフォームでOpenJTalk辞書を自動ダウンロード
  - ビルドアーティファクトに日本語TTS機能を含める
  - Windows/Linux/macOSで統一された日本語音声合成機能

## [1.5.1] - 2025-09-17

### 🔧 Improvements

#### Fixed
- **piper_phonemize UTF-8エンコーディング対応** (#178)
  - テキスト処理でのエンコーディング問題を解決
  - 多言語テキストの安定した処理を実現

- **Windows 11 espeak-ng-dataディレクトリ検出問題** (#177)
  - Windows 11環境でのディレクトリ検出ロジックを改善
  - 自動ダウンロード機能との互換性向上

### 📚 Documentation

#### Added
- **日本語TTS品質向上の技術レポート** (#176)
  - 品質問題の詳細な分析
  - 改善提案と実装ロードマップ

#### Changed
- **ブランディング更新** (#175)
  - プロジェクトロゴの刷新
  - 視覚的アイデンティティの強化

### 🧪 Developer Experience

#### Added
- **PyPiパッケージ改善** (#172)
  - 音素マップモジュールをパッケージに含める
  - インストール後すぐに使える完全な機能セット

## [1.5.0] - 2025-09-02

### 🚀 Major Features

#### Added
- **マルチスピーカー → 単一話者モデル変換** (#170)
  - マルチスピーカーモデルから特定話者を抽出
  - 単一話者モデルとしてエクスポート可能
  - メモリ使用量の最適化

- **Hugging Face Spaces対応** (#168)
  - 実際のモデルファイルのアップロード機能
  - Web UIでのモデルデプロイメント
  - GitHub Pages対応の改善

- **ストリーミングTTS** (#151)
  - Raw phonemesモードでのストリーミング対応
  - リアルタイム音声合成の遅延削減
  - バッファリング最適化

- **カスタム辞書機能の大幅拡張** (#143, #149)
  - 拡張辞書フォーマット対応
  - ユーザー定義辞書の優先度制御
  - 音素マッピングの改善

### 🔧 Improvements

#### Changed
- **メモリ管理最適化** (#166, #164)
  - マルチスピーカーモデル学習時のメモリ効率改善
  - num_workers自動調整機能の削除（共有メモリ問題対応）
  - GPUメモリフラグメンテーション対策

- **日本語TTS改善** (#167, #160)
  - GitHub PagesでのWebデモ日本語モデル読み込み修正
  - カスタム辞書機能の有効化による発音改善
  - OpenJTalk統合の最適化

#### Fixed
- NumPy 2.x互換性対応 (#163)
- GitHub Actionsリリースワークフロー修正 (#162)
- Docker環境でのテスト改善 (#147)
- WebAssembly版の各種修正 (#136, #144)

### 📚 Documentation

#### Added
- Unity統合プラグイン「uPiper」情報追加 (#154)
- 英語版README作成
- WebAssembly対応ドキュメント (#150)
- ドキュメント構造の大規模再編成 (#133, #150)

### 🎯 Performance
- **音素タイミング情報出力** (#128)
  - リップシンク用タイミング情報
  - フレーム単位の音素境界情報

- **GPU最適化** (#124)
  - device_id選択機能
  - マルチGPU環境での安定性向上

### 🧪 Developer Experience

#### Added
- WebUI実装 (#131)
- Docker環境とCI/CDパイプライン構築 (#129)
- Hugging Face Spaces自動デプロイ (#134)
- GitHubスポンサーボタン追加 (#148)

#### Changed
- piper-plusブランディング更新 (#161)
- プロジェクト構造のクリーンアップ
- CSS10日本語データセット対応強化 (#117)

## [1.4.0] - 2025-08-17

### 🚀 Major Features

#### Added
- **カスタム辞書機能の大幅拡張** (#143, #149)
  - 拡張辞書フォーマット対応
  - ユーザー定義辞書の優先度制御
  - 音素マッピングの改善

- **Raw phonemesモードでのストリーミング対応** (#151)
  - リアルタイム音声合成の遅延削減
  - バッファリング最適化

- **Unity統合プラグイン「uPiper」情報追加** (#154)
  - Unity向けTTS統合
  - 英語版README作成

#### Fixed
- **日本語音声合成の発音問題を修正** (#160)
  - カスタム辞書機能の有効化
  - 発音精度の向上

- **Docker container tests改善** (#147)
  - テストスクリプトの最適化
  - CI/CD安定性向上

#### Changed
- **piper-plusブランディング更新** (#161)
  - プロジェクトクリーンアップ
  - ドキュメント構造の整理

- **ドキュメント構造の大規模再編成** (#150)
  - WebAssembly対応の追加
  - ナビゲーション改善

#### Documentation
- GitHubスポンサーボタン追加 (#148)
- Unity統合ガイド追加
- WebAssembly実装ドキュメント

## [1.3.0] - 2025-07-20

### 🎯 音声品質向上コンポーネント統合 (PR #98)

#### Added
- **EMA (Exponential Moving Average)** - 学習安定性とファインチューニング品質向上
  - デフォルトで有効 (decay rate: 0.9995)
  - `--no-ema` で無効化可能
  - `--ema-decay` で減衰率調整可能
- **AccentProcessor** - 日本語韻律・アクセント処理の高精度化
  - 拡張アクセントマーク対応 (↑↓→⤴⤵|‖)
  - prosody_ids として自動保存
  - 前処理パイプラインに統合
- **F0 Predictor** - FastSpeech2ベースのピッチ予測
  - 離散F0ビン (256レベル) による予測
  - 韻律埋め込み統合
  - SynthesizerTrn に組み込み

#### Changed
- **PyTorch Lightning 2.4.0 対応**
  - 非推奨API (`Trainer.add_argparse_args`) を削除
  - 新しいTrainer初期化方式に対応
  - DDP戦略での安定動作確認
- **依存関係の細かい指定**
  - `pytorch-lightning>=2.4.0,<2.5.0`
  - `torch>=2.0.0,<2.6.0`
  - `torchaudio>=2.0.0,<2.6.0`
  - `ruff==0.12.4` (全ファイル統一)

#### Fixed
- **セキュリティ改善**
  - `torch.load()` に `weights_only=True` を追加
  - pickle security warning を完全解決
- **分散学習最適化**
  - PyTorch Lightning ログ精度向上
  - `batch_size` と `sync_dist` の適切な設定
  - Multi-GPU環境での正確な指標計算
  - 統一ログヘルパーメソッド実装

#### Performance
- **期待される音声品質向上**
  - EMA: MOS +0.08-0.12
  - AccentProcessor: MOS +0.06-0.08  
  - F0 Predictor: MOS +0.04-0.06
  - **総合: MOS +0.18-0.26**

#### Documentation
- `src/python/docs/integrated-components-ja.md` を更新
- README.md にPR #98コンポーネント情報を追加
- Multi-GPU使用例を更新

### 🧪 テスト・検証

#### Tested
- Multi-GPU (4 x NVIDIA L4) での動作確認
- CSS10日本語データセット (6,841 utterances) での検証
- EMA, AccentProcessor, F0 Predictor の統合動作確認
- 自動学習率スケーリング (0.0002 → 0.0032)
- 有効バッチサイズ: 256

## [1.2.0] - 2025-06-29

### Added
- マルチGPU学習対応（PyTorch Lightning 2.x）
- 日本語音声合成対応（OpenJTalk統合）
- 自動ダウンロード機能

### Fixed
- 前処理済み .pt ファイル破損時の自動スキップ
- DataLoader GPU転送最適化