# M1-4: preprocess.py 音素化パイプライン リファクタ

> **マイルストーン**: M1
> **前提チケット**: M0-1, M0-2, M1-1, M1-3
> **後続チケット**: M1-7 (旧コード削除), M1-8 (テスト/CI)
> **見積り**: 大
> **リスク**: 高

## タスク目的とゴール

preprocess.py の音素化パイプラインを piper_g2p に移行する。preprocess.py には 2 つの独立した音素化パスが存在し、それぞれ異なる BOS/EOS/パディング処理を行っている。この移行により、音素化ロジックを piper_g2p に委譲し、BOS/EOS/パディングの責務を PiperEncoder に統一する。

**これは M1 で最もリスクの高いチケットである。** BOS/EOS の欠落は学習データの破損に直結し、モデル品質に不可逆的な影響を与える。

## 実装する内容の詳細

### 現状のアーキテクチャ

preprocess.py には 2 つの音素化パスが存在する:

**注意**: 本チケットの行番号は調査時点の参照値であり、先行チケット (M1-2, M1-3) の変更により変動する。実装時は以下のキーワードで最新位置を特定すること:
- パス A: `def phonemize_batch_openjtalk` で検索
- パス B: `def _phonemize_batch_multilingual_impl` で検索
- post_process_ids: `phonemizer.post_process_ids` で検索

#### パス A: 日本語モノリンガル (668-801 行)

```
現在のフロー:
  phonemize_japanese_with_prosody(text, custom_dict=...)
    → トークン列 (BOS/EOS が埋め込み済み)
    → post_process_ids() は no-op (何もしない)
    → phoneme_ids を直接出力
```

- `phonemize_japanese_with_prosody()` が返すトークンには既に BOS (id=1) と EOS (id=2) が含まれている
- `post_process_ids()` は日本語モノリンガルの場合は何も加工しない
- トークン → ID 変換ループ (737-743 行) で ID マップを参照

#### パス B: マルチリンガル (803-952 行)

```
現在のフロー:
  MultilingualPhonemizer.phonemize_with_prosody(text)
    → セグメントごとに言語検出 + 音素化
    → 各セグメントから BOS/EOS を除去
    → post_process_ids() が BOS/EOS/パディングを追加 (動的 EOS 追跡あり)
    → phoneme_ids を出力
```

- `MultilingualPhonemizer` がセグメント単位で音素化
- セグメント間の BOS/EOS を除去し、`post_process_ids()` で全体に BOS/EOS を付与
- 日本語疑問文の動的 EOS (疑問詞マーカー `?!`, `?.`, `?~`) を追跡
- トークン → ID 変換ループ (880-886 行) で ID マップを参照

### 移行後のアーキテクチャ

```
移行後のフロー (パス A / パス B 共通):
  piper_g2p の Phonemizer.phonemize_with_prosody(text)
    → 純粋な IPA トークン列 (BOS/EOS なし)
    → PiperEncoder.encode_with_prosody()
      → BOS/EOS/パディングの付与
      → トークン → ID 変換
      → phoneme_ids + prosody_features を出力
```

- piper_g2p の Phonemizer は純粋な IPA トークンのみを返す (BOS/EOS を含まない)
- PiperEncoder が BOS/EOS/パディングの付与とトークン → ID 変換を一括で担当
- 日本語疑問文の動的 EOS も PiperEncoder 内で処理

### 作業項目

#### 作業 1: 音素化呼び出しの置換

**パス A (日本語モノリンガル):**

| 項目 | 現在 | 移行後 |
|------|------|--------|
| 音素化関数 | `phonemize_japanese_with_prosody(text, custom_dict=...)` | `piper_g2p.JapanesePhonemizer(custom_dict=...).phonemize_with_prosody(text)` |
| 戻り値 | BOS/EOS 埋め込み済みトークン列 | 純粋な IPA トークン列 (BOS/EOS なし) |

