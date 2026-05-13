window.BENCHMARK_DATA = {
  "lastUpdate": 1778679324448,
  "repoUrl": "https://github.com/ayutaz/piper-plus",
  "entries": {
    "Python inference benchmark": [
      {
        "commit": {
          "author": {
            "email": "41669061+ayutaz@users.noreply.github.com",
            "name": "yousan",
            "username": "ayutaz"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7f0da7eaaca78529318d8d1626d1f1b04bdd203f",
          "message": "fix(ci): dev push 限定の RTF Regression / Docker Build 失敗を修正 + PR 検知拡張 (#463)\n\n* fix(ci): dev push 限定で連続失敗していた 2 workflow を修正\n\n- RTF Regression: benchmark-action@v1.20.4 は内部で\n  `git fetch ... gh-pages:gh-pages` を呼ぶため repo に gh-pages branch が\n  無いと `fatal: couldn't find remote ref gh-pages` で失敗していた\n  (header コメントの auto-push 期待と実挙動が異なる)。 Store step の前に\n  idempotent な gh-pages 初期化 step を追加し、 初回 dev push で空 orphan\n  commit を push して以降の baseline 比較を有効化する。\n- Docker Build (build-cpp-dev): `wget -q` で onnxruntime release-asset を\n  ダウンロードしていたため、 transient な GitHub redirect 失敗で silently\n  exit 1 → ビルド全体が落ちていた (dev push で 9+ 回連続失敗)。 curl\n  --retry 5 --retry-all-errors に置換し、 retry / progress を可視化。\n- pre-commit hadolint hook を CI と揃え (`--failure-threshold=error`):\n  既存 warning (DL3015/DL4001 等、 .hadolint.yaml で error 化していない)\n  でローカル commit が silently 落ちる drift を解消。\n\n* fix(ci): dev push 限定の失敗を PR 段階で検知できるよう trigger 拡張\n\nこれまで Docker Build / RTF Regression の dev push 限定失敗は PR で\n検知できず、 dev へマージしてから事故るループだった (PR #463 自体は\nfix だけ。 これは原因系の再発防止)。\n\nDocker Build (docker-build.yml):\n- trigger に `pull_request: branches: [dev]` を追加 (paths は push と\n  同じ)。 PR で全 7 Dockerfile を build-only で回し、 wget silent fail /\n  apt package 不在等の Dockerfile 起因問題を PR で fail-fast。\n- `docker/build-push-action.with.push` を `true` から\n  `${{ github.event_name != 'pull_request' }}` へ条件化 (全 10 step)。\n  PR では push しない、 push event でのみ ghcr.io / Docker Hub へ push。\n- `docker/login-action` (ghcr.io login) も `if: github.event_name !=\n  'pull_request'` で gate (全 7 step)。 fork PR で write token 不在の\n  ため落ちるのも回避。\n- Docker Hub login と cosign installer / sign は既に tag ref で\n  gate 済みのため触らない (PR では既に skip)。\n- concurrency group を追加: PR は cancel-in-progress=true で古い build を\n  cancel、 push to dev は cancel-in-progress=false (image push 途中で\n  止めるとレジストリが不整合になり得るため)。\n\nRTF Regression (rtf-regression.yml):\n- `Ensure gh-pages branch exists` step を PR でも実行する形に拡張。\n  PR: read-only check で不在なら `::error::` で fail し、 push to dev\n  が落ちる前に PR 段階で surface する。 push to dev: 不在なら従来通り\n  空 orphan commit で作成。 fork PR は job-level if で既に skip。\n\n* fix(docker/cpp-dev): ONNX Runtime v1.20.0 layout 変更で cp が directory を落とす真因を修正\n\nPR #463 で trigger を PR に拡張したことで、 dev 連続 9 回失敗の真因が\nようやく surface した。 `wget -q` が silent fail していたわけではなく、\nONNX Runtime v1.20.0 が `lib/cmake/` と `lib/pkgconfig/` を lib/ 配下に\nsubdirectory として同梱しており、 `cp onnxruntime-.../lib/* /usr/local/lib/`\nが `cp: -r not specified; omitting directory` で exit 1 になっていた。\n\n`wget -q` は download 自体は成功させていて、 後段の cp が失敗 → bash\n`set -o pipefail` + && chain で全体が exit 1 → 元コミットでは\n\"wget exit 1\" のように見えていた。 curl にしたことで cp の stderr が\nbuild log に visible になり、 PR 段階で真因特定できた。\n\n修正: `cp` → `cp -r` (include 側と対称)。\n\n* fix(ci): Copilot review #463 対応 (worktree 経由 orphan / curl コメント精緻化)\n\n- rtf-regression.yml: gh-pages 初期化を `git switch --orphan` から\n  `git worktree add --orphan -b gh-pages` に変更。 dev checkout の\n  working tree を一切触らず一時 worktree でだけ orphan commit を作って\n  push する。 `git switch --orphan` も Git 2.27+ では working tree を\n  clear するが、 version dependent な挙動より明示的な isolation の\n  ほうが読み手にも自明。 checkout-back conflict も発生しない。\n- docker/cpp-dev/Dockerfile: コメントの「retry / progress を可視化」\n  が誤り (`-fsSL` の `-s` は progress bar 抑制) だったので修正。\n  実際の curl 置換の目的は (1) 真因が cp side だったため後段エラーが\n  build log で visible になること、 (2) `--retry-all-errors` で\n  transient redirect/network 失敗を retry すること、 (3) `-fS` の組合せ\n  で curl 自身のエラーは silent でなく stderr に出すこと。 `-s` は\n  build log が膨大化しないよう意図的に維持。\n\n* fix(ci/rtf): PR で gh-pages 不在を warning にする (chicken-and-egg 回避)\n\nPR #463 の trigger 拡張で意図通り PR で gh-pages 不在を検知できるよう\nになったが、 「初回 dev push 前は gh-pages が必ず不在」という\nchicken-and-egg があり、 fail にすると PR を merge できない。\n\n→ `::error::` を `::warning::` に変更し、 step 自体は success させる。\n通常運用 (gh-pages 作成後) では silent pass、 万一 gh-pages が削除\nされた場合は warning で flag するが merge は可能 (直後の dev push で\n自動再生成される)。\n\ngh-pages の直 push を avoid: 副作用が大きい (public な GitHub Pages\nsurface を作ってしまう) ため CI workflow 側で対応する保守的アプローチ。",
          "timestamp": "2026-05-13T22:33:39+09:00",
          "tree_id": "3e5605ffba7616f7a699db8cfb09580816060466",
          "url": "https://github.com/ayutaz/piper-plus/commit/7f0da7eaaca78529318d8d1626d1f1b04bdd203f"
        },
        "date": 1778679323166,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "RTF (en)",
            "value": 0.1012,
            "unit": "ratio"
          },
          {
            "name": "Latency P50 (en)",
            "value": 25.9,
            "unit": "ms"
          },
          {
            "name": "Latency P95 (en)",
            "value": 26,
            "unit": "ms"
          },
          {
            "name": "Cold Start (en)",
            "value": 1387.8,
            "unit": "ms"
          },
          {
            "name": "Peak Memory (en)",
            "value": 209.7,
            "unit": "MB"
          },
          {
            "name": "Model Size (en)",
            "value": 37.6,
            "unit": "MB"
          }
        ]
      }
    ]
  }
}