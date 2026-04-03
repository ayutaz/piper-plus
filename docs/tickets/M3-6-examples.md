# M3-6: 使用例ドキュメント

> **Phase:** 3 — 配布
> **見積り:** 中
> **依存:** M3-2, M3-3
> **ブロック:** なし (Phase 3 最終チケット)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m3-6-使用例ドキュメント)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

C API 共有ライブラリの利用者が 5 分以内に動作確認できるサンプルコードとビルド手順を提供する。対象は C 開発者、Flutter/Dart 開発者、Godot GDExtension 開発者。

**ゴール:**
- `examples/c-api/` ディレクトリに 3 つの実行可能な C サンプルプログラムを配置
- 各サンプルが `pkg-config` (Makefile) と `find_package` (CMake) の両方でビルド可能
- README にダウンロードからビルド・実行までの手順を記載

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 内容 |
|---------|------|
| `examples/c-api/basic.c` (新規) | ワンショット合成 + WAV 保存 |
| `examples/c-api/streaming.c` (新規) | ストリーミングコールバック合成 |
| `examples/c-api/multi_language.c` (新規) | 多言語合成デモ |
| `examples/c-api/Makefile` (新規) | pkg-config ベースのビルド |
| `examples/c-api/CMakeLists.txt` (新規) | find_package ベースのビルド |
| `examples/c-api/README.md` (新規) | 手順書 |

### 2.2 basic.c -- ワンショット合成 + WAV 保存

```c
/*
 * basic.c -- piper-plus C API basic example
 *
 * Usage:
 *   ./basic <model.onnx> <dict_dir> "Hello, world!" output.wav
 */
#include <piper_plus.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Minimal WAV header writer */
static void write_wav(const char *path, const float *samples,
                      int32_t num_samples, int32_t sample_rate) {
    FILE *f = fopen(path, "wb");
    if (!f) { perror("fopen"); return; }

    int32_t data_size = num_samples * 2;  /* 16-bit PCM */
    int32_t file_size = 36 + data_size;

    /* RIFF header */
    fwrite("RIFF", 1, 4, f);
    fwrite(&file_size, 4, 1, f);
    fwrite("WAVE", 1, 4, f);

    /* fmt chunk */
    fwrite("fmt ", 1, 4, f);
    int32_t fmt_size = 16;
    int16_t audio_format = 1;  /* PCM */
    int16_t num_channels = 1;
    int32_t byte_rate = sample_rate * 2;
    int16_t block_align = 2;
    int16_t bits_per_sample = 16;
    fwrite(&fmt_size, 4, 1, f);
    fwrite(&audio_format, 2, 1, f);
    fwrite(&num_channels, 2, 1, f);
    fwrite(&sample_rate, 4, 1, f);
    fwrite(&byte_rate, 4, 1, f);
    fwrite(&block_align, 2, 1, f);
    fwrite(&bits_per_sample, 2, 1, f);

    /* data chunk */
    fwrite("data", 1, 4, f);
    fwrite(&data_size, 4, 1, f);
    for (int32_t i = 0; i < num_samples; i++) {
        float s = samples[i];
        if (s > 1.0f) s = 1.0f;
        if (s < -1.0f) s = -1.0f;
        int16_t pcm = (int16_t)(s * 32767.0f);
        fwrite(&pcm, 2, 1, f);
    }

    fclose(f);
    printf("Wrote %s (%d samples, %d Hz)\n", path, num_samples, sample_rate);
}

int main(int argc, char *argv[]) {
    if (argc < 5) {
        fprintf(stderr,
            "Usage: %s <model.onnx> <dict_dir> \"text\" <output.wav>\n",
            argv[0]);
        return 1;
    }

    const char *model_path = argv[1];
    const char *dict_dir   = argv[2];
    const char *text       = argv[3];
    const char *output_wav = argv[4];

    printf("piper-plus version: %s (API %d)\n",
           piper_plus_version(), piper_plus_api_version());

    /* Create engine */
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = model_path;
    config.dict_dir   = dict_dir;

    PiperPlusEngine *engine = piper_plus_create(&config);
    if (!engine) {
        fprintf(stderr, "Error: %s\n", piper_plus_get_last_error());
        return 1;
    }

    printf("Sample rate: %d Hz\n", piper_plus_sample_rate(engine));
    printf("Speakers: %d\n", piper_plus_num_speakers(engine));
    printf("Languages: %d\n", piper_plus_num_languages(engine));

    /* Synthesize */
    PiperPlusSynthOptions opts = piper_plus_default_options();
    float *samples = NULL;
    int32_t num_samples = 0, sample_rate = 0;

    int32_t status = piper_plus_synthesize(
        engine, text, &opts, &samples, &num_samples, &sample_rate);

    if (status != PIPER_PLUS_OK) {
        fprintf(stderr, "Synthesis failed: %s\n",
                piper_plus_get_last_error());
        piper_plus_free(engine);
        return 1;
    }

    /* Write WAV */
    write_wav(output_wav, samples, num_samples, sample_rate);

    /* Cleanup */
    piper_plus_free_audio(samples);
    piper_plus_free(engine);

    return 0;
}
```

