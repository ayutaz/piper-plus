# Research

先行研究・最新論文を用いた piper-plus 改善調査のスナップショット集。
各レポートは調査時点での主張・出典・確信度を記録し、実装判断のインプットとする。
ここにある版数・依存関係・実装状況は各ファイルの日付時点の記録であり、現行の
リリースや runtime 対応状況を示すものではない。

> [!NOTE]
> TTS 分野は進展が速いため、各レポートは**調査日時点のスナップショット**。
> 実装着手前に一次ソースの再確認を推奨。日付入りファイル名で版を管理する。

## レポート一覧

- [GPT-SoVITS参照候補・学習準備の再監査 2026-10-17](gpt-sovits-readiness-audit-2026-10-17.md) — 最新SHAの再確認、既存/修正済み/未実装の候補台帳、学習前に残る条件。
- [zero-shot不具合修正・品質改善計画 2026-10-09](../design/zero-shot-recovery-and-improvement-plan-2026-10-09.md) — 調査・監査を受けた実行計画。更新周期/データ/評価の修正、既存再評価、単一要因学習、v12参照系列入力の順と完了条件を定義。
- [zero-shot既存実装の不具合監査 2026-10-09](zero-shot-implementation-audit-2026-10-09.md) — 実LightningによるCPU再現でG/D更新周期とWavLM discriminator無更新を確認。v11保存ログの裏付け、固定音声/F0/runtime検証の欠落、設計事項との切り分けを収載。
- [GPT-SoVITS最新版からのzero-shot改善調査 2026-10-09](gpt-sovits-zero-shot-2026-10-09.md) — V2Pro正式releaseとV5開発版を区別した公式コード調査、現zero-shot実装の改善候補、v11保存ログの再解析。参照系列入力のv12案と、既存契約内の入力/cache/評価/EMA改修を分離。v11の敵対rampはep15で上限到達済みであり、従来の凍結案を再検討する根拠も収載。
- [改善調査 統合レポート 2026-06-15](improvement-survey-2026-06-15.md) — この research archive 内の統合参照源（2026-06-15 snapshot）。 2 つのスナップショット (2026-06-03 / v1.12.0、 2026-06-15 / v1.13.0) を統合した、 5 軸 (A. 音声品質モデル / B. ランタイム・エッジ / C. 多言語 G2P / D. エコシステム / E. 運用ガイダンス) の **31 アクション** ロードマップ。 短期 (3〜6 ヶ月) と中期 (1 年) で分類、 KPI 案・統合判断履歴付き。 統合一次ソース 47 件 / 43 主張確定 / 7 棄却 / DRAFT PR (#222 #355 #386) + Open PR #537 (ready-for-review、 v2.0.0 候補) との重複除外済。 §G オープンクエスチョンは Phase 4 deep-research で全件分類完了 (本表 9 + companion 11 = **全 20 件、 RESOLVED 5 / CONVERGED 7 / IRREDUCIBLE 8**、 文献調査による closure 完了、 残りは PoC 待ち)。

## 深堀りコンパニオン

- [Decoder Upgrade: iSTFTNet2-MB (A-1) と MS-Wavehax (A-2)](decoder-upgrades-istftnet2-and-mswavehax.md) — 統合レポート §A の A-1 / A-2 について、 v1.12.0 で導入済みの **MB-iSTFT-VITS** との差分を**コード位置 (`mb_istft.py:14` import / `:25` PQMF クラス / `:133-296` MBiSTFTGenerator クラス) と数値で明示**。 「置換」ではなく「枠組み流用 + 増築」 (A-1 は backbone 1D→1D-2D 置換、 A-2 は streaming 専用 vocoder 併設) であることを示し、 並走戦略と実装フェーズを提示。 §2.5 に Phase 1〜4 deep-research の段階的更新 (Risk 1 中→低 / Risk 2 中→高 / Risk 3 中→低 に再評価) と companion オープンクエスチョン Q10〜Q20 全 11 件の分類済表を併載。
