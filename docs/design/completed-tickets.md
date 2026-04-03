# C API 共有ライブラリ — 完了チケット一覧

> Issue #295 の Phase 1〜4 で完了したチケットの記録。
> 詳細な実装内容は git log を参照。

## Phase 1: 基本 C API (M1-1〜M1-8)

| ID | タイトル | 見積り | 完了 |
|----|---------|--------|------|
| M1-1 | ExternalProject に `-fPIC` を追加 | 小 | ✅ |
| M1-2 | `-static-libstdc++` を共有ライブラリに適用しない | 小 | ✅ |
| M1-3 | PiperPlusConfig に `dict_dir` フィールド追加 | 中 | ✅ |
| M1-4 | CMake `PIPER_PLUS_BUILD_SHARED` + OBJECT ライブラリ | 大 | ✅ |
| M1-5 | `piper_plus.h` ヘッダー作成 | 中 | ✅ |
| M1-6 | `piper_plus_c_api.cpp` 実装 | 大 | ✅ |
| M1-7 | C API 単体テスト (モデル不要) | 中 | ✅ |
| M1-8 | CI 統合 (3 プラットフォームビルド検証) | 中 | ✅ |

### M1-1: ExternalProject に `-fPIC` を追加
Linux x86_64 で共有ライブラリビルド時のリンクエラー回避。CMakeLists.txt の OpenJTalk/spdlog/hts_engine に `-DCMAKE_POSITION_INDEPENDENT_CODE=ON` および `CFLAGS=-fPIC` を追加。

### M1-2: `-static-libstdc++` を共有ライブラリに適用しない
`-static-libgcc -static-libstdc++` を `piper` 実行ファイルのみに限定。`-Wl,-rpath,'$ORIGIN'` をグローバル `CMAKE_CXX_FLAGS` から `piper` ターゲット固有の `target_link_options` に移動。

### M1-3: PiperPlusConfig に `dict_dir` フィールド追加
共有ライブラリ利用者が OpenJTalk 辞書ディレクトリを明示指定可能にする `dict_dir` フィールドを追加。`setenv("OPENJTALK_DICTIONARY_PATH", ...)` 方式で既存の辞書検索ロジックに統合。

### M1-4: CMake `PIPER_PLUS_BUILD_SHARED` + OBJECT ライブラリ
`piper_common` OBJECT ライブラリでソース二重列挙を解消。`-DPIPER_PLUS_BUILD_SHARED=ON` で 3 プラットフォーム対応の共有ライブラリをビルド可能に。GNUInstallDirs、EXPORT PiperPlusTargets、RPATH 設定 (`$ORIGIN` / `@loader_path`) を含む。

### M1-5: `piper_plus.h` ヘッダー作成
C99/C++17 両対応の公開 C API ヘッダー。POD struct、opaque handle、`PIPER_PLUS_API` エクスポートマクロ、`_reserved` ABI パディング、スレッドセーフティドキュメント。Dart `ffigen` 互換。

### M1-6: `piper_plus_c_api.cpp` 実装
Phase 1 全 API 関数の実装。`synthesisConfig` save/restore による `languageId` 未復元バグの回避、`atomic<bool> inProgress` による再入防止、`thread_local` エラーメッセージ、int16->float32 変換。

### M1-7: C API 単体テスト (モデル不要)
Google Test ベースの 24 テストケース。バージョン情報、デフォルトオプション、NULL 安全性 (全 API 関数)、無効モデルパス、エラーメッセージ取得、ステータスコード定数、struct memset 安全性。

### M1-8: CI 統合 (3 プラットフォームビルド検証)
`cpp-tests.yml` に共有ライブラリビルド + テストを統合。Windows マトリクス追加、シンボル可視性検証 (`piper_plus_` プレフィックスのみ)、C API テスト実行、Linux `libstdc++` 動的リンク確認。

## Phase 2: ストリーミング + テスト (M2-1〜M2-6)

