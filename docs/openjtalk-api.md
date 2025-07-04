# OpenJTalk API ドキュメント

## 概要
OpenJTalkラッパーは、日本語テキストを音素列に変換するためのC言語APIを提供します。このAPIは、Linux、macOS、Windowsで動作します。

## API関数

### openjtalk_is_available()
OpenJTalkバイナリが利用可能かどうかをチェックします。

```c
bool openjtalk_is_available();
```

**戻り値:**
- `true`: OpenJTalkバイナリが見つかった場合
- `false`: OpenJTalkバイナリが見つからない場合

**使用例:**
```c
if (!openjtalk_is_available()) {
    fprintf(stderr, "OpenJTalk is not installed\n");
    return -1;
}
```

### openjtalk_ensure_dictionary()
OpenJTalk辞書が利用可能であることを確認し、必要に応じて自動ダウンロードします。

```c
bool openjtalk_ensure_dictionary();
```

**戻り値:**
- `true`: 辞書が利用可能な場合
- `false`: 辞書の取得に失敗した場合

**環境変数:**
- `OPENJTALK_DICTIONARY_PATH`: カスタム辞書パスを指定
- `PIPER_OFFLINE_MODE=1`: オフラインモード（自動ダウンロード無効）
- `PIPER_AUTO_DOWNLOAD_DICT=0`: 自動ダウンロードを無効化

### openjtalk_text_to_phonemes()
日本語テキストを音素列に変換します。

```c
char* openjtalk_text_to_phonemes(const char* text);
```

**パラメータ:**
- `text`: 変換する日本語テキスト（UTF-8エンコーディング）

**戻り値:**
- 成功時: 音素列を含む文字列（要free）
- 失敗時: NULL

**使用例:**
```c
const char* text = "こんにちは世界";
char* phonemes = openjtalk_text_to_phonemes(text);
if (phonemes) {
    printf("Phonemes: %s\n", phonemes);
    openjtalk_free_phonemes(phonemes);
}
```

### openjtalk_free_phonemes()
`openjtalk_text_to_phonemes()`で割り当てられたメモリを解放します。

```c
void openjtalk_free_phonemes(char* phonemes);
```

**パラメータ:**
- `phonemes`: 解放する音素文字列

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