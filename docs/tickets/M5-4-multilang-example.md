# M5-4: multi_language.c サンプル追加

> **Phase:** 5 -- ドキュメント
> **利用者視点の優先度:** 中 -- 多言語合成の利用開始を容易にする
> **見積り:** 小
> **依存:** M3-6 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

M3-6 で予定されていた 3 つ目のサンプル (多言語合成デモ) を追加し、C API の多言語機能の使い方を利用者に示す。

**現状:** M3-6 で `simple_synth.c` (ワンショット合成) と `streaming.c` (ストリーミング合成) の 2 サンプルが追加済み。多言語モデルを使用した言語切り替えのサンプルが不足している。

**ゴール:** 6 言語 (JA/EN/ZH/ES/FR/PT) のテキストを順に合成し、`language_id` の自動検出と明示指定の両方を示すサンプルを提供する。

---

## 2. 実装する内容の詳細

### 2.1 multi_language.c

```c
/* examples/c-api/multi_language.c
 * 多言語合成デモ — 6 言語のテキストを順に合成し WAV 出力 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include "piper_plus.h"

typedef struct {
    const char *lang;
    int32_t     language_id;
    const char *text;
} LangSample;

static const LangSample samples[] = {
    {"JA",  0, "こんにちは、今日は良い天気ですね。"},
    {"EN",  1, "Hello, how are you today?"},
    {"ZH",  2, "你好，今天天气很好。"},
    {"ES",  3, "Hola, ?como estas hoy?"},
    {"FR",  4, "Bonjour, comment allez-vous?"},
    {"PT",  5, "Ola, como voce esta hoje?"},
};
#define NUM_SAMPLES (sizeof(samples) / sizeof(samples[0]))

/* WAV ヘッダー書き込み (リトルエンディアン安全) */
static void write_wav_header(FILE *fp, int32_t num_samples,
                             int32_t sample_rate) { /* ... */ }

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <model.onnx> [config.json] [dict_dir]\n",
                argv[0]);
        return 1;
    }

    /* 1. エンジン初期化 — memset で全フィールドをゼロ初期化 */
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path  = argv[1];
    config.config_path = argc > 2 ? argv[2] : NULL;  /* NULL = model_path + ".json" */
    config.dict_dir    = argc > 3 ? argv[3] : NULL;

    PiperPlusEngine *engine = piper_plus_create(&config);
    if (!engine) {
        fprintf(stderr, "Engine creation failed: %s\n",
                piper_plus_get_last_error());
        return 1;
    }

    printf("Languages: %d, Speakers: %d, Sample rate: %d Hz\n",
           piper_plus_num_languages(engine),
           piper_plus_num_speakers(engine),
           piper_plus_sample_rate(engine));

    /* 2. 言語ごとに合成 — 方法 A: language_id を明示指定 */
    for (size_t i = 0; i < NUM_SAMPLES; ++i) {
        printf("[%s] \"%s\"\n", samples[i].lang, samples[i].text);

        PiperPlusSynthOptions opts = piper_plus_default_options();
        opts.language_id = samples[i].language_id;

        float  *out_samples    = NULL;
        int32_t out_num_samples = 0;
        int32_t out_sample_rate = 0;

        clock_t start = clock();
        int32_t rc = piper_plus_synthesize(engine, samples[i].text, &opts,
                                           &out_samples, &out_num_samples,
                                           &out_sample_rate);
        clock_t end = clock();

        if (rc != PIPER_PLUS_OK) {
            fprintf(stderr, "  Synthesis error: %s\n",
                    piper_plus_get_last_error());
            continue;
        }

        double elapsed = (double)(end - start) / CLOCKS_PER_SEC;
        double duration = (double)out_num_samples / out_sample_rate;
        printf("  -> %.2fs audio in %.3fs (RTF=%.2f)\n",
               duration, elapsed, elapsed / duration);

        /* WAV 出力 */
        char filename[64];
        snprintf(filename, sizeof(filename), "output_%s.wav",
                 samples[i].lang);
        /* write WAV using out_samples, out_num_samples, out_sample_rate ... */

        piper_plus_free_audio(out_samples);
    }

    /* 3. 方法 B: language_id=-1 (自動検出) のデモ */
    printf("\n--- Auto-detect mode (language_id=-1) ---\n");
    for (size_t i = 0; i < NUM_SAMPLES; ++i) {
        PiperPlusSynthOptions opts = piper_plus_default_options();
        opts.language_id = -1;  /* デフォルト値 = 自動検出 */

        float  *out_samples    = NULL;
        int32_t out_num_samples = 0;
        int32_t out_sample_rate = 0;

        int32_t rc = piper_plus_synthesize(engine, samples[i].text, &opts,
                                           &out_samples, &out_num_samples,
                                           &out_sample_rate);
        if (rc == PIPER_PLUS_OK) {
            printf("[%s] auto-detect -> %.2fs audio\n",
                   samples[i].lang,
                   (double)out_num_samples / out_sample_rate);
            piper_plus_free_audio(out_samples);
        }
    }

    piper_plus_free(engine);
    return 0;
}
```

