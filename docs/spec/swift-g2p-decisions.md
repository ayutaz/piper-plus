# Swift G2P — Pre-Implementation Decision Items

> **Status:** Open — decisions required before [Issue #387](https://github.com/ayutaz/piper-plus/issues/387) implementation begins
> **Companion:** [docs/spec/swift-g2p.md](./swift-g2p.md), [docs/guides/swift-g2p-integration.md](../guides/swift-g2p-integration.md)
> **Last updated:** 2026-05-05

実装着手前に決めるべき事項を網羅的に整理する。各項目に **選択肢 / 推奨 / 理由** を記載。
未決定 (`UNDECIDED`) の項目はオーナーの判断が必要。

---

## ⚠️ 重大な盲点 (調査で発覚)

仕様書 (`swift-g2p.md`) では「Rust G2P は iOS で pure Rust + 標準ライブラリのみ」と書いたが、**English と Chinese の辞書は現状ディスクファイル依存**で、iOS App Sandbox では動作しない:

| 言語 | 辞書 | サイズ | 現状 | iOS 対応 |
|------|------|-------|------|---------|
| JA | NAIST-JDIC | ~25 MB | `naist-jdic` feature で **embedded** ✓ | OK |
| EN | `cmudict_data.json` | 3.7 MB | `EnglishPhonemizer::new()` が `./cmudict_data.json` を disk から読む | **要対応** |
| ZH | `pinyin_single.json` + `pinyin_phrases.json` | 2.7 MB | `ChinesePhonemizer::new(path1, path2)` が disk から読む | **要対応** |
| KO/ES/FR/PT/SV | (なし、規則ベース) | 0 | 規則のみ | OK |

→ **D-2 (辞書埋込戦略)** を最優先で決定する必要あり。これが決まらないと Cargo.toml と FFI の実装手順が固まらない。

---

## D-1. パッケージ命名

| 項目 | 選択肢 | **推奨** | 理由 |
|------|--------|---------|------|
| Swift product 名 | `PiperPlusG2P` / `PiperG2P` / `PiperPlus.G2P` | **`PiperPlusG2P`** | 既存 `PiperPlus` (合成エンジン) と命名整合 |
| Swift target 名 (wrapper) | 同上 | `PiperPlusG2P` | product と同名 |
| Swift binaryTarget 名 | `PiperPlusG2PBinary` / `PiperPlusG2PFramework` | **`PiperPlusG2PBinary`** | 既存 `PiperPlusBinary` と命名整合 |
| C ヘッダ名 | `piper_plus_g2p.h` / `pp_g2p.h` | **`piper_plus_g2p.h`** | 既存 `piper_plus.h` と整合 |
| C 関数 prefix | (既存 `piper_plus_g2p_*`) | **維持** | 既に publish 済の Rust crate ABI |
| xcframework zip 名 | `libpiper_plus_g2p-ios-v${VERSION}.xcframework.zip` | **これ** | 既存 `libpiper_plus-ios-v${VERSION}.xcframework.zip` と整合 |
| modulemap 内 module 名 | `PiperPlusG2P` / `PiperPlusG2PBinary` | **`PiperPlusG2PBinary`** | binaryTarget 名と一致させる (Swift 側 wrapper が `@_exported import` で再 export) |

---

## D-2. 辞書埋込戦略 (最重要)

iOS では disk path 依存が機能しないため、英語 / 中国語の辞書を Rust crate にどう同梱するか決める必要がある。

### 選択肢

#### Option A: `bundled-dicts` feature を新設し `include_str!` / `include_bytes!`

```rust
// src/rust/piper-plus-g2p/src/english.rs
#[cfg(feature = "bundled-dicts")]
const CMU_DICT_JSON: &str = include_str!("../data/cmudict_data.json");

#[cfg(feature = "bundled-dicts")]
impl EnglishPhonemizer {
    pub fn new_bundled() -> Result<Self, G2pError> {
        let dict: HashMap<String, String> = serde_json::from_str(CMU_DICT_JSON)?;
        Ok(Self::new_with_hashmap(dict))
    }
}
```

| Pros | Cons |
|------|------|
| 単一 `.a` ファイル、ランタイム I/O 不要 | バイナリサイズ +6.5 MB (cmudict + pinyin) |
| `Bundle.main.path(forResource:)` 不要、Swift API シンプル | 辞書を更新するたびに crate 再ビルド要 |
| 既存 jpreprocess の `naist-jdic` パターンと一貫性 | crate ソースツリーに `data/` ディレクトリ追加要 |

#### Option B: SPM resources として bundle に埋込み、Swift 側で `Bundle.module` から読込み

```swift
public init() throws {
    let url = Bundle.module.url(forResource: "cmudict_data", withExtension: "json")!
    let data = try Data(contentsOf: url)
    // ... 内部で from_json_bytes() を呼ぶ
}
```

| Pros | Cons |
|------|------|
| バイナリサイズが分離 (zip 圧縮効率高) | SPM の `resources:` 機構と binaryTarget の組合せが複雑 |
| 辞書だけ別配信可能 | C FFI と Swift Bundle の橋渡しが必要 |
| Cargo features 操作不要 | `from_json_bytes` 互換 API を English にも追加要 (現状 Chinese のみ存在) |

#### Option C: ハイブリッド (デフォルト埋込、サイズ重視 lite slice で除外)

A をデフォルトにしつつ、`--no-default-features --features english,spanish,french,portuguese,swedish` ビルドの lite slice を別途配布。

| Pros | Cons |
|------|------|
| 大半の consumer は何も考えずに動く | 配布物が 2 系統 (full / lite) に増える |
| サイズ制約のある App Clip 等で lite slice 選択可 | リリースワークフローが複雑化 |

### 推奨

**Option A (`bundled-dicts` feature 新設) で開始**。lite slice は §7.4 (将来検討) に温存。

理由:
- iOS xcframework は consumer 側で言語選択不可なので、デフォルト全部入りが現実的
- 既に `naist-jdic` feature が同じパターンで成功している
- バイナリ全体 ~35 MB は piper-plus 合成エンジン (~31MB ORT + 15MB libpiper_plus) と同程度、許容範囲
- App Clip 不可は元々 piper-plus エコシステム全体で同じ制約

### 必要な実装作業

1. `src/rust/piper-plus-g2p/data/` 新規作成
2. `cmudict_data.json` / `pinyin_single.json` / `pinyin_phrases.json` を `src/cpp/` から `data/` にコピーまたは symlink (DRY 違反は build script で解決)
3. `Cargo.toml` に `bundled-dicts = []` feature 追加 (default に入れるか、`all-languages` 経由で入るかは判断)
4. `english.rs` に `new_bundled()` 追加 (`#[cfg(feature = "bundled-dicts")]`)
5. `chinese.rs` に `new_bundled()` 追加 (同上)
6. `ffi.rs::register_one()` で `bundled-dicts` feature 時に `new_bundled()` を呼ぶ分岐追加

> **`UNDECIDED`**: `bundled-dicts` を **default features に含めるか**? 含めると crates.io 経由の Rust consumer も常に +6.5 MB を背負う。**推奨**: feature flag 維持、iOS ビルド時のみ `--features bundled-dicts,naist-jdic` で有効化。

---

## D-3. バージョニング戦略

| 項目 | 選択肢 | **推奨** |
|------|-------|---------|
| Cargo crate `piper-plus-g2p` のバージョン | 0.4.x 維持 / 1.0.0 にバンプ | **0.5.0** (`bundled-dicts`, `staticlib` 追加で minor bump) |
| Swift package version | piper-plus 全体と同期 (`1.14.0`) / 独立 | **同期** (CHANGELOG が 1 系列で済む) |
| `naist-jdic` feature を default に追加するか | yes / no | **no** (現状維持。crates.io 利用者の選択を尊重) |
| `bundled-dicts` を default に追加するか | yes / no | **no** (上と同じ理由、iOS ビルド時のみ enable) |

---

## D-4. xcframework 配布形態

| 項目 | 選択肢 | **推奨** | 理由 |
|------|-------|---------|------|
| 既存 `libpiper_plus.xcframework` と統合か独立か | 統合 / 独立 | **独立** | G2P 単独利用時に ORT 30MB を強制したくない |
| Lite slice (JA 除く) の同時提供 | yes / no | **no (初版)** | 配布物 2 系統は運用負荷高、需要発生後に検討 |
| macOS / visionOS slice 同時提供 | yes / no | **no (初版)** | 段階リリース。需要次第で §7.1 拡張 |
| Universal slice (device+sim 1 ファイル) | xcframework / fat archive | **xcframework** | App Store の要求に合致、既存パターンと一致 |

---

## D-5. Cargo features 構成

| 項目 | 選択肢 | **推奨** |
|------|-------|---------|
| iOS ビルド時の features | `default,japanese,naist-jdic,bundled-dicts` / `all-languages,naist-jdic,bundled-dicts` | **`all-languages,naist-jdic,bundled-dicts`** (明示的に全有効化) |
| consumer 向けに features を露出 | yes (Swift trait) / no | **no** | binaryTarget は ABI 固定、Swift 側からビルド時 features は変更不可 |
| `ffi` feature を実際に使うか | enable on iOS / always-on | **always-on** | 現状 ffi.rs は無条件ビルド済、`ffi` feature は未使用フラグ。本リリースで除去するか維持するかは別途判断 |

---

## D-6. Chinese FFI 拡張の実装ディテール

§3.4 で「`ChinesePhonemizer::new_embedded()` を追加して `register_one("zh")` から呼ぶ」と書いたが、より具体的に:

### 案

```rust
// chinese.rs
#[cfg(feature = "bundled-dicts")]
impl ChinesePhonemizer {
    pub fn new_bundled() -> Result<Self, G2pError> {
        const SINGLE: &[u8] = include_bytes!("../data/pinyin_single.json");
        const PHRASE: &[u8] = include_bytes!("../data/pinyin_phrases.json");
        Self::from_json_bytes(SINGLE, PHRASE)
    }
}

// ffi.rs
#[cfg(all(feature = "chinese", feature = "bundled-dicts"))]
"zh" => {
    registry.register("zh", Box::new(crate::chinese::ChinesePhonemizer::new_bundled()?));
}
#[cfg(all(feature = "chinese", not(feature = "bundled-dicts")))]
"zh" => {
    return Err(crate::G2pError::Phonemize(
        "Chinese requires bundled-dicts feature or use from_dicts() directly".into(),
    ));
}
```

### `UNDECIDED` 項目

- **既存 `ChinesePhonemizer::new(path1, path2)` を保持するか?**
  - Pro: デスクトップ用途で外部辞書差し替え可能
  - Con: iOS では到達しない死コード
  - **推奨**: 保持 (デスクトップ単体テストで使われている)

---

## D-7. JSON I/F の維持判断

現行 FFI: `phonemize` は `{"tokens": [...], "language": ".."}` 形式の JSON を返す。

### 選択肢

| 案 | Pros | Cons |
|----|------|------|
| **JSON 維持 (推奨)** | 既存 ABI 互換、Codable で自然 | UTF-8 → JSON parse のオーバーヘッド (μs オーダー) |
| binary struct を返す (新 API 追加) | 高速、メモリ効率良い | C struct + 複雑なメモリ管理、wrapper 工数大 |
| バッファに書く API (`piper_plus_g2p_phonemize_into`) | ゼロコピー可能 | API 複雑化、エラーハンドリング難 |

### 推奨

**JSON 維持**。Swift 側 `JSONDecoder` は十分高速 (~100 μs/call、テキスト 1 文長で問題なし)。リアルタイムで毎フレーム呼ぶ用途は想定しない。

---

## D-8. Prosody 情報の露出

Rust 側 `phonemize_with_prosody()` は (tokens, prosody_info) を返すが、現行 FFI は tokens のみを JSON に含める。

| 選択肢 | 推奨 |
|-------|------|
| 初版で prosody は出さない | **これ** |
| JSON に prosody フィールドを追加 (後方互換) | 将来検討 |

理由: Swift G2P の主用途は IPA token 列生成。prosody は piper-plus 合成エンジン内部で消費される情報で、外部 consumer の需要は低い。需要発生時に JSON フィールド追加で対応可 (後方互換)。

---

## D-9. ライセンス・帰属表示

xcframework に同梱した辞書のライセンスをどう consumer に伝えるか。

| 辞書 | ライセンス | 帰属表示の必要性 |
|------|----------|---------------|
| NAIST-JDIC | BSD-3-Clause | App ライセンス画面に "NAIST-JDIC" 表示推奨 |
| CMU Pronouncing Dictionary | BSD-2-Clause | 同上 |
| pinyin (CC-CEDICT 派生) | CC BY-SA 4.0 | **必須** — Share-Alike 義務の解釈に注意 |

### `UNDECIDED`

- **CC BY-SA 4.0 の Share-Alike 義務をどう解釈するか?**
  - 純粋に「同じライセンスで再配布」なら、辞書のみ別 zip にして元ライセンスのまま配布する方が clean
  - 一般的な解釈: 辞書由来の派生物を再配布する場合、その派生部分を CC BY-SA で公開すれば足りる (consumer のアプリ全体に伝播しない)
  - 法務確認したいなら別途 issue 化

### 対応案

1. xcframework root に `LICENSE-THIRD-PARTY.txt` を同梱 (NAIST-JDIC / CMU / CC-CEDICT 全文)
2. `docs/guides/swift-g2p-integration.md` に Acknowledgements 雛形を提供 (consumer がコピペ可能)
3. README に "App ライセンス画面に表示推奨" を明記

---

## D-10. テスト戦略

| テスト層 | 内容 | 必須? |
|---------|------|------|
| Rust unit (既存) | `cargo test --features all-languages,naist-jdic,bundled-dicts` | 必須 |
| Rust FFI (既存 + 拡張) | `tests::test_ffi_*` に Chinese ケース追加 | 必須 |
| iOS slice ビルド成功 | `release-shared-lib.yml` の `build-g2p-ios` matrix が pass | 必須 |
| xcframework アセンブリ | `xcodebuild -create-xcframework` 成功 | 必須 |
| Swift wrapper unit | `Tests/PiperPlusG2PTests/` の XCTest (各言語 1 ケース + エラー系) | 必須 |
| Cross-runtime golden | 8 言語 × 5 テストフレーズ で Python/Rust/Swift の token 列一致 | **`UNDECIDED`** |
| iOS Simulator E2E | CI で simulator 起動して例題実行 | 推奨 |
| パフォーマンスベンチ | P95 latency < 50ms / 100 char | 推奨 |
| メモリプロファイル | App 起動時の peak RSS | 推奨 |

### `UNDECIDED`

- **Cross-runtime golden test のスコープ**
  - 既に Python/Rust/Go/JS で同等の実装があり、フレーズ単位で一致を確認すべき
  - 既存の `docs/spec/*-contract.toml` パターンを踏襲し `docs/spec/swift-g2p-contract.toml` を追加するか?
  - **推奨**: 別 PR / 別 issue で対応 (本 issue の scope 拡大を防ぐ)

---

## D-11. CI コスト・運用

| 項目 | 影響 | 対応 |
|------|------|------|
| `macos-15` runner 追加マトリクス (×2 slice) | release 時間 +5-10 分、課金 +$0.16/run (2 slice × 20 分 × $0.08/min) | 許容 |
| PR ごとに iOS G2P ビルドする? | PR スループット低下 | **tag 時のみ** にする提案、PR では Rust unit + ffi.rs ユニットテストのみ |
| cbindgen のキャッシュ | `actions/cache` で `~/.cargo/bin/cbindgen` を pin | 必須 |
| `Package.swift` checksum 計算は dev で手動か CI で自動か | 既存パターンは手動 (release 前に maintainer が計算) | **手動維持** (既存と同じ) |

---

## D-12. ドキュメント・サンプル

| 項目 | 選択肢 | **推奨** |
|------|-------|---------|
| `examples/swift/G2PExample/` を作る? | 本 issue 内 / 別 issue | **別 issue** に切り出し (UI 含む実例は scope が広がる) |
| README.md の「ランタイム別パッケージ」テーブル更新 | 必須 | Swift 行を追加 (合成 + G2P を別行) |
| `docs/migration/` エントリ | 不要 | 純粋な機能追加、後方互換破壊なし |
| `CHANGELOG.md` エントリ | 必須 | v1.14.0 (or 該当版) で `feat(swift): G2P 単独利用 SPM product 追加 (#387)` |
| 命名一貫性: `g2p` vs `G2P` vs `GraphemeToPhoneme` | 既存 G2P で統一 | docs / API でも `G2P` 大文字を維持 |

---

## D-13. Issue / PR 管理

| 項目 | 推奨 |
|------|------|
| Issue クローズ条件 | xcframework 配信 + Package.swift で SPM resolve 可能になった時点 |
| Sub-issue 切出し候補 | (1) cross-runtime golden test、(2) Swift G2P サンプルアプリ、(3) macOS slice 追加、(4) lite slice 追加 |
| ラベル | 既存 `enhancement` に加え `swift` `ios` `g2p` を新設 |
| PR 分割 | **複数 PR** 推奨: ① Rust crate (bundled-dicts feature + new_bundled API)、② FFI 拡張 + cbindgen、③ Package.swift + Swift wrapper、④ CI 拡張、⑤ docs |
| PR にマイルストーン番号入れない | (user preference) |

---

## D-14. App Store / Privacy

| 項目 | 状態 |
|------|------|
| `PrivacyInfo.xcprivacy` (xcframework root) | 既存 `cmake/PrivacyInfo.xcprivacy` を流用 (Required Reason API なし、空の宣言) |
| Required Reason API 利用 | **なし** (file path 読込なし、システム時刻取得なし) |
| `ITSAppUsesNonExemptEncryption` | consumer の `Info.plist` 側で `false` 推奨 (G2P は暗号化不使用) |

---

## D-15. リスク受容判断

| リスク | 影響 | 受容? |
|--------|------|------|
| バイナリ +35 MB (NAIST-JDIC + CMU + pinyin) | App Clip 不可、通常アプリは OK | **受容** |
| jpreprocess 0.9.x の iOS 動作未検証 | 最悪 build 失敗で release ブロック | **検証必須**: `cargo build --target aarch64-apple-ios` を実装着手前にローカル試行 |
| crates.io publish との同期 (rlib + staticlib 共存) | Rust consumer 側で `staticlib` 不要、crates.io 既存利用者影響なし | **受容** |
| cbindgen 自動生成ヘッダの diff が PR で大きい | コードレビュー負荷 | **受容** (CI で diff 確認) |
| App Store rejection | 低 (純 G2P で privacy 影響なし) | **受容** |

---

## 決定が必要な項目サマリ (Owner Action)

| ID | 項目 | 推奨案 | 確認必要 |
|----|------|-------|---------|
| **D-2** | 辞書埋込戦略 | Option A (`bundled-dicts` feature 新設) | **要** — 仕様の前提 |
| D-3 | crate version bump | 0.5.0 (minor) | 要 |
| D-5 | `bundled-dicts` を default に入れるか | no (iOS ビルド時のみ) | 要 |
| D-9 | CC BY-SA 4.0 解釈 | LICENSE-THIRD-PARTY.txt 同梱 + README で明示 | **要** — 法務面 |
| D-10 | Cross-runtime golden test 範囲 | 別 issue に切出し | 要 |
| D-13 | PR 分割方針 | 5 PR 案 | 要 |
| D-15 | jpreprocess iOS 動作検証 | 実装前にローカルで `cargo build --target aarch64-apple-ios` | **要** — リスク先行潰し |

それ以外の項目は本ドキュメント記載の推奨案で進める前提。

---

## Updating

本書は実装着手後 (実装完了まで) に発見した追加判断事項を都度追記する。
全 ID が解決したら `Status` を `Resolved — implementation underway` に更新し、本書の役割を `swift-g2p.md` (仕様) と `swift-g2p-integration.md` (ガイド) に引き継ぐ。
