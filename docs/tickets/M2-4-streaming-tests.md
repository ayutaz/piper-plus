# M2-4: ストリーミング単体テスト (モデル不要)

> **Phase:** 2 --- ストリーミング + テスト
> **見積り:** 中
> **依存:** M2-2 (Iterator パターン), M2-3 (コールバック合成)
> **ブロック:** M2-5, M2-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m2-4-ストリーミング単体テスト-モデル不要)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

M2-2 / M2-3 で実装した Iterator パターンとコールバック合成の C API に対して、モデルファイルなしで実行可能な単体テストを追加する。M1-7 で追加済みのワンショット合成のモデル不要テストと同じファイル (`test_c_api.cpp`) に、ストリーミング固有のテストケースを追加する。

**ゴール:**
- NULL safety / エラーパスの網羅的テスト (モデルなし)
- `PiperPlusAudioChunk` 構造体のサイズ・アラインメント検証
- 排他制御の検証 (合成中に別の合成を呼ぶケース)
- 3 プラットフォームで CI GREEN

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/cpp/tests/test_c_api.cpp` | ストリーミング用テストケースを追加 |
| `src/cpp/tests/CMakeLists.txt` | 変更なし (test_c_api は M1-7 で登録済み) |

### 2.2 テストケース一覧

#### グループ 1: Iterator パターン (synth_start / synth_next)

```cpp
// --- Iterator: NULL safety ---

