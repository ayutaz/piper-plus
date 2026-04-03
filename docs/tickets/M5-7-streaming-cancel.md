# M5-7: ストリーミング中断 API (synthesize_streaming_ex)

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- リアルタイム再生中のキャンセルは UX 必須
> **見積り:** 小
> **依存:** Phase 2 完了 (M2-3)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

現在の `piper_plus_synthesize_streaming()` は `void` 戻りのコールバックを使用しており、利用者が途中で合成を中断する手段がない。中断可能なコールバック (戻り値 `int`: `0`=continue, `非0`=abort) を持つ新関数を追加する。

**現状:** `PiperPlusAudioCallback` は `void` 戻り値。長いテキストの合成中にユーザーがキャンセルボタンを押しても、全文の合成が完了するまで制御が戻らない。

**ゴール:** `piper_plus_synthesize_streaming_ex()` を追加し、コールバックの戻り値で中断を制御可能にする。既存の `piper_plus_synthesize_streaming()` は後方互換のまま維持。

---

## 2. 実装する内容の詳細

### 2.1 ヘッダー追加 (`src/cpp/piper_plus.h`)

```c
/* ===== Cancellable streaming callback (M5-7) ===== */

/** Callback that returns 0 to continue, non-zero to abort. */
typedef int (*PiperPlusAudioCallbackEx)(
    const float *samples,
    int32_t      num_samples,
    int32_t      sample_rate,
    void        *user_data);

/** Synthesize with cancellable streaming.
 *  If callback returns non-zero, synthesis stops and function returns
 *  PIPER_PLUS_OK (not an error -- caller requested abort). */
PIPER_PLUS_API int32_t piper_plus_synthesize_streaming_ex(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    PiperPlusAudioCallbackEx      callback,
    void                         *user_data);
```

### 2.2 C API 実装 (`src/cpp/piper_plus_c_api.cpp`)

既存の `piper_plus_synthesize_streaming()` と同じ構造で、コールバック戻り値チェックを追加:

```cpp
// コールバック呼び出し後
int cbResult = callback(chunk.samples, chunk.num_samples,
                        chunk.sample_rate, user_data);
if (cbResult != 0) {
    // Caller requested abort -- clean up iterator state
    engine->iterState.active = false;
    engine->inProgress.store(false);
    engine->voice.synthesisConfig = engine->iterState.savedConfig;
    return PIPER_PLUS_OK;  // Not an error
}
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | `PiperPlusAudioCallbackEx` typedef + `piper_plus_synthesize_streaming_ex` 宣言 |
| `src/cpp/piper_plus_c_api.cpp` | `piper_plus_synthesize_streaming_ex` 実装 |

**変更不要:** 既存の `piper_plus_synthesize_streaming` は後方互換のまま維持。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | 新関数実装 + テスト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestStreamingExNullEngine` | NULL エンジンで呼び出し | `PIPER_PLUS_ERR` |
| `TestStreamingExNullCallback` | NULL コールバック | `PIPER_PLUS_ERR` |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestStreamingExComplete` | コールバックが常に 0 を返す | 全チャンク受信 + `PIPER_PLUS_OK` |
| `TestStreamingExAbortFirst` | 最初のチャンクで 1 を返す | 1 チャンクのみ + `PIPER_PLUS_OK` |
| `TestStreamingExAbortMiddle` | 2 番目のチャンクで中断 | 2 チャンクのみ + `PIPER_PLUS_OK` |
| `TestStreamingExReuse` | 中断後に再度合成 | 2 回目の合成が正常完了 (BUSY にならない) |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 中断後の `inProgress` 解放漏れ | 高 | 中断パスで必ず `inProgress.store(false)` + `savedConfig` 復元 |
| 中断を `PIPER_PLUS_OK` で返すか別コードで返すか | 低 | `PIPER_PLUS_OK` を返す (中断はエラーではない)。利用者はコールバック内の状態で判断可能 |

### レビュー時の確認項目

1. 中断後にエンジンが再利用可能であること (`inProgress`, `iterState.active`, `savedConfig` の復元)
2. コールバック内で例外が発生した場合のクリーンアップ
3. 既存の `piper_plus_synthesize_streaming` が変更されていないこと

---

## 6. 一から作り直すとしたら

`piper_plus_synthesize_streaming` を最初から `int` 戻り値のコールバックにしておくべきだった。ただし ABI 互換を壊すため、`_ex` サフィックスの新関数で対応する。

---

## 7. 後続タスクへの連絡事項

- 将来の API バージョン 2 では `PiperPlusAudioCallbackEx` をデフォルトにし、`void` 戻り値の旧コールバックは deprecated にすることを検討。
