# Kotlin G2P ライブラリ — マイルストーン管理 (Issue #388)

> **親 Issue**: [#388](https://github.com/ayutaz/piper-plus/issues/388) — 「Kotlin 向けの g2p ライブラリの提供」
> **要件定義書**: [docs/spec/kotlin-g2p-requirements.md](../../spec/kotlin-g2p-requirements.md)
> **設計書**: [docs/spec/kotlin-g2p-design.md](../../spec/kotlin-g2p-design.md)
> **チケット INDEX**: [docs/tickets/kotlin-g2p/README.md](README.md)
> **作業ブランチ**: `feat/issue-388-kotlin-g2p`
> **判定基準**: 自動化可能性 (CLI/CI で完結) を最優先。実装工数は評価軸から除外。

このドキュメントは Issue #388 の **マイルストーン管理ハブ** です。各マイルストーンは複数のチケットを束ねた成果単位で、**Entry/Exit Criteria** によって着手・完了を管理します。チケット個別の詳細仕様は [チケット INDEX](README.md) を参照してください。

---

## 1. マイルストーン一覧

```
M0   Design Phase            ✅ Done       (2026-05-07)
M0.5 Requirements Phase      ✅ Done       (2026-05-07)
─────────────────────────────────────────────────────────────
M1   C API Extension         📋 Ready      (engine-less G2P)        ← クリティカルパス起点
M2   JNI Bridge              ⏸ Blocked     (depends on M1)
M3   Kotlin Public API       ⏸ Blocked     (depends on M2)
M4   Gradle Module + Build   ⏸ Blocked     (depends on M3)
─────────────────────────────────────────────────────────────
M5   Automated Tests (L1-L5) ⏸ Blocked     (depends on M4)
M6   Dictionary Distribution ⏸ Blocked     (depends on M3, parallel to M5)
M7   Maven Central Publish   ⏸ Blocked     (depends on M5)
M8   Docs & Sample App       ⏸ Blocked     (depends on M7)
─────────────────────────────────────────────────────────────
M9   GA Release v1.0.0       🎯 Target      (Maven Central 公開 + アナウンス)
```

ステータス凡例: 🎯 Target / 📋 Ready / 🚧 In Progress / 👀 Review / ✅ Done / ⏸ Blocked / ❌ Cancelled

---

## 2. マイルストーン詳細

### M0: Design Phase ✅ Done

**Goal**: 3 並列調査エージェント (codebase / concept / competitor) で実装方針を確定し、設計書とチケット INDEX を作成。

| 項目 | 内容 |
|------|------|
| **Deliverables** | `docs/spec/kotlin-g2p-design.md` (541 行)、`docs/tickets/kotlin-g2p/README.md` (487 行) |
| **Entry Criteria** | Issue #388 の存在確認、ブランチ `feat/issue-388-kotlin-g2p` 作成 |
| **Exit Criteria** | 調査結果を統合し、アプローチ A (JNI + AAR + Maven Central) を採択した設計書がコミット済 |
| **Status** | ✅ Done (commit `25700837`、2026-05-07) |
| **Outcome** | アプローチ A 採択、7 チケット (Phase 1-7) のロードマップ確定 |

---

### M0.5: Requirements Phase ✅ Done

**Goal**: 設計書策定後の 4 並列技術調査で得た新事実 — 特に **engine-less C API 必須** — を反映した要件定義書を作成。

| 項目 | 内容 |
|------|------|
| **Deliverables** | `docs/spec/kotlin-g2p-requirements.md` (~600 行)、設計書とチケット INDEX への前提変更注記 |
| **Entry Criteria** | M0 完了 |
| **Exit Criteria** | 機能要件 (FR) / 非機能要件 (NFR) / 制約 / 受け入れ基準 / リスク / オープンクエスチョン がドキュメント化され、コミット済 |
| **Status** | ✅ Done (commit `4d641179`、2026-05-07) |
| **Outcome** | engine-less C API (FR-CAPI-1) が新規要件として確定、TICKET-00 を Phase 0.5 として追加 |

**主要発見**:
- `piper_plus_phonemize()` は `Voice` (= ONNX モデル) 経由でのみ動作する (`piper_plus_c_api.cpp:1005`)
- 他ランタイム (Python/Rust/Go/JS/C#) は engine-less で動作するため、C API のみが特殊
- → Kotlin AAR は C API 拡張 (FR-CAPI-1) 経由で他ランタイム同等の体験を提供する

---

### M1: C API Extension (Engine-less G2P) 📋 Ready

**Goal**: ONNX モデル不要の G2P エントリポイントを C API に追加し、Kotlin AAR から呼び出せる土台を構築する。

| 項目 | 内容 |
|------|------|
| **対応チケット** | TICKET-00 (新規、要件定義書 §6.1 由来) |
| **Deliverables** | `src/cpp/piper_plus.h` の拡張、`src/cpp/piper_plus_c_api.cpp` の実装、内蔵 languageIdMap データ、新規 GTest テストケース |
| **Entry Criteria** | M0.5 完了、保守者からの C API 拡張承認 (Q-1) |
| **Exit Criteria** | (1) 新 API シグネチャ 5 関数 (`piper_plus_g2p_create/free/phonemize/available_languages/load_custom_dict`) が `piper_plus.h` に追加<br>(2) 既存 ABI と互換 (PIPER_PLUS_API_VERSION 1 維持)<br>(3) 既存 `piper_plus_phonemize()` と新 API の出力が byte-for-byte 一致 (8 言語 × 50 ケース)<br>(4) GTest で新規テスト全 PASS<br>(5) AddressSanitizer ビルドで実行時エラーゼロ |
| **Estimated Effort** | M (実装期間でなくレビュー往復を含む) |
| **Risk** | R-1 (内部リファクタ膨張) — 既存 `Voice` 構造を保ちつつ `languageIdMap` のみ内蔵データ化で抑制 |
| **Dependencies** | なし (クリティカルパス起点) |
| **CI Gate** | C++ unit test、ASan、ABI compatibility check |

**チェックリスト**:
- [ ] Q-1 (保守者承認) 解決
- [ ] Q-8 (language ID 体系) 解決
- [ ] `piper_plus.h` に 5 関数追加、コメントで lifetime / threading 規約明示
- [ ] `piper_plus_c_api.cpp` に実装追加 (`Voice` 構築なしで `phonemizeText` 等を呼べる経路)
- [ ] 内蔵 languageIdMap (8 言語) データ追加
- [ ] GTest fixture 追加
- [ ] 既存 API との byte 一致確認テスト
- [ ] CHANGELOG `## [Unreleased]` にエントリ追加

---

### M2: JNI Bridge ⏸ Blocked (depends on M1)

**Goal**: M1 で追加した engine-less C API を Kotlin から呼ぶための JNI 層を実装。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-01](README.md#ticket-01-jni-bridge--c-api-gluing) |
| **Deliverables** | `android/piper-plus-g2p/src/main/cpp/piper_plus_g2p_jni.cpp`、`CMakeLists.txt` |
| **Entry Criteria** | M1 完了、新 C API ヘッダが安定 |
| **Exit Criteria** | (1) JNI 5 関数 (`nativeCreate/Phonemize/AvailableLanguages/LoadCustomDict/Destroy`) 実装<br>(2) `JNIStringGuard` RAII で UTF-8 文字列リーク防止<br>(3) `JNI_OnLoad` で例外クラス global ref キャッシュ<br>(4) BORROWED ポインタ即コピー徹底<br>(5) CMake で 3 ABI (arm64-v8a / armeabi-v7a / x86_64) ビルド成功<br>(6) `nm -D libpiper_plus_g2p_jni.so` で必要 symbol 露出確認<br>(7) AddressSanitizer ビルド PASS |
| **Estimated Effort** | S |
| **Risk** | R-5 (BORROWED ポインタ寿命誤認) — `NewStringUTF` 即コピー + ASan で抑制 |
| **Dependencies** | M1 (新 C API ヘッダ) |
| **CI Gate** | L2 (JVM JNI smoke test on Linux .so)、L5 (ABI / 16 KB page size 検証) |

---

### M3: Kotlin Public API ⏸ Blocked (depends on M2)

**Goal**: ユーザーが触る Kotlin パブリック API を実装。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-02](README.md#ticket-02-kotlin-パブリック-api--data-class) |
| **Deliverables** | `PiperPlusG2p.kt`、`PiperPlusG2pNative.kt`、`PiperPlusG2pException.kt`、`PhonemeResult.kt`、`OpenJTalkDictionary.kt` (雛形) |
| **Entry Criteria** | M2 完了、JNI シグネチャ確定 |
| **Exit Criteria** | (1) `PiperPlusG2p` が `AutoCloseable` 実装、`use { }` ブロック対応<br>(2) `@Synchronized` が全 native 呼び出しに適用<br>(3) `PhonemeResult` data class、`PiperPlusG2pException` 例外型完成<br>(4) Kotlin 2.1.0 + JDK 17 で警告なしビルド<br>(5) dokka でドキュメント生成成功<br>(6) L1 (Pure Kotlin unit test) 全 PASS |
| **Estimated Effort** | S |
| **Risk** | 低 (idiomatic Kotlin で既存パターン踏襲) |
| **Dependencies** | M2 (JNI シグネチャ) |
| **CI Gate** | L1 (Pure Kotlin unit test) |

---

### M4: Gradle Module + Build Configuration ⏸ Blocked (depends on M3)

**Goal**: 独立 Gradle module として `android/piper-plus-g2p/` を構成し、AAR を生成可能にする。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-03](README.md#ticket-03-gradle-module--公開設定) |
| **Deliverables** | `android/piper-plus-g2p/build.gradle.kts`、`consumer-rules.pro`、`proguard-rules.pro`、`AndroidManifest.xml`、`android/settings.gradle.kts` の更新 |
| **Entry Criteria** | M3 完了 |
| **Exit Criteria** | (1) `./gradlew :piper-plus-g2p:assembleRelease` で AAR 生成成功<br>(2) AAR 構造に `jni/{arm64-v8a, armeabi-v7a, x86_64}/lib*.so` 全て含まれる<br>(3) AAR サイズ < 10 MB (目標 < 5 MB)<br>(4) `objdump -p libpiper_plus_g2p_jni.so` で全 ABI が `align 2**14` (16 KB page size)<br>(5) `./gradlew :piper-plus-g2p:publishToMavenLocal` でローカル publish 成功<br>(6) vanniktech plugin v0.30.0 採用、`SonatypeHost.CENTRAL_PORTAL` 設定 |
| **Estimated Effort** | M |
| **Risk** | R-7 (namespace 衝突) — `com.piperplus.g2p` で分離済 |
| **Dependencies** | M3 |
| **CI Gate** | assembleRelease 成功 + AAR サイズチェック + 16 KB page align 検証 |

---

### M5: Automated Tests (L1-L5) ⏸ Blocked (depends on M4)

**Goal**: 5 層の自動テストを CI で完結する形で整備し、実機なしの回帰検知を実現。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-04](README.md#ticket-04-自動テスト整備-l1-l5) |
| **Deliverables** | unit test (`src/test/`)、instrumented test (`src/androidTest/`)、parity fixture、`.github/workflows/kotlin-g2p-ci.yml` |
| **Entry Criteria** | M4 完了 (AAR ビルド可能) |
| **Exit Criteria** | (1) L1〜L5 すべて GitHub Actions で全 PASS<br>(2) L4 で 8 言語 × 50+ ケース byte 一致 (FR-TEST-1)<br>(3) L3 が emulator のみで完走 (実機接続なし)<br>(4) フレーキー率 < 1% (10 回連続 PASS で merge 許可)<br>(5) CI 全体の wall-clock time < 30 分 |
| **Estimated Effort** | M |
| **Risk** | R-2 (Gradle Managed Devices 不安定) — KVM 必須、API 30+ 固定、retry 設定 |
| **Dependencies** | M4 |
| **CI Gate** | L1-L5 全 PASS が PR マージ条件 |

**5 層テストの内訳**:
- L1: `./gradlew :piper-plus-g2p:test` (Pure Kotlin unit)
- L2: `./gradlew :piper-plus-g2p:linuxTest` (JVM JNI smoke on Linux .so)
- L3: `./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest` (Gradle Managed Devices)
- L4: `./gradlew :piper-plus-g2p:parityTest` (Cross-runtime parity)
- L5: `objdump -p` / `nm -D` script (ABI / 16 KB page size 検証)

---

### M6: Dictionary Distribution ⏸ Blocked (depends on M3, parallel to M5)

**Goal**: OpenJTalk 辞書 (~102 MB) を AAR に同梱せず、3 配布パターンを API で提供。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-05](README.md#ticket-05-辞書配布戦略) |
| **Deliverables** | `OpenJTalkDictionary.kt` 実装完成、`DictionaryDownloader.kt`、`docs/guides/android-g2p-dictionary.md` |
| **Entry Criteria** | M3 完了 (`OpenJTalkDictionary` 雛形済) |
| **Exit Criteria** | (1) 3 パターン (`fromAssets` / `fromPath` / `downloadFromHuggingFace`) 全実装<br>(2) HF Hub DL の SHA-256 チェックサム検証実装<br>(3) L3 instrumented test で各パターンの動作確認 PASS (HF Hub は WireMock でモック化)<br>(4) F-Droid 対応ドキュメント (Anti-Feature: "Non-Free Network Services" 明記)<br>(5) 既存 TTS フル AAR (`PiperPlus.kt:80-146`) の展開ロジックと整合 |
| **Estimated Effort** | M |
| **Risk** | R-6 (UX 悪化) — 3 パターン提供で軽減、Q-7 (HF Hub repo 確定) を解決必須 |
| **Dependencies** | M3 (parallel to M5) |
| **CI Gate** | L3 で 3 パターン instrumented test PASS |

---

### M7: Maven Central Publish Automation ⏸ Blocked (depends on M5)

**Goal**: タグ push → Maven Central 自動公開を実現し、人手介入ゼロを担保。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-06](README.md#ticket-06-maven-central-公開自動化) |
| **Deliverables** | `.github/workflows/release-kotlin-g2p.yml`、GitHub Actions secrets 登録手順書、`build.gradle.kts` の publishing 設定完成 |
| **Entry Criteria** | M5 完了 (5 層テスト全 PASS)、Q-2 (Sonatype Central Portal 登録) 解決 |
| **Exit Criteria** | (1) PR で `--dry-run` (publishToMavenLocal) 成功<br>(2) タグ `kotlin-g2p-v*` push → 30 分以内に Maven Central で検索可能 (NFR-PUB-1)<br>(3) GPG 署名検証 PASS (`./gradlew :piper-plus-g2p:checkMavenCentralPublicationSignature`)<br>(4) バージョン乖離 (POM vs git tag) 検知 CI gate<br>(5) 必要 secrets 4 個全登録 (`MAVEN_CENTRAL_USERNAME/PASSWORD/SIGNING_IN_MEMORY_KEY/PASSWORD`) |
| **Estimated Effort** | S |
| **Risk** | R-3 (credentials 漏洩) — secrets、PR では publish skip / R-9 (vanniktech beta) — JReleaser fallback 準備 |
| **Dependencies** | M5 |
| **CI Gate** | tag push 後の publish 成功 + 署名検証 |

**前提準備チェックリスト**:
- [ ] Sonatype Central Portal に `io.github.ayutaz` namespace 登録 (Q-2)
- [ ] GPG キー生成 (in-memory key 形式)
- [ ] GitHub Actions secrets 4 個登録
- [ ] 既存 release-*.yml パターン (Rust/npm/Go) との一貫性確認

---

### M8: Documentation & Sample App ⏸ Blocked (depends on M7)

**Goal**: ユーザーが迷わず導入できるドキュメントとサンプルアプリを整備。

| 項目 | 内容 |
|------|------|
| **対応チケット** | [TICKET-07](README.md#ticket-07-ドキュメント--サンプルアプリ) |
| **Deliverables** | `android/piper-plus-g2p/README.md`、`examples/android-g2p-sample/` (Compose アプリ)、`docs/guides/android-g2p-integration.md`、`CLAUDE.md` / ルート `README.md` / `CHANGELOG.md` 更新 |
| **Entry Criteria** | M7 完了 (Maven Central で実際に取得可能) |
| **Exit Criteria** | (1) `android/piper-plus-g2p/README.md` で 3 ステップで動作開始可能<br>(2) サンプルアプリが CI で `assembleDebug` 成功<br>(3) サンプルアプリで 8 言語タブ切替 + カスタム辞書 + HF Hub DL デモが動作<br>(4) CLAUDE.md / ルート README / CHANGELOG が一貫 (全 7 ランタイム揃う)<br>(5) dokka 生成 javadoc が Maven Central に同梱<br>(6) docs link checker PASS |
| **Estimated Effort** | S |
| **Risk** | 低 (既存ドキュメントの拡張のみ) |
| **Dependencies** | M7 (実際に Maven Central から取得できる状態を前提にしたドキュメント) |
| **CI Gate** | docs link checker、サンプルアプリ assembleDebug |

---

### M9: GA Release v1.0.0 🎯 Target

**Goal**: 全マイルストーン完了後、`kotlin-g2p-v1.0.0` タグを切って Maven Central に公開、Issue #388 を close。

| 項目 | 内容 |
|------|------|
| **Deliverables** | `kotlin-g2p-v1.0.0` git tag、Maven Central で `io.github.ayutaz:piper-plus-g2p-android:1.0.0` 公開、Issue #388 close、リリースアナウンス |
| **Entry Criteria** | M1〜M8 全完了、要件定義書 §14 受け入れ基準 (AC-1〜13、AC-REL-1〜4) 全 PASS |
| **Exit Criteria** | (1) Maven Central で `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` が解決可能<br>(2) サンプルアプリが 1.0.0 を依存に取って動作<br>(3) Issue #388 が close、PR がマージ済 (dev → main)<br>(4) GitHub Releases に release notes 公開<br>(5) CLAUDE.md「ランタイム別パッケージ」表が全 7 ランタイム揃う |
| **Estimated Effort** | XS (タグ push のみ、CI が公開を担当) |
| **Risk** | Maven Central は immutable: 一度公開した version は取消不可 (CONSTRAINT-6) |
| **Dependencies** | M1〜M8 全完了 |
| **CI Gate** | release-kotlin-g2p.yml が完走 |

---

## 3. 依存関係グラフ

```
M0 (Design) ──→ M0.5 (Requirements)
                       │
                       ▼
                  ┌───  M1 (C API Extension) ←── クリティカルパス起点
                  │     │
                  │     ▼
                  │   M2 (JNI Bridge)
                  │     │
                  │     ▼
                  │   M3 (Kotlin API) ───┐
                  │     │                │
                  │     ▼                ▼
                  │   M4 (Gradle)    M6 (Dict)  ← M3 完了後並列着手可
                  │     │                │
                  │     ▼                │
                  │   M5 (Tests) ←──────┘
                  │     │
                  │     ▼
                  │   M7 (Maven Publish)
                  │     │
                  │     ▼
                  │   M8 (Docs & Sample)
                  │     │
                  │     ▼
                  └─→  M9 (GA v1.0.0) 🎯
```

**並列着手可能ポイント**:
- M3 完了後、**M4 と M6 は並列着手可能** (M4 は Gradle / build、M6 は辞書配布で互いに独立)
- M5 は M4 完了が必要 (instrumented test に AAR が必要)
- M6 は M5 と並行できる (M6 の L3 サブセットは M5 の L3 統合より先行可能)

**クリティカルパス**: M1 → M2 → M3 → M4 → M5 → M7 → M8 → M9

---

## 4. 進捗ダッシュボード

```
M0   Design Phase            ████████████████████  100%  ✅ Done       (commit 25700837)
M0.5 Requirements Phase      ████████████████████  100%  ✅ Done       (commit 4d641179)
M1   C API Extension         ████████████████████  100%  ✅ Done       (commit c2696072)
M2   JNI Bridge              ████████████████████  100%  ✅ Done       (commit c2696072)
M3   Kotlin Public API       ████████████████████  100%  ✅ Done       (commit c2696072)
M4   Gradle Module + Build   ████████████████████  100%  ✅ Done       (commit c2696072)
M5   Automated Tests         ████████████████████  100%  ✅ Done       (L1/L3/L4-structural/L4-strict-golden/L5)
M6   Dictionary Distribution ████████████████████  100%  ✅ Done       (DictionaryDownloader + ガイド)
M7   Maven Central Publish   ████████████████████  100%  ✅ Done       (release-kotlin-g2p.yml)
M8   Docs & Sample App       ████████████████████  100%  ✅ Done       (Compose サンプルアプリ + ドキュメント)
M9   GA Release v1.0.0       ░░░░░░░░░░░░░░░░░░░░    0%  🎯 Target      (タグ push 待ち、Q-1/Q-2/Q-7 解決後)
```

---

## 5. マイルストーン横断のチェックリスト

各マイルストーン完了時に確認する項目。要件定義書 §14 受け入れ基準と紐付け。

### 5.1 全 Phase 共通

- [ ] CHANGELOG `## [Unreleased]` に該当 M の変更を記載
- [ ] PR description にマイルストーンと対応チケットを明記
- [ ] CI 全 PASS (該当する CI gate のみ)
- [ ] レビュー 1 名以上 approve

### 5.2 Phase 別の受け入れ基準 (要件定義書 §14 と対応)

| AC ID | マイルストーン | 検証方法 |
|-------|------------|--------|
| AC-1 | M1 | 新 C API シグネチャ追加確認 |
| AC-2 | M3 | `./gradlew :piper-plus-g2p:test` |
| AC-3 | M5 | `./gradlew :piper-plus-g2p:linuxTest` |
| AC-4 | M5 | `./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest` |
| AC-5 | M5 | `./gradlew :piper-plus-g2p:parityTest` (8 言語 × 50 ケース) |
| AC-6 | M4, M5 | `objdump -p \| grep "align 2**14"` |
| AC-7 | M7 | `./gradlew publishToMavenCentralRepository --dry-run` |
| AC-8 | M4 | AAR サイズ計測 |
| AC-9 | M8 | README.md レビュー |
| AC-10 | M8 | サンプルアプリ assembleDebug |
| AC-11 | M8 | CHANGELOG / README / CLAUDE.md レビュー |
| AC-12 | M5 | 8 言語 phonemize instrumented test |
| AC-13 | M5 | ZH-EN parity test |
| AC-REL-1 | M9 | Maven Central 検索 |
| AC-REL-2 | M7, M9 | GPG 署名検証 |
| AC-REL-3 | M7 | バージョン乖離 CI gate |
| AC-REL-4 | M9 | サンプルアプリの実利用検証 |

---

## 6. オープンクエスチョンとマイルストーン

要件定義書 §15 のオープンクエスチョンを、解決すべきマイルストーンに紐付け。

| Q ID | 質問 | 解決マイルストーン |
|------|------|---------------|
| Q-1 | C API engine-less エントリポイント追加に対する保守者承認 | **M1 着手前** |
| Q-2 | `io.github.ayutaz` Maven Central namespace の登録状況 | **M7 着手前** |
| Q-3 | 既存 `tests/fixtures/g2p/*.json` の構造と PUA / prosody / SSML カバー率 | M5 着手時 |
| Q-4 | g2pk2 / pypinyin の C++ 実装内辞書サイズ実測値 | M4 (assembleRelease 後) |
| Q-5 | Custom Dictionary JSON v1.0/v2.0 schema 正式仕様 | M3 (FR-DICT-CUSTOM-1 実装時) |
| Q-6 | ORT 1.17.0 の armeabi-v7a / x86_64 AAR が Maven Central にあるか | M4 着手時 |
| Q-7 | OpenJTalk 辞書の HF Hub 配布リポジトリ確定 | **M6 着手前** |
| Q-8 | engine-less API の language ID は 6lang モデルと整合 (ja=0, en=1, …) させるか | **M1 着手前** |
| Q-9 | Gradle Managed Devices で OpenJTalk 辞書 (~102MB) を assets バンドル時の emulator メモリ要件 | M5 / M6 着手時 |
| Q-10 | サンプルアプリのディレクトリ配置 | M8 着手時 |

**ブロッカー**: Q-1, Q-2, Q-7, Q-8 が解決しないとマイルストーン着手不可。

---

## 7. リスク管理 (マイルストーン横断)

要件定義書 §13 のリスクを、影響を受けるマイルストーンに紐付け。

| R ID | リスク | 影響 M | 緩和タイミング |
|------|-------|------|------------|
| R-1 | engine-less C API の内部リファクタ膨張 | M1 | M1 設計レビュー時 |
| R-2 | Gradle Managed Devices CI 不安定 | M5 | M4 で managedDevices 設定時に prototype |
| R-3 | Maven Central credentials 漏洩 | M7 | M7 着手前に secrets 登録手順 review |
| R-4 | 16 KB page size 非対応 | M2, M4, M5 | M2 で max-page-size flag 必須化、M5 で L5 検証 |
| R-5 | JNI BORROWED ポインタ寿命誤認 | M2 | M2 の ASan ビルド + コードレビュー |
| R-6 | OpenJTalk 辞書配布 UX 悪化 | M6 | M6 で 3 パターン提供 |
| R-7 | `android/piper-plus/` namespace 衝突 | M4 | M4 で namespace 分離検証 |
| R-8 | 8 言語クロスランタイムドリフト | M5 | M5 の L4 parity test を merge gate に |
| R-9 | vanniktech plugin Sonatype Central Portal 対応 beta | M7 | M7 着手前に JReleaser fallback 準備 |
| R-10 | Issue #388 タイトル「Kotolin」(タイポ) | — | 要件定義書冒頭で確定済 |

---

## 8. レポーティング・コミュニケーション

### 8.1 進捗の可視化

- 本 MILESTONES.md の §4 進捗ダッシュボードを各 PR マージ時に更新
- 各マイルストーン完了時に Issue #388 にコメント (短く: "M3 ✅ done @ commit XXXX")
- ブロッカー発生時は親 Issue にコメントで明示 (オープンクエスチョン Q-X が未解決等)

### 8.2 PR / コミット規約

- ブランチ命名: `feat/issue-388-kotlin-g2p-mN-<short-name>` (例: `feat/issue-388-kotlin-g2p-m1-c-api-extension`)
- コミットメッセージ prefix: `feat(kotlin-g2p)` / `docs(kotlin-g2p)` / `test(kotlin-g2p)` / `ci(kotlin-g2p)`
- PR タイトルに対応マイルストーンを含める (例: `[M1] feat(kotlin-g2p): engine-less G2P C API`)

### 8.3 マイルストーン完了の判定

各マイルストーンの **Exit Criteria** を全て満たし、CI が緑になったタイミングで完了とする。**Definition of Done** は要件定義書 §14 の AC-X に対応する CI gate が全 PASS を意味する。

---

## 9. スコープ管理

### 9.1 マイルストーン内で扱う変更

- 各マイルストーンの **Deliverables** に列挙されたファイル / 機能のみ
- 想定外の変更は別 Issue / 別 PR に切り出す

### 9.2 マイルストーン外への持ち越し候補

要件定義書 §11 「スコープ外」を再掲。発見次第別 Issue 化:

- TTS フル機能の Kotlin AAR 化 → 既存 `android/piper-plus/`
- Android System TTS Engine 化 → 別 Issue
- Voice Cloning Kotlin API → 別 Issue (C API EXPERIMENTAL のため)
- Phoneme Timing 出力 Kotlin API → 別 Issue
- SSML 完全パース → 必要に応じ別 Issue
- ストリーミング phonemize (文単位 yield) → G2P 用途では不要

---

## 10. 関連ドキュメント

- [docs/spec/kotlin-g2p-requirements.md](../../spec/kotlin-g2p-requirements.md) — 要件定義書
- [docs/spec/kotlin-g2p-design.md](../../spec/kotlin-g2p-design.md) — 設計書
- [docs/tickets/kotlin-g2p/README.md](README.md) — チケット INDEX (本書から個別チケットへ)
- [Issue #388](https://github.com/ayutaz/piper-plus/issues/388) — 親 Issue

---

## 11. 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | マイルストーン管理ハブ初版。M0〜M9 の 9 マイルストーンを定義し、各マイルストーンの Goal / Deliverables / Entry/Exit Criteria / Dependencies / Risk を整理。要件定義書 §14 受け入れ基準と §15 オープンクエスチョンをマイルストーンに紐付け。クリティカルパス: M1 (C API 拡張) → M2 (JNI) → M3 (Kotlin API) → M4 (Gradle) → M5 (Tests) → M7 (Maven Publish) → M8 (Docs) → M9 (GA)。 |
