# Migration guides

`piper-plus` の version-to-version migration guide はすべてこのディレクトリに置きます。 ユーザー視点で **既存コードがそのままでは動かなくなる変更** (= breaking change) を解説するのが目的です。 内部リファクタや非互換ではない API 追加はここではなく `CHANGELOG.md` の `### Added` / `### Changed` 節で扱います。

## ファイル命名規則

`v<X>-to-v<Y>.md` の形 (例: `v1.11-to-v1.12.md`)。 hot-fix を伴う場合も major.minor 単位で 1 ファイルに集約し、 patch-level の細分化はしません (`v1.12.0-to-v1.12.1.md` 等は作らない)。

## 見出し規約

各 migration guide のトップ見出しは `# vX → vY migration guide`。 そのほかの構造は自由ですが、 個別の breaking change には **`## <change-id>` の H2 見出し** を 1 つずつ用意してください。 H2 見出しのテキストは GitHub Markdown anchor として CHANGELOG から `[label](docs/migration/vX-to-vY.md#change-id)` で参照されるので、 一度公開した H2 はリネームしないでください (anchor が壊れます)。

H2 anchor slug の算出:

1. lower-case にする
2. `[^\w\s-]` (`\w` = alphanum + underscore) に該当する文字を削除
3. 連続する空白 / underscore を単一 `-` に置換
4. 先頭・末尾の `-` を trim

例:

| 見出し | anchor |
|--------|--------|
| `## foo removal` | `#foo-removal` |
| ``## `Generator` class removal`` | `#generator-class-removal` |
| `## config schema v2` | `#config-schema-v2` |

絵文字や日本語を含む見出しは、 上記アルゴリズム後に空になる可能性があります。 その場合は ASCII subset の代替見出しを併設するか、 CHANGELOG 側から anchor を省略してください (anchor なしのファイル link は許可されます)。

## CHANGELOG との cross-ref

`CHANGELOG.md` の `## [Unreleased]` セクションに `### Breaking` 節を追加するとき、 各 entry には **少なくとも 1 つ** の `docs/migration/v*-to-v*.md` リンクを含めてください。 `scripts/check_migration_xref.py` (CI workflow `Migration Guide Lint` + pre-commit `migration-guide-lint`) が自動検査します。

書式例:

```markdown
### Breaking

- `Generator` クラスを削除。 MB-iSTFT base からの fine-tune に移行してください。 ([移行ガイド](docs/migration/v1.12-to-v1.13.md#generator-class-removal))
- `phonemize()` 戻り値が単一要素から複数要素へ変更。 ([移行ガイド](docs/migration/v1.12-to-v1.13.md#phonemize-return-shape))
```

`### Breaking` という見出しテキストは厳密に一致する必要があります。 `### Changed (Breaking)` のような変則は検査対象外になるため、 ユーザー向け migration 情報は **必ず `### Breaking` 節に集約**してください。

## anchor を省略してよい場合

- migration guide の全体概要 link (`[v1.13 migration overview](docs/migration/v1.12-to-v1.13.md)`)
- 同じ breaking change を別 entry が anchor 付きで参照済みで、 こちらは context link

CI は anchor なしを fail にはしません。 ただし strict CI で `--strict-anchor` flag を指定するとき (release branch 等で運用予定) は anchor 必須になります。

## 関連 doc

- [CHANGELOG.md](../../CHANGELOG.md) — release notes
- [docs/proposals/ci-expansion-2026-05.md](../proposals/ci-expansion-2026-05.md#5-真に追加する価値があるトップ-10) — Top 10 #3 親調査 (M1.2 / PR #511 で実装完了)
- [docs/spec/release-versions.toml](../spec/release-versions.toml) — release version pin
