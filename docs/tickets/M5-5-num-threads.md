# M5-5: num_threads ORT SessionOptions 接続

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- モバイル・組み込みでスレッド数制御が必要
> **見積り:** 小
> **依存:** Phase 1 完了 (M1-6)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

`PiperPlusConfig.num_threads` は既にヘッダーで宣言済みだが、`piper_plus_create()` 内で ONNX Runtime の `SessionOptions` に渡されていない。この値を `Ort::SessionOptions::SetIntraOpNumThreads()` に接続し、利用者がスレッド数を制御できるようにする。

**現状:** `piper_plus_create()` は `config->num_threads` を無視して `loadVoice()` を呼んでいる。`loadVoice()` 内部では ORT デフォルト (全コア使用) が適用される。

**ゴール:** `num_threads > 0` の場合、`Ort::SessionOptions::SetIntraOpNumThreads(num_threads)` が設定され、`num_threads == 0` の場合は ORT デフォルト (auto) が維持される。

---

## 2. 実装する内容の詳細

### 2.1 piper.hpp / piper.cpp の変更

`loadVoice` に `numThreads` パラメータを追加:

```cpp
// piper.hpp
void loadVoice(PiperConfig &config, std::string modelPath,
               std::string modelConfigPath, Voice &voice,
               std::optional<SpeakerId> &speakerId,
               bool useCuda = false, int gpuDeviceId = 0,
               int numThreads = 0);
```

`piper.cpp` の `loadModel()` / `loadVoice()` 内で `SessionOptions` 設定:

```cpp
if (numThreads > 0) {
    options.SetIntraOpNumThreads(numThreads);
}
```

### 2.2 piper_plus_c_api.cpp の変更

`piper_plus_create()` 内で `num_threads` を `loadVoice()` に渡す:

```cpp
piper::loadVoice(engine->config, modelPath, configPath,
                 engine->voice, speakerId, useCuda, gpuDeviceId,
                 config->num_threads);
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper.hpp` | `loadVoice` に `numThreads` パラメータ追加 |
| `src/cpp/piper.cpp` | `loadModel` / `loadVoice` で `SessionOptions` 設定 |
| `src/cpp/piper_plus_c_api.cpp` | `piper_plus_create` から `num_threads` を渡す |

**変更不要:** `piper_plus.h` (既に `num_threads` フィールドが宣言済み)

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | パラメータ接続 + テスト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestNumThreadsZero` | `num_threads=0` でエンジン作成 | ORT デフォルト動作 (クラッシュなし) |
| `TestNumThreadsNegative` | `num_threads=-1` でエンジン作成 | エラーまたは 0 にクランプ |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestNumThreadsOne` | `num_threads=1` で合成 | 合成成功 (シングルスレッド) |
| `TestNumThreadsFour` | `num_threads=4` で合成 | 合成成功 |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `loadVoice` のシグネチャ変更が既存呼び出し元に影響 | 低 | デフォルト引数 `numThreads = 0` で後方互換 |
| ORT の `SetIntraOpNumThreads` に負値を渡すと未定義動作 | 低 | 負値は 0 にクランプ |

### レビュー時の確認項目

1. `loadVoice` の既存呼び出し元 (CLI, テスト) がデフォルト引数で動作すること
2. `num_threads=1` でシングルスレッド動作が確認できること
3. `num_threads=0` で従来と同じ動作であること

---

## 6. 一から作り直すとしたら

`loadVoice` に個別パラメータを追加し続けるとシグネチャが肥大化する。`LoadVoiceOptions` 構造体を導入して全オプションをまとめる設計が望ましい。ただし既存 CLI への影響が大きいため、Phase 5 の範囲ではデフォルト引数追加に留める。

---

## 7. 後続タスクへの連絡事項

- **M5-6 (Provider 対応):** `loadVoice` に `numThreads` と同様に `provider` 文字列を渡す変更が必要。M5-5 と M5-6 を同時に実装する場合は `LoadVoiceOptions` 構造体の導入を検討。
