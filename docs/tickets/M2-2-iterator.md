# M2-2: Iterator パターン (synth_start / synth_next)

> **Phase:** 2 --- ストリーミング + テスト
> **見積り:** 大
> **依存:** M2-1 (音素化ループ抽出)
> **ブロック:** M2-3, M2-4, M2-5
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m2-2-iterator-パターン-synth_start--synth_next)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

文単位の逐次合成を実現する Iterator パターン API (`synth_start` / `synth_next`) を C API に追加する。OHF-Voice/piper1-gpl の libpiper と同様のパターンで、Go/Rust/低メモリ環境でチャンク単位の音声取得を可能にする。

**ゴール:**
- `piper_plus_synth_start()` でテキストを文分割してキューに保持する
- `piper_plus_synth_next()` で 1 文ずつ合成して `PiperPlusAudioChunk` を返す
- 最終チャンクで `PIPER_PLUS_DONE` を返してイテレーション完了を通知する
- ワンショット合成 / Iterator 合成の排他制御 (`PIPER_PLUS_ERR_BUSY`) を実装する

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/cpp/piper_plus.h` | `PiperPlusAudioChunk` 構造体、`synth_start` / `synth_next` 関数宣言、`PIPER_PLUS_ERR_BUSY` 定数追加 |
| `src/cpp/piper_plus_c_api.cpp` | `IteratorState` 内部構造体、`synth_start` / `synth_next` 実装 |

### 2.2 ヘッダー変更 (`piper_plus.h`)

```c
/* ===== 追加するステータスコード ===== */
#define PIPER_PLUS_ERR_BUSY  -6   /* Engine is busy (re-entrant call) */

/* ===== Audio chunk (既存。要求定義書 5 で定義済み) ===== */
/* PiperPlusAudioChunk は Phase 1 M1-5 で定義済みの想定:
 *   const float *samples;
 *   int32_t      num_samples;
 *   int32_t      sample_rate;
 *   int32_t      is_last;
 */

/* ===== Iterator pattern ===== */

/**
 * Start iterative synthesis.
 *
 * Splits text into sentences and prepares internal queue.
 * Call piper_plus_synth_next() repeatedly to get audio chunks.
 *
 * @param engine  Engine handle (must not be NULL)
 * @param text    UTF-8 text to synthesize (must not be NULL or empty)
 * @param opts    Synthesis options (NULL = defaults)
 * @return PIPER_PLUS_OK on success,
 *         PIPER_PLUS_ERR_BUSY if another synthesis is in progress,
 *         PIPER_PLUS_ERR on error
 *
 * @note This function is NOT thread-safe. One engine = one synthesis at a time.
 */
PIPER_PLUS_API int32_t piper_plus_synth_start(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts);

/**
 * Get next audio chunk from iterative synthesis.
 *
 * @param engine     Engine handle
 * @param out_chunk  Caller-provided struct, callee fills fields.
 *                   out_chunk->samples points to internal buffer;
 *                   valid until next synth_next() or synth_start() call.
 * @return PIPER_PLUS_OK    if chunk is available (more to come),
 *         PIPER_PLUS_DONE  if this was the last chunk (is_last=1),
 *         PIPER_PLUS_ERR   if synth_start() was not called
 */
PIPER_PLUS_API int32_t piper_plus_synth_next(
    PiperPlusEngine      *engine,
    PiperPlusAudioChunk  *out_chunk);
```

### 2.3 内部実装 (`piper_plus_c_api.cpp`)

#### IteratorState 構造体

```cpp
struct IteratorState {
    std::vector<std::string> sentences;       // splitTextToSentences() の結果
    size_t currentIndex = 0;                  // 次に合成する文のインデックス
    std::vector<float> currentChunkSamples;   // 現在のチャンクの float32 サンプル
    bool active = false;                      // Iterator がアクティブか

