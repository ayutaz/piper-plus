# OpenJTalk API ドキュメント

## 概要
OpenJTalkラッパーは、日本語テキストを音素列に変換するためのC言語APIを提供します。このAPIは、Linux、macOS、Windowsで動作します。

## API関数

### openjtalk_is_available()
OpenJTalkバイナリが利用可能かどうかをチェックします。システムPATH、または環境変数で指定されたパスからOpenJTalkバイナリを検索します。

```c
bool openjtalk_is_available();
```

**説明:**
この関数は内部的に以下の順序でOpenJTalkバイナリを検索します：
1. 環境変数 `OPENJTALK_PATH` で指定されたパス
2. システムのPATH環境変数内のディレクトリ
3. プラットフォーム固有の標準インストールパス

**パラメータ:**
なし

**戻り値:**
- `true`: OpenJTalkバイナリが見つかった場合
- `false`: OpenJTalkバイナリが見つからない場合

**エラーハンドリング:**
この関数は例外を投げません。バイナリが見つからない場合は単に`false`を返します。

**使用例:**
```c
#include <stdio.h>
#include "openjtalk_wrapper.h"

int main() {
    if (!openjtalk_is_available()) {
        fprintf(stderr, "Error: OpenJTalk is not installed or not in PATH\n");
        fprintf(stderr, "Please install OpenJTalk or set OPENJTALK_PATH environment variable\n");
        return -1;
    }
    
    printf("OpenJTalk is available\n");
    return 0;
}
```

### openjtalk_ensure_dictionary()
OpenJTalk辞書が利用可能であることを確認し、必要に応じて自動ダウンロードします。

```c
bool openjtalk_ensure_dictionary();
```

**説明:**
この関数はOpenJTalkの音声合成に必要な辞書ファイルの存在を確認します。辞書が見つからない場合、設定に応じて自動的にダウンロードを試みます。

**パラメータ:**
なし

**戻り値:**
- `true`: 辞書が利用可能な場合（既存または正常にダウンロードされた）
- `false`: 辞書の取得に失敗した場合

**環境変数:**
- `OPENJTALK_DICTIONARY_PATH`: カスタム辞書パスを指定
  - 例: `/usr/local/share/open_jtalk/dic`
- `PIPER_OFFLINE_MODE=1`: オフラインモード（自動ダウンロード無効）
- `PIPER_AUTO_DOWNLOAD_DICT=0`: 自動ダウンロードを無効化

**エラーハンドリング:**
- ネットワークエラー: 標準エラー出力にメッセージを出力し、`false`を返す
- ディスク容量不足: 標準エラー出力にメッセージを出力し、`false`を返す
- 権限エラー: 標準エラー出力にメッセージを出力し、`false`を返す

**使用例:**
```c
#include <stdio.h>
#include <stdlib.h>
#include "openjtalk_wrapper.h"

int main() {
    // カスタム辞書パスを設定（オプション）
    setenv("OPENJTALK_DICTIONARY_PATH", "/path/to/custom/dic", 1);
    
    // 辞書の確認と自動ダウンロード
    if (!openjtalk_ensure_dictionary()) {
        fprintf(stderr, "Failed to ensure OpenJTalk dictionary\n");
        fprintf(stderr, "Check network connection or set PIPER_OFFLINE_MODE=1\n");
        return -1;
    }
    
    printf("Dictionary is ready\n");
    return 0;
}
```

### openjtalk_text_to_phonemes()
日本語テキストを音素列に変換します。

```c
char* openjtalk_text_to_phonemes(const char* text);
```

**説明:**
この関数は日本語テキストを受け取り、OpenJTalkを使用して音素列に変換します。出力される音素は空白で区切られた形式になります。

**パラメータ:**
- `text`: 変換する日本語テキスト（UTF-8エンコーディング）
  - NULLを渡すとNULLを返します
  - 空文字列を渡すと空文字列を返します
  - 最大長: 4096バイト（現在の制限）

**戻り値:**
- 成功時: 音素列を含む文字列（呼び出し側でfreeが必要）
  - 例: "k o N n i ch i w a s e k a i"
