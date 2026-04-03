# M2-3: コールバック合成 (synthesize_streaming)

> **Phase:** 2 --- ストリーミング + テスト
> **見積り:** 小
> **依存:** M2-2 (Iterator パターン)
> **ブロック:** M2-4, M2-5
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m2-3-コールバック合成-synthesize_streaming)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

Flutter/Dart の `NativeCallable.listener` で音声チャンクを逐次受信するためのコールバック合成 API を追加する。M2-2 で実装した Iterator パターンを内部で駆動し、各チャンクを `PiperPlusAudioCallback` で呼び出し側に転送する薄いラッパー関数を提供する。

**ゴール:**
- `piper_plus_synthesize_streaming()` でテキストを文単位に分割しチャンクごとにコールバックを呼ぶ
- `user_data` ポインタが正しくコールバックに転送される
- Iterator と同じ排他制御 (`PIPER_PLUS_ERR_BUSY`) が機能する
- Dart FFI の `NativeCallable.listener` と互換 (void 戻りのコールバック)

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/cpp/piper_plus.h` | `PiperPlusAudioCallback` typedef (M1-5 で定義済みの想定)、`piper_plus_synthesize_streaming` 関数宣言の確認 |
| `src/cpp/piper_plus_c_api.cpp` | `piper_plus_synthesize_streaming` 実装 |

### 2.2 ヘッダー確認 (`piper_plus.h`)

以下の定義は M1-5 (ヘッダー作成) と要求定義書のセクション 5 で既に定義済みの想定。本チケットでは確認のみ。

```c
/* ===== Streaming callback ===== */
typedef void (*PiperPlusAudioCallback)(
    const float *samples,
    int32_t      num_samples,
    int32_t      sample_rate,
    void        *user_data
);

/* ===== Synthesis: streaming with callback ===== */

/**
 * Synthesize text with streaming callback.
 *
 * Internally drives the iterator pattern (synth_start/synth_next)
 * and calls the callback for each sentence chunk.
 *
 * @param engine     Engine handle (must not be NULL)
 * @param text       UTF-8 text to synthesize (must not be NULL or empty)
 * @param opts       Synthesis options (NULL = defaults)
 * @param callback   Audio callback (must not be NULL)
 * @param user_data  Opaque pointer passed to callback (may be NULL)
 * @return PIPER_PLUS_OK on success,
 *         PIPER_PLUS_ERR_BUSY if another synthesis is in progress,
 *         PIPER_PLUS_ERR on error
 *
 * @note The callback is invoked on the caller's thread (synchronous).
 * @note The samples pointer in the callback is valid only during the
 *       callback invocation. Callers must copy data if needed later.
 */
PIPER_PLUS_API int32_t piper_plus_synthesize_streaming(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    PiperPlusAudioCallback        callback,
    void                         *user_data);
