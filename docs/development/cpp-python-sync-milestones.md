# C++ / Python 同期 — マイルストーン計画

> **作成日**: 2026-03-08
> **ブランチ**: `fix/cpp-python-sync`
> **参照**: [cpp-python-implementation-diff.md](cpp-python-implementation-diff.md)

---

## 概要

C++ 推論パイプラインを Python 学習パイプラインと同期させるための段階的な修正計画。
全修正を4つのマイルストーンに分割し、各マイルストーンは独立してリリース可能。

### マイルストーン一覧

| MS | 名称 | 優先度 | 対象ファイル数 | 推定規模 | 状態 |
|----|------|--------|--------------|---------|------|
| **M1** | 音素化パイプライン同期 | Critical | 2 | L | ✅ 完了 (6/8 PASS) |
| **M1.5** | OpenJTalkフロントエンド統一 | Critical | 3+ | L | 🔲 未着手 |
| **M2** | ログ・テスト整合性 | High | 3 | S | 🔲 未着手 |
| **M3** | インターフェース改善 | Medium | 2 | M | 🔲 未着手 |
| **M4** | Docker 回帰テスト | High | 2 | M | 🔲 未着手 |

---

## M1: 音素化パイプライン同期 (Critical) — ✅ 完了

> **目標**: C++ の `openjtalk_phonemize.cpp` を Python の `japanese.py` と同等の音素化出力に揃える
> **影響**: 全テストケースで phoneme_ids が不一致（100%）→ 一致を目指す
> **コミット**: `c251b1d` (2026-03-08)
> **結果**: 8テスト中6テストでPython完全一致

### M1 テスト結果

| # | テキスト | 結果 | 備考 |
|---|---------|------|------|
| 1 | こんにちは、今日は良い天気ですね。 | ✅ PASS (38 ids) | |
| 2 | 本当ですか？ | ✅ PASS (16 ids) | |
| 3 | 本当?! | ✅ PASS (9 ids) | |
| 4 | そうなの？。 | ❌ FAIL | A1オフセット差異（prosodyマーク位置ずれ） |
| 5 | さんぽに行きましょう。 | ✅ PASS (21 ids) | |
| 6 | あんないします。 | ❌ FAIL | アクセント句分割差異（C++が2句、Pythonが1句） |
| 7 | ぎんこうに行きます。 | ✅ PASS (20 ids) | |
| 8 | 本を読みました。 | ✅ PASS (20 ids) | |

### M1 残存差異の原因分析

2件のFAILは**コードバグではなく、OpenJTalkフロントエンドの差異**:

- **Test 4**: OpenJTalkバイナリの A1 値がpyopenjtalkと異なるオフセット（C++: a1=-2 開始, Python: a1=0 開始）。`]`(アクセント核) の挿入位置がずれる。
- **Test 6**: OpenJTalkバイナリが「あんないします」を2アクセント句（4+3モーラ）に分割するのに対し、pyopenjtalkは1アクセント句（7モーラ）として解析。C++側に追加の `[` マークが挿入される。

→ **M1.5 で根本対策**（pyopenjtalkのCライブラリ直接リンク）

### M1-1: プロソディマーク挿入（栗原方式）

**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`
**対象関数**: `openjtalk_text_to_phonemes_with_prosody()` 内の音素列構築部分（行100-180付近）
**難易度**: M（約40行追加）
**依存**: なし（最初に実装すべき）

**実装内容**:
1. OpenJTalkから取得した音素リスト（A1/A2/A3付き）を処理する際、A2値の先読みを行い、以下の条件でプロソディマークトークンを挿入:

| 条件 | マーク | ID | 挿入位置 |
|------|--------|-----|---------|
| `a1 == 0 && a2_next == a2 + 1` | `]` | 9 | 当該音素の**後** |
| `a2 == a3 && a2_next == 1` | `#` | 7 | 当該音素の**後** |
| `a2 == 1 && a2_next == 2` | `[` | 8 | 当該音素の**前** |