**パス B (マルチリンガル):**

| 項目 | 現在 | 移行後 |
|------|------|--------|
| 音素化クラス | `piper_train.phonemize.MultilingualPhonemizer` | `piper_g2p.MultilingualPhonemizer` |
| 戻り値 | セグメント単位の BOS/EOS 除去済みトークン列 | 純粋な IPA トークン列 (BOS/EOS なし) |

#### 作業 2: PiperEncoder による BOS/EOS/パディングの付与

**最重要作業。BOS/EOS の欠落は学習データ破損に直結する。**

- パス A: 現在は音素化関数が BOS/EOS を埋め込んでいるが、移行後は PiperEncoder が担当する
- パス B: 現在は `post_process_ids()` が BOS/EOS を付与しているが、移行後は PiperEncoder が担当する
- PiperEncoder は以下を処理する:
  - BOS (id=1) をシーケンス先頭に挿入
  - EOS (id=2) をシーケンス末尾に挿入
  - フォニーム間パディング (id=0) の挿入
  - 日本語疑問文の動的 EOS マーカー処理

**危険: パス A で PiperEncoder を追加し忘れると、BOS/EOS が完全に欠落する。** 旧コードでは音素化関数自体が BOS/EOS を埋め込んでいたため、piper_g2p に切り替えた後に PiperEncoder を入れ忘れるリスクが極めて高い。

#### 作業 3: トークン → ID 変換ループの統一

現在、パス A (737-743 行) とパス B (880-886 行) に重複するトークン → ID 変換ループが存在する。移行後は PiperEncoder が一括で処理するため、これらのループは不要になる。

```python
# 現在のコード (737-743 行、パス A):
phoneme_ids = []
for token in tokens:
    if token in id_map:
        phoneme_ids.append(id_map[token])
    else:
        ...  # unknown token handling

# 現在のコード (880-886 行、パス B):
# ほぼ同一のループ
```

移行後:
```python
# PiperEncoder が内部でトークン → ID 変換を実行
result = encoder.encode_with_prosody(tokens, prosody_info)
phoneme_ids = result.phoneme_ids
prosody_features = result.prosody_features
```

#### 作業 4: prosody dict → ProsodyInfo 型の統一

現在、prosody 情報は辞書型 (`{"a1": int, "a2": int, "a3": int}`) で管理されている。piper_g2p は `ProsodyInfo` 型 (または同等の型) を使用する。両パスで型を統一する。

| 項目 | 現在 | 移行後 |
|------|------|--------|
| prosody 型 | `list[dict[str, int]]` | `list[ProsodyInfo]` (piper_g2p 定義) |
| 変換 | 手動で辞書を構築 | PiperEncoder が型変換を担当 |

### 変更対象ファイル

| ファイル | 変更範囲 | リスク |
|---------|---------|--------|
| `preprocess.py` | パス A (668-801 行): 音素化呼び出し + PiperEncoder 追加 | 高 |
| `preprocess.py` | パス B (803-952 行): 音素化クラス置換 + PiperEncoder 追加 | 高 |
| `preprocess.py` | トークン → ID 変換ループ (737-743, 880-886 行): PiperEncoder に統一 | 中 |
| `preprocess.py` | post_process_ids() 呼び出しの削除 | 中 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 A | 1 | パス A (日本語モノリンガル) の移行 + PiperEncoder 統合 |
| 実装者 B | 1 | パス B (マルチリンガル) の移行 + PiperEncoder 統合 |
| テスト作成者 | 1 | Unit テスト + E2E テスト (BOS/EOS 検証、phoneme_ids 一致検証) |
| レビュアー | 1 | BOS/EOS 処理の正確性、パディングの正確性、回帰テスト結果の確認 |

## 提供範囲とテスト

### 提供範囲

- `preprocess.py` のパス A / パス B の音素化パイプライン全体

### テスト項目

