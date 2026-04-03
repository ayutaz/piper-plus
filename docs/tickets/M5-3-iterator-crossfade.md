# M5-3: Iterator crossfade 対応

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 高 -- ストリーミング利用時の音質に直結
> **見積り:** 中
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

Iterator パターン (`synth_start` / `synth_next`) の文境界でクリック音が発生する可能性を、crossfade 処理により解消する。

**現状:** Iterator パターンは文ごとに `textToAudio()` を呼び出し、各チャンクを逐次返す。文境界ではチャンク末尾と次チャンク先頭のサンプル値が不連続になり、クリック音 (pop noise) が発生する可能性がある。ワンショット合成 (`piper_plus_synthesize`) では既存の `crossfadeAudioChunks()` が適用されるが、Iterator パターンでは未適用。

**ゴール:** `synth_next` でチャンク間の crossfade を適用し、ワンショット合成と同等の音質をストリーミングでも実現する。

---

## 2. 実装する内容の詳細

### 2.1 IteratorState 拡張

```cpp
struct IteratorState {
    // 既存フィールド
    std::vector<std::string> sentences;
    size_t currentIndex;
    // ...

    // Phase 5: crossfade 用
    static constexpr size_t CROSSFADE_SAMPLES = 220; // 10ms @ 22050Hz
    std::vector<int16_t> prevTail; // 前チャンクの末尾サンプル
};
```

### 2.2 synth_next での crossfade 処理

```cpp
// synth_next 内部 (疑似コード)
// 1. 現在の文を合成
std::vector<int16_t> currentChunk;
textToAudio(config, voice, sentences[currentIndex], currentChunk, ...);

// 2. 前チャンクの末尾と現在のチャンク先頭を crossfade
if (!state->prevTail.empty() && currentChunk.size() >= CROSSFADE_SAMPLES) {
    for (size_t i = 0; i < CROSSFADE_SAMPLES; ++i) {
        float alpha = static_cast<float>(i) / CROSSFADE_SAMPLES;
        currentChunk[i] = static_cast<int16_t>(
            state->prevTail[i] * (1.0f - alpha) +
            currentChunk[i] * alpha
        );
    }
}

// 3. 現在のチャンク末尾を保存 (次回の crossfade 用)
if (currentChunk.size() >= CROSSFADE_SAMPLES) {
    state->prevTail.assign(
        currentChunk.end() - CROSSFADE_SAMPLES,
        currentChunk.end());
    // crossfade 適用済み末尾は次チャンクに委譲するため、トリミング
    currentChunk.resize(currentChunk.size() - CROSSFADE_SAMPLES);
} else {
    state->prevTail.clear();
}

// 4. 最終チャンクの場合は prevTail も出力に含める
if (isLastChunk) {
    currentChunk.insert(currentChunk.end(),
                        state->prevTail.begin(),
                        state->prevTail.end());
    state->prevTail.clear();
}
```

