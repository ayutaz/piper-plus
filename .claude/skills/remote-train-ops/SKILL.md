---
name: remote-train-ops
description: vast.ai 等のリモート GPU instance での学習運用 (レンタル/デプロイ/監視/停止) の標準手順と事故防止チェックリスト。v11 Phase B/C で実測した 6 クラスの運用事故 (無言死・監視不達・pin 不整合・pkill 自己マッチ・遅い box の見逃し・幽霊起動) の再発防止。instance を触る作業はすべて本 skill の手順に従う。
argument-hint: "[rent|deploy|monitor|stop] (任意)"
disable-model-invocation: false
allowed-tools: Bash(vastai *) Bash(ssh *) Bash(scp *) Read Grep
---

# リモート学習運用 Skill

vast.ai instance での学習運用の標準手順。v11 Phase B/C (2026-08) で実測した
運用事故 6 クラスとその対策を制度化する。**GPU 遊休の課金は事故 1 回あたり
$10-50 の実害** — 手順の省略は費用に直結する。

## 事故クラスと対策 (実測に基づく)

| # | 事故 | 実測 | 対策 (本 skill の手順) |
|---|------|------|------|
| 1 | **スクリプトの無言死** (`set -u` 未定義変数等で die/marker を通らず終了) | VRAM_PEAK unbound で 4.5h+8.7h 空転 | §2-3: 全スクリプトに ERR trap 必須 + 起動後 30 秒でログ確認 |
| 2 | **Monitor 通知不達** | 3 回 (SMOKE_FAILED を検知せず計 ~27h 遊休) | §4: 重要な完了待ちは Monitor でなく **背景 Bash until ループ** (完了時に必ず 1 回通知される) |
| 3 | **pin 不整合** (local script / remote script / repo rev の 3 点ズレ) | 2 回 (pin 違反で即死) | §2: 「local 更新 → 全 3 点を同時 bump → scp → remote で md5 照合」の順序を厳守。remote だけ sed しない |
| 4 | **pkill 自己マッチ** | 3 回 (ssh ごと死んで無言) | kill と起動は**別々の Bash/ssh 呼び出し**に分ける ([x] エスケープでは不十分)。guard-bash hook が同一コマンド連結を block する |
| 5 | **遅い box の見逃し** | PCIe box が 6.4x 遅く $60 浪費 | §1: レンタル直後・データ DL **前**に 25-batch 速度サニティ。予算導出の sec/step 上限で gate |
| 6 | **幽霊起動** (queued start の遅延発火) | v10b instance が勝手に再起動し ~$50 浪費 | §5: `vastai start` がキューされたら**必ず台帳に記録**し、不要になったら `vastai stop` を明示発行。stop/destroy 後は `vastai show instances` で全台の actual_status を確認 |

## 1. レンタル

```bash
vastai search offers 'num_gpus=4 gpu_name=A100_SXM4 reliability>0.99 duration>3 disk_space>800 inet_down>1' -o 'dph' --raw
vastai create instance <id> --image nvidia/cuda:12.8.1-devel-ubuntu24.04 --disk 900 --label <purpose>
```

- **SXM4 を優先** (A100 PCIe box は同価格帯で 6.4x 遅い実測あり。PCIe は DDP
  allreduce 税も重い)。price は市場変動する — レンタル時に再検索
- 起動後、**データ DL 前に速度サニティ**: base 構成 25 batch (1 GPU) を回し、
  予算から導出した sec/step 上限 (80ep × epoch_steps × sec/step × $/hr ≤ 予算)
  を超える box は即 destroy して別を探す。bootstrap ~2-3h を無駄にしない

## 2. デプロイ (pin 同期の不変手順)

1. **local (scratchpad) のスクリプトを先に編集** — remote を直接 sed しない
2. 編集は Write/Edit ツールで行う。**bash heredoc への `\` を含む文字列の埋め込みは
   エスケープが層で潰れる既知の罠** (3 回実測) — heredoc パッチが必要な場合は
   Python 側で `BS = chr(92)` を使って組み立てる
3. pin (repo rev) を bump する場合は **local の全スクリプトを同時に** bump
4. `bash -n` (構文) → scp → remote で `sed -i 's/\r$//'` + `bash -n` + pin 値の
   grep 照合、まで 1 セット
5. スクリプトの canonical は HF (`<run>-results/scripts/`) — ランディング毎に退避

## 3. スクリプト規約 (無言死の根絶)

- 冒頭に `set -euo pipefail` + **ERR trap 必須**:
  ```bash
  trap 'mark "<RUN>_FAILED: line $LINENO: $BASH_COMMAND (exit $?)"' ERR
  ```
  これが無いと `set -u` の未定義変数や途中コマンドの失敗が **marker を残さず
  無言死**し、監視が「まだ走っている」と誤認する
- 失敗 marker (`*_FAILED`) は必ず log の**新しい行**として出す (監視の grep 対象)
- 起動後 30 秒でログ末尾を必ず確認 (「launched」だけでなく次の STEP が出るまで)

## 4. 監視 (通知が確実に届く形)

- **重要な完了待ち (smoke 判定 / bootstrap 完了 / 本走完走) は背景 Bash の
  until ループ**で待つ — 完了時に必ず 1 回のタスク完了通知が届く:
  ```bash
  # run_in_background: true で実行
  until ssh ... 'tail -20 <log> | grep -qE "DONE|FAILED"' </dev/null; do sleep 120; done
  ssh ... 'tail -10 <log>'
  ```
- Monitor ツールは補助 (定期進捗の可視化) に留める — **通知不達が 3 回実測**
  されており、単独では费用事故を防げない
- 判定条件は「アンカー行 (最新 launch マーカー) 以降のみ」を対象にする —
  ログ累積で過去の FAILED に誤マッチする事故も実測済み
- ssh 内の grep には `</dev/null` を付ける (stdin 吸い込みハング防止)

## 5. 停止・destroy (課金の確実な停止)

1. `vastai stop instance <id>` → **数秒後に `vastai show instances` で
   actual_status を必ず確認** (intended と actual の両方)
2. `vastai start` が "queued" を返した場合は要注意 — **GPU が空いた時点で
   遅延発火して勝手に課金が再開する** (実測 ~$50)。不要になったら明示的に
   stop/destroy して台帳確認
3. destroy は不可逆 — 先に **退避チェックリスト**: ckpt (HF) / 評価 JSON (HF) /
   較正・smoke レポート (HF) / 実行スクリプト (HF) / 聴感 wav (ローカル)。
   destroy は `echo y | vastai destroy instance <id>` (確認プロンプトあり)
4. 作業の節目 (フェーズ完了・失敗で停止した時) には**全 instance の一覧**を
   確認する — 自分のセッション外の instance には触らない

## 6. resume の前提

- ckpt は HF に epoch ごと退避されている前提 (uploader の稼働をログで確認)
- 新 box での resume は: bootstrap → ckpt を `checkpoints/last.ckpt` に配置 →
  **較正 JSON (`*_calibration.json`) も HF から復元** (無いと hparams 検査が
  default 値と比較して誤 ABORT する — 実測) → 同一 env override で launch