- 失敗時: NULL

**エラーハンドリング:**
- 入力テキストが4096バイトを超える場合: NULLを返し、stderrにエラーメッセージ
- OpenJTalkの実行に失敗した場合: NULLを返し、stderrにエラーメッセージ
- メモリ割り当てに失敗した場合: NULLを返す

**使用例:**
```c
#include <stdio.h>
#include <string.h>
#include "openjtalk_wrapper.h"

int main() {
    // 基本的な使用例
    const char* text = "こんにちは世界";
    char* phonemes = openjtalk_text_to_phonemes(text);
    if (phonemes) {
        printf("Input: %s\n", text);
        printf("Phonemes: %s\n", phonemes);
        openjtalk_free_phonemes(phonemes);
    } else {
        fprintf(stderr, "Failed to convert text to phonemes\n");
        return -1;
    }
    
    // エラーハンドリングの例
    char* long_text = malloc(5000);
    memset(long_text, 'あ', 4999);
    long_text[4999] = '\0';
    
    char* result = openjtalk_text_to_phonemes(long_text);
    if (!result) {
        fprintf(stderr, "Expected error: text too long\n");
    }
    
    free(long_text);
    return 0;
}
```

**パフォーマンス考慮事項:**
- この関数は外部プロセスを起動するため、高頻度での呼び出しは避けてください
- バッチ処理が必要な場合は、テキストをまとめて処理することを検討してください

### openjtalk_free_phonemes()
`openjtalk_text_to_phonemes()`で割り当てられたメモリを解放します。

```c
void openjtalk_free_phonemes(char* phonemes);
```

**説明:**
この関数は`openjtalk_text_to_phonemes()`によって動的に割り当てられたメモリを安全に解放します。メモリリークを防ぐため、必ず呼び出してください。

**パラメータ:**
- `phonemes`: 解放する音素文字列
  - NULLを渡しても安全（何もしない）
  - 既に解放済みのポインタを渡すと未定義動作

**戻り値:**
なし

**使用例:**
```c
#include <stdio.h>
#include "openjtalk_wrapper.h"

void process_text(const char* text) {
    char* phonemes = openjtalk_text_to_phonemes(text);
    if (phonemes) {
        // 音素を使用
        printf("Phonemes: %s\n", phonemes);
        
        // 必ずメモリを解放
        openjtalk_free_phonemes(phonemes);
        phonemes = NULL; // ダングリングポインタを防ぐ
    }
}

// NULLセーフな使用例
void safe_example() {
    char* phonemes = NULL;
    
    // 条件によっては音素が生成されない場合
    if (some_condition) {
        phonemes = openjtalk_text_to_phonemes("テスト");
    }
    
    // NULLでも安全に呼び出せる
    openjtalk_free_phonemes(phonemes);
}
```

## 内部API関数（上級者向け）

より細かい制御が必要な場合に使用する内部API関数です。

### openjtalk_initialize()
OpenJTalkインスタンスを初期化します。

```c
OpenJTalk* openjtalk_initialize();
```

**説明:**
この関数はOpenJTalkインスタンスを作成し、初期化します。メモリが動的に割り当てられ、必要な内部構造がセットアップされます。

**パラメータ:**
なし

**戻り値:**
- 成功時: OpenJTalkインスタンスへのポインタ
- 失敗時: NULL（メモリ割り当て失敗など）

**使用例:**
```c
OpenJTalk* oj = openjtalk_initialize();
if (!oj) {
    fprintf(stderr, "Failed to initialize OpenJTalk\n");
    return -1;
}
```

### openjtalk_finalize()
OpenJTalkインスタンスを終了し、メモリを解放します。

```c
void openjtalk_finalize(OpenJTalk* oj);
```

**説明:**
この関数はOpenJTalkインスタンスに関連するすべてのリソースを解放します。

**パラメータ:**
- `oj`: 解放するOpenJTalkインスタンス
  - NULLを渡しても安全（何もしない）

**戻り値:**
なし

### openjtalk_extract_fullcontext()
テキストからフルコンテキストラベルを抽出します。