2. 挿入されたマークの prosody_features は `{0, 0, 0}` とする
3. BOS (`^`) / EOS (`$`等) の prosody_features も `{0, 0, 0}` とする

**Python参照**: `japanese.py` 行213-246 (`phonemize_with_prosody` メソッド内)

```python
# 栗原方式の条件
if a2 == 1 and a2_next == 2:
    phonemes.insert(pos, "[")     # ピッチ上昇
if a1 == 0 and a2_next == a2 + 1:
    phonemes.append("]")          # アクセント核
if a2 == a3 and a2_next == 1:
    phonemes.append("#")          # アクセント句境界
```

**C++疑似コード**:
```cpp
// openjtalk_text_to_phonemes_with_prosody() 内
std::vector<PhonemeWithProsody> result;
for (size_t i = 0; i < raw_phonemes.size(); i++) {
    int a1 = raw_phonemes[i].a1;
    int a2 = raw_phonemes[i].a2;
    int a3 = raw_phonemes[i].a3;
    int a2_next = (i + 1 < raw_phonemes.size()) ? raw_phonemes[i+1].a2 : 0;

    // [: ピッチ上昇（当該音素の前に挿入）
    if (a2 == 1 && a2_next == 2) {
        result.push_back({"[", {0, 0, 0}});
    }

    result.push_back(raw_phonemes[i]);

    // ]: アクセント核（当該音素の後に挿入）
    if (a1 == 0 && a2_next == a2 + 1) {
        result.push_back({"]", {0, 0, 0}});
    }
    // #: アクセント句境界（当該音素の後に挿入）
    if (a2 == a3 && a2_next == 1) {
        result.push_back({"#", {0, 0, 0}});
    }
}
```

**テストケース**:
| 入力 | 期待する挿入 |
|------|------------|
| 「こんにちは」 | `[` が句頭に挿入 |
| 「今日は良い天気ですね。」 | `[` × 4, `]` × 3 が各アクセント句に挿入 |
| 「ありがとうございます。」 | `#` がアクセント句境界に挿入 |

---

### M1-2: 文脈依存Nバリアント

**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`
**対象関数**: 新規関数 `applyNPhonemeRules()` を追加、音素列構築後に呼び出し
**難易度**: M（約50行追加）
**依存**: M1-1の後（プロソディマーク挿入済みの音素列に対して適用）

**実装内容**:
1. `phonemeToPua` マップに4エントリ追加:
   ```cpp
   {"N_m", 0xE019}, {"N_n", 0xE01A}, {"N_ng", 0xE01B}, {"N_uvular", 0xE01C}
   ```

2. `applyNPhonemeRules()` 関数を実装:
   - 音素列を走査し、`N` を発見したら次の音素を確認
   - 次の音素に基づき `N` を適切なバリアントに置換

**分類ルール**:
| バリアント | PUA | 条件（次の音素） |
|-----------|-----|----------------|
| `N_m` | 0xE019 | `m`, `my`, `b`, `by`, `p`, `py` |
| `N_n` | 0xE01A | `n`, `ny`, `t`, `ty`, `d`, `dy`, `ts`, `ch` |
| `N_ng` | 0xE01B | `k`, `ky`, `kw`, `g`, `gy`, `gw` |
| `N_uvular` | 0xE01C | 語末 / 母音(`a`,`i`,`u`,`e`,`o`) / その他 |

**Python参照**: `japanese.py` 行85-132 (`_apply_n_phoneme_rules()`)

**C++疑似コード**:
```cpp
void applyNPhonemeRules(std::vector<std::string>& phonemes) {
    static const std::set<std::string> bilabial = {"m", "my", "b", "by", "p", "py"};
    static const std::set<std::string> alveolar = {"n", "ny", "t", "ty", "d", "dy", "ts", "ch"};
    static const std::set<std::string> velar = {"k", "ky", "kw", "g", "gy", "gw"};

    for (size_t i = 0; i < phonemes.size(); i++) {
        if (phonemes[i] != "N") continue;

        std::string next = (i + 1 < phonemes.size()) ? phonemes[i + 1] : "";
        // スペシャルトークン([, ], #, $, ?)はスキップして実音素を探す
        size_t j = i + 1;
        while (j < phonemes.size() && isSpecialToken(phonemes[j])) j++;
        std::string nextReal = (j < phonemes.size()) ? phonemes[j] : "";

        if (bilabial.count(nextReal))      phonemes[i] = "N_m";
        else if (alveolar.count(nextReal)) phonemes[i] = "N_n";
        else if (velar.count(nextReal))    phonemes[i] = "N_ng";
        else                               phonemes[i] = "N_uvular";
    }
}
```

**エッジケース**:
- 「ん」が文末にある場合 → `N_uvular`
- 「ん」の後にプロソディマーク (`]`, `#`) がある場合 → マークをスキップして実音素を参照
- 「んん」のように連続する場合 → 各 `N` を独立に処理

