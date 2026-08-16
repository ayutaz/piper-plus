# zs-quality-anatomy — v10a-r2 残存アーティファクト解剖スクリプト (2026-08-16)

`docs/design/zero-shot-v10b-quality-plan.md` §1 の実測数値 (フレーム格子トーンコム /
5.5-8.5kHz 棚 / F0 ダイナミクス圧縮 / 750-1000Hz 包絡欠損) を生成した分析コードの
アーカイブ。事前登録メトリクス (SR/128 格子コム超過 dB、>4kHz 残差 autocorr
@lag128/256) の定義の出典であり、Phase A (E-4) で piper_train.tools への正式移植の
種になる。ローカル wav パスがハードコードされている点に注意 (session scratchpad から
の保全コピー、そのままでは他環境で動かない)。
