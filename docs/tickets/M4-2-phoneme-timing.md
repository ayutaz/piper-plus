# M4-2: Phoneme timing 出力

> **Phase:** 4 -- 拡張 (将来)
> **利用者視点の優先度:** 高 -- Godot/Unity のリップシンクが主要ユースケース
> **見積り:** 中
> **依存:** Phase 3 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m4-2-phoneme-timing-出力)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

合成後の音素タイミング情報 (各音素の開始/終了時刻) を C API 経由で取得可能にする。リップシンク (Godot, Unity)、字幕同期、カラオケ表示などのユースケースに対応する。

**現状:** C++ 内部では `SynthesisResult::phonemeTimings` (`std::vector<PhonemeInfo>`) が既に利用可能。`piper.cpp` L815-824 で `extractTimingsFromDurations()` がタイミング情報を生成し、`result.hasTimingInfo = true` を設定している。CLI (`main.cpp`) では `--output-timing json|tsv` で出力可能。ただし、C API にはこの情報にアクセスする手段がない。

**ゴール:** ワンショット合成・Iterator 合成の両方で、合成後に音素タイミング情報を C 構造体として取得できる API を追加する。

---

## 2. 実装する内容の詳細

### 2.1 ヘッダー追加 (`src/cpp/piper_plus.h`)

```c
/* ===== Phoneme Timing (Phase 4) ===== */

/** Single phoneme timing entry. */
typedef struct PiperPlusPhonemeInfo {
    const char *phoneme;      /* UTF-8 phoneme string */
    float       start_time;   /* Start time in seconds */
    float       end_time;     /* End time in seconds */
    int32_t     start_frame;  /* Start frame index */
    int32_t     end_frame;    /* End frame index */
} PiperPlusPhonemeInfo;

/** Phoneme timing result. Owned by the engine; valid until next synthesis call. */
typedef struct PiperPlusTimingResult {
    const PiperPlusPhonemeInfo *entries;   /* Array of timing entries */
    int32_t                     count;     /* Number of entries */
} PiperPlusTimingResult;

/** Get phoneme timing information from the last synthesis call.
 *  Returns PIPER_PLUS_OK if timing is available, PIPER_PLUS_ERR otherwise.
 *  The result is valid until the next synthesis call on the same engine.
 *
 *  @note Timing is only available when the model has duration output.
 *        Check return value before accessing out_timing fields. */
PIPER_PLUS_API int32_t piper_plus_get_phoneme_timing(
    const PiperPlusEngine       *engine,
    PiperPlusTimingResult       *out_timing);
```

### 2.2 内部ストレージ (`src/cpp/piper_plus_c_api.cpp`)

**PiperPlusEngine 構造体拡張:**

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;
    piper::Voice       voice;
    bool               inProgress;
    // Phase 4: Phoneme timing
    piper::SynthesisResult lastResult;           // 直近の合成結果
    std::vector<PiperPlusPhonemeInfo> cTimings;   // C 構造体キャッシュ
    std::vector<std::string> timingStrings;       // 文字列バッファ (ポインタ寿命保証)
};
```

**合成後の結果保存:**

ワンショット合成 (`piper_plus_synthesize`) および Iterator の各 `synth_next` 呼び出し後に、`SynthesisResult` を `engine->lastResult` に保存する。

**`piper_plus_get_phoneme_timing` 実装:**

```cpp
int32_t piper_plus_get_phoneme_timing(
    const PiperPlusEngine *engine,
    PiperPlusTimingResult *out_timing
) {
    if (!engine || !out_timing) {
        return PIPER_PLUS_ERR;
    }
    if (!engine->lastResult.hasTimingInfo ||
        engine->lastResult.phonemeTimings.empty()) {
        out_timing->entries = nullptr;
        out_timing->count = 0;
        return PIPER_PLUS_ERR;
    }

    // C 構造体に変換 (キャッシュ)
    auto* mutableEngine = const_cast<PiperPlusEngine*>(engine);
    mutableEngine->timingStrings.clear();
    mutableEngine->cTimings.clear();

    for (const auto& t : engine->lastResult.phonemeTimings) {
        mutableEngine->timingStrings.push_back(t.phoneme);
        PiperPlusPhonemeInfo info;
        info.phoneme = mutableEngine->timingStrings.back().c_str();
        info.start_time = t.start_time;
        info.end_time = t.end_time;
        info.start_frame = t.start_frame;
        info.end_frame = t.end_frame;
        mutableEngine->cTimings.push_back(info);
    }

    out_timing->entries = mutableEngine->cTimings.data();
    out_timing->count = static_cast<int32_t>(mutableEngine->cTimings.size());
    return PIPER_PLUS_OK;
}
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | `PiperPlusPhonemeInfo`, `PiperPlusTimingResult` 構造体 + `piper_plus_get_phoneme_timing()` 宣言 |
| `src/cpp/piper_plus_c_api.cpp` | `PiperPlusEngine` に `lastResult` / `cTimings` / `timingStrings` 追加、合成後の結果保存、`get_phoneme_timing` 実装 |
| `src/cpp/tests/test_c_api.cpp` | タイミング取得テスト追加 |