**テストケース**:
| 入力 | N位置 | 次の音素 | 期待 |
|------|-------|---------|------|
| さんぽ | N→p | p (両唇音) | N_m |
| あんない | N→n | n (歯茎音) | N_n |
| ぎんこう | N→k | k (軟口蓋音) | N_ng |
| ほん (語末) | N→EOS | — | N_uvular |
| ほんを | N→o | o (母音) | N_uvular |

---

### M1-3: 疑問詞マーカー

**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`
**対象関数**: 新規関数 `getQuestionType()` を追加、EOS生成時に呼び出し
**難易度**: M（約40行追加）
**依存**: なし（M1-1, M1-2と独立に実装可能）

**実装内容**:
1. `phonemeToPua` マップに3エントリ追加:
   ```cpp
   {"?!", 0xE016}, {"?.", 0xE017}, {"?~", 0xE018}
   ```

2. `getQuestionType()` 関数を実装:
   - 元テキストの末尾を解析して疑問詞タイプを判定
   - 結果に応じたEOSトークンを返す

**分類ルール**:
| テキスト末尾パターン | EOSトークン | ID |
|-------------------|-----------|-----|
| 疑問符なし | `$` | 2 |
| `?`, `？` | `?` | 3 |
| `?!`, `！？`, `？！`, `!?` | `?!` (PUA 0xE016) | 4 |
| `?.`, `。？`, `？。` | `?.` (PUA 0xE017) | 5 |
| `?~`, `～？`, `？～` | `?~` (PUA 0xE018) | 6 |

**Python参照**: `japanese.py` 行40-78 (`_get_question_type()`)

**C++疑似コード**:
```cpp
std::string getQuestionType(const std::string& text) {
    // UTF-8テキストの末尾2文字を取得
    auto last2 = getLastNChars(text, 2);  // UTF-8対応が必要

    // 強調疑問: ?! or !? or ？！ or ！？
    if (endsWithAny(last2, {"?!", "!?", "？！", "！？"}))
        return "?!";
    // 平叙疑問: ?. or 。？ or ？。
    if (endsWithAny(last2, {"?.", "。？", "？。"}))
        return "?.";
    // 確認疑問: ?~ or ～？ or ？～
    if (endsWithAny(last2, {"?~", "～？", "？～"}))
        return "?~";

    // 単純疑問: ? or ？
    auto lastChar = getLastNChars(text, 1);
    if (lastChar == "?" || lastChar == "？")
        return "?";

    // 平叙文
    return "$";
}
```

**注意点**:
- テキストはUTF-8エンコーディング → 全角文字（`？`, `！`, `。`, `～`）は3バイト
- 末尾の空白・改行を除去してから判定する必要あり
- OpenJTalkは末尾の句読点を `sil` に変換するため、元テキストから判定する必要がある

**テストケース**:
| 入力 | 期待EOS |
|------|--------|
| 「こんにちは。」 | `$` (ID=2) |
| 「本当ですか？」 | `?` (ID=3) |
| 「本当?!」 | `?!` (ID=4) |
| 「そうなの？。」 | `?.` (ID=5) |
| 「行くよね？～」 | `?~` (ID=6) |
| 「マジ！？」 | `?!` (ID=4) |

---

### M1-4: EOS処理の統合

**対象ファイル**: `src/cpp/openjtalk_phonemize.cpp`
**対象関数**: 末尾 `sil` → EOS 変換部分
**難易度**: S（約10行変更）
**依存**: M1-3（疑問詞マーカー実装後）

**実装内容**:
- 現在の C++ は末尾 `sil` を一律 EOS (`$`, ID=2) に変換している
- M1-3 の `getQuestionType()` の結果を使い、適切な EOS トークンに変換

**変更前**:
```cpp
// 末尾 sil の処理
if (phoneme == "sil" && isLast) {
    // → $ (EOS) を追加
}
```

**変更後**:
```cpp
if (phoneme == "sil" && isLast) {
    std::string eosType = getQuestionType(originalText);
    // → eosType に応じたトークンを追加
}
```

---

### M1 完了条件

- [x] ~~8つのテストテキスト全てで Python と同一の phoneme_ids が生成される~~ → 6/8 PASS（残2件はM1.5で対応）
- [x] プロソディマーク (`[`, `]`, `#`) が正しい位置に挿入される（ロジックはPythonと同一）
- [x] Nバリアント (N_m, N_n, N_ng, N_uvular) が正しく分類される
- [x] 疑問詞マーカー (`?`, `?!`, `?.`, `?~`) が正しく生成される
- [x] prosody_features のトークン数が phoneme_ids と一致する
- [ ] 既存の C++ テストが全てパスする → M2で対応