TEST(CApiStreamingTest, SynthStartNullEngine) {
    // synth_start with NULL engine should return ERR
    int32_t rc = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);

    const char *err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiStreamingTest, SynthStartNullText) {
    // synth_start with NULL text should return ERR_TEXT
    // Note: engine is also NULL here, so ERR takes precedence
    int32_t rc = piper_plus_synth_start(nullptr, nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingTest, SynthNextNullEngine) {
    // synth_next with NULL engine should return ERR
    PiperPlusAudioChunk chunk = {};
    int32_t rc = piper_plus_synth_next(nullptr, &chunk);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingTest, SynthNextNullChunk) {
    // synth_next with NULL out_chunk should return ERR
    // (engine is also NULL, so ERR for engine takes precedence)
    int32_t rc = piper_plus_synth_next(nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

// --- Iterator: state machine ---

TEST(CApiStreamingTest, SynthNextWithoutStart) {
    // synth_next without prior synth_start should return ERR
    // This requires a valid engine, but without a model we can't create one.
    // If a mock/stub engine becomes available, test here.
    // For now, verify NULL engine path.
    PiperPlusAudioChunk chunk = {};
    int32_t rc = piper_plus_synth_next(nullptr, &chunk);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}
```

#### グループ 2: コールバック合成 (synthesize_streaming)

```cpp
// --- Callback: NULL safety ---

TEST(CApiStreamingTest, StreamingNullEngine) {
    auto cb = [](const float*, int32_t, int32_t, void*) {};
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, "hello", nullptr,
        reinterpret_cast<PiperPlusAudioCallback>(+cb), nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingTest, StreamingNullText) {
    auto cb = [](const float*, int32_t, int32_t, void*) {};
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, nullptr, nullptr,
        reinterpret_cast<PiperPlusAudioCallback>(+cb), nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingTest, StreamingEmptyText) {
    auto cb = [](const float*, int32_t, int32_t, void*) {};
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, "", nullptr,
        reinterpret_cast<PiperPlusAudioCallback>(+cb), nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}

TEST(CApiStreamingTest, StreamingNullCallback) {
    // NULL callback should return ERR even with a valid engine
    // (engine is NULL here, so ERR for engine takes precedence)
    int32_t rc = piper_plus_synthesize_streaming(
        nullptr, "hello", nullptr, nullptr, nullptr);
    EXPECT_EQ(rc, PIPER_PLUS_ERR);
}
```

#### グループ 3: 構造体検証

```cpp
// --- Struct layout ---

TEST(CApiStreamingTest, AudioChunkStructSize) {
    // PiperPlusAudioChunk should be a simple POD struct
    // Verify it has the expected fields and is reasonably sized
    PiperPlusAudioChunk chunk = {};

    // Default initialization should zero all fields
    EXPECT_EQ(chunk.samples, nullptr);
    EXPECT_EQ(chunk.num_samples, 0);
    EXPECT_EQ(chunk.sample_rate, 0);
    EXPECT_EQ(chunk.is_last, 0);

    // Size should be pointer + 3 ints (with possible padding)
    // On 64-bit: pointer(8) + int32(4) + int32(4) + int32(4) = 20, padded to 24
    // On 32-bit: pointer(4) + int32(4) + int32(4) + int32(4) = 16
    EXPECT_GE(sizeof(PiperPlusAudioChunk), 16u);
    EXPECT_LE(sizeof(PiperPlusAudioChunk), 32u);
}

TEST(CApiStreamingTest, AudioChunkFieldOffsets) {
    // Verify fields are accessible and independently settable
    PiperPlusAudioChunk chunk = {};

    float dummy_samples[] = {0.1f, 0.2f, 0.3f};
    chunk.samples = dummy_samples;
    chunk.num_samples = 3;
    chunk.sample_rate = 22050;
    chunk.is_last = 1;

    EXPECT_EQ(chunk.samples[0], 0.1f);
    EXPECT_EQ(chunk.samples[2], 0.3f);
    EXPECT_EQ(chunk.num_samples, 3);
    EXPECT_EQ(chunk.sample_rate, 22050);
    EXPECT_EQ(chunk.is_last, 1);
}
```

#### グループ 4: ステータスコード定数

```cpp
TEST(CApiStreamingTest, StatusCodeValues) {
    // Verify status code constants are defined and have expected values
    EXPECT_EQ(PIPER_PLUS_OK, 0);
    EXPECT_EQ(PIPER_PLUS_DONE, 1);
    EXPECT_LT(PIPER_PLUS_ERR, 0);
    EXPECT_LT(PIPER_PLUS_ERR_MODEL, 0);
    EXPECT_LT(PIPER_PLUS_ERR_CONFIG, 0);
    EXPECT_LT(PIPER_PLUS_ERR_TEXT, 0);
    EXPECT_LT(PIPER_PLUS_ERR_BUSY, 0);

    // All error codes should be distinct
    std::set<int32_t> codes = {
        PIPER_PLUS_OK, PIPER_PLUS_DONE, PIPER_PLUS_ERR,
        PIPER_PLUS_ERR_MODEL, PIPER_PLUS_ERR_CONFIG,
        PIPER_PLUS_ERR_TEXT, PIPER_PLUS_ERR_BUSY
    };
    EXPECT_EQ(codes.size(), 7u);
}
```

#### グループ 5: 排他制御 (モデル不要パス)

```cpp
TEST(CApiStreamingTest, SynthStartBusyCheckPrecedence) {
    // When engine is NULL, ERR should be returned regardless of busy state.
    // This verifies the NULL check takes precedence over busy check.
    int32_t rc1 = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc1, PIPER_PLUS_ERR);

    // Immediately callable again (no state corruption from NULL engine)
    int32_t rc2 = piper_plus_synth_start(nullptr, "hello", nullptr);
    EXPECT_EQ(rc2, PIPER_PLUS_ERR);
}
```

### 2.3 テストケースの技術的制約

モデルなしの単体テストでは `PiperPlusEngine` を有効に作成できないため、以下のテストは M2-5 (統合テスト) に委譲する:

| テスト | 理由 | 委譲先 |
|--------|------|--------|
| `synth_start` -> `synth_next` -> `DONE` の正常フロー | モデルが必要 | M2-5 |
| `synth_start` 後に `synthesize` -> `ERR_BUSY` | 有効なエンジンが必要 | M2-5 |
| コールバックの `user_data` 転送 | 有効なエンジンが必要 | M2-5 |
| Iterator の全チャンクサンプル数確認 | モデルが必要 | M2-5 |

### 2.4 既存テスト (`test_c_api.cpp`) との統合

M1-7 で作成された `test_c_api.cpp` には以下のテストグループが既にある:

- `CApiTest`: version, default_options, NULL safety, invalid model path, error message, query null engine

本チケットでは `CApiStreamingTest` テストグループを追加。同じファイルに追記する形で、ヘッダーの `#include` は共有。

```cpp
// test_c_api.cpp の末尾に追加
// ===== Phase 2: Streaming tests =====

TEST(CApiStreamingTest, SynthStartNullEngine) { ... }
// ...
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| テスト実装者 | 1 | test_c_api.cpp へのテストケース追加 (~150 行) |

合計 1 名。全テストがモデル不要で高速実行可能なため、手動検証も容易。

---

## 4. 提供範囲とテスト項目

### 4.1 提供するテストの分類

| カテゴリ | テスト数 | 内容 |
|---------|---------|------|
| Iterator NULL safety | 4 | synth_start/next への NULL 引数 |
| Iterator state machine | 1 | synth_next without start |
| Callback NULL safety | 4 | streaming への NULL 引数 |
| Struct layout | 2 | AudioChunk のサイズ・フィールド検証 |
| Status codes | 1 | 全ステータスコード定数の値確認 |
| 排他制御 precedence | 1 | NULL vs busy のチェック順序 |
| **合計** | **13** | |

### 4.2 受け入れ基準

- 全 13 テストが 3 プラットフォーム (Linux / macOS / Windows) で PASS
- モデルファイル不要
- 既存の M1-7 テストに回帰なし
- テスト実行時間が 1 秒以内 (モデルロードなし)

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| モデルなしテストのカバレッジが限定的 | 中 | 正常パス (合成成功) のテストは全て M2-5 に委譲。本チケットではエラーパスと API 契約の検証に集中 |
| `PiperPlusAudioChunk` のサイズがプラットフォーム依存 | 低 | `sizeof()` の検証を 16-32 バイトの範囲チェックにして、32-bit / 64-bit 両方をカバー |
| コールバック関数ポインタのキャスト | 低 | C++ ラムダを `PiperPlusAudioCallback` にキャストする際、ABI 互換性に注意。stateless ラムダの `+` 演算子で関数ポインタに変換 |
| `#include <set>` の追加 | 低 | ステータスコードの uniqueness テストに `std::set` を使用。テストファイルへの `#include` 追加のみ |

### 5.2 レビュー項目

- [ ] 全テストがモデルなしで実行可能であること (`GTEST_SKIP()` は使用しない)
- [ ] 既存の `CApiTest` テストグループに影響しないこと
- [ ] `PiperPlusAudioChunk` のサイズ検証が 32-bit / 64-bit 両方で妥当であること
- [ ] コールバック関数ポインタのキャストが C99 互換であること
- [ ] エラーメッセージ検証 (`get_last_error`) が NULL チェック込みであること

---

## 6. 一から作り直すとしたら

テスト設計を一から考え直すなら:

**1. Mock Engine の導入:**
`PiperPlusEngine` の mock/stub を作成し、モデルなしでも `synth_start` -> `synth_next` の正常パスをテストできるようにする。現在の設計では `piper_plus_create()` がモデルロードを行うため、有効なエンジンを作成するにはモデルが必須。

mock 導入の方法:
- `piper_plus_create_mock()` テスト専用ファクトリ (固定波形を返すダミーモデル)
- テスト用の `PiperPlusEngine` を直接構築 (内部構造体へのアクセスが必要)

ただし、mock はメンテナンスコストが高く、内部構造への依存を生むため、現状の「エラーパスのみ単体テスト + 正常パスは統合テスト」の分割は実用的な妥協。

**2. テストファイルの分割:**
M1-7 の `test_c_api.cpp` が大きくなりすぎた場合、`test_c_api_streaming.cpp` に分割することを検討。ただし Phase 2 の時点ではテスト総数 ~20 程度 (M1-7 の ~6 + 本チケットの ~13) なので、分割は不要。

---

## 7. 後続タスクへの連絡事項

### M2-5 (統合テスト) への申し送り

- 本チケットでカバーできなかった正常パスのテストは M2-5 で網羅すること:
  - `synth_start` -> `synth_next` x N -> `DONE` の完全フロー
  - `synthesize_streaming` + コールバック呼び出し回数 >= 1
  - `user_data` の転送確認
  - Iterator 完了後の再利用 (`synth_start` -> ... -> `DONE` -> `synth_start` -> ...)
  - 排他制御: Iterator 中の `synthesize` -> `ERR_BUSY`
- テストモデルは `test/models/multilingual-test-medium.onnx` を使用 (存在しなければ `GTEST_SKIP`)

### M2-6 (CI 統合) への申し送り

- 本チケットのテストはモデル不要なので、既存の CI (`cpp-tests.yml`) のテスト実行ステップに `test_c_api` が含まれていれば自動的に実行される。追加の CI 設定は不要。
- M1-8 で `test_c_api` が CI のテストリストに追加済みであることを前提とする。
