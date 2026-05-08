# Swift G2P 配布仕様

> **Status:** Implemented (v1.14.0+)
> **対象 Issue:** [#387](https://github.com/ayutaz/piper-plus/issues/387)
> **対象ファイル:**
> [`src/rust/piper-plus-g2p/`](../../src/rust/piper-plus-g2p/),
> [`Sources/PiperPlusG2P/`](../../Sources/PiperPlusG2P/),
> [`Package.swift`](../../Package.swift),
> [`.github/workflows/release-shared-lib.yml`](../../.github/workflows/release-shared-lib.yml),
> [`docs/guides/swift-g2p-integration.md`](../guides/swift-g2p-integration.md)

---

## 概要

本仕様は piper-plus を **Swift / iOS / macOS から G2P (Grapheme-to-Phoneme) として利用する** ための配布物・ビルド経路・公開 API を定義する。
合成エンジン本体 (`libpiper_plus.a` + ONNX Runtime) を組み込まずに、**G2P 単体**として 8 言語 (ja / en / zh / ko / es / fr / pt / sv) を Swift から呼べるようにする。

実装の詳細は実コードを真とし、本仕様は方針・契約・採用しなかった案を残すことに専念する。API/JSON envelope/ABI 互換性の規範定義は [`docs/spec/swift-g2p-contract.toml`](./swift-g2p-contract.toml) を参照。

---

## 1. 背景と要件

### 1.1 ユースケース

| シナリオ | 必要機能 | ORT 依存 |
|---------|---------|----------|
| iOS アプリで piper-plus と組み合わせて TTS 合成 | 既存 `libpiper_plus.a` 内蔵 G2P で解決済 | あり |
| **iOS / macOS アプリで G2P 単体利用 (Issue #387)** | 文字列 → IPA トークン列 | **なし** |
| 単語のフリガナ付与 / 発音記号生成 | 同上 | なし |
| サードパーティ TTS と組合せ (例: AVSpeechSynthesizer の前処理) | 同上 | なし |
| 多言語ローカライズ補助ツール | 同上 | なし |

> Swift エコシステムには公式の多言語 G2P が乏しく、特に**規則ベースのみで動く ES/PT/FR/SV** および **辞書埋込済の JA / ZH / EN** をオフラインで提供できる価値は大きい。

### 1.2 既存資産

| 資産 | 状態 | 本仕様で利用 |
|------|------|-------------|
| `src/rust/piper-plus-g2p` (Rust crate, 8 言語) | 公開済 (crates.io: `piper-plus-g2p`) | **基盤** |
| `src/rust/piper-plus-g2p/src/ffi.rs` (C ABI, 5 関数) | 既実装 | **流用 + Chinese embedded コンストラクタ追加** |
| `Sources/PiperPlus/PiperPlus.swift` (合成エンジン用 Swift wrapper) | v1.13.0 公開 | 同 Package.swift に target 追加 |
| `release-shared-lib.yml` の `build-ios` matrix | 2 slice (device / simulator) ビルド済 | 並列に G2P slice ジョブを追加 |

### 1.3 非目標

- **学習側 G2P (`src/python/g2p/`) との同期**: ランタイム G2P (Rust 実装) に閉じる。学習側 (Python) は scope 外。
- **PUA エンコード後の phoneme_ids 出力**: G2P は IPA トークン列を返すまでが責務 (既存 ffi.rs と同じ)。`phoneme_id_map` への変換は合成エンジンか consumer 側で行う。
- **visionOS / Mac Catalyst**: 本リリースでは見送り。`Package.swift` の `platforms:` 拡張で将来対応可。
- **SSML パーサ**: Rust 側 `ssml` モジュールは別途公開。G2P レイヤでは生テキストを受ける。

---

## 2. 採用方針: Plan A — Rust FFI + Swift wrapper

### 2.1 アーキテクチャ

```
┌────────────────────────────────────────────────┐
│ Swift consumer (iOS / macOS app)               │
│   import PiperPlusG2P                          │
│   let phonemizer = try Phonemizer(             │
│       languages: [.japanese, .english])        │
│   let tokens = try phonemizer.phonemize(       │
│       "こんにちは", language: .japanese)         │
└────────────────────┬───────────────────────────┘
                     │  Swift idiomatic API
┌────────────────────▼───────────────────────────┐
│ Sources/PiperPlusG2P/*.swift                   │
│   Phonemizer.swift   (class wrapper)           │
│   Language.swift     (enum)                    │
│   G2PError.swift     (Error, diagnostic info)  │
│   PhonemizeResult.swift (Codable)              │
│   PUAMap.swift       (token ↔ PUA codepoint)   │
└────────────────────┬───────────────────────────┘
                     │  C FFI (piper_plus_g2p_*)
┌────────────────────▼───────────────────────────┐
│ libpiper_plus_g2p.a  (Rust staticlib)          │
│   src/rust/piper-plus-g2p/src/ffi.rs           │
│     piper_plus_g2p_create()                    │
│     piper_plus_g2p_phonemize() → JSON          │
│     piper_plus_g2p_available_languages()       │
│     piper_plus_g2p_free_string()               │
│     piper_plus_g2p_free()                      │
└────────────────────┬───────────────────────────┘
                     │  pure Rust (依存なし — 規則ベース or 埋込辞書)
            ja: jpreprocess (NAIST-JDIC bundled)
            en: cmudict (JSON, bundled-dicts feature)
            zh: 静的 JSON 辞書 (CC-CEDICT 由来)
            ko/es/fr/pt/sv: 規則ベース
```

### 2.2 不変条件

- **C 依存なし**: `libpiper_plus_g2p.a` は Rust + 標準ライブラリのみ。OpenJTalk / mecab / espeak-ng への C 依存を持ち込まない。
- **ONNX Runtime 依存なし**: 合成エンジンと完全に独立。consumer は ORT を Embed & Sign せずに利用可。
- **既存 `libpiper_plus.a` との衝突なし**: シンボル名 `piper_plus_g2p_*` で名前空間分離済。両方をリンクしてもよい。
- **JSON I/F 維持**: `phonemize` 結果は既存 ffi.rs 同様 `{"tokens":[...],"language":".."}` 形式。Swift 側も同じ JSON を Codable で受ける。

---

## 3. アーキテクチャ詳細

### 3.1 配布構成

**xcframework は独立配布する** (`libpiper_plus.xcframework` には統合しない)。

| 配布物 | 中身 | サイズ目安 | 用途 |
|--------|------|-----------|------|
| `libpiper_plus-ios-v${VERSION}.xcframework.zip` (既存) | C++ 合成 + 内部 G2P + ORT 必須 | ~15 MB (zip) | 合成エンジン |
| **`libpiper_plus_g2p-apple-v${VERSION}.xcframework.zip` (v1.14.0+)** | **Rust G2P のみ、ORT 不要** | **~3-5 MB (zip, 言語デフォルト構成)** | **G2P 単独** |

> **artifact 名**: G2P xcframework は v1.14.0 で macOS slice を加えた際 `-ios-` から `-apple-` に rename。旧 `-ios-` 名は維持しない。

#### 統合せず独立にする理由

| 観点 | 統合した場合 | 独立にした場合 (採用) |
|------|------------|---------------------|
| G2P 単独利用時の依存 | ORT (~31MB device / ~67MB simulator) を必須化してしまう | ORT 不要、軽量 |
| バイナリサイズ | 単一巨大 archive | 用途別に選択可 |
| 合成 + G2P 両方使う場合 | リンク 1 回 | リンク 2 回 (`libpiper_plus.a` + `libpiper_plus_g2p.a`) — シンボル衝突なし |
| Cargo features の露出 | C++ 側で機能 flag 管理が必要 | Rust の Cargo features を直接活用 |
| リリース cadence | 合成と G2P が連動 (片方の不具合で両方ブロック) | 独立リリース可 |

> `Package.swift` では両方の `binaryTarget` を別 product として宣言し、consumer は `.product(name: "PiperPlus", ...)` か `.product(name: "PiperPlusG2P", ...)` を独立に選べる。

### 3.2 Slice 構成

| Slice | アーキテクチャ | 用途 |
|-------|--------------|------|
| `ios-arm64` | arm64 (device) | 実機 (iPhone / iPad) |
| `ios-arm64_x86_64-simulator` | arm64 + x86_64 (universal) | シミュレータ (Apple Silicon Mac / Intel Mac) |
| `macos-arm64_x86_64` (v1.14.0+) | arm64 + x86_64 (universal) | macOS host (`swift run` / CLI tooling) |

> 合成エンジンの `libpiper_plus.xcframework` には macOS slice は無い (ORT が独自に macOS 配布チャンネルを持つため)。G2P は pure Rust でこの制約がない。

### 3.3 言語構成 (デフォルト)

xcframework に同梱する Cargo features は `all-languages,naist-jdic,bundled-dicts,ffi`:

- **JA**: `naist-jdic` feature 有効化で NAIST-JDIC 辞書を staticlib に埋込む (Rust 側で `include_bytes!` 済)。
- **EN**: `bundled-dicts` feature 有効化で cmudict JSON を staticlib に埋込む。
- **ZH**: `bundled-dicts` feature 有効化で pinyin JSON を staticlib に埋込む。
- **KO / ES / FR / PT / SV**: 規則ベース、追加データなし。

> JA naist-jdic 追加でバイナリサイズが ~25-30 MB 増えるため、サイズ制約のある consumer 向けに将来 **「JA を除いた lite slice」** を追加できる余地を残す (§7.4 参照)。

### 3.4 Chinese FFI 拡張

iOS で外部辞書ファイルを置けないため、`bundled-dicts` feature 経由で `ChinesePhonemizer::new_bundled()` を `register_one("zh")` から呼ぶ。実装は [`src/rust/piper-plus-g2p/src/ffi.rs`](../../src/rust/piper-plus-g2p/src/ffi.rs) の `register_one()` を参照。

### 3.5 Swift API

`Sources/PiperPlusG2P/` 配下の以下のファイルが API の定義 (実装が真):

| ファイル | 役割 |
|---------|------|
| [`Language.swift`](../../Sources/PiperPlusG2P/Language.swift) | 8 言語の enum (`ja`/`en`/`zh`/`ko`/`es`/`fr`/`pt`/`sv`) |
| [`G2PError.swift`](../../Sources/PiperPlusG2P/G2PError.swift) | エラー型。診断情報 (要求された言語 / 失敗した言語) を associated value で保持 |
| [`PhonemizeResult.swift`](../../Sources/PiperPlusG2P/PhonemizeResult.swift) | JSON envelope の Codable 受け先 |
| [`Phonemizer.swift`](../../Sources/PiperPlusG2P/Phonemizer.swift) | C FFI を包む `final class` (`@unchecked Sendable`) |
| [`PUAMap.swift`](../../Sources/PiperPlusG2P/PUAMap.swift) | PUA codepoint ⇔ multi-character token の対応 |

API/JSON envelope/ABI の規範は [`docs/spec/swift-g2p-contract.toml`](./swift-g2p-contract.toml) に集約。利用者向けの解説は [`docs/guides/swift-g2p-integration.md`](../guides/swift-g2p-integration.md)。

### 3.6 module.modulemap (xcframework 内)

```
module PiperPlusG2PBinary {
  umbrella header "piper_plus_g2p.h"
  export *
  module * { export * }
}
```

`piper_plus_g2p.h` は `cbindgen` で `ffi.rs` から自動生成 (release CI 内、設定は [`src/rust/piper-plus-g2p/cbindgen.toml`](../../src/rust/piper-plus-g2p/cbindgen.toml))。

---

## 4. 実装サマリ

各ファイルの内容は実コード/CI/manifest が真。本節は変更点の所在のみ示す。

| 領域 | 実体 |
|------|------|
| Rust crate `[lib]` 拡張 (`staticlib`/`cdylib`/`rlib`)、`bundled-dicts` feature | [`src/rust/piper-plus-g2p/Cargo.toml`](../../src/rust/piper-plus-g2p/Cargo.toml) |
| C ABI (5 関数)、Chinese embedded コンストラクタ、`default_languages()` | [`src/rust/piper-plus-g2p/src/ffi.rs`](../../src/rust/piper-plus-g2p/src/ffi.rs) |
| `cbindgen` 設定 | [`src/rust/piper-plus-g2p/cbindgen.toml`](../../src/rust/piper-plus-g2p/cbindgen.toml) |
| iOS / macOS slice 並列ビルド + xcframework アセンブリ | [`.github/workflows/release-shared-lib.yml`](../../.github/workflows/release-shared-lib.yml) (`build-g2p-apple` matrix + `assemble-g2p-xcframework`) |
| PR 自動検証 (macOS local build → `swift test`) | [`.github/workflows/swift-g2p-ci.yml`](../../.github/workflows/swift-g2p-ci.yml) |
| Swift Package 宣言 (`PiperPlusG2P` product, `binaryTarget`, `g2pVersion`/`g2pChecksum`) | [`Package.swift`](../../Package.swift) (release flow はファイル冒頭コメントを参照) |
| Swift wrapper 5 ファイル | [`Sources/PiperPlusG2P/`](../../Sources/PiperPlusG2P/) |
| XCTest 3 ファイル (Phonemizer / Concurrency / Golden) | [`tests/PiperPlusG2PTests/`](../../tests/PiperPlusG2PTests/) |
| 利用ガイド / consumer 向け FAQ | [`docs/guides/swift-g2p-integration.md`](../guides/swift-g2p-integration.md) |
| consumer サンプル (CLI) | [`examples/swift-g2p/HelloG2P/`](../../examples/swift-g2p/HelloG2P/) |
| 第三者ライセンス (cmudict / pinyin) | [`src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md`](../../src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md) |

リリース手順は [`Package.swift`](../../Package.swift) ファイル冒頭コメントに正本を置く (workflow_dispatch → checksum 計算 → Package.swift 更新 → tag push)。本仕様には複製しない。

---

## 5. 採用しなかった案

| 案 | 不採用理由 |
|----|-----------|
| **方針 2: Swift ネイティブ実装 (8 言語フル移植)** | 13,620 行の重複保守。jpreprocess の NAIST-JDIC 再実装 / pypinyin 互換コード / Hangul 分解規則が必要。Rust 側のバグ修正がそのまま Swift 側に反映されない drift リスク。学習・運用コストが過大。 |
| **方針 3: ハイブリッド (JA だけ OpenJTalk C 経由 + 他は Rust)** | Rust の jpreprocess が既に OpenJTalk 互換 + iOS で動作 (NAIST-JDIC 埋込済) のため、ハイブリッドの前提が崩れる。複数 binary 管理コスト増。 |
| **既存 `libpiper_plus.xcframework` に統合** | G2P 単独利用 (本 issue の主用途) で ORT (~31MB) を強制するためサイズ・依存が肥大。両方使う consumer は両 xcframework をリンクすれば済む。 |
| **CMake で iOS slice をビルド** | piper-plus-g2p は pure Rust + 規則・埋込辞書のみで C 依存がなく、CMake (fmt/spdlog/openjtalk のようなツリー) を通す必要がない。cargo 直 + lipo の方が単純。 |
| **`module.modulemap` を省略 (Bridging Header 方式)** | SPM `binaryTarget` は modulemap を要求。Bridging Header は Xcode プロジェクト個別設定でユーザー側手間が増える。 |
| **JA naist-jdic を別 xcframework に切り出し** | 本リリースでは見送り (lite/full 2 配布物の運用負荷)。サイズ 30MB 増は許容範囲、必要が出たら §7.4 で対応。 |
| **WASM `@piper-plus/g2p` を Swift から呼ぶ** | iOS で WASM ランタイム (wasmer-swift 等) を組み込むのは過剰。pure Rust → C ABI が直接的かつ高速。 |
| **`UniFFI`** | 自動生成の Swift API は pretty だが、本ケースは関数 5 個の薄ラッパで十分。UniFFI ランタイム依存追加 (~数 MB) は割に合わない。手書き wrapper の方が軽量。 |

---

## 6. 拡張可能性

### 6.1 visionOS / Mac Catalyst slice
`Package.swift` の `platforms:` と CI matrix に追加するのみ。Rust の `aarch64-apple-visionos*` / `*-apple-ios-macabi` target で同じビルド経路。

### 6.2 Android 配布
同じ Rust ソースから `aarch64-linux-android` 等の target で `.so` を生成し AAR 化 (Issue #388 で別途対応済み)。

### 6.3 SSML サポート
Rust 側の `piper_plus_g2p::ssml` モジュール (既存) を ffi.rs に export 追加 → Swift wrapper でも `phonemizeSSML(_:)` を提供。本リリースでは見送り (G2P コアに集中)。

### 6.4 Lite slice (JA 除外) / 言語選択ビルド
バイナリサイズに敏感な consumer 向けに `libpiper_plus_g2p_lite-apple.xcframework.zip` (`--no-default-features --features english,spanish,french,portuguese`) を追加配布する選択肢。本リリースでは見送り、需要が出たら §3.1 のテーブルに lite slice を追加。

### 6.5 Phoneme ID encoding を Swift 側に開く
現在 Rust の `encode::tokens_to_ids()` は ffi.rs 未 export。将来 SwiftUI のリアルタイムプレビュー等で需要が出たら `piper_plus_g2p_encode()` を追加。

---

## 7. 関連リンク

- Issue #387: <https://github.com/ayutaz/piper-plus/issues/387>
- 利用ガイド: [`docs/guides/swift-g2p-integration.md`](../guides/swift-g2p-integration.md)
- ABI 契約: [`docs/spec/swift-g2p-contract.toml`](./swift-g2p-contract.toml)
- 既存 iOS 仕様: [`docs/spec/ios-shared-lib.md`](./ios-shared-lib.md)
- 既存 iOS ガイド: [`docs/guides/ios-integration.md`](../guides/ios-integration.md)
- piper-plus-g2p crate: [`src/rust/piper-plus-g2p/`](../../src/rust/piper-plus-g2p/)
- C FFI 実装: [`src/rust/piper-plus-g2p/src/ffi.rs`](../../src/rust/piper-plus-g2p/src/ffi.rs)
- 業界事例 (sherpa-onnx Swift): <https://github.com/k2-fsa/sherpa-onnx/blob/master/.github/workflows/build-xcframework.yaml>
- cbindgen: <https://github.com/mozilla/cbindgen>
- cargo iOS targets: <https://doc.rust-lang.org/rustc/platform-support.html#tier-2>

---

## Updating

本仕様を変更する場合:

1. **API 追加 (e.g. SSML)**: §3.5 と §4 を更新。`Package.swift` に新 product を足すか、既存 wrapper に method を足すかを判断。
2. **xcframework 構造を変える**: §3.1 と §3.2 を更新し `release-shared-lib.yml` の matrix を同期。
3. **言語デフォルトを変える** (例: lite slice 採用): §3.3 と §6.4 を更新。
4. **新 platform slice 追加** (visionOS / Mac Catalyst): §3.2 + §6.1 + `Package.swift platforms:` + release CI matrix を一括更新。