```c
HTS_Label_Wrapper* openjtalk_extract_fullcontext(OpenJTalk* oj, const char* text);
```

**説明:**
この関数は日本語テキストを解析し、HTSフルコンテキストラベルを生成します。これは音声合成の中間表現です。

**パラメータ:**
- `oj`: OpenJTalkインスタンス
- `text`: 解析する日本語テキスト（UTF-8）

**戻り値:**
- 成功時: HTS_Label_Wrapperインスタンス
- 失敗時: NULL

### HTS_Label_get_size()
ラベル数を取得します。

```c
size_t HTS_Label_get_size(HTS_Label_Wrapper* label);
```

**パラメータ:**
- `label`: HTS_Label_Wrapperインスタンス

**戻り値:**
ラベルの数

### HTS_Label_get_string()
指定したインデックスのラベル文字列を取得します。

```c
const char* HTS_Label_get_string(HTS_Label_Wrapper* label, size_t index);
```

**パラメータ:**
- `label`: HTS_Label_Wrapperインスタンス
- `index`: ラベルのインデックス（0ベース）

**戻り値:**
- 成功時: ラベル文字列（解放不要）
- 失敗時: NULL（インデックスが範囲外）

### HTS_Label_clear()
HTS_Label_Wrapperをクリアします。

```c
void HTS_Label_clear(HTS_Label_Wrapper* label);
```

**パラメータ:**
- `label`: クリアするHTS_Label_Wrapperインスタンス

**完全な使用例:**
```c
#include "openjtalk_wrapper.h"
#include <stdio.h>

int main() {
    // OpenJTalkインスタンスを初期化
    OpenJTalk* oj = openjtalk_initialize();
    if (!oj) {
        fprintf(stderr, "Failed to initialize OpenJTalk\n");
        return -1;
    }
    
    // フルコンテキストラベルを抽出
    const char* text = "こんにちは";
    HTS_Label_Wrapper* label = openjtalk_extract_fullcontext(oj, text);
    if (!label) {
        fprintf(stderr, "Failed to extract full context\n");
        openjtalk_finalize(oj);
        return -1;
    }
    
    // ラベルを処理
    size_t label_count = HTS_Label_get_size(label);
    printf("Label count: %zu\n", label_count);
    
    for (size_t i = 0; i < label_count; i++) {
        const char* label_str = HTS_Label_get_string(label, i);
        if (label_str) {
            printf("Label[%zu]: %s\n", i, label_str);
        }
    }
    
    // クリーンアップ
    HTS_Label_clear(label);
    openjtalk_finalize(oj);
    
    return 0;
}
```

## 音素記号

変換される音素記号の例：

| カタカナ | 音素 |
|---------|------|
| ア | a |
| カ | k a |
| ガ | g a |
| サ | s a |
| ザ | z a |
| タ | t a |
| ダ | d a |
| ナ | n a |
| ハ | h a |
| バ | b a |
| パ | p a |
| マ | m a |
| ヤ | y a |
| ラ | r a |
| ワ | w a |
| ン | N |
| ッ | q |
| ー | (前の母音を延長) |

## エラーハンドリング

現在の実装では、エラー時にはNULLが返されます。詳細なエラー情報は標準エラー出力に出力されます。

```c
char* phonemes = openjtalk_text_to_phonemes(text);
if (!phonemes) {
    // エラーメッセージは stderr に出力される
    fprintf(stderr, "Failed to convert text to phonemes\n");
}
```

## スレッドセーフティ

⚠️ **警告**: 現在の実装はスレッドセーフではありません。複数スレッドから同時に使用する場合は、適切な同期機構を実装してください。

## メモリ使用量

- 入力テキストのサイズに比例してメモリを使用
- 内部バッファは4096バイトに制限（将来的に改善予定）
- 一時ファイルがシステムの一時ディレクトリに作成される

## 制限事項

1. 入力テキストは4096バイト未満である必要があります
2. 一時ファイルへの書き込み権限が必要です
3. OpenJTalkバイナリへのアクセスが必要です