1. パス A で BOS/EOS が正しく付与されていること
2. パス B で BOS/EOS が正しく付与されていること
3. フォニーム間パディング (id=0) が正しく挿入されていること
4. 日本語疑問文の動的 EOS マーカーが正しく処理されていること
5. prosody_features と phoneme_ids のアライメントが正しいこと
6. 移行前後で phoneme_ids が完全一致すること

### Unit テスト

1. **パス A: BOS/EOS 存在確認**
   ```python
   # 日本語モノリンガルパスの出力で BOS=1 が先頭、EOS=2 が末尾にあること
   result = preprocess_japanese("こんにちは")
   assert result.phoneme_ids[0] == 1   # BOS
   assert result.phoneme_ids[-1] == 2  # EOS
   ```

2. **パス A: phoneme_ids 一致検証**
   ```python
   # 旧コードと新コードで同一テキストから同一の phoneme_ids が生成されること
   old_ids = old_preprocess_japanese("こんにちは")
   new_ids = new_preprocess_japanese("こんにちは")
   assert old_ids == new_ids
   ```

3. **パス B: マルチリンガル BOS/EOS 確認**
   ```python
   # JA+EN 混合テキストで BOS が先頭、EOS が末尾にあること
   result = preprocess_multilingual("こんにちは。Hello.")
   assert result.phoneme_ids[0] == 1   # BOS
   assert result.phoneme_ids[-1] == 2  # EOS
   ```

4. **パス B: セグメント間パディング確認**
   ```python
   # JA→EN のセグメント境界にパディングが挿入されていること
   result = preprocess_multilingual("こんにちは。Hello.")
   # セグメント境界にパディング (id=0) が存在することを確認
   ```

5. **日本語疑問文の動的 EOS**
   ```python
   # 疑問詞マーカーが正しく処理されること
   result = preprocess_japanese("今日は何曜日ですか？")
   # 疑問詞マーカーに対応する EOS が含まれていること
   ```

6. **prosody_features アライメント**
   ```python
   # phoneme_ids と prosody_features の長さが一致すること
   result = preprocess_japanese("こんにちは")
   assert len(result.prosody_features) == len(result.phoneme_ids)
   ```

### E2E テスト

1. **小規模データセット前処理 (日本語モノリンガル)**:
   - 10 発話の日本語テキストを前処理
   - 出力される phoneme_ids が移行前の出力と完全一致することを diff で確認
   - 出力される prosody_features が移行前の出力と完全一致することを確認

2. **小規模データセット前処理 (マルチリンガル)**:
   - JA+EN+ZH を含む 10 発話のマルチリンガルテキストを前処理
   - 出力される phoneme_ids が移行前の出力と完全一致することを diff で確認

3. **学習スモークテスト**:
   - 移行後のコードで前処理したデータセットを使い、1 epoch の学習を実行
   - エラーなく完了することを確認 (品質は確認しない -- phoneme_ids 一致が保証されていれば品質は同等)

## 懸念事項とレビュー項目

### 懸念事項

1. **BOS/EOS 欠落 (最大リスク)**: パス A で piper_g2p に切り替えた後、PiperEncoder を追加し忘れると BOS/EOS が完全に欠落する。旧コードでは音素化関数自体が BOS/EOS を埋め込んでいたため、「音素化関数を差し替えれば動く」という誤解が生じやすい。**実装者は必ず PiperEncoder の追加を最初に行い、BOS/EOS の存在を Unit テストで確認してから後続作業に進むこと。**

2. **学習データ破損の不可逆性**: BOS/EOS やパディングの誤りは、生成される phoneme_ids を汚染する。汚染されたデータで学習を開始すると、数日間の GPU 時間が無駄になる。E2E テストで移行前後の phoneme_ids 完全一致を確認してから学習に進むこと。