### 2.3 streaming.c -- ストリーミングコールバック合成

```c
/*
 * streaming.c -- piper-plus streaming callback example
 *
 * Demonstrates chunk-by-chunk audio synthesis using the callback API.
 * Each chunk is printed to stdout as it arrives.
 */
#include <piper_plus.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    int32_t total_samples;
    int32_t chunk_count;
} StreamContext;

static void on_audio_chunk(const float *samples, int32_t num_samples,
                           int32_t sample_rate, void *user_data) {
    StreamContext *ctx = (StreamContext *)user_data;
    ctx->total_samples += num_samples;
    ctx->chunk_count++;
    printf("  Chunk %d: %d samples (%d Hz)\n",
           ctx->chunk_count, num_samples, sample_rate);
}

int main(int argc, char *argv[]) {
    if (argc < 4) {
        fprintf(stderr,
            "Usage: %s <model.onnx> <dict_dir> \"text\"\n", argv[0]);
        return 1;
    }

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = argv[1];
    config.dict_dir   = argv[2];

    PiperPlusEngine *engine = piper_plus_create(&config);
    if (!engine) {
        fprintf(stderr, "Error: %s\n", piper_plus_get_last_error());
        return 1;
    }

    PiperPlusSynthOptions opts = piper_plus_default_options();
    StreamContext ctx = {0, 0};

    printf("Streaming synthesis: \"%s\"\n", argv[3]);
    int32_t status = piper_plus_synthesize_streaming(
        engine, argv[3], &opts, on_audio_chunk, &ctx);

    if (status != PIPER_PLUS_OK) {
        fprintf(stderr, "Streaming failed: %s\n",
                piper_plus_get_last_error());
        piper_plus_free(engine);
        return 1;
    }

    printf("Done: %d chunks, %d total samples\n",
           ctx.chunk_count, ctx.total_samples);

    piper_plus_free(engine);
    return 0;
}
```

### 2.4 multi_language.c -- 多言語合成デモ

