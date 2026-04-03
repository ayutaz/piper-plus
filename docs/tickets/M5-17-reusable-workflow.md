# M5-17: cpp-tests.yml / ci.yml 重複解消

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 低 -- CI 保守性の改善 (エンドユーザーには不可視)
> **見積り:** 小
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`cpp-tests.yml` と `ci.yml` の C++ テスト部分を reusable workflow (`_build-test-cpp.yml`) に抽出し、重複を解消する。

**現状の問題:** C++ のビルド・テスト手順が `cpp-tests.yml` (C API 専用) と `ci.yml` (全体 CI) の両方に記述されている。CMake オプション、キャッシュ設定、テストモデルのダウンロード手順が二重管理となっており、一方の更新が他方に反映されないリスクがある。

**ゴール:** C++ ビルド・テスト部分を `_build-test-cpp.yml` (reusable workflow) に抽出し、両ワークフローから `uses:` で呼び出す。

---

## 2. 実装する内容の詳細

### 2.1 reusable workflow 作成

**ファイル:** `.github/workflows/_build-test-cpp.yml`

```yaml
name: C++ Build & Test (reusable)
on:
  workflow_call:
    inputs:
      run-integration-tests:
        type: boolean
        default: true
      cmake-args:
        type: string
        default: ""
```

**ジョブ内容:**
- CMake configure + build (3 プラットフォーム matrix)
- 単体テスト実行
- テストモデルダウンロード + キャッシュ (integration-tests が true の場合)
- 統合テスト実行 (integration-tests が true の場合)

### 2.2 呼び出し元の更新

**`cpp-tests.yml`:**
```yaml
jobs:
  cpp-tests:
    uses: ./.github/workflows/_build-test-cpp.yml
    with:
      run-integration-tests: true
```

**`ci.yml`:**
```yaml
jobs:
  cpp-tests:
    uses: ./.github/workflows/_build-test-cpp.yml
    with:
      run-integration-tests: false  # ci.yml ではモデル不要テストのみ
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `.github/workflows/_build-test-cpp.yml` | 新規作成 (reusable workflow) |
| `.github/workflows/cpp-tests.yml` | C++ ビルド・テスト部分を `uses:` に置換 |
| `.github/workflows/ci.yml` | C++ テスト部分を `uses:` に置換 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | reusable workflow 作成 + 呼び出し元更新 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### スコープ

- reusable workflow の作成
- 既存 2 ワークフローの重複部分を `uses:` に置換
- CI 動作の回帰なし

### テスト項目

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| cpp-tests.yml 実行 | PR で C++ ファイル変更 | 3 プラットフォーム GREEN |
| ci.yml 実行 | PR で任意ファイル変更 | C++ テスト部分が GREEN |
| reusable workflow 単体 | `workflow_dispatch` でテスト | 正常完了 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| reusable workflow のトリガー制約 | 低 | `workflow_call` は同一リポジトリ内のみ。外部からの呼び出しは不要 |
| キャッシュキーの衝突 | 低 | 呼び出し元ごとに `inputs` でキャッシュプレフィックスを分離 |
| secrets の転送 | 低 | C++ テストに secrets は不要。必要になった場合は `secrets: inherit` で対応 |

### レビュー時の確認項目

1. reusable workflow の inputs が十分に柔軟であること
2. 両呼び出し元で CI が GREEN であること
3. テストモデルキャッシュが正しく動作すること

---

## 6. 一から作り直すとしたら

Phase 2 の M2-6 で `cpp-tests.yml` を作成した時点で reusable workflow にすべきだった。`ci.yml` との重複は M2-6 時点で予見可能だった。

---

## 7. 後続タスクへの連絡事項

- **M5-20 (Android AAR):** Android ビルドを追加する場合、`_build-test-cpp.yml` に `platform` input を追加して Android matrix を含められる設計にしておくこと。
