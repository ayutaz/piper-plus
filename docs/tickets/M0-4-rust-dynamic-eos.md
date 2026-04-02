# M0-4: Rust piper-g2p `PiperEncoder` 動的 EOS 対応

> **マイルストーン**: M0
> **前提チケット**: なし
> **後続チケット**: M2-2 (アダプタレイヤー)
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/rust/piper-g2p/src/encode.rs` の `PiperEncoder` は構築時に EOS トークンを `"$"` 固定で解決する。
日本語の疑問文には `"?"`, `"?!"`, `"?."`, `"?~"` の 4 種類の EOS バリアントが存在し、実行時に動的に EOS を切り替える必要がある。

**ゴール**: `PiperEncoder` が実行時に EOS トークンを動的に選択できるようにする。既存の呼び出し元はデフォルト `"$"` のまま動作し、後方互換性を維持する。

## 実装する内容の詳細

### 変更箇所

**ファイル**: `src/rust/piper-g2p/src/encode.rs`

#### 方式 A: `encode_with_prosody()` に `eos_token` パラメータ追加 (推奨)

##### 1. 新メソッド追加 (既存メソッドは非破壊)

```rust
impl PiperEncoder {
    /// Encode with explicit EOS token.
    /// `eos_token` defaults to "$" if None.
    pub fn encode_with_eos(
        &self,
        tokens: &[String],
        eos_token: Option<&str>,
    ) -> Result<Vec<i64>, G2pError> {
        let (ids, _) = self.encode_with_prosody_and_eos(tokens, &[], eos_token)?;
        Ok(ids)
    }

    /// Encode with prosody and explicit EOS token.
    pub fn encode_with_prosody_and_eos(
        &self,
        tokens: &[String],
        prosody: &[Option<ProsodyInfo>],
        eos_token: Option<&str>,
    ) -> Result<(Vec<i64>, Vec<ProsodyFeature>), G2pError> {
        // ... 既存の encode_with_prosody() のロジックと同一だが、
        // 最後の ids.push(self.eos_id) を動的 EOS に置換
        let eos_id = match eos_token {
            Some(token) => self.resolve_eos_id(token)?,
            None => self.eos_id,  // デフォルト "$"
        };
        // ...
        ids.push(eos_id);
        // ...
    }
}
```

##### 2. EOS ID 解決ヘルパーメソッド

```rust
impl PiperEncoder {
    /// Resolve an EOS token string to its phoneme ID.
    fn resolve_eos_id(&self, token: &str) -> Result<i64, G2pError> {
        self.id_map
            .get(token)
            .and_then(|ids| ids.first().copied())
            .ok_or_else(|| G2pError::PhonemeIdNotFound {
                phoneme: token.to_string(),
            })
    }
}
```

##### 3. 既存メソッドのリファクタ (コード重複防止)

既存の `encode()` と `encode_with_prosody()` は、内部で `eos_token=None` として新メソッドに委譲する形にリファクタし、コード重複を防ぐ。これにより EOS 処理ロジックが `encode_with_prosody_and_eos()` の一箇所に集約される。

```rust
// リファクタ後: 既存メソッドは新メソッドに委譲
pub fn encode(&self, tokens: &[String]) -> Result<Vec<i64>, G2pError> {
    let (ids, _) = self.encode_with_prosody_and_eos(tokens, &[], None)?;
    Ok(ids)
}

