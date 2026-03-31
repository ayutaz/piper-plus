# P1-008: pyproject.toml extras 拡張

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-103
> 依存チケット: P1-001, P1-002, P1-003, P1-004, P1-005 (全言語 Phonemizer)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

Phase 0 で作成した `pyproject.toml` に残り 5 言語の optional extras を追加し、`uv pip install piper-g2p[all]` で全言語の依存が一括インストールできるようにする。ルールベース言語 (ES/FR/PT) は外部依存がないため、extras 定義のみで実質的な依存追加はない。

### ゴール

- `uv pip install piper-g2p[zh]` で pypinyin がインストールされる
- `uv pip install piper-g2p[ko]` で g2pk2 がインストールされる
- `uv pip install piper-g2p[es]` / `[fr]` / `[pt]` が定義されている (空 extras)
- `uv pip install piper-g2p[all]` で JA+EN+ZH+KO+ES+FR+PT の全依存がインストールされる
- 各 extras の依存バージョン制約が正しい

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/pyproject.toml` | extras 拡張 |

### 実装手順

1. 既存の `pyproject.toml` の `[project.optional-dependencies]` セクションを拡張
2. 以下の extras を追加:

```toml
[project.optional-dependencies]
# Phase 0 (既存)
ja = ["pyopenjtalk-plus>=0.3.0; platform_machine != 'aarch64'",
      "pyopenjtalk>=0.3.0; platform_machine == 'aarch64'"]
en = ["g2p-en>=2.1.0"]

# Phase 1 (新規)
zh = ["pypinyin>=0.50"]
ko = ["g2pk2>=0.0.3"]
es = []  # ルールベース、外部依存なし
fr = []  # ルールベース、外部依存なし
pt = []  # ルールベース、外部依存なし

# 全言語一括
all = ["piper-g2p[ja,en,zh,ko,es,fr,pt]"]

# 開発用
dev = ["pytest>=7.0", "ruff>=0.4.0"]
```

3. `project.classifiers` に対応言語を追加:

```toml
classifiers = [
    "Natural Language :: Japanese",
    "Natural Language :: English",
    "Natural Language :: Chinese (Simplified)",
    "Natural Language :: Korean",
    "Natural Language :: Spanish",
    "Natural Language :: French",
    "Natural Language :: Portuguese",
]
```

4. インストールテストを実行して全 extras が動作することを確認

### API / インターフェース

該当なし (パッケージメタデータの変更のみ)。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | pyproject.toml の編集、インストールテスト |

---

## 4. テスト計画

### 提供範囲

各 extras が正しい依存をインストールし、対応言語の Phonemizer が動作すること。

### Unit テスト

| テストケース | コマンド | 期待結果 |
|-------------|---------|---------|
| zh extras | `uv pip install piper-g2p[zh]` | `import pypinyin` 成功 |
| ko extras | `uv pip install piper-g2p[ko]` | `import g2pk2` 成功 |
| es extras | `uv pip install piper-g2p[es]` | インストール成功 (追加依存なし) |
| fr extras | `uv pip install piper-g2p[fr]` | インストール成功 (追加依存なし) |
| pt extras | `uv pip install piper-g2p[pt]` | インストール成功 (追加依存なし) |
| all extras | `uv pip install piper-g2p[all]` | 全依存がインストールされる |
| コアのみ | `uv pip install piper-g2p` | 外部依存なしで成功 |

### E2E テスト

- `piper-g2p[all]` インストール後に `available_languages()` が 7 言語を返すこと
- 各言語の `get_phonemizer()` が正しいインスタンスを返すこと

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **g2pk2 の transitive 依存**: g2pk2 は内部で `python-mecab-ko` を使用し、これが C 拡張を含む。一部プラットフォーム (Windows ARM64) でビルドに失敗する可能性がある。`ko` extras のドキュメントに注意事項を追記する。
- **pypinyin のバージョン制約**: `>=0.50` は保守的だが、pypinyin の内部 API 変更でピンイン出力形式が変わる可能性がある。CI でバージョンロックテストを追加する。
- **空 extras の意義**: ES/FR/PT の空 extras は実質的な効果がないが、将来の依存追加時の後方互換性と、`[all]` の構文上の一貫性のために定義する。
- **self-referencing extras**: `all = ["piper-g2p[ja,en,zh,ko,es,fr,pt]"]` の self-reference が pip/uv で正しく解決されることを確認する。対応していない場合は展開形式 `all = ["pyopenjtalk-plus...", "g2p-en...", "pypinyin...", ...]` を使用する。

### レビュー項目

- [ ] 全 7 言語の extras が定義されていること
- [ ] `all` extras が全言語の依存を含むこと
- [ ] バージョン制約が適切であること
- [ ] classifiers に全言語が含まれること
- [ ] `uv pip install piper-g2p` (コアのみ) が外部依存なしで成功すること

---

## 6. 一から作り直すとしたら

extras の命名規則を ISO 639-1 コードに統一する方針は現在と同じでよい。ただし、`ko` extras の g2pk2 依存が重い (tensorflow 等の transitive 依存) ため、軽量フォールバック (ルールベース韓国語 G2P) を `ko-lite` extras として別途提供することも検討する。

---

## 7. 後続タスクへの連絡事項

- P1-009 (ドキュメント): 各 extras のインストールコマンドを README に記載
- P1-011 (API 凍結): extras 名は v1.0.0 で確定、後方互換性を維持する
- CI: `g2p-python-ci.yml` のテストマトリクスに extras 別のインストールテストを追加
