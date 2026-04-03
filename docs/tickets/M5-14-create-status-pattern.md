# M5-14: piper_plus_create を status + out_engine パターンに変更

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 中 -- エラー原因の正確な把握が可能になる
> **見積り:** 中 (API 破壊的変更)
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`piper_plus_create()` の戻り値を `PiperPlusEngine*` から `int32_t` (ステータスコード) に変更し、エンジンは `PiperPlusEngine** out_engine` で返すパターンに移行する。

**現状の問題:** `piper_plus_create()` は失敗時に `NULL` を返すが、失敗原因 (モデルファイル不在、config 不正、ONNX Runtime 初期化失敗) を区別できない。`piper_plus_get_last_error()` で文字列は取得できるが、プログラム的な分岐には不向き。

**ゴール:** `ERR_MODEL` / `ERR_CONFIG` / `ERR_ORT` 等の具体的なステータスコードを返し、FFI 利用側でエラー種別に応じたハンドリング (リトライ、ユーザーへのメッセージ表示) を可能にする。

---

## 2. 実装する内容の詳細

### 2.1 ヘッダー変更 (`src/cpp/piper_plus.h`)

```c
/* 既存 (廃止) */
// PIPER_PLUS_API PiperPlusEngine* piper_plus_create(const PiperPlusConfig *config);

/* 新 API */
PIPER_PLUS_API int32_t piper_plus_create(
    const PiperPlusConfig *config,
    PiperPlusEngine      **out_engine);

/* 新ステータスコード */
#define PIPER_PLUS_ERR_MODEL   (-10)  /* モデルファイルが見つからない/読み込み失敗 */
#define PIPER_PLUS_ERR_CONFIG  (-11)  /* config.json 不正 */
#define PIPER_PLUS_ERR_ORT     (-12)  /* ONNX Runtime 初期化失敗 */
```

### 2.2 C API 実装 (`src/cpp/piper_plus_c_api.cpp`)

- `piper_plus_create` のシグネチャを変更
- try-catch で例外種別を判別し、対応するエラーコードを返却
- 成功時は `*out_engine` にポインタを設定し `PIPER_PLUS_OK` を返却
- `out_engine == NULL` の場合は `PIPER_PLUS_ERR` を即座に返却

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | シグネチャ変更 + ステータスコード追加 |
| `src/cpp/piper_plus_c_api.cpp` | 実装変更 |
| `src/cpp/tests/test_c_api.cpp` | 全テストの `piper_plus_create` 呼び出しを更新 |
| `src/cpp/tests/test_c_api_integration.cpp` | 同上 |
| `examples/c-api/*.c` | サンプルコード更新 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | シグネチャ変更 + 全テスト・サンプル更新 |

合計 1 名。破壊的変更だが影響範囲は限定的 (C API 利用箇所のみ)。

---

## 4. 提供範囲とテスト項目

### スコープ

- `piper_plus_create` のシグネチャ変更
- 新ステータスコード 3 種の追加
- 既存テスト・サンプルの更新

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestCreateOutEngineNull` | `out_engine = NULL` で呼び出し | `PIPER_PLUS_ERR` + クラッシュなし |
| `TestCreateInvalidModel` | 存在しないモデルパス | `PIPER_PLUS_ERR_MODEL` |
| `TestCreateInvalidConfig` | 不正な JSON config | `PIPER_PLUS_ERR_CONFIG` |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestCreateSuccess` | 正常なモデル + config | `PIPER_PLUS_OK` + `*out_engine != NULL` |
| `TestCreateThenSynthesize` | 新 API で作成 -> 合成 | 合成成功 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| ABI 破壊的変更 | 高 | semver メジャーバージョンアップで対応。CHANGELOG に明記 |
| 例外種別の判別精度 | 中 | C++ 例外メッセージのパターンマッチに依存。判別不能な場合は汎用 `PIPER_PLUS_ERR` にフォールバック |

### レビュー時の確認項目

1. 全既存テストが新シグネチャで PASS すること
2. `out_engine` の NULL チェックがあること
3. 各エラーコードのテストがあること

---

## 6. 一から作り直すとしたら

Phase 1 の設計時点でこのパターンを採用すべきだった。sherpa-onnx 等の先行事例は全て `int status + out pointer` パターンを使用しており、C API のデファクトスタンダード。Phase 1 では実装速度を優先して `PiperPlusEngine*` 返却としたが、エラーハンドリングの不便さが明白になった。

---

## 7. 後続タスクへの連絡事項

- **全 Phase 5 チケット:** 新シグネチャを前提として実装すること。
- **examples/ 更新:** M3-6 のサンプルコードも新 API に更新が必要。
- **バインディング生成ツール:** cbindgen / c2ffi 等を使う場合はヘッダー変更後に再生成。