```

**設計判断: `void` 戻りのコールバック**

Dart の `NativeCallable.listener` は void 戻りのコールバックのみ対応。コールバックの戻り値で合成中断を制御するパターン (sherpa-onnx 方式) は Dart から使えないため、本 API ではコールバックは常に void とし、中断機能は将来の Phase 4 で `PiperPlusAudioCallback` に `int` 戻りバリアントを追加する形で対応する。

### 2.3 実装 (`piper_plus_c_api.cpp`)

```cpp
int32_t piper_plus_synthesize_streaming(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    PiperPlusAudioCallback        callback,
    void                         *user_data) {

    if (!engine) { g_last_error = "engine is NULL"; return PIPER_PLUS_ERR; }
    if (!text || text[0] == '\0') { g_last_error = "text is NULL or empty"; return PIPER_PLUS_ERR_TEXT; }
    if (!callback) { g_last_error = "callback is NULL"; return PIPER_PLUS_ERR; }

    PIPER_PLUS_TRY

    // Start iterator (handles busy check internally)
    int32_t rc = piper_plus_synth_start(engine, text, opts);
    if (rc != PIPER_PLUS_OK) {
        return rc;  // ERR_BUSY or other error, g_last_error already set
    }

    // Drive iterator to completion
    PiperPlusAudioChunk chunk;
    for (;;) {
        rc = piper_plus_synth_next(engine, &chunk);

        if (rc == PIPER_PLUS_ERR) {
            // Error during synthesis - iterator already cleaned up inProgress
            return PIPER_PLUS_ERR;
        }

        // Deliver chunk to callback (even for PIPER_PLUS_DONE, which has
        // the last valid chunk with is_last=1)
        if (chunk.num_samples > 0) {
            callback(chunk.samples, chunk.num_samples,
                     chunk.sample_rate, user_data);
        }

        if (rc == PIPER_PLUS_DONE) {
            break;
        }
    }

    return PIPER_PLUS_OK;

    PIPER_PLUS_CATCH(PIPER_PLUS_ERR)
}
```

### 2.4 実装の核心: Iterator ラッパー

`synthesize_streaming` は M2-2 の `synth_start` / `synth_next` を内部で駆動する純粋なラッパー。新規のロジックは以下の 3 点のみ:

1. **NULL callback チェック**: `synth_start` にはない入力検証
2. **チャンクごとのコールバック呼び出し**: `synth_next` が返すチャンクの `samples` / `num_samples` / `sample_rate` をコールバックに転送
3. **最終チャンクの処理**: `PIPER_PLUS_DONE` 返却時も `num_samples > 0` ならコールバックを呼ぶ (最後の文の音声)

### 2.5 エラー時のクリーンアップ

- `synth_start` が失敗 (`ERR_BUSY` 等): Iterator は開始されていないため、クリーンアップ不要
- `synth_next` がエラー: `PIPER_PLUS_CATCH` マクロ内で例外がキャッチされた場合、`synth_next` 内部で `inProgress = false` にリセットされる (M2-2 の設計)
- `callback` 内で例外が投げられた場合: `PIPER_PLUS_TRY` / `PIPER_PLUS_CATCH` で補足し、`g_last_error` に記録。ただし `inProgress` が `true` のまま残るリスクがある

**対策: callback 例外時の inProgress リセット**

```cpp
// callback で例外が起きた場合のガード
// PIPER_PLUS_CATCH を拡張するか、ローカルの try-catch で対処
try {
    callback(chunk.samples, chunk.num_samples,
             chunk.sample_rate, user_data);
} catch (...) {
    // Callback threw - clean up iterator state
    engine->iterState.active = false;
    engine->inProgress = false;
    engine->voice.synthesisConfig = engine->iterState.savedConfig;
    g_last_error = "callback threw an exception";
    return PIPER_PLUS_ERR;
}
```

### 2.6 スレッドモデル

`piper_plus_synthesize_streaming()` は同期関数。コールバックは呼び出し元と同じスレッドで実行される。Flutter/Dart 側でバックグラウンドスレッドから呼び出し、UI スレッドへの転送は Dart の `Isolate` / `SendPort` で行う設計を想定。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | `piper_plus_synthesize_streaming` 実装 (~40 行) |

合計 1 名。M2-2 の Iterator を薄くラップするだけの小規模タスク。

---

## 4. 提供範囲とテスト項目

### 4.1 本チケットの提供範囲

- `piper_plus_synthesize_streaming()` の実装コードのみ
- 詳細テストは M2-4 / M2-5 で行う

### 4.2 手動検証項目 (実装者が確認)

| テスト | 期待結果 |
|--------|---------|
| `synthesize_streaming(NULL, ...)` | `PIPER_PLUS_ERR` |
| `synthesize_streaming(engine, NULL, ...)` | `PIPER_PLUS_ERR_TEXT` |
| `synthesize_streaming(engine, "hello", NULL, NULL, NULL)` | `PIPER_PLUS_ERR` (callback が NULL) |
| `synthesize_streaming` 中に `synthesize` を呼ぶ | `PIPER_PLUS_ERR_BUSY` |
| `synthesize_streaming` 中に `synth_start` を呼ぶ | `PIPER_PLUS_ERR_BUSY` |

### 4.3 受け入れ基準

- `piper_plus_synthesize_streaming` がヘッダーで宣言され、実装されている
- コールバックがチャンクごとに呼ばれる (M2-5 統合テストで検証)
- `user_data` が正しくコールバックに転送される
- NULL callback で `PIPER_PLUS_ERR` を返す
- 排他制御が Iterator / ワンショットと共有されている
- 3 プラットフォームでビルドが通る

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| callback 内の例外で `inProgress` がリークする | 中 | callback 呼び出しを try-catch でガードし、例外時に Iterator state を明示的にクリーンアップする |
| callback が長時間ブロックする | 低 | ドキュメントに「callback は速やかに返ること」を記載。C API は同期設計のため、callback のブロックは呼び出し側の責任 |
| `PIPER_PLUS_DONE` 時のチャンクが空 (`num_samples == 0`) の可能性 | 低 | `synth_next` が全文消費後に `DONE` を返す設計 (M2-2) では、最終チャンクは `is_last=1` + 有効サンプルを含む。空チャンクのコールバック呼び出しは `num_samples > 0` で防御 |
| C callback から C++ 例外が伝播するリスク | 低 | 要求定義書 NFR-4 の通り、全例外は API 境界で捕捉。callback はユーザー提供のため C++ 例外の throw は非推奨だが、安全のため try-catch でガード |

### 5.2 レビュー項目

- [ ] `synth_start` / `synth_next` の排他制御が callback 版でも正しく機能すること
- [ ] callback 内の例外で `inProgress` が正しくリセットされること
- [ ] `user_data` が `NULL` でも安全に動作すること
- [ ] `PIPER_PLUS_DONE` 返却時の最終チャンクが正しくコールバックされること
- [ ] ヘッダーの docstring が Dart FFI の制約 (void 戻り) を明記していること

---

## 6. 一から作り直すとしたら

コールバック合成を Iterator のラッパーとして実装するのは正しい判断。ただし、将来的に以下の拡張が必要になる可能性がある:

**1. 中断 (cancellation) 対応:**
現在のコールバックは `void` 戻りだが、`int` 戻り (0 = continue, 1 = abort) のバリアントを追加すると、長文合成の途中キャンセルが可能になる。ただし Dart `NativeCallable.listener` との互換性を壊すため、別関数 (`piper_plus_synthesize_streaming_ex`) として追加するのが妥当。

**2. 非同期モデル:**
現在は同期 (caller のスレッドで callback を呼ぶ) だが、内部スレッドで合成して callback を呼ぶ非同期バリアントがあると、Flutter の UI スレッドブロック問題を回避できる。ただし、スレッド管理の複雑さとプラットフォーム互換性を考慮すると、同期モデルの方がシンプルで安全。非同期は Dart の `Isolate` 側で実現する方が適切。

**3. Iterator を介さない直接実装:**
Iterator 経由でなく `textToAudioStreaming` (C++ 関数) を直接ラップする方法もある。しかし技術調査 1.6 で判明した通り `textToAudioStreaming` にはマルチリンガルのデッドコード問題があり、Iterator (`textToAudio` ベース) の方が正確。

---

## 7. 後続タスクへの連絡事項

### M2-4 (ストリーミング単体テスト) への申し送り

- `TestStreamingNullCallback`: `synthesize_streaming(engine, "hello", NULL, NULL, NULL)` -> `PIPER_PLUS_ERR`
- `TestStreamingNullEngine`: `synthesize_streaming(NULL, "hello", NULL, callback, NULL)` -> `PIPER_PLUS_ERR`
- `TestStreamingEmptyText`: `synthesize_streaming(engine, "", NULL, callback, NULL)` -> `PIPER_PLUS_ERR_TEXT`
- callback の `user_data` 転送テスト: `user_data` に整数ポインタを渡し、callback 内でインクリメントし、関数終了後に値を確認

### M2-5 (統合テスト) への申し送り

- コールバックが 1 回以上呼ばれること (文数 >= 1 のテキスト)
- `samples` が非 NULL で `num_samples > 0` であること
- `sample_rate` がモデルの設定値と一致すること
- 全チャンクのサンプル数合計がワンショットのサンプル数と概ね一致すること (M2-2 と同じ許容基準: 10% 以内)
