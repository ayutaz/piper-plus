# Swift G2P 配布仕様

> **Version:** 1.0 (Draft)
> **Status:** Proposed
> **対象 Issue:** [#387](https://github.com/ayutaz/piper-plus/issues/387)
> **対象ファイル (新規/改修):**
> `src/rust/piper-plus-g2p/Cargo.toml`,
> `src/rust/piper-plus-g2p/src/ffi.rs`,
> `cmake/PiperPlusG2pShared.cmake` (新規) もしくは `release-shared-lib.yml` 内の Cargo ビルド,
> `Sources/PiperPlusG2P/` (新規),
> `Package.swift`,
> `.github/workflows/release-shared-lib.yml`,
> `docs/guides/swift-g2p-integration.md`

---

## 概要

本仕様は piper-plus を **Swift / iOS から G2P (Grapheme-to-Phoneme) として利用する** ための配布物・ビルド経路・公開 API を定義する。
合成エンジン本体 (`libpiper_plus.a` + ONNX Runtime) を組み込まずに、**G2P 単体**として 8 言語 (ja / en / zh / ko / es / fr / pt / sv) を Swift から呼べるようにする。

---

## 1. 背景と要件

### 1.1 ユースケース

| シナリオ | 必要機能 | ORT 依存 |
|---------|---------|----------|
| iOS アプリで piper-plus と組み合わせて TTS 合成 | 既存 `libpiper_plus.a` 内蔵 G2P で解決済 | あり |
| **iOS アプリで G2P 単体利用 (Issue #387)** | 文字列 → IPA トークン列 | **なし** |
| 単語のフリガナ付与 / 発音記号生成 | 同上 | なし |
| サードパーティ TTS と組合せ (例: AVSpeechSynthesizer の前処理) | 同上 | なし |
| 多言語ローカライズ補助ツール | 同上 | なし |

> Issue #387 の本文 (`Use case: iOS`) は短いが、Swift エコシステムには公式の多言語 G2P が乏しく、特に**規則ベースのみで動く ES/PT/FR/SV** および **辞書埋込済の JA / ZH / KO** をオフラインで提供できる価値は大きい。

### 1.2 既存資産

| 資産 | 状態 | 本仕様で利用 |
|------|------|-------------|
| `src/rust/piper-plus-g2p` (Rust crate, 13,620 行, 8 言語) | 公開済 (crates.io: `piper-plus-g2p`) | **基盤** |
| `src/rust/piper-plus-g2p/src/ffi.rs` (C ABI, 5 関数) | 既実装 | **ほぼそのまま流用** |
| `Sources/PiperPlus/PiperPlus.swift` (合成エンジン用 Swift wrapper, 18 行) | v1.13.0 公開 | 同 Package.swift に target 追加 |
| `cmake/ios.toolchain.cmake` | iOS arm64 + simulator universal 対応済 | 直接使用しない (Cargo 側で iOS target を指定) |
| `release-shared-lib.yml` の `build-ios` matrix | 2 slice (device / simulator) ビルド済 | 並列に G2P slice ジョブを追加 |

### 1.3 非目標

- **学習側 G2P (`src/python/g2p/`) との同期**: ランタイム G2P (Rust 実装) に閉じる。学習側 (Python) は scope 外。
- **PUA エンコード後の phoneme_ids 出力**: G2P は IPA トークン列を返すまでが責務 (既存 ffi.rs と同じ)。`phoneme_id_map` への変換は合成エンジンか consumer 側で行う。
- **macOS / visionOS / Mac Catalyst**: 本仕様は iOS のみ。将来 `Package.swift` の `platforms:` 拡張時に検討。
- **SSML パーサ**: Rust 側 `ssml` モジュールは別途公開。G2P レイヤでは生テキストを受ける。

---

## 2. 採用方針: Plan A — Rust FFI + Swift wrapper

### 2.1 アーキテクチャ

```
┌────────────────────────────────────────────────┐
│ Swift consumer (iOS app)                       │
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
│   G2PError.swift     (Error)                   │
│   PhonemizeResult.swift (Codable)              │
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
            zh: 静的 JSON 辞書 (CC-CEDICT 由来)
            ko/en/es/fr/pt/sv: 規則ベース
```

### 2.2 不変条件

- **C 依存なし**: `libpiper_plus_g2p.a` は Rust + 標準ライブラリのみ。OpenJTalk / mecab / espeak-ng への C 依存を持ち込まない。
- **ONNX Runtime 依存なし**: 合成エンジンと完全に独立。consumer は ORT を Embed & Sign せずに利用可。
- **既存 `libpiper_plus.a` との衝突なし**: シンボル名 `piper_plus_g2p_*` で名前空間分離済。両方をリンクしてもよい。
- **JSON I/F 維持**: `phonemize` 結果は既存 ffi.rs 同様 `{"tokens":[...],"language":".."}` 形式。後方互換のため Swift 側も同じ JSON を Codable で受ける。

---

## 3. アーキテクチャ詳細

### 3.1 配布構成

**xcframework は独立配布する** (`libpiper_plus.xcframework` には統合しない)。

| 配布物 | 中身 | サイズ目安 | 用途 |
|--------|------|-----------|------|
| `libpiper_plus-ios-v${VERSION}.xcframework.zip` (既存) | C++ 合成 + 内部 G2P + ORT 必須 | ~15 MB (zip) | 合成エンジン |
| **`libpiper_plus_g2p-apple-v${VERSION}.xcframework.zip` (新規, v1.14.0+)** | **Rust G2P のみ、ORT 不要** | **~3-5 MB (zip, 言語デフォルト構成)** | **G2P 単独** |

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

xcframework に同梱する Cargo features は **`all-languages`** 相当:

```
default = ["english", "chinese", "korean", "spanish", "french", "portuguese", "swedish"]
                                        + japanese (naist-jdic)
```

- **JA**: `naist-jdic` feature 有効化で NAIST-JDIC 辞書を staticlib に埋込む (Rust 側で `include_bytes!` 済)。これにより consumer 側で OpenJTalk 辞書をバンドルする必要がない。
- **ZH**: 静的 JSON 辞書 (CC-CEDICT 由来) を `include_str!` で埋込み済。
- **KO / EN / ES / FR / PT / SV**: 規則ベース、追加データなし。

> JA naist-jdic 追加でバイナリサイズが ~25-30 MB 増えるため、サイズ制約のある consumer 向けに将来 **「JA を除いた lite slice」** を追加できる余地を残す (§7.4 参照、本リリースでは未対応)。

### 3.4 Chinese FFI 拡張 (必須)

現行 `ffi.rs` の `register_one()` は中国語を **登録不可** にしている (辞書ファイルパスが必要なため):

```rust
#[cfg(feature = "chinese")]
"zh" => {
    return Err(crate::G2pError::Phonemize(
        "Chinese requires dictionary paths; use from_dicts() instead".into(),
    ));
}
```

iOS では辞書を埋込済 (静的 JSON) として扱うため、本仕様では:

1. `ChinesePhonemizer::new_embedded()` を追加 (内部の `include_str!` 済 JSON を使う pre-built コンストラクタ)。
2. `register_one("zh")` でこれを呼び出すように変更。
3. テスト: `ffi.rs` の `tests::test_ffi_create_with_chinese()` を追加。

> 既存の `ChinesePhonemizer::from_dicts(path1, path2)` は引き続き保持 (デスクトップ / 学習側で外部辞書を差し替える用途のため)。

### 3.5 Swift API 設計

`Sources/PiperPlusG2P/` 以下に以下のファイルを新規作成:

#### `Language.swift`

```swift
public enum Language: String, CaseIterable, Sendable {
    case japanese  = "ja"
    case english   = "en"
    case chinese   = "zh"
    case korean    = "ko"
    case spanish   = "es"
    case french    = "fr"
    case portuguese = "pt"
    case swedish   = "sv"
}
```

#### `G2PError.swift`

```swift
public enum G2PError: Error, Sendable, Equatable {
    case initializationFailed
    case phonemizeReturnedNull
    case invalidUTF8
    case decodeFailed(String)
}
```

> 実装: [`Sources/PiperPlusG2P/G2PError.swift`](../../Sources/PiperPlusG2P/G2PError.swift) と一致。
> ケースの意味:
> - `initializationFailed` — `piper_plus_g2p_create` が NULL を返した (要求した languages が一つも登録できなかった)。
> - `phonemizeReturnedNull` — `piper_plus_g2p_phonemize` が NULL を返した (init で登録されていない言語、または入力が phonemizer で解釈できない)。
> - `invalidUTF8` — FFI からの戻り値が UTF-8 として解釈できない (実装上は不到達)。
> - `decodeFailed(String)` — JSON envelope の Decodable 失敗 (Rust 側 envelope 変更の早期検出)。

#### `PhonemizeResult.swift`

```swift
public struct PhonemizeResult: Codable, Sendable {
    public let tokens: [String]
    public let language: String
}
```

#### `Phonemizer.swift`

```swift
public final class Phonemizer: @unchecked Sendable {
    private let handle: OpaquePointer

    public init(languages: [Language] = Language.allCases) throws {
        let csv = languages.map(\.rawValue).joined(separator: ",")
        guard let h = csv.withCString({ piper_plus_g2p_create($0) }) else {
            throw G2PError.initializationFailed
        }
        self.handle = OpaquePointer(h)
    }

    public func phonemize(_ text: String, language: Language) throws -> PhonemizeResult {
        let cString = try text.withCString { textPtr -> UnsafeMutablePointer<CChar>? in
            language.rawValue.withCString { langPtr in
                piper_plus_g2p_phonemize(.init(handle), textPtr, langPtr)
            }
        }
        guard let cString else { throw G2PError.nullResult }
        defer { piper_plus_g2p_free_string(cString) }

        let json = String(cString: cString).data(using: .utf8) ?? Data()
        return try JSONDecoder().decode(PhonemizeResult.self, from: json)
    }

    public var availableLanguages: [Language] {
        guard let cString = piper_plus_g2p_available_languages(.init(handle)) else { return [] }
        defer { piper_plus_g2p_free_string(cString) }
        return String(cString: cString)
            .split(separator: ",")
            .compactMap { Language(rawValue: String($0)) }
    }

    deinit {
        piper_plus_g2p_free(.init(handle))
    }
}
```

#### `module.modulemap` (xcframework 内)

```
module PiperPlusG2PBinary {
  umbrella header "piper_plus_g2p.h"
  export *
  module * { export * }
}
```

`piper_plus_g2p.h` は Rust の `cbindgen` で `ffi.rs` から自動生成する (§4.2)。

---

## 4. 実装スコープ

### 4.1 `src/rust/piper-plus-g2p/Cargo.toml`

```toml
[lib]
crate-type = ["staticlib", "cdylib", "rlib"]
```

を追加。`staticlib` で iOS 向け `.a` を生成、`rlib` は既存の Rust consumer 用 (crates.io 経由) を維持、`cdylib` はデスクトップでの動的リンクと将来の Android 用。

> 注: 現状 Cargo.toml に `[lib]` セクションは無く、暗黙的に `rlib` のみ。**追加変更は最小限** (1 ブロックのみ)。

### 4.2 `cbindgen.toml` (新規)

`src/rust/piper-plus-g2p/cbindgen.toml`:

```toml
language = "C"
header = "/* SPDX-License-Identifier: MIT */\n/* Auto-generated by cbindgen — do not edit by hand. */"
include_guard = "PIPER_PLUS_G2P_H"
sys_includes = ["stdint.h", "stddef.h"]

[export]
include = [
  "PiperG2pHandle",
  "piper_plus_g2p_create",
  "piper_plus_g2p_phonemize",
  "piper_plus_g2p_available_languages",
  "piper_plus_g2p_free_string",
  "piper_plus_g2p_free",
]

[parse]
parse_deps = false
```

CI (`release-shared-lib.yml`) の `build-g2p-ios` ステップ内で `cbindgen --config cbindgen.toml --crate piper-plus-g2p --output piper_plus_g2p.h` を実行。

### 4.3 `src/rust/piper-plus-g2p/src/ffi.rs` 修正

1. **Chinese 登録対応** (§3.4): `ChinesePhonemizer::new_embedded()` を呼ぶよう `register_one("zh")` を変更。
2. **Japanese 登録**: `register_one("ja")` で `JapanesePhonemizer::new()?` を呼ぶ部分は既に存在 (`#[cfg(feature = "japanese")]` 付き)。`naist-jdic` feature 同時有効化で NAIST-JDIC 埋込辞書を使うことを README に明記。

### 4.4 iOS ビルド経路: cargo + lipo (CMake は使わない)

合成エンジン側 (`libpiper_plus.a`) は CMake で iOS toolchain を使うが、**G2P 側は cargo 単独で iOS 向けにクロスコンパイルする**:

```bash
# device slice (arm64)
cargo build --manifest-path src/rust/piper-plus-g2p/Cargo.toml \
  --release --target aarch64-apple-ios \
  --features all-languages,naist-jdic,bundled-dicts,ffi

# simulator slice (arm64 + x86_64) — 個別ビルド後 lipo で合成
cargo build --manifest-path src/rust/piper-plus-g2p/Cargo.toml \
  --release --target aarch64-apple-ios-sim \
  --features all-languages,naist-jdic,bundled-dicts,ffi
cargo build --manifest-path src/rust/piper-plus-g2p/Cargo.toml \
  --release --target x86_64-apple-ios \
  --features all-languages,naist-jdic,bundled-dicts,ffi
lipo -create \
  target/aarch64-apple-ios-sim/release/libpiper_plus_g2p.a \
  target/x86_64-apple-ios/release/libpiper_plus_g2p.a \
  -output build-g2p-ios-sim/libpiper_plus_g2p.a
```

> 理由: piper-plus-g2p は pure Rust + 標準ライブラリのみで、CMake / OpenJTalk / fmt / spdlog のような C++ 依存ツリーを通す必要がない。cargo 直 + lipo の方が遥かに単純で速い (~30 秒 / slice)。
> 関連業界事例: sherpa-onnx は cargo build + xcodebuild -create-xcframework パターンを採用。

### 4.5 `.github/workflows/release-shared-lib.yml` 拡張

`build-ios` matrix 完了後、別 matrix `build-g2p-apple` を追加し、最後に `assemble-g2p-xcframework` で `xcodebuild -create-xcframework` を実行。

> 当初のジョブ名は `build-g2p-ios` だったが、v1.14.0 で macOS slice を追加した際 `build-g2p-apple` に rename。同時に xcframework artifact 名も `libpiper_plus_g2p-ios-` から `libpiper_plus_g2p-apple-` へ変更。

```yaml
build-g2p-apple:
  name: Build piper-plus-g2p Apple ${{ matrix.slice }}
  runs-on: macos-15
  timeout-minutes: 25
  strategy:
    fail-fast: false
    matrix:
      include:
        - slice: ios-arm64
          rust_targets: "aarch64-apple-ios"
        - slice: ios-arm64_x86_64-simulator
          rust_targets: "aarch64-apple-ios-sim,x86_64-apple-ios"
        - slice: macos-arm64_x86_64
          rust_targets: "aarch64-apple-darwin,x86_64-apple-darwin"
  steps:
    - uses: actions/checkout@v6
    - uses: dtolnay/rust-toolchain@stable
      with:
        targets: ${{ matrix.rust_targets }}
    - name: Install cbindgen
      run: cargo install cbindgen --locked
    - name: Build slice (cargo + lipo)
      working-directory: src/rust/piper-plus-g2p
      run: |
        IFS=',' read -ra TGT <<< "${{ matrix.rust_targets }}"
        for t in "${TGT[@]}"; do
          cargo build --release --target "$t" \
            --features all-languages,naist-jdic,bundled-dicts,ffi
        done
        # …lipo logic here for simulator slice…
    - name: Generate piper_plus_g2p.h
      working-directory: src/rust/piper-plus-g2p
      run: cbindgen --config cbindgen.toml --crate piper-plus-g2p --output piper_plus_g2p.h
    - name: Stage slice for xcframework
      run: |
        mkdir -p slice-out/lib slice-out/include
        cp build-g2p-ios/libpiper_plus_g2p.a slice-out/lib/
        cp src/rust/piper-plus-g2p/piper_plus_g2p.h slice-out/include/
        cat > slice-out/include/module.modulemap <<'EOF'
        module PiperPlusG2PBinary {
          umbrella header "piper_plus_g2p.h"
          export *
          module * { export * }
        }
        EOF
    - uses: actions/upload-artifact@v4
      with:
        name: piper-plus-g2p-slice-${{ matrix.slice }}
        path: slice-out/

assemble-g2p-xcframework:
  needs: build-g2p-apple
  runs-on: macos-15
  steps:
    - uses: actions/download-artifact@v4
    - run: |
        xcodebuild -create-xcframework \
          -library piper-plus-g2p-slice-ios-arm64/lib/libpiper_plus_g2p.a \
            -headers piper-plus-g2p-slice-ios-arm64/include \
          -library piper-plus-g2p-slice-ios-arm64_x86_64-simulator/lib/libpiper_plus_g2p.a \
            -headers piper-plus-g2p-slice-ios-arm64_x86_64-simulator/include \
          -library piper-plus-g2p-slice-macos-arm64_x86_64/lib/libpiper_plus_g2p.a \
            -headers piper-plus-g2p-slice-macos-arm64_x86_64/include \
          -output piper_plus_g2p.xcframework
        zip -ry libpiper_plus_g2p-apple.xcframework.zip piper_plus_g2p.xcframework
    - uses: actions/upload-artifact@v4
      with:
        name: libpiper_plus_g2p-apple-xcframework
        path: libpiper_plus_g2p-apple.xcframework.zip
```

### 4.6 `Package.swift` 拡張

```swift
// G2P xcframework debuts in v1.14.0 (Issue #387) — one tag after the
// synthesis xcframework which shipped at v1.13.0 (Issue #377). Update
// `g2pChecksum` manually before each tag push, same flow as PiperPlusBinary.
let g2pVersion = "1.14.0"
let g2pChecksum = "0000…0000"  // placeholder until v1.14.0 release tag

let package = Package(
    name: "PiperPlus",
    // macOS が必要なのは G2P xcframework に macos slice が含まれるため
    // (v1.14.0+)。PiperPlus (合成エンジン) は実質 iOS-only。
    platforms: [.iOS(.v15), .macOS(.v13)],
    products: [
        .library(name: "PiperPlus",    targets: ["PiperPlus"]),
        .library(name: "PiperPlusG2P", targets: ["PiperPlusG2P"]),  // ← 新規
    ],
    dependencies: [ /* …onnxruntime SPM as today… */ ],
    targets: [
        // 既存
        .target(name: "PiperPlus", dependencies: […], path: "Sources/PiperPlus"),
        .binaryTarget(name: "PiperPlusBinary", url: …, checksum: …),
        // 新規
        .target(
            name: "PiperPlusG2P",
            dependencies: [.target(name: "PiperPlusG2PBinary")],
            path: "Sources/PiperPlusG2P"
        ),
        .binaryTarget(
            name: "PiperPlusG2PBinary",
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(g2pVersion)/libpiper_plus_g2p-apple-v\(g2pVersion).xcframework.zip",
            checksum: g2pChecksum
        ),
    ]
)
```

> consumer は `.product(name: "PiperPlusG2P", package: "piper-plus")` だけを宣言すれば G2P のみ pull (ORT 不要)。

### 4.7 リリース手順 (Maintainer)

1. `dev` で `release-shared-lib.yml` を `workflow_dispatch` 実行 (no tag) → `libpiper_plus_g2p-apple.xcframework.zip` artifact が出る。
2. `swift package compute-checksum libpiper_plus_g2p-apple.xcframework.zip` でチェックサム計算。
3. `Package.swift` の `g2pChecksum` と `g2pVersion` を更新。
4. `chore(spm): bump PiperPlusG2P to v${VERSION}` でコミット → tag push。
5. release ジョブが `libpiper_plus_g2p-apple-v${VERSION}.xcframework.zip` を Releases に publish。

> 既存 `PiperPlusBinary` のチェックサム検証ロジック (sha256 突合) は `PiperPlusG2PBinary` にも適用する。release ジョブの guard を拡張。

### 4.8 ドキュメント

- `docs/guides/swift-g2p-integration.md` (本仕様と対の利用ガイド) を新規作成。
- `docs/guides/ios-integration.md` の「Step 5: Use from Your Language」§ Swift に "G2P 単体利用は別 product `PiperPlusG2P` を参照" のリンクを追加。
- `README.md` の「ランタイム別パッケージ」テーブルに Swift 行を追加 (現在は記載なし)。
- `CHANGELOG.md` に v1.14.0 (or 該当バージョン) で feature 追加を記述。

### 4.9 テスト

| 層 | テスト |
|----|-------|
| Rust ffi.rs | 既存 `tests::test_ffi_*` を Chinese 用に拡張 (§3.4) |
| Rust integration | `cargo test --features all-languages,naist-jdic` がローカルとCIで pass |
| iOS slice ビルド | `release-shared-lib.yml` の `build-g2p-ios` 各 slice が成功 |
| xcframework アセンブリ | `xcodebuild -create-xcframework` 成功 + `lipo -archs` 確認 |
| Swift wrapper | `Tests/PiperPlusG2PTests/` 新規 (XCTest 8 ケース最低限: 各言語 1 ケース + エラー系) |
| End-to-end (例) | `examples/swift/G2PExample/` を新規作成 (オプション、別 issue に分離可) |

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

## 6. リスクと対応

| リスク | 確度 | 影響 | 対応 |
|--------|------|------|------|
| `staticlib` 追加で既存 Rust consumer (crates.io 経由 rlib) のビルドが影響 | 低 | 中 | `crate-type = ["staticlib", "cdylib", "rlib"]` で `rlib` を保持。crates.io publish 時の挙動は同等。 |
| naist-jdic 埋込でバイナリサイズ +25-30MB | 中 | 中 | iOS の通常アプリでは許容範囲 (App Clip 10MB 制約は元々 piper-plus 全体で超過)。サイズ問題が出たら §7.4 lite slice 検討。 |
| cbindgen 自動生成ヘッダと手書き modulemap の食い違い | 中 | 中 | CI で `piper_plus_g2p.h` の export シンボルと modulemap の `umbrella header` 記述を 1 ファイル名に統一。 release 前に `swift build` を CI で走らせて結合検証。 |
| Rust 1.x 系で iOS-sim target が rustup 未配布になる | 低 | 高 | `aarch64-apple-ios-sim` は Rust 1.71+ で安定。`rust-toolchain.toml` で MSRV を明示し、release 用 toolchain を pin。 |
| Swift 5.9 未満の consumer | 低 | 中 | `Package.swift` で `swift-tools-version: 5.9` 明示 (既存と同じ)。Swift 5.9 = Xcode 15+。`docs/guides/swift-g2p-integration.md` で前提を明記。 |
| Microsoft が onnxruntime SPM パッケージ依存 (合成側) を破壊 | 低 | 既存と同じ | G2P 側は ORT 非依存なので独立に動く。むしろメリット。 |
| Chinese FFI 拡張で既存の `from_dicts(path1, path2)` API が壊れる | 低 | 中 | `new_embedded()` を別コンストラクタとして追加 (既存 API 非破壊)。テスト追加。 |
| ja 用 `naist-jdic` feature でクロスコンパイル時に `bincode` 互換性問題 | 中 | 中 | jpreprocess + bincode は v0.9 で iOS arm64 動作確認実績あり (関連 PR の CI ログで確認可)。失敗時は jpreprocess バージョン pin。 |
| `cargo install cbindgen` が CI で遅い (~2 分) | 低 | 低 | runner キャッシュ (`actions/cache`) で `~/.cargo/bin/cbindgen` を pin。 |

---

## 7. 拡張可能性

### 7.1 macOS / visionOS slice 追加
`Package.swift` の `platforms:` と CI matrix に追加するのみ。Rust の `aarch64-apple-darwin` / `x86_64-apple-darwin` / `aarch64-apple-visionos*` target で同じビルド経路。

### 7.2 Android 配布
同じ Rust ソースから `aarch64-linux-android` 等の target で `.so` を生成し AAR 化。本仕様の範囲外だが基盤は再利用可。

### 7.3 SSML サポート
Rust 側の `piper_plus_g2p::ssml` モジュール (既存) を ffi.rs に export 追加 → Swift wrapper でも `phonemizeSSML(_:)` を提供。本リリースでは見送り (G2P コアに集中)。

### 7.4 Lite slice (JA 除外) / 言語選択ビルド
バイナリサイズに敏感な consumer 向けに `libpiper_plus_g2p_lite-ios.xcframework.zip` (`--no-default-features --features english,spanish,french,portuguese`) を追加配布する選択肢。本リリースでは見送り、需要が出たら §3.1 のテーブルに lite slice を追加。

### 7.5 Phoneme ID encoding を Swift 側に開く
現在 Rust の `encode::tokens_to_ids()` は ffi.rs 未 export。将来 SwiftUI のリアルタイムプレビュー等で需要が出たら `piper_plus_g2p_encode()` を追加。

---

## 8. 関連リンク

- Issue #387: <https://github.com/ayutaz/piper-plus/issues/387>
- 既存 Swift Package (合成): [Package.swift](../../Package.swift), [Sources/PiperPlus/](../../Sources/PiperPlus/)
- 既存 iOS 仕様: [docs/spec/ios-shared-lib.md](./ios-shared-lib.md)
- 既存 iOS ガイド: [docs/guides/ios-integration.md](../guides/ios-integration.md)
- piper-plus-g2p crate: [src/rust/piper-plus-g2p/](../../src/rust/piper-plus-g2p/)
- C FFI 実装: [src/rust/piper-plus-g2p/src/ffi.rs](../../src/rust/piper-plus-g2p/src/ffi.rs)
- 業界事例 (sherpa-onnx Swift): <https://github.com/k2-fsa/sherpa-onnx/blob/master/.github/workflows/build-xcframework.yaml>
- cbindgen: <https://github.com/mozilla/cbindgen>
- cargo iOS targets: <https://doc.rust-lang.org/rustc/platform-support.html#tier-2>

---

## Updating

本仕様を変更する場合:

1. **API 追加 (e.g. SSML)**: §3.5 と §4.3, §4.6 を更新。`Package.swift` に新 product を足すか、既存 wrapper に method を足すかを判断。
2. **xcframework 構造を変える**: §3.1 と §3.2 を更新し `release-shared-lib.yml` の matrix を同期。
3. **言語デフォルトを変える** (例: lite slice 採用): §3.3 と §7.4 を更新。
4. **macOS / visionOS slice 追加**: §3.2 + §7.1 + `Package.swift platforms:` + release CI matrix を一括更新。
