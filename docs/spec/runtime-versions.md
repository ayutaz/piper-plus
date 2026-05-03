# Runtime Version Policy & Update Plan

各プログラム言語・ランタイム・プラットフォームの現状バージョンとサポートステータス、および必要なアップデート計画を一括で記録する。EOL を迎えたものや近く EOL になるものを早期に検出するためのリファレンス。

> **判定基準日:** 2026-05-03
> **次回レビュー目安:** 2026-11 (.NET 10 LTS リリースおよび .NET 8 EOL の数か月前)

---

## 目次

1. [サマリ](#サマリ)
2. [サポート切れ (要対応)](#-サポート切れ-要対応)
3. [近く EOL (計画的に更新)](#-近く-eol-計画的に更新)
4. [問題なし (最新水準)](#-問題なし-最新水準)
5. [Unity 対応の検討経緯](#unity-対応の検討経緯)
6. [ONNX Runtime バージョン整合 (参考)](#onnx-runtime-バージョン整合-参考)
7. [アップデート優先順位](#アップデート優先順位)
8. [参考資料](#参考資料)

---

## サマリ

| 状態 | 対象 |
|------|------|
| ❌ サポート切れ (要対応) | Node.js engines `>=18.0.0`, piper-python `python>=3.8`, .NET 9 (CI のみ) |
| ⚠️ 近く EOL (計画的に更新) | ubuntu-22.04 runner, debian:bookworm, net8.0 (2026-11), CUDA 12.1 と 12.4 の混在 |
| ✅ 問題なし | Go 1.26, Rust 1.88 + edition 2024, Python 3.11/3.12/3.13, Node.js 24.x (CI), C++17, CUDA 12.x |

---

## ❌ サポート切れ (要対応)

### Node.js engines `>=18.0.0`

- **対象ファイル:**
  - `src/wasm/openjtalk-web/package.json:95`
  - `src/wasm/g2p/package.json:54`
- **状況:** Node.js 18 は **2025-04-30 で EOL**
- **CI で使用しているバージョン:** 24.x (問題なし)
- **対応:** `engines.node` を `>=20.0.0` または `>=22.0.0` (Active LTS) に引き上げる

### piper-python の Python `>=3.8`

- **対象ファイル:** `src/rust/piper-python/pyproject.toml:9`
- **状況:** Python 3.8 は **2024-10 で EOL**
- **他パッケージの指定:** `pyproject.toml`, `src/python/pyproject.toml`, `src/python/g2p/pyproject.toml` 等は `>=3.11` で統一済み
- **対応:** `requires-python` を `>=3.11` に揃える

### .NET 9 (CI で使用)

- **対象ファイル:**
  - `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj:5` (`<TargetFramework>net9.0</TargetFramework>`)
  - `src/csharp/PiperPlus.Core.Tests/PiperPlus.Core.Tests.csproj:4` (`<TargetFramework>net9.0</TargetFramework>`)
  - `.github/workflows/csharp-ci.yml:37-39` (`9.0.x` を CI でテスト)
  - `.github/workflows/csharp-build-all-platforms.yml:58-60` (同上)
- **状況:** .NET 9 は **2026-05-12 EOL** (今月)
- **対応:** `net9.0` → `net8.0` (LTS、2026-11 まで) にダウングレード
- **Unity 互換性のための multi-target 化は不要** (詳細は [Unity 対応の検討経緯](#unity-対応の検討経緯))

---

## ⚠️ 近く EOL (計画的に更新)

### ubuntu-22.04 runner

- **対象ワークフロー (10+):** `android-build.yml`, `ci.yml`, `csharp-ci.yml`, `csharp-build-all-platforms.yml`, `g2p-go-publish.yml`, `go-ci.yml`, `python-tests.yml`, `release-shared-lib.yml` 等
- **状況:** GitHub Actions が 2025-12 から段階的退役を開始予定
- **対応:** `ubuntu-22.04` → `ubuntu-24.04` に統一 (一部ワークフローは既に 24.04)

### debian:bookworm (Debian 12)

- **対象ファイル:**
  - `Dockerfile`
  - `docker/wyoming/Dockerfile`
- **状況:** Debian 12 通常サポートは **2026-06 で終了** (LTS で 2028-06 まで継続)
- **対応:** LTS 期間中は維持可。中長期で `debian:trixie` (Debian 13) への移行を検討

### .NET 8 (LTS)

- **対象ファイル:** `src/csharp/PiperPlus.Core/PiperPlus.Core.csproj:4`
- **状況:** **2026-11-10 EOL (LTS)**
- **対応:** .NET 10 LTS リリース (2025-11) 後、`net10.0` への切り替えを検討

### CUDA 12.1 と 12.4 の混在

- **対象ファイル:**
  - `docker/python-train/Dockerfile` (`nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04` / `runtime`)
  - `docker/python-inference/Dockerfile` (`nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04`)
- **状況:** CUDA 12.x はサポート中だが 12.1 と 12.4 が混在
- **対応:** 統一 (12.4 推奨)。PyTorch 互換性 (`torch>=2.1.0+cu121`) との整合性確認

---

## ✅ 問題なし (最新水準)

### Node.js (CI)

| 設定 | 値 |
|------|---|
| CI 共通 (`NODE_VERSION`) | `24.x` |
| 対象ワークフロー | `ci.yml`, `npm-publish.yml`, `g2p-cross-platform-ci.yml`, `g2p-wasm-ci.yml`, `test-webassembly.yml` |

Node.js 24 は Active LTS (2028-04 まで)。

### Python (本体パッケージ)

| パッケージ | requires-python |
|----------|-----------------|
| `pyproject.toml` (root) | `>=3.11` |
| `src/python/pyproject.toml` | `>=3.11` |
| `src/python/g2p/pyproject.toml` | `>=3.11` |
| `src/python_stub/pyproject.toml` | `>=3.11` |
| `src/piper_phonemize_bundled/pyproject.toml` | `>=3.11` |

CI は `3.11`/`3.12`/`3.13` の matrix。3.11 EOL は 2027-10。

### Go

| 項目 | 値 |
|------|---|
| `src/go/go.mod:3` | `1.26` |
| `src/go/phonemize/go.mod:3` | `1.26` |
| CI (`go-ci.yml:47`, `g2p-go-publish.yml:30`) | `1.26` |
| Docker (`src/go/docker/Dockerfile:7`) | `golang:1.26` |

Go は最新2バージョンサポート。1.26 は最新水準。

### Rust

| 項目 | 値 |
|------|---|
| `src/rust/Cargo.toml:7` | `edition = "2024"` |
| `src/rust/Cargo.toml:8` | `rust-version = "1.88"` |
| CI (複数) | `stable` |

edition 2024 は Rust 1.85 以降で利用可能。1.88 は MSRV として妥当。

### C++

| 項目 | 値 |
|------|---|
| `cmake/CompilerSettings.cmake:4` | `CMAKE_CXX_STANDARD 17` |
| `cmake/CompilerSettings.cmake:8` | `CMAKE_C_STANDARD 99` |
| `CMakeLists.txt:1` | `cmake_minimum_required(VERSION 3.15)` |
| Android (`android/piper-plus/src/main/cpp/CMakeLists.txt:1`) | `3.22.1` |

C++17 は安定して現役。C++20/23 移行は任意。

### Android

| 項目 | 値 |
|------|---|
| compileSdk | 35 (Android 15) |
| minSdk | 24 (Android 7.0) |
| Java/Kotlin JVM | 11 |
| ABI | arm64-v8a |

---

## Unity 対応の検討経緯

`PiperPlus.Core` を `netstandard2.1` + `net8.0` のマルチターゲット化することで Unity 6.x LTS から直接利用可能にする案を検討したが、**実施しない**ことに決定 (2026-05-03)。

### 判断根拠

隣接する Unity プロジェクト [`uPiper`](https://github.com/ayutaz/uPiper) は piper-plus の C# DLL を一切使用していない。

| 確認項目 | 結果 |
|---------|------|
| `Plugins/**/PiperPlus*.dll` | 0 件 |
| `Packages/manifest.json` の piper-plus 参照 | 無し (DotNetG2P 系 UPM のみ) |
| `.cs` ファイルの `using PiperPlus.*` | 0 件 |
| `PiperPlus` 文字列 | テストメソッド名・コメント中の仕様参照 (`piper-plus short-text-contract.toml`) のみ |

uPiper は piper-plus を「**仕様** (`docs/spec/*.toml` の contract)」としてのみ参照し、**ランタイム実装は `Unity.InferenceEngine` + `DotNetG2P` (UPM) + 独自実装で構成**している。したがって `PiperPlus.Core.dll` を Unity 互換にする必要はない。

### Unity の .NET サポート状況 (2026-05 時点・参考情報)

| Unity バージョン | API Compatibility | C# 言語 | スクリプティング |
|----------------|-------------------|---------|----------------|
| Unity 2021/2022 LTS | .NET Standard 2.1 | C# 9 | Mono / IL2CPP (両者 EOL) |
| **Unity 6.0 / 6.3 LTS (現行)** | **.NET Standard 2.1** | **C# 9.0** | Mono / IL2CPP |
| Unity 6.7 (予定) | + 実験的 CoreCLR | Modern C# | + CoreCLR |
| Unity 6.8 (2026年内目標) | CoreCLR ベース | Modern C# | CoreCLR / IL2CPP (Mono廃止) |

### 将来の再検討トリガー

以下のいずれかが発生した場合に再検討:

- uPiper またはサードパーティの Unity プロジェクトが `PiperPlus.Core` を直接利用する要望を出した場合
- piper-plus 独自の Unity 統合 (`com.ayutaz.piperplus` UPM パッケージ) を提供したくなった場合
- Unity 6.7+ で CoreCLR ベースの実験的プレイヤーが安定した場合 (`net8.0` 直接サポート)

再検討時の作業見積りは git 履歴の本ドキュメント以前の版 (`git log --follow docs/spec/runtime-versions.md` で参照可) に詳細な互換性調査結果 (BCL API 置換 9 種類、C# 言語機能 9 箇所、Polyfill 戦略、設計判断 Q1-Q4 等) が残っている。

---

## ONNX Runtime バージョン整合 (参考)

各ランタイムで指定している ONNX Runtime バージョンが揃っていない。詳細は [ort-versions.md](ort-versions.md) 参照。

| 言語 | 指定 |
|------|------|
| Python | `>=1.17` |
| C# | `1.24.3` |
| Go | `1.27.0` (経由) |
| Rust | `2.0.0-rc.12` (RC版) |
| Release shared lib CI | `1.17.0` |

中長期で安定版に揃える検討余地あり。

---

## アップデート優先順位

| 優先度 | 項目 | 工数 | 備考 |
|--------|------|------|------|
| **P0** | piper-python `python>=3.8` → `>=3.11` | XS | 1行修正 |
| **P0** | Node.js `engines.node>=18.0.0` → `>=20.0.0` | XS | 2ファイル修正 |
| **P0** | .NET Cli/Tests `net9.0` → `net8.0` | S | csproj + CI 修正。Unity 対応は不要 ([検討経緯](#unity-対応の検討経緯)) |
| P1 | GitHub Actions runner `ubuntu-22.04` → `ubuntu-24.04` 統一 | S | 10+ ワークフロー一括修正 |
| P1 | CUDA 12.1 → 12.4 統一 | S | docker/python-train の base image 変更 |
| P2 | ONNX Runtime バージョン整合 | M | 互換性検証必要 |
| P2 | net8.0 → net10.0 LTS | M | 2026-11 (.NET 8 EOL) 前に |
| P3 | debian:bookworm → trixie | S | LTS 期間中は急がない |

---

## 参考資料

- [Unity Manual: API compatibility levels for .NET (6000.3)](https://docs.unity3d.com/6000.3/Documentation/Manual/dotnet-profile-support.html)
- [Unity Manual: C# compiler and language version reference (6000.3)](https://docs.unity3d.com/6000.3/Documentation/Manual/csharp-compiler.html)
- [Unity Discussions: Path to CoreCLR, 2026: Upgrade Guide](https://discussions.unity.com/t/path-to-coreclr-2026-upgrade-guide/1714279)
- [.NET Support Policy](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)
- [Microsoft Learn: Use .NET 4 and later versions in Unity](https://learn.microsoft.com/en-us/visualstudio/gamedev/unity/unity-scripting-upgrade)
- [Node.js Release Schedule](https://nodejs.org/en/about/previous-releases)
- [Python Release Cycle](https://devguide.python.org/versions/)