---

## M1.5: OpenJTalkフロントエンド統一 (Critical)

> **目標**: C++がOpenJTalkバイナリ(system()呼び出し)を使用しているのをpyopenjtalkのCライブラリ直接呼び出しに置き換え、Python/C++間のA1/A2/A3値の完全一致を保証する
> **影響**: M1で残存した2件のテスト不一致を根本解消。全テキストで品質の完全一致を実現。
> **依存**: M1完了後

### 背景

現在のC++は`system()`で外部OpenJTalkバイナリを呼び出してfullcontextラベルを取得しているが、Pythonは`pyopenjtalk.extract_fullcontext()`でCライブラリを直接呼び出している。

同じOpenJTalkでも、バイナリ版とCライブラリ版では辞書バージョン・アクセント解析アルゴリズムが異なり、以下の差異が発生する:

| 差異 | 影響 | 発生例 |
|------|------|--------|
| A1値のオフセット | prosodyマーク(`]`)の位置ずれ | 「そうなの？。」 |
| アクセント句分割の違い | 余分な`[`マーク挿入 | 「あんないします。」 |
| A3値の違い | `#`(句境界)の有無 | 複合語で差異の可能性 |

### M1.5-1: pyopenjtalkのCライブラリ直接リンク

**対象ファイル**: `src/cpp/openjtalk_wrapper.c`, `CMakeLists.txt`
**難易度**: L（ビルドシステム変更を伴う）

**現状**: `openjtalk_wrapper.c` 内に直接API呼び出しのコメントアウトされたコードが存在（行380-494）。以下の理由で無効化されている:
- OpenJTalk静的ライブラリのリンクが必要
- `libOpenJTalk.a` がCMakeで未リンク（`libHTSEngine.a` は既にリンク済み）

**実装方針**:

1. **pyopenjtalk/open_jtalkのビルド統合**:
   - pyopenjtalkが内部で使用しているOpenJTalk + MeCab + NAIST-JDicと同じバージョンをC++ビルドに組み込む
   - CMakeLists.txtにOpenJTalk静的ライブラリのリンクを追加

2. **直接API呼び出しの実装**:
   ```cpp
   // system() + ファイルI/O の代わりに直接呼び出し
   #include "openjtalk_api.h"

   OpenJTalkProsodyResult* openjtalk_text_to_phonemes_with_prosody(const char* text) {
       OpenJTalk* oj = openjtalk_initialize(dictionary_path);
       HTS_Label* labels = openjtalk_extract_fullcontext(oj, text);
       // ラベルからA1/A2/A3を抽出（既存のパースロジックを流用）
       // ...
       openjtalk_finalize(oj);
       return result;
   }
   ```