    // M2-1 の phonemizeText + synthesize に必要な保存状態
    piper::SynthesisConfig savedConfig;       // synth_start 時の synthesisConfig 保存
};
```

#### PiperPlusEngine 拡張

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;
    piper::Voice       voice;
    bool               inProgress = false;   // Phase 1 (M1-6) で追加済み
    IteratorState      iterState;            // Phase 2 で追加
};
```

#### synth_start 実装

```cpp
int32_t piper_plus_synth_start(PiperPlusEngine *engine,
                                const char *text,
                                const PiperPlusSynthOptions *opts) {
    if (!engine) { g_last_error = "engine is NULL"; return PIPER_PLUS_ERR; }
    if (!text || text[0] == '\0') { g_last_error = "text is NULL or empty"; return PIPER_PLUS_ERR_TEXT; }
    if (engine->inProgress) { g_last_error = "synthesis in progress"; return PIPER_PLUS_ERR_BUSY; }

    PIPER_PLUS_TRY

    // Mark busy
    engine->inProgress = true;

    // Apply synthesis options
    if (opts) {
        applySynthOptions(engine->voice.synthesisConfig, opts);
    }

    // Save config for restore after iteration
    engine->iterState.savedConfig = engine->voice.synthesisConfig;

    // Split text into sentences using M2-1 extracted function
    engine->iterState.sentences = piper::splitTextToSentences(
        text,
        engine->voice.phonemizeConfig.phonemeType,
        0  // default chunk size
    );

    engine->iterState.currentIndex = 0;
    engine->iterState.currentChunkSamples.clear();
    engine->iterState.active = true;

    // Handle empty split result
    if (engine->iterState.sentences.empty()) {
        engine->iterState.active = false;
        engine->inProgress = false;
        return PIPER_PLUS_OK;
    }

    return PIPER_PLUS_OK;

    PIPER_PLUS_CATCH(PIPER_PLUS_ERR)
}
```

#### synth_next 実装

```cpp
int32_t piper_plus_synth_next(PiperPlusEngine *engine,
                               PiperPlusAudioChunk *out_chunk) {
    if (!engine) { g_last_error = "engine is NULL"; return PIPER_PLUS_ERR; }
    if (!out_chunk) { g_last_error = "out_chunk is NULL"; return PIPER_PLUS_ERR; }
    if (!engine->iterState.active) {
        g_last_error = "synth_start() was not called";
        return PIPER_PLUS_ERR;
    }

    PIPER_PLUS_TRY

    auto &state = engine->iterState;

    // Check if all sentences processed
    if (state.currentIndex >= state.sentences.size()) {
        // Restore config and mark done
        engine->voice.synthesisConfig = state.savedConfig;
        state.active = false;
        engine->inProgress = false;

        out_chunk->samples = nullptr;
        out_chunk->num_samples = 0;
        out_chunk->sample_rate = engine->voice.synthesisConfig.sampleRate;
        out_chunk->is_last = 1;
        return PIPER_PLUS_DONE;
    }

    // Synthesize current sentence using textToAudio
    const std::string &sentence = state.sentences[state.currentIndex];
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult synthResult;

    piper::textToAudio(engine->config, engine->voice, sentence,
                       audioBuffer, synthResult, nullptr, nullptr);

    // Convert int16 -> float32
    state.currentChunkSamples.resize(audioBuffer.size());
    for (size_t i = 0; i < audioBuffer.size(); i++) {
        state.currentChunkSamples[i] =
            static_cast<float>(audioBuffer[i]) / 32767.0f;
    }

    state.currentIndex++;
    bool isLast = (state.currentIndex >= state.sentences.size());

    // Fill output chunk
    out_chunk->samples = state.currentChunkSamples.data();
    out_chunk->num_samples = static_cast<int32_t>(state.currentChunkSamples.size());
    out_chunk->sample_rate = engine->voice.synthesisConfig.sampleRate;
    out_chunk->is_last = isLast ? 1 : 0;

    // If last chunk, clean up
    if (isLast) {
        engine->voice.synthesisConfig = state.savedConfig;
        state.active = false;
        engine->inProgress = false;
    }

    return isLast ? PIPER_PLUS_DONE : PIPER_PLUS_OK;

    PIPER_PLUS_CATCH(PIPER_PLUS_ERR)
}
```

