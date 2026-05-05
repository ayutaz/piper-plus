# Swift G2P Integration Guide

> **Status:** Proposed — implementation tracked in [Issue #387](https://github.com/ayutaz/piper-plus/issues/387)
> **Spec:** [docs/spec/swift-g2p.md](../spec/swift-g2p.md)
> **適用バージョン:** v1.14.0+ (予定)

iOS / Swift プロジェクトから piper-plus の **G2P (Grapheme-to-Phoneme) を単独で利用する**ための統合ガイド。
合成エンジン (`PiperPlus`) と独立した Swift Package product `PiperPlusG2P` を提供する。

> **合成エンジンと組み合わせて TTS をフルパイプラインで使いたい場合は** → [iOS Integration Guide (合成エンジン)](./ios-integration.md) を参照。本ガイドは **G2P のみ** が必要な consumer 向け。

---

## When to use `PiperPlusG2P`

| Your situation | Use |
|----------------|-----|
| ONNX 合成までフルで使う | `PiperPlus` (合成 + 内部 G2P + ORT) — [iOS Integration Guide](./ios-integration.md) |
| **テキスト → IPA トークンのみ必要** | **`PiperPlusG2P`** (本ガイド) |
| AVSpeechSynthesizer / 別 TTS の前処理に発音記号がほしい | `PiperPlusG2P` |
| 単語にフリガナ・発音記号を付与したい | `PiperPlusG2P` |
| 多言語ローカライズのオフライン補助ツール | `PiperPlusG2P` |

`PiperPlusG2P` は **ONNX Runtime に依存しない** ため、Embed & Sign 不要、バイナリサイズも軽量 (~3-5 MB zip)。

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Xcode | 15+ |
| iOS Deployment Target | 15.0+ |
| Swift | 5.9+ |
| Bitcode | Disabled (deprecated since Xcode 14) |

---

## Supported Languages

| Language | Code | 実装 | 辞書同梱 | バイナリへの寄与 |
|----------|------|------|---------|----------------|
| 日本語 | `ja` | jpreprocess (Rust port of OpenJTalk) | NAIST-JDIC 埋込 | ~30 MB |
| 英語 | `en` | g2p 規則 + CMU 辞書 | あり | ~2 MB |
| 中国語 (Mandarin) | `zh` | pypinyin 互換 | CC-CEDICT 由来 JSON 埋込 | ~3 MB |
| 韓国語 | `ko` | Hangul 分解規則 | なし (規則ベース) | <1 MB |
| スペイン語 | `es` | 規則ベース | なし | <1 MB |
| フランス語 | `fr` | 規則ベース | なし | <1 MB |
| ポルトガル語 | `pt` | 規則ベース | なし | <1 MB |
| スウェーデン語 | `sv` | 規則ベース | なし | <1 MB |

> 配布される xcframework はデフォルトで **全 8 言語有効**。consumer 側で言語の選択無効化はできない (Cargo features がビルド時に固定化されるため)。サイズ制約のあるアプリ向け lite slice の提供は将来検討中 ([spec §7.4](../spec/swift-g2p.md#74-lite-slice-ja-除外--言語選択ビルド))。

---

## Step 1: Add `PiperPlusG2P` to your Package.swift

```swift
// Package.swift
// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "MyApp",
    platforms: [.iOS(.v15)],
    dependencies: [
        .package(url: "https://github.com/ayutaz/piper-plus", from: "1.14.0"),
    ],
    targets: [
        .target(
            name: "MyApp",
            dependencies: [
                .product(name: "PiperPlusG2P", package: "piper-plus"),
            ]
        ),
    ]
)
```

> SwiftPM が `binaryTarget(url:, checksum:)` から `libpiper_plus_g2p-ios-v${VERSION}.xcframework.zip` を取得する。初回 resolve 時にダウンロード ~3-5 MB。

### Xcode プロジェクトの場合 (Package.swift を使わない)

1. **GitHub Releases** から `libpiper_plus_g2p-ios-v${VERSION}.xcframework.zip` をダウンロード
   ```bash
   gh release download v1.14.0 -p 'libpiper_plus_g2p-ios-v*.xcframework.zip' --repo ayutaz/piper-plus
   unzip libpiper_plus_g2p-ios-v*.xcframework.zip
   ```
2. **Project Navigator** に `piper_plus_g2p.xcframework` をドラッグ
3. **Targets** → **General** → **Frameworks, Libraries, and Embedded Content** で **"Do Not Embed"** (static archive)
4. Swift から `import PiperPlusG2PBinary` で C API を直接利用するか、`Sources/PiperPlusG2P/*.swift` を手動コピーして `import PiperPlusG2P` を使う

---

## Step 2: Use from Swift

### 基本: 単一言語

```swift
import PiperPlusG2P

let phonemizer = try Phonemizer(languages: [.english])
let result = try phonemizer.phonemize("Hello, world!", language: .english)
print(result.tokens)
// → ["h", "ə", "ˈl", "oʊ", " ", "ˈw", "ɝː", "l", "d", "!"]
```

### 多言語

```swift
import PiperPlusG2P

let phonemizer = try Phonemizer(languages: [.japanese, .english, .chinese])

let ja = try phonemizer.phonemize("こんにちは", language: .japanese)
let en = try phonemizer.phonemize("Hello",   language: .english)
let zh = try phonemizer.phonemize("你好",     language: .chinese)

print(ja.tokens, en.tokens, zh.tokens)
```

### 全言語デフォルトで初期化

```swift
let phonemizer = try Phonemizer()  // languages: Language.allCases (全 8 言語)
print(phonemizer.availableLanguages)
// → [.japanese, .english, .chinese, .korean, .spanish, .french, .portuguese, .swedish]
```

### エラーハンドリング

```swift
import PiperPlusG2P

do {
    let phonemizer = try Phonemizer(languages: [.english])
    let result = try phonemizer.phonemize("Hello", language: .japanese) // 未登録
} catch G2PError.unsupportedLanguage(let code) {
    print("Language not registered: \(code)")
} catch {
    print("Other error: \(error)")
}
```

### SwiftUI から

```swift
import SwiftUI
import PiperPlusG2P

struct PhonemeView: View {
    @State private var input = "Hello"
    @State private var phonemes: [String] = []
    private let phonemizer = try? Phonemizer(languages: [.english])

    var body: some View {
        VStack {
            TextField("Text", text: $input)
            Button("Phonemize") {
                phonemes = (try? phonemizer?.phonemize(input, language: .english).tokens) ?? []
            }
            Text(phonemes.joined(separator: " "))
        }
    }
}
```

---

## Time-To-Hello-World Target

| Stage | Target | Action |
|-------|--------|--------|
| 0:00–0:02 | 2 min | このガイドを読む、`PiperPlusG2P` を選ぶ |
| 0:02–0:05 | 3 min | `Package.swift` に dependency 追加、`swift package resolve` |
| 0:05–0:10 | 5 min | `Phonemizer` 初期化、最初の `phonemize` を呼んで Console 出力確認 |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `swift package resolve` で checksum mismatch | `Package.swift` の checksum が tag commit と不一致 | リポジトリの該当タグを check out するか、`Package.swift` を最新タグに合わせる |
| `import PiperPlusG2P` が見つからない | `dependencies` に product を追加し忘れ | `.product(name: "PiperPlusG2P", package: "piper-plus")` を targets の dependencies に追加 |
| `Phonemizer(languages:)` が `initializationFailed` を投げる | 内部で全言語の registration が失敗 (極稀) | デバッグ用に `languages: [.english]` のみで試して subset を絞る |
| `phonemize(_:language:)` が `nullResult` を返す | `Phonemizer` 初期化時に渡していない言語を呼んだ | `init(languages:)` の配列に対象言語を含める |
| 中国語の結果が空 | `ChinesePhonemizer` の埋込辞書が読めていない | xcframework のバージョン確認。`v1.14.0+` で埋込辞書サポート |
| 日本語の結果が文字化け | iOS 側で SourceFile encoding が UTF-8 でない | Xcode → File Inspector → Text Encoding を `Unicode (UTF-8)` に |
| `_piper_plus_g2p_*` undefined symbol (link time) | xcframework が target に追加されていない | Step 1 を確認。手動追加の場合は **Frameworks, Libraries** で **Do Not Embed** で **Linked** になっているか |
| Build OK on simulator, crash on device | 単一 slice のみ取得 (古い tar.gz など) | v1.14.0+ の xcframework.zip を使用 (両 slice 同梱) |

---

## App Store Submission Checklist

`PiperPlusG2P` は **Required Reason API を直接呼んでいない** ため、本ライブラリ起因で Privacy Manifest 追加項目はない。

ただし合成側 (`PiperPlus`) と併用する場合は [iOS Integration Guide § App Store Submission](./ios-integration.md#app-store-submission-checklist) を参照。

### `Info.plist`

```xml
<key>ITSAppUsesNonExemptEncryption</key>
<false/>
```

`PiperPlusG2P` は暗号化を使用しない (内部辞書は plaintext)。

---

## Compatibility Status

| Item | Status | Notes |
|------|--------|-------|
| iOS device + simulator | ✓ | `ios-arm64` + `ios-arm64_x86_64-simulator` |
| Swift `import PiperPlusG2P` | ✓ | `module.modulemap` 同梱 |
| macOS | ✗ | 別 slice として将来追加予定 ([spec §7.1](../spec/swift-g2p.md#71-macos--visionos-slice-追加)) |
| visionOS / Mac Catalyst | ✗ | 同上 |
| App Extension / App Clip | ⚠ | サイズ次第で可能 (5 言語規則ベースのみなら ~2 MB)、JA/ZH 含めると 10MB を超え App Clip 不可 |
| Privacy Manifest | ✓ (informational) | xcframework root に空の `PrivacyInfo.xcprivacy` を同梱 (Required Reason API 利用なし) |
| iOS 14 以下 | ✗ | iOS 15+ のみ (`Package.swift` の platforms 制約) |

---

## License Notes

`PiperPlusG2P` は MIT License で配布される。ただし内蔵辞書のライセンスに注意:

| 言語 | 辞書 | ライセンス | 同梱形態 |
|------|------|-----------|---------|
| 日本語 | NAIST-JDIC | BSD-3-Clause + Modified-BSD | バイナリ埋込 (consumer の app に複製される) |
| 中国語 | CC-CEDICT 由来 (派生) | Creative Commons Attribution-Share Alike 4.0 | バイナリ埋込 |
| 英語 | CMU Pronouncing Dictionary | BSD-2-Clause | バイナリ埋込 |
| 他 | (規則ベースのみ、辞書なし) | — | — |

詳細: [src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md](../../src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md)

> **App Store 配布時の注意**: アプリの License/About 画面に上記ライセンス表記を含めること推奨。CC BY-SA 4.0 (CC-CEDICT) 派生部分について、由来表示が義務付けられる。

---

## Further Reading

- [Swift G2P Specification](../spec/swift-g2p.md) — design rationale, alternatives, risks
- [iOS Integration Guide (合成エンジン)](./ios-integration.md) — フル TTS が必要な場合
- [piper-plus-g2p crate (Rust)](../../src/rust/piper-plus-g2p/) — 同じロジックの Rust API ドキュメント
- [Issue #387](https://github.com/ayutaz/piper-plus/issues/387) — 機能リクエスト trackr
