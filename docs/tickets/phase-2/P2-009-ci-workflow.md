# [P2-009] CI ワークフロー

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: NFR-202
> 依存チケット: P2-001, P2-004, P2-007
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` Rust crate 用の CI ワークフロー `g2p-rust-ci.yml` を作成する。PR 時には 3 OS でのビルド・テスト・lint を実行し、タグ `rust-g2p-v*` push 時には crates.io への publish を自動実行する。

### ゴール
- `.github/workflows/g2p-rust-ci.yml` が作成されている
- PR / push to dev で `src/rust/piper-g2p/**` の変更時に自動起動する
- 3 OS (ubuntu-24.04, macos-latest, windows-latest) x stable でテスト実行
- `cargo fmt --check` + `cargo clippy` + `cargo test` が全て通過する
- タグ `rust-g2p-v*` push で crates.io publish ジョブが起動する
- 既存の `rust-tests.yml` との重複を最小化する

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `.github/workflows/g2p-rust-ci.yml` | 新規 | piper-g2p CI ワークフロー |
| `.github/workflows/rust-tests.yml` | 変更 | piper-g2p のテストを含めるか、除外するかの判断 |

### 実装手順

1. **`g2p-rust-ci.yml` 作成**
   ```yaml
   name: g2p-rust-ci

   on:
     workflow_call:
     pull_request:
       branches: [dev]
       paths:
         - 'src/rust/piper-g2p/**'
         - '.github/workflows/g2p-rust-ci.yml'
     push:
       branches: [dev]
       paths:
         - 'src/rust/piper-g2p/**'
       tags:
         - 'rust-g2p-v*'

   env:
     CARGO_TERM_COLOR: always

   jobs:
     check:
       name: cargo check + fmt + clippy
       runs-on: ubuntu-24.04
       defaults:
         run:
           working-directory: src/rust
       steps:
         - uses: actions/checkout@v6
         - uses: dtolnay/rust-toolchain@stable
           with:
             components: rustfmt, clippy
         - uses: Swatinem/rust-cache@v2
           with:
             workspaces: src/rust -> target
         - name: cargo fmt
           run: cargo fmt -p piper-g2p -- --check
         - name: cargo clippy (all features)
           run: cargo clippy -p piper-g2p --all-features -- -D warnings
         - name: cargo clippy (no default features)
           run: cargo clippy -p piper-g2p --no-default-features -- -D warnings

     test:
       name: tests (${{ matrix.os }})
       runs-on: ${{ matrix.os }}
       strategy:
         fail-fast: false
         matrix:
           os: [ubuntu-24.04, macos-latest, windows-latest]
       defaults:
         run:
           working-directory: src/rust
       steps:
         - uses: actions/checkout@v6
         - uses: dtolnay/rust-toolchain@stable
         - uses: Swatinem/rust-cache@v2
           with:
             workspaces: src/rust -> target
         - name: test (all features)
           run: cargo test -p piper-g2p --all-features
         - name: test (no default features)
           run: cargo test -p piper-g2p --no-default-features
         - name: test (japanese only)
           run: cargo test -p piper-g2p --no-default-features --features japanese

     # MSRV 検証
     msrv:
       name: MSRV check (1.88)
       runs-on: ubuntu-24.04
       defaults:
         run:
           working-directory: src/rust
       steps:
         - uses: actions/checkout@v6
         - uses: dtolnay/rust-toolchain@1.88.0
         - uses: Swatinem/rust-cache@v2
           with:
             workspaces: src/rust -> target
         - run: cargo check -p piper-g2p --all-features

     # workspace 互換性テスト (re-export が壊れていないか)
     workspace-compat:
       name: workspace build
       runs-on: ubuntu-24.04
       defaults:
         run:
           working-directory: src/rust
       steps:
         - uses: actions/checkout@v6
         - uses: actions/setup-python@v6
           with:
             python-version: '3.12'
         - name: Install ALSA dev
           run: sudo apt-get update && sudo apt-get install -y libasound2-dev
         - uses: dtolnay/rust-toolchain@stable
         - uses: Swatinem/rust-cache@v2
           with:
             workspaces: src/rust -> target
         - name: cargo build --workspace
           run: cargo build --workspace --all-features
         - name: cargo test --workspace
           run: cargo test --workspace --all-features

     # crates.io publish (タグトリガー)
     publish:
       name: publish to crates.io
       if: startsWith(github.ref, 'refs/tags/rust-g2p-v')
       needs: [check, test, msrv, workspace-compat]
       runs-on: ubuntu-24.04
       defaults:
         run:
           working-directory: src/rust
       steps:
         - uses: actions/checkout@v6
         - uses: dtolnay/rust-toolchain@stable
         - name: cargo publish
           run: cargo publish -p piper-g2p
           env:
             CARGO_REGISTRY_TOKEN: ${{ secrets.CRATES_IO_TOKEN }}
   ```

2. **既存 `rust-tests.yml` との関係整理**
   `rust-tests.yml` は `src/rust/**` の変更で起動し、workspace 全体をテストする。`g2p-rust-ci.yml` は piper-g2p 固有のテスト (feature 組み合わせ、MSRV、publish) を担当する。重複を避けるため:
   - `rust-tests.yml`: workspace 全体のビルド・テスト (既存のまま)
   - `g2p-rust-ci.yml`: piper-g2p 固有のテスト + publish

### API / インターフェース

CI 設定のため公開 API への変更なし。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| DevOps / CI 担当 | 1 | ワークフロー作成、secrets 設定、タグ運用ドキュメント |

---

## 4. テスト計画

### 提供範囲
CI ワークフロー自体の動作確認。

### Unit テスト
なし (CI 設定)。

### E2E テスト
1. PR を作成して `g2p-rust-ci.yml` が起動することを確認
2. 全ジョブ (check, test x3, msrv, workspace-compat) が緑になることを確認
3. タグ push のテストは dry-run で確認:
   ```bash
   # publish の dry-run (ローカル)
   cd src/rust
   cargo publish -p piper-g2p --dry-run
   ```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **CRATES_IO_TOKEN シークレット**: リポジトリの GitHub Secrets に `CRATES_IO_TOKEN` が設定されている必要がある。P0-001 (パッケージ名予約) で crates.io アカウントは作成済みのはず。
- **publish 時の workspace path 依存**: `piper-g2p` の Cargo.toml に `piper-core` への path 依存はないが、workspace member として同居している。`cargo publish` は path 依存を自動的に crates.io 依存に変換しない。piper-g2p が piper-core に依存しないことを確認する (P2-002 で保証済み)。
- **既存 `rust-tests.yml` との CI 時間増加**: 両方のワークフローが同時に起動すると CI リソースを消費する。`piper-g2p/**` のみの変更では `rust-tests.yml` も起動する (`src/rust/**` にマッチするため)。paths フィルタの調整を検討する。
- **MSRV 1.88**: 現時点で stable より新しい場合は CI が失敗する。`dtolnay/rust-toolchain` で特定バージョンを指定しているため問題ないが、GitHub-hosted runner に Rust 1.88 のツールチェインが存在するか確認が必要。

### レビュー項目
- `paths` フィルタが `src/rust/piper-g2p/**` を正しくターゲットしていること
- publish ジョブが `needs: [check, test, msrv, workspace-compat]` で全ジョブ成功後にのみ実行されること
- タグパターンが `rust-g2p-v*` であること (他のタグと衝突しない)
- `cargo publish` に `--dry-run` がついていないこと (本番用)

---

## 6. 一から作り直すとしたら

- `rust-tests.yml` に piper-g2p のテストを統合して単一ワークフローにする案。ただし publish ジョブは piper-g2p 固有のため、分離した方がタグトリガーの管理がシンプルになる。
- GitHub Actions の reusable workflow (`workflow_call`) を使って、テストジョブを共有する案。`rust-tests.yml` と `g2p-rust-ci.yml` でテストマトリクスが同一なら検討に値する。

---

## 7. 後続タスクへの連絡事項

- **P2-010**: v1.0.0 リリース時にタグ `rust-g2p-v1.0.0` を push する。publish ジョブが自動実行される。
- **P2-008**: jpreprocess 互換性テストは `cargo test -p piper-g2p --features naist-jdic` で実行される。CI の `test (all features)` ジョブでカバーされる。
- **リポジトリ管理者**: `CRATES_IO_TOKEN` シークレットの設定が必要。既に P0-001 で使用済みであれば追加設定は不要。
