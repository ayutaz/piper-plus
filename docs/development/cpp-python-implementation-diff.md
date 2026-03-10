# C++/Python実装差分レポート -- 最終サマリー

> 全差分解消完了: 2026-03-10 | ブランチ: `fix/cpp-python-sync` (PR #229)

## 概要

C++推論(piper)とPython学習(pyopenjtalk-plus)の音素化パイプラインにおける実装差分を調査・解消した。
15エージェント並行調査 + Docker推論実測比較により差分を特定し、M1-M4の4マイルストーンで全ての差分を解消。
8テキストの回帰テストで **8/8 PASS** (phoneme_ids完全一致) を達成。

## マイルストーン概要

| MS | 内容 | キーコミット |
|----|------|-------------|
| M1 | 疑問詞マーカー・Nバリアント・プロソディマーク挿入をC++に実装 | `c251b1d` |
| M1.5 | OpenJTalkフロントエンドをpyopenjtalk-plus (Cライブラリ直接リンク) に統一 | `2997b1b` |
| M2 | テスト58件追加 (Nバリアント38 + 疑問詞20)、ユーティリティ分離、prosody型修正 | `31b586c` |
| M3 | JSON prosody_features入力サポート、カスタム辞書UTF-8境界修正 | - |
| M4 | Docker回帰テスト (`regression_test.sh` 8/8 PASS)、CI C++テストジョブ追加 | - |

## 主要差分と解消状況

### 高severity (音素化結果に直接影響)

| # | 差分 | 影響 | 解消 |
|---|------|------|------|
| 1 | プロソディマーク欠落 | `[`/`]`/`#`マークなし -> アクセント情報消失 | M1 |
| 2 | Nバリアント未実装 | 全て`N`のまま -> 鼻音同化情報消失 | M1 |
| 3 | 疑問詞マーカー未実装 | 疑問文の種類区別不可 | M1 |
| 4 | BOS/EOS制御 | `^`/`$`トークンの日本語側処理不整合 | M1 |
| 5 | OpenJTalkフロントエンド不一致 | SourceForge版 vs r9y9フォーク -> NJDルール・A1/A2/A3値差異 | M1.5 |

### 中severity (出力形式・インターフェースに影響)

| # | 差分 | 解消 |
|---|------|------|
| 6 | JSON prosody_features未出力 | M3 |
| 7 | 日本語辞書境界処理 (`\b`がマルチバイト非対応) | M3 |

### 低severity (ログ・テスト・運用)

| # | 差分 | 解消 |
|---|------|------|
| 8 | PUAトークンログ不整合 (puaToPhoneme未登録) | M1 |
| 9 | ユニットテスト不足 | M2 (58テスト追加) |
| 10 | Docker回帰テスト未整備 | M4 |

## CI/インテグレーション修正

| コミット | 内容 |
|---------|------|
| `de94e47` | Copilotレビュー3件対応 (fprintf配置、CMakeマクロ化、ダウンロード直列化) |
| `9db0dfe` | ExternalProject並列ビルドのレースコンディション修正 |
| `768c7e9` | バイナリ相対パスでの辞書検索実装 (Windows/Linux/macOS対応) |
| `35c2e87` | phoneme_idsクラッシュ防止 + テストモデルにPUAトークン追加 |
| `0cb7b42` | 辞書ダウンロードCIテスト修正 |
| `8ced3d2` | CIテストをM1.5アーキテクチャに適合 |

## 回帰テスト結果 (8/8 PASS)

| テスト | テキスト | 検証ポイント |
|--------|---------|-------------|
| 1 | こんにちは、今日は良い天気ですね。 | 基本文、N_n/N_ng、プロソディマーク |
| 2 | 本当ですか？ | 汎用疑問 `?`(ID=3) |
| 3 | 本当?! | 強調疑問 `?!`(ID=4) |
| 4 | そうなの？。 | 平叙疑問 `?.`(ID=5) |
| 5 | さんぽに行きましょう。 | N_m (両唇音同化) |
| 6 | あんないします。 | N_n (歯茎音同化) |
| 7 | ぎんこうに行きます。 | N_ng (軟口蓋音同化) |
| 8 | 本を読みました。 | N_uvular (口蓋垂音) |

全テストで phoneme_ids、prosody_features (A1/A2/A3)、プロソディマーク、Nバリアント、疑問詞EOSが C++/Python 間で完全一致。

## 調査対象ファイル

### C++

| ファイル | 役割 |
|---------|------|
| `src/cpp/openjtalk_phonemize.cpp` | 音素化メインロジック (プロソディマーク・N分類・疑問詞) |
| `src/cpp/openjtalk_api.c` | OpenJTalk C API + NJD後処理 (M1.5) |
| `src/cpp/openjtalk_wrapper.c` | API/バイナリ切り替えラッパー |
| `src/cpp/piper.cpp` | BOS/EOS制御、phoneme_id変換、puaToPhonemeログ |
| `src/cpp/custom_dictionary.cpp` | カスタム辞書 (M3: UTF-8境界修正) |

### Python

| ファイル | 役割 |
|---------|------|
| `src/python/piper_train/phonemize/japanese.py` | 音素化リファレンス実装 |
| `src/python/piper_train/phonemize/jp_id_map.py` | IDマップ (65トークン) |
| `src/python/piper_train/phonemize/token_mapper.py` | PUAマッピング (29エントリ、U+E000-E01C) |
| `src/python/piper_train/infer_onnx.py` | ONNX推論スクリプト |

## 残課題

なし (全マイルストーン完了)
