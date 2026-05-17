# piper-plus リリース QA デバッグチェックリスト

> **目的**: 次期リリース (CHANGELOG `[Unreleased]` = Kotlin/Android G2P #388 + ZH-EN code-switching #384 + Swift G2P #387) の
> 全ランタイム品質をローカルで網羅検証する。エッジケース・境界条件まで含む。
> **対象ブランチ**: `dev` / **作成日**: 2026-05-17 / **実行者**: Claude Code (ローカル Windows 11)

---

## QA 実行結果サマリ (2026-05-17 実行)

全 7 ランタイムの機能テスト・契約ゲート・エッジケース・E2E を実行。**機能面のリリースブロッカーは検出されず。**

### テスト結果 (環境要因の失敗を除き全 PASS)

| 対象 | 結果 |
|------|------|
| Python runtime / g2p / train / fuzz | 545 / 1291 / 833 / 8 passed |
| Rust core+g2p+cli+wasm | 全合格 (piper-plus-python のみ Py3.14 で実行不可=環境) |
| C# | 1392 passed / 1 skipped |
| C++ ctest | 40/40 passed |
| WASM / npm | 774 / 775 (1 skip) |
| Go phonemize | 合格 (piperplus は CGO 無効=環境) |
| Kotlin G2P L1 | 23/24 (1 失敗は下記 CRLF アーティファクト) |
| 契約ゲート | 48/50 実質 PASS (リポジトリバグ 0) |
| 推論エッジ 14 種 / E2E | 全 14 クラッシュなし / 13 TTS 合成成功 |

### 検出 finding

| ID | 重要度 | 内容 |
|----|--------|------|
| F1 | 🟡 | `.gitattributes` に `*.go` の `eol=lf` ルール欠落 (`.py/.c/.cs` 等にはある) → Windows で gofmt 全件誤検出 |
| F5 | 🟡 | `piper-phonemize==1.1.0` に Windows wheel/sdist 無し → root `preprocess` extra が Windows install 不可、`uv sync --all-extras` 失敗 |
| F6 | 🟡 | 契約ゲート 15+ 本が Windows 日本語(cp932)コンソールで `print()` クラッシュ (`PYTHONUTF8=1` で全 PASS) |
| F7 | 🟡 | `check_secret_path_reference` が `build/` を除外せず + ALLOWLIST がパス区切り依存 → Windows で 30 件誤検出 |
| F2/F3/F4 | 🟢 | openjtalk-web lint 債務 95 件(非 CI ゲート) / Korean テスト脆弱性 / `pytest-asyncio` 欠落警告 |
| CRLF | 🟢 | Python 側 loanword JSON 2 件が working tree で CRLF (repo blob は LF、CI 緑) → loanword gate と Kotlin L1 のローカル失敗原因 |

### 環境制約 (this PC 固有、リポジトリ問題ではない)

- **piper-plus-python** (Rust): ローカル Python 3.14 + PyO3 0.24.2 非互換 — CI は 3.12 で `cargo check`、問題なし
- **Go piperplus/cmd**: CGO 必須 (`onnxruntime_go`)、mingw-w64 gcc 不在でローカルビルド不可 — CI Windows runner には gcc あり

---

## 凡例

| 記号 | 意味 |
|------|------|
| ✅ | Windows ローカルで実行可能 |
| ⚠️ | 追加セットアップが必要 (下記 Phase 0 参照) |
| ❌ | ローカル不可 — CI / 学習サーバー / macOS 専用 |
| 状態列 | 実行時に `PASS` / `FAIL` / `SKIP` を記入 |

**実行方法**: 各 Phase を上から順に実行。`FAIL` 時は原因を切り分けてから次へ。
Phase 1〜4 は全 PASS が必須ゲート。Phase 5〜11 はリリース判断材料。

---

## Phase 0: 環境準備 & ツール可用性

確認済みローカルツール (2026-05-17 時点):

| ツール | バージョン / 場所 | 状態 |
|--------|------------------|------|
| uv | 0.11.8 | ✅ |
| Python | 3.14.3 (※CI は 3.11/3.13 — version 起因の差異に注意) | ✅ |
| .NET SDK | 10.0.204 | ✅ |
| cargo / rustc | 1.92.0 | ✅ |
| go | 1.26.1 | ✅ |
| node / npm | 24.15.0 / 11.4.2 | ✅ |
| cmake | 3.28.1 | ✅ |
| gh | 2.76.1 | ✅ |
| C++ (MSVC) | VS 2026 Community + Build Tools 2022、Windows SDK 10.0.26100 導入済 | ✅ |
| Docker | 29.2.1 | ✅ |
| JDK 17 | Microsoft OpenJDK 17.0.16 (`JAVA_HOME` 設定済、※PATH の `java` は 8) | ✅ |
| Android Studio / SDK | Studio + SDK + emulator + NDK 群導入済 (`%LOCALAPPDATA%\Android\Sdk`) | ⚠️ NDK 26.1.10909125 / platform-35 のみ追加 DL 要 |
| wasm32 target | rustup 導入済 | ⚠️ `wasm-pack` のみ追加要 |
| pre-commit | 未インストール | ⚠️ `uvx pre-commit` で都度実行 |
| Swift / Xcode | — | ❌ macOS 必須 — この PC では不可 |

| # | 準備項目 | コマンド | 合格条件 | 可否 | 状態 |
|---|---------|---------|---------|------|------|
| 0.1 | Python 依存同期 | `uv sync` | エラーなし | ✅ | |
| 0.2 | Rust 依存取得 | `cd src\rust && cargo fetch` | エラーなし | ✅ | |
| 0.3 | .NET 依存復元 | `dotnet restore src\csharp\PiperPlus.sln` | エラーなし | ✅ | |
| 0.4 | Go 依存取得 | `cd src\go && go mod download` | エラーなし | ✅ | |
| 0.5 | npm 依存 (g2p ローカルリンク) | `cd src\wasm\openjtalk-web && npm install "@piper-plus/g2p@file:../g2p"` | エラーなし | ✅ | |
| 0.6 | テストモデル存在確認 | `test\models\multilingual-test-medium.onnx` (+ `.json`, `.cpu.opt.onnx`) | 3 ファイル存在 | ✅ | |
| 0.7 | wasm-pack 導入 | `cargo install wasm-pack --locked` | `wasm-pack --version` 応答 | ✅ | |
| 0.8 | C++ configure 確認 | `cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTS=ON` | configure 成功 (cmake 3.28 は VS17/Build Tools 2022 を使用) | ✅ | |
| 0.9 | Android SDK パス設定 | `$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"` または `android\local.properties` に `sdk.dir` を記述 | gradlew が SDK 検出 | ✅ | |
| 0.10 | Android NDK / platform 追加 | `& "$env:LOCALAPPDATA\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat" "ndk;26.1.10909125" "platforms;android-35"` | インストール完了 | ✅ | |

---

## Phase 1: Lint / Format (6 ランタイム)

| # | 項目 | コマンド | 合格条件 | 可否 | 状態 |
|---|------|---------|---------|------|------|
| 1.1 | Python ruff check | `uv run ruff check src/python_run/ src/python/` | 違反 0 | ✅ | |
| 1.2 | Python ruff format | `uv run ruff format --check src/python_run/ src/python/` | 差分 0 | ✅ | |
| 1.3 | Rust fmt | `cd src\rust && cargo fmt --all -- --check` | 差分 0 | ✅ | |
| 1.4 | Rust clippy | `cd src\rust && cargo clippy --workspace --all-features -- -D warnings` | warning 0 | ✅ | |
| 1.5 | C# format | `dotnet format src\csharp\PiperPlus.sln --verify-no-changes --no-restore` | 差分 0 | ✅ | |
| 1.6 | Go vet | `cd src\go && go vet ./... ./phonemize/...` | 警告 0 | ✅ | |
| 1.7 | Go fmt 差分 | `cd src\go && gofmt -l . phonemize` | 出力 0 行 | ✅ | |
| 1.8 | JS lint | `cd src\wasm\openjtalk-web && npm run lint` | エラー 0 (script があれば) | ✅ | |
| 1.9 | C++ clang-format | `pre-commit run clang-format --all-files` | 差分 0 | ⚠️ clang 要 | |
| 1.10 | ruff バージョン同期 (6 箇所) | `uv run python scripts/check_ruff_version_sync.py` | 一致 | ✅ | |

---

## Phase 2: ビルド検証

| # | 項目 | コマンド | 合格条件 | 可否 | 状態 |
|---|------|---------|---------|------|------|
| 2.1 | Python editable install | `uv pip install -e src/python/g2p -e src/python -e src/python_run` | import 成功 | ✅ | |
| 2.2 | Rust workspace build | `cd src\rust && cargo build --release --workspace` | 成功 | ✅ | |
| 2.3 | Rust naist-jdic feature | `cd src\rust && cargo build -p piper-plus --features naist-jdic` | 成功 | ✅ | |
| 2.4 | C# Release build | `dotnet build src\csharp\PiperPlus.sln -c Release --nologo` | 成功 | ✅ | |
| 2.5 | C# CLI self-contained publish | `dotnet publish src\csharp\PiperPlus.Cli\PiperPlus.Cli.csproj -c Release -r win-x64 --self-contained true -o publish/` | バイナリ生成 | ✅ | |
| 2.6 | Go build (全パッケージ + CLI) | `cd src\go && go build ./... && go build -o bin\piper-plus.exe ./cmd/piper-plus` | 成功 | ✅ | |
| 2.7 | C++ cmake build (tests 付き) | `cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTS=ON && cmake --build build --config Release` | 成功 (初回は ORT/piper-phonemize 取得で数十分) | ✅ | |
| 2.8 | WASM build | `cd src\rust\piper-wasm && wasm-pack build --target web --release --features multilingual` | pkg 生成 | ✅ (要 0.7) | |
| 2.9 | C API shared lib | `cmake --build build --config Release --target piper_plus_shared` | `.dll` 生成 | ✅ | |
| 2.10 | Kotlin G2P AAR | `cd android && .\gradlew.bat :piper-plus-g2p:assembleRelease` | AAR 生成 | ✅ (要 0.9/0.10) | |

---

## Phase 3: ユニットテスト (全ランタイム)

| # | 項目 | コマンド | 合格条件 | 可否 | 状態 |
|---|------|---------|---------|------|------|
| 3.1 | Python ランタイム | `cd src\python_run && uv run pytest tests/ -o addopts="" --tb=short -q` | 全 PASS | ✅ | |
| 3.2 | Python G2P パッケージ | `cd src\python\g2p && uv run pytest -o addopts="" --tb=short -q` | 全 PASS | ✅ | |
| 3.3 | Python 学習側 (unit のみ) | `cd src\python && uv run pytest tests/ -o addopts="" -m "unit and not training and not benchmark and not inference" --tb=short -q` | 全 PASS | ✅ | |
| 3.4 | Python 学習側 (inference) | `cd src\python && uv run pytest tests/test_export_onnx.py tests/test_infer_onnx.py -o addopts="" --tb=short -q` | 全 PASS | ⚠️ torch 要 | |
| 3.5 | Rust piper-plus | `cd src\rust && cargo test -p piper-plus --no-fail-fast` | 全 PASS | ✅ | |
| 3.6 | Rust naist-jdic feature | `cd src\rust && cargo test -p piper-plus --features naist-jdic --no-fail-fast` | 全 PASS | ✅ | |
| 3.7 | Rust G2P crate | `cd src\rust && cargo test -p piper-plus-g2p --no-fail-fast` | 全 PASS | ✅ | |
| 3.8 | Rust WASM (ja-external) | `cd src\rust && cargo test -p piper-plus-wasm --features ja-external --no-fail-fast` | 全 PASS | ✅ | |
| 3.9 | C# 全テスト (~1000) | `dotnet test src\csharp\PiperPlus.sln -c Release --no-build --nologo --verbosity minimal` | 全 PASS | ✅ | |
| 3.10 | Go (race 付き) | `cd src\go && go test -race -count=1 ./... ./phonemize/...` | 全 PASS | ✅ | |
| 3.11 | Go 統合テスト | `cd src\go && go test -tags=integration -count=1 ./...` | 全 PASS | ✅ | |
| 3.12 | JS/WASM npm package | `cd src\wasm\openjtalk-web && npm run test:npm-package:all` | 全 PASS | ✅ | |
| 3.13 | C++ ctest | `ctest --test-dir build -C Release --output-on-failure` | 全 PASS | ✅ | |
| 3.14 | C++ Debug ビルドでも実行 | `cmake --build build --config Debug && ctest --test-dir build -C Debug --output-on-failure` | 全 PASS | ✅ | |
| 3.15 | Kotlin G2P L1 単体テスト | `cd android && .\gradlew.bat :piper-plus-g2p:testDebugUnitTest` | 全 PASS (18 件) | ✅ (要 0.9/0.10) | |

---

## Phase 4: 契約ゲート / クロスランタイム整合性

### 4.0 一括実行 (推奨スタート点)

| # | 項目 | コマンド | 合格条件 | 可否 | 状態 |
|---|------|---------|---------|------|------|
| 4.0 | pre-commit 全 hook | `uvx pre-commit run --all-files` | 全 hook PASS | ⚠️ | |

> 4.0 が FAIL した hook を 4.1〜4.4 で個別に切り分ける。各スクリプトは `uv run python scripts/<name>.py` で単体実行可。

### 4.1 クロスランタイム同期 (10 ミラーの byte-for-byte 一致)

| # | 項目 | コマンド | 状態 |
|---|------|---------|------|
| 4.1.1 | ZH-EN loanword 同期 | `uv run python scripts/check_loanword_consistency.py` (or `/check-loanword`) | |
| 4.1.2 | loanword forward-compat | `uv run python scripts/check_loanword_forward_compat.py` | |
| 4.1.3 | PUA テーブル整合 | `uv run python scripts/check_pua_consistency.py` (or `/check-pua`) | |
| 4.1.4 | 辞書整合 / バージョン | `uv run python scripts/check_dictionary_consistency.py` / `check_dictionary_versions.py` | |
| 4.1.5 | 言語パリティ (8 言語 × 7 ランタイム) | `uv run python scripts/check_language_parity.py` | |
| 4.1.6 | CLI フラグ / help パリティ | `uv run python scripts/check_cli_flag_parity.py` / `check_cli_help_drift.py` | |
| 4.1.7 | voice カタログパリティ | `uv run python scripts/check_voice_catalog_parity.py` | |
| 4.1.8 | workspace Python パリティ | `uv run python scripts/check_workspace_python_parity.py` | |

### 4.2 契約 spec ドリフトゲート

各 `docs/spec/*-contract.toml` に対する drift 検査。コマンドパターン `uv run python scripts/check_<name>.py`:

| # | 対象スクリプト | 状態 |
|---|---------------|------|
| 4.2.1 | `check_audio_format_contract` / `check_ort_session_contract` / `check_ort_provider_contract` | |
| 4.2.2 | `check_short_text_contract` / `check_text_splitter_contract` / `check_ssml_contract` | |
| 4.2.3 | `check_phoneme_timing_contract` / `check_streaming_api_contract` | |
| 4.2.4 | `check_swift_g2p_contract` / `check_pt_dialect_contract` / `check_speaker_encoder_contract` | |
| 4.2.5 | `check_inference_input_contract` / `check_onnx_export_contract` / `check_onnx_inputs` | |
| 4.2.6 | `check_language_id_map_contract` / `check_chinese_tone_contract` / `check_japanese_n_variant_contract` | |
| 4.2.7 | `check_phoneme_set_version` / `check_spec_meta` | |

### 4.3 G2P ゴールデン fixture パリティ (419 ケース)

| # | 項目 | コマンド | 合格条件 | 状態 |
|---|------|---------|---------|------|
| 4.3.1 | Python ↔ ゴールデン一致 | `cd src\python\g2p && uv run pytest -o addopts="" -k "golden or parity or fixture" -q` | 全 PASS | |
| 4.3.2 | Rust ↔ ゴールデン一致 | `cd src\rust && cargo test -p piper-plus-g2p golden --no-fail-fast` | 全 PASS | |
| 4.3.3 | Go ↔ ゴールデン一致 | `cd src\go && go test ./phonemize/... -run Golden -count=1` | 全 PASS | |
| 4.3.4 | fixture 再生成で差分が出ないこと | `uv run python scripts/regenerate_g2p_golden_fixtures.py --check` | 差分 0 | |

---

## Phase 5: G2P エッジケース / 境界テスト (モデル不要)

> 各項目は 8 言語 (ja/en/zh/ko/es/fr/pt/sv) の G2P に対し「クラッシュしない + 期待音素列」を確認。
> 既存テスト (`test_edge_cases.py`, `test_ssml_attacks.py`, `tests/fuzz/`) を実行 + 下記の入力を手動プローブ。

### 5.1 入力境界

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 5.1.1 | 空文字列 `""` | 空結果を返す / 例外なし | |
| 5.1.2 | 空白のみ `"   "` / `"\t\n"` | クラッシュなし | |
| 5.1.3 | 単一文字 (各言語: `あ` `a` `中` `한` `é` `ã`) | 正常音素化 | |
| 5.1.4 | 制御文字 / ゼロ幅 (U+200B) / BOM (U+FEFF) | サニタイズ or 安全に無視 | |
| 5.1.5 | 超長文 (phoneme id > 400) | `--max-phoneme-ids` 切り詰め挙動が定義通り | |
| 5.1.6 | スペースなしの超長単語 (1000 文字) | OOM / ハングなし | |
| 5.1.7 | 数字 (`123` `3.14` `-5` `1,000,000` `2026年`) | 各言語の数詞展開 | |
| 5.1.8 | 記号のみ (`...!?` `@#$%` `()[]`) | クラッシュなし | |
| 5.1.9 | 絵文字混在 (`hello 😀 world`) | 絵文字をスキップ / 安全処理 | |
| 5.1.10 | Unicode 正規化差異 (NFC vs NFD の `é`) | 同一音素列を返す | |

### 5.2 多言語 / 言語自動検出

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 5.2.1 | スクリプト混在 `日本語とEnglishと中文` | 各セグメントを正しい言語へディスパッチ | |
| 5.2.2 | ZH-EN: `请打开 GPS` (acronym) | GPS が pinyin 経路 (Issue #384) | |
| 5.2.3 | ZH-EN: `我喜欢用 Python 写代码` (loanword) | Python が pinyin 経路 | |
| 5.2.4 | ZH-EN: `让我用 ChatGPT 写代码` (混成) | letter fallback 経路 | |
| 5.2.5 | ZH-EN dispatch opt-out | Rust `enable_zh_en_dispatch(false)` / Go `SetZhEnDispatch(false)` / C# `EnableZhEnDispatch=false` / WASM `setZhEnDispatch(false)` で米国英語経路に戻る | |
| 5.2.6 | 言語検出の曖昧入力 (ローマ字日本語 `konnichiwa`) | 定義通りの言語にフォールバック | |

### 5.3 言語固有ルール

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 5.3.1 | 日本語 疑問詞マーカー `?!` `?.` `?~` | 強調/平叙/確認の 3 分岐 (Issue #204) | |
| 5.3.2 | 日本語 N バリアント | `さんぽ`(N_m) `あんない`(N_n) `りんご`(N_ng) 他 (Issue #207) | |
| 5.3.3 | 日本語 長音/促音/拗音 | `コーヒー` `がっこう` `きょう` 正常 | |
| 5.3.4 | 英語 OOV 単語 / 大文字略語 | g2p-en フォールバック | |
| 5.3.5 | 中国語 多音字 (声調) | `行` (xíng/háng) など文脈依存 | |
| 5.3.6 | 韓国語 連音化 | g2pk2 ルール (任意依存、未導入時スキップ) | |
| 5.3.7 | ES/FR/SV 言語固有文字 | `ñ ç å ö ü ã õ` を正しく音素化 | |
| 5.3.8 | PT BR/EU dialect 切替 | `pt` (BR) と `pt-PT` (EU) で 5 差分が反映 | |

### 5.4 PUA / multi-codepoint 音素

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 5.4.1 | multi-codepoint 音素 `ɔɪ` `œ̃` `ɐ̃` | PUA マッピングが 1 トークンとして処理 | |
| 5.4.2 | PT-EU 専用 codepoint `ɨ` `ɫ` | PUA contract に登録済み | |
| 5.4.3 | PUA contract 4 不変条件 | `/check-pua` skill 実行 | |

### 5.5 SSML

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 5.5.1 | `<break time="500ms"/>` / `strength` | break 挿入 | |
| 5.5.2 | `<prosody rate="slow">` / ネスト prosody | length_scale 反映 | |
| 5.5.3 | 不正 SSML (未閉じタグ / 無効属性 / 無効 time 値) | graceful にエラー or 無視 | |
| 5.5.4 | `<speak>` ルートなし / 空 `<speak></speak>` | クラッシュなし | |
| 5.5.5 | XML エンティティ `&lt; &amp; &#xtest;` | 正しくデコード | |
| 5.5.6 | SSML インジェクション攻撃 | `cd src\python_run && uv run pytest tests/test_ssml_attacks.py -o addopts="" -q` | |

### 5.6 カスタム辞書 / インライン音素

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 5.6.1 | カスタム辞書 JSON v1 / v2 / TSV | 3 形式すべて読込成功 | |
| 5.6.2 | 辞書の重複エントリ / 不正ファイル | 定義通りの優先順位 / エラー | |
| 5.6.3 | インライン音素 `[[ h ə l oʊ ]]` | 音素を直接採用 | |
| 5.6.4 | インライン異常系 (`[[]]` 空 / 未閉じ `[[` / 未知音素) | graceful | |

### 5.7 Fuzz テスト

| # | 項目 | コマンド | 状態 |
|---|------|---------|------|
| 5.7.1 | Python fuzz 3 種 | `cd src\python_run && uv run pytest tests/fuzz/ -o addopts="" -q` | |
| 5.7.2 | Rust cargo-fuzz (短時間) | `cd src\rust\piper-plus-g2p && cargo +nightly fuzz run <target> -- -max_total_time=60` | ⚠️ nightly 要 |

---

## Phase 6: 推論エッジケース (テストモデル使用)

> モデル: `test\models\multilingual-test-medium.onnx` (6 言語)。
> PowerShell では CPU 強制に `$env:CUDA_VISIBLE_DEVICES=""` を先に設定。
> 基本コマンド: `cd src\python && uv run python -m piper_train.infer_onnx --model ..\..\test\models\multilingual-test-medium.onnx --config ..\..\test\models\multilingual-test-medium.onnx.json --output-dir <out> --text "<入力>" --language ja-en-zh-es-fr-pt --speaker-id 0`

### 6.1 パラメータ境界

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 6.1.1 | `--speaker-id` = 0 / 有効最大 / -1 / 範囲外 (9999) | 範囲外は明示エラー | |
| 6.1.2 | `--noise-scale` = 0 / 0.667 / 1.5 / 負値 | 退化・負値でクラッシュなし | |
| 6.1.3 | `--length-scale` = 0 / 1.0 / 3.0 / 負値 | 0/負値の扱いが定義通り | |
| 6.1.4 | `--noise-w` 境界値 | クラッシュなし | |
| 6.1.5 | `--sentence-silence` = 0 / 大きい値 | 無音長が反映 | |

### 6.2 テキスト境界

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 6.2.1 | 空テキスト `""` | クラッシュなし / 空 or 極短 WAV | |
| 6.2.2 | 1〜2 文字 (`あ` / `Hi`) | 短テキスト戦略 A/B/C が発動 | |
| 6.2.3 | 超長テキスト (10 文以上) | メモリ安定 / 全文合成 | |
| 6.2.4 | 6 学習言語すべてで合成 | 各言語で可聴な音声 | |
| 6.2.5 | 言語コード順入れ替え (`pt-fr-es-zh-en-ja`) | canonical key 正規化で同結果 | |

### 6.3 ストリーミング / 文分割

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 6.3.1 | 終止符分割 `.!?。！？．` | 文ごとに分割・yield | |
| 6.3.2 | 終止符なしの長文 | 1 ユニットとして処理 | |
| 6.3.3 | SSML 入力 | 分割せず単一ユニット | |
| 6.3.4 | streaming スクリプト | `uv run python scripts/test_streaming_mode.py` | |

### 6.4 Phoneme Timing 出力

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 6.4.1 | JSON / TSV / SRT 出力 | 3 形式生成 | |
| 6.4.2 | timing の数値整合 | `(hop_length / sample_rate) × 1000` で byte-for-byte | |
| 6.4.3 | timing パリティ (全 6 ランタイム) | `uv run python scripts/check_phoneme_timing_contract.py` | |

### 6.5 入力経路バリエーション

| # | エッジケース | コマンド / 検証内容 | 状態 |
|---|------------|-------------------|------|
| 6.5.1 | Raw phoneme 入力 | `uv run python scripts/test_raw_phonemes.py` | |
| 6.5.2 | インライン `[[ ]]` 記法 | `uv run python scripts/test_phoneme_input.py` | |
| 6.5.3 | JSONL 入力 (phoneme_ids 直接) | `echo '{"phoneme_ids":[...],"speaker_id":0}' \| infer_onnx` | |
| 6.5.4 | Speaker embedding 経路 | `--reference-audio` + `--speaker-encoder-model` で声質指定 | |

### 6.6 異常系 / 環境変数

| # | エッジケース | 検証内容 | 状態 |
|---|------------|---------|------|
| 6.6.1 | モデルファイル不在 | 明示エラー (スタックトレースなし) | |
| 6.6.2 | config JSON 不正 / 不在 | 明示エラー | |
| 6.6.3 | 破損 ONNX ファイル | 明示エラー | |
| 6.6.4 | `PIPER_DISABLE_WARMUP=1` | warmup スキップ、結果不変 | |
| 6.6.5 | `PIPER_DISABLE_CACHE=1` | `.opt.onnx` キャッシュ未生成 | |
| 6.6.6 | `PIPER_INTRA_THREADS` 変更 | 反映 / クラッシュなし | |
| 6.6.7 | 並行推論 (複数スレッド同時) | スレッド安全 (Rust/Go/C# runtime) | |

---

## Phase 7: CLI スモーク / UX (モデル不要分)

| # | 項目 | コマンド | 合格条件 | 状態 |
|---|------|---------|---------|------|
| 7.1 | Python CLI help/version | `cd src\python && uv run python -m piper_train.infer_onnx --help` | 表示 | |
| 7.2 | Rust CLI help/version | `src\rust\target\release\piper-cli.exe --help` / `--version` | 表示 | |
| 7.3 | Go CLI help | `src\go\bin\piper-plus.exe --help` | 表示 | |
| 7.4 | C# CLI help | `publish\PiperPlus.Cli.exe --help` | 表示 | |
| 7.5 | C++ CLI help | `build\Release\piper.exe --help` | 表示 | |
| 7.6 | `--list-models` (言語フィルタ付き) | 各 CLI で実行 | モデル一覧表示 | |
| 7.7 | モデル名エイリアス解決 | `--model tsukuyomi` (DL 確認) | 自動解決 | |
| 7.8 | 必須引数欠落 / 不正引数 | 各 CLI で意図的に誤入力 | 明示エラー + 終了コード ≠ 0 | |
| 7.9 | CLI UX 統合スクリプト | `uv run python scripts/test_cli_ux.py` | PASS | |
| 7.10 | Windows での Unicode 引数 | `--text "日本語テスト🎌"` | 文字化けなし | |

---

## Phase 8: 統合 / E2E

| # | 項目 | コマンド | 可否 | 状態 |
|---|------|---------|------|------|
| 8.1 | 日本語 TTS E2E | `uv run python scripts/test_japanese_tts.py` | ✅ | |
| 8.2 | 多言語 TTS E2E (サブセット) | `uv run python scripts/test_multilingual_tts.py --languages en_US ja_JP --test-type basic` | ✅ ネットワーク要 | |
| 8.3 | issue #426 回帰 E2E | `e2e-issue-426.yml` / `integration-tests-issue-426.yml` 相当のローカル再現 | ⚠️ | |
| 8.4 | OpenAI 互換 API サーバー | `docker/python-inference/inference.py` 起動 → `/v1/audio/speech` `/health` 叩く | ✅ | |
| 8.5 | WebUI (Gradio) 起動確認 | `docker/webui/app.py` 起動 → UI 表示 | ✅ | |
| 8.6 | Docker ビルド検証 | `docker build` (python-inference / webui) | ✅ Docker 29.2.1 | |
| 8.7 | Wyoming + HA 統合 | `docker/wyoming/` ビルド + smoke | ⚠️ HA 実機連携は任意 | |
| 8.8 | C API サンプル (C/Dart/Godot) | `examples/c-api/` ビルド + 実行 | ✅ | |

---

## Phase 9: リリース固有チェック

| # | 項目 | コマンド | 合格条件 | 状態 |
|---|------|---------|---------|------|
| 9.1 | バージョンマニフェスト同期 (9 manifest) | `uv run python scripts/check_version_manifest_sync.py` | 一致 | |
| 9.2 | CHANGELOG Unreleased 整合 | `uv run python scripts/check_changelog_unreleased.py` | PASS | |
| 9.3 | migration ↔ CHANGELOG パリティ | `uv run python scripts/check_migration_changelog_parity.py` | PASS | |
| 9.4 | ORT バージョンドリフト | `uv run python scripts/check_ort_version_drift.py` / `check_ort_versions.py` | 一致 | |
| 9.5 | OpenJTalk バージョン同期 | `uv run python scripts/check_openjtalk_version_sync.py` | 一致 | |
| 9.6 | Public API diff (破壊的変更検出) | `public-api-diff.yml` 相当 / `cargo public-api` 等 | 想定通り | |
| 9.7 | 非推奨 API の残留確認 | `uv run python scripts/check_deprecated_api_lingering.py` | PASS | |
| 9.8 | README 整合 (breaking/h2/code/latency) | `uv run python scripts/check_readme_breaking_sync.py` 他 3 本 | PASS | |
| 9.9 | ライセンスチェック | `license-check.yml` 相当 (依存ライセンス棚卸し) | 問題なし | |
| 9.10 | シークレットスキャン | `gh` or `gitleaks` でローカルスキャン | 検出 0 | |
| 9.11 | lockfile 整合 / サイズ | `uv run python scripts/check_lockfile_consistency.py` / `check_lockfile_size.py` | PASS | |
| 9.12 | Cargo.lock 重複検出 | `uv run python scripts/check_cargo_lock_duplicates.py` | PASS | |
| 9.13 | GitHub Actions ピン留め | `uv run python scripts/check_action_pins.py` | PASS | |
| 9.14 | model checksum 検証 | `uv run python scripts/verify_model_checksums.py` | 一致 | |
| 9.15 | skill / hook health | `/skill-health` | PASS | |

---

## Phase 10: パフォーマンス / メモリ回帰

| # | 項目 | コマンド | 合格条件 | 状態 |
|---|------|---------|---------|------|
| 10.1 | RTF 回帰 | `uv run python scripts/benchmark_runtime.py` → `check_benchmark_json.py` | 基準内 | |
| 10.2 | メモリ回帰 | `memory-regression.yml` 相当の計測 | 基準内 | |
| 10.3 | バンドルサイズゲート (npm / AAR) | `uv run python scripts/check_bundle_size.py` | 上限内 | |
| 10.4 | 非対称レイテンシ検出 | `uv run python scripts/check_asymmetric_latency.py` | PASS | |
| 10.5 | ストリーミング比較ベンチ | `uv run python scripts/benchmark_streaming_comparison.py` | 基準内 | |
| 10.6 | unwrap 密度 (Rust panic 経路) | `uv run python scripts/check_unwrap_density.py` | 上限内 | |

---

## Phase 11: 既知 Issue 回帰確認

> CHANGELOG `[Unreleased]` と直近修正に対する pin テスト。再発していないことを確認。

| # | Issue | 回帰確認内容 | 状態 |
|---|-------|------------|------|
| 11.1 | #388 Kotlin/Android G2P | L1 pure-Kotlin unit (18 件) / L5 16KB align + AAR < 10MB ゲート | |
| 11.2 | #384 ZH-EN code-switching | 全 7 ランタイムで `phonemize_embedded_english` の lookup priority / opt-out | |
| 11.3 | #387 Swift G2P | `check_swift_g2p_contract.py` / xcframework 構成 (CI 確認) | |
| 11.4 | #426 | `e2e-issue-426` / `integration-tests-issue-426` の再現 | |
| 11.5 | #204 疑問詞マーカー | `?!` `?.` `?~` の 3 分岐が維持 | |
| 11.6 | #207 N バリアント | N_m/N_n/N_ng/N_uvular 分類が維持 | |
| 11.7 | #320 MB-iSTFT decoder | 出力形状 `[B,1,T]` 維持・ランタイム変更不要 | |
| 11.8 | v1.12.0 breaking | `phonemize()` 複数要素化 (migration ガイド整合) | |

---

## 推奨実行順序

1. **Phase 0** — 環境準備 (1 回のみ)
2. **Phase 1 → 2 → 3** — Lint/Format → Build → Unit test (各ランタイム並行可)
3. **Phase 4** — 契約ゲート (`4.0` 一括 → FAIL を個別切り分け)
4. **Phase 5 → 6** — エッジケース (G2P → 推論)
5. **Phase 7 → 8** — CLI / E2E
6. **Phase 9 → 10 → 11** — リリース固有 / 回帰

Phase 1〜4 が全 PASS してからリリースタグ判断に進む。

## ローカル実行不可 / 要注意項目まとめ

この PC は **7 ランタイム中 6 つをフル検証可能** (確認済: VS 2026 + Build Tools 2022 / Docker 29.2.1 / JDK 17 / Android Studio + SDK + emulator)。ローカル不可は Swift/iOS のみ。

| 項目 | 理由 | 代替 |
|------|------|------|
| Swift G2P xcframework (11.3) | macOS + Xcode 必須 — この PC では不可 | CI `swift-g2p-ci.yml` / `release-shared-lib.yml` |
| Kotlin G2P 計装テスト L3 (11.1) | emulator/AVD 起動が必要 (SDK に emulator あり、ローカル可だが時間要) | CI `kotlin-g2p-ci.yml` でも可 |
| 学習系テスト (Phase 3.4 一部) | GPU + データセット要 | 学習サーバー専用、QA 対象外 |
| 多言語 E2E 全 23 言語 (8.2) | モデル DL ~120GB | `--languages` でサブセット限定 |
| C++ ビルド初回 (2.7) | ORT + piper-phonemize を ExternalProject で取得 — 数十分要 | 2 回目以降はビルドキャッシュ利用 |
| Python 3.14 (ローカル) | CI は 3.11/3.13 | version 起因の差異が出たら CI 結果を正とする |
