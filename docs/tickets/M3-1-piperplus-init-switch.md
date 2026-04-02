# M3-1: PiperPlus 初期化の切り替え

> **マイルストーン**: M3
> **前提チケット**: M0 完了
> **後続チケット**: M3-2, M3-3, M3-4, M3-5
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/wasm/openjtalk-web/src/index.js` の `PiperPlus.initialize()` メソッド内で使用されている `SimpleUnifiedPhonemizer` を `@piper-plus/g2p` パッケージの `G2P.create()` に置き換える。現在の内部読み込み方式から、事前読み込み済み WASM モジュール + 辞書を受け取るファクトリ方式に移行し、G2P パッケージによる統一的な音素化基盤を確立する。

## 実装する内容の詳細

### 現状

`src/wasm/openjtalk-web/src/index.js` の 257-268 行目:

```javascript
this._phonemizer = new SimpleUnifiedPhonemizer();
await this._phonemizer.initialize({
  openjtalk: {
    dictData: dictFiles,
    voiceData: voiceData,
  },
});

if (this._config.phoneme_id_map) {
  this._phonemizer.setPhonemeIdMap(this._config.phoneme_id_map);
}
```

`SimpleUnifiedPhonemizer` は内部で OpenJTalk WASM の読み込みと辞書のセットアップを行う。`setPhonemeIdMap()` で ZH/KO/ES/FR/PT/SV のフォールバック用 phoneme_id_map を別途設定している。

### 変更内容

1. **`G2P.create()` への切り替え** (257-268 行目)
   - `G2P.create()` は事前読み込み済みの WASM モジュール + 辞書を引数として受け取るファクトリメソッド
   - 渡すパラメータ:
     - `languages`: `config.language_id_map` から取得した対応言語リスト
     - `jaDict`: `{ dictData, voiceData }` (DictManager が取得済みのデータ)
     - `openjtalkModule`: 事前読み込み済み WASM モジュール
   - `setPhonemeIdMap()` の個別呼び出しは不要になる (G2P 側で管理)

2. **`Encoder` インスタンスの作成**
   - `config.phoneme_id_map` から `Encoder` を生成
   - `Encoder` は M3-2 で `G2P.encode()` の引数として使用される

3. **import 文の追加**
   - `import { G2P, Encoder } from '@piper-plus/g2p'` を追加
   - `SimpleUnifiedPhonemizer` の import は M3-5 で削除するため、このチケットでは残す

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/wasm/openjtalk-web/src/index.js` | `SimpleUnifiedPhonemizer` → `G2P.create()` + `Encoder` 生成に置き換え |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| JS 開発者 | 1 | index.js の初期化ロジック書き換え、G2P.create() の統合 |
| レビュアー | 1 | API 互換性の確認、OpenJTalk WASM ライフサイクルの検証 |

## 提供範囲とテスト

### 提供範囲

- `src/wasm/openjtalk-web/src/index.js` の初期化セクション (257-268 行目) の変更
- `G2P` / `Encoder` の import 追加

### テスト項目

- `G2P.create()` が正常に呼び出され、G2P インスタンスが生成されること
- `Encoder` が `phoneme_id_map` から正しく生成されること
- 初期化完了後に `this._g2p` と `this._encoder` が利用可能であること

### Unit テスト

- `G2P.create()` をモックし、正しいパラメータ (`languages`, `jaDict`, `openjtalkModule`) で呼び出されることを検証
- `Encoder` コンストラクタに `phoneme_id_map` が渡されることを検証
- `G2P.create()` が失敗した場合のエラーハンドリングを検証

### E2E テスト

- `PiperPlus.initialize()` が実モデル config で正常に完了すること
- 初期化後に `synthesize()` が動作すること (音声出力の確認)

## 懸念事項とレビュー項目

### 懸念事項

1. **OpenJTalk WASM ライフサイクル管理の差異**: `SimpleUnifiedPhonemizer` は内部で WASM モジュールの読み込みとライフサイクルを管理しているが、`G2P.create()` は事前読み込み済みモジュールを受け取る方式。DictManager が返す `dictData` / `voiceData` のフォーマットが G2P の期待するフォーマットと一致するか確認が必要
2. **progress コールバックのタイミング**: 初期化の進捗報告ロジックが G2P.create() のタイミングと合致するか確認

### レビュー項目

1. `G2P.create()` に渡すパラメータの型と形式が正しいか
2. `Encoder` のインスタンス保持方法 (`this._encoder`) が適切か
3. `SimpleUnifiedPhonemizer` の初期化コードがデッドコードとして残っていないか
4. エラーハンドリング (G2P.create() 失敗時) が適切か

## 一から作り直すとしたら

G2P パッケージのファクトリ方式 (事前読み込み済みモジュールを受け取る) は、`SimpleUnifiedPhonemizer` の内部読み込み方式よりも明確に優れている。DI (依存性注入) パターンにより、テスタビリティが向上し、WASM モジュールの共有やキャッシュが容易になる。最初からこの方式で設計すべきだった。

## 後続タスクへの連絡事項

- M3-2 は `this._g2p` と `this._encoder` が利用可能であることを前提とする
- M3-4 (テスト更新) では、初期化テストのモックを `SimpleUnifiedPhonemizer` から `G2P.create()` に変更する必要がある
- `SimpleUnifiedPhonemizer` の import 文はこのチケットでは残す。M3-5 で削除する
