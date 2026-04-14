---
name: check-pr-ready
description: PR 作成前の最終チェックリスト (lint/test/docs/CHANGELOG/未コミット確認)。/precheck の拡張版で、ドキュメント整合性も検証します。
argument-hint: "[skip-tests]"
disable-model-invocation: true
allowed-tools: Bash(uv run *) Bash(cargo *) Bash(dotnet *) Bash(go *) Bash(node *) Bash(npm *) Bash(cmake *) Bash(ctest *) Bash(git *) Bash(gh *) Read Grep Glob
---

# PR 作成前 最終チェック

PR を出す前にすべての品質チェックを実行し、問題があればレポートします。
**マージ可能な状態か判定する** ことが目的です。

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- リモート差分 (dev との): !`git log --oneline dev..HEAD 2>/dev/null | head -10`
- 未コミット: !`git status --porcelain 2>/dev/null | head -20`
- 変更ファイル数: !`git diff --name-only dev..HEAD 2>/dev/null | wc -l | tr -d ' '`

## 実行手順 (順番通り、失敗したら停止して報告)

### Phase 1: ブランチと未コミット確認

1. ブランチが `dev` 以外であることを確認
2. 未コミット変更があれば、ユーザーに確認して `/commit` を促す
3. dev との差分が 1 コミット以上あることを確認 (空の PR を防ぐ)

### Phase 2: コードチェック

`$ARGUMENTS` に `skip-tests` が **含まれていない** 場合のみ、以下を実行:

4. **`/precheck` skill を実行** (lint + format + test)
   - 実装: precheck と同じロジックを直接実行 (lint + format + scope-detected tests)
5. 失敗があれば即停止し、修正案を提示

### Phase 3: ドキュメント整合性チェック

6. **CLAUDE.md 更新確認**:
   - `git diff dev..HEAD --name-only` で大きな機能追加 (50 行以上の新規ファイル) を検出
   - 検出された場合、`CLAUDE.md` が同じ PR で更新されているか確認
   - 未更新なら警告 (機能の追加箇所と CLAUDE.md のセクション提案)

7. **README 更新確認**:
   - 同様に、README.md / src/python_run/README.md / src/wasm/openjtalk-web/README.npm.md を確認
   - 機能名や API が変わっている場合は更新を促す

8. **CHANGELOG 更新確認**:
   - `CHANGELOG.md` の Unreleased セクションが更新されているか確認
   - 大きな機能追加なら未更新を警告

9. **docstring カバレッジ確認** (Python の場合):
   - `git diff dev..HEAD --name-only -- 'src/python_run/piper/*.py' 'src/python/g2p/*.py'`
   - 新規 public 関数/クラスに docstring があるかチェック (簡易)

### Phase 4: PR 本文ドラフト

10. 上記すべてが OK なら、PR 本文のドラフトを生成:
    - タイトル: dev..HEAD の最初のコミット件名 (70 文字以内)
    - Summary: 各コミットの要約から 3-5 個の bullet
    - Test plan: 実行したチェックの結果 checklist
    - 形式は `gh pr create --body "$(cat <<'EOF' ... EOF\n)"` で渡せる Markdown

### Phase 5: 最終判定

11. すべて緑 → 「PR 作成準備完了」と報告し、`gh pr create` コマンドの提案を出力
12. 1 つでも警告/失敗 → 修正項目をリスト化、緑にしてから再実行を促す

## 報告フォーマット

```
## PR Ready Check 結果

### Phase 1: ブランチ
- [x] ブランチ: feat/xxx (dev ではない)
- [x] 未コミット: 0 件
- [x] dev との差分: 5 コミット

### Phase 2: コードチェック
- [x] Python ruff check
- [x] Python ruff format
- [x] Python pytest (212 passed)
- [x] WASM npm test (481 passed)

### Phase 3: ドキュメント
- [x] CLAUDE.md 更新済み
- [x] README 更新済み
- [ ] ⚠️ CHANGELOG.md Unreleased 未更新

### Phase 4: PR 本文ドラフト
(生成された PR 本文)

### 判定: ⚠️ 1 件の警告あり (CHANGELOG)
修正してから再実行してください。
```

## 注意

- ユーザーが `skip-tests` 引数を渡した場合は Phase 2 のみスキップ (緊急修正用)
- pytest.ini の `--cov` に注意: `-o addopts=""` で上書き
- 大規模機能 (>100 行) では CLAUDE.md / CHANGELOG / docs/features の更新を必須とする
- PR 作成自体は Phase 5 の **提案だけ** で、実行はユーザーに任せる
