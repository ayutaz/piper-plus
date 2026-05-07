# Android G2P — OpenJTalk 辞書配布ガイド (Issue #388)

`piper-plus-g2p-android` の AAR には **OpenJTalk 辞書 (~102MB) は同梱しません**。
他の 7 言語 (en / zh / ko / es / fr / pt / sv) はすべて `libpiper_plus.so`
内のデータと規則ベース実装で完結するため、辞書ハンドル無しで動作します。
日本語のみが OpenJTalk の辞書を必要とするため、利用するアプリ側で 3 つの
配布パターンから選んでください。

> 関連: [要件定義書 §6.4](../spec/kotlin-g2p-requirements.md)、
> [`OpenJTalkDictionary`](../../android/piper-plus-g2p/src/main/java/com/piperplus/g2p/OpenJTalkDictionary.kt)、
> [`DictionaryDownloader`](../../android/piper-plus-g2p/src/main/java/com/piperplus/g2p/DictionaryDownloader.kt)

---

## 1. 辞書ハンドルの種類

`OpenJTalkDictionary.fromAssets(context)` を呼ぶ前に、辞書がどこにあるか
を決めます。`PiperPlusG2p.create(context, dictionary = …)` 時に
`null` を渡せば日本語以外の 7 言語のみで動作します。

| パターン | API | 配布物のサイズ影響 | F-Droid 互換 | UX |
|--------|-----|----------------|--------------|----|
| A. App assets バンドル | `OpenJTalkDictionary.fromAssets(context)` | APK +102MB | ◎ | ◎ (オフライン可) |
| B. Play Asset Delivery | `OpenJTalkDictionary.fromPath(packPath)` | install-time pack | ✕ (F-Droid 非対応) | ◎ |
| C. Runtime DL (HF Hub) | `DictionaryDownloader.downloadFromHuggingFace(...)` | APK 同程度 | △ (Anti-Feature 申告) | △ (初回のみ DL) |

---

## 2. パターン A: App assets

最もシンプル。APK に辞書を同梱し、初回起動時に `filesDir` へ展開します。

```text
my-app/
└── src/main/assets/open_jtalk_dic/
    ├── char.bin
    ├── dicrc
    ├── left-id.def
    ├── matrix.bin
    ├── right-id.def
    ├── sys.dic
    └── unk.dic
```

**手順:**
1. リリースから取得: `wget https://huggingface.co/ayousanz/piper-plus-base/resolve/main/open_jtalk_dic.tar`
2. 展開: `tar -xf open_jtalk_dic.tar -C app/src/main/assets/`
3. `aaptOptions { noCompress 'bin', 'dic' }` を `android { }` ブロックに追加 (任意 — 既に圧縮するメリットは薄い)
4. Kotlin:
```kotlin
val dict = OpenJTalkDictionary.fromAssets(context)
val g2p = PiperPlusG2p.create(context, dict)
```

`fromAssets` は `filesDir/open_jtalk_dic/` が空の場合だけ展開を行うので、
2 回目以降の起動はノーオペで済みます。

---

## 3. パターン B: Play Asset Delivery (install-time pack)

Google Play 配布専用。アプリ APK サイズを抑えつつ install 時に DL を完結
させたい場合に有効。

```kotlin
// AssetPackManager 経由でパック保存先を取得した後、
val packPath = "/data/.../assets/open_jtalk_dic_pack/open_jtalk_dic"
val dict = OpenJTalkDictionary.fromPath(packPath)
val g2p  = PiperPlusG2p.create(context, dict)
```

詳細は Android 公式ドキュメント
[Play Asset Delivery](https://developer.android.com/guide/playcore/asset-delivery)
を参照。

> **F-Droid との両立**: F-Droid フレーバーには PAD が存在しないため、
> `productFlavors` で flavors を分け、F-Droid フレーバーは A または C を選ぶ。

---

## 4. パターン C: 実行時 DL (Hugging Face Hub)

`DictionaryDownloader.downloadFromHuggingFace()` は以下を行います:

1. `https://huggingface.co/<repo>/resolve/main/open_jtalk_dic.tar.sha256` から SHA-256 sidecar 取得
2. `https://huggingface.co/<repo>/resolve/main/open_jtalk_dic.tar` を `cacheDir` にダウンロード
3. SHA-256 を検証 (NFR-SEC-2)
4. tar を `filesDir/open_jtalk_dic/` へ展開
5. [OpenJTalkDictionary] を返す

```kotlin
lifecycleScope.launch {
    val dict = DictionaryDownloader.downloadFromHuggingFace(context) { read, total ->
        // UI 進捗バー更新
    }
    val g2p = PiperPlusG2p.create(context, dict)
}
```

### F-Droid 注意

F-Droid で配布するアプリでこの API を露出する場合、**Anti-Feature**
"Non-Free Network Services" を `metadata/<package>/en-US/short_description.txt`
の Antifeatures フィールドに明記してください。

---

## 5. 辞書を使わない構成 (7 言語のみ)

日本語以外で十分なら辞書ハンドル不要:

```kotlin
val g2p = PiperPlusG2p.create(context)  // dictionary = null
val r = g2p.phonemize("hola mundo", "es")  // OK
```

`g2p.phonemize("こんにちは", "ja")` は OpenJTalk が初期化されていない
ため空または "unknown" 言語の結果を返します (例外ではなく劣化動作)。

---

## 6. チェックサム配布

HF Hub repo に配置するファイル名:

| ファイル | 内容 |
|---------|-----|
| `open_jtalk_dic.tar` | naist-jdic を tar アーカイブ化したもの (~102MB) |
| `open_jtalk_dic.tar.sha256` | 1 行の sha256sum 出力形式 (`<sha>  open_jtalk_dic.tar`) |

リリース時は `tools/build-openjtalk-dict-archive.sh` (M6 で追加予定) で
両ファイルを生成し、HF Hub の repo にアップロードします。

---

## 7. 関連ドキュメント

- [要件定義書 §6.4 (FR-DICT-*)](../spec/kotlin-g2p-requirements.md)
- [既存 TTS フル AAR の辞書展開ロジック (`PiperPlus.kt:80-146`)](../../android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt)
- [`OpenJTalkDictionary` Kotlin source](../../android/piper-plus-g2p/src/main/java/com/piperplus/g2p/OpenJTalkDictionary.kt)
- [`DictionaryDownloader` Kotlin source](../../android/piper-plus-g2p/src/main/java/com/piperplus/g2p/DictionaryDownloader.kt)