3. **辞書の同梱**:
   - pyopenjtalkと同じNAIST-JDicバージョンをDockerイメージ/バイナリ配布に含める
   - 辞書パスの設定方法を統一

**代替案**:

| アプローチ | メリット | デメリット | 推奨 |
|-----------|---------|-----------|:---:|
| **A: OpenJTalk Cライブラリ直接リンク** | 完全一致保証、プロセス起動不要 | ビルド複雑化、辞書バージョン管理 | ✅ |
| B: pyopenjtalkをC++から呼ぶ（Python埋め込み） | 確実に一致 | Python依存が増える | ❌ |
| C: 辞書バージョンのみ統一 | 変更最小 | 完全一致は保証されない | ❌ |

### M1.5-2: Docker辞書バージョン統一

**対象ファイル**: `docker/cpp-inference/Dockerfile`, `src/cpp/openjtalk_dictionary_manager.c`
**難易度**: M

pyopenjtalkが使用するNAIST-JDicバージョンを特定し、C++ビルドでも同じバージョンを使用するようにする。

### M1.5-3: 回帰テスト8/8 PASS確認

**前提**: M1.5-1またはM1.5-2完了後
**難易度**: S

M1で使用した8テストケース全てでphoneme_idsの完全一致を確認。

### M1.5 完了条件

- [ ] C++がOpenJTalkのCライブラリを直接呼び出し（system()廃止）
- [ ] pyopenjtalkと同じ辞書バージョンを使用
- [ ] 8つのテストテキスト全てでPythonと同一のphoneme_idsが生成される（8/8 PASS）
- [ ] prosody_features (A1/A2/A3) がPythonと完全一致
- [ ] プロセス起動オーバーヘッドの解消（パフォーマンス改善）

---

## M2: ログ・テスト整合性 (High)

> **目標**: デバッグ出力の完全性とテストコードの正確性を確保
> **影響**: 開発効率・CI信頼性

### M2-1: puaToPhoneme ログ表示用マップ更新

**対象ファイル**: `src/cpp/piper.cpp`
**対象**: `puaToPhoneme` マップ（行60付近）
**難易度**: S（7行追加）

**実装内容**:
```cpp
// 既存マップに追加
{0xE016, "?!"}, {0xE017, "?."}, {0xE018, "?~"},
{0xE019, "N_m"}, {0xE01A, "N_n"}, {0xE01B, "N_ng"}, {0xE01C, "N_uvular"}
```

---

### M2-2: test_prosody_inference.cpp の型修正

**対象ファイル**: `src/cpp/tests/test_prosody_inference.cpp`
**対象**: `ProsodyTensorDataType` テスト
**難易度**: S（数行変更）

**実装内容**:
- 現在: `ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT` を期待
- 修正: `ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64` に変更
- 理由: 実際の `piper.cpp` のパイプラインでは int64 を使用

---

### M2-3: 新機能のユニットテスト追加

**対象ファイル**: 新規 `src/cpp/tests/test_n_variants.cpp`、`src/cpp/tests/test_question_markers.cpp`
**難易度**: M（各約30行）

**テストケース**:

#### test_n_variants.cpp
```
TEST: N_m_before_bilabial  — 「さんぽ」→ N が N_m に変換
TEST: N_n_before_alveolar  — 「あんない」→ N が N_n に変換
TEST: N_ng_before_velar    — 「ぎんこう」→ N が N_ng に変換
TEST: N_uvular_at_end      — 「ほん」→ N が N_uvular に変換
TEST: N_uvular_before_vowel — 「ほんを」→ N が N_uvular に変換
```

#### test_question_markers.cpp
```
TEST: Declarative           — 「こんにちは。」→ EOS = $
TEST: SimpleQuestion        — 「本当？」→ EOS = ?
TEST: EmphasisQuestion      — 「本当?!」→ EOS = ?!
TEST: DeclarativeQuestion   — 「そうなの？。」→ EOS = ?.
TEST: ConfirmQuestion       — 「行くよね？～」→ EOS = ?~
TEST: FullwidthEmphasis     — 「マジ！？」→ EOS = ?!
```

