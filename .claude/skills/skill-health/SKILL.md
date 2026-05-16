---
name: skill-health
description: `.claude/skills/*/SKILL.md` の frontmatter / referenced script 実在 / trigger 衝突 / `.claude/hooks/*.sh` の executable+shebang を検査する meta-skill。 メタワークフロー監査で「hook script rot が最高リスク」と判明したため、 commit 前または skill 編集後に呼んで health check を行う。
disable-model-invocation: false
allowed-tools: Bash(uv run *) Bash(ls *) Bash(test *) Bash(file *) Bash(stat *) Read Grep
---

# Skill / Hook Health Check

このプロジェクトの自動化資産 (16 skill + 5 hook + 49 pre-commit hook) を meta-level で健全性検証する。

memory `feedback_conservative_changes.md` に従い、 read-only、 検査結果を report として返すのみ。 修正は別 skill / 手動で。

## カバー範囲

| 検証対象 | 内容 |
|---------|------|
| SKILL.md frontmatter | name / description / allowed-tools の必須 key、 description 長 |
| name ↔ directory 一致 | `.claude/skills/foo/SKILL.md` の `name: foo` であること |
| scripts/*.py 参照 | SKILL.md 内で参照されるスクリプトが repo 内に実在 |
| trigger 衝突 | 複数 skill の description で同じ 「...」 が使われていないか |
| hook 実行可能性 | `.claude/hooks/*.sh` の executable bit + shebang |

## 実行ステップ

### 1. 検査スクリプト実行

```bash
uv run python scripts/check_skill_health.py --verbose
```

期待出力例:

```text
inspected 16 skills, 5 hooks
OK skill-health: 16 skill(s), 5 hook(s) inspected
```

### 2. 失敗時の対応

| エラー種別 | 修正案 |
|----------|------|
| `frontmatter not parseable` | YAML 構文エラー。 `---` 行 + key: value を見直す |
| `missing frontmatter key: name` | SKILL.md 冒頭に name 追加 |
| `name does not match directory` | ディレクトリ名と SKILL.md の name を揃える |
| `references <path> but file does not exist` | 参照されるスクリプトを作るか SKILL.md から消す |
| `trigger fragment used by: [...]` | 複数 skill で同じ trigger 文言 → どちらかを書き換えて曖昧性除去 |
| `not executable` | `chmod +x .claude/hooks/*.sh` |
| `no shebang on line 1` | `#!/usr/bin/env bash` を 1 行目に追加 |

### 3. CI 連携

このチェック自体は CI gate にする選択もあるが、 false positive (trigger 衝突警告は意図的なケースもある) のため pre-commit には入れずに skill 経由で呼ぶ。

将来、 false positive を減らせた段階で pre-commit hook 化を検討。

## 注意

- **memory feedback_conservative_changes**: 自動修復しない。 検査結果のみ。
- **trigger 衝突**: 「コミット前」 のような短い fragment は多数 skill に出現しても問題ないが、 「6 エージェント並列レビュー」 のような特定 skill 専用文言が他に漏れていたら衝突。
- **frontmatter 長さ警告**: description は 80-400 chars が推奨。 800 chars 超は単一文を超えており指針違反。

## 使用例

```text
# 全 skill / hook の health check
/skill-health

# verbose で全 skill / hook を一覧
/skill-health verbose
```

## 期待効果

- skill / hook の **script reference rot** を pre-commit 入れなくても定期検査可
- `name ↔ directory` ミスマッチ (skill 追加時の rename 忘れ) の早期発見
- **trigger 衝突** の検出 (どの skill が呼ばれるべきか LLM に曖昧)
- `.claude/hooks/*.sh` の **shebang 漏れ / executable 漏れ** 防止
