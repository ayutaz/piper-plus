# スウェーデン語対応 マイルストーン計画

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-30 |
| Issue | #296 |
| ブランチ | `feature/swedish-language-support` |
| 関連文書 | `swedish-requirements.md`, `swedish-g2p-design.md`, `swedish-spec-index.md` |
| チケット | `docs/tickets/index.md` |

---

## 全体ロードマップ

```
Phase 1: Python Phonemizer
  ├── M1.1 データ準備 (NST辞書 + SAMPA→IPA変換)
  ├── M1.2 音素インベントリ + PUA割り当て
  ├── M1.3 Rule-based G2P エンジン
  ├── M1.4 辞書ルックアップ統合
  ├── M1.5 マルチリンガル統合
  └── M1.6 テストスイート + CI
      ↓
Phase 2: クロスプラットフォーム
  ├── M2.1 Rust 実装
  ├── M2.2 C# 実装
  ├── M2.3 C++ 実装
  └── M2.4 WASM/JS 実装
      ↓
Phase 3: TTSモデル学習 & リリース
  ├── M3.1 データセット準備
  ├── M3.2 ファインチューニング
  └── M3.3 ONNX エクスポート + リリース
      ↓
Phase 4: 品質向上 (将来)
  ├── M4.1 声調アクセント対応
  ├── M4.2 複合語分割改善
  └── M4.3 数字・略語展開
```

### Phase 間の依存関係

| 依存元 | 依存先 | 関係 |
|--------|--------|------|
| Phase 2 | Phase 1 | Phase 1 完了後に開始 |
| Phase 3 | Phase 1 | Phase 1 完了後に開始 (Phase 2 と並行可) |
| Phase 4 | Phase 1 | Phase 1 完了後に開始 |

---

## Phase 1: Python Phonemizer

**目標**: espeak-ng不使用で精度 ≥95% のスウェーデン語G2Pを Python で実装

### M1.1 データ準備

| 項目 | 内容 |
|------|------|
| 目標 | NST辞書 (CC0) をダウンロードし、piper-plus で使えるIPA形式に変換 |
| 成果物 | `tools/convert_nst_dictionary.py`, Core辞書JSON (238K語) |
| 対応要件 | FR-02 |
| 前提 | なし |

**タスク**:

| # | タスク | 詳細 |
|---|--------|------|
| 1 | NST辞書ダウンロード | OpenSLR 29 から `lexicon-sv.tgz` 取得 |
| 2 | SAMPA→IPA変換テーブル実装 | 43 SAMPA音素 → IPA マッピング (nst-dictionary-integration.md 準拠) |
| 3 | 変換スクリプト作成 | CLI: `--input`, `--output`, `--tier core/full`, `--gzip` |
| 4 | フィルタリング | !SIL, `<UNK>`, ハイフン断片除外、大文字→小文字 |
| 5 | Core辞書生成 | 副ストレスなし = 単純語 ~238K語を抽出 |
| 6 | スポットチェック | 20語の IPA 正確性を検証 |

**完了基準**: 変換後の Core辞書で スポットチェック20語全正解

---

### M1.2 音素インベントリ + PUA割り当て

| 項目 | 内容 |
|------|------|
| 目標 | スウェーデン語の音素をpiper-plusの音素体系に統合 |
| 成果物 | `sv_id_map.py`, `token_mapper.py` 変更 |
| 対応要件 | FR-04 |
| 前提 | なし (M1.1 と並行可) |

**タスク**:

| # | タスク | 詳細 |
|---|--------|------|
| 1 | `sv_id_map.py` 作成 | `SWEDISH_PHONEMES` リスト (19音素) 定義 |
| 2 | PUA割り当て | 9個の長母音 (0xE059-0xE061) を `FIXED_PUA_MAPPING` に追加 |
| 3 | `_PUA_START` 更新 | 0xE059 → 0xE064 |
| 4 | 衝突検証 | 既存6言語のPUAと衝突しないことを確認 |

**完了基準**: 全PUA割り当てがユニーク、既存言語と衝突なし

---

### M1.3 Rule-based G2P エンジン

| 項目 | 内容 |
|------|------|
| 目標 | OOV語向けのネイティブG2P規則エンジンを実装 |
| 成果物 | `swedish.py` の規則エンジン部分 |
| 対応要件 | FR-03a〜FR-03g |
| 前提 | M1.2 (音素インベントリ) |

**タスク**:

