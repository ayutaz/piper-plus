# Issue #752 / PR #753 CI 修復計画

調査日: 2026-10-05。対象は IPA 入力 API を追加する [PR #753](https://github.com/ayutaz/piper-plus/pull/753)。

## 確認済みの原因

| CI | 証拠 | 対応 |
| --- | --- | --- |
| doc-examples-gate | [run 36902537254](https://github.com/ayutaz/piper-plus/actions/runs/36902537254) で監査スナップショット不一致。最新 dev を取り込んだ作業ツリーでも再現した。469 個のコードブロックのうち、phoneme-input.md の一つだけが行 492–494 から 511–513 へ移動しており、内容ハッシュは同じ。 | 既存の監査コマンドで JSON を再生成し、不一致チェックを再実行する。 |
| ARM64 Native | [run 36902537016](https://github.com/ayutaz/piper-plus/actions/runs/36902537016) はコンパイル 73/73 と tarball 作成を完了後、builder のファイルシステム全体を local exporter でコピー中に 30 分制限へ到達した。Native という名前だがランナーは x64。後続処理の想定ファイル名も Dockerfile の出力名と一致していなかった。 | ARM64 専用ランナーを使い、既存の最終 scratch ステージから tarball だけを出力する。正式なファイル名で検証・アップロードする。 |
| Rust macOS | [run 36902537231](https://github.com/ayutaz/piper-plus/actions/runs/36902537231) の注釈は hosted runner の通信断。失敗したアサーションやコンパイルエラーは確認できず、ログ取得も不可。 | 修正した head で同じ macOS テストを再実行し、再発時は新しいログと注釈で調査する。現時点で通信断の根本原因は未確定。 |

## 実施順序

1. 最新 dev を PR ブランチへ取り込み、既存の機能コミットを保持する。
2. 成果物検証の失敗テストを先に実行する。欠落、破損、x86_64、32-bit、異なるバイト順、実行権限なしを拒否し、ARM64 ELF を受け入れる検証を実装する。
3. ARM64 workflow を ubuntu-24.04-arm へ切り替える。uname で実機のアーキテクチャを確認し、Buildx と build-push-action で成果物だけを出力する。キャッシュは専用 scope を用いる。ジョブ制限は 30 分を維持する。
4. 監査 JSON を再生成し、監査・Python lint・成果物検証・Rust G2P テストをローカルで確認する。
5. 同じ PR ブランチへ push し、監査・ARM64・macOS を含む最新 head の CI を確認する。失敗時はログに基づいて追加対応する。

## 検証の範囲

成果物検証はアーカイブを展開せず、piper-plus/bin/piper-plus が実行権限を持つ通常ファイルで、64-bit little-endian ELF の AArch64 実行形式であることを確認する。音声生成の品質や実行時共有ライブラリの完全性は、この検証だけでは判断できない。

GitHub の [hosted runner 仕様](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) に ubuntu-24.04-arm が掲載されている。Docker の [local exporter](https://docs.docker.com/build/exporters/local-tar/) は選択ステージのファイルシステムを出力するため、今回の既存 scratch ステージを使うことでビルド依存やキャッシュの全量コピーを避けられる。[GHA cache](https://docs.docker.com/build/cache/backends/gha/) は build-push-action を介して利用する。
