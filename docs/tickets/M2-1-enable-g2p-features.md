# M2-1: Cargo.toml features 有効化

> **マイルストーン**: M2
> **前提チケット**: M0-4
> **後続チケット**: M2-2, M2-3, M2-4, M2-5, M2-6, M2-7
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`src/rust/piper-core/Cargo.toml` の piper-g2p 依存を `features = []` から `features = ["all-languages"]` に変更し、piper-core が piper-g2p の全言語 G2P 機能を利用できるようにする。

`japanese` feature は jpreprocess (0.9) を pull する。`naist-jdic` (日本語辞書バンドル) は piper-core 自身の feature gate で制御されるため、piper-g2p 側の feature とは独立している。

**ゴール**: `cargo check` および `cargo build` が `all-languages` feature 有効状態で正常に完了し、piper-g2p の全言語 G2P 機能が piper-core から利用可能になる状態。

## 実装する内容の詳細

### 変更箇所

**ファイル**: `src/rust/piper-core/Cargo.toml`

```toml
# 変更前
piper-g2p = { path = "../piper-g2p", features = [] }

# 変更後
piper-g2p = { path = "../piper-g2p", features = ["all-languages"] }
```

### 確認事項

1. `piper-g2p` の `all-languages` feature が存在し、8言語全て (JA/EN/ZH/KO/ES/FR/PT/SV) を有効化することを確認
2. `japanese` feature が jpreprocess 0.9 を pull することを確認
3. piper-core の `naist-jdic` feature gate が piper-g2p の feature とは独立していることを確認
4. 個別言語 feature (`japanese`, `english`, `chinese` 等) での部分ビルドが可能であることを確認

### 変更しないもの

- piper-core の feature gate 定義 (`naist-jdic` 等) -- 既存のまま
- piper-g2p の Cargo.toml -- 変更不要
- piper-core のソースコード -- このチケットでは Cargo.toml のみ

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | Cargo.toml の feature 変更、ビルド確認 |

## 提供範囲とテスト

### 提供範囲

- `src/rust/piper-core/Cargo.toml` の 1 行変更

### テスト項目

1. `cargo check -p piper-core` が成功すること
2. `cargo build -p piper-core` が成功すること
3. 個別 feature 組み合わせでのビルド確認:
   - `cargo check -p piper-core --no-default-features`
   - `cargo check -p piper-core --features "naist-jdic"`
4. ワークスペース全体のビルド: `cargo build --workspace`

### Unit テスト

- `cargo test -p piper-core` が全件パスすること
- `cargo test -p piper-g2p --features all-languages` が全件パスすること

### E2E テスト

- `cargo build -p piper-plus-cli --release` が成功すること
- CLI バイナリが起動できること

## 懸念事項とレビュー項目

### 懸念事項

1. **ビルド時間の増加**: jpreprocess のコンパイルにより CI のビルド時間が増加する可能性がある。特にクリーンビルド時に顕著。CI のタイムアウト設定の確認が必要
2. **バイナリサイズの増加**: 全言語の G2P コードがリンクされることで、最終バイナリのサイズが増加する。feature gate による選択的リンクが正しく機能するか確認する
3. **依存バージョン衝突**: jpreprocess 0.9 が piper-core の他の依存 (特に lindera 関連) と衝突する可能性
4. **feature flag 相互依存**: piper-core 自体には `all-languages` feature がない。piper-g2p 側の `all-languages` を有効化する形。`--no-default-features` でビルドした場合の挙動を確認すること。

### レビュー項目

1. feature 名が正しいこと (`all-languages`)
2. piper-g2p 側の feature 定義と整合していること
3. `Cargo.lock` の差分が妥当であること (新規依存の確認)
4. ビルド時間の変化を計測・記録すること

## 一から作り直すとしたら

piper-core の Cargo.toml で piper-g2p を最初から `features = ["all-languages"]` で依存する設計にしていれば、この変更チケット自体が不要だった。段階的移行のために `features = []` で開始したことは正しい判断だが、feature の粒度設計 (全言語一括 vs. 言語別) をもう少し早い段階で確定しておくべきだった。

## 後続タスクへの連絡事項

- M2-2 以降のチケットは、このチケットの完了後に `piper_plus_g2p` の全言語 Phonemizer が piper-core から利用可能であることを前提とする
- ビルド時間の計測結果を共有すること (CI タイムアウト調整の判断材料)
- `Cargo.lock` の変更は大きくなる可能性があるため、コミットメッセージにその旨を記載すること
