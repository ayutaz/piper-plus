# [P0-001] パッケージ名予約

> Phase: 0 (MVP)
> マイルストーン: v0.0.1 -- パッケージ名予約
> 対応要求: (なし -- インフラ前提タスク)
> 依存チケット: なし (最初のチケット)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` を PyPI, crates.io, npm の 3 レジストリで確保する。名前スクワッティングを防ぎ、後続フェーズでのパッケージ公開をブロックされないようにする。Phase 0 では Python (PyPI) のみ実パッケージを開発するが、Rust (crates.io) と JS (npm) は Phase 2/3 で使用するため、このタイミングで同時に予約する。

### ゴール
- PyPI に `piper-g2p` v0.0.1 placeholder が publish されている
- crates.io に `piper-g2p` v0.0.1 placeholder が publish されている
- npm に `@piper-plus/g2p` v0.0.1 placeholder が publish されている
- 3 パッケージとも `pip install` / `cargo add` / `npm install` でインストール可能 (中身は空でよい)

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `tmp/placeholder/pypi/pyproject.toml` | PyPI placeholder パッケージ定義 |
| `tmp/placeholder/pypi/piper_g2p/__init__.py` | `__version__ = "0.0.1"` のみ |
| `tmp/placeholder/crates/Cargo.toml` | crates.io placeholder crate 定義 |
| `tmp/placeholder/crates/src/lib.rs` | `//! piper-g2p placeholder` のみ |
| `tmp/placeholder/npm/package.json` | npm placeholder パッケージ定義 |
| `tmp/placeholder/npm/index.js` | `module.exports = {}` のみ |

注: `tmp/placeholder/` は publish 後に削除する一時ディレクトリ。リポジトリにはコミットしない。

### 実装手順

1. **PyPI placeholder 作成**
   ```toml
   # tmp/placeholder/pypi/pyproject.toml
   [project]
   name = "piper-g2p"
   version = "0.0.1"
   description = "Multilingual G2P (Grapheme-to-Phoneme) for TTS — placeholder"
   requires-python = ">=3.11"
   license = "MIT"
   authors = [{name = "piper-plus contributors"}]
   readme = "README.md"
   ```
   ```bash
   cd tmp/placeholder/pypi
   uv build
   uv publish --token $PYPI_TOKEN
   ```

2. **crates.io placeholder 作成**
   ```toml
   # tmp/placeholder/crates/Cargo.toml
   [package]
   name = "piper-g2p"
   version = "0.0.1"
   edition = "2021"
   description = "Multilingual G2P (Grapheme-to-Phoneme) for TTS — placeholder"
   license = "MIT"
   repository = "https://github.com/yousan/piper-plus"
   ```
   ```bash
   cd tmp/placeholder/crates
   cargo publish --token $CRATES_IO_TOKEN
   ```

3. **npm placeholder 作成**
   ```json
   {
     "name": "@piper-plus/g2p",
     "version": "0.0.1",
     "description": "Multilingual G2P (Grapheme-to-Phoneme) for TTS — placeholder",
     "license": "MIT",
     "repository": {"type": "git", "url": "https://github.com/yousan/piper-plus"}
   }
   ```
   ```bash
   cd tmp/placeholder/npm
   npm publish --access public
   ```

4. **確認**: 各レジストリのパッケージページが表示されることを確認
5. **クリーンアップ**: `rm -rf tmp/placeholder`

### API / インターフェース

なし (placeholder のため)。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| インフラ担当 | 1 | 3 レジストリへの placeholder publish |

---

## 4. テスト計画

### 提供範囲
publish 後のインストール確認のみ。

### Unit テスト
なし。

### E2E テスト
```bash
# PyPI
uv pip install piper-g2p==0.0.1
python -c "import piper_g2p; print(piper_g2p.__version__)"
# -> "0.0.1"

# crates.io
cargo add piper-g2p@0.0.1
# -> Cargo.toml に追加される

# npm
npm install @piper-plus/g2p@0.0.1
# -> node_modules/@piper-plus/g2p/ が作成される
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **PyPI 名の衝突**: `piper-g2p` が既に取得されている可能性がある。事前に `pip index versions piper-g2p` で確認する。取得済みの場合は `piper-plus-g2p` にフォールバック。
- **npm scope**: `@piper-plus` org が npm に存在しない場合は先に org を作成する必要がある。
- **crates.io の名前ポリシー**: crates.io は placeholder publish を推奨していない。最低限のコード (空の lib.rs + description) を含めること。

### レビュー項目
- パッケージ名が 3 レジストリで統一感があること (`piper-g2p` / `piper-g2p` / `@piper-plus/g2p`)
- ライセンスが MIT であること
- description が適切であること (将来ユーザが検索で見つけたときに意図が分かる)

---

## 6. 一から作り直すとしたら

- **モノレポ名を使わない独立名**: `piper-g2p` ではなく `ipa-g2p` のようなプロジェクト非依存名にすると、piper-plus 以外の TTS プロジェクトからの採用が心理的に容易になる。ただし既に `piper-plus` ブランドで認知があるため、現時点では `piper-g2p` が妥当。
- **npm scope を `@piper-g2p`** にして 3 レジストリで完全に名前を統一する案もあるが、既存の `piper-plus` npm パッケージとの整合性を優先して `@piper-plus/g2p` を採用。

---

## 7. 後続タスクへの連絡事項

- **P0-002**: PyPI の `piper-g2p` が予約済みであることを前提にする。もし名前が取得できず `piper-plus-g2p` にフォールバックした場合、`pyproject.toml` のパッケージ名を変更すること。
- **全後続チケット**: v0.0.1 は placeholder であり、実コードは v0.1.0 (P0-002 以降) から入る。v0.0.1 を yanking するかどうかは v0.1.0 リリース時に判断する。
