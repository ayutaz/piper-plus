---
name: create-pr
description: 「PR を作って」「pull request を出して」要求で発動。 push → 構造化 PR 本文 (pull_request_template.md 準拠) で PR 作成 → CI 監視ループ → review thread 返信+resolve まで 1 skill で完結。 skill 間 handoff を排除し工程の取りこぼしを防ぐ。 マイルストーン非付与、 auto-merge 非使用。
argument-hint: "[base-branch] [--title <title>] [--no-watch]"
disable-model-invocation: false
allowed-tools: Bash(git *) Bash(gh *) Bash(sleep *) Bash(python *) Bash(cat *) Read Write ScheduleWakeup TaskList TaskStop
---

# PR 作成 + CI 監視 + レビュー対応 (end-to-end)

`/create-pr` 1 コマンドで PR ライフサイクル全体を完結する skill:

**push → PR 作成 → CI 監視ループ → review thread 返信 + resolve → 報告**

過去 `/create-pr` → `/watch-pr` → `/reply-review` を別々の skill 呼び出しで連鎖していたが、 「次の skill を Skill ツールで呼べ」 という散文 handoff は LLM が実行を飛ばすと工程が抜ける (PR #496 / #505 で発生)。 本 skill は全工程を **inline フェーズ** として持ち、 skill 間 handoff をゼロにする。

> 単体利用: CI 監視のみ → `/watch-pr <PR#>`、 review 対応のみ → `/reply-review <PR#>`、 backlog 集計 → `/check-review-backlog`。 これらは本 skill のフェーズ 5 / 6 と同一手順の standalone 版。

## 自動発動条件

- 「PR を作って / 出して」「pull request を作って」「この変更で PR にして」「branch を push して PR にして」

明示呼び出し: `/create-pr` / `/create-pr <base-branch>` / `/create-pr --no-watch` (PR 作成のみ、 監視ループに入らない)

## 引数

- `$ARGUMENTS` 空: base = `dev` (memory `feedback_merge_caution`: 通常 dev を base)
- `<base-branch>`: 明示指定 (例: `main`)
- `--title <title>`: title 上書き (デフォルトは最新コミット message から抽出)
- `--no-watch`: フェーズ 5/6 (CI 監視・review 対応) を skip し PR 作成で終了

## 制約 (memory 参照)

- **マイルストーン非付与** (`feedback_pr_no_milestones`): `--milestone` を付けない。 本文に「M1」等も書かない
- **auto-merge 禁止** (`feedback_merge_caution`): `gh pr merge --auto` 等を使わない。 マージはユーザー判断
- **本文書き換えは body-file** (`feedback_pr_body_over_comments`): 既存 PR 更新は `gh pr edit --body-file`。 新規コメント追記しない。 review thread への reply はこの制約の対象外
- **--no-verify 禁止** (CLAUDE.md): hook bypass 系を使わない
- **review thread の自動 reply は SAFE 系のみ**: stale / Copilot style noise のみ自動 reply+resolve。 人間 reviewer・logic/security 指摘は user 判断 (フェーズ 6)

## PR 本文フォーマット (重要 — テンプレート準拠必須)

**PR 本文は `.github/pull_request_template.md` の必須セクションをすべて含むこと。** `validate-pr-body` CI ゲートが以下を検査し、 欠けると PR が必ず red になる (PR #505 で発生した既知バグ — 旧フォーマットはこのゲートを通らなかった):

- `## Test Plan` セクションが存在し非空 (**大文字 P**。 `## Test plan` は grep `^## Test Plan` に不一致で fail)
- `## Risk Level` セクションでチェックボックスがちょうど **1 個** `- [x]`
- `## Affected Components` セクションでチェックボックス最低 1 個 `- [x]`

PR title は **70 文字以内**、 `type(scope):` prefix (例 `fix(g2p):` `ci:` `feat(workflow):`)。

PR 本文は以下を **この順** で含める (1-8 は template 準拠の必須セクション、 9-10 は create-pr 独自の value-add):

1. `## Summary` — 解決する問題 / 動機 (1-3 文)。 時系列表現 (Phase 1/2) は使わない
2. `## Affected Components` — 該当を `- [x]`: Python / Rust / C# / C++ / Go / WASM-npm / Docker / CI-CD / Documentation
3. `## Type` — Bug fix / New feature / Refactoring / Documentation / CI/CD / Dependencies
4. `## Risk Level` — patch / minor / major の **ちょうど 1 個**を `- [x]` (patch=bugfix/内部, minor=新機能/非破壊, major=破壊的変更)
5. `## Contract Impact` — `docs/spec/*.toml` 影響。 無ければ `- [x] None`
6. `## 変更内容` — 機能カテゴリ別の表 `機能名 / 動作 / これがないと起こること` の 3 列
7. `## 設計判断` — 意思決定の根拠 bullet (conservative/aggressive 判断・誤検出回避・bypass 経路・既存整合)
8. `## Test Plan` — `- [ ]` で reviewer がそのまま使える具体的手順 (抽象表現禁止)
9. `## Checklist` — Tests pass locally / No GPL-LGPL deps / Documentation updated
10. `## Related Issues` — `Closes #N` 等、 無ければ「なし」

禁止: 時系列 (Phase/開発過程)、 マイルストーン番号、 「LLM が生成」 等の co-authored note。

## 実行手順

### フェーズ 1: ブランチ状態確認

```bash
git status --short
git log --oneline <base>..HEAD
git diff --stat <base>..HEAD
git rev-parse --abbrev-ref HEAD
git rev-parse --abbrev-ref @{u} 2>/dev/null || echo "no-upstream"
```

確認: working tree、 commit が 1 つ以上 ahead か、 upstream 設定済みか。 ブランチが `dev`/`main` なら停止 (feature ブランチ必須)。

### フェーズ 2: PR 本文 draft 作成

`git log <base>..HEAD --pretty=format:"%h %s%n%b"` で全 commit を読み、 機能カテゴリ・規模・トレードオフを抽出。 上記 10 セクションを埋めて `/tmp/pr-body-<branch-slug>.md` に書き出す。

### フェーズ 2.5: PR 本文 self-check (validate-pr-body 先取り)

push 前に必須セクションを検証する。 1 つでも欠けたら修正してからフェーズ 3 へ:

```bash
B=/tmp/pr-body-<branch-slug>.md
for s in "## Summary" "## Affected Components" "## Type" "## Risk Level" "## Contract Impact" "## Test Plan" "## Checklist" "## Related Issues"; do
  grep -qF "$s" "$B" || echo "MISSING: $s"
done
# Risk Level は [x] ちょうど 1 個であること (出力が 1 でなければ fail)
awk '/^## Risk Level/{f=1;next}/^## /{f=0}f' "$B" | grep -cE '^- \[x\] '
# Affected Components は [x] 1 個以上
awk '/^## Affected Components/{f=1;next}/^## /{f=0}f' "$B" | grep -cE '^- \[x\] '
```

### フェーズ 3: push

```bash
git push -u origin <branch-name>   # upstream 未設定時。 設定済みなら git push
```

### フェーズ 4: PR 作成 / 既存 PR 更新

`gh pr list --head <branch> --json number` で既存 PR を判定:

```bash
# 新規
gh pr create --base <base> --title "<title>" --body-file /tmp/pr-body-<branch-slug>.md
# 既存 (本ブランチに PR があれば本文置換)
gh pr edit <PR#> --body-file /tmp/pr-body-<branch-slug>.md
```

`--milestone` は付けない。 PR URL / 番号を控える。

`--no-watch` 指定時はここで終了 (PR URL を報告)。 それ以外はフェーズ 5 へ自動継続 (確認を挟まない)。

### フェーズ 5: CI 監視ループ (inline — skill handoff なし)

PR 作成後、 CI を完了まで監視する。 **`/watch-pr` skill は呼ばず以下を本 skill 内で実行する。**

**5.1 ポーリング** — `gh pr checks <PR> --json name,bucket` を取得し bucket (pass/fail/pending/skipping/cancel) を集計。

**5.2 判定**:

- **pending ≥ 1** → 5.3 (継続監視)
- **fail = 0 かつ pending = 0** → all green。 フェーズ 6 を実行し all-resolved ならフェーズ 7 で完了報告
- **fail ≥ 1** → 5.4 (失敗分析) を実行後、 フェーズ 6 → フェーズ 7

**5.3 継続監視 (self-pace)**:

- background watcher が未 arm なら arm する (`Bash` を `run_in_background: true` で):
  `gh pr checks <PR> --json name,bucket` を ~120s 間隔でポーリングし、 pending=0 になったら集計行を出力して exit するループ。 完了通知でループに再入する。
- fallback として `ScheduleWakeup(delaySeconds=1800, prompt="/create-pr ...<元の引数>")` を設定。
- watcher 完了通知 か wakeup で 5.1 に再入。 各再入でフェーズ 6 (review) も実行する。
- 4 時間以上 pending が続く場合はループを終了し user に報告。

**5.4 失敗分析** — 失敗 job のログを `gh run view <run-id> --log-failed` で fetch し分類:

| 分類 | signature | 推奨アクション |
|------|-----------|---------------|
| format drift | `ruff` `cargo fmt` `gofmt` `clippy` 系 | `pre-commit run --all-files` で修復 |
| test fail | `FAILED` `assert` `panicked` | テスト名を抽出して提示 |
| build error | `error[E` `cannot find` | ログ提示、 user 方針確認 |
| flake | `timeout` `network` `rate limit` | `gh run rerun <id> --failed` 提案 |
| contract drift | `MISMATCH` `OUT OF SYNC` | 該当 `/check-*` skill 案内 |
| validate-pr-body | `Missing required section` | フェーズ 2 に戻り本文修正 → `gh pr edit --body-file` |

分類結果と推奨アクションを user に提示。 format drift / validate-pr-body は本 skill で修正→push まで実施してよい。 test/build error は user 判断。

### フェーズ 6: review thread 返信 + resolve (inline — skill handoff なし)

CI 監視の各 iteration および all-green 時に **必ず実行する。** `/reply-review` skill は呼ばず以下を実行:

**6.1 未解決 thread 取得**:

```bash
gh api graphql -f query='
query($pr: Int!) {
  repository(owner: "ayutaz", name: "piper-plus") {
    pullRequest(number: $pr) {
      reviewThreads(first: 50) { nodes {
        id isResolved
        comments(first: 1) { nodes {
          databaseId path body author { login } originalCommit { oid }
        } }
      } }
    }
  }
}' -F pr=<PR> --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'
```

**6.2 各 thread を分類**:

- **SAFE-stale**: コメント以降に該当ファイル更新済 (`git log <originalCommit.oid>..HEAD -- <path>` が非空)
- **SAFE-copilot-style**: Copilot bot (`author.login` = `copilot-pull-request-reviewer` or `*[bot]`) + style noise (`^Consider (using|renaming)\b` `^Optional:` `\bnit:` 等)
- **REVIEW-human**: author が人間 reviewer
- **REVIEW-blocker**: Copilot/CodeQL の logic / security / API 指摘 (style noise でない)

**6.3 SAFE 系の自動対応** — 各 SAFE thread に REST API で reply → GraphQL で resolve:

```bash
# reply (in_reply_to は REST の comment databaseId)
gh api repos/ayutaz/piper-plus/pulls/<PR>/comments --method POST \
  -F in_reply_to=<databaseId> -f body="対応しました (commit <hash>)。<要約>"
# resolve (threadId は GraphQL node ID)
gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=<threadId>
```

**6.4 REVIEW 系** — 自動 reply / resolve せず、 表形式で user に提示し判断を促す。 user が修正を指示したら: 修正 → commit → push → 該当 thread に reply (commit hash 付き) → resolve。 修正コミット後の reply+resolve を忘れないこと (PR #505 で抜けた工程)。

> 詳細な分類 regex と API の注意点 (node ID と databaseId の取り違え等) は `reply-review/SKILL.md` を参照。 手順自体は上記で完結している。

### フェーズ 7: 最終報告

```text
PR #<N>: https://github.com/ayutaz/piper-plus/pull/<N>

CI: <all green / red N 件 / pending N 件>
Review: <resolved N 件 / 自動対応 N 件 / user 判断待ち N 件>

次のアクション:
- <red なら> 失敗分類と推奨アクション
- <REVIEW 残あれば> user 判断が必要な thread
- <all green + resolved 全部> merge 判断は user に委ねる (auto-merge 禁止)
```

## guard hook 回避

PR body 内に `--no-verify` 等の禁止文字列があると pre-commit / GitHub hook が誤検出することがある:

- 実行コマンドは抽象表記にする (「auto-merge」「hook bypass フラグ」等)
- 禁止文字列を含めたい場合は `--body-file` 経由で渡す (引数で渡さない)

## 使用例

```text
/create-pr                          # dev base に PR 作成 → CI 監視 → review 対応まで自動
/create-pr main                     # main base
/create-pr --title "fix(g2p): ..."  # title 上書き
/create-pr --no-watch               # PR 作成のみ (監視ループに入らない)
```

## 関連 skill

- `/watch-pr <PR#>`: 本 skill フェーズ 5 の standalone 版 (既存 PR の CI 監視のみ)
- `/reply-review <PR#>`: 本 skill フェーズ 6 の standalone 版 (既存 PR の review 対応のみ)
- `/check-review-backlog`: 全 open PR の未解決 review 集計
- `/loop /watch-pr <PR#>`: CI を長時間継続監視 (本 skill フェーズ 5 を loop 化)
- `/sync-docs`: PR 作成前のドキュメント整合性監査 (推奨フロー: `/sync-docs` → `/create-pr`)

## 期待効果

- **skill 間 handoff ゼロ** — push / PR 作成 / CI 監視 / review 対応が 1 skill の連続フェーズ。 「次の skill を呼び忘れて工程が抜ける」 (PR #496 / #505) を構造的に防止
- PR 本文が `pull_request_template.md` 準拠で `validate-pr-body` を必ず通る
- PR body の構造標準化、 フェーズ/マイルストーン表記の排除
- review thread の reply+resolve 漏れ防止