### 2.3 crossfade パラメータ

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| crossfade サンプル数 | 220 | 10ms @ 22050Hz。既存の `crossfadeAudioChunks` と同等 |
| crossfade カーブ | 線形 (linear) | 既存実装と同一。コサインカーブは将来検討 |

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus_c_api.cpp` | `IteratorState` に `prevTail` フィールド追加、`synth_next` に crossfade ロジック追加 |
| `src/cpp/tests/test_c_api_integration.cpp` | crossfade 前後の波形比較テスト追加 |

**変更不要:** `piper_plus.h` (公開インターフェースに変更なし)、`piper.cpp`。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | IteratorState 拡張 + crossfade ロジック + テスト |

合計 1 名。既存の `crossfadeAudioChunks` のロジックを Iterator に適用する作業。

---

## 4. 提供範囲とテスト項目

### スコープ

- `IteratorState` に前チャンクの末尾サンプルバッファを追加
- `synth_next` でチャンク先頭と前チャンク末尾を crossfade
- crossfade サンプル数: 220 (10ms @ 22050Hz)
- 最終チャンクで残りの `prevTail` を出力に含める

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestCrossfadeLinear` | 既知の 2 チャンクで crossfade を適用 | 期待される線形補間値と一致 |
| `TestCrossfadeShortChunk` | `CROSSFADE_SAMPLES` 未満のチャンク | crossfade をスキップし、元のデータを維持 |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestIteratorCrossfade` | 2 文テキストを Iterator で合成 | 文境界付近のサンプルが滑らかに遷移 (不連続なし) |
| `TestIteratorVsOneShotParity` | 同一テキストを Iterator とワンショットで合成 | 総サンプル数が近似 (crossfade 分の差異のみ) |
| `TestSingleSentenceNoCrossfade` | 1 文テキストを Iterator で合成 | crossfade 不要、ワンショットと同一結果 |
| `TestCallbackCrossfade` | 2 文テキストを Callback で合成 | Callback 経由でも crossfade が適用される |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| crossfade による遅延 | 低 | `CROSSFADE_SAMPLES` (220) は極めて小さく、処理時間への影響は無視できる |
| 最終チャンクの出力タイミング | 中 | `prevTail` の flush を最終チャンクで行うため、最後のチャンクが `CROSSFADE_SAMPLES` 分だけ長くなる。呼び出し側で割り当てるバッファサイズに注意が必要だが、C API は内部でバッファを管理するため問題なし |
| Callback パターンとの整合性 | 中 | Callback パターンは Iterator のラッパーなので、Iterator に crossfade を実装すれば Callback でも自動的に適用される。ただし、Callback のバッファサイズが変わる点をドキュメントに記載 |
| 無音区間 (`sentence_silence_sec`) との干渉 | 低 | `sentence_silence_sec` はチャンク間に無音を挿入する設定。crossfade は無音挿入前のチャンク末尾に適用するため干渉しない |

### レビュー時の確認項目

1. `prevTail` の初期化とクリアが正しいこと (初回チャンクでは crossfade をスキップ)
2. 最終チャンクで `prevTail` が確実に出力に含まれること (サンプル欠落なし)
3. `CROSSFADE_SAMPLES` が既存の `crossfadeAudioChunks` と同一値であること
4. `CROSSFADE_SAMPLES` 未満の短いチャンクが正しく処理されること
5. Callback パターン経由でも crossfade が適用されることのテスト

---

## 6. 一から作り直すとしたら

**crossfade を `textToAudio` の内部に統合する設計。** 現在の設計では crossfade がワンショット (`crossfadeAudioChunks`) と Iterator (`prevTail` + `synth_next`) で別々に実装される。`textToAudio` が文ごとの合成結果を返す際に crossfade 情報 (末尾サンプル) を一緒に管理するクラスを提供すれば、ワンショットと Iterator で同一のロジックを共有できる。ただし、`piper.cpp` の大幅なリファクタリングが必要であり、Phase 5 の範囲を超える。

**M2-2 で既に指摘済み:** マイルストーン M2-2 の懸念事項に「crossfade 非対応の音質差リスク」が記載されていた。本チケットがその対応。

---

## 7. 後続タスクへの連絡事項

- **M5-1 (RAII ガード):** M5-1 が先に完了している場合、`IteratorState` の拡張は RAII パターンに従うこと (`prevTail` は `IteratorState` のデストラクタで自動クリーンアップされるため追加対応不要)。
- **将来の crossfade カーブ改善:** 線形 crossfade はシンプルだが、コサインカーブ (`0.5 * (1 - cos(pi * alpha))`) の方が聴感上滑らかになる場合がある。将来の品質改善として検討可能。
- **`sentence_silence_sec` との組み合わせ:** crossfade 適用後に無音を挿入する順序を維持すること。逆順にすると無音部分が crossfade で消失する。