| ID | タイトル | 見積り | 完了 |
|----|---------|--------|------|
| M2-1 | textToAudio の音素化ループを再利用可能関数に抽出 | 中 | ✅ |
| M2-2 | Iterator パターン (synth_start / synth_next) | 大 | ✅ |
| M2-3 | コールバック合成 (synthesize_streaming) | 小 | ✅ |
| M2-4 | ストリーミング単体テスト (モデル不要) | 中 | ✅ |
| M2-5 | 統合テスト (モデル必要) | 中 | ✅ |
| M2-6 | CI 統合更新 | 中 | ✅ |

### M2-1: textToAudio の音素化ループを再利用可能関数に抽出
`textToAudio()` から `phonemizeText()` と `splitTextToSentences()` を抽出する純粋なリファクタリング。Iterator パターン (M2-2) の前提条件。`textToAudioStreaming` のマルチリンガルデッドコード問題を発見・記録。

### M2-2: Iterator パターン (synth_start / synth_next)
文単位の逐次合成 API。`synth_start()` でテキストを文分割してキューに保持し、`synth_next()` で 1 文ずつ合成。`textToAudio()` ベースでマルチリンガルを完全サポート。ワンショット/Iterator 間の排他制御 (`PIPER_PLUS_ERR_BUSY`)。

### M2-3: コールバック合成 (synthesize_streaming)
M2-2 の Iterator を内部駆動する薄いラッパー。`PiperPlusAudioCallback` でチャンクごとにコールバック呼び出し。Dart `NativeCallable.listener` 互換 (void 戻り)。callback 例外時の `inProgress` リセットガード付き。

### M2-4: ストリーミング単体テスト (モデル不要)
13 テストケース。Iterator/コールバックの NULL safety、`PiperPlusAudioChunk` struct レイアウト検証、ステータスコード定数、排他制御 precedence。`test_c_api.cpp` に `CApiStreamingTest` グループとして追加。

### M2-5: 統合テスト (モデル必要)
テストモデル (`multilingual-test-medium.onnx`) を使用した 13 テストケース。ワンショット/Iterator/コールバックの全合成パス検証、クエリ API、排他制御、speaker_id 変更、Iterator 再利用。モデル非存在時は `GTEST_SKIP`。

### M2-6: CI 統合更新
テストモデル + 辞書のキャッシュ機構追加。統合テストとシンボル可視性検証を 3 プラットフォーム CI に組み込み。テスト結果アーティファクトのアップロード。Phase 4 候補として多言語文分割精度向上と crossfade 対応を記録。

## Phase 3: 配布 (M3-1〜M3-6)

| ID | タイトル | 見積り | 完了 |
|----|---------|--------|------|
| M3-1 | 配布ファイルマニフェスト + install ターゲット整備 | 中 | ✅ |
| M3-2 | pkg-config ファイル生成 | 小 | ✅ |
| M3-3 | CMake Config パッケージ生成 | 中 | ✅ |
| M3-4 | macOS RPATH 修正 + プラットフォーム別リンク設定 | 小 | ✅ |
| M3-5 | リリースワークフロー拡張 | 大 | ✅ |
| M3-6 | 使用例ドキュメント | 中 | ✅ |

### M3-1: 配布ファイルマニフェスト + install ターゲット整備
ONNX Runtime 同梱 install、OpenJTalk 辞書/G2P 辞書 install、`verify_install_layout.cmake` 検証スクリプト。M1-4 で対応済みの GNUInstallDirs/EXPORT の上に配布固有ルールを追加。

### M3-2: pkg-config ファイル生成
`cmake/piper_plus.pc.in` テンプレートから `piper_plus.pc` を生成。`dictdir`/`g2p_dictdir` カスタム変数、`Libs.private` に ORT。Godot GDExtension (SCons) / Meson / 手動 Makefile 向け。