```c
/*
 * multi_language.c -- piper-plus multi-language synthesis example
 *
 * Synthesizes text in multiple languages using a multilingual model.
 * Language detection is automatic (language_id = -1).
 */
#include <piper_plus.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc < 3) {
        fprintf(stderr,
            "Usage: %s <multilingual_model.onnx> <dict_dir>\n", argv[0]);
        return 1;
    }

    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = argv[1];
    config.dict_dir   = argv[2];

    PiperPlusEngine *engine = piper_plus_create(&config);
    if (!engine) {
        fprintf(stderr, "Error: %s\n", piper_plus_get_last_error());
        return 1;
    }

    printf("Languages: %d\n", piper_plus_num_languages(engine));

    /* Test texts in multiple languages */
    const char *texts[] = {
        "Hello, how are you today?",                /* English */
        "\xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf\xe3\x80\x82",  /* Japanese: こんにちは。 */
        "\xe4\xbd\xa0\xe5\xa5\xbd\xef\xbc\x8c\xe4\xbb\x8a\xe5\xa4\xa9\xe5\xa4\xa9\xe6\xb0\x94\xe5\xbe\x88\xe5\xa5\xbd\xe3\x80\x82",  /* Chinese: 你好，今天天气很好。 */
        "Hola, como estas hoy?",                     /* Spanish */
        "Bonjour, comment allez-vous?",              /* French */
    };
    const char *lang_names[] = {
        "English", "Japanese", "Chinese", "Spanish", "French"
    };
    int num_texts = sizeof(texts) / sizeof(texts[0]);

    for (int i = 0; i < num_texts; i++) {
        PiperPlusSynthOptions opts = piper_plus_default_options();
        opts.language_id = -1;  /* Auto-detect language */

        float *samples = NULL;
        int32_t num_samples = 0, sample_rate = 0;

        int32_t status = piper_plus_synthesize(
            engine, texts[i], &opts, &samples, &num_samples, &sample_rate);

        if (status == PIPER_PLUS_OK) {
            float duration = (float)num_samples / (float)sample_rate;
            printf("[%s] %d samples (%.2f sec)\n",
                   lang_names[i], num_samples, duration);
            piper_plus_free_audio(samples);
        } else {
            printf("[%s] Failed: %s\n",
                   lang_names[i], piper_plus_get_last_error());
        }
    }

    piper_plus_free(engine);
    return 0;
}
```

### 2.5 Makefile (pkg-config ベース)

```makefile
# examples/c-api/Makefile
# Build examples using pkg-config
#
# Prerequisites:
#   export PKG_CONFIG_PATH=/path/to/piper-plus-install/lib/pkgconfig
#
# Usage:
#   make           # Build all examples
#   make basic     # Build single example
#   make clean     # Clean build artifacts

CC      ?= gcc
CFLAGS  ?= -Wall -Wextra -std=c99
LDFLAGS ?=

PKG_CFLAGS  := $(shell pkg-config --cflags piper_plus 2>/dev/null)
PKG_LIBS    := $(shell pkg-config --libs piper_plus 2>/dev/null)

ifeq ($(PKG_CFLAGS),)
  $(error pkg-config cannot find piper_plus. Set PKG_CONFIG_PATH.)
endif

TARGETS := basic streaming multi_language

.PHONY: all clean

all: $(TARGETS)

basic: basic.c
	$(CC) $(CFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS) $(LDFLAGS)

streaming: streaming.c
	$(CC) $(CFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS) $(LDFLAGS)

multi_language: multi_language.c
	$(CC) $(CFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS) $(LDFLAGS)

clean:
	rm -f $(TARGETS)
```

### 2.6 CMakeLists.txt (find_package ベース)

```cmake
# examples/c-api/CMakeLists.txt
# Build examples using find_package(PiperPlus)
#
# Prerequisites:
#   cmake -B build -DCMAKE_PREFIX_PATH=/path/to/piper-plus-install
#
# Usage:
#   cmake -B build -DCMAKE_PREFIX_PATH=/path/to/piper-plus-install
#   cmake --build build

cmake_minimum_required(VERSION 3.15)
project(piper_plus_examples C)

find_package(PiperPlus REQUIRED)

# Print discovered paths (useful for debugging)
message(STATUS "PiperPlus version: ${PiperPlus_VERSION}")
message(STATUS "OpenJTalk dict: ${PiperPlus_DICT_DIR}")
message(STATUS "G2P dicts: ${PiperPlus_G2P_DICT_DIR}")

# basic: one-shot synthesis + WAV output
add_executable(basic basic.c)
target_link_libraries(basic PRIVATE PiperPlus::piper_plus)

# streaming: callback-based streaming synthesis
add_executable(streaming streaming.c)
target_link_libraries(streaming PRIVATE PiperPlus::piper_plus)

# multi_language: multilingual synthesis demo
add_executable(multi_language multi_language.c)
target_link_libraries(multi_language PRIVATE PiperPlus::piper_plus)
```

### 2.7 README.md