### 2.2 ビルドシステム更新

**Makefile:**

```makefile
# examples/c-api/Makefile に追加
multi_language: multi_language.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)
```

**CMakeLists.txt:**

```cmake
# examples/c-api/CMakeLists.txt に追加
add_executable(multi_language multi_language.c)
target_link_libraries(multi_language PRIVATE piper_plus_shared)
```

### 2.3 README.md 更新

`examples/c-api/README.md` に `multi_language.c` のビルド・実行手順を追加。

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `examples/c-api/multi_language.c` | 新規作成: 6 言語合成サンプル |
| `examples/c-api/Makefile` | `multi_language` ターゲット追加 |
| `examples/c-api/CMakeLists.txt` | `multi_language` ターゲット追加 |
| `examples/c-api/README.md` | ビルド・実行手順追加 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | サンプルコード作成 + ビルドシステム更新 + README 更新 |

合計 1 名。既存の `simple_synth.c` をベースに拡張するだけ。

---

## 4. 提供範囲とテスト項目

### スコープ

- `multi_language.c`: 6 言語テキストの合成、WAV 出力、合成時間表示
- `language_id` の明示指定と自動検出 (`-1`) の両方を示す
- WAV ヘッダーはエンディアン安全な実装
- ビルドシステム (Makefile, CMakeLists.txt) に統合
- README に使い方を記載

### テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| C99 コンパイル | `gcc -std=c99 -Wall -Wextra -Werror` | 警告なしでコンパイル成功 |
| C11 コンパイル | `gcc -std=c11 -Wall -Wextra -Werror` | 警告なしでコンパイル成功 |
| CMake ビルド | `cmake --build . --target multi_language` | ビルド成功 |
| 実行テスト | モデルを指定して実行 | 6 つの WAV ファイルが生成される |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| テストモデルが多言語非対応 | 中 | サンプルコードは任意のモデルで動作するように設計。多言語モデルがない場合は単一言語のみ合成される旨をコメントで説明 |
| WAV ヘッダーのエンディアン | 低 | `fwrite` ではなくバイト単位で書き込む関数を使用し、ビッグエンディアン環境でも正しく動作 |
| `language_id=-1` の動作確認 | 中 | `PiperPlusSynthOptions.language_id` のデフォルト値は `-1` (自動検出)。`piper_plus_default_options()` で初期化すれば自動検出が有効になる。多言語 G2P が未対応の言語では明示指定にフォールバックする旨をコメントで説明 |

### レビュー時の確認項目

1. C99 互換であること (C++ 機能を使用していないこと)
2. `-Wall -Wextra` で警告なしであること
3. `piper_plus_free_audio()` が全てのパスで呼ばれること (メモリリークなし)
4. エラーハンドリングが全ての API 呼び出しに対して行われていること
5. WAV ヘッダーがリトルエンディアン安全であること
6. 既存の `simple_synth.c` / `streaming.c` と一貫したコードスタイルであること

---

## 6. 一から作り直すとしたら

**インタラクティブなデモアプリケーション。** 現在のサンプルはバッチ処理 (全言語を順に合成) だが、stdin からテキストを受け取り、言語を自動検出して合成する REPL 形式のデモの方が、利用者にとって直感的かもしれない。ただし、C99 の制約内で REPL を実装するのは過剰であり、シンプルなバッチ処理で十分。

---

## 7. 後続タスクへの連絡事項

- **M4-1 (カスタム辞書):** カスタム辞書 API が完成したら、`multi_language.c` に辞書ロードのデモを追加することを検討。
- **M4-3 (G2P 単独 API):** G2P API が公開されたら、合成前に音素列を表示するデモ (`piper_plus_phonemize` の呼び出し) を追加することを検討。
- **README.md の言語:** サンプルの README は英語で記述し、非日本語話者の開発者にもアクセスしやすくする。