### 2.4 `textToAudio` ベースで実装する理由

技術調査 (1.6, 6.1) で発見された通り、`textToAudioStreaming()` のマルチリンガル処理にはデッドコード問題がある:

- `usesOpenJTalk()` が `MultilingualPhonemes` でも `true` を返す (piper.hpp L36)
- そのため `textToAudioStreaming()` L1756 の `else if (MultilingualPhonemes)` に到達しない
- マルチリンガルテキストは常に OpenJTalk-only の音素化パスを通り、英語/中国語等が正しく処理されない

`textToAudio()` はマルチリンガルを完全サポートしている (L1111-1293)。Iterator は `splitTextToSentences()` で文分割した後、各文を `textToAudio()` で個別合成するため、マルチリンガル問題を根本的に回避できる。

### 2.5 ポインタ寿命の設計

`out_chunk->samples` は `IteratorState.currentChunkSamples` の内部バッファを指す。次の `synth_next()` 呼び出しで上書きされるため、呼び出し側は次の呼び出し前にデータをコピーする必要がある。この規約はヘッダーの docstring に明記する。

### 2.6 排他制御

| 状況 | 結果 |
|------|------|
| Iterator 中に `piper_plus_synthesize()` を呼ぶ | `PIPER_PLUS_ERR_BUSY` |
| Iterator 中に `piper_plus_synth_start()` を呼ぶ | `PIPER_PLUS_ERR_BUSY` |
| `piper_plus_synthesize()` 中に `piper_plus_synth_start()` を呼ぶ | `PIPER_PLUS_ERR_BUSY` |
| `piper_plus_synth_start()` 後に `piper_plus_synth_next()` を全チャンク消費 | 正常終了、`inProgress = false` |

`inProgress` フラグは Phase 1 (M1-6) で `piper_plus_synthesize()` に既に実装されている前提。本チケットでは `synth_start` / `synth_next` でも同じフラグを使って排他制御する。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | ヘッダー拡張 + C API 実装 + IteratorState 設計 |
| テスター | 1 | M2-4 で詳細テストを担当 (本チケットでは基本的な手動動作確認のみ) |
| レビュアー | 1 | メモリ寿命 + 排他制御 + エラーパスのレビュー |

---

## 4. 提供範囲とテスト項目

### 4.1 本チケットのテスト (実装検証用、最小限)

本チケットでは実装コードのみ提供する。詳細なテストは M2-4 (ストリーミング単体テスト) と M2-5 (統合テスト) で行う。

ただし、実装者は以下の手動検証を行うこと:

- `synth_start(NULL, ...)` -> `PIPER_PLUS_ERR`
- `synth_next(engine, NULL)` -> `PIPER_PLUS_ERR`
- `synth_next` without `synth_start` -> `PIPER_PLUS_ERR`

### 4.2 受け入れ基準