---

### M2-4: CMakeLists.txt テスト登録

**対象ファイル**: `CMakeLists.txt` または `src/cpp/tests/CMakeLists.txt`
**難易度**: S

新規テストファイルをビルド対象に追加。

---

### M2 完了条件

- [ ] `--debug` 出力で新PUAトークンが正しい名前で表示される
- [ ] prosody_features 型テストが int64 で通過する
- [ ] 新規テスト (N variants, question markers) が全てパスする
- [ ] CI（GitHub Actions）が全テストパスする

---

## M3: インターフェース改善 (Medium)

> **目標**: C++ 推論の柔軟性を向上
> **影響**: 外部ツール連携・デバッグ効率

### M3-1: JSON入力で prosody_features サポート

**対象ファイル**: `src/cpp/main.cpp`
**対象関数**: `--json-input` モードのJSON解析部分（行50-120付近）
**難易度**: M（約40行追加）

**実装内容**:
- JSON入力フォーマットに `prosody_features` フィールドを追加:
  ```json
  {
    "text": "こんにちは",
    "speaker_id": 0,
    "prosody_features": [[a1,a2,a3], [a1,a2,a3], ...]
  }
  ```
- `prosody_features` が指定された場合、自動生成の代わりにそれを使用
- `prosody_features` が省略された場合、従来通り自動生成

**現在のJSON入力フィールド**: `text`, `speaker_id`, `speaker`, `output_file`
**追加フィールド**: `prosody_features` (optional)

---

### M3-2: カスタム辞書の日本語単語境界修正

**対象ファイル**: `src/cpp/custom_dictionary.cpp`
**対象関数**: `loadDictionary()` / `applyDictionary()` 内の正規表現構築部分
**難易度**: M（約30行変更）

**問題**:
- 現在の C++ は辞書エントリのマッチに `\b`（ワードバウンダリ）を使用
- `\b` は ASCII のワードバウンダリにのみ対応し、日本語文字（マルチバイト UTF-8）では正しく動作しない
- 例: 辞書に「東京」を登録しても、`\b東京\b` が日本語テキスト内でマッチしない

**Python側の対処** (`custom_dict.py`):
```python
if ord(c) > 127:  # 非ASCII → ワードバウンダリ不要
    pattern = word  # そのまま使用
else:
    pattern = r'\b' + word + r'\b'
```

**C++修正案**:
```cpp
std::string buildPattern(const std::string& word) {
    // 先頭文字がマルチバイト（UTF-8で0x80以上）か判定
    if (static_cast<unsigned char>(word[0]) > 0x7F) {
        return word;  // 日本語: バウンダリなし
    }
    return "\\b" + word + "\\b";  // ASCII: 従来通り
}
```

---

### M3 完了条件

- [ ] `--json-input` で `prosody_features` を渡して推論できる
- [ ] 日本語辞書エントリが正しくマッチする
- [ ] 英語辞書エントリの `\b` 動作が維持される

---

## M4: Docker 回帰テスト (High)

> **目標**: 全修正後に C++ と Python の推論結果が一致することを Docker で検証
> **影響**: リリース品質保証

### M4-1: Docker イメージ再ビルド

**対象**: `docker/cpp-inference/Dockerfile`
**難易度**: S

修正済みの C++ コードで Docker イメージを再ビルド。

---

### M4-2: 回帰テストスクリプト作成

**対象ファイル**: 新規 `docker/cpp-inference/regression_test.sh`
**難易度**: M

**テスト内容**:
1. 8つのテストテキストで C++ と Python の両方を推論
2. phoneme_ids の完全一致を検証
3. prosody_features のトークン数一致を検証
4. 疑問詞EOS の一致を検証