### M3-3: CMake Config パッケージ生成
`find_package(PiperPlus)` + `target_link_libraries(app PiperPlus::piper_plus)` を実現。`PiperPlusConfig.cmake.in`、`write_basic_package_version_file` (SameMajorVersion)、`PiperPlus_DICT_DIR` 変数。

### M3-4: macOS RPATH 修正 + プラットフォーム別リンク設定
ONNX Runtime dylib の `install_name` を `@rpath/...` に修正する `install_name_tool` カスタムコマンド。`piper_plus` 自体の RPATH は M1-4 で設定済み。install 後の RPATH 検証テスト。

### M3-5: リリースワークフロー拡張
4 プラットフォーム (Linux x64/arm64, macOS arm64, Windows x64) の共有ライブラリ配布。`build-piper.yml` に `build-shared` input 追加、install layout/RPATH/シンボル可視性/pkg-config 検証、リリースアセット自動アップロード。

### M3-6: 使用例ドキュメント
`examples/c-api/` に 3 つの C サンプル (basic/streaming/multi_language)。Makefile (pkg-config) + CMakeLists.txt (find_package) の両方でビルド可能。WAV 出力、ストリーミングコールバック、多言語合成デモ。

## Phase 4: 拡張 (M4-1〜M4-6)

| ID | タイトル | 見積り | 完了 |
|----|---------|--------|------|
| M4-1 | カスタム辞書 API | 中 | ✅ |
| M4-2 | Phoneme timing 出力 | 中 | ✅ |
| M4-3 | G2P 単独利用 API | 中 | ✅ |
| M4-4 | Android NDK ビルド | 大 | ✅ |
| M4-5 | int16/float32 二重変換の解消 | 中 | ✅ |
| M4-6 | dladdr による辞書自動検出改善 | 中 | ✅ |

### M4-1: カスタム辞書 API
既存の `CustomDictionary` C++ クラスを C API でラップ。`piper_plus_load_custom_dict()`, `piper_plus_clear_custom_dict()`, `piper_plus_add_dict_word()`, `piper_plus_dict_entry_count()` の 4 関数。JSON v1.0/v2.0 対応。合成パイプラインで `applyToText()` を自動適用。

### M4-2: Phoneme timing 出力
合成後の音素タイミング情報 (開始/終了時刻、フレームインデックス) を C 構造体で取得。`PiperPlusPhonemeInfo`/`PiperPlusTimingResult` + `piper_plus_get_phoneme_timing()`。リップシンク (Godot/Unity) 向け。ワンショット/Iterator 両対応。

### M4-3: G2P 単独利用 API
ONNX 推論なしでテキストから IPA 音素列に変換。`piper_plus_phonemize()` + `piper_plus_available_languages()`。M2-1 の `phonemizeText()` を利用。カスタム辞書 (M4-1) との統合済み。Rust `piper-plus-g2p` FFI とは独立運用。

### M4-4: Android NDK ビルド
Android NDK ツールチェインで `libpiper_plus.so` (arm64-v8a) をクロスコンパイル。ONNX Runtime Android AAR 統合、全 ExternalProject のツールチェイン引き渡し、ARM64 NEON 有効化、`__ANDROID__` 分岐での辞書パス対応、CI ワークフロー。

### M4-5: int16/float32 二重変換の解消
`float32 -> int16 -> float32` の二重変換を解消。`synthesize()` に float32 出力バリアント追加、`runInference()` 内部ヘルパー抽出。C API は ONNX 出力を直接 float32 のまま返却。ARM64 NEON の float32 正規化関数追加。既存 int16 パス (CLI/WAV) は維持。

### M4-6: dladdr による辞書自動検出改善
`dladdr()` / `GetModuleHandleEx()` でライブラリ自身のパスを取得し、`../share/open_jtalk/dic/` を自動検出。`dict_dir = NULL` でも辞書が見つかる DX 改善。`library_path.h/c` に統一ヘルパー。3 箇所 (`openjtalk_dictionary_manager.c`, `piper.cpp`, `custom_dictionary.cpp`) のフォールバック付き統合。