| # | タスク | 対応要件 | 詳細 |
|---|--------|---------|------|
| 1 | 正規化 + トークン化 | FR-03 共通 | Unicode NFC、小文字化、句読点分割 |
| 2 | Soft/Hard 子音分岐 | FR-03a | 17規則の最長一致、例外リスト ~140語、形態論ヒューリスティック |
| 3 | sj-sound パターン | FR-03c | 無条件6パターン + sk+前母音 + 接尾辞 (-tion/-sion/-age) |
| 4 | 母音長 (Complementary Quantity) | FR-03d | 18母音テーブル、r+C例外、語末m例外、機能語リスト |
| 5 | 非強勢母音短縮 | FR-03e | 16接尾辞パターン、シュワー不使用 |
| 6 | ストレス検出 | FR-03f | 5段階優先 (機能語→単音節→接尾辞→接頭辞→第1音節) |
| 7 | ローンワード規則 | FR-03g | 接尾辞7パターン + 接頭辞5パターン (ネイティブ規則の前に適用) |
| 8 | レトロフレックス同化 | FR-03b | 後処理: r+C→retroflex、カスケード、rrブロック、ɭ停止 |
| 9 | `SK_BACK_VOWEL_EXCEPTIONS` | FR-03a/c | människa, marskalk |

**完了基準**: FR-03 の各テストケースで規定精度以上 (soft/hard 全問正解、sj-sound ≥90% 等)

---

### M1.4 辞書ルックアップ統合

| 項目 | 内容 |
|------|------|
| 目標 | NST辞書ルックアップとRule-basedフォールバックを統合した SwedishPhonemizer 完成 |
| 成果物 | `swedish.py` 完成版 (辞書+規則の統合パイプライン) |
| 対応要件 | FR-01, FR-05 |
| 前提 | M1.1 (辞書), M1.3 (規則エンジン) |

**タスク**:

| # | タスク | 詳細 |
|---|--------|------|
| 1 | 辞書ロード機構 | JSON dict ロード、`dict_path` パラメータ、`PIPER_SV_DICT_PATH` 環境変数 |
| 2 | ルックアップ → フォールバック パイプライン | Stage 1 辞書 → Stage 2-6 規則 |
| 3 | `SwedishPhonemizer` ABC 準拠 | `phonemize()`, `phonemize_with_prosody()`, `get_phoneme_id_map()` |
| 4 | ProsodyInfo 構築 | a1=0, a2=ストレス(0/1/2), a3=単語音素数 |
| 5 | `__all__` + モジュールレベル便利関数 | `phonemize_swedish()`, `phonemize_swedish_with_prosody()` |

**完了基準**: Phonemizer ABC の全メソッドが正しく動作、辞書内語100%正確

---

### M1.5 マルチリンガル統合

| 項目 | 内容 |
|------|------|
| 目標 | "sv" をpiper-plusの言語レジストリに統合 |
| 成果物 | `registry.py`, `multilingual.py`, `multilingual_id_map.py` 変更 |
| 対応要件 | FR-06 |
| 前提 | M1.4 (SwedishPhonemizer 完成) |

**タスク**:

| # | タスク | 詳細 |
|---|--------|------|
| 1 | `registry.py` | `_auto_register()` に SwedishPhonemizer 登録、`_detect_default_latin()` に "sv" 追加 |
| 2 | `multilingual.py` | `_latin_languages` に "sv" 追加 |
| 3 | `multilingual_id_map.py` | `LANGUAGE_PHONEMES["sv"]` 登録 |
| 4 | 動作検証 | `get_phonemizer("sv")`, `get_phonemizer("en-sv")` が動作 |

**完了基準**: sv単独 + en-sv マルチリンガルが動作、既存6言語に影響なし

---

### M1.6 テストスイート + CI

| 項目 | 内容 |
|------|------|
| 目標 | 110+ テストケースの実装とCI統合 |
| 成果物 | `test/test_swedish_phonemizer.py`, CI ワークフロー確認 |
| 対応要件 | FR-07, NFR-03 |
| 前提 | M1.5 (全統合完了) |

**タスク**:

