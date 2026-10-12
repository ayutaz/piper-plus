# つくよみちゃん: 試聴後の公開に向けた準備

作成: 2026-10-12。公開先は`ayousanz/piper-plus-tsukuyomi-chan/releases/zs-v1/`。
同じ公開base由来の既存500 epoch FTを使う。
人手の試聴結果とHF公開はまだ未実施。技術的な公開準備と品質判定を区別する。
元の配布候補と試聴資料は`output/public-tsukuyomi-release-20261010/`に保持する。
準備コピーは`output/publication-ready-20261012/prepared/`。

過去の照合・比較結果は[検証記録のPR #793](https://github.com/ayutaz/piper-plus/pull/793)を参照。
ベースはrevision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1`で公開済み。
つくよみちゃん公開先の現在の親revisionは
`36b59c825c36bd386b8960cf3f604382f52f2a87`。変更があれば公開前に調査する。
旧root model/configとbase・研究保存先のprivate/gate設定は保持する。

## 試聴前に完了させる作業

- 最終22ファイルのhash/size、対応config、モデルカード、固定source/baseを照合。
- 新規コピーで通常生成・配布例・checkpoint strict loadを確認。
- 公開先に対するdry-runと人手結果欠落時の停止を確認。
- 回答の不足、試聴WAVの変更、payloadの変更、HF親revision/設定の変更を拒否する。
- 元候補を保持し、試聴結果の反映前にmetadataをbackupする。
- 試聴ページでは日本語3文のFT・旧モデル・baseを比較できる。

準備helperはGitHubで管理する`scripts/tsukuyomi_release/`。
配布物・モデル重み・元録音・private評価embeddingをGitHubへ追加しない。
テストは一時directoryと架空の回答を使用し、実際の人手承認・HF公開を行わない。

## 試聴結果の反映と公開

1. 人手の実回答を確認し、`human-review-template.json`のコピーへ記録する。
   必須項目は`reading`、`similarity`、`naturalness`、`noise`、実際のユーザー発言、
   timezone付き記録日時、実験基準版の公開判断、試聴WAV 3件のhash。
   空欄を機械指標から埋めたり、未知の項目を「問題なし」にしない。
   問題があれば原因を調べ、修正した対象を再試聴する。
2. 次のcommandで結果を反映する。重み・config・sampleは変更しない。
   モデルカード・検証JSON・manifest・SHA256SUMSをまとめて更新する。

   ```powershell
   uv run --no-sync python -m scripts.tsukuyomi_release.record_review --workspace output/publication-ready-20261012/prepared --review output/publication-ready-20261012/actual-human-review.json
   ```

3. applyなしで公開前検査を行う。

   ```powershell
   uv run --no-sync python -m scripts.tsukuyomi_release.publish_bundle --workspace output/publication-ready-20261012/prepared
   ```

4. 結果・制約・最終hashが揃った後、指定した公開先へ追加する。
   gateの変更、旧root model/configの置換、削除操作は含まない。

   ```powershell
   uv run --no-sync python -m scripts.tsukuyomi_release.publish_bundle --workspace output/publication-ready-20261012/prepared --apply
   ```

5. receiptの公開commitを固定し、未認証の新規取得・生成・checkpoint読み込み・
   旧rootと研究保存先の保持を確認する。

   ```powershell
   uv run --no-sync python -m scripts.tsukuyomi_release.consumer --workspace output/publication-ready-20261012/prepared
   ```

機械検証と人手試聴の記録が全て揃い、公開後検証にも成功した時点で公開完了とする。
人手の回答反映後に古い`finalize_bundle.py`を実行しない。
これはpendingの準備候補を生成する旧helperで、回答を上書きする。
任意の全文章・全言語の品質承認や、FTによる声質改善をこの工程だけで宣言しない。

## 準備コピーの再作成

出力先が存在する場合は上書きせず停止する。
別の新規directoryを指定し、sourceの全hashを検査してから準備する。

```powershell
uv run --no-sync python -m scripts.tsukuyomi_release.prepare --source output/public-tsukuyomi-release-20261010 --output output/publication-ready-20261012/prepared
uv run --no-sync python -m scripts.tsukuyomi_release.consumer --workspace output/publication-ready-20261012/prepared --candidate
```

candidate検証は新規コピーによる事前確認で、匿名の公開取得とは区別する。
独立したPyPI 2.0.0 consumer環境とtraining環境は今回のworkspaceの既存環境を使う。
別workspaceで実行する場合は、同じ環境と配布物を用意してから実行する。
他runtime/OS・Colab GPU全工程の実モデル確認は別途の検証対象であり、
この準備helperの成功をその確認済み証拠として扱わない。