```bash
#!/bin/bash
TEXTS=(
  "こんにちは、今日は良い天気ですね。"
  "本当ですか？"
  "本当?!"
  "そうなの？。"
  "さんぽに行きましょう。"
  "あんないします。"
  "ぎんこうに行きます。"
  "本を読みました。"
)

for text in "${TEXTS[@]}"; do
  cpp_ids=$(echo "$text" | piper --model ... --debug 2>&1 | grep "Converted" | ...)
  py_ids=$(python analyze_phonemes.py "$text" | ...)
  if [ "$cpp_ids" != "$py_ids" ]; then
    echo "FAIL: $text"
    echo "  C++:    $cpp_ids"
    echo "  Python: $py_ids"
    exit 1
  fi
done
echo "ALL TESTS PASSED"
```

---

### M4-3: CI ワークフロー統合

**対象ファイル**: `.github/workflows/` 内の CI 定義
**難易度**: S

Docker 回帰テストを CI に追加（オプション）。

---

### M4 完了条件

- [ ] 8つのテストテキスト全てで C++ / Python の phoneme_ids が完全一致
- [ ] Docker イメージが正常にビルドできる
- [ ] 回帰テストスクリプトが全テストをパスする

---

## 実装順序（推奨）

```
M1: 音素化パイプライン同期 ✅ 完了 (6/8 PASS)
  │
  └── M1.5: OpenJTalkフロントエンド統一 ← 次のステップ
        ├── M1.5-1: Cライブラリ直接リンク
        ├── M1.5-2: 辞書バージョン統一
        └── M1.5-3: 8/8 PASS確認
              │
              ├── M2: ログ・テスト整合性
              │     ├── M2-1: puaToPhoneme更新 ✅ (M1で対応済み)
              │     ├── M2-2: 型修正
              │     ├── M2-3: テスト追加
              │     └── M2-4: CMake登録
              │
              ├── M3: インターフェース改善
              │     ├── M3-1: JSON prosody
              │     └── M3-2: 辞書修正
              │
              └── M4: Docker回帰テスト
                    ├── M4-1: Docker再ビルド
                    ├── M4-2: 回帰テスト
                    └── M4-3: CI
```

**推奨する作業フロー**:
1. ~~**M1** を実装~~ → ✅ 完了
2. **M1.5** で OpenJTalk フロントエンドを統一し、残存2件のテスト不一致を解消
3. **M2** で テスト・ログを整備
4. **M3** で インターフェースを改善
5. **M4** で Docker 回帰テストを実行して検証

---

## 対象ファイル変更サマリー

| ファイル | 変更種別 | マイルストーン | 状態 |
|---------|---------|-------------|------|
| `src/cpp/openjtalk_phonemize.cpp` | 大幅修正 | M1 | ✅ 完了 |
| `src/cpp/piper.cpp` | BOS/EOS制御 + マップ追加 | M1 | ✅ 完了 |
| `src/cpp/openjtalk_wrapper.c` | Cライブラリ直接呼び出し | M1.5-1 | 🔲 |
| `CMakeLists.txt` | OpenJTalkライブラリリンク | M1.5-1 | 🔲 |
| `src/cpp/openjtalk_dictionary_manager.c` | 辞書パス統一 | M1.5-2 | 🔲 |
| `docker/cpp-inference/Dockerfile` | 辞書バージョン統一 | M1.5-2 | 🔲 |
| `src/cpp/tests/test_prosody_inference.cpp` | 型修正 | M2-2 | 🔲 |
| `src/cpp/tests/test_n_variants.cpp` | **新規** | M2-3 | 🔲 |
| `src/cpp/tests/test_question_markers.cpp` | **新規** | M2-3 | 🔲 |
| `CMakeLists.txt` | テスト登録 | M2-4 | 🔲 |
| `src/cpp/main.cpp` | JSON拡張 | M3-1 | 🔲 |
| `src/cpp/custom_dictionary.cpp` | 境界修正 | M3-2 | 🔲 |
| `docker/cpp-inference/Dockerfile` | リビルド | M4-1 | 🔲 |
| `docker/cpp-inference/regression_test.sh` | **新規** | M4-2 | 🔲 |