pub fn encode_with_prosody(
    &self,
    tokens: &[String],
    prosody: &[Option<ProsodyInfo>],
) -> Result<(Vec<i64>, Vec<ProsodyFeature>), G2pError> {
    self.encode_with_prosody_and_eos(tokens, prosody, None)
}
```

この委譲パターンにより:
- 既存の公開 API シグネチャは変更なし (後方互換)
- EOS 解決ロジックが `encode_with_prosody_and_eos()` 内に一元化される
- 将来の EOS 関連修正が一箇所で済む

#### 方式 B: `PiperEncoder::new()` で EOS を設定 (代替案)

```rust
pub fn new_with_eos(
    id_map: PhonemeIdMap,
    mode: UnknownTokenMode,
    eos_token: &str,
) -> Result<Self, G2pError> {
    // eos_token を id_map から解決
}
```

方式 B は疑問文のたびに新しい `PiperEncoder` を生成する必要があり非効率。方式 A を推奨。

### 変更量の見積り

- `encode_with_eos()`: 新メソッド ~5行
- `encode_with_prosody_and_eos()`: 既存 `encode_with_prosody()` と同構造で ~55行 (ロジックはコピー + EOS 部分のみ変更)
- `resolve_eos_id()`: ヘルパー ~8行
- 既存メソッドの委譲リファクタ: ~10行 (既存ロジック削除 + 委譲呼び出し)
- テスト: ~80行 (全4 EOS バリアントの個別テスト含む)
- 合計: ~160行変更

### リファクタリング (推奨 -- 上記「3. 既存メソッドのリファクタ」に統合済み)

既存メソッドの委譲パターンは上記セクション 3 に記載。コード重複を防ぐため、このリファクタリングは新メソッド追加と同時に実施すること。

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Rust 実装者 | 1 | `PiperEncoder` の新メソッド追加 + テスト作成 |
| レビュアー | 1 | API 設計確認、後方互換性確認、テスト結果確認 |

## 提供範囲とテスト

### 提供範囲

- `src/rust/piper-g2p/src/encode.rs` に以下を追加:
  - `encode_with_eos()` メソッド
  - `encode_with_prosody_and_eos()` メソッド
  - `resolve_eos_id()` プライベートメソッド
- 既存の `encode()` / `encode_with_prosody()` を内部委譲にリファクタリング (推奨: コード重複防止)
- ユニットテスト追加

### テスト項目

1. `encode_with_eos(tokens, None)` が既存の `encode()` と同一結果を返すこと
2. `encode_with_eos(tokens, Some("?"))` の最後の ID が `"?"` の phoneme ID であること (通常疑問)
3. `encode_with_eos(tokens, Some("?!"))` の最後の ID が `"?!"` の phoneme ID であること (強調疑問)
4. `encode_with_eos(tokens, Some("?."))` の最後の ID が `"?."` の phoneme ID であること (平叙疑問)
5. `encode_with_eos(tokens, Some("?~"))` の最後の ID が `"?~"` の phoneme ID であること (確認疑問)
6. 存在しない EOS トークン (`"??"` 等) で `G2pError` が返ること
7. 既存の `encode()` / `encode_with_prosody()` がリファクタ後も同一結果を返すこと (委譲パターンのリグレッション確認)

### Unit テスト

`src/rust/piper-g2p/src/encode.rs` の `#[cfg(test)] mod tests` に追加:

```rust
#[test]
fn test_encode_with_dynamic_eos_all_variants() {
    let map = make_map(&[
        ("^", &[1]), ("_", &[0]), ("$", &[2]),
        ("?", &[3]), ("?!", &[4]), ("?.", &[5]), ("?~", &[6]),
        ("a", &[15]),
    ]);
    let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
    let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();

    // Default EOS ("$")
    let ids_default = encoder.encode_with_eos(&tokens, None).unwrap();
    assert_eq!(*ids_default.last().unwrap(), 2); // "$" = 2

    // Dynamic EOS ("?") — 通常疑問
    let ids_question = encoder.encode_with_eos(&tokens, Some("?")).unwrap();
    assert_eq!(*ids_question.last().unwrap(), 3); // "?" = 3

    // Dynamic EOS ("?!") — 強調疑問
    let ids_excl = encoder.encode_with_eos(&tokens, Some("?!")).unwrap();
    assert_eq!(*ids_excl.last().unwrap(), 4); // "?!" = 4

    // Dynamic EOS ("?.") — 平叙疑問
    let ids_decl_q = encoder.encode_with_eos(&tokens, Some("?.")).unwrap();
    assert_eq!(*ids_decl_q.last().unwrap(), 5); // "?." = 5

    // Dynamic EOS ("?~") — 確認疑問
    let ids_confirm = encoder.encode_with_eos(&tokens, Some("?~")).unwrap();
    assert_eq!(*ids_confirm.last().unwrap(), 6); // "?~" = 6
}

#[test]
fn test_encode_with_eos_none_matches_encode() {
    let map = make_map(&[
        ("^", &[1]), ("_", &[0]), ("$", &[2]), ("a", &[15]),
    ]);
    let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
    let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();

    let ids_encode = encoder.encode(&tokens).unwrap();
    let ids_with_eos = encoder.encode_with_eos(&tokens, None).unwrap();
    assert_eq!(ids_encode, ids_with_eos);
}

#[test]
fn test_encode_with_invalid_eos_error() {
    let map = make_map(&[
        ("^", &[1]), ("_", &[0]), ("$", &[2]), ("a", &[15]),
    ]);
    let encoder = PiperEncoder::new(map, UnknownTokenMode::Skip).unwrap();
    let tokens: Vec<String> = vec!["a"].into_iter().map(String::from).collect();

    let result = encoder.encode_with_eos(&tokens, Some("??"));
    assert!(result.is_err());
}
```