```markdown
# piper-plus C API Examples

Working examples for the piper-plus C API shared library.

## Prerequisites

Download the pre-built shared library from
[GitHub Releases](https://github.com/ayutaz/piper-plus/releases):

    # Linux x86_64
    wget https://github.com/ayutaz/piper-plus/releases/download/v1.10.0/piper-plus-shared-linux-x64.tar.gz
    mkdir -p piper-plus && tar -xzf piper-plus-shared-linux-x64.tar.gz -C piper-plus

    # macOS ARM64
    wget https://github.com/ayutaz/piper-plus/releases/download/v1.10.0/piper-plus-shared-macos-arm64.tar.gz
    mkdir -p piper-plus && tar -xzf piper-plus-shared-macos-arm64.tar.gz -C piper-plus

You also need a model file (.onnx + .onnx.json). Download from
[HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan):

    # Example: tsukuyomi-chan multilingual model
    wget https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-6lang-v2.onnx
    wget https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-6lang-v2.onnx.json

## Build with Makefile (pkg-config)

    export PKG_CONFIG_PATH=/path/to/piper-plus/lib/pkgconfig
    make

## Build with CMake (find_package)

    cmake -B build -DCMAKE_PREFIX_PATH=/path/to/piper-plus
    cmake --build build

## Run

    # Basic synthesis (outputs WAV file)
    LD_LIBRARY_PATH=/path/to/piper-plus/lib \
      ./basic model.onnx /path/to/piper-plus/share/open_jtalk/dic \
      "Hello, world!" output.wav

    # Streaming synthesis
    LD_LIBRARY_PATH=/path/to/piper-plus/lib \
      ./streaming model.onnx /path/to/piper-plus/share/open_jtalk/dic \
      "This is a streaming test."

    # Multi-language synthesis
    LD_LIBRARY_PATH=/path/to/piper-plus/lib \
      ./multi_language model.onnx /path/to/piper-plus/share/open_jtalk/dic

On macOS, use `DYLD_LIBRARY_PATH` instead of `LD_LIBRARY_PATH`,
or install the library to a system path.

## API Reference

See [piper_plus.h](../../src/cpp/piper_plus.h) for the complete API
documentation.
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| C 開発者 | 1 | サンプルコード作成 (basic.c, streaming.c, multi_language.c) |
| テクニカルライター | 1 | README.md 作成、ビルド手順の検証 |

---

## 4. 提供範囲とテスト項目

### 4.1 ビルドテスト

| テスト | 検証方法 |
|--------|---------|
| Makefile ビルド | `PKG_CONFIG_PATH=... make` が Linux/macOS で成功 |
| CMake ビルド | `cmake -B build -DCMAKE_PREFIX_PATH=...` が 3 プラットフォームで成功 |
| C99 互換 | `gcc -std=c99 -Wall -Wextra` で警告なし |
| C++ 互換 | `g++ -std=c++17` でもコンパイル可能 (ヘッダーが C/C++ 両対応) |

### 4.2 実行テスト

| テスト | モデル依存 | 内容 |
|--------|----------|------|
| basic: バージョン出力 | 不要 | `piper_plus_version()` が非 NULL |
| basic: エンジン作成失敗 | 不要 | 存在しないモデルパスでエラーメッセージ表示 |
| basic: WAV 生成 | 必要 | 有効なモデルで WAV ファイルが生成される |
| streaming: チャンク受信 | 必要 | コールバックが 1 回以上呼ばれる |
| multi_language: 全言語合成 | 必要 | 5 言語それぞれでサンプル数 > 0 |

### 4.3 CI テスト (M3-5 の一部として)

```bash
# examples ディレクトリからの CMake ビルドテスト (モデル不要)
cmake -B /tmp/ex-build \
  -S examples/c-api \
  -DCMAKE_PREFIX_PATH=/tmp/piper-plus-install
cmake --build /tmp/ex-build

# バージョン出力テスト (モデル不要)
LD_LIBRARY_PATH=/tmp/piper-plus-install/lib \
  /tmp/ex-build/basic nonexistent.onnx /tmp/dict "test" /dev/null || true