**変更不要:** `piper.cpp` 内の `extractTimingsFromDurations()` は既存のまま利用。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | C API ラッパー実装 + テスト |

合計 1 名。既存の `SynthesisResult::phonemeTimings` を C 構造体に変換するだけで新規ロジックは不要。

---

## 4. 提供範囲とテスト項目

### スコープ

- C API に音素タイミング取得関数を追加
- ワンショット合成・Iterator 合成の両方で対応
- ストリーミングコールバック合成はチャンク単位のためタイミング取得不可 (制限事項として文書化)

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestGetTimingNullEngine` | `piper_plus_get_phoneme_timing(NULL, &result)` | `PIPER_PLUS_ERR` |
| `TestGetTimingNullOutput` | `piper_plus_get_phoneme_timing(engine, NULL)` | `PIPER_PLUS_ERR` |
| `TestGetTimingBeforeSynth` | 合成前にタイミング取得 | `PIPER_PLUS_ERR` + `count = 0` |
| `TestTimingStructLayout` | `PiperPlusPhonemeInfo` のサイズ・アラインメント | FFI 互換 (Dart ffigen で解析可能) |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestTimingAfterSynthesize` | ワンショット合成 -> タイミング取得 | `count > 0`, 各エントリの `start_time < end_time` |
| `TestTimingAfterSynthNext` | Iterator 合成 -> 各チャンクでタイミング取得 | チャンクごとにタイミングが更新される |
| `TestTimingPhonemeStrings` | タイミングの `phoneme` 文字列 | 有効な UTF-8 文字列 |
| `TestTimingTimeOrder` | 全エントリの時刻順 | `entries[i].end_time <= entries[i+1].start_time` |
| `TestTimingModelWithoutDuration` | duration 出力なしモデル | `PIPER_PLUS_ERR` + `count = 0` |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| ポインタ寿命 | 高 | `PiperPlusTimingResult` のポインタは次回合成まで有効。ヘッダーコメントに "valid until next synthesis call" を明記。`timingStrings` を `PiperPlusEngine` に保持して寿命を保証 |
| `const_cast` の安全性 | 中 | `piper_plus_get_phoneme_timing` は `const PiperPlusEngine*` を取るが、内部で `cTimings` キャッシュを更新する。API セマンティクス上は「読み取り」だが、内部的にはキャッシュ書き込みが発生。`mutable` で対応するか、`const` を外すか検討 |
| `hasTimingInfo` がモデル依存 | 中 | `session.hasDurationOutput` が false のモデルではタイミング取得不可。ドキュメントで明記し、`PIPER_PLUS_ERR` を返す |
| Iterator での累積タイミング | 低 | Iterator パターンでは文単位でタイミングが生成される。累積タイミング (全テキスト通しの時刻) が必要な場合は呼び出し側で offset を加算する。これは API ドキュメントで説明 |

### レビュー時の確認項目

1. `PiperPlusPhonemeInfo` が POD 構造体であること (Dart ffigen 互換)
2. `timingStrings` のバッファが次回合成まで生存すること
3. ワンショット合成で複数文のテキストを渡した場合、全文のタイミングが連結されること
4. `const_cast` の使用が最小限であること (代替: `mutable` キーワード)
5. ストリーミングコールバック合成での振る舞いがドキュメントに記載されていること

---

## 6. 一から作り直すとしたら

**タイミング情報をチャンクに埋め込む設計:** 現在の設計は「合成後に別関数で取得」だが、`PiperPlusAudioChunk` にタイミング情報を埋め込む方がスコープが明確。

```c
typedef struct PiperPlusAudioChunk {
    const float *samples;
    int32_t      num_samples;
    int32_t      sample_rate;
    int32_t      is_last;
    // Phase 4 拡張
    const PiperPlusPhonemeInfo *timings;
    int32_t                     timing_count;
} PiperPlusAudioChunk;
```

OHF-Voice/piper1-gpl の `piper_audio_chunk` もこのパターンを採用している。ただし、Phase 2 で既に定義された `PiperPlusAudioChunk` を変更すると ABI 互換性が壊れる。`_reserved` フィールドを使えば ABI 互換を維持できるが、設計の後付け感は否めない。

**理想的には Phase 2 の段階で** `PiperPlusAudioChunk` にタイミングフィールドを含めておくべきだった。

---

## 7. 後続タスクへの連絡事項

- **Phase 2 の `PiperPlusAudioChunk` 設計:** Phase 2 の `_reserved` フィールドの使い方として、将来のタイミング埋め込みを考慮しておくと、ABI 互換のまま拡張可能。
- **Godot リップシンク:** Godot GDExtension でリップシンクを実装する場合、音素→ viseme マッピングも必要になる。これは C API の範囲外だが、タイミング情報があれば GDExtension 側でマッピング可能。
- **JSON/TSV 出力:** 既存の `outputTimingsAsJSON()` / `outputTimingsAsTSV()` は `std::ostream` 依存。C API からは構造体で取得するため、JSON/TSV 変換は利用者側の責任。