### E2E テスト

`src/rust/piper-g2p/tests/` に追加 (または既存の integration test ファイルに追加):

```rust
#[test]
fn test_japanese_question_dynamic_eos_e2e() {
    // 日本語疑問文テキスト → phonemize → encode_with_eos("?") → 検証
    // phonemize で得たトークンを encode_with_eos で ID 化し、
    // 最後の ID が "?" の ID であることを確認
}
```

## 懸念事項とレビュー項目

### 懸念事項

- **API 後方互換性**: 既存の `encode()` / `encode_with_prosody()` を変更しないため、既存の呼び出し元に影響はない。ただし、将来的に `encode_with_prosody_and_eos()` と `encode_with_prosody()` の 2 系統が並存することによる混乱の可能性がある
- **phoneme_id_map に EOS バリアントが含まれるか**: `"?"`, `"?!"`, `"?."`, `"?~"` が `phoneme_id_map` に含まれていない場合、`resolve_eos_id()` がエラーを返す。実行時ではなくエンコーダ構築時に利用可能な EOS トークンを検証する設計も検討する
- **パフォーマンス**: `resolve_eos_id()` は毎回 `HashMap::get()` を呼ぶ。頻度が高い場合は構築時に全 EOS バリアントの ID をキャッシュする設計も検討する

### レビュー項目

- [ ] 既存の `encode()` / `encode_with_prosody()` の動作が変わらないこと
- [ ] `encode_with_eos(tokens, None)` が `encode(tokens)` と同一結果であること
- [ ] 全 5 種類の EOS (`"$"`, `"?"`, `"?!"`, `"?."`, `"?~"`) が正しく動作すること
- [ ] 存在しない EOS トークンで適切なエラーが返ること
- [ ] `cargo test` が全件パスすること
- [ ] `cargo clippy` で warning がないこと

## 一から作り直すとしたら

`PiperEncoder` の設計を最初から EOS を動的に受け取る形にする。`encode()` のシグネチャ自体に `eos: EosToken` を含め、`EosToken` を enum で定義する:

```rust
pub enum EosToken {
    Declarative,      // "$"
    Question,         // "?"
    Exclamatory,      // "?!"
    DeclarativeQ,     // "?."
    Confirmation,     // "?~"
}
```

これにより型安全性が確保され、存在しない EOS トークン文字列を渡すランタイムエラーがコンパイル時に防げる。

## 後続タスクへの連絡事項

- M2-2 (アダプタレイヤー) は `encode_with_eos()` / `encode_with_prosody_and_eos()` を使用して日本語疑問文の動的 EOS を実現する
- 新メソッドの最終的なシグネチャ (引数名、型) をチケット完了時に記載すること
- `phoneme_id_map` に `"?"`, `"?!"`, `"?."`, `"?~"` が含まれていることの確認結果を記載すること (含まれていない場合は M2-2 で id_map 側の対応が必要)
- コード重複排除のリファクタリング (既存メソッドの内部委譲) を実施したかどうかを記載すること