- `synth_start` -> 複数回 `synth_next` -> `PIPER_PLUS_DONE` のフローが正常動作
- `out_chunk->samples` が次の `synth_next` まで有効
- Iterator 中の `piper_plus_synthesize()` 呼び出しは `PIPER_PLUS_ERR_BUSY`
- `PIPER_PLUS_ERR_BUSY` ステータスコードが `piper_plus.h` に定義されている
- `PiperPlusAudioChunk` が `piper_plus.h` に定義されている
- 3 プラットフォームでビルドが通る

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| `textToAudio()` が各文で `languageId` を変更する | 高 | `savedConfig` で `synth_start` 時の config を保存し、各 `synth_next` 呼び出し前に `languageId` を復元する。ただし auto-detect は文単位で機能させるため、`originalLanguageId` は各文で再設定する |
| 文分割の粒度がワンショットと異なる | 中 | `splitTextToSentences()` は `textToAudioStreaming()` の文分割ロジックを使うため、ワンショットとは文の粒度が異なる可能性がある。ワンショットでは `textToAudio()` が全テキストを 1 つの合成単位として処理するのに対し、Iterator は文ごとに分離する。音質の微差は許容する |
| 空文が `splitTextToSentences()` から返る可能性 | 低 | `synth_next` で空文はスキップし、次の文に進む |
| `IteratorState` のメモリ消費 | 低 | 文リスト + 現在のチャンクバッファのみ。チャンクは 1 文分なので通常数 KB 程度 |
| crossfade 非対応によるワンショットとの音質差 | 中 | `textToAudio` ベースの Iterator は文間の crossfade を行わない。`textToAudioStreaming()` (L1836-1844) は crossfade を実装しているが、Iterator はこのコードパスを使わない。そのため、文境界でのクリック音や不自然な接続が生じる可能性がある。対策として `sentence_silence_sec` (文間無音) を適切に設定することで接続部を滑らかにする。crossfade の Iterator 対応は Phase 4 候補として検討する (M2-6 後続タスクに記載) |

### 5.2 レビュー項目

- [ ] `IteratorState.currentChunkSamples` の寿命が `synth_next` 間で正しく管理されている
- [ ] `inProgress` フラグが全エラーパスで正しくリセットされている (例外含む)
- [ ] `savedConfig` の復元が Iterator 完了時 (正常/エラー両方) で行われている
- [ ] `PIPER_PLUS_CATCH` マクロが `inProgress` を `false` に戻しているか
- [ ] 空テキスト、1 文のみ、100 文のケースで正しく動作するか
- [ ] `PiperPlusAudioChunk` のフィールドが C99 POD として Dart `ffigen` 互換であるか

---

## 6. 一から作り直すとしたら

Iterator パターンの理想的な設計は、`textToAudio()` のモノリシック処理を完全にパイプライン化すること:

```
TextInput -> [Splitter] -> sentence_queue
             -> [Phonemizer] -> phoneme_queue
             -> [Synthesizer] -> audio_queue
             -> [Consumer]
```

各ステージがキューで接続され、Consumer が `synth_next()` で 1 チャンクずつ pull する設計。これにより:
- Phonemizer と Synthesizer を別スレッドで並列実行できる (レイテンシ改善)
- バックプレッシャーで自然なメモリ制御ができる

しかし、この設計は piper の C++ コアに大規模な変更が必要なため、現実的ではない。本チケットの「文分割 -> 逐次 textToAudio」方式は、最小の変更で動作する実用的な妥協。

---

## 7. 後続タスクへの連絡事項

### M2-3 (コールバック合成) への申し送り

- `piper_plus_synthesize_streaming()` は本チケットの Iterator を内部で駆動する薄いラッパーとして実装できる。`synth_start()` -> ループ `synth_next()` -> チャンクごとにコールバック呼び出し。
- `inProgress` フラグは Iterator と共有するため、コールバック合成でも排他制御は自動的に機能する。
- コールバック合成中の `synth_next()` は `PIPER_PLUS_ERR_BUSY` で拒否される (逆も同様)。

### M2-4 (テスト) への申し送り

- `IteratorState` のアクセスは `PiperPlusEngine` 内部に閉じているため、テストは公開 API (`synth_start` / `synth_next`) 経由でのみ行う。
- テストすべきエッジケース:
  - `synth_start` に空テキスト -> `PIPER_PLUS_ERR_TEXT`
  - `synth_start` 後に 0 文に分割される入力 (空白のみ等) -> 最初の `synth_next` で `PIPER_PLUS_DONE`
  - `synth_start` を 2 回連続 -> `PIPER_PLUS_ERR_BUSY`
  - Iterator 完了後に再度 `synth_start` -> 正常動作

### M2-5 (統合テスト) への申し送り

- Iterator の全チャンクサンプル数合計がワンショットのサンプル数と概ね一致することを確認するテストを追加すること。ただし、文分割の粒度が異なるため完全一致は期待しない (10% 以内の差を許容基準とする)。
