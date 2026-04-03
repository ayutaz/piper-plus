# M1-3: PiperPlusConfig に `dict_dir` フィールド追加

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 中
> **依存:** M1-5 (ヘッダー)
> **ブロック:** M1-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-3-piperplusconfig-に-dict_dir-フィールド追加)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

共有ライブラリとして利用する場合、`openjtalk_dictionary_manager.c` の `get_exe_relative_dict_path()` 関数はホストアプリ (Flutter / Godot / Python) の実行ファイルパスを返すため、OpenJTalk 辞書の自動検出が機能しない。この問題は技術調査レポート 5.1 で「高リスク」として識別されている。

**ゴール:** `PiperPlusConfig` に `dict_dir` フィールドを追加し、共有ライブラリ利用者が辞書ディレクトリを明示的に指定できるようにする。`dict_dir = NULL` の場合は既存の環境変数 (`OPENJTALK_DICTIONARY_PATH`) / 自動検出にフォールバックする。

---

## 2. 実装する内容の詳細

### 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` (新規、M1-5 で作成) | `PiperPlusConfig` struct に `dict_dir` フィールド追加 |
| `src/cpp/piper_plus_c_api.cpp` (新規、M1-6 で作成) | `piper_plus_create()` で `dict_dir` を処理 |

**注意:** このチケットは M1-5 / M1-6 と一体的に実装される。ここでは設計仕様を定義する。

### 具体的な変更内容

#### 2.1 PiperPlusConfig struct (piper_plus.h)

```c
typedef struct PiperPlusConfig {
    const char *model_path;       /* .onnx file path (UTF-8) */
    const char *config_path;      /* .json config path (UTF-8, NULL = model_path + ".json") */
    const char *provider;         /* "cpu", "cuda", "coreml", "directml" (NULL = "cpu") */
    int32_t     num_threads;      /* ONNX Runtime intra-op threads (0 = auto) */
    int32_t     gpu_device_id;    /* GPU device index (provider != "cpu") */
    const char *dict_dir;         /* OpenJTalk dictionary directory (UTF-8, NULL = auto-detect).
                                   * Recommended to set explicitly when using as shared library,
                                   * as auto-detection relies on executable path which may not
                                   * point to the library's location. */
    int32_t     _reserved[7];     /* ABI padding (reduced from 8 to 7 due to dict_dir addition) */
} PiperPlusConfig;
```

**ABI 設計の注意:**
- `dict_dir` (ポインタ) を追加したため、`_reserved` は 8 から 7 に減る
- 64-bit システムでポインタは 8 バイト。`_reserved[7]` = 28 バイト。合計パディングは依然十分
- `memset(&config, 0, sizeof(config))` で初期化した場合、`dict_dir = NULL` となり自動検出にフォールバック

#### 2.2 piper_plus_create() での処理 (piper_plus_c_api.cpp)

```cpp
PiperPlusEngine* piper_plus_create(const PiperPlusConfig* config) {
    PIPER_PLUS_TRY

    if (!config || !config->model_path) {
        g_last_error = "config and config->model_path must not be NULL";
        return nullptr;
    }

    // Set dictionary directory via environment variable if specified.
    // This must happen BEFORE loadVoice(), which triggers OpenJTalk initialization.
    if (config->dict_dir && config->dict_dir[0] != '\0') {
#ifdef _WIN32
        _putenv_s("OPENJTALK_DICTIONARY_PATH", config->dict_dir);
#else
        setenv("OPENJTALK_DICTIONARY_PATH", config->dict_dir, 1);  // overwrite=1
#endif
    }

    // ... rest of create logic (config_path auto-generation, loadVoice, etc.)

    PIPER_PLUS_CATCH(nullptr)
}
```

#### 2.3 辞書パス検索の優先順位 (既存 openjtalk_dictionary_manager.c の動作)

`get_openjtalk_dictionary_path()` の既存の検索順序:

1. 環境変数 `OPENJTALK_DICTIONARY_PATH`
2. 実行ファイルからの相対パス (`../share/open_jtalk/dic`)
3. システムパス (`/usr/share/open_jtalk/dic` 等)
4. ローカルデータディレクトリ (自動ダウンロード先)

`dict_dir` を `setenv` で設定することで、優先順位 1 を経由して既存のロジックに統合される。`openjtalk_dictionary_manager.c` の変更は不要。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | M1-5 / M1-6 と同一担当者がヘッダーと実装に反映 |

