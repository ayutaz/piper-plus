# Piper TTS - プロジェクト概要

VITS ベースの高品質ニューラル TTS。**6言語マルチリンガルモデル**を学習済み、**8言語の G2P コード**を全7ランタイム (Python/C#/Rust/Go/JS-WASM/C++/CLI) に実装済み。

**ブランチ**: `dev` (v1.12.0 リリース済み)。v1.12.0 Breaking changes: [docs/migration/v1.11-to-v1.12.md](docs/migration/v1.11-to-v1.12.md)。

---

## 現在の状態

### 学習済みモデル (6言語マルチリンガル)

| モデル | 学習基盤 | 状態 | パス |
|-------|--------|------|------|
| **6lang base (HiFi-GAN)** | 75 epoch (v1.11 系) | 完了 (2026-03-16) | `/data/piper/output-multilingual-6lang/` |
| **6lang base MB-iSTFT** | 75 epoch スクラッチ | 完了 (2026-04-16) | `/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` |
| **つくよみちゃん 6lang-v2** | 6lang ベースから FT 500 epoch | 完了 (2026-03-16) | `/data/piper/output-tsukuyomi-finetune-6lang-v2/tsukuyomi-6lang-v2-fixed.onnx` |
| **つくよみちゃん MB-iSTFT** | 6lang MB-iSTFT ベースから FT 500 epoch | 完了 (2026-05-02) | `/data/piper/output-tsukuyomi-mb-istft-finetune/tsukuyomi-mb-istft-500epoch.onnx` |
| **CSS10 JA 6lang** | 6lang ベースから 50 epoch | 完了 (2026-03-16) | `test/models/multilingual-test-medium.onnx` |

### データセット

| データセット | 発話数 | 話者数 | シンボル | パス |
|-------------|-------|-------|---------|------|
| `dataset-multilingual-6lang-filtered` | **508,187** | 571 | 173 | `/data/piper/dataset-multilingual-6lang-filtered/` |
| `dataset-tsukuyomi-finetune-6lang` | 100 | 1 | 173 | `/data/piper/dataset-tsukuyomi-finetune-6lang/` |

**6lang 内訳:** ja 60,148 (20話者, MOE-Speech) / en 74,912 (310, LibriTTS-R) / zh 63,223 (142, AISHELL-3) / es 168,374 (63, CML-TTS) / fr 107,464 (28, CML-TTS) / pt 34,066 (8, CML-TTS)。言語コード: ja=0, en=1, zh=2, es=3, fr=4, pt=5。

**前処理:** `src/python/piper_train/tools/prepare_multilingual_dataset.py`

---

## 開発環境セットアップ

clone 直後 1 回だけ実行 (commit 時の lint drift / format drift を CI 待ち前に検出):

```bash
pip install pre-commit  # または: uvx pre-commit
pre-commit install      # .git/hooks/pre-commit を生成
```

これで `git commit` 時に ruff (check + format) と PUA consistency が自動実行され、
drift があれば commit がブロックされます (auto-fix も適用)。手動全件確認は
`pre-commit run --all-files`。

**Pre-push 段階 (opt-in、推奨):**

```bash
pre-commit install --hook-type pre-push   # .git/hooks/pre-push を追加生成
```

`git push` 直前に 4 つの contract gate (loanword / PUA / language parity /
CHANGELOG unreleased) を full-repo で実行 (~20-30 秒)。`SKIP=...` で commit
時に gate を bypass した場合でも push 前に drift を検出できる。bypass は
`git push --no-verify`。

> **Why:** PR #401 で ruff format 漏れが 2 度起きた (commits 5d9c60e6 / 8dc19e3b)。
> CI 検出 (~12 秒) → 修正 → commit → push の cycle of shame を断つため、
> ローカル commit 時点で format drift を fail-fast。CI 側にも
> `.github/workflows/pre-commit.yml` で同じ hook を gate 化済み (install 忘れ
> しても PR 時に検出)。

> **ruff version pin:** `.pre-commit-config.yaml` の `rev: vX` と
> `.github/workflows/python-lint.yml` / `.github/workflows/ci.yml` の
> `(uv) pip install ruff==X`、加えて `pyproject.toml` の 3 dependency
> group エントリ (合計 6 箇所) は同期必須。
> drift = local-clean / CI-fail mismatch (PR #401 の根本原因の一つ)。
> `scripts/check_ruff_version_sync.py` + `ruff-version-sync.yml` で
> 6 箇所一致を CI gate (本 gate がなければ Dependabot uv-workspace PR が
> pyproject.toml だけ bump → drift → 後追い PR が発生する)。

---

## 学習テンプレート

> 6lang ベース学習は完了済み。新規 FT を行う際は Template B を使う。

### Template A: 事前学習 (Multi-speaker pretraining)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir <DATASET_DIR> \
    --prosody-dim 16 \
    --accelerator gpu --devices 4 --precision 32-true \
    --max_epochs <EPOCHS> --batch-size 20 --samples-per-speaker 2 \
    --checkpoint-epochs 5 --quality medium \
    --base_lr 2e-4 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --audio-log-epochs 5 \
    --default_root_dir <OUTPUT_DIR> > training.log 2>&1 &
```

### Template B: シングルスピーカー ファインチューニング

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir <FINETUNE_DATASET> \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision 32-true \
    --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 50 --quality medium \
    --base_lr 2e-5 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --val-every-n-epochs 50 --audio-log-epochs 50 \
    --resume-from-multispeaker-checkpoint <BASE_CHECKPOINT> \
    --default_root_dir <OUTPUT_DIR> > training.log 2>&1 &
```

### A vs B 主要差分

B (FT) は A から `--devices 1`、`--base_lr 2e-5` (1/10 で catastrophic forgetting 防止)、`--batch-size 4`、`--max_epochs 500`、`--freeze-dp` 自動有効、`--audio-log-epochs 50` (Validation 頻度に合わせ) を変更。HiFi-GAN ckpt からの resume/FT は v1.12.0 で明示エラー (MB-iSTFT base から再 FT)。

---

## 実装済み機能

### Decoder & 生成

- **MB-iSTFT-VITS2 Decoder** (`vits/mb_istft.py`, `vits/stft_onnx.py`) — HiFi-GAN を完全置換、CPU Decoder 単体で **2.21x 高速化** (HiFi-GAN 168.2ms → MB-iSTFT 76.2ms / 100 phoneme p50、PR #320 内部 A/B microbench)。End-to-end の Latency P50 は README.md の Benchmark 表 (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs で **27ms**) を canonical 値とする (測定環境・テスト長が異なるため別値)。`upsample_rates=(4,4)` + iSTFT(4x) + PQMF(4x) = 256x。出力形状 `[B, 1, T]` 維持で C#/Rust/Go/WASM/C++ ランタイム変更不要。CLI: `--c-sub-stft` (sub-band STFT loss 係数; hparams `sub_stft_{fft,hop,win}_sizes` は config-only)。Issue #268, PR #320。
- **WavLM Discriminator** (`vits/models.py:WavLMDiscriminator`) — 学習時のみ知覚品質判別。GPU +1-2GB。CLI: `--no-wavlm`, `--wavlm-every-n-steps`, `--c-wavlm`。V100 では `--no-wavlm` 推奨。
- **prosody_features (A1/A2/A3)** (`vits/models.py`) — OpenJTalk 由来の韻律情報を DP 入力に活用。CLI: `--prosody-dim 16` (デフォルト)。
- **EMA + stochastic** — ONNX エクスポート時に EMA 自動適用 (チェックポイントに state あれば)。`--no-stochastic` で deterministic。

### 学習補助

- **Duration Predictor 凍結** (`vits/lightning.py:configure_optimizers`) — CLI `--freeze-dp` で DP 凍結。`--resume-from-multispeaker-checkpoint` 使用時は自動有効。テスト: `src/python/tests/test_freeze_dp.py`。
- **転移学習** (`__main__.py:load_multispeaker_checkpoint`) — CLI `--resume-from-multispeaker-checkpoint` で emb_g 除去 + emb_lang 補正 + freeze-dp を一括実行。HiFi-GAN ckpt は明示エラー。
- **言語グループ均等サンプリング** (`vits/dataset.py:SpeakerBalancedBatchSampler`) — 話者比 ≥ 3:1 で自動有効化。CLI: `--language-balanced-sampling`。
- **学習高速化** — Validation 頻度削減、DataLoader 最適化 (num_workers=2, pin_memory)、DDP `find_unused_parameters=True`。CLI: `--val-every-n-epochs`, `--limit-val-batches`, `--num-workers`, `--no-pin-memory`。
- **WandB Audio Logging** (`vits/lightning.py:on_validation_epoch_end`) — Validation 時に音声サンプルアップロード。CLI: `--audio-log-epochs`, `--num-test-examples`。
- **エネルギー VAD 高速キャッシュ** (`norm_audio/__init__.py`) — Silero ONNX VAD を numpy エネルギー VAD に置換、~25x 高速化 (~390ms → ~8ms/file)。

### ONNX エクスポート

- **FP16 デフォルト** (`export_onnx.py`) — モデルサイズ ~50% 削減。CLI: `--no-fp16` で無効化。
- **emb_lang 自動統一** (`export_onnx.py:should_unify_emb_lang`) — シングルスピーカー多言語モデルで自動有効化、声質統一。CLI: `--unify-emb-lang` / `--no-unify-emb-lang` (auto), `--unify-emb-lang-source N`。テスト: `src/python/tests/test_export_onnx.py`。
- **Speaker Embedding 入力パス** (`vits/models.py:infer`, `export_onnx.py`) — `speaker_embedding` テンソルで声質指定、speaker_id と排他。CLI: `--speaker-embedding`, `--reference-audio`, `--speaker-encoder-model`。テスト: `src/python/tests/test_speaker_embedding.py`。

### Voice Cloning

- **Speaker Encoder (ECAPA-TDNN)** (`src/python/piper_train/speaker_encoder/`) — 256 次元 L2 正規化 embedding。テスト: `test/test_speaker_encoder.py` (legacy 位置、その他は `src/python/tests/` 配下)。
- **全ランタイム統合** — Rust/C#/Go/WASM/C++ に Speaker Encoder + speaker_embedding 統合。CLI: `--reference-audio`, `--speaker-embedding`, `--speaker-encoder-model`。C API は `speaker_embedding` テンソル経路のみ動作 (ECAPA-TDNN 推論 API はスタブ、CLI 経路では動作)。

### G2P (8言語)

`MultilingualPhonemizer` が `UnicodeLanguageDetector` で言語自動検出、各言語 Phonemizer に委譲。

| 言語 | コード | 実装 | 依存 |
|------|--------|------|------|
| 日本語 | ja | JapanesePhonemizer | pyopenjtalk-plus |
| 英語 | en | EnglishPhonemizer | g2p-en (Apache-2.0) |
| 中国語 | zh | ChinesePhonemizer | pypinyin (MIT) |
| 韓国語 | ko | KoreanPhonemizer | g2pk2 (Apache-2.0, optional) |
| ES/PT/FR/SV | es/pt(=pt-BR)/pt-PT/fr/sv | 各 Phonemizer | 規則ベース (依存なし) |

> **PT BR/EU 切替:** `pt` と `pt-BR` は Brazilian Portuguese (BR、 後方互換のため `pt` は BR alias を維持)、 `pt-PT`/`pt-pt` は European Portuguese (EU、 全 8 ランタイム実装)。 `PortuguesePhonemizer(dialect=Dialect.BR | Dialect.EU)` で同一クラス内 dialect 切替。 EU は BR との 5 主要差分 (t/d palatalisation / final-e / final-s / coda-l / r-realization) を post-processing で表現。 IPA 専用 codepoint `ɨ` (中央母音) と `ɫ` (velarised lateral) を PUA contract に追加。 仕様: `docs/spec/pt-dialect-contract.toml`。

> **学習済みモデルは 6 言語 (sv/ko 未含有)、コードは 8 言語対応。**

**実装:** `src/python/g2p/piper_plus_g2p/{multilingual,japanese,english,chinese,korean,spanish,portuguese,french,swedish}.py` (学習側) / `src/python_run/piper/phonemize/` (ランタイム側)。
**ABC + レジストリ:** `g2p/piper_plus_g2p/{base,registry}.py`。

### G2P 詳細機能 (日本語)

- **疑問詞マーカー拡張** (`japanese.py:_get_question_type`) — `?!` 強調 / `?.` 平叙 / `?~` 確認 (Issue #204)。
- **文脈依存 N バリアント** (`japanese.py:_apply_n_phoneme_rules`) — 「ん」を後続音で 4 種に分類: N_m / N_n / N_ng / N_uvular (Issue #207)。

### G2P 詳細機能 (中国語)

- **ZH-EN 混在ピンイン化** (`chinese.py:phonemize_embedded_english`) — 中国語に隣接する英単語 (acronym/loanword) を米国英語ではなく Mandarin pinyin で発音。`MultilingualPhonemizer` が `[zh,en,zh]`/`[zh,en]`/`[en,zh]` パターンを自動検出してディスパッチ。辞書 (canonical source): `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` (acronyms 66 / loanwords 40 / letter_fallback 26 (A-Z))。カスタム上書きは `ChinesePhonemizer(zh_en_loanword_dict_paths=...)`。**全 10 mirror 同期** (Python canonical + Rust 2 crate / Go / C# / WASM / C++ / Kotlin Android / Swift G2P)。CI gate `ZH-EN Loanword Sync Gate / json-sync` が mirror + fixture の byte-for-byte 一致を強制 (`scripts/check_loanword_consistency.py`、`/check-loanword` skill)。Forward-compat loader: 全ランタイムで `schema_version: 2` の未来フィールド受理を pinning。Issue #384, [docs/reference/zh-en-loanword/README.md](docs/reference/zh-en-loanword/README.md)。

### ランタイム共通機能

- **CPU 推論最適化 (Tier 1-2)** — 4 言語実装で ORT セッション設定統一、Warmup 2 回 (100 phonemes、scales=[0.667,1.0,0.8])、`.opt.onnx`+`.ok` キャッシュ、JA 音素化 LRU キャッシュ (Python のみ)。仕様: `docs/spec/ort-session-contract.toml`。CLI: `--no-warmup`。env: `PIPER_DISABLE_WARMUP`, `PIPER_DISABLE_CACHE`, `PIPER_INTRA_THREADS`。
- **短テキスト合成品質改善 (Strategy A/B/C)** — 全 6 ランタイム (Python/Rust/C#/Go/WASM/C++) 並列実装。A: Silence Padding + Post-trim、B: Dynamic Scales、C: SSML `<break>` 自動挿入 (SSML 実装ランタイムでのみ)。仕様: `docs/spec/short-text-contract.toml`。
- **ストリーミング文単位分割** — 終止符 `.`/`!`/`?`/`。`/`！`/`？`/`．` で分割し文ごとに音素化・推論・yield。SSML は単一ユニット。Python: `src/python_run/piper/text_splitter.py`、Rust: `piper-core/src/streaming.rs`、他言語: 同等実装。仕様: `docs/spec/text-splitter-contract.toml`。**Breaking (v1.12.0):** Python `PiperVoice.phonemize()` が単一要素から複数要素へ (詳細: マイグレーションガイド)。
- **SSML 基本サポート** (Python/Rust/C#/Go/WASM/C++ の 6 ランタイム + G2P-only npm 解析 API) — `<speak>`, `<break>`, `<prosody rate>` を W3C サブセットで実装。実装: `g2p/piper_plus_g2p/ssml.py`, `piper-plus-g2p/src/ssml.rs` (Rust canonical), `PiperPlus.Core/Ssml/SsmlParser.cs`, `go/piperplus/ssml/parser.go`, `wasm/g2p/src/ssml.js` (npm `@piper-plus/g2p`), `src/cpp/ssml.{hpp,cpp}` (CLI `--ssml` 経由、C API 非エクスポート)。 piper-core は `piper-plus-g2p::ssml` を re-export (API 互換維持)。 piper-wasm は同パーサーを `isSsml` / `parseSsml` で WASM expose (TTS 統合は openjtalk-web の `synthesizeSsml` 側で iterate して silence 挿入 + length_scale 切替)。
- **Phoneme Timing 出力** — 全 6 ランタイム (Python/JS-WASM 新規 + Rust/Go/C++/C# 既存) で JSON/TSV/SRT 出力。`(hop_length / sample_rate) × 1000` で byte-for-byte 互換。Python: `piper.timing` モジュール、`PiperVoice.synthesize_with_timing()`、HTTP `/api/phoneme-timing`。WASM: `AudioResult.timing` (deep frozen)。仕様: `docs/spec/phoneme-timing-contract.toml`。

### ランタイム別パッケージ

| ランタイム | パッケージ | バージョン | テスト | パス |
|-----------|----------|----------|-------|------|
| Python (PyPI) | `piper-plus` | 1.12.0 | pytest 多数 | `src/python_run/piper/` |
| C# (NuGet) | `PiperPlus.Core` / `PiperPlus.Cli` | 0.3.0 | ~1000 (xUnit v3) | `src/csharp/PiperPlus.{Core,Cli}/` (TFM `net10.0`) |
| Rust (crates.io) | `piper-plus` / `piper-plus-cli` | 0.4.0 | 多数 | `src/rust/piper-{core,cli,python,wasm}/` |
| Go (Go module) | `github.com/ayutaz/piper-plus/src/go` | tag-based | 793 | `src/go/piperplus/`, `src/go/cmd/piper-plus/` |
| JS/WASM (npm) | `piper-plus` | 0.6.0 | ~1200 + 56 (Rust) | `src/wasm/openjtalk-web/`, `src/rust/piper-wasm/` |
| C API | `libpiper_plus` | shared lib | C/Dart/Godot サンプル | `src/cpp/piper_plus.{h,c_api.cpp}`, `cmake/PiperPlusShared.cmake` |
| iOS xcframework + SPM | `piper-plus` (Swift Package) | 1.13.0+ (M4) | release-shared-lib CI | `Package.swift`, `Sources/PiperPlus/`, `cmake/PrivacyInfo.xcprivacy` |
| **Kotlin/Android G2P (Maven Central)** | `io.github.ayutaz:piper-plus-g2p-android` | 1.0.0+ | L1〜L5 (kotlin-g2p-ci.yml) | `android/piper-plus-g2p/` |
| iOS / macOS Swift G2P (SPM) | `PiperPlusG2P` (Swift product, 別 xcframework `-apple-`) | 1.14.0+ | XCTest (CI) + `examples/swift-g2p/HelloG2P` CLI | `Sources/PiperPlusG2P/`, `Tests/PiperPlusG2PTests/`, `examples/swift-g2p/`, `Package.swift` (Issue #387) |
| 独立 G2P | `piper-plus-g2p` (Py/Rust)、`@piper-plus/g2p` (npm)、`src/go/phonemize` (Go)、`io.github.ayutaz:piper-plus-g2p-android` (Kotlin) | 同上 | — | `src/{python/g2p,rust/piper-plus-g2p,wasm/g2p,go/phonemize}/`、`android/piper-plus-g2p/` |

**主な追加機能 (全ランタイム共通):** モデル名自動解決 (`--model tsukuyomi` でエイリアス + 自動 DL)、カスタム辞書 (JSON v1/v2 / TSV)、`[[ phoneme ]]` インライン音素記法 (C#/Python)、`--sentence-silence` / `--phoneme-silence` 制御、`--list-models` 言語フィルタ。

### サーバー / Docker / 統合

- **OpenAI 互換 TTS API** (`docker/python-inference/inference.py`) — FastAPI ベース、`/v1/audio/speech`、`/v1/models`、`/v1/audio/speech/languages`、`/health`、`/api/phoneme-timing`。テスト: `test_openai_api.py`。
- **WebUI (Gradio)** (`docker/webui/app.py`) — 6lang モデル対応。CI: `webui-test.yml`。ドキュメント: `docs/features/webui.md`。
- **Wyoming Docker + HA 統合** (`docker/wyoming/`) — Home Assistant 連携。ガイド: `docs/guides/home-assistant.md`。
- **MOS ベンチマーク** (`tools/benchmark/`) — サンプル生成、PESQ/STOI 計算、調査フォーム生成。ドキュメント: `docs/benchmark-mos.md`。
- **iOS/Android ビルド CI** (`release-shared-lib.yml`, `cmake/ios.toolchain.cmake`) — libpiper_plus を iOS arm64 / Android (arm64-v8a/armeabi-v7a/x86_64) でクロスコンパイル。iOS は xcframework (device + simulator universal) として配信、`Package.swift` 経由で SPM 利用可能。Apple-embedded プラットフォーム検出は `PIPER_APPLE_EMBEDDED` 変数で集約 (CMakeLists.txt)、OpenJTalk 関数は `src/cpp/openjtalk_ios_stub.c` で stub 化。詳細: `docs/guides/platform/ios-integration.md`、`docs/reference/ios-shared-lib.md`。
- **モデル投稿ガイド** — `CONTRIBUTING_MODELS.md` + GitHub Issue テンプレート (`.github/ISSUE_TEMPLATE/model-{request,submission}.yml`)。

---

## 主要ファイル索引

### Python (学習側)

| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS 実装 | `src/python/piper_train/vits/` (`models.py`, `lightning.py`, `mb_istft.py`, `stft_onnx.py`, `stft_loss.py`) |
| ONNX エクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| ORT セッション管理 | `src/python/piper_train/ort_utils.py` |
| Speaker Encoder | `src/python/piper_train/speaker_encoder/` |
| データセット前処理 | `src/python/piper_train/tools/{prepare_multilingual_dataset,add_prosody_features,prepare_bilingual_dataset}.py` |

### Python (ランタイム側 + G2P)

| 用途 | パス |
|------|------|
| Voice / 音素化 | `src/python_run/piper/{voice,timing,text_splitter}.py`, `src/python_run/piper/phonemize/` |
| HTTP サーバー | `src/python_run/piper/http_server.py` (FastAPI) |
| G2P パッケージ | `src/python/g2p/piper_plus_g2p/` (基底: `base.py`, レジストリ: `registry.py`) |

### 横断的な仕様 / ドキュメント

| 用途 | パス |
|------|------|
| ORT セッション仕様 | `docs/spec/ort-session-contract.toml` |
| 短テキスト戦略仕様 | `docs/spec/short-text-contract.toml` |
| テキスト分割仕様 | `docs/spec/text-splitter-contract.toml` |
| Phoneme Timing 仕様 | `docs/spec/phoneme-timing-contract.toml` |
| ORT バージョン表 | `docs/reference/ort-versions.md` |
| マイグレーションガイド | `docs/migration/v1.11-to-v1.12.md` |

### 各言語ランタイム

| ランタイム | エントリ | テスト |
|-----------|---------|-------|
| C# | `src/csharp/PiperPlus.sln` | `src/csharp/PiperPlus.Core.Tests/` |
| Rust | `src/rust/Cargo.toml` (workspace) | `src/rust/piper-core/tests/` |
| Go | `src/go/cmd/piper-plus/` | `src/go/piperplus/`, `src/go/phonemize/` |
| WASM/npm | `src/wasm/openjtalk-web/src/index.js` | `src/wasm/openjtalk-web/test/js/` |
| C API | `src/cpp/piper_plus.h`, `piper_plus_c_api.cpp` | `src/cpp/tests/test_c_api*.cpp` |

---

## 基本コマンド

### ONNX エクスポート

```bash
# 推奨 (EMA + stochastic + FP16 + emb_lang 自動統一)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
    /path/to/checkpoint.ckpt /path/to/output.onnx
```

| オプション | 既定 | 説明 |
|-----------|------|------|
| `--no-stochastic` | - | deterministic (デバッグ用) |
| `--no-fp16` | - | FP16 変換を無効化 |
| `--unify-emb-lang` / `--no-unify-emb-lang` | auto | emb_lang 自動統一 (シングルスピーカー多言語で自動有効) |
| `--unify-emb-lang-source N` | 0 | emb_lang 統一のソース言語 index |
| `--simplify` | - | ONNX simplification 適用 |
| `--debug` | - | デバッグログ |

### 推論

```bash
# テキスト直接 (6lang multilingual)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model <model.onnx> --config <config.json> --output-dir <out> \
    --text "こんにちは" --language ja-en-zh-es-fr-pt --speaker-id 0 --noise-scale 0.667

# Voice Cloning (参照音声から)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model <model.onnx> --config <config.json> --output-dir <out> \
    --text "こんにちは" \
    --reference-audio <ref.wav> --speaker-encoder-model <encoder.onnx> \
    --language ja-en-zh-es-fr-pt
```

`--language` の言語コード順は任意 (内部で canonical key に正規化)。

**JSONL 入力 (phoneme_ids 直接指定):**

```bash
cat test.jsonl | uv run python -m piper_train.infer_onnx --model <model.onnx> --output-dir <out>
# 1 行 1 発話: {"phoneme_ids": [...], "speaker_id": 0, "prosody_features": [{"a1": -2, ...}]}
```

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| 推論音声が「ピー」音 | DP 学習失敗。`--samples-per-speaker` を使う / `--disable_auto_lr_scaling` / `--base_lr 1e-4` |
| GPU OOM | `NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1` / batch_size と samples_per_speaker を下げる / 異なる batch size からの resume を避ける |
| 学習速度が遅い (V100) | `--precision 32-true` (FP16-mixed は backward 29-40s に劣化) / ゾンビ GPU プロセス確認 (`nvidia-smi --query-compute-apps=pid,used_memory --format=csv`) / `--max-phoneme-ids 400` / `--val-every-n-epochs 10` / `--limit-val-batches 20` / `--no-wavlm` |
| ONNX 変換エラー | `CUDA_VISIBLE_DEVICES=""` で CPU モード |
| HiFi-GAN ckpt resume 失敗 | v1.12.0 で `Generator` 削除。MB-iSTFT base から再 FT (`piper-plus-base/model.ckpt`)。詳細: マイグレーションガイド |

---

## 外部リソース

| リソース | URL |
|----------|-----|
| 6lang ベース ckpt | `ayousanz/piper-plus-base` (HF) |
| つくよみちゃん ONNX | `ayousanz/piper-plus-tsukuyomi-chan` (HF) |
| CSS10 JA ONNX | `ayousanz/piper-plus-css10-ja-6lang` (HF) |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` (HF) |
| パッケージレジストリ | PyPI / NuGet / crates.io / npm — それぞれ `piper-plus` または `PiperPlus.*` で検索 |

---

## Automation (skill / hook / pre-commit)

開発作業の繰り返しを skill / pre-commit / pre-push gate に落とし込んでいる。 詳細仕様は [.claude/README.md](.claude/README.md)。 主要 skill 一覧:

| skill | 用途 |
|-------|------|
| `/create-pr` | push 済 branch から構造化 PR 本文を作成 (auto chain で `/watch-pr` / `/check-review-backlog` 発動) |
| `/watch-pr <PR>` / `/watch-ci-patterns` | CI 監視、 failure を flake/drift/env/test bug に分類 |
| `/reply-review <PR>` | unresolved review thread への返信 + resolve |
| `/check-review-backlog` | open PR の review backlog 集計 |
| `/precheck` / `/check-pr-ready` / `/run-tests` | scope 自動判定で local CI equivalent を実行 |
| `/commit` / `/sync-docs` | コミット前 ドキュメント整合性 + 構造化メッセージ |
| `/check-loanword` / `/check-pua` / `/check-runtime-parity` / `/check-cross-runtime` / `/check-new-runtime-asset` | cross-runtime 同期検査 |
| `/add-language <code>` / `/review-language <code>` | 新言語追加と 10 エージェント並列レビュー |
| `/release-prep` / `/prepare-release` | リリース確認 (read-mostly) と bump 適用案 |
| `/publish-model` | 学習 ckpt → export + sanity + bench + HF upload chain |
| `/bump-deps` | ORT/openjtalk/ruff の cross-runtime canonical sync 更新 |
| `/skill-health` | skill / hook 自身の health check (frontmatter / script 参照 / trigger 衝突) |

pre-commit / pre-push gate は `.pre-commit-config.yaml` に集約 (50+ hook、 contract gate 18+、 cross-language formatter 6 言語)。 各 hook の trigger 条件と既知パターンは [.claude/README.md](.claude/README.md) を参照。

---

## アーカイブ: バイリンガル版 (v2/v3/v4) の履歴

v2/v3/v4 は 6lang に置き換え済み。詳細・旧データセットパス・つくよみちゃん FT 履歴 (v3→v4→6lang-v2 の段階的改善、`emb_lang` コピーや `--freeze-dp` の learnings) は git 履歴 (`git log --grep="bilingual\\|v[234]"`) または `CHANGELOG-archive.md` を参照。