# -> "Error: ..." が出力されることを確認 (exit code 1)
```

---

## 5. 懸念事項とレビュー項目

| 懸念 | 詳細 | 対策 |
|------|------|------|
| WAV ライター | `basic.c` の WAV ライターが簡易実装。エンディアンがリトルエンディアン前提 | x86_64 / ARM64 はリトルエンディアンなので問題なし。ヘッダーコメントに「little-endian only」と明記 |
| LD_LIBRARY_PATH の必要性 | RPATH (M3-4) が正しく設定されていれば `LD_LIBRARY_PATH` は不要だが、examples は install 先とは別の場所から実行するため必要 | README に `LD_LIBRARY_PATH` の設定方法を明記。「install 先で実行する場合は不要」の注記を追加 |
| モデルの入手方法 | examples の実行にはモデルファイルが必要 | README に HuggingFace からのダウンロード手順を記載 |
| `dict_dir` の指定が冗長 | 毎回辞書パスを指定するのは面倒 | Phase 4 (M4-6) の `dladdr` 辞書自動検出で改善予定。examples では明示指定で確実に動作する方法を示す |
| 多言語テキストの文字列リテラル | `multi_language.c` の日本語・中国語テキストがエスケープシーケンスになる | UTF-8 ソースファイルとして保存し、`\xe3\x81\x93...` のエスケープは可読性のために残す。コメントに元テキストを記載 |

**レビュー項目:**
- [ ] 3 つのサンプルが `gcc -std=c99 -Wall -Wextra` で警告なしコンパイル
- [ ] Makefile と CMakeLists.txt の両方でビルド成功
- [ ] README の手順が正確で、初見の開発者が再現可能
- [ ] ヘッダーの Doxygen コメントと使用例が整合

---

## 6. 一から作り直すとしたら

1. **サンプルコードに WAV ライターを含めず、raw PCM 出力にする。** WAV ヘッダーの実装は本質ではなく、バグの温床になる。`stdout` に raw float32 PCM を出力し、`ffplay -f f32le -ar 22050 -ac 1 -` 等の外部ツールで再生する方式がシンプル。ただし「5 分で動作確認」のゴールからは遠ざかるため、WAV ライターを含める判断は妥当。

2. **Dart FFI / Godot GDExtension のサンプルも Phase 3 に含める。** 要求定義書 Section 1.1 で Dart/Godot が主要ユースケースとして挙げられているが、C サンプルのみでは間接的なデモにしかならない。ただし、Dart / GDExtension のサンプルは各エコシステムの知識が必要なため、Phase 4 以降が現実的。

3. **自動テスト用の fixture モデルを examples に同梱する。** テストモデル (`test/models/multilingual-test-medium.onnx`) をサンプルディレクトリに symlink し、`make test` で自動テストを実行できるようにする。ただし ONNX モデルは ~75MB あり、examples ディレクトリに含めるのは不適切。

---

## 7. 後続タスクへの連絡事項

- **Phase 4 (M4-1 カスタム辞書):** カスタム辞書 API が追加されたら、`examples/c-api/custom_dict.c` サンプルを追加する。
- **Phase 4 (M4-2 Phoneme timing):** タイミング API が追加されたら、字幕生成のサンプルを追加する。
- **Dart FFI サンプル:** C API の設計が Flutter/Dart FFI を主要ユースケースとしているため (要求定義書 Section 9)、Dart サンプルは独立した Issue/PR で提供することを推奨。
- **CI 連携:** M3-5 の CI ワークフローに examples のビルドテストを含める。モデル不要のビルドのみテストし、実行テストはモデル存在時のみ。

---

## Phase 3 全体の振り返り: 一から設計するなら

Phase 3 を最初から設計し直すとしたら、以下の点を変更する。

### 配布レイアウトの設計

**現状:** M3-1 で `GNUInstallDirs` を導入し、M1-4 のハードコードされたパスを差し替えた。

**改善案:** Phase 1 の M1-4 で最初から `GNUInstallDirs` を使い、`EXPORT PiperPlusTargets` も含めるべきだった。Phase 3 での差し替えは影響範囲が広く、テストの再実行が必要になる。配布レイアウトは API 設計と同様に、最初から正しく設計するコストが最も低い。

**sherpa-onnx / vcpkg / Conan との整合:** 現在のレイアウト (`lib/`, `include/`, `share/`) は vcpkg の `vcpkg_cmake_install()` と完全互換。Conan も `CMakeToolchain` + `cmake_layout()` で同じレイアウトを期待する。sherpa-onnx はカスタムレイアウト (`lib/`, `include/`, `bin/sherpa-onnx-data/`) だが、piper-plus の `share/` 方式の方がFHS (Filesystem Hierarchy Standard) に準拠しており、Linux ディストリビューションのパッケージングにも適している。

### pkg-config と CMake Config の両方が本当に必要か

**結論: 両方必要。** ただし優先度は異なる。

| 利用シーン | 推奨 | 理由 |
|-----------|------|------|
| CMake プロジェクト (Flutter desktop, Qt) | CMake Config | ターゲットベースの依存伝播が最も堅牢 |
| Godot GDExtension (SCons) | pkg-config | GDExtension は SCons ベースで CMake を使わない |
| Meson プロジェクト | pkg-config | Meson は pkg-config をネイティブサポート |
| 手動 Makefile | pkg-config | 最もシンプルなインテグレーション |
| vcpkg / Conan | CMake Config | パッケージマネージャは `find_package` を前提 |

両方を提供する追加コストは低い (M3-2 は小タスク)。CMake Config だけでは SCons/Meson ユーザーをカバーできない。特に Godot GDExtension (要求定義書 Section 1.1.1) は SCons を使うため、pkg-config は必須。

### リリースワークフローの自動化範囲

**現状:** M3-5 で `dev-build-all.yml` / `build-piper.yml` を拡張し、4 プラットフォームの共有ライブラリアセットを生成。

**改善案:**

1. **`cmake --install` ベースのパッケージングを CLI にも適用する。** 現在の `build-piper.yml` は 200+ 行の手動ファイルコピーロジック (L262-489) を含んでいる。`cmake --install` に統一すれば、CLI と共有ライブラリの両方を同じ install ロジックでパッケージングでき、コードの重複を大幅に削減できる。本フェーズでは共有ライブラリのみ `cmake --install` を使い、CLI 側は既存のまま残す保守的な選択をしたが、全体的なリファクタリングの余地がある。

2. **共有ライブラリ専用 workflow を分離する。** `build-piper.yml` に `build-shared` フラグを追加する方式は条件分岐が増える。`build-piper-shared.yml` として分離し、依存セットアップは composite action で共有する方が保守性が高い。

3. **リリースアセットの自動テスト。** 現在の CI はビルド検証のみで、リリースアセットの tar.gz/zip を展開して動作確認するステップがない。ダウンロード -> 展開 -> `verify_install_layout.cmake` -> サンプルビルド -> サンプル実行 (モデル不要テスト) のパイプラインを追加すべき。

4. **vcpkg ポートの自動生成。** CMake Config パッケージが正しく機能すれば、vcpkg の `portfile.cmake` は `vcpkg_from_github()` + `vcpkg_cmake_configure(-DPIPER_PLUS_BUILD_SHARED=ON)` + `vcpkg_cmake_install()` + `vcpkg_cmake_config_fixup()` の 15 行程度で完成する。Phase 4 の候補として検討に値する。

### 全体的なアーキテクチャ判断

Phase 3 の 6 チケットは配布インフラに集中しており、実装コード (C API 自体) の変更は含まない。これは正しい分離。ただし、M3-4 (RPATH) は M1-4 (CMake 共有ライブラリターゲット定義) の一部として Phase 1 で実装すべきだった。ライブラリの RPATH は「配布」ではなく「ビルドシステム設計」の領域であり、Phase 1 で正しく設定しておけば Phase 3 での修正が不要だった。

同様に、M3-1 の `GNUInstallDirs` 導入と `EXPORT` 句の追加も、M1-4 で最初から含めるべきだった。Phase 3 は本来、M3-2 (pkg-config)、M3-3 (CMake Config)、M3-5 (リリースワークフロー)、M3-6 (使用例) の 4 チケットで済んだはず。

**教訓:** ビルドシステムの設計 (RPATH, install layout, EXPORT) は Phase 1 で完成させ、Phase 3 は「パッケージング + ドキュメント」に集中すべき。