3. **日本語疑問文の動的 EOS**: 疑問詞マーカー (`?!`, `?.`, `?~`) は日本語固有の機能であり、PiperEncoder に正しく引き継がれる必要がある。M0-2 の PiperEncoder 設計でこの機能が含まれていることを確認する。

4. **パディング挿入ロジックの差異**: 旧コードのパス A とパス B でパディング挿入ロジックが微妙に異なる可能性がある。PiperEncoder に統一する際に、両パスの出力が旧コードと一致することを個別に確認する。

5. **prosody_features のアライメント**: PiperEncoder が BOS/EOS/パディングを挿入する際に、対応する prosody_features (a1=0, a2=0, a3=0) も挿入する必要がある。アライメントがずれると学習時にインデックスエラーまたは品質劣化が発生する。

6. **パス A/B の分離前提の妥当性**: パス A/B の分離は調査時のコード構造に基づく。実装着手時に `preprocess.py` を通読し、現在の分岐構造を確認すること。`phonemize_batch_openjtalk` と `_phonemize_batch_multilingual_impl` が存在しない場合は本チケットの設計を見直す必要がある。

### レビュー項目

1. **BOS/EOS の存在**: 全テストケースの出力で `phoneme_ids[0] == 1` (BOS) かつ `phoneme_ids[-1] == 2` (EOS) であること
2. **パディングの正確性**: フォニーム間にパディング (id=0) が正しく挿入されていること
3. **動的 EOS**: 日本語疑問文の疑問詞マーカーが正しく処理されていること
4. **prosody アライメント**: `len(prosody_features) == len(phoneme_ids)` であること
5. **phoneme_ids 完全一致**: 移行前後のテストデータで phoneme_ids が完全一致すること (1 ビットの差異も許容しない)
6. **post_process_ids() の削除**: 旧 `post_process_ids()` の呼び出しが削除されていること
7. **トークン → ID 変換ループの削除**: 旧ループ (737-743, 880-886 行) が削除され、PiperEncoder に統一されていること

## 一から作り直すとしたら

piper_g2p の IPA ファースト設計が正しいアプローチである。音素化 (Phonemizer) は純粋な IPA トークンの生成のみを担当し、BOS/EOS/パディングの付与はエンコーディングレイヤー (PiperEncoder) が担当するべきだった。旧 piper_train のコードでは音素化関数が BOS/EOS を埋め込んでおり、これが責務の混在を引き起こしていた。

具体的には:

- **音素化レイヤー**: テキスト → IPA トークン列 (言語固有のロジックのみ)
- **エンコーディングレイヤー**: IPA トークン列 → phoneme_ids (BOS/EOS/パディング/ID変換を含むフォーマット固有のロジック)

この分離により、音素化レイヤーは piper 固有のフォーマット (BOS/EOS 等) を知る必要がなくなり、他の TTS システムでも再利用可能になる。PiperEncoder は piper 固有のフォーマットを一箇所にカプセル化し、変更時の影響範囲を最小化する。

旧コードの最大の設計問題は、パス A とパス B で BOS/EOS の処理方式が異なっていたことである。パス A は音素化関数内で BOS/EOS を埋め込み、パス B は `post_process_ids()` で後付けしていた。この不統一が移行時のリスクを高めている。

## 後続タスクへの連絡事項

- M1-7 (旧コード削除): このチケット完了後、以下が削除可能になる
  - `phonemize_japanese_with_prosody()` 関数
  - `post_process_ids()` 関数
  - トークン → ID 変換ループ (旧コード)
  - パス A / パス B の旧分岐ロジック
- M1-8 (テスト/CI): E2E テストの実行結果 (phoneme_ids 一致確認) をこのチケットのレビューで添付すること。M1-8 ではこのテストを CI に組み込む
- **全後続チケットへの警告**: このチケットの完了前に学習を開始しないこと。phoneme_ids の完全一致が確認されるまで、移行後のコードで生成したデータセットは学習に使用しないこと
