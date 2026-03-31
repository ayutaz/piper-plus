# P1-009: ドキュメント + 既知制限記載

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: NFR-101
> 依存チケット: P1-001 ~ P1-008 (全言語実装 + extras)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージの各言語 Phonemizer について、既知制限を明確に文書化する。ユーザーが各言語の G2P 品質と制限事項を事前に把握できるようにし、プロダクション利用時の期待値を適切に設定する。docstring、README、および言語別セクションの 3 層でドキュメントを提供する。

### ゴール

- 各言語の既知制限がクラス docstring に記載されている
- README に言語別のクイックスタート + 制限事項セクションがある
- 各言語 Phonemizer の IPA 出力例が文書化されている
- PiperEncoder の使用方法が文書化されている
- カスタム辞書の JSON フォーマット仕様が記載されている

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/README.md` | パッケージ README (PyPI 表示用) |
| `src/python/g2p/piper_g2p/chinese.py` | docstring に既知制限追記 |
| `src/python/g2p/piper_g2p/korean.py` | docstring に既知制限追記 |
| `src/python/g2p/piper_g2p/spanish.py` | docstring に既知制限追記 |
| `src/python/g2p/piper_g2p/french.py` | docstring に既知制限追記 |
| `src/python/g2p/piper_g2p/portuguese.py` | docstring に既知制限追記 |

### 実装手順

1. 各言語 Phonemizer のクラス docstring に既知制限を追記:

**ChinesePhonemizer**:
```python
"""Chinese (Mandarin) phonemizer using pypinyin.

Known limitations:
- Recursive tone sandhi not implemented: Only pairwise T3+T3 sandhi
  is applied left-to-right. For 3+ consecutive T3 syllables (e.g.,
  你买火), the correct bracketed sandhi based on syntactic structure
  is not applied.
- No word segmentation: pypinyin operates on individual characters,
  so word-level polyphone disambiguation may be inaccurate for
  certain characters.

Dependencies: pypinyin>=0.50 (MIT)
"""
```

**KoreanPhonemizer**:
```python
"""Korean phonemizer using g2pk2 and Hangul decomposition.

Known limitations:
- g2pk2 fallback quality: When g2pk2 is not installed, phonological
  rules (liaison, nasalization, aspiration, tensification) are not
  applied. Output quality degrades significantly.
- Limited liaison coverage: Even with g2pk2, some colloquial phonological
  changes (e.g., 의→에 weakening) are only partially covered.
- Not thread-safe: The global g2pk2 instance cache is not thread-safe.

Dependencies: g2pk2>=0.0.3 (Apache-2.0, optional)
"""
```

**SpanishPhonemizer**:
```python
"""Spanish rule-based phonemizer.

Known limitations:
- Seseo only: Latin American pronunciation (c/z → [s]). Castilian
  distinction (c/z → [θ]) is not supported.
- No dialect switching: Voseo, lleismo, s-aspiration, and other
  dialectal variations are not implemented.

Dependencies: None (pure rule-based)
"""
```

**FrenchPhonemizer**:
```python
"""French rule-based phonemizer.

Known limitations:
- Liaison not implemented: Obligatory liaison (e.g., "les amis" →
  /lez‿ami/) is not applied. This requires POS tagging and syntactic
  analysis which is beyond rule-based G2P.
- Schwa deletion: The e muet deletion rules are conservative. In
  natural speech, many schwas are dropped depending on dialect,
  speaking rate, and prosodic context.

Dependencies: None (pure rule-based)
"""
```

**PortuguesePhonemizer**:
```python
"""Brazilian Portuguese rule-based phonemizer.

Known limitations:
- BR-PT only: European Portuguese (EU-PT) is not supported. EU-PT
  differs significantly in vowel reduction, sibilant realization,
  and final consonant handling.
- No dialect variants: Carioca, Paulista, Mineiro, and other BR-PT
  regional variants are not distinguished.

Dependencies: None (pure rule-based)
"""
```

2. README.md を作成:

**構成**:
- Quick Start (インストール + 3 行コード例)
- Supported Languages (7 言語テーブル: 言語名, コード, 依存, ライセンス)
- Usage Examples (各言語の出力例)
- Multilingual Text (MultilingualPhonemizer の使用例)
- PiperEncoder (Piper TTS 統合の使用例)
- Custom Dictionary (JSON フォーマット仕様)
- Known Limitations (言語別の制限事項テーブル)
- API Reference (簡易版)
- License

3. Known Limitations セクションの内容:

| 言語 | 制限事項 |
|------|---------|
| JA | OpenJTalk の辞書精度に依存、未知語の読み推定精度は限定的 |
| EN | g2p-en の CMU Pronouncing Dictionary に未登録の語は letter-to-sound フォールバック |
| ZH | 再帰的声調サンドヒ未実装 (3 連続以上の三声) |
| KO | g2pk2 未インストール時はフォールバック品質、連音規則カバレッジ限定的 |
| ES | seseo のみ、方言切替なし |
| FR | liaison 未実装 |
| PT | BR-PT のみ、EU-PT 非対応 |

### API / インターフェース

該当なし (ドキュメントのみ)。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| ドキュメントエージェント | 1 | README 作成、docstring 追記、IPA 出力例の検証 |

---

## 4. テスト計画

### 提供範囲

ドキュメントの正確性を検証する。

### Unit テスト

| テストケース | 検証内容 |
|-------------|---------|
| README コード例 | README 内のコード例が実際に動作すること |
| IPA 出力例 | ドキュメント記載の入出力例が実装と一致すること |

### E2E テスト

- README の Quick Start セクションのコードが copy-paste で動作すること

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **出力例の維持コスト**: IPA 出力例は実装の変更に追従する必要がある。doctest 形式にすることで自動検証が可能になるが、pytest-doctest の設定が必要。
- **多言語ドキュメント**: 現時点では英語のみ。日本語ドキュメントの需要はあるが、Phase 1 スコープ外とする。

### レビュー項目

- [ ] 全 7 言語の既知制限がクラス docstring に記載されていること
- [ ] README に全言語のクイックスタート例があること
- [ ] README 内のコード例がすべて動作すること
- [ ] カスタム辞書の JSON スキーマ (v1.0/v2.0) が正確に記載されていること
- [ ] PiperEncoder の使用方法が記載されていること

---

## 6. 一から作り直すとしたら

ドキュメントを Sphinx / MkDocs で生成し、autodoc で docstring から自動生成する方式にする。これにより docstring とドキュメントの乖離を防げる。Phase 2 以降の検討事項。

---

## 7. 後続タスクへの連絡事項

- P1-011 (API 凍結): README の API Reference セクションが v1.0.0 の公式ドキュメントのベースとなる
- PyPI: README.md は pyproject.toml の `readme = "README.md"` で PyPI ページに表示される