合計: 1 名。M1-5 (ヘッダー) と M1-6 (実装) に含めて実装する。

---

## 4. 提供範囲とテスト項目

### スコープ

- `PiperPlusConfig` の `dict_dir` フィールド定義
- `piper_plus_create()` で `dict_dir` を環境変数に設定するロジック
- ヘッダーのドキュメントコメント (共有ライブラリ利用時の推奨事項)

### スコープ外

- `dladdr()` / `GetModuleHandleEx()` によるライブラリパスからの自動検出 (M4-6)
- OpenJTalk 辞書の自動ダウンロード機能の変更

### テスト項目

| テスト | 方法 | 期待結果 |
|--------|------|----------|
| `dict_dir` = NULL で create | M1-7 で実装 | 既存の自動検出にフォールバック (エラーにならない) |
| `dict_dir` = 存在しないパスで create | M1-7 で実装 | create は成功するが、合成時に辞書エラーになる可能性あり (既存動作と同等) |
| `dict_dir` = 有効なパスで create | M2-5 統合テストで実装 | 辞書が正しくロードされる |
| `memset(&config, 0, sizeof(config))` での初期化 | M1-7 で実装 | `dict_dir = NULL` となり、自動検出にフォールバック |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `setenv` はプロセスグローバルな副作用を持つ | 中 | 複数エンジンインスタンスが異なる `dict_dir` を指定した場合、最後に create されたインスタンスの設定が有効になる。ヘッダーのドキュメントに「プロセス内で統一すること」を明記 |
| `setenv` のスレッドセーフティ | 低 | POSIX では `setenv` は MT-Unsafe。ただし `piper_plus_create()` は「初回は単一スレッドから呼び出す」という既存制約内で呼ばれる (技術調査 5.3) |
| `_reserved` フィールド数の減少 (8 -> 7) | 低 | `dict_dir` が 1 ポインタ (8 バイト) を占有し、`_reserved[7]` で 28 バイトのパディングが残る。将来のフィールド追加に十分な余裕 |

### レビュー項目

- [ ] `PiperPlusConfig.dict_dir` のドキュメントコメントに共有ライブラリでの推奨事項が記載されているか
- [ ] `setenv` がプラットフォーム別 (`_putenv_s` / `setenv`) で実装されているか
- [ ] `dict_dir` が空文字列 (`""`) の場合に `setenv` が呼ばれないか (NULL と空文字列の両方をチェック)
- [ ] `_reserved` の要素数が `dict_dir` 追加分だけ減っているか
- [ ] `loadVoice()` より前に `setenv` が呼ばれているか

---

## 6. 一から作り直すとしたら

`setenv` によるプロセスグローバルな副作用は理想的ではない。ゼロから設計するなら以下の 2 つのアプローチを検討する:

### 案 A: `loadVoice()` に辞書パスパラメータを追加

```cpp
void loadVoice(PiperConfig&, string modelPath, string configPath,
               Voice&, optional<SpeakerId>&, bool useCuda,
               int gpuDeviceId = 0,
               const char* dictDir = nullptr);  // 新パラメータ
```

メリット: プロセスグローバルな副作用なし、インスタンスごとに異なる辞書を指定可能。
デメリット: C++ API の変更が必要で、既存の呼び出し元 (main.cpp, test.cpp) に影響。

### 案 B: `dladdr()` によるライブラリパスからの自動検出 (M4-6)

`dict_dir = NULL` 時にライブラリ自身のパスから `../share/open_jtalk/dic` を検索する。`setenv` 不要。
デメリット: プラットフォーム依存コードが増える。

Phase 1 では `setenv` 方式を採用し、M4-6 で `dladdr` 方式に移行するのが現実的なロードマップ。

---

## 7. 後続タスクへの連絡事項

- **M1-5 (ヘッダー):** `PiperPlusConfig` struct に `dict_dir` フィールドを含めること。`_reserved` を 7 に減らすこと。
- **M1-6 (実装):** `piper_plus_create()` で `dict_dir` を `setenv` する処理を `loadVoice()` 呼び出しの**前**に配置すること。
- **M1-7 (テスト):** `dict_dir = NULL` と `dict_dir = "/nonexistent"` のテストケースを含めること。
- **M4-6 (将来):** `dladdr()` / `GetModuleHandleEx()` によるライブラリパス自動検出で `setenv` 方式を置き換える際、後方互換性のために `dict_dir` が明示指定されている場合はそちらを優先するロジックを維持すること。
