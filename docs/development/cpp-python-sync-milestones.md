# C++/Python音素化パイプライン同期 — マイルストーン完了サマリー

> 全マイルストーン(M1-M4)完了: 2026-03-10
> ブランチ: `fix/cpp-python-sync`

## 概要

C++推論パイプライン(piper)とPython学習パイプライン(pyopenjtalk-plus)の音素化結果を完全同期。
8テキストの回帰テストで8/8 PASS達成。

## マイルストーン一覧

### M1: C++/Python音素化パイプライン同期 ✅

- プロソディマーク挿入(`[`/`]`/`#`) — 栗原方式のA1/A2/A3条件判定
- 文脈依存Nバリアント(`N_m`/`N_n`/`N_ng`/`N_uvular`) — 後続音素による自動分類
- 疑問詞タイプEOSマーカー(`?!`/`?.`/`?~`) — 元テキスト末尾パターンから判定
- BOS/EOS制御
- **主要ファイル**: `openjtalk_phonemize.cpp`, `piper.cpp`
- **コミット**: `c251b1d` (2026-03-08)
- **結果**: M1時点で6/8 PASS（残2件はOpenJTalkフロントエンド差異、M1.5で解消）

### M1.5: OpenJTalkフロントエンド統一 ✅

- SourceForge版OpenJTalkバイナリ(`system()`呼び出し)を廃止
- pyopenjtalk-plus v0.4.1.post7のr9y9/open_jtalk Cライブラリに移行(API直接呼び出し)
- NJD後処理ルール(`apply_original_rule_before_chaining`, `modify_acc_after_chaining`)をCにポート
- `text2mecab` 3引数API対応（buffer_sizeパラメータ追加）
- ExternalProject URLをPyPI sdistに変更（ライブラリ+辞書を同一ソースから取得）
- **主要ファイル**: `openjtalk_api.c`, `openjtalk_wrapper.c`, `CMakeLists.txt`, `cmake/patch_r9y9_openjtalk.cmake`
- **結果**: 8/8 PASS（M1残存2件を根本解消）

### M2: ログ・テスト整合性 ✅

- Nバリアント38件+疑問詞マーカー20件 = 58ユニットテスト追加（全PASS）
- PUAトークンログ出力の整合性確認（`puaToPhoneme`マップに7エントリ追加）
- `test_prosody_inference.cpp`の型をfloat→int64に修正
- テストユーティリティを`openjtalk_phonemize_utils.cpp/hpp`に分離
- **主要ファイル**: `src/cpp/tests/test_n_variants.cpp`, `test_question_markers.cpp`

### M3: インターフェース改善 ✅

- JSON `prosody_features`入力対応（`ProsodyFeature`構造体を`piper.hpp`に移動）
- 日本語辞書エントリの単語境界修正（マルチバイトUTF-8で`\b`をスキップ）
- **主要ファイル**: `openjtalk_phonemize.cpp`, `piper.hpp`, `piper.cpp`, `main.cpp`, `custom_dictionary.cpp`

### M4: Docker回帰テスト ✅

- 8テキスト比較テスト(`regression_test.sh`) — 8/8 PASS
- `Dockerfile.test`でC++ユニットテスト実行
- `docker-test.yml`にC++パストリガー+ユニットテストジョブ追加
- **主要ファイル**: `docker/cpp-inference/regression_test.sh`, `Dockerfile.test`, `.github/workflows/docker-test.yml`

## 回帰テスト結果

| # | テキスト | IDs数 | EOS | 結果 |
|---|---------|-------|-----|------|
| 1 | こんにちは、今日は良い天気ですね。 | 38 | $ | PASS |
| 2 | 本当ですか？ | 16 | ? | PASS |
| 3 | 本当？！ | 9 | ?! | PASS |
| 4 | そうなの？。 | 11 | ?. | PASS |
| 5 | さんぽに行きましょう。 | 21 | $ | PASS |
| 6 | あんないします。 | 15 | $ | PASS |
| 7 | ぎんこうに行きます。 | 20 | $ | PASS |
| 8 | 本を読みました。 | 20 | $ | PASS |

## CI/インテグレーション修正

M4完了後のCI全チェック通過対応:

| コミット | 内容 |
|---------|------|
| `de94e47` | Copilotレビュー3件対応(fprintf配置、CMakeマクロ化、ダウンロード直列化) |
| `9db0dfe` | ExternalProject並列ビルドのレースコンディション修正(`URL_HASH SHA256`+`DEPENDS`直列化) |
| `768c7e9` | バイナリ相対パスでの辞書検索実装(Windows/Linux/macOS) |
| `35c2e87` | phoneme_idsクラッシュ防止 + テストモデルにPUAトークン追加 |
| `0cb7b42` | 辞書ダウンロードCIテスト修正 |
| `8ced3d2` | CIテストをM1.5アーキテクチャに適合(バイナリ確認→piper存在確認に変更) |

## 変更ファイル一覧

| カテゴリ | ファイル | 変更内容 |
|---------|---------|---------|
| C++コア | `openjtalk_phonemize.cpp` | プロソディマーク、Nバリアント、疑問詞マーカー |
| C++コア | `openjtalk_api.c` | NJD後処理ルールのCポート |
| C++コア | `openjtalk_wrapper.c` | API直接呼び出し(バイナリフォールバック付き) |
| C++コア | `piper.cpp` | BOS/EOS制御、PUAログマップ拡張、外部プロソディ対応 |
| C++コア | `piper.hpp` | ProsodyFeature構造体移動 + API拡張 |
| C++コア | `main.cpp` | JSON prosody_features解析 |
| C++コア | `openjtalk_dictionary_manager.c` | バイナリ相対パス辞書検索 |
| C++コア | `phoneme_ids.cpp` | 未知phonemeガード追加 |
| C++コア | `custom_dictionary.cpp` | 日本語単語境界修正 |
| ビルド | `CMakeLists.txt` | pyopenjtalk-plus ExternalProject統一 |
| ビルド | `cmake/patch_r9y9_openjtalk.cmake` | MSVCインストールパッチ |
| テスト | `tests/CMakeLists.txt` | `link_openjtalk_to_test`マクロ |
| テスト | `tests/test_n_variants.cpp` | Nバリアント38テスト |
| テスト | `tests/test_question_markers.cpp` | 疑問詞マーカー20テスト |
| テスト | `openjtalk_phonemize_utils.cpp/hpp` | テストユーティリティ |
| テスト | `ja_JP-test-medium.onnx.json` | PUAトークン追加 |
| Docker | `regression_test.sh` | 8テキスト回帰テスト |
| Docker | `Dockerfile.test` | C++ユニットテスト用 |
| CI | `docker-test.yml` | ユニットテストジョブ追加 |
| CI | `test-japanese-tts.yml` | 辞書パス環境変数追加 |
| CI | `test-multilingual-tts.yml` | 辞書パス環境変数・バンドル辞書削除 |