| # | タスク | テスト数 |
|---|--------|---------|
| 1 | 基本母音テスト | 10 |
| 2 | Soft/Hard テスト | 15 |
| 3 | レトロフレックステスト | 12 |
| 4 | sj-sound テスト | 20 |
| 5 | 母音長テスト | 10 |
| 6 | "o" 曖昧性テスト | 10 |
| 7 | 非強勢母音テスト | 8 |
| 8 | ストレステスト | 10 |
| 9 | ローンワードテスト | 10 |
| 10 | エッジケーステスト | 5 |
| 11 | 回帰テスト | 既存6言語の非影響確認 |
| 12 | CI確認 | `python-tests.yml` で全テスト PASS |

**完了基準**: 110テスト全PASS、既存テスト全PASS、CI green

---

## Phase 2: クロスプラットフォーム

**目標**: Phase 1 の Python 実装を全プラットフォームにポート

### M2.1 Rust 実装

| 項目 | 内容 |
|------|------|
| 成果物 | `src/rust/piper-core/src/phonemize/swedish.rs` |
| 前提 | Phase 1 完了 |

**タスク**: 辞書ロード (HashMap) + G2P規則のRustポート + Phonemizer trait 実装 + テスト

### M2.2 C# 実装

| 項目 | 内容 |
|------|------|
| 成果物 | `src/csharp/PiperPlus.Core/Phonemize/SwedishPhonemizer.cs` |
| 前提 | Phase 1 完了 |

**タスク**: 辞書ロード (Dictionary) + G2P規則のC#ポート + IPhonemizer 実装 + xUnit テスト

### M2.3 C++ 実装

| 項目 | 内容 |
|------|------|
| 成果物 | `src/cpp/swedish_phonemize.cpp`, `swedish_phonemize.hpp` |
| 前提 | Phase 1 完了 |

**タスク**: 辞書ロード (unordered_map) + G2P規則のC++ポート + CMakeLists.txt 更新 + テスト

### M2.4 WASM/JS 実装

| 項目 | 内容 |
|------|------|
| 成果物 | `src/wasm/openjtalk-web/src/swedish.js` |
| 前提 | Phase 1 完了 |

**タスク**: 辞書ロード (IndexedDB キャッシュ) + G2P規則のJSポート + Node.js テスト

---

## Phase 3: TTSモデル学習 & リリース

**目標**: スウェーデン語音声合成モデルの学習と公開

### M3.1 データセット準備

| 項目 | 内容 |
|------|------|
| 成果物 | スウェーデン語TTSデータセット (LJSpeech形式) |
| 前提 | Phase 1 完了 (Phonemizer で phoneme_ids 生成) |

**タスク**: 音声データ収集/選定、PhonemizerでG2P変換、prosody_features 付与、データセット検証

### M3.2 ファインチューニング

| 項目 | 内容 |
|------|------|
| 成果物 | 学習済みチェックポイント |
| 前提 | M3.1, 6langベースモデル (epoch=74-step=504712.ckpt) |

**タスク**: `--resume-from-multispeaker-checkpoint` でベースモデルから転移学習、Template B パラメータ適用

### M3.3 ONNX エクスポート + リリース

| 項目 | 内容 |
|------|------|
| 成果物 | ONNX モデル (FP16), HuggingFace 公開 |
| 前提 | M3.2 |

**タスク**: `export_onnx.py` でエクスポート、推論テスト (全6言語+sv)、HuggingFace アップロード、README更新

---

## Phase 4: 品質向上 (将来)

**目標**: 声調、複合語、数字対応で品質を向上

### M4.1 声調アクセント対応

| 項目 | 内容 |
|------|------|
| 成果物 | ProsodyInfo a1 に accent 1/2 をマッピング |
| 前提 | Phase 1 完了、NST辞書オリジナル版 (51フィールド) の声調情報取得 |

**タスク**: NST オリジナル辞書の `"` (accent 1) / `""` (accent 2) パース、OOV向け形態論規則 (単音節=1, 複合語=2)、`prosody_language_ids` に sv 追加

### M4.2 複合語分割改善

| 項目 | 内容 |
|------|------|
| 成果物 | 複合語分割ヒューリスティック (結合形素 s/e/o 対応) |
| 前提 | Phase 1 完了 |

**タスク**: 右→左走査の最長一致分割、結合形素検出、複合語ストレス (第1要素=主、第2要素=副)

### M4.3 数字・略語展開

| 項目 | 内容 |
|------|------|
| 成果物 | 数字→スウェーデン語テキスト変換、略語辞書 |
| 前提 | Phase 1 完了 |

**タスク**: 基数/序数変換 (ett/en 区別含む)、一般略語 (km, Dr., st. 等)、日付/時刻フォーマット
