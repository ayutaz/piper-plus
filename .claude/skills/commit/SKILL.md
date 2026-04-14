---
name: commit
description: piper-plus のコミットルール (CLAUDE.md 準拠) でステージ済みファイルをコミットします。--no-verify 禁止、HEREDOC、適切な prefix を強制。
argument-hint: "[optional commit message]"
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git log *) Bash(git add *) Bash(git commit *) Bash(git rev-parse *)
---

# piper-plus 向けコミット

CLAUDE.md のコミット規約に従い、ステージ済みまたは指定ファイルを安全にコミットします。

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 直近のコミット: !`git log -3 --oneline`
- ステージ状態: !`git status --short`
- 差分サマリ: !`git diff --stat HEAD`

## 手順

> **💡 大規模変更の場合**: `/sync-docs` を先に呼び出してドキュメント整合性を確認することを推奨します。このスキルはステップ 2.5 でその判定を行います。

### 1. ブランチ確認

現在のブランチを確認し、`dev` の場合はユーザーに確認を取る (CLAUDE.md: 通常はフィーチャーブランチで作業)。

### 2. 変更内容の把握

- `git status --short` で変更ファイルを確認
- `git diff` で内容を簡単にレビュー
- `.env`, `.env.*`, `credentials*`, `*.pem`, `*.key` 等の秘密情報が含まれていないか **必ず** チェック
- 含まれていたら **即中止** してユーザーに報告

### 2.5. ドキュメント同期チェック

コード変更のサイズと種類に応じて、ドキュメント更新が必要か判定します。

#### 判定基準

以下のいずれかに該当する場合、**`/sync-docs` skill を呼び出すことを強く推奨**:

- [ ] `git diff --stat` の変更行数が **100 行以上**
- [ ] `src/python_run/piper/` / `src/python/g2p/` / `src/rust/piper-core/` / `src/cpp/` / `src/csharp/` / `src/go/` / `src/wasm/openjtalk-web/src/` に新規ファイルが追加されている
- [ ] 公開 API (関数シグネチャ、クラス、メソッド、HTTP エンドポイント) に変更がある
- [ ] `piper_train` / `timing` / `voice` / `phonemize` / `config` などのコアモジュールが変更されている
- [ ] 新規テストファイル (`tests/test_*.py`, `test/js/test-*.js`, etc.) が 3 つ以上追加されている

#### アクション

1. **大規模/コア変更** → ユーザーに `/sync-docs` の実行を促す:
   > このコミットには X 件のコア変更が含まれます。`/sync-docs` でドキュメント整合性を監査してからコミットしますか?

2. **小規模変更 (< 100 行、ドキュメントのみ、テストのみ、バグ修正)** → スキップ可
3. **ユーザーが「スキップ」を選択** → 警告のみ表示して続行

このステップは **informational** です。ユーザーが明示的にスキップを選べば、コミット自体はブロックしません。

### 3. ファイルのステージング

- ユーザーが既にステージしている場合はそのまま使用
- 必要なら関連ファイルだけを `git add <file1> <file2>` で個別追加
- **`git add -A` / `git add .` は禁止** (誤って秘密情報をステージするリスク)

### 4. コミットメッセージ生成

`$ARGUMENTS` がある場合はそれを優先。なければ変更内容から自動生成:

#### Prefix 規約

| Prefix | 用途 |
|--------|------|
| `feat(<scope>):` | 新機能 (scope = python/rust/cpp/cs/go/wasm/ci/docs) |
| `fix(<scope>):` | バグ修正 |
| `refactor(<scope>):` | リファクタ (機能変更なし) |
| `docs:` | ドキュメントのみ |
| `test:` | テスト追加・修正 |
| `chore(<scope>):` | ビルド/依存/雑務 |
| `perf(<scope>):` | パフォーマンス改善 |

#### メッセージ本文の規約

- 1-2 文、why を強調
- 日本語可
- 命令形ではなく事実の記述 ("Add X" ではなく "X を追加")
- 詳細は本文に bullet で記述 (短いタイトルだけでなく)

### 5. コミット実行

**必須形式: HEREDOC**

```bash
git commit -m "$(cat <<'EOF'
<prefix>(<scope>): <summary>

- <detail 1>
- <detail 2>
EOF
)"
```

### 6. 禁止事項 (CLAUDE.md より)

- ❌ `--no-verify` (pre-commit hook を skip しない)
- ❌ `--no-gpg-sign` (署名を skip しない)
- ❌ `--amend` は明示要求がない限り使用しない (新コミットを作る)
- ❌ 既存の published コミットの修正
- ❌ `git config` の変更
- ❌ pre-commit hook が失敗したら、原因を修正して **新しいコミット** を作る (amend ではなく)

### 7. pre-commit hook 失敗時

pre-commit hook (例: ruff format hook) が失敗したら:

1. エラー内容を確認
2. 原因を修正 (ruff format/check --fix を手動実行など)
3. 修正したファイルを `git add` で再ステージ
4. **新しいコミット** を作成 (amend ではない)
5. ユーザーに「hook が失敗したので修正後に再コミットした」と報告

### 8. 成功後の報告

```
✅ コミット成功
- ハッシュ: abc1234
- メッセージ: feat(python): ...
- ファイル: 5 changed (+120 -30)
- ドキュメント同期: ✅ (完了) / ⚠️ (未実行・推奨) / - (小規模のためスキップ)

push する場合:
  git push origin <branch-name>

PR 作成する場合:
  /check-pr-ready で最終チェック
```

## 注意

- push は実行しない (明示要求があるまで)
- PR は作成しない
- 1 コミットで複数の論理的に異なる変更を混ぜない
- 大きな変更は複数の小さなコミットに分割することを提案